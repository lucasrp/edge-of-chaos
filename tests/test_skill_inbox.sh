#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-skill-inbox-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state" "$TMP_EDGE/logs" "$TMP_EDGE/search"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

DISPATCH_TOOL="$EDGE_DIR/tools/edge-dispatch"
CLOSE_TOOL="$EDGE_DIR/tools/edge-close"
STEP_TOOL="$EDGE_DIR/tools/edge-skill-step"
INBOX_TOOL="$EDGE_DIR/tools/edge-skill-inbox"

echo "=== edge-skill-inbox Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: dispatch captures a deterministic async inbox snapshot ---"
SEED_OUTPUT=$(python3 - <<'PY' "$EDGE_DIR"
import json
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, edge_dir + "/search")
from dashboard_db import add_chat, pin_chat

direct_id = add_chat("user", "Prioritize operator feedback before exploration.")
task_id = add_chat("user", "\n".join([
    "[task-intent]",
    "task: TASK-001",
    "action: prioritize",
    "apply: next-dispatch",
    "reason: user interaction always wins",
]))
steering_id = add_chat("user", "\n".join([
    "[steering-intent]",
    "target_type: topic",
    "target_id: operator-feedback",
    "action: prioritize",
    "label: operator feedback",
    "apply: next-dispatch",
]))
runtime_id = add_chat("user", "\n".join([
    "[runtime-intent]",
    "target_type: primitive",
    "target_id: primitives-status",
    "action: stable",
    "label: primitives status cli",
    "apply: next-dispatch",
]))
pinned_id = add_chat("user", "User interaction is priority.")
pin_chat(pinned_id)

print(json.dumps({
    "captured_ids": [direct_id, task_id, steering_id, runtime_id, pinned_id],
    "pinned_id": pinned_id,
}))
PY
)

"$DISPATCH_TOOL" open \
    --trigger heartbeat \
    --cycle-id cycle-skill-inbox \
    --postflight-profile none >/dev/null
"$DISPATCH_TOOL" dispatch --skill research >/dev/null

LATE_OUTPUT=$(python3 - <<'PY' "$EDGE_DIR"
import json
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, edge_dir + "/search")
from dashboard_db import add_chat

late_id = add_chat("user", "This message arrived after dispatch and should wait for the next cycle.")
print(json.dumps({"late_id": late_id}))
PY
)

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$SEED_OUTPUT" "$LATE_OUTPUT"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
seed = json.loads(sys.argv[2])
late = json.loads(sys.argv[3])
inbox = dispatch["request"]["async_inbox"]

assert inbox["priority"] == "high"
assert inbox["priority_reason"] == "user_async_input"
assert inbox["dispatch_guidance"].startswith("user interaction is priority")
assert inbox["skill"] == "research"
assert inbox["unprocessed_total"] == 5
assert inbox["pinned_total"] == 1
assert inbox["message_ids"] == seed["captured_ids"]
assert len(inbox["direct_messages"]) == 2
assert len(inbox["task_intents"]) == 1
assert len(inbox["steering_intents"]) == 1
assert len(inbox["runtime_intents"]) == 1
assert seed["pinned_id"] in [item["chat_id"] for item in inbox["pinned_messages"]]
assert late["late_id"] not in inbox["message_ids"]
PY
then
    pass "dispatch captures operator-priority inbox without late arrivals"
else
    fail "dispatch captures operator-priority inbox without late arrivals"
fi

echo "--- Test 2: edge-skill-inbox read returns the captured dispatch snapshot ---"
if python3 - <<'PY' "$("$INBOX_TOOL" read --skill research)" "$SEED_OUTPUT" "$LATE_OUTPUT"
import json
import sys

snapshot = json.loads(sys.argv[1])
seed = json.loads(sys.argv[2])
late = json.loads(sys.argv[3])

assert snapshot["message_ids"] == seed["captured_ids"]
assert snapshot["unprocessed_total"] == 5
assert late["late_id"] not in snapshot["message_ids"]
assert snapshot["priority"] == "high"
PY
then
    pass "edge-skill-inbox read is deterministic during an active cycle"
else
    fail "edge-skill-inbox read is deterministic during an active cycle"
fi

echo "--- Test 3: successful close consumes only the captured inbox ---"
EDGE_CYCLE_ID=cycle-skill-inbox "$STEP_TOOL" research start >/dev/null
EDGE_CYCLE_ID=cycle-skill-inbox "$STEP_TOOL" research end >/dev/null
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$EDGE_DIR" "$SEED_OUTPUT" "$LATE_OUTPUT" "$TMP_EDGE/state/current-dispatch.json"
import json
import sys

edge_dir = sys.argv[1]
seed = json.loads(sys.argv[2])
late = json.loads(sys.argv[3])
dispatch = json.load(open(sys.argv[4], encoding="utf-8"))

sys.path.insert(0, edge_dir + "/search")
from dashboard_db import get_chats

messages = {int(item["id"]): item for item in get_chats(limit=20)}
for chat_id in seed["captured_ids"]:
    assert messages[chat_id]["processed"] == 1
assert messages[seed["pinned_id"]]["pinned"] == 1
assert messages[late["late_id"]]["processed"] == 0

inbox = dispatch["request"]["async_inbox"]
assert dispatch["state"]["close_status"] == "completed"
assert inbox["processed_count"] == 5
assert inbox["processed_message_ids"] == seed["captured_ids"]
assert "processed_at" in inbox
PY
then
    pass "edge-close consumes captured ids and leaves late input for the next cycle"
else
    fail "edge-close consumes captured ids and leaves late input for the next cycle"
fi

echo "--- Test 4: after close, read falls back to the live inbox ---"
if python3 - <<'PY' "$("$INBOX_TOOL" read --skill research)" "$LATE_OUTPUT"
import json
import sys

snapshot = json.loads(sys.argv[1])
late = json.loads(sys.argv[2])

assert snapshot["message_ids"] == [late["late_id"]]
assert snapshot["unprocessed_total"] == 1
assert snapshot["priority"] == "high"
PY
then
    pass "edge-skill-inbox read falls back to live inbox when the cycle is inactive"
else
    fail "edge-skill-inbox read falls back to live inbox when the cycle is inactive"
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
