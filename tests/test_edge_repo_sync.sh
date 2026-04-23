#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-repo-sync-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO"

git -C "$TMP_REPO" init -b main >/dev/null
git -C "$TMP_REPO" config user.name "Codex Test"
git -C "$TMP_REPO" config user.email "codex@example.com"

mkdir -p "$TMP_REPO/tools"
cat >"$TMP_REPO/tools/demo.sh" <<'EOF'
#!/usr/bin/env bash
echo demo
EOF
chmod +x "$TMP_REPO/tools/demo.sh"
git -C "$TMP_REPO" add tools/demo.sh
git -C "$TMP_REPO" commit -m "initial" >/dev/null
BASE_SHA=$(git -C "$TMP_REPO" rev-parse HEAD)

mkdir -p "$TMP_REPO/bin"
cat >"$TMP_REPO/bin/new-tool.sh" <<'EOF'
#!/usr/bin/env bash
echo new
EOF
chmod +x "$TMP_REPO/bin/new-tool.sh"
git -C "$TMP_REPO" add bin/new-tool.sh
git -C "$TMP_REPO" commit -m "add new tool" >/dev/null

echo "changed" >>"$TMP_REPO/tools/demo.sh"
mkdir -p "$TMP_REPO/state" "$TMP_REPO/config"
cat >"$TMP_REPO/state/local.json" <<'EOF'
{"state":"local"}
EOF
cat >"$TMP_REPO/config/preflight.yaml" <<'EOF'
version: 1
protocol: preflight
EOF

echo "=== edge-repo-sync Smoke Test ==="

STATUS_JSON=$(/usr/bin/python3 "$EDGE_DIR/tools/edge-repo-sync" --repo "$TMP_REPO" status --ref "$BASE_SHA" --json)
if python3 - <<'PY' "$STATUS_JSON"
import json, sys
payload = json.loads(sys.argv[1])
assert payload["head_sha"]
assert payload["ref_sha"]
assert payload["ahead_count"] == 1
assert payload["tracked_dirty_count"] == 1
assert payload["untracked_count"] == 2
assert payload["exact_code"] is False
PY
then
  pass "status reports ahead/dirty state"
else
  fail "status reports ahead/dirty state"
fi

AUDIT_JSON=$(/usr/bin/python3 "$EDGE_DIR/tools/edge-repo-sync" --repo "$TMP_REPO" audit --ref "$BASE_SHA" --json)
if python3 - <<'PY' "$AUDIT_JSON"
import json, sys
payload = json.loads(sys.argv[1])
assert payload["local_only_commit_count"] == 1
commits = payload["local_only_commits"]
assert commits[0]["subject"] == "add new tool"
local_files = {item["path"]: item["classification"] for item in payload["local_only_versioned_files"]}
assert local_files["bin/new-tool.sh"] == "genotype_candidate"
tracked = {item["path"]: item["classification"] for item in payload["status"]["tracked_dirty_files"]}
assert tracked["tools/demo.sh"] == "genotype_candidate"
untracked = {item["path"]: item["classification"] for item in payload["status"]["untracked_files"]}
assert untracked["state/local.json"] == "state_only"
assert untracked["config/preflight.yaml"] == "host_migration"
PY
then
  pass "audit classifies genotype, host migration, and state drift"
else
  fail "audit classifies genotype, host migration, and state drift"
fi

set +e
/usr/bin/python3 "$EDGE_DIR/tools/edge-repo-sync" --repo "$TMP_REPO" sync-exact-code --ref "$BASE_SHA" >/dev/null 2>&1
SYNC_STATUS=$?
set -e
if [[ "$SYNC_STATUS" -eq 2 ]]; then
  pass "sync-exact-code blocks without --force when tracked code is dirty"
else
  fail "sync-exact-code blocks without --force when tracked code is dirty"
fi

SYNC_JSON=$(/usr/bin/python3 "$EDGE_DIR/tools/edge-repo-sync" --repo "$TMP_REPO" sync-exact-code --ref "$BASE_SHA" --force --json)
if python3 - <<'PY' "$SYNC_JSON" "$TMP_REPO" "$BASE_SHA"
import json, sys
from pathlib import Path
payload = json.loads(sys.argv[1])
repo = Path(sys.argv[2])
base_sha = sys.argv[3]
assert payload["status"]["head_sha"] == base_sha
assert payload["status"]["tracked_dirty_count"] == 0
assert payload["status"]["exact_code"] is True
assert (repo / "state" / "local.json").exists()
assert (repo / "config" / "preflight.yaml").exists()
assert not (repo / "bin" / "new-tool.sh").exists()
PY
then
  pass "sync-exact-code resets tracked code while preserving untracked state"
else
  fail "sync-exact-code resets tracked code while preserving untracked state"
fi

echo ""
echo "=== Results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "SOME TESTS FAILED"
  exit 1
fi
