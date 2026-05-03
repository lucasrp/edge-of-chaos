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
cat >"$TMP_BIN/edge-signals" <<'EOF'
#!/usr/bin/env bash
echo "edge-signals $*"
EOF
cat >"$TMP_BIN/edge-context" <<'EOF'
#!/usr/bin/env bash
echo "edge-context $*"
EOF
cat >"$TMP_BIN/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*"
EOF
cat >"$TMP_BIN/edge-repo-sync" <<'EOF'
#!/usr/bin/env bash
echo "edge-repo-sync $*"
EOF
chmod +x "$TMP_BIN/edge-search" "$TMP_BIN/edge-sources" "$TMP_BIN/edge-signals" "$TMP_BIN/edge-context" "$TMP_BIN/git" "$TMP_BIN/edge-repo-sync"

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
assert summary["capability_total"] >= 6
assert summary["health_status"] == "degraded"
names = {item["name"]: item for item in payload["capabilities"]}
assert names["search.corpus"]["effective_status"] == "available"
assert names["sources.aggregate"]["effective_status"] == "available"
assert names["signals.aggregate"]["effective_status"] == "available"
assert names["context.aggregate"]["effective_status"] == "available"
assert names["repo.status"]["effective_status"] == "available"
assert names["repo.sync"]["effective_status"] == "available"
assert names["storage.sync"]["effective_status"] == "degraded"
assert names["source.arxiv"]["effective_status"] in {"active", "probed"}
source_bindings = payload["source_bindings"]
assert source_bindings["summary"]["source_total"] == 1
assert source_bindings["bindings"][0]["source"] == "arxiv"
assert source_bindings["bindings"][0]["binding_status"] == "present"
recommended = {item["name"] for item in payload["recommended"]}
assert "search.corpus" in recommended
assert "sources.aggregate" in recommended
PY
then
  pass "status merges static and primitive capabilities"
else
  fail "status merges static and primitive capabilities"
fi

SOURCE_BINDINGS_OUTPUT=$(PATH="$TMP_BIN" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" source-bindings --json --skill research)
if python3 - <<'PY' "$SOURCE_BINDINGS_OUTPUT"
import json, sys
payload = json.loads(sys.argv[1])
assert payload["summary"]["source_total"] == 1
assert payload["summary"]["bound_total"] == 1
assert payload["bindings"][0]["capability"] == "sources.aggregate"
PY
then
  pass "source binding surface resolves manifest sources"
else
  fail "source binding surface resolves manifest sources"
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
