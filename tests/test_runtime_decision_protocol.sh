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

request = {"skill": "research", "corpus_query": "heartbeat dispatch timeout", "configured_integrations": [], "unbound_integrations": []}
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
        "search_protocol": search_protocol,
        "epistemic_protocol": epistemic_protocol,
    }
}
prompt = render_skill_runtime_prompt("research", state)
assert "search_protocol" in prompt
assert "epistemic_protocol" in prompt
assert "first-principles derivation" in prompt
assert "fall back to web search" in prompt
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

from _shared.dispatch_runtime import _epistemic_protocol, _search_protocol

request = {"skill": "heartbeat", "corpus_query": "", "configured_integrations": [], "unbound_integrations": []}
search_protocol = _search_protocol("heartbeat", request)
epistemic_protocol = _epistemic_protocol("heartbeat")
assert search_protocol["required"] is False
assert epistemic_protocol["required"] is False
PY
then
    pass "heartbeat remains exempt from the substantive protocol"
else
    fail "heartbeat remains exempt from the substantive protocol"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi

