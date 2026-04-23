#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-publish-guard-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state/events"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="publish-guard-test"

GUARD_TOOL="$EDGE_DIR/tools/edge-publish-guard"
DISPATCH_FILE="$TMP_EDGE/state/current-dispatch.json"
EVENTS_FILE="$TMP_EDGE/state/events/log.jsonl"

echo "=== edge-publish-guard Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: no active cycle allows publish ---"
if "$GUARD_TOOL" --operation blog-publish --target "$TMP_EDGE/blog/entries/test.md" >/dev/null; then
    pass "guard allows publish with no active cycle"
else
    fail "guard allows publish with no active cycle"
fi

echo "--- Test 2: active heartbeat before dispatch is blocked and emits event ---"
cat >"$DISPATCH_FILE" <<'JSON'
{
  "cycle_id": "cycle-heartbeat-inline",
  "request": {
    "trigger": "heartbeat",
    "skill": "bob-heartbeat"
  },
  "state": {
    "active": true,
    "skill_dispatched": false
  }
}
JSON

set +e
"$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/test.md" >/dev/null 2>/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$STATUS" "$EVENTS_FILE"
import json
import sys
status = int(sys.argv[1])
events_path = sys.argv[2]
events = [json.loads(line) for line in open(events_path, encoding="utf-8") if line.strip()]
assert status == 2
event = [item for item in events if item["type"] == "HeartbeatInlineWorkDetected"][-1]
assert event["payload"]["operation"] == "consolidate-state"
assert event["payload"]["skill"] == "bob-heartbeat"
assert event["payload"]["skill_dispatched"] is False
PY
then
    pass "guard blocks inline publish before dispatch and emits event"
else
    fail "guard blocks inline publish before dispatch and emits event"
fi

echo "--- Test 3: dispatched substantive skill allows publish ---"
cat >"$DISPATCH_FILE" <<'JSON'
{
  "cycle_id": "cycle-heartbeat-dispatched",
  "request": {
    "trigger": "heartbeat",
    "skill": "research"
  },
  "state": {
    "active": true,
    "skill_dispatched": true
  }
}
JSON

if "$GUARD_TOOL" --operation blog-publish --target "$TMP_EDGE/blog/entries/test.md" >/dev/null; then
    pass "guard allows publish after substantive dispatch"
else
    fail "guard allows publish after substantive dispatch"
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
