#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-runner-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
TMP_HOME="$TMP_BASE/home"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state" "$TMP_HOME/.local/bin"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"
export HOME="$TMP_HOME"

RUNNER_TOOL="$EDGE_DIR/tools/edge-runner"

cat >"$TMP_HOME/.local/bin/claude" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$EDGE_CYCLE_ID" > "${MOCK_CLAUDE_ENV_OUT:?}"
printf '%s\n' "$*" > "${MOCK_CLAUDE_ARGS_OUT:?}"
if [ -n "${MOCK_CLAUDE_SLEEP_SECONDS:-}" ]; then
  sleep "${MOCK_CLAUDE_SLEEP_SECONDS}"
fi
if [ "${MOCK_CLAUDE_HEARTBEAT_FLOW:-0}" = "1" ]; then
  "${EDGE_REPO_DIR:?}/tools/edge-dispatch" dispatch --skill discovery >/dev/null
  "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery start >/dev/null
  "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery end >/dev/null
fi
exit "${MOCK_CLAUDE_EXIT_CODE:-0}"
SH
chmod +x "$TMP_HOME/.local/bin/claude"
export EDGE_CLAUDE_BIN="$TMP_HOME/.local/bin/claude"

echo "=== edge-runner Smoke Test ==="
echo "Temp state: $TMP_EDGE"
echo ""

echo "--- Test 1: heartbeat skill run opens and closes cycle mechanically ---"
export MOCK_CLAUDE_ENV_OUT="$TMP_BASE/cycle-id.txt"
export MOCK_CLAUDE_ARGS_OUT="$TMP_BASE/args.txt"
unset MOCK_CLAUDE_EXIT_CODE || true
export MOCK_CLAUDE_HEARTBEAT_FLOW=1
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/current-beat.json" "$TMP_EDGE/state/events/log.jsonl" "$TMP_BASE/cycle-id.txt" "$TMP_BASE/args.txt"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
legacy = json.load(open(sys.argv[2], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[3], encoding="utf-8") if line.strip()]
cycle_id = open(sys.argv[4], encoding="utf-8").read().strip()
args = open(sys.argv[5], encoding="utf-8").read().strip()
request = dispatch["request"]

assert cycle_id == dispatch["cycle_id"]
assert request["trigger"] == "heartbeat"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["preflight_status"] == "completed"
assert request["schema_version"] == 1
assert "Dispatch runtime context below" in args
assert "health_snapshot" in args
assert request["primitives_status"]["summary"]["health_status"] == "ok"
assert "workflow_status" in request
assert "claims_summary" in request
assert legacy["active"] is False
assert any(event["type"] == "CycleStarted" for event in events)
assert any(event["type"] == "PreflightCompleted" for event in events)
assert any(event["type"] == "CycleClosed" for event in events)
assert "/ed-heartbeat" in args
PY
then
    pass "heartbeat run exports cycle id, request context, and closes the shadow cycle"
else
    fail "heartbeat run exports cycle id, request context, and closes the shadow cycle"
fi

echo "--- Test 2: success without skill completion evidence closes as failed ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
set +e
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
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
assert dispatch["state"]["close_reason"] == "missing_dispatch"
PY
then
    pass "runner downgrades heartbeat success to failed when the skill never completes"
else
    fail "runner downgrades heartbeat success to failed when the skill never completes"
fi

echo "--- Test 3: failed backend closes cycle as failed ---"
export MOCK_CLAUDE_EXIT_CODE=7
set +e
"$RUNNER_TOOL" prompt \
    --prompt "diagnose" \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
status = int(sys.argv[2])

assert status == 7
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "backend_exit_7"
PY
then
    pass "backend failure maps to failed CycleClosed state"
else
    fail "backend failure maps to failed CycleClosed state"
fi

echo "--- Test 4: bare heartbeat invocation auto-inferrs heartbeat dispatch defaults ---"
unset MOCK_CLAUDE_EXIT_CODE || true
export MOCK_CLAUDE_HEARTBEAT_FLOW=1
"$RUNNER_TOOL" skill --skill /ed-heartbeat >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))

assert dispatch["request"]["trigger"] == "heartbeat"
assert dispatch["request"]["policy"] == "autonomous"
assert dispatch["request"]["routing_mode"] == "auto"
assert dispatch["request"]["preflight_profile"] == "heartbeat_default"
assert dispatch["request"]["postflight_profile"] == "standard"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
PY
then
    pass "bare heartbeat skill run auto-opens the heartbeat lifecycle"
else
    fail "bare heartbeat skill run auto-opens the heartbeat lifecycle"
fi

echo "--- Test 5: heartbeat dispatch timeout closes explicitly instead of stalling ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
unset MOCK_CLAUDE_EXIT_CODE || true
export MOCK_CLAUDE_SLEEP_SECONDS=3
export EDGE_HEARTBEAT_DISPATCH_TIMEOUT_SECONDS=1
set +e
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
STATUS=$?
set -e
unset MOCK_CLAUDE_SLEEP_SECONDS || true
unset EDGE_HEARTBEAT_DISPATCH_TIMEOUT_SECONDS || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
status = int(sys.argv[3])

assert status == 1
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "heartbeat_dispatch_timeout"
assert any(event["type"] == "HeartbeatDispatchTimedOut" for event in events)
PY
then
    pass "heartbeat dispatch timeout closes explicitly instead of stalling"
else
    fail "heartbeat dispatch timeout closes explicitly instead of stalling"
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
