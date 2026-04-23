#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-runner-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
TMP_HOME="$TMP_BASE/home"
PROTO_PREFLIGHT="$EDGE_DIR/config/preflight.yaml"
PROTO_POSTFLIGHT="$EDGE_DIR/config/postflight.yaml"
BACKUP_PREFLIGHT="$TMP_BASE/preflight.yaml.bak"
BACKUP_POSTFLIGHT="$TMP_BASE/postflight.yaml.bak"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

cleanup() {
    if [[ -f "$BACKUP_PREFLIGHT" ]]; then mv "$BACKUP_PREFLIGHT" "$PROTO_PREFLIGHT"; else rm -f "$PROTO_PREFLIGHT"; fi
    if [[ -f "$BACKUP_POSTFLIGHT" ]]; then mv "$BACKUP_POSTFLIGHT" "$PROTO_POSTFLIGHT"; else rm -f "$PROTO_POSTFLIGHT"; fi
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state" "$TMP_HOME/.local/bin"
mkdir -p "$TMP_HOME/.claude/projects/test-project"

if [[ -f "$PROTO_PREFLIGHT" ]]; then cp "$PROTO_PREFLIGHT" "$BACKUP_PREFLIGHT"; fi
if [[ -f "$PROTO_POSTFLIGHT" ]]; then cp "$PROTO_POSTFLIGHT" "$BACKUP_POSTFLIGHT"; fi
cat >"$PROTO_PREFLIGHT" <<'YAML'
version: 1
protocol: preflight
context_notes: []
operator_notes: []
procedures:
  - id: health-snapshot
    kind: health.snapshot
  - id: inbox
    kind: inbox.snapshot
  - id: claude-sessions
    kind: claude.sessions.digest
  - id: claims
    kind: claims.refresh
  - id: primitives
    kind: primitives.status
  - id: capabilities
    kind: capabilities.status
  - id: corpus
    kind: corpus.lookup
  - id: workflows
    kind: workflow.status
  - id: queue
    kind: queue.status
  - id: onboarding
    kind: onboarding.status
YAML

cat >"$TMP_HOME/.claude/projects/test-project/session-1.jsonl" <<'JSONL'
{"type":"user","timestamp":"2026-04-23T10:00:00Z","sessionId":"session-1","message":{"role":"user","content":"topics deve ser consultado no edge search em todo beat"}}
{"type":"user","timestamp":"2026-04-23T10:05:00Z","sessionId":"session-1","message":{"role":"user","content":"workflow automatico deve acontecer so com orientacao explicita do operador"}}
{"type":"user","timestamp":"2026-04-23T10:10:00Z","sessionId":"session-1","message":{"role":"user","content":"a primitive do exa no ed deveria mencionar deep research"}}
{"type":"user","timestamp":"2026-04-23T10:15:00Z","sessionId":"session-1","message":{"role":"user","content":"topics deve ser consultado no edge search em todo beat"}}
JSONL
cat >"$PROTO_POSTFLIGHT" <<'YAML'
version: 1
protocol: postflight
context_notes: []
operator_notes: []
procedures:
  - id: validate-recent
    kind: validate.recent
  - id: claims
    kind: claims.refresh
  - id: primitives
    kind: primitives.status
  - id: capabilities
    kind: capabilities.status
  - id: workflows
    kind: workflow.status
  - id: briefing
    kind: briefing.refresh
  - id: cycle-health
    kind: cycle_health.observe
YAML

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"
export HOME="$TMP_HOME"
export EDGE_OPERATOR_PRESSURE_DISABLE_LLM=1

RUNNER_TOOL="$EDGE_DIR/tools/edge-runner"

cat >"$TMP_HOME/.local/bin/claude" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$EDGE_CYCLE_ID" >> "${MOCK_CLAUDE_ENV_OUT:?}"
printf '__INVOCATION__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf '%s\n' "$*" >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf '__END__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
if [ -n "${MOCK_CLAUDE_SLEEP_SECONDS:-}" ]; then
  sleep "${MOCK_CLAUDE_SLEEP_SECONDS}"
fi
if [ "${MOCK_CLAUDE_HEARTBEAT_FLOW:-0}" = "1" ]; then
  if [[ "$*" == *"/ed-heartbeat"* ]]; then
    "${EDGE_REPO_DIR:?}/tools/edge-dispatch" dispatch --skill discovery >/dev/null
  elif [[ "$*" == *"/discovery"* ]]; then
    "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery start >/dev/null
    "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery end >/dev/null
  fi
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
rm -f "$MOCK_CLAUDE_ENV_OUT" "$MOCK_CLAUDE_ARGS_OUT"
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
cycle_ids = [line.strip() for line in open(sys.argv[4], encoding="utf-8") if line.strip()]
invocations = []
current = []
for raw_line in open(sys.argv[5], encoding="utf-8"):
    line = raw_line.rstrip("\n")
    if line == "__INVOCATION__":
        current = []
        continue
    if line == "__END__":
        invocations.append("\n".join(current))
        current = []
        continue
    current.append(line)
request = dispatch["request"]

assert len(cycle_ids) == 2
assert cycle_ids[0] == dispatch["cycle_id"]
assert cycle_ids[1] == dispatch["cycle_id"]
assert request["trigger"] == "heartbeat"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["preflight_status"] == "warning"
assert request["schema_version"] == 1
assert request["pre_skill_context"]["protocol"] == "preflight"
assert request["pre_skill_context"]["source_hash"].startswith("sha256:")
assert len(request["preflight_evidence"]) >= 1
assert any(item["kind"] == "health.snapshot" for item in request["preflight_evidence"])
assert any(item["kind"] == "claude.sessions.digest" for item in request["preflight_evidence"])
corpus_step = next(item for item in request["preflight_evidence"] if item["kind"] == "corpus.lookup")
assert corpus_step["satisfied"] is False
assert corpus_step["missing_required_types"] == ["topic", "workflow", "memory"]
assert request["operator_pressure_summary"]["item_total"] >= 3
assert request["operator_pressure_summary"]["workflow_candidates"] >= 1
assert request["operator_pressure_summary"]["capability_candidates"] >= 1
assert request["operator_pressure_digest"]["repeated_operator_guidance"]
assert request["operator_pressure_digest"]["active_entities"]
assert request["search_protocol"]["required"] is True
assert request["epistemic_protocol"]["required"] is True
assert request["heartbeat_routing"]["suggested_skill"] == "autonomy"
assert request["heartbeat_routing"]["round_robin_skills"] == [
    "autonomy",
    "reflection",
    "report",
    "research",
    "map",
    "discovery",
    "strategy",
]
assert "Dispatch runtime context below" in invocations[0]
assert "health_snapshot" in invocations[0]
assert "pre_skill_context" in invocations[0]
assert "preflight_evidence" in invocations[0]
assert "corpus_coverage" in invocations[0]
assert "operator_pressure_digest" in invocations[0]
assert "search_protocol" in invocations[0]
assert "epistemic_protocol" in invocations[0]
assert "configured_integrations" in invocations[0]
assert "heartbeat_routing" in invocations[0]
assert request["primitives_status"]["summary"]["health_status"] == "ok"
assert "workflow_status" in request
assert "claims_summary" in request
assert legacy["active"] is False
assert any(event["type"] == "CycleStarted" for event in events)
assert any(event["type"] == "PreflightCompleted" for event in events)
assert any(event["type"] == "SkillDispatched" for event in events)
assert any(event["type"] == "SkillRunCompleted" for event in events)
assert any(event["type"] == "CycleClosed" for event in events)
assert len(invocations) == 2
assert "/ed-heartbeat" in invocations[0]
assert "/discovery" in invocations[1]
assert "Dispatch runtime context below" in invocations[0]
assert "Dispatch runtime context below" in invocations[1]
PY
then
    pass "heartbeat run dispatches and executes the follow-on skill before closing the cycle"
else
    fail "heartbeat run dispatches and executes the follow-on skill before closing the cycle"
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
export MOCK_CLAUDE_SLEEP_SECONDS=2
export MOCK_CLAUDE_HEARTBEAT_FLOW=1
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
unset MOCK_CLAUDE_SLEEP_SECONDS || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["close_reason"] in ("", None)
assert not any(event["type"] == "HeartbeatDispatchTimedOut" for event in events[-20:])
PY
then
    pass "heartbeat dispatch no longer times out by default"
else
    fail "heartbeat dispatch no longer times out by default"
fi

echo "--- Test 6: explicit heartbeat dispatch timeout still closes explicitly instead of stalling ---"
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
