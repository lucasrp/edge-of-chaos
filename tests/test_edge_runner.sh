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
publish_mock_artifact() {
  local skill="$1"
  python3 - "$skill" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

skill = sys.argv[1].strip().lstrip("/") or "skill"
cycle_id = os.environ.get("EDGE_CYCLE_ID", "")
state_dir = Path(os.environ["EDGE_STATE_DIR"])
events = state_dir / "state" / "events" / "log.jsonl"
events.parent.mkdir(parents=True, exist_ok=True)
safe_skill = re.sub(r"[^a-z0-9-]+", "-", skill.lower()).strip("-") or "skill"
event = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "type": "ArtifactPublished",
    "actor": "continuity",
    "cycle_id": cycle_id,
    "artifact": f"blog/entries/mock-{safe_skill}-{cycle_id}.md",
    "payload": {"source_skill": safe_skill},
}
with open(events, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
}
PROMPT="$(cat)"
printf '%s\n' "$EDGE_CYCLE_ID" >> "${MOCK_CLAUDE_ENV_OUT:?}"
printf '__INVOCATION__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf 'ARGS: %s\n' "$*" >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf 'STDIN:\n%s\n' "$PROMPT" >> "${MOCK_CLAUDE_ARGS_OUT:?}"
printf '__END__\n' >> "${MOCK_CLAUDE_ARGS_OUT:?}"
if [ -n "${MOCK_CLAUDE_SLEEP_SECONDS:-}" ]; then
  sleep "${MOCK_CLAUDE_SLEEP_SECONDS}"
fi
if [ "${MOCK_CLAUDE_FAIL_ONCE:-0}" = "1" ]; then
  INVOCATIONS="$(grep -c '^__INVOCATION__$' "${MOCK_CLAUDE_ARGS_OUT:?}" 2>/dev/null || true)"
  if [ "$INVOCATIONS" = "1" ]; then
    printf '%s\n' "${MOCK_CLAUDE_FAIL_ONCE_OUTPUT:-Acknowledged — standing by.}"
    exit "${MOCK_CLAUDE_FAIL_ONCE_EXIT_CODE:-1}"
  fi
fi
if [ "${MOCK_CLAUDE_HEARTBEAT_FLOW:-0}" = "1" ]; then
  if [[ "$PROMPT" == *"/ed-heartbeat"* ]]; then
    "${EDGE_REPO_DIR:?}/tools/edge-dispatch" dispatch --skill discovery >/dev/null
    if [ "${MOCK_CLAUDE_HEARTBEAT_INLINE_DONE:-0}" = "1" ]; then
      python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["EDGE_STATE_DIR"]) / "state" / "current-dispatch.json"
state = json.loads(path.read_text(encoding="utf-8"))
now = datetime.now(timezone.utc).isoformat()
state_block = state.setdefault("state", {})
state_block["postflight_status"] = "warning"
state_block["postflight_reason"] = "inline_substantive_work"
state_block["postflight_checked_at"] = now
state_block["updated_at"] = now
path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
      publish_mock_artifact discovery
    fi
  elif [[ "$PROMPT" == *"/discovery"* ]]; then
    for step in direction explore application persistence; do
      "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery "$step" >/dev/null
    done
    "${EDGE_REPO_DIR:?}/tools/edge-skill-step" discovery end >/dev/null
    publish_mock_artifact discovery
  elif [ -z "${MOCK_CLAUDE_ARTIFACT_MARKDOWN:-}" ]; then
    for skill in autonomy reflection report research map strategy planner sources; do
      if [[ "$PROMPT" == *"/$skill"* ]]; then
        publish_mock_artifact "$skill"
        break
      fi
    done
  fi
fi
if [ -z "${MOCK_CLAUDE_ARTIFACT_MARKDOWN:-}" ] && [ "${MOCK_CLAUDE_EXIT_CODE:-0}" = "0" ] && [ "${MOCK_CLAUDE_HEARTBEAT_FLOW:-0}" != "1" ] && [[ "$PROMPT" == *"/autonomy"* ]]; then
  publish_mock_artifact autonomy
fi
if [ -n "${MOCK_CLAUDE_ARTIFACT_MARKDOWN:-}" ]; then
  printf '%b\n' "$MOCK_CLAUDE_ARTIFACT_MARKDOWN"
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

assert len(cycle_ids) == 1
assert cycle_ids[0] == dispatch["cycle_id"]
assert request["trigger"] == "heartbeat"
assert request["skill"] == "report"
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
assert corpus_step["missing_required_types"] == ["workflow", "memory"]
assert request["operator_pressure_summary"]["item_total"] >= 3
assert request["operator_pressure_summary"]["signal_from_operator_now"] >= 1
assert request["operator_pressure_summary"]["operator_toil_optimizable_now"] >= 1
assert request["operator_pressure_summary"]["pre_skill_context"] >= 1
assert request["operator_pressure_summary"]["workflow_candidates"] >= 1
assert request["operator_pressure_summary"]["capability_candidates"] >= 1
assert request["operator_pressure_summary"]["substrate_gap_requests"] >= 1
assert request["operator_pressure_digest"]["signal_from_operator_now"]
assert request["operator_pressure_digest"]["operator_toil_optimizable_now"]
assert request["operator_pressure_digest"]["pre_skill_context"]
assert request["operator_pressure_digest"]["substrate_gap_requests"]
assert "mistakes_to_avoid_now" in request["operator_pressure_digest"]
assert request["operator_pressure_digest"]["active_entities"]
assert request["operator_pressure"]["projection"]["projection_status"] in ("fresh", "refreshed")
assert request["operator_pressure"]["projection"]["path"].endswith("/state/projections/operator-pressure.json")
assert request["delta_prerequisite"]["inputs"]["raw_chat"]["source_paths"]["projection"].endswith("/state/projections/operator-pressure.json")
assert request["beat_launch_context"]["signal_from_operator_now"]
assert request["beat_launch_context"]["signal_from_edge_state_now"]
assert request["beat_launch_context"]["pre_skill_context"]
assert request["beat_launch_context"]["substrate_gap_requests"]
assert any("Operator pressure pre-skill rule" in note for note in request["pre_skill_context"]["context_notes"])
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
assert request["exploration_pack"]["skill"] == "report"
assert request["exploration_pack"]["status"] in ("ready", "degraded")
assert request["exploration_pack"]["path"].endswith("/pack.json")
assert request["heartbeat_routing"]["suggested_skill"] == "report"
assert request["heartbeat_routing"]["selected_skill"] == "report"
assert request["heartbeat_routing"]["dispatch_mode"] == "deterministic_heartbeat_router"
assert request["heartbeat_routing"]["acknowledged"] is True
assert request["heartbeat_routing"]["round_robin_skills"] == [
    "report",
    "research",
    "discovery",
    "planner",
]
assert len(invocations) == 1
assert invocations[0].splitlines()[0] == "ARGS: -p -"
assert "/ed-heartbeat" not in invocations[0]
assert "/report" in invocations[0]
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
assert "exploration_pack" in invocations[0]
assert "Adversarial Feynman" in open(request["exploration_pack"]["markdown_path"], encoding="utf-8").read()
assert "configured_integrations" in invocations[0]
assert "heartbeat_routing" in invocations[0]
assert "autonomy_primitives_checkup" not in request
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
PY
then
    pass "heartbeat run dispatches and executes the follow-on skill before closing the cycle"
else
    fail "heartbeat run dispatches and executes the follow-on skill before closing the cycle"
fi

echo "--- Test 1b: heartbeat router prioritizes queued dispatch before fairness ---"
export MOCK_CLAUDE_ENV_OUT="$TMP_BASE/cycle-id-inline.txt"
export MOCK_CLAUDE_ARGS_OUT="$TMP_BASE/args-inline.txt"
rm -f "$MOCK_CLAUDE_ENV_OUT" "$MOCK_CLAUDE_ARGS_OUT"
cat >"$TMP_EDGE/state/dispatch-queue.json" <<'JSON'
[
  {
    "entry_id": "queue-report-1",
    "source": "test-suite",
    "skill": "report",
    "reason": "exercise deterministic heartbeat queue priority"
  }
]
JSON
export MOCK_CLAUDE_HEARTBEAT_FLOW=1
export MOCK_CLAUDE_ARTIFACT_MARKDOWN=$'# Queued Report Priority\n\nThis queued report artifact is intentionally long enough for the stdout publication bridge to accept it as a valid runtime artifact during the deterministic heartbeat routing test.'
"$RUNNER_TOOL" skill \
    --skill /ed-heartbeat \
    --dispatch-trigger heartbeat \
    --dispatch-policy autonomous \
    --dispatch-routing-mode auto \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >/dev/null
unset MOCK_CLAUDE_ARTIFACT_MARKDOWN || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$TMP_EDGE/logs/events.jsonl" "$TMP_BASE/cycle-id-inline.txt" "$TMP_BASE/args-inline.txt" "$TMP_EDGE/state/dispatch-queue.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
run_events = [json.loads(line) for line in open(sys.argv[3], encoding="utf-8") if line.strip()]
cycle_ids = [line.strip() for line in open(sys.argv[4], encoding="utf-8") if line.strip()]
queue = json.load(open(sys.argv[6], encoding="utf-8"))
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

assert len(cycle_ids) == 1
assert len(invocations) == 1
assert "/ed-heartbeat" not in invocations[0]
assert "/report" in invocations[0]
assert dispatch["request"]["skill"] == "report"
assert dispatch["request"]["heartbeat_routing"]["selected_skill"] == "report"
assert dispatch["request"]["heartbeat_routing"]["dispatch_mode"] == "deterministic_heartbeat_router"
assert dispatch["request"]["heartbeat_routing"]["acknowledged"] is False
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["postflight_status"] in {"completed", "warning"}
assert dispatch["state"]["dispatch_queue_ack"]["removed"] is True
assert dispatch["state"]["dispatch_queue_ack"]["skill"] == "report"
assert queue == []
completion_events = [
    e for e in events
    if e.get("type") == "SkillRunCompleted"
    and e.get("cycle_id") == dispatch["cycle_id"]
]
assert completion_events
assert completion_events[-1]["payload"]["skill"] == "report"
handoff_events = [
    e for e in run_events
    if e.get("type") == "run_step"
    and e.get("run_kind") == "edge-runner"
    and e.get("phase") == "handoff"
    and e.get("status") == "completed"
    and e.get("target") == "report"
]
assert handoff_events
PY
then
    pass "heartbeat router prioritizes queued dispatch before fairness"
else
    fail "heartbeat router prioritizes queued dispatch before fairness"
fi

echo "--- Test 1c: non-heartbeat skills publish stdout through the shared runtime bridge ---"
PUBLISH_SKILLS=(discovery research report strategy planner autonomy reflection sources map test-agent-autonomy)
PUBLISH_OK=1
for skill in "${PUBLISH_SKILLS[@]}"; do
    export MOCK_CLAUDE_ENV_OUT="$TMP_BASE/cycle-id-publish-$skill.txt"
    export MOCK_CLAUDE_ARGS_OUT="$TMP_BASE/args-publish-$skill.txt"
    rm -f "$MOCK_CLAUDE_ENV_OUT" "$MOCK_CLAUDE_ARGS_OUT"
    unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
    export MOCK_CLAUDE_ARTIFACT_MARKDOWN="# Runtime Artifact ${skill}

This is a complete markdown artifact emitted by the backend for ${skill}.

It should be published by the runtime bridge, not by the individual skill."
    if ! "$RUNNER_TOOL" skill \
        --skill "$skill" \
        --dispatch-trigger operator \
        --dispatch-policy operator \
        --dispatch-routing-mode explicit \
        --dispatch-preflight-profile standard \
        --dispatch-postflight-profile standard \
        --dispatch-force >/dev/null; then
        PUBLISH_OK=0
        break
    fi
    if ! python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$skill"; then
import json
import sys
from pathlib import Path

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
entries_dir = Path(sys.argv[3])
reports_dir = Path(sys.argv[4])
skill = sys.argv[5]
cycle_id = dispatch["cycle_id"]

expected_skill = skill
expected_source_skill = "autonomy" if skill == "test-agent-autonomy" else skill

assert dispatch["request"]["skill"] == expected_skill
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["close_reason"] != "missing_artifact_published"

published = [
    event for event in events
    if event.get("cycle_id") == cycle_id
    and event.get("type") == "ArtifactPublished"
    and (event.get("payload") or {}).get("source_skill") == expected_source_skill
    and (event.get("payload") or {}).get("auto_published") is True
]
assert published, f"no auto-published artifact for {skill}"
artifact = published[-1]["artifact"]
assert artifact.startswith("blog/entries/")
entry_path = entries_dir / Path(artifact).name
assert entry_path.exists()
entry = entry_path.read_text(encoding="utf-8")
assert "runtime-published" in entry
assert f"source_skill: {expected_source_skill}" in entry
report_name = (published[-1].get("payload") or {})["report"]
assert (reports_dir / report_name).exists()

phase_events = [
    event for event in events
    if event.get("cycle_id") == cycle_id
    and event.get("type") == "PhaseCompleted"
    and (event.get("payload") or {}).get("pipeline") == "runtime-stdout-artifact"
    and (event.get("payload") or {}).get("ok") is True
]
assert phase_events
PY
        PUBLISH_OK=0
        break
    fi
done
unset MOCK_CLAUDE_ARTIFACT_MARKDOWN || true

if [[ "$PUBLISH_OK" -eq 1 ]]; then
    pass "non-heartbeat skills publish stdout through the shared runtime bridge"
else
    fail "non-heartbeat skills publish stdout through the shared runtime bridge"
fi

echo "--- Test 1d: plain terminal prose is captured as an artifact without dumping the body ---"
export MOCK_CLAUDE_ENV_OUT="$TMP_BASE/cycle-id-plain-stdout.txt"
export MOCK_CLAUDE_ARGS_OUT="$TMP_BASE/args-plain-stdout.txt"
rm -f "$MOCK_CLAUDE_ENV_OUT" "$MOCK_CLAUDE_ARGS_OUT" "$TMP_BASE/plain-stdout.out"
export MOCK_CLAUDE_ARTIFACT_MARKDOWN=$'Plain Runtime Report\n\nThis report intentionally has no markdown heading. The runtime should still capture the terminal prose as a durable artifact instead of letting an artifact-producing skill close with text only in stdout. The body is long enough to satisfy the artifact bridge threshold.'
"$RUNNER_TOOL" skill \
    --skill /report \
    --dispatch-trigger operator \
    --dispatch-policy operator \
    --dispatch-routing-mode explicit \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >"$TMP_BASE/plain-stdout.out"
unset MOCK_CLAUDE_ARTIFACT_MARKDOWN || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$TMP_EDGE/blog/entries" "$TMP_BASE/plain-stdout.out"
import json
import sys
from pathlib import Path

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
entries_dir = Path(sys.argv[3])
runner_stdout = Path(sys.argv[4]).read_text(encoding="utf-8")

assert dispatch["request"]["skill"] == "report"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
published = [
    event for event in events
    if event.get("type") == "ArtifactPublished"
    and event.get("cycle_id") == dispatch["cycle_id"]
]
assert published
artifact = published[-1]["artifact"]
entry = entries_dir / Path(artifact).name
text = entry.read_text(encoding="utf-8")
assert "# Plain Runtime Report" in text
assert "artifact-producing skill close with text only in stdout" in text
assert "edge-runner: published artifact blog/entries/" in runner_stdout
assert "artifact-producing skill close with text only in stdout" not in runner_stdout
PY
then
    pass "plain terminal prose is captured as an artifact without dumping the body"
else
    fail "plain terminal prose is captured as an artifact without dumping the body"
fi

echo "--- Test 1e: artifact supervisor retries acknowledgement-only backend failure ---"
export MOCK_CLAUDE_ENV_OUT="$TMP_BASE/cycle-id-retry.txt"
export MOCK_CLAUDE_ARGS_OUT="$TMP_BASE/args-retry.txt"
rm -f "$MOCK_CLAUDE_ENV_OUT" "$MOCK_CLAUDE_ARGS_OUT" "$TMP_BASE/retry.out"
export MOCK_CLAUDE_FAIL_ONCE=1
export MOCK_CLAUDE_FAIL_ONCE_OUTPUT="Acknowledged — staying out of Frostpeck's way."
export MOCK_CLAUDE_ARTIFACT_MARKDOWN=$'# Retry Published Report\n\nThe artifact supervisor retried a backend response that only acknowledged and did not publish. This second attempt produces a complete runtime-published report artifact.'
"$RUNNER_TOOL" skill \
    --skill /research \
    --dispatch-trigger operator \
    --dispatch-policy operator \
    --dispatch-routing-mode explicit \
    --dispatch-preflight-profile heartbeat_default \
    --dispatch-postflight-profile standard \
    --dispatch-force >"$TMP_BASE/retry.out"
unset MOCK_CLAUDE_FAIL_ONCE MOCK_CLAUDE_FAIL_ONCE_OUTPUT MOCK_CLAUDE_ARTIFACT_MARKDOWN || true

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$TMP_EDGE/blog/entries" "$TMP_BASE/retry.out" "$TMP_BASE/args-retry.txt"
import json
import sys
from pathlib import Path

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
entries_dir = Path(sys.argv[3])
runner_stdout = Path(sys.argv[4]).read_text(encoding="utf-8")
args_log = Path(sys.argv[5]).read_text(encoding="utf-8")

assert dispatch["request"]["skill"] == "research"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert args_log.count("__INVOCATION__") == 2
assert "ARTIFACT SUPERVISOR RETRY" in args_log
retry_started = [
    event for event in events
    if event.get("type") == "ArtifactSupervisionRetryStarted"
    and event.get("cycle_id") == dispatch["cycle_id"]
]
retry_completed = [
    event for event in events
    if event.get("type") == "ArtifactSupervisionRetryCompleted"
    and event.get("cycle_id") == dispatch["cycle_id"]
]
assert retry_started
assert retry_completed
assert retry_completed[-1]["payload"]["published"] is True
published = [
    event for event in events
    if event.get("type") == "ArtifactPublished"
    and event.get("cycle_id") == dispatch["cycle_id"]
]
assert published
artifact = published[-1]["artifact"]
entry = entries_dir / Path(artifact).name
assert "Retry Published Report" in entry.read_text(encoding="utf-8")
assert "edge-runner: published artifact blog/entries/" in runner_stdout
assert "Frostpeck" not in runner_stdout
PY
then
    pass "artifact supervisor retries acknowledgement-only backend failure"
else
    fail "artifact supervisor retries acknowledgement-only backend failure"
fi

echo "--- Test 2: dispatched skill success without artifact closes as failed ---"
unset MOCK_CLAUDE_HEARTBEAT_FLOW || true
cat >"$TMP_EDGE/state/dispatch-queue.json" <<'JSON'
[
  {
    "entry_id": "queue-map-no-artifact",
    "source": "test-suite",
    "skill": "map",
    "reason": "exercise missing artifact close gate"
  }
]
JSON
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
assert dispatch["request"]["skill"] == "map"
assert dispatch["state"]["skill_dispatched"] is True
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "missing_artifact_published"
PY
then
    pass "runner downgrades artifactless dispatched skill success to failed"
else
    fail "runner downgrades artifactless dispatched skill success to failed"
fi
printf '[]\n' >"$TMP_EDGE/state/dispatch-queue.json"

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
assert dispatch["state"]["close_reason"] in ("", None, "postflight_step_warning")
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
assert dispatch["state"]["close_reason"] in ("", None, "postflight_step_warning")
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
    stdout = ""
    stderr = ""

def fake_run(cmd, *, env, cwd, input, text, capture_output):
    captured["cmd"] = cmd
    captured["input"] = input
    captured["text"] = text
    captured["cwd"] = cwd
    captured["capture_output"] = capture_output
    return Result()

module.resolve_claude_bin = lambda: "/mock/claude"
module.subprocess.run = fake_run
os.environ["EDGE_RUNNER_SKILL_TIMEOUT_SEC"] = "0"
try:
    status, output = module.invoke_backend(args, {"EDGE_REPO_DIR": edge_dir}, cycle_id=None)
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
assert captured["capture_output"] is True
assert output == ""
PY
then
    pass "large backend prompt is streamed through stdin"
else
    fail "large backend prompt is streamed through stdin"
fi

echo "--- Test 10: health snapshot refresh timeout falls back to the last snapshot ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import importlib
import json
import os
import sys
import time
from pathlib import Path

edge_dir = Path(sys.argv[1])
tmp_base = Path(sys.argv[2])
runtime = tmp_base / "health-timeout-runtime"
(runtime / "bin").mkdir(parents=True, exist_ok=True)
(runtime / "health").mkdir(parents=True, exist_ok=True)
(runtime / "bin" / "edge-check.sh").write_text("#!/usr/bin/env bash\nsleep 10\n", encoding="utf-8")
(runtime / "bin" / "edge-check.sh").chmod(0o755)
(runtime / "health" / "current.json").write_text(
    json.dumps({"status": "degraded", "score": 67, "ts": "2026-05-02T00:00:00+00:00"}),
    encoding="utf-8",
)

sys.path.insert(0, str(edge_dir / "tools"))
module = importlib.import_module("_shared.dispatch_runtime")
module.EDGE_REPO_DIR = runtime
module.HEALTH_CURRENT_FILE = runtime / "health" / "current.json"
os.environ["EDGE_PREFLIGHT_HEALTH_TIMEOUT_SEC"] = "1"
started = time.monotonic()
try:
    snapshot = module._health_snapshot()
finally:
    os.environ.pop("EDGE_PREFLIGHT_HEALTH_TIMEOUT_SEC", None)
elapsed = time.monotonic() - started

assert elapsed < 4, elapsed
assert snapshot["status"] == "degraded"
assert snapshot["score"] == 67
assert snapshot["refresh_status"] == "stale_timeout"
assert "timeout" in snapshot["refresh_reason"]
PY
then
    pass "health snapshot refresh timeout falls back to the last snapshot"
else
    fail "health snapshot refresh timeout falls back to the last snapshot"
fi

echo "--- Test 11: preflight claims summary uses cached projections ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import importlib
import json
import os
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
tmp_base = Path(sys.argv[2])
runtime = tmp_base / "claims-cache-runtime"
projection_dir = runtime / "state" / "projections"
projection_dir.mkdir(parents=True, exist_ok=True)
claims_path = projection_dir / "claims-digest.json"
orphans_path = projection_dir / "orphan-claims.json"
claims_path.write_text(json.dumps({"open_total": 2, "verified_total": 5, "attention_count": 1}), encoding="utf-8")
orphans_path.write_text(json.dumps({"orphan_total": 3, "open_orphan_total": 1}), encoding="utf-8")

sys.path.insert(0, str(edge_dir / "tools"))
module = importlib.import_module("_shared.dispatch_runtime")
module.CLAIMS_DIGEST_FILE = claims_path
module.ORPHAN_CLAIMS_FILE = orphans_path
if hasattr(module, "refresh_continuity_projections"):
    def _explode():
        raise AssertionError("preflight claims summary must not refresh continuity projections")
    module.refresh_continuity_projections = _explode

os.environ["EDGE_PREFLIGHT_CLAIMS_MAX_AGE_SEC"] = "86400"
try:
    claims, orphans = module._claims_summary()
finally:
    os.environ.pop("EDGE_PREFLIGHT_CLAIMS_MAX_AGE_SEC", None)

assert claims["open_total"] == 2
assert claims["verified_total"] == 5
assert claims["projection_status"] == "cached"
assert orphans["orphan_total"] == 3
assert orphans["open_orphan_total"] == 1
assert orphans["projection_status"] == "cached"
PY
then
    pass "preflight claims summary uses cached projections"
else
    fail "preflight claims summary uses cached projections"
fi

echo "--- Test 12: runner evidence gates scan bounded JSONL tails ---"
if python3 - <<'PY' "$EDGE_DIR" "$TMP_BASE"
import importlib.machinery
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

edge_dir = Path(sys.argv[1])
tmp_base = Path(sys.argv[2])
state_dir = tmp_base / "runner-tail-runtime" / "state" / "events"
state_dir.mkdir(parents=True, exist_ok=True)
events_path = state_dir / "log.jsonl"
steps_path = tmp_base / "runner-tail-runtime" / "logs" / "skill-steps.jsonl"
steps_path.parent.mkdir(parents=True, exist_ok=True)

cycle_id = "cycle-tail-proof"
old_cycle = "cycle-old"
threshold = "2026-05-02T00:00:00+00:00"
large_payload = "x" * 2048
with events_path.open("w", encoding="utf-8") as handle:
    for index in range(5000):
        handle.write(json.dumps({
            "ts": "2026-05-01T00:00:00+00:00",
            "type": "ArtifactPublished",
            "cycle_id": old_cycle,
            "artifact": f"blog/entries/old-{index}.md",
            "payload": {"noise": large_payload},
        }) + "\n")
    handle.write(json.dumps({
        "ts": "2026-05-02T00:01:00+00:00",
        "type": "SkillRunCompleted",
        "cycle_id": cycle_id,
        "payload": {"skill": "strategy", "registry_skill": "strategy"},
    }) + "\n")
    handle.write(json.dumps({
        "ts": "2026-05-02T00:02:00+00:00",
        "type": "ArtifactPublished",
        "cycle_id": cycle_id,
        "artifact": "blog/entries/current.md",
        "payload": {"artifact": "blog/entries/current.md"},
    }) + "\n")

loader = importlib.machinery.SourceFileLoader("edge_runner", str(edge_dir / "tools" / "edge-runner"))
spec = importlib.util.spec_from_loader("edge_runner", loader)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

module.STATE_EVENTS_FILE = events_path
module.SKILL_STEPS_FILE = steps_path
module.read_dispatch_state = lambda: {
    "cycle_id": cycle_id,
    "request": {"skill": "strategy"},
    "state": {"skill_dispatched": True, "dispatched_at": threshold},
}
os.environ["EDGE_JSONL_TAIL_BYTES"] = "8192"
try:
    assert module.skill_run_completed_for_cycle(cycle_id, "strategy") is True
    assert module.artifact_published_for_cycle(cycle_id) is True
finally:
    os.environ.pop("EDGE_JSONL_TAIL_BYTES", None)

assert events_path.stat().st_size > 8 * 1024 * 1024
PY
then
    pass "runner evidence gates scan bounded JSONL tails"
else
    fail "runner evidence gates scan bounded JSONL tails"
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
