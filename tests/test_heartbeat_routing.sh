#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-heartbeat-routing-XXXXXX)"
TMP_REPO="$TMP_BASE/repo"
TMP_STATE="$TMP_BASE/state"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_REPO/config" "$TMP_STATE" "$TMP_HOME"

export HOME="$TMP_HOME"
export EDGE_REPO_DIR="$TMP_REPO"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CODENAME="routing-test"

echo "=== heartbeat routing Smoke Test ==="
echo "Temp state: $TMP_STATE"
echo ""

echo "--- Test 1: heartbeat routing exposes explicit action-skill fairness lane ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.dispatch_runtime import HEARTBEAT_FAIRNESS_SKILLS, prepare_heartbeat_routing

state = {
    "cycle_id": "cycle-routing-1",
    "request": {
        "trigger": "heartbeat",
        "skill": "heartbeat",
        "async_inbox": {"priority": "normal", "direct_messages": [], "steering_intents": []},
        "dispatch_queue_summary": {"pending_total": 0, "head": None},
    },
    "state": {},
}
routing = prepare_heartbeat_routing(state, skill="heartbeat")
assert routing is not None
assert tuple(routing["round_robin_skills"]) == HEARTBEAT_FAIRNESS_SKILLS
assert routing["suggested_skill"] == "report"
assert routing["priority_hints"] == []
PY
then
    pass "heartbeat routing exposes explicit action-skill fairness lane"
else
    fail "heartbeat routing exposes explicit action-skill fairness lane"
fi

echo "--- Test 2: fairness cursor only advances when the suggested skill is actually dispatched ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE/state/heartbeat-rotation.json"
import json
import sys
from pathlib import Path

edge_dir, rotation_path = sys.argv[1:]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.dispatch_runtime import acknowledge_heartbeat_routing, prepare_heartbeat_routing

state = {
    "cycle_id": "cycle-routing-2",
    "request": {
        "trigger": "heartbeat",
        "skill": "heartbeat",
        "async_inbox": {"priority": "normal", "direct_messages": [], "steering_intents": []},
        "dispatch_queue_summary": {"pending_total": 0, "head": None},
    },
    "state": {},
}
prepare_heartbeat_routing(state, skill="heartbeat")
ack = acknowledge_heartbeat_routing(state, dispatched_skill="discovery", dispatch_mode="normal")
assert ack is not None
assert ack["acknowledged"] is False
assert not Path(rotation_path).exists()

ack = acknowledge_heartbeat_routing(state, dispatched_skill="report", dispatch_mode="normal")
assert ack is not None
assert ack["acknowledged"] is True
saved = json.loads(Path(rotation_path).read_text(encoding="utf-8"))
assert saved["cursor"] == 1
assert saved["last_acknowledged_skill"] == "report"

next_state = {
    "cycle_id": "cycle-routing-3",
    "request": {
        "trigger": "heartbeat",
        "skill": "heartbeat",
        "async_inbox": {"priority": "normal", "direct_messages": [], "steering_intents": []},
        "dispatch_queue_summary": {"pending_total": 0, "head": None},
    },
    "state": {},
}
next_routing = prepare_heartbeat_routing(next_state, skill="heartbeat")
assert next_routing is not None
assert next_routing["suggested_skill"] == "research"
PY
then
    pass "fairness cursor only advances when the suggested skill is actually dispatched"
else
    fail "fairness cursor only advances when the suggested skill is actually dispatched"
fi

echo "--- Test 3: priority hints override fairness when queue or inbox is hot ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.dispatch_runtime import prepare_heartbeat_routing

state = {
    "cycle_id": "cycle-routing-4",
    "request": {
        "trigger": "heartbeat",
        "skill": "heartbeat",
        "async_inbox": {"priority": "high", "direct_messages": [{"id": "m1"}], "steering_intents": []},
        "dispatch_queue_summary": {"pending_total": 1, "head": {"skill": "planner", "source": "internal-curation"}},
    },
    "state": {},
}
routing = prepare_heartbeat_routing(state, skill="heartbeat")
assert routing is not None
hints = routing["priority_hints"]
assert hints[0]["reason"] == "dispatch_queue_pending"
assert hints[0]["skill"] == "planner"
assert any(item["reason"] == "async_inbox_priority" and item["skill"] == "planner" for item in hints)
PY
then
    pass "priority hints override fairness when queue or inbox is hot"
else
    fail "priority hints override fairness when queue or inbox is hot"
fi

echo "--- Test 4: self-healing unknown primitive failures hint autonomy ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.dispatch_runtime import prepare_heartbeat_routing

state = {
    "cycle_id": "cycle-routing-5",
    "request": {
        "trigger": "heartbeat",
        "skill": "heartbeat",
        "async_inbox": {"priority": "normal", "direct_messages": [], "steering_intents": []},
        "dispatch_queue_summary": {"pending_total": 0, "head": None},
        "self_healing": {"needs_llm": [{"primitive": "exa"}]},
    },
    "state": {},
}
routing = prepare_heartbeat_routing(state, skill="heartbeat")
assert routing is not None
assert any(item["reason"] == "self_healing_needs_llm" and item["skill"] == "autonomy" for item in routing["priority_hints"])
PY
then
    pass "self-healing unknown primitive failures hint autonomy"
else
    fail "self-healing unknown primitive failures hint autonomy"
fi

echo "--- Test 5: policy-only memory does not force planner routing ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_STATE/state/heartbeat-rotation.json"
import sys
from pathlib import Path

edge_dir, rotation_path = sys.argv[1:]
Path(rotation_path).unlink(missing_ok=True)
sys.path.insert(0, f"{edge_dir}/tools")
from _shared.dispatch_runtime import _recommend_action_skill, build_beat_launch_context

policy_request = {
    "operator_pressure_digest": {
        "signal_from_operator_now": [
            {
                "kind": "memory_update",
                "target": "policy",
                "source_kinds": ["memory"],
                "text": "Genotype workflow: issue -> clone -> PR -> merge -> close -> deploy",
            }
        ],
        "memory_updates": [
            {
                "kind": "memory_update",
                "target": "policy",
                "source_kinds": ["memory"],
                "text": "Genotype workflow: issue -> clone -> PR -> merge -> close -> deploy",
            }
        ],
    },
    "open_gaps_summary": {"open_total": 0},
}
beat_launch = build_beat_launch_context(policy_request)
skill, reason = _recommend_action_skill(policy_request, beat_launch)
assert skill == "report"
assert "no dominant" in reason

actionable_request = {
    "operator_pressure_digest": {
        "signal_from_operator_now": [
            {
                "kind": "task_intent",
                "target": "repo",
                "source_kinds": ["session"],
                "text": "Corrija a issue 499, abra PR e deploy.",
            }
        ],
    },
    "open_gaps_summary": {"open_total": 0},
}
beat_launch = build_beat_launch_context(actionable_request)
skill, reason = _recommend_action_skill(actionable_request, beat_launch)
assert skill == "planner"
assert "execution sequencing" in reason
PY
then
    pass "policy-only memory does not force planner routing"
else
    fail "policy-only memory does not force planner routing"
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
