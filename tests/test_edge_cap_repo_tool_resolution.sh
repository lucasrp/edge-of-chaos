#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-cap-repo-tools-XXXXXX)"
TMP_STATE="$TMP_BASE/state"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE"

echo "=== edge-cap repo tool resolution Smoke Test ==="
OUTPUT=$(PATH="" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="captest" \
  /usr/bin/python3 "$EDGE_DIR/tools/edge-cap" status --json --skill research)

if python3 - <<'PY' "$OUTPUT"
import json, sys
payload = json.loads(sys.argv[1])
names = {item["name"]: item for item in payload["capabilities"]}
assert names["search.corpus"]["effective_status"] == "available"
assert names["sources.aggregate"]["effective_status"] == "available"
assert names["signals.aggregate"]["effective_status"] == "available"
assert names["context.aggregate"]["effective_status"] == "available"
assert names["repo.sync"]["effective_status"] == "available"
PY
then
  pass "repo-local edge-* tools resolve without PATH"
else
  fail "repo-local edge-* tools resolve without PATH"
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
