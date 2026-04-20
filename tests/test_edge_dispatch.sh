#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-dispatch-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

DISPATCH_TOOL="$EDGE_DIR/tools/edge-dispatch"
GUARD_TOOL="$EDGE_DIR/bin/heartbeat-dispatch-guard.sh"

echo "=== edge-dispatch Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: heartbeat open creates dispatch + legacy mirror ---"
"$DISPATCH_TOOL" open \
    --trigger heartbeat \
    --cycle-id cycle-test-heartbeat \
    --policy autonomous \
    --routing-mode auto \
    --arg topic=enforcement >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/current-beat.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
legacy = json.load(open(sys.argv[2], encoding="utf-8"))

assert dispatch["cycle_id"] == "cycle-test-heartbeat"
assert dispatch["request"]["trigger"] == "heartbeat"
assert dispatch["request"]["preflight_profile"] == "heartbeat_default"
assert dispatch["state"]["active"] is True
assert dispatch["state"]["skill_dispatched"] is False
assert legacy["active"] is True
assert legacy["skill_dispatched"] is False
PY
then
    pass "heartbeat open writes dispatch state and current-beat mirror"
else
    fail "heartbeat open writes dispatch state and current-beat mirror"
fi

echo "--- Test 2: guard blocks heartbeat artifact writes before dispatch ---"
BLOCK_PAYLOAD=$(python3 - <<'PY' "$TMP_EDGE"
import json
import sys
root = sys.argv[1]
print(json.dumps({
    "tool_name": "Write",
    "tool_input": {"file_path": f"{root}/blog/entries/test.md"},
}))
PY
)

set +e
EDGE_ROOT="$TMP_EDGE" bash "$GUARD_TOOL" <<<"$BLOCK_PAYLOAD" >/dev/null 2>/dev/null
STATUS=$?
set -e
if [[ "$STATUS" -eq 2 ]]; then
    pass "guard blocks heartbeat writes before skill dispatch"
else
    fail "guard blocks heartbeat writes before skill dispatch (exit=$STATUS)"
fi

echo "--- Test 3: dispatch marks skill and unblocks guard ---"
"$DISPATCH_TOOL" dispatch --skill research >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/current-beat.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
legacy = json.load(open(sys.argv[2], encoding="utf-8"))

assert dispatch["request"]["skill"] == "research"
assert dispatch["state"]["skill_dispatched"] is True
assert dispatch["state"]["skill_status"] == "running"
assert legacy["skill_dispatched"] is True
assert legacy["skill"] == "research"
PY
then
    pass "dispatch updates active cycle and legacy heartbeat mirror"
else
    fail "dispatch updates active cycle and legacy heartbeat mirror"
fi

if EDGE_ROOT="$TMP_EDGE" bash "$GUARD_TOOL" <<<"$BLOCK_PAYLOAD" >/dev/null 2>/dev/null; then
    pass "guard allows writes after dispatch"
else
    fail "guard allows writes after dispatch"
fi

echo "--- Test 3b: second dispatch with different skill is rejected ---"
set +e
SECOND_DISPATCH_OUTPUT=$("$DISPATCH_TOOL" dispatch --skill autonomy 2>&1)
SECOND_DISPATCH_STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$SECOND_DISPATCH_STATUS" "$SECOND_DISPATCH_OUTPUT"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
status = int(sys.argv[3])
output = sys.argv[4]

assert status == 1
assert dispatch["request"]["skill"] == "research"
assert dispatch["state"]["phase"] == "skill_dispatched"
assert len([event for event in events if event["type"] == "SkillDispatched"]) == 1
assert "already dispatched" in output
PY
then
    pass "second dispatch with a different skill is rejected"
else
    fail "second dispatch with a different skill is rejected"
fi

echo "--- Test 3c: repeated dispatch with same skill is idempotent ---"
"$DISPATCH_TOOL" dispatch --skill research >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
assert len([event for event in events if event["type"] == "SkillDispatched"]) == 1
PY
then
    pass "repeated dispatch with same skill is a no-op"
else
    fail "repeated dispatch with same skill is a no-op"
fi

echo "--- Test 4: close emits inactive state and shadow events ---"
"$DISPATCH_TOOL" close --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
with open(sys.argv[2], encoding="utf-8") as f:
    events = [json.loads(line) for line in f if line.strip()]

types = [event["type"] for event in events]
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert types.count("CycleStarted") == 1
assert types.count("SkillDispatched") == 1
assert types.count("CycleClosed") == 1
PY
then
    pass "close finalizes state and emits CycleClosed"
else
    fail "close finalizes state and emits CycleClosed"
fi

echo "--- Test 5: operator cycle suppresses legacy heartbeat guard fallback ---"
python3 - <<'PY' "$TMP_EDGE/state/current-beat.json"
import json
import sys
from datetime import datetime, timezone

payload = {
    "active": True,
    "started_at": datetime.now(timezone.utc).isoformat(),
    "skill_dispatched": False,
    "skill": None,
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(payload, f)
PY

"$DISPATCH_TOOL" open \
    --trigger operator \
    --cycle-id cycle-test-operator \
    --skill reflection \
    --arg topic=enforcement >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
assert dispatch["request"]["trigger"] == "operator"
assert dispatch["request"]["skill"] == "reflection"
assert dispatch["request"]["preflight_profile"] == "operator_default"
assert dispatch["request"]["args"]["topic"] == "enforcement"
PY
then
    pass "operator open writes canonical operator request"
else
    fail "operator open writes canonical operator request"
fi

if EDGE_ROOT="$TMP_EDGE" bash "$GUARD_TOOL" <<<"$BLOCK_PAYLOAD" >/dev/null 2>/dev/null; then
    pass "operator cycle bypasses stale legacy heartbeat sentinel"
else
    fail "operator cycle bypasses stale legacy heartbeat sentinel"
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
