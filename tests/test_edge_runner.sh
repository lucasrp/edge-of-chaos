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
{"type":"user","timestamp":"2026-04-23T10:20:00Z","sessionId":"session-1","message":{"role":"user","content":"eu nao deveria ter que repetir esse passo; isso deveria vir no install"}}
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
export EDGE_EXPLORE_SKIP_SOURCES=1
export MEMORY_PROJECT_DIR="test-project"
export HOME="$TMP_HOME"
export EDGE_OPERATOR_PRESSURE_DISABLE_LLM=1
export EDGE_OPERATOR_PRESSURE_WINDOW_DAYS=30

RUNNER_TOOL="$EDGE_DIR/tools/edge-runner"

cat >"$TMP_HOME/.local/bin/claude" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
PROMPT="$(cat)"
printf '%s\n' "$EDGE_CYCLE_ID" >> "${MOCK_CLAUDE_ENV_OUT:?}"
printf '__INVOCATION__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf 'ARGS: %s\n' "$*" >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf 'STDIN:\n%s\n' "$PROMPT" >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf '__END__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
if [ -n "${MOCK_CLAUDE_SLEEP_SECONDS:-}" ]; then
  sleep "${MOCK_CLAUDE_SLEEP_SECONDS}"
fi
if [ "${MOCK_CLAUDE_HEARTBEAT_FLOW:-0}" = "1" ]; then
  if [[ "$PROMPT" == *"/ed-heartbeat"* ]]; then
    "${EDGE_REPO_DIR:?}/tools/edge-dispatch" dispatch --skill discovery >/dev/null
  elif [[ "$PROMPT" == *"/discovery"* ]]; then
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
beat_mirror = json.load(open(sys.argv[2], encoding="utf-8"))
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
assert request["operator_pressure_summary"]["signal_from_operator_now"] >= 1
assert request["operator_pressure_summary"]["operator_toil_optimizable_now"] >= 1
assert request["operator_pressure_summary"]["workflow_candidates"] >= 1
assert request["operator_pressure_summary"]["capability_candidates"] >= 1
assert request["operator_pressure_summary"]["substrate_gap_requests"] >= 1
assert request["operator_pressure_digest"]["signal_from_operator_now"]
assert request["operator_pressure_digest"]["operator_toil_optimizable_now"]
assert request["operator_pressure_digest"]["substrate_gap_requests"]
assert "mistakes_to_avoid_now" in request["operator_pressure_digest"]
assert request["operator_pressure_digest"]["active_entities"]
assert request["operator_pressure"]["projection"]["projection_status"] in ("fresh", "refreshed")
assert request["operator_pressure"]["projection"]["path"].endswith("/state/projections/operator-pressure.json")
assert request["delta_prerequisite"]["inputs"]["raw_chat"]["source_paths"]["projection"].endswith("/state/projections/operator-pressure.json")
assert request["beat_launch_context"]["signal_from_operator_now"]
assert request["beat_launch_context"]["signal_from_edge_state_now"]
assert request["beat_launch_context"]["substrate_gap_requests"]
assert request["beat_launch_context"]["decision_blend"] == {
    "operator_min_weight": 0.20,
    "edge_state_min_weight": 0.20,
    "exploration_weight": 0.60,
}
assert any("Corpus coverage is missing required types" in item for item in request["beat_launch_context"]["signal_from_edge_state_now"])
assert request["search_protocol"]["required"] is True
assert request["epistemic_protocol"]["required"] is True
assert request["delta_prerequisite"]["required"] is True
assert request["delta_prerequisite"]["digest_update_required"] is False
assert request["delta_prerequisite"]["inputs"]["raw_chat"]["available"] is True
assert request["delta_prerequisite"]["inputs"]["raw_chat"]["recent_items"]
assert request["exploration_pack"]["skill"] == "discovery"
assert request["exploration_pack"]["status"] in ("ready", "degraded")
assert request["exploration_pack"]["path"].endswith("/pack.json")
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
assert "beat_launch_context" in invocations[0]
assert "delta_prerequisite" in invocations[0]
assert "DELTA PREREQUISITE" in invocations[0]
assert "search_protocol" in invocations[0]
assert "epistemic_protocol" in invocations[0]
assert "exploration_pack" in invocations[1]
assert "delta_prerequisite" in invocations[1]
assert "Adversarial Feynman" in open(request["exploration_pack"]["markdown_path"], encoding="utf-8").read()
assert "configured_integrations" in invocations[0]
assert "heartbeat_routing" in invocations[0]
assert request["primitives_status"]["summary"]["health_status"] == "ok"
assert "workflow_status" in request
assert "claims_summary" in request
assert beat_mirror["active"] is False
assert any(event["type"] == "CycleStarted" for event in events)
assert any(event["type"] == "PreflightCompleted" for event in events)
assert any(event["type"] == "SkillDispatched" for event in events)
assert any(event["type"] == "ExplorationPackPublished" for event in events)
assert any(event["type"] == "SkillRunCompleted" for event in events)
assert any(event["type"] == "CycleClosed" for event in events)
assert len(invocations) == 2
assert invocations[0].splitlines()[0] == "ARGS: -p -"
assert invocations[1].splitlines()[0] == "ARGS: -p -"
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

echo "--- Test 6: autonomy skill receives deep primitives/capabilities checkup ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
unset MOCK_CLAUDE_EXIT_CODE || true
"$RUNNER_TOOL" skill \
    --skill /autonomy \
    --dispatch-trigger operator \
    --dispatch-policy operator \
    --dispatch-routing-mode explicit \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
request = dispatch["request"]
checkup = request["autonomy_primitives_checkup"]

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert checkup["status"] in {"ok", "warning", "degraded", "fail"}
assert "primitive_summary" in checkup
assert "capability_summary" in checkup
assert "candidate_actions" in checkup
assert any(event["type"] == "AutonomyPrimitiveCheckupCompleted" for event in events)
PY
then
    pass "autonomy checkup runs through edge-primitives --checkup"
else
    fail "autonomy checkup runs through edge-primitives --checkup"
fi

echo "--- Test 7: explicit heartbeat timeout env is ignored ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
unset MOCK_CLAUDE_EXIT_CODE || true
export MOCK_CLAUDE_SLEEP_SECONDS=2
export MOCK_CLAUDE_HEARTBEAT_FLOW=1
export EDGE_HEARTBEAT_DISPATCH_TIMEOUT_SECONDS=1
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
unset MOCK_CLAUDE_SLEEP_SECONDS || true
unset EDGE_HEARTBEAT_DISPATCH_TIMEOUT_SECONDS || true

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
    pass "heartbeat timeout env no longer kills long beats"
else
    fail "heartbeat timeout env no longer kills long beats"
fi

echo "--- Test 8: backend exceeding EDGE_RUNNER_SKILL_TIMEOUT_SEC is killed and cycle closes failed ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
unset MOCK_CLAUDE_EXIT_CODE || true
export MOCK_CLAUDE_SLEEP_SECONDS=10
export EDGE_RUNNER_SKILL_TIMEOUT_SEC=2
set +e
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null 2>&1
STATUS=$?
set -e
unset MOCK_CLAUDE_SLEEP_SECONDS || true
unset EDGE_RUNNER_SKILL_TIMEOUT_SEC || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
status = int(sys.argv[3])

assert status != 0
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "skill_subprocess_timeout"
assert any(event["type"] == "SkillSubprocessTimeout" for event in events[-30:])
PY
then
    pass "watchdog kills hung backend and closes cycle as skill_subprocess_timeout"
else
    fail "watchdog kills hung backend and closes cycle as skill_subprocess_timeout"
fi

echo "--- Test 9: backend prompt is delivered through stdin, not argv ---"
if python3 - <<'PY' "$EDGE_DIR"
import argparse
import importlib.machinery
import importlib.util
import os
import sys

edge_dir = sys.argv[1]
loader = importlib.machinery.SourceFileLoader("edge_runner", f"{edge_dir}/tools/edge-runner")
spec = importlib.util.spec_from_loader("edge_runner", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

large_prompt = "prompt-line\n" + ("x" * (3 * 1024 * 1024))
args = argparse.Namespace(
    cmd="prompt",
    prompt=large_prompt,
    skill="",
    backend="claude",
    cwd=None,
    max_turns=2,
    allowed_tools="Bash",
    output_format="json",
    dangerously_skip_permissions=True,
)
captured = {}

class Result:
    returncode = 0

def fake_run(cmd, *, env, cwd, input, text):
    captured["cmd"] = cmd
    captured["input"] = input
    captured["text"] = text
    captured["cwd"] = cwd
    return Result()

module.resolve_claude_bin = lambda: "/mock/claude"
module.subprocess.run = fake_run
os.environ["EDGE_RUNNER_SKILL_TIMEOUT_SEC"] = "0"
try:
    status = module.invoke_backend(args, {"EDGE_REPO_DIR": edge_dir}, cycle_id=None)
finally:
    os.environ.pop("EDGE_RUNNER_SKILL_TIMEOUT_SEC", None)

assert status == 0
assert captured["cmd"] == [
    "/mock/claude",
    "-p",
    "-",
    "--max-turns",
    "2",
    "--allowedTools",
    "Bash",
    "--output-format",
    "json",
    "--dangerously-skip-permissions",
]
assert captured["input"] == large_prompt
assert large_prompt not in captured["cmd"]
assert captured["text"] is True
PY
then
    pass "large backend prompt is streamed through stdin"
else
    fail "large backend prompt is streamed through stdin"
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
