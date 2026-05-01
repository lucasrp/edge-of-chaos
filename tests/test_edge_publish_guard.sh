#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-publish-guard-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
MANUAL_OUT="$TMP_BASE/manual.out"
OPERATOR_OUT="$TMP_BASE/operator.out"
EXPIRED_OUT="$TMP_BASE/expired.out"
ACTIVE_OPERATOR_OUT="$TMP_BASE/active-operator.out"
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
FUTURE_EXPIRES_AT="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
PY
)"
cat >"$DISPATCH_FILE" <<'JSON'
{
  "cycle_id": "cycle-heartbeat-inline",
  "request": {
    "trigger": "heartbeat",
    "skill": "bob-heartbeat"
  },
  "state": {
    "active": true,
    "skill_dispatched": false,
    "expires_at": "__FUTURE_EXPIRES_AT__"
  }
}
JSON
python3 - <<'PY' "$DISPATCH_FILE" "$FUTURE_EXPIRES_AT"
import pathlib, sys
path = pathlib.Path(sys.argv[1])
path.write_text(path.read_text().replace("__FUTURE_EXPIRES_AT__", sys.argv[2]), encoding="utf-8")
PY

set +e
EDGE_CYCLE_ID=cycle-heartbeat-inline "$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/test.md" >/dev/null 2>/dev/null
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
assert event["payload"]["publisher_cycle_id"] == "cycle-heartbeat-inline"
PY
then
    pass "guard blocks same-cycle inline publish before dispatch and emits event"
else
    fail "guard blocks same-cycle inline publish before dispatch and emits event"
fi

echo "--- Test 3: active heartbeat without publisher cycle allows manual publish ---"
if "$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/manual.md" >"$MANUAL_OUT"; then
    pass "guard allows unscoped manual publish while heartbeat is active"
else
    cat "$MANUAL_OUT"
    fail "guard allows unscoped manual publish while heartbeat is active"
fi

echo "--- Test 4: different publisher cycle allows parallel operator publish ---"
if EDGE_CYCLE_ID=cycle-operator-work "$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/operator.md" >"$OPERATOR_OUT"; then
    pass "guard allows different-cycle operator publish while heartbeat is active"
else
    cat "$OPERATOR_OUT"
    fail "guard allows different-cycle operator publish while heartbeat is active"
fi

echo "--- Test 5: dispatched substantive skill allows publish ---"
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

echo "--- Test 6: expired heartbeat cycle does not block same-cycle publish ---"
PAST_EXPIRES_AT="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
PY
)"
cat >"$DISPATCH_FILE" <<JSON
{
  "cycle_id": "cycle-heartbeat-expired",
  "request": {
    "trigger": "heartbeat",
    "skill": "bob-heartbeat"
  },
  "state": {
    "active": true,
    "skill_dispatched": false,
    "expires_at": "$PAST_EXPIRES_AT"
  }
}
JSON

if EDGE_CYCLE_ID=cycle-heartbeat-expired "$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/expired.md" --json >"$EXPIRED_OUT"; then
    if grep -q "expired_heartbeat_cycle" "$EXPIRED_OUT"; then
        pass "guard ignores expired heartbeat cycles"
    else
        cat "$EXPIRED_OUT"
        fail "guard reports expired heartbeat cycles"
    fi
else
    cat "$EXPIRED_OUT"
    fail "guard ignores expired heartbeat cycles"
fi

echo "--- Test 7: active operator cycle never blocks publish ---"
cat >"$DISPATCH_FILE" <<'JSON'
{
  "cycle_id": "cycle-operator",
  "request": {
    "trigger": "operator",
    "skill": "research"
  },
  "state": {
    "active": true,
    "skill_dispatched": false
  }
}
JSON

if EDGE_CYCLE_ID=cycle-operator "$GUARD_TOOL" --operation consolidate-state --target "$TMP_EDGE/blog/entries/operator-active.md" --json >"$ACTIVE_OPERATOR_OUT"; then
    if grep -q "non_heartbeat_cycle" "$ACTIVE_OPERATOR_OUT"; then
        pass "guard allows active operator cycles"
    else
        cat "$ACTIVE_OPERATOR_OUT"
        fail "guard reports active operator cycles"
    fi
else
    cat "$ACTIVE_OPERATOR_OUT"
    fail "guard allows active operator cycles"
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
