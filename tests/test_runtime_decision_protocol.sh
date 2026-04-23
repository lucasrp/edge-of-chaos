#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== runtime decision protocol Test ==="
echo ""

echo "--- Test 1: substantive skills receive mandatory search + epistemic protocol ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))

from _shared.dispatch_runtime import _epistemic_protocol, _search_protocol, render_skill_runtime_prompt

request = {
    "skill": "research",
    "corpus_query": "heartbeat dispatch timeout",
    "configured_integrations": [],
    "unbound_integrations": [],
    "search_runtime": {
        "builtin_web_search": False,
        "web_provider": "exa",
        "web_fallback": "claude_web",
        "builtin_web_search_unlocked": False,
    },
}
search_protocol = _search_protocol("research", request)
epistemic_protocol = _epistemic_protocol("research")

assert search_protocol["required"] is True
assert search_protocol["required_internal_coverage"] == ["topic", "workflow", "memory"]
assert search_protocol["rounds"][0]["id"] == "search_round_1"
assert search_protocol["rounds"][1]["id"] == "adversarial_interpretation"
assert search_protocol["rounds"][2]["id"] == "search_round_2"
assert search_protocol["fallback"]["allowed"] is True
assert epistemic_protocol["required"] is True
assert len(epistemic_protocol["checkpoints"]) == 3

state = {
    "request": {
        "schema_version": 1,
        "skill": "research",
        "runtime_policy": {},
        "pre_skill_context": {},
        "preflight_evidence": [],
        "corpus_query": "heartbeat dispatch timeout",
        "corpus_coverage": {"required": [], "optional": [], "required_covered": False, "missing_required_types": ["topic"]},
        "corpus_hits": [],
        "duplicate_risk": {},
        "configured_integrations": [],
        "unbound_integrations": [],
        "search_runtime": {
            "builtin_web_search": False,
            "web_provider": "exa",
            "web_fallback": "claude_web",
            "builtin_web_search_unlocked": False,
        },
        "search_protocol": search_protocol,
        "epistemic_protocol": epistemic_protocol,
    }
}
prompt = render_skill_runtime_prompt("research", state)
assert search_protocol["fallback"]["tool"] == "exa"
assert search_protocol["fallback"]["builtin_web_search"]["enabled"] is False
assert "search_protocol" in prompt
assert "search_runtime" in prompt
assert "epistemic_protocol" in prompt
assert "first-principles derivation" in prompt
assert "configured web provider" in prompt
assert "do not call `WebSearch`/`WebFetch` directly" in prompt
PY
then
    pass "substantive skills get explicit search/epistemic runtime protocol"
else
    fail "substantive skills get explicit search/epistemic runtime protocol"
fi

echo "--- Test 2: heartbeat is exempt from the substantive protocol ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))

from _shared.dispatch_runtime import _epistemic_protocol, _search_protocol, render_skill_runtime_prompt

request = {"skill": "heartbeat", "corpus_query": "", "configured_integrations": [], "unbound_integrations": []}
search_protocol = _search_protocol("heartbeat", request)
epistemic_protocol = _epistemic_protocol("heartbeat")
assert search_protocol["required"] is False
assert epistemic_protocol["required"] is False
state = {"request": {"heartbeat_routing": {"suggested_skill": "autonomy"}, "async_inbox": {}, "schema_version": 1}}
prompt = render_skill_runtime_prompt("heartbeat", state)
assert "HEARTBEAT ROUTER CONTRACT" in prompt
assert "Do not draft artifacts" in prompt
assert "edge-dispatch dispatch --skill <chosen-skill>" in prompt
PY
then
    pass "heartbeat remains exempt from the substantive protocol"
else
    fail "heartbeat remains exempt from the substantive protocol"
fi

echo "--- Test 3: preflight step exceptions degrade to warning instead of aborting ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))

import _shared.dispatch_runtime as runtime

original_protocol = runtime.ensure_compiled_protocol
original_execute = runtime._execute_preflight_step
try:
    runtime.ensure_compiled_protocol = lambda _stage: {
        "source_hash": "sha256:test",
        "compiled_hash": "sha256:test",
        "context_notes": [],
        "operator_notes": [],
        "procedures": [{"id": "boom", "kind": "health.snapshot"}],
    }
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")
    runtime._execute_preflight_step = boom
    state = {"cycle_id": "cycle-test", "request": {"skill": "research", "args": {}}, "state": {}}
    runtime.enrich_dispatch_state(state, skill="research")
    evidence = state["request"]["preflight_evidence"]
    assert evidence[0]["status"] == "warning"
    assert evidence[0]["satisfied"] is False
    assert evidence[0]["failure_mode"] == "exception"
    assert state["state"]["preflight_status"] == "warning"
finally:
    runtime.ensure_compiled_protocol = original_protocol
    runtime._execute_preflight_step = original_execute
PY
then
    pass "preflight exceptions degrade to warning instead of aborting"
else
    fail "preflight exceptions degrade to warning instead of aborting"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
