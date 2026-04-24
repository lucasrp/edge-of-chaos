#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-context-XXXXXX)"
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

mkdir -p "$TMP_STATE/health" "$TMP_STATE/state/events" "$TMP_BIN"

cat >"$TMP_STATE/health/current.json" <<'JSON'
{"schema_version":2,"status":"healthy","score":91,"hard_fail":false,"dimensions":{}}
JSON
cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{"summary":{"health_status":"ok","broken_total":0,"degraded_total":0},"sources":[]}
JSON
cat >"$TMP_STATE/state/capabilities-status.json" <<'JSON'
{"summary":{"health_status":"ok","broken_total":0,"degraded_total":0},"capabilities":[]}
JSON

cat >"$TMP_BIN/edge-sources-fake" <<'SH'
#!/usr/bin/env bash
cat <<'JSON'
{
  "exa": {
    "results": [
      {"title": "Meta event planning", "url": "https://example.test/meta", "source": "Exa", "detail": "conversion window", "score": 10}
    ],
    "wildcard": false
  }
}
JSON
SH
chmod +x "$TMP_BIN/edge-sources-fake"

echo "=== edge-context Smoke Test ==="
OUTPUT=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="contexttest" EDGE_SOURCES_BIN="$TMP_BIN/edge-sources-fake" \
  "$EDGE_DIR/tools/edge-context" --query "meta events" --mode all --intent research --json --no-wildcard)

if python3 - <<'PY' "$OUTPUT"
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["schema_version"] == 1
assert payload["query"] == "meta events"
assert payload["mode"] == "all"
assert isinstance(payload["signals"], dict)
assert isinstance(payload["sources"], dict)
assert payload["sources"]["ok"] is True
assert "exa" in payload["sources"]["results_by_source"]
summary = payload["summary"]
assert summary["signals_returned"] >= 1
assert summary["source_total"] == 1
assert summary["source_result_total"] == 1
PY
then
  pass "edge-context preserves signals and sources lanes"
else
  fail "edge-context preserves signals and sources lanes"
fi

SOURCE_ONLY=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" EDGE_CODENAME="contexttest" EDGE_SOURCES_BIN="$TMP_BIN/edge-sources-fake" \
  "$EDGE_DIR/tools/edge-context" --query "meta events" --mode sources --json --no-wildcard)

if python3 - <<'PY' "$SOURCE_ONLY"
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["signals"] is None
assert payload["sources"]["ok"] is True
assert payload["summary"]["source_total"] == 1
PY
then
  pass "edge-context can run sources-only mode"
else
  fail "edge-context can run sources-only mode"
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
