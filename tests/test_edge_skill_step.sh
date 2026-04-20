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

echo "--- Test 1: English skill alias resolves to registry skill and writes log ---"
"$STEP_TOOL" discovery start >/dev/null
"$STEP_TOOL" discovery end >"$TMP_BASE/discovery-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_EDGE/state/events/log.jsonl" "$TMP_BASE/discovery-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
output = open(sys.argv[3], encoding="utf-8").read()

assert steps[0]["skill"] == "discovery"
assert steps[0]["registry_skill"] == "ed-descoberta"
assert steps[1]["skill"] == "discovery"
assert steps[1]["registry_skill"] == "ed-descoberta"
assert "warning" not in steps[1]
assert "ed-descoberta" in output
assert any(event["type"] == "SkillStepObserved" for event in events)
assert any(event["type"] == "SkillRunCompleted" for event in events)
PY
then
    pass "English discovery skill resolves to registry and emits logs/events"
else
    fail "English discovery skill resolves to registry and emits logs/events"
fi

echo "--- Test 2: prefixed runtime skill alias resolves to same registry skill ---"
"$STEP_TOOL" /gauss-autonomy start >/dev/null
"$STEP_TOOL" /gauss-autonomy end >"$TMP_BASE/autonomy-end.txt"

if python3 - <<'PY' "$TMP_EDGE/logs/skill-steps.jsonl" "$TMP_BASE/autonomy-end.txt"
import json
import sys

steps = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
output = open(sys.argv[2], encoding="utf-8").read()
last = steps[-1]

assert last["skill"] == "/gauss-autonomy"
assert last["registry_skill"] == "ed-autonomia"
assert "warning" not in last
assert "ed-autonomia" in output
PY
then
    pass "prefixed autonomy skill resolves to registry"
else
    fail "prefixed autonomy skill resolves to registry"
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
