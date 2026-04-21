#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-close-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state/events" "$TMP_EDGE/logs" "$TMP_EDGE/state"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

DISPATCH_TOOL="$EDGE_DIR/tools/edge-dispatch"
CLOSE_TOOL="$EDGE_DIR/tools/edge-close"
STEP_TOOL="$EDGE_DIR/tools/edge-skill-step"

echo "=== edge-close Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: completed close is rejected without skill completion evidence ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-missing >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
set +e
"$CLOSE_TOOL" --status completed >/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
status = int(sys.argv[2])

assert status == 1
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "missing_skill_run_completed"
assert dispatch["state"]["postflight_status"] == "failed"
PY
then
    pass "edge-close downgrades incomplete cycles to failed"
else
    fail "edge-close downgrades incomplete cycles to failed"
fi

echo "--- Test 2: completed close succeeds with skill end evidence and postflight ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-complete --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery start >/dev/null
EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery end >/dev/null
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/logs/post-skill.log"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
postflight = open(sys.argv[2], encoding="utf-8").read()
steps = dispatch["state"].get("postflight_steps", [])
delta = dispatch["state"].get("postflight_delta", {})
step_names = {step.get("step") for step in steps}

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["postflight_status"] == "completed"
assert "validate_recent" in postflight
assert {"validate_recent", "claims_digest", "primitives_status", "workflow_status", "briefing_digest"} <= step_names
assert "claims_open_delta" in delta
PY
then
    pass "edge-close completes only after skill end evidence and enriched postflight"
else
    fail "edge-close completes only after skill end evidence and enriched postflight"
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
