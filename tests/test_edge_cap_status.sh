#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-cap-status-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
TMP_BIN="$TMP_BASE/bin"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state" "$TMP_STATE/libexec/captest" "$TMP_BIN"

cat >"$TMP_BIN/edge-search" <<'EOF'
#!/usr/bin/env bash
echo "edge-search $*"
EOF
cat >"$TMP_BIN/edge-sources" <<'EOF'
#!/usr/bin/env bash
echo "edge-sources $*"
EOF
cat >"$TMP_BIN/edge-workflows" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "status" ]]; then
  echo '{"summary":{"workflow_total":1,"cited_total":1,"broken_total":0,"stale_total":0,"top_used":[],"top_broken":[]},"workflows":[]}'
else
  echo "edge-workflows $*"
fi
EOF
cat >"$TMP_BIN/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*"
EOF
chmod +x "$TMP_BIN/edge-search" "$TMP_BIN/edge-sources" "$TMP_BIN/edge-workflows" "$TMP_BIN/git"

cat >"$TMP_STATE/state/sources-manifest.yaml" <<'YAML'
sources:
  - name: arxiv
    description: Academic preprints
    status: active
YAML
cat >"$TMP_STATE/libexec/captest/arxiv" <<'EOF'
#!/usr/bin/env bash
echo '{"ok":true,"source":"arxiv"}'
EOF
chmod +x "$TMP_STATE/libexec/captest/arxiv"
cat >"$TMP_STATE/libexec/captest/arxiv.meta.yaml" <<'YAML'
name: arxiv
description: Academic preprints
YAML

echo "=== edge-cap status Smoke Test ==="
OUTPUT=$(PATH="$TMP_BIN" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" status --json --skill research)

if python3 - <<'PY' "$OUTPUT"
import json, sys
payload = json.loads(sys.argv[1])
summary = payload["summary"]
assert summary["capability_total"] >= 5
assert summary["health_status"] == "degraded"
names = {item["name"]: item for item in payload["capabilities"]}
assert names["search.corpus"]["effective_status"] == "available"
assert names["sources.aggregate"]["effective_status"] == "available"
assert names["workflow.recommend"]["effective_status"] == "available"
assert names["repo.status"]["effective_status"] == "available"
assert names["storage.sync"]["effective_status"] == "degraded"
assert names["source.arxiv"]["effective_status"] in {"active", "probed"}
recommended = {item["name"] for item in payload["recommended"]}
assert "search.corpus" in recommended
assert "sources.aggregate" in recommended
PY
then
  pass "status merges static and primitive capabilities"
else
  fail "status merges static and primitive capabilities"
fi

if [[ -f "$TMP_STATE/state/capabilities-status.json" ]]; then
  pass "capabilities status snapshot written"
else
  fail "capabilities status snapshot missing"
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
