#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-runtime-interventions-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"
AUTONOMY_DIR="$EDGE_DIR/autonomy"
CAP_FILE="$AUTONOMY_DIR/capabilities.md"
FRONTIER_FILE="$AUTONOMY_DIR/frontier.md"
CAP_BACKUP="$TMP_BASE/capabilities.md.bak"
FRONTIER_BACKUP="$TMP_BASE/frontier.md.bak"

cleanup() {
    if [ -f "$CAP_BACKUP" ]; then
        mv "$CAP_BACKUP" "$CAP_FILE"
    else
        rm -f "$CAP_FILE"
    fi
    if [ -f "$FRONTIER_BACKUP" ]; then
        mv "$FRONTIER_BACKUP" "$FRONTIER_FILE"
    else
        rm -f "$FRONTIER_FILE"
    fi
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state/events" "$TMP_STATE/logs" "$TMP_STATE/blog/entries" "$TMP_STATE/state/signals" "$TMP_STATE/search" "$AUTONOMY_DIR"

if [ -f "$CAP_FILE" ]; then cp "$CAP_FILE" "$CAP_BACKUP"; fi
if [ -f "$FRONTIER_FILE" ]; then cp "$FRONTIER_FILE" "$FRONTIER_BACKUP"; fi

cat >"$TMP_STATE/state/current-dispatch.json" <<'JSON'
{
  "version": 1,
  "cycle_id": "cycle-20260420T220000Z-runtime",
  "request": {
    "trigger": "heartbeat",
    "skill": "reflection",
    "policy": "autonomous"
  },
  "state": {
    "active": true,
    "phase": "skill_dispatched",
    "skill_dispatched": true,
    "preflight_status": "completed",
    "skill_status": "running",
    "postflight_status": "pending",
    "opened_at": "2026-04-20T22:00:00+00:00",
    "dispatched_at": "2026-04-20T22:01:00+00:00",
    "updated_at": "2026-04-20T22:01:30+00:00"
  }
}
JSON

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-20T21:00:00+00:00","type":"CycleStarted","cycle_id":"cycle-a","payload":{"trigger":"heartbeat"}}
{"ts":"2026-04-20T21:01:00+00:00","type":"SkillDispatched","cycle_id":"cycle-a","payload":{"trigger":"heartbeat","skill":"planner","dispatch_mode":"normal"}}
{"ts":"2026-04-20T21:20:00+00:00","type":"CycleClosed","cycle_id":"cycle-a","payload":{"trigger":"heartbeat","skill":"planner","close_status":"completed"}}
{"ts":"2026-04-21T01:00:00+00:00","type":"CycleStarted","cycle_id":"cycle-followup","payload":{"trigger":"operator"}}
{"ts":"2026-04-21T01:01:00+00:00","type":"SkillDispatched","cycle_id":"cycle-followup","payload":{"trigger":"operator","skill":"repair","dispatch_mode":"normal"}}
{"ts":"2026-04-21T01:15:00+00:00","type":"CycleClosed","cycle_id":"cycle-followup","payload":{"trigger":"operator","skill":"repair","close_status":"completed"}}
JSONL

cat >"$TMP_STATE/logs/skill-steps.jsonl" <<'JSONL'
{"skill":"reflection","event":"end","expected":5,"done":4,"explicit_skips":1,"silent_skips":["crossref"],"completion_pct":80,"ts":"2026-04-20T22:02:00"}
JSONL

cat >"$TMP_STATE/state/primitives-status.json" <<'JSON'
{
  "generated_at": "2026-04-20T22:10:00+00:00",
  "summary": {
    "window_days": 30,
    "declared_total": 2,
    "contract_only_total": 0,
    "active_total": 1,
    "probed_total": 0,
    "broken_total": 1,
    "drifted_total": 0,
    "usage_30d_total": 12,
    "counts_by_effective_status": {
      "broken": 1,
      "active": 1
    },
    "health_status": "fail"
  },
  "sources": [
    {
      "name": "exa",
      "effective_status": "broken",
      "probe_status": "fail",
      "usage_30d": 10,
      "manifest_status": "active",
      "problems": ["last_probe_failed"]
    },
    {
      "name": "grok",
      "effective_status": "active",
      "probe_status": "unknown",
      "usage_30d": 2,
      "manifest_status": "active",
      "problems": []
    }
  ]
}
JSON

cat >"$TMP_STATE/state/ops-hotspots.json" <<'JSON'
{
  "generated_at": "2026-04-20T22:12:00+00:00",
  "window": "48h",
  "incidents": [],
  "top_pain": [],
  "recovered_but_unstable": [
    {
      "signature": "exa timeout on retry",
      "count": 3,
      "last_seen": "2026-04-20T22:05:00+00:00"
    }
  ],
  "codify_now": [
    {
      "signature": "missing pre-skill evidence guardrail",
      "count": 4,
      "last_seen": "2026-04-20T22:06:00+00:00"
    }
  ]
}
JSON

cat >"$TMP_STATE/state/proposals.json" <<'JSON'
[
  {
    "id": "prop-runtime-1",
    "title": "Instrument explicit pre-skill evidence",
    "type": "runtime",
    "status": "active",
    "created": "2026-04-20T22:12:00+00:00",
    "updated": "2026-04-20T22:12:00+00:00",
    "evidence": ["GAP-101"]
  }
]
JSON

cat >"$TMP_STATE/state/tasks.snapshot.json" <<'JSON'
{
  "version": 1,
  "tasks": [
    {
      "id": "TASK-RUNTIME-001",
      "title": "Investigate exa guardrail",
      "status": "todo",
      "priority": "P1",
      "owner": "ed",
      "blocked": false
    }
  ]
}
JSON

cat >"$CAP_FILE" <<'MD'
| # | Name | Sheridan |
|---|------|----------|
| 1 | Safe execution | 8 |
| 2 | Runtime transparency | 4 |
| 3 | Primitive stewardship | 3 |
MD

cat >"$FRONTIER_FILE" <<'MD'
### GAP-101: instrument explicit pre-skill evidence
MD

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
import json
import os
import sys
from pathlib import Path

edge_dir = os.environ["EDGE_REPO_DIR"]
state_dir = Path(os.environ["EDGE_STATE_DIR"])
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()

seed = client.get("/api/dashboard/runtime")
assert seed.status_code == 200, seed.status_code
seed_data = seed.get_json()

cycle_id = seed_data["runtime_current_cycle"]["cycle_id"]
primitive_id = seed_data["runtime_primitives"]["top_sources"][0]["id"]
frontier_id = seed_data["runtime_autonomy"]["next_steps"][0]["id"]
codify_id = seed_data["runtime_autonomy"]["codify_now"][0]["id"]

dispatch = client.post(
    f"/api/runtime/dispatch/{cycle_id}/action",
    json={
        "action": "require-review",
        "reason": "cycle needs explicit human review before continuation",
        "label": "reflection",
        "reference": cycle_id,
    },
)
assert dispatch.status_code == 200, dispatch.status_code
assert dispatch.get_json()["queued"] is True
assert dispatch.get_json()["dispatch_mode"] == "next-dispatch"

evidence = client.post(
    "/api/runtime/evidence/pre-skill/action",
    json={
        "action": "incomplete",
        "reason": "pre-skill evidence is still missing operator-grade detail",
        "label": "pre-skill evidence",
        "reference": cycle_id,
    },
)
assert evidence.status_code == 200, evidence.status_code

primitive = client.post(
    f"/api/runtime/primitive/{primitive_id}/action",
    json={
        "action": "confirm-failure",
        "reason": "probe failure is reproducible and should not be ignored",
        "label": "exa",
        "reference": "exa",
    },
)
assert primitive.status_code == 200, primitive.status_code

proposal = client.post(
    f"/api/runtime/autonomy/{frontier_id}/action",
    json={
        "action": "promote-proposal",
        "reason": "frontier gap should become an explicit proposal",
        "value": "Instrument explicit pre-skill evidence",
        "label": "instrument explicit pre-skill evidence",
        "reference": frontier_id,
    },
)
assert proposal.status_code == 200, proposal.status_code

task = client.post(
    f"/api/runtime/autonomy/{codify_id}/action",
    json={
        "action": "promote-task",
        "reason": "codify-now incident needs a concrete operator-visible task",
        "value": "Investigate exa guardrail",
        "label": "missing pre-skill evidence guardrail",
        "reference": "missing pre-skill evidence guardrail",
    },
)
assert task.status_code == 200, task.status_code
assert task.get_json()["resulting_state"] == "queued"

messages = client.get("/api/chat?unprocessed=1").get_json()["messages"]
intents = [m for m in messages if m["author"] == "user" and m["text"].startswith("[runtime-intent]")]
assert len(intents) == 5
assert any("target_type: dispatch" in m["text"] for m in intents)
assert any("target_type: evidence" in m["text"] for m in intents)
assert any("target_type: primitive" in m["text"] for m in intents)
assert any("target_type: autonomy" in m["text"] for m in intents)
assert any("Instrument explicit pre-skill evidence" in m["text"] for m in intents)
assert any("Investigate exa guardrail" in m["text"] for m in intents)

operator_log = [
    json.loads(line)
    for line in (state_dir / "logs" / "operator-actions.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
assert operator_log[-1]["action"] == "runtime:promote-task"
assert operator_log[-1]["target_type"] == "autonomy"
assert operator_log[-1]["resulting_state"] == "queued"

runtime = client.get("/api/dashboard/runtime")
assert runtime.status_code == 200, runtime.status_code
data = runtime.get_json()
assert data["runtime_queued_count"] == 5
assert data["runtime_intervention_trace_count"] == 5
assert data["runtime_intervention_lineage_count"] == 5
assert {item["action"] for item in data["runtime_intervention_trace"]} == {
    "runtime:require-review",
    "runtime:incomplete",
    "runtime:confirm-failure",
    "runtime:promote-proposal",
    "runtime:promote-task",
}

proposal_lineage = next(item for item in data["runtime_intervention_lineage"] if item["display_action"] == "promote-proposal")
assert proposal_lineage["downstream_target"]["type"] == "proposal"
assert proposal_lineage["downstream_target"]["label"] == "Instrument explicit pre-skill evidence"

task_lineage = next(item for item in data["runtime_intervention_lineage"] if item["display_action"] == "promote-task")
assert task_lineage["downstream_target"]["type"] == "task"
assert task_lineage["downstream_target"]["label"] == "Investigate exa guardrail"

dispatch_lineage = next(item for item in data["runtime_intervention_lineage"] if item["display_action"] == "require-review")
assert dispatch_lineage["reference"] == cycle_id
assert dispatch_lineage["downstream_cycles"][0]["cycle_id"] == "cycle-followup"

partial = client.get("/partials/runtime")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "queued for next dispatch" in text
assert "intervention lineage" in text
assert "require review" in text
assert "Instrument explicit pre-skill evidence" in text
assert "Investigate exa guardrail" in text
print("ok")
PY
