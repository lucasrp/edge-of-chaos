#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-skill-step-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/logs" "$TMP_EDGE/state/events"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"
export EDGE_CYCLE_ID="cycle-test-skill-step"

STEP_TOOL="$EDGE_DIR/tools/edge-skill-step"

echo "=== edge-skill-step Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: English skill alias resolves to modern semantic registry skill ---"
"$STEP_TOOL" discovery direction >/dev/null
"$STEP_TOOL" discovery explore >/dev/null
"$STEP_TOOL" discovery application >/dev/null
"$STEP_TOOL" discovery persistence >/dev/null
"$STEP_TOOL" discovery end >"$TMP_BASE/discovery-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_EDGE/state/events/log.jsonl" "$TMP_BASE/discovery-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
output = open(sys.argv[3], encoding="utf-8").read()

assert steps[0]["skill"] == "discovery"
assert steps[0]["registry_skill"] == "ed-discovery"
end = steps[4]
assert end["skill"] == "discovery"
assert end["registry_skill"] == "ed-discovery"
assert end["contract"] == "semantic_checkpoints"
assert end["expected"] == 4
assert end["done"] == 4
assert end["silent_skips"] == []
assert "warning" not in end
assert "ed-discovery" in output
assert any(event["type"] == "SkillStepObserved" for event in events)
assert any(event["type"] == "SkillRunCompleted" for event in events)
PY
then
    pass "English discovery skill resolves to semantic registry and emits logs/events"
else
    fail "English discovery skill resolves to semantic registry and emits logs/events"
fi

echo "--- Test 2: prefixed runtime skill alias resolves and reports semantic skips ---"
"$STEP_TOOL" /gauss-autonomy diagnosis >/dev/null
"$STEP_TOOL" /gauss-autonomy end >"$TMP_BASE/autonomy-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_BASE/autonomy-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
output = open(sys.argv[2], encoding="utf-8").read()
last = steps[-1]

assert last["skill"] == "/gauss-autonomy"
assert last["registry_skill"] == "ed-autonomy"
assert last["expected"] == 4
assert last["done"] == 1
assert last["silent_skips"] == ["decision", "change", "verification"]
assert "warning" not in last
assert "ed-autonomy" in output
assert "decision:" in output
PY
then
    pass "prefixed autonomy skill resolves and reports semantic skips"
else
    fail "prefixed autonomy skill resolves and reports semantic skips"
fi

echo "--- Test 3: unregistered skills are optional and still emit completion ---"
"$STEP_TOOL" /gauss-prototype end >"$TMP_BASE/prototype-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_EDGE/state/events/log.jsonl" "$TMP_BASE/prototype-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
output = open(sys.argv[3], encoding="utf-8").read()
last = steps[-1]

assert last["skill"] == "/gauss-prototype"
assert last["registry_status"] == "unregistered"
assert last["expected"] == 0
assert last["completion_pct"] == 100
assert "warning" not in last
assert "sem contrato" in output
assert any(event["type"] == "SkillRunCompleted" and event["payload"].get("registry_status") == "unregistered" for event in events)
PY
then
    pass "unregistered skill completion is optional but observable"
else
    fail "unregistered skill completion is optional but observable"
fi

echo "--- Test 4: legacy Portuguese registry aliases remain compatible during migration ---"
"$STEP_TOOL" ed-descoberta direction >/dev/null
"$STEP_TOOL" ed-descoberta skip explore already-covered >/dev/null
"$STEP_TOOL" ed-descoberta end >"$TMP_BASE/legacy-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_BASE/legacy-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
output = open(sys.argv[2], encoding="utf-8").read()
last = steps[-1]

assert last["skill"] == "ed-descoberta"
assert last["registry_skill"] == "ed-discovery"
assert last["done"] == 1
assert last["explicit_skips"] == 1
assert last["skip_details"] == {"explore": "already-covered"}
assert last["silent_skips"] == ["application", "persistence"]
assert "ed-discovery" in output
PY
then
    pass "legacy Portuguese alias resolves to modern semantic registry"
else
    fail "legacy Portuguese alias resolves to modern semantic registry"
fi

echo "--- Test 5: reports ignore optional unregistered completion entries ---"
"$STEP_TOOL" report --last 10 >"$TMP_BASE/report.txt"

if python3 - <<'PY' "$TMP_BASE/report.txt"
import sys

output = open(sys.argv[1], encoding="utf-8").read()
assert "ed-discovery" in output
assert "ed-autonomy" in output
assert "/gauss-prototype" not in output
PY
then
    pass "report focuses on registered semantic checkpoint contracts"
else
    fail "report focuses on registered semantic checkpoint contracts"
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
