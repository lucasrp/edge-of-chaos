#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-close-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"
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

mkdir -p "$TMP_EDGE/blog/entries" "$TMP_EDGE/reports" "$TMP_EDGE/state/events" "$TMP_EDGE/logs" "$TMP_EDGE/state"

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
  - id: curation
    kind: curation.digest
  - id: briefing
    kind: briefing.refresh
  - id: cycle-health
    kind: cycle_health.observe
YAML

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

DISPATCH_TOOL="$EDGE_DIR/tools/edge-dispatch"
CLOSE_TOOL="$EDGE_DIR/tools/edge-close"
STEP_TOOL="$EDGE_DIR/tools/edge-skill-step"

append_artifact_published() {
    local cycle_id="$1"
    local skill="$2"
    local slug="$3"
    python3 - <<'PY' "$TMP_EDGE/state/events/log.jsonl" "$cycle_id" "$skill" "$slug"
import json
import sys
from datetime import datetime, timezone

path, cycle_id, skill, slug = sys.argv[1:5]
event = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "type": "ArtifactPublished",
    "actor": "continuity",
    "cycle_id": cycle_id,
    "artifact": f"blog/entries/{slug}.md",
    "payload": {"source_skill": skill},
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
}

append_phase_failed() {
    local cycle_id="$1"
    local slug="$2"
    local reason="$3"
    python3 - <<'PY' "$TMP_EDGE/state/events/log.jsonl" "$cycle_id" "$slug" "$reason"
import json
import sys
from datetime import datetime, timezone

path, cycle_id, slug, reason = sys.argv[1:5]
event = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "type": "PhaseCompleted",
    "actor": "consolidate-state",
    "cycle_id": cycle_id,
    "artifact": f"blog/entries/{slug}.md",
    "payload": {
        "pipeline": "consolidate-state",
        "phase": "review",
        "ok": False,
        "reason": reason,
    },
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
}

append_skill_completed() {
    local cycle_id="$1"
    local skill="$2"
    python3 - <<'PY' "$TMP_EDGE/state/events/log.jsonl" "$cycle_id" "$skill"
import json
import sys
from datetime import datetime, timezone

path, cycle_id, skill = sys.argv[1:4]
event = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "type": "SkillRunCompleted",
    "actor": "edge-runner",
    "cycle_id": cycle_id,
    "payload": {
        "skill": skill,
        "registry_skill": skill,
        "event": "end",
        "expected": 1,
        "done": 1,
        "explicit_skips": 0,
        "silent_skips": [],
        "completion_pct": 100,
    },
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
}

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

echo "--- Test 1b: edge-close refuses to close a different EDGE_CYCLE_ID ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-mismatch --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
for step in direction explore application persistence; do
    EDGE_CYCLE_ID=cycle-close-mismatch "$STEP_TOOL" discovery "$step" >/dev/null
done
EDGE_CYCLE_ID=cycle-close-mismatch "$STEP_TOOL" discovery end >/dev/null
set +e
EDGE_CYCLE_ID=cycle-other "$CLOSE_TOOL" --status completed >/dev/null 2>/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
status = int(sys.argv[2])

assert status == 1
assert dispatch["cycle_id"] == "cycle-close-mismatch"
assert dispatch["state"]["active"] is True
assert dispatch["state"]["close_status"] is None
PY
then
    pass "edge-close validates EDGE_CYCLE_ID before postflight"
else
    fail "edge-close validates EDGE_CYCLE_ID before postflight"
fi

EDGE_CYCLE_ID=cycle-close-mismatch "$DISPATCH_TOOL" close --status aborted >/dev/null

echo "--- Test 2: completed close is rejected without artifact publication evidence ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-no-artifact --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
for step in direction explore application persistence; do
    EDGE_CYCLE_ID=cycle-close-no-artifact "$STEP_TOOL" discovery "$step" >/dev/null
done
EDGE_CYCLE_ID=cycle-close-no-artifact "$STEP_TOOL" discovery end >/dev/null
set +e
"$CLOSE_TOOL" --status completed >/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
status = int(sys.argv[3])

assert status == 1
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "missing_artifact_published"
assert dispatch["state"]["postflight_status"] == "failed"
assert dispatch["state"]["artifact_supervision_status"] == "blocked"
assert dispatch["state"]["artifact_supervision_reason"] == "missing_artifact_published"
assert dispatch["state"]["artifact_supervision_required"] is True
blocked = [
    event for event in events
    if event.get("cycle_id") == "cycle-close-no-artifact"
    and event.get("type") == "ArtifactSupervisionBlocked"
]
assert blocked
payload = blocked[-1]["payload"]
assert payload["required"] is True
assert payload["reason"] == "missing_artifact_published"
PY
then
    pass "edge-close requires artifact publication for publishing skills"
else
    fail "edge-close requires artifact publication for publishing skills"
fi

echo "--- Test 2b: heartbeat router closes without artifact publication evidence ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-heartbeat-router --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill roberto-heartbeat >/dev/null
append_skill_completed cycle-close-heartbeat-router roberto-heartbeat
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/logs/post-skill.log" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
postflight = open(sys.argv[2], encoding="utf-8").read()
events = [json.loads(line) for line in open(sys.argv[3], encoding="utf-8") if line.strip()]
steps = dispatch["state"].get("postflight_steps", [])

assert dispatch["request"]["skill"] == "roberto-heartbeat"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["close_reason"] != "missing_artifact_published"
assert dispatch["state"]["postflight_status"] in {"completed", "warning"}
assert "procedure: artifact_supervision | status: OK" not in postflight
assert dispatch["state"]["artifact_supervision_status"] == "not_required"
assert dispatch["state"]["artifact_supervision_required"] is False
assert any(
    event.get("cycle_id") == "cycle-close-heartbeat-router"
    and event.get("type") == "ArtifactSupervisionSkipped"
    for event in events
)
assert len(steps) >= 6
PY
then
    pass "edge-close exempts heartbeat router from artifact publication"
else
    fail "edge-close exempts heartbeat router from artifact publication"
fi

echo "--- Test 2c: non-heartbeat skills require artifact publication regardless of prefix ---"
"$DISPATCH_TOOL" open --trigger operator --cycle-id cycle-close-prefixed-no-artifact --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill roberto-autonomy >/dev/null
EDGE_CYCLE_ID=cycle-close-prefixed-no-artifact "$STEP_TOOL" /roberto-autonomy diagnosis >/dev/null
EDGE_CYCLE_ID=cycle-close-prefixed-no-artifact "$STEP_TOOL" /roberto-autonomy end >/dev/null
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
assert dispatch["request"]["trigger"] == "operator"
assert dispatch["request"]["skill"] == "roberto-autonomy"
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "missing_artifact_published"
assert dispatch["state"]["postflight_status"] == "failed"
assert dispatch["state"]["artifact_supervision_status"] == "blocked"
assert dispatch["state"]["artifact_supervision_required"] is True
PY
then
    pass "edge-close requires artifact publication for prefixed non-heartbeat skills"
else
    fail "edge-close requires artifact publication for prefixed non-heartbeat skills"
fi

echo "--- Test 2d: delta and loader support skills are artifact-exempt ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))
from _shared.skill_policy import skill_requires_artifact_publication

assert not skill_requires_artifact_publication("delta")
assert not skill_requires_artifact_publication("ed-delta", instance="ed")
assert not skill_requires_artifact_publication("loader")
assert not skill_requires_artifact_publication("ed-loader", instance="ed")
assert not skill_requires_artifact_publication("heartbeat")
assert skill_requires_artifact_publication("autonomy")
assert skill_requires_artifact_publication("ed-autonomy", instance="ed")
assert skill_requires_artifact_publication("reflection")
PY
then
    pass "edge-close policy exempts delta and loader support skills only"
else
    fail "edge-close policy exempts delta and loader support skills only"
fi

echo "--- Test 2e: failed publication pipeline is reported by artifact supervision ---"
"$DISPATCH_TOOL" open --trigger operator --cycle-id cycle-close-pipeline-blocked --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill research >/dev/null
append_skill_completed cycle-close-pipeline-blocked research
append_phase_failed cycle-close-pipeline-blocked blocked-report review_gate_failed
set +e
"$CLOSE_TOOL" --status completed >/dev/null
STATUS=$?
set -e

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl" "$STATUS"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
events = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
status = int(sys.argv[3])

assert status == 1
assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "failed"
assert dispatch["state"]["close_reason"] == "pipeline_blocked_before_publish"
assert dispatch["state"]["artifact_supervision_status"] == "blocked"
assert dispatch["state"]["artifact_supervision_reason"] == "pipeline_blocked_before_publish"
evidence = dispatch["state"]["artifact_supervision_evidence"]
assert evidence["artifact"] == "blog/entries/blocked-report.md"
assert evidence["reason"] == "review_gate_failed"
blocked = [
    event for event in events
    if event.get("cycle_id") == "cycle-close-pipeline-blocked"
    and event.get("type") == "ArtifactSupervisionBlocked"
]
assert blocked
payload = blocked[-1]["payload"]
assert payload["pipeline_evidence"]["reason"] == "review_gate_failed"
PY
then
    pass "edge-close reports failed pipeline evidence through artifact supervision"
else
    fail "edge-close reports failed pipeline evidence through artifact supervision"
fi

echo "--- Test 3: completed close succeeds with skill end evidence, artifact publication, and postflight ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-complete --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
for step in direction explore application persistence; do
    EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery "$step" >/dev/null
done
EDGE_CYCLE_ID=cycle-close-complete "$STEP_TOOL" discovery end >/dev/null
append_artifact_published cycle-close-complete discovery complete
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/logs/post-skill.log" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
postflight = open(sys.argv[2], encoding="utf-8").read()
events = [json.loads(line) for line in open(sys.argv[3], encoding="utf-8") if line.strip()]
steps = dispatch["state"].get("postflight_steps", [])
delta = dispatch["state"].get("postflight_delta", {})

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["postflight_status"] in {"completed", "warning"}
assert dispatch["state"]["artifact_supervision_status"] == "published"
assert dispatch["state"]["artifact_supervision_reason"] == "artifact_published"
assert dispatch["state"]["artifact_supervision_artifact"] == "blog/entries/complete.md"
assert any(
    event.get("cycle_id") == "cycle-close-complete"
    and event.get("type") == "ArtifactSupervisionCompleted"
    and event.get("artifact") == "blog/entries/complete.md"
    for event in events
)
assert postflight.strip()
assert len(steps) >= 6
assert "claims_open_delta" in delta
PY
then
    pass "edge-close completes only after skill end evidence, artifact publication, and enriched postflight"
else
    fail "edge-close completes only after skill end evidence, artifact publication, and enriched postflight"
fi

echo "--- Test 4: autofixable validate_recent becomes warning, not failed close ---"
TODAY="$(date +%Y-%m-%d)"
cat >"$TMP_EDGE/blog/entries/2026-04-22-warning.md" <<EOF
---
date: $TODAY
title: Warning Example
report: reports/2026-04-22-warning.html
tags: [note]
---

warning body
EOF
cat >"$TMP_EDGE/reports/2026-04-22-warning.html" <<'EOF'
<html><body>warning report</body></html>
EOF
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-warning --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
for step in direction explore application persistence; do
    EDGE_CYCLE_ID=cycle-close-warning "$STEP_TOOL" discovery "$step" >/dev/null
done
EDGE_CYCLE_ID=cycle-close-warning "$STEP_TOOL" discovery end >/dev/null
append_artifact_published cycle-close-warning discovery warning
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/blog/entries/2026-04-22-warning.md"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))
entry = open(sys.argv[2], encoding="utf-8").read()

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
assert dispatch["state"]["close_reason"] == "postflight_step_warning"
assert dispatch["state"]["postflight_status"] == "warning"
assert "report: 2026-04-22-warning.html" in entry
PY
then
    pass "autofixable validate_recent closes as completed with warning"
else
    fail "autofixable validate_recent closes as completed with warning"
fi

echo "--- Test 5: mixed aware/naive completion timestamps still close successfully ---"
"$DISPATCH_TOOL" open --trigger heartbeat --cycle-id cycle-close-naive-mixed --force >/dev/null
"$DISPATCH_TOOL" dispatch --skill discovery >/dev/null
python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json" "$TMP_EDGE/state/events/log.jsonl"
import json
import sys

dispatch_path, events_path = sys.argv[1], sys.argv[2]
dispatch = json.load(open(dispatch_path, encoding="utf-8"))
dispatch["cycle_id"] = "cycle-close-naive-mixed"
dispatch["request"]["skill"] = "discovery"
dispatch["state"]["opened_at"] = "2026-04-22T00:00:00+00:00"
dispatch["state"]["dispatched_at"] = "2026-04-22T00:00:01+00:00"
json.dump(dispatch, open(dispatch_path, "w", encoding="utf-8"), indent=2)
with open(dispatch_path, "a", encoding="utf-8") as fh:
    fh.write("\n")

event = {
    "ts": "2026-04-22T00:00:02",
    "type": "SkillRunCompleted",
    "cycle_id": "cycle-close-naive-mixed",
    "payload": {"skill": "discovery", "registry_skill": "discovery"},
}
with open(events_path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
artifact = {
    "ts": "2026-04-22T00:00:03",
    "type": "ArtifactPublished",
    "actor": "continuity",
    "cycle_id": "cycle-close-naive-mixed",
    "artifact": "blog/entries/naive-mixed.md",
    "payload": {"source_skill": "discovery"},
}
with open(events_path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(artifact) + "\n")
PY
"$CLOSE_TOOL" --status completed >/dev/null

if python3 - <<'PY' "$TMP_EDGE/state/current-dispatch.json"
import json
import sys

dispatch = json.load(open(sys.argv[1], encoding="utf-8"))

assert dispatch["state"]["active"] is False
assert dispatch["state"]["close_status"] == "completed"
PY
then
    pass "mixed aware/naive timestamps do not break edge-close"
else
    fail "mixed aware/naive timestamps do not break edge-close"
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
