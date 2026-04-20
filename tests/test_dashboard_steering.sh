#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-steering-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"
TMP_HOME="$TMP_BASE/home"
STRATEGY_FILE="$EDGE_DIR/config/strategy.md"
STRATEGY_BACKUP="$TMP_BASE/strategy.md.bak"

cleanup() {
    if [ -f "$STRATEGY_BACKUP" ]; then
        mv "$STRATEGY_BACKUP" "$STRATEGY_FILE"
    else
        rm -f "$STRATEGY_FILE"
    fi
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/blog/entries" "$TMP_STATE/state/signals" "$TMP_STATE/threads" "$TMP_STATE/logs" "$TMP_STATE/search" "$TMP_HOME/.claude/projects/test-project/memory/topics"

if [ -f "$STRATEGY_FILE" ]; then cp "$STRATEGY_FILE" "$STRATEGY_BACKUP"; fi

cat >"$STRATEGY_FILE" <<'MD'
# Strategy

Make epistemic steering explicit and operator-visible.

- keep steering decisions queued for the next dispatch
- show claim and proposal direction without hidden markdown edits
- tie runtime visibility to explicit operator direction
MD

cat >"$TMP_HOME/.claude/projects/test-project/memory/topics/dispatch.md" <<'MD'
# Dispatch transparency
MD

cat >"$TMP_HOME/.claude/projects/test-project/memory/topics/epistemics.md" <<'MD'
# Epistemic steering
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-claims-a.md" <<'MD'
---
title: "Dispatch evidence review"
date: "2026-04-20"
claims:
  - "Dispatch cycles need explicit close evidence"
  - "!Pre-skill is still not instrumented"
threads:
  - runtime-transparency
report: dispatch-evidence.html
---
body
MD

cat >"$TMP_STATE/threads/runtime-transparency.md" <<'MD'
---
id: runtime-transparency
title: "Runtime transparency"
status: active
owner: ed
goal: "Expose dispatch and evidence state to the operator"
---
## Next
Ship the runtime dashboard section.
MD

cat >"$TMP_STATE/state/proposals.json" <<'JSON'
[
  {
    "id": "prop-1",
    "title": "Surface lineage in dashboard",
    "type": "execution",
    "status": "active",
    "created": "2026-04-20T20:00:00+00:00",
    "updated": "2026-04-20T20:10:00+00:00",
    "evidence": ["Dispatch evidence review", "Dispatch cycles need explicit close evidence"],
    "cost": "medium"
  }
]
JSON

cat >"$TMP_STATE/state/signals/decision.md" <<'MD'
- Approved dashboard lineage slice
MD

HOME="$TMP_HOME" MEMORY_PROJECT_DIR="test-project" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
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

seed = client.get("/api/dashboard/epistemics")
assert seed.status_code == 200, seed.status_code
seed_data = seed.get_json()

claim_id = seed_data["ep_claims"]["recent"][0]["claim_id"]
claim_label = seed_data["ep_claims"]["recent"][0]["text"]
proposal_id = seed_data["ep_proposals"]["active"][0]["id"]
proposal_label = seed_data["ep_proposals"]["active"][0]["title"]
topic_id = seed_data["ep_strategy"]["topics"][0]["id"]
topic_label = seed_data["ep_strategy"]["topics"][0]["title"]
objective_id = seed_data["ep_strategy"]["objectives"][0]["id"]
objective_label = seed_data["ep_strategy"]["objectives"][0]["title"]

proposal = client.post(
    f"/api/steering/proposal/{proposal_id}/action",
    json={
        "action": "approve",
        "reason": "evidence is already aligned with operator intent",
        "label": proposal_label,
        "reference": "Dispatch evidence review",
    },
)
assert proposal.status_code == 200, proposal.status_code
assert proposal.get_json()["queued"] is True
assert proposal.get_json()["dispatch_mode"] == "next-dispatch"

proposal_dup = client.post(
    f"/api/steering/proposal/{proposal_id}/action",
    json={
        "action": "approve",
        "reason": "evidence is already aligned with operator intent",
        "label": proposal_label,
        "reference": "Dispatch evidence review",
    },
)
assert proposal_dup.status_code == 200, proposal_dup.status_code
assert proposal_dup.get_json()["duplicate"] is True

claim = client.post(
    f"/api/steering/claim/{claim_id}/action",
    json={
        "action": "disputed",
        "reason": "pre-skill evidence is still incomplete",
        "label": claim_label,
        "reference": "2026-04-20-claims-a.md",
    },
)
assert claim.status_code == 200, claim.status_code

topic = client.post(
    f"/api/steering/topic/{topic_id}/action",
    json={
        "action": "prioritize",
        "reason": "dispatch transparency should stay ahead of other topics",
        "label": topic_label,
        "reference": "dispatch.md",
    },
)
assert topic.status_code == 200, topic.status_code

objective = client.post(
    f"/api/steering/objective/{objective_id}/action",
    json={
        "action": "attach",
        "reason": "the next dispatch should bind this objective explicitly",
        "label": objective_label,
        "reference": objective_id,
    },
)
assert objective.status_code == 200, objective.status_code

strategy = client.post(
    "/api/steering/strategy/global/action",
    json={
        "action": "redirect",
        "reason": "runtime evidence needs tighter operator focus",
        "value": "focus runtime evidence over prose cleanup on the next dispatch",
        "label": "strategy",
        "reference": "config/strategy.md",
    },
)
assert strategy.status_code == 200, strategy.status_code
strategy_data = strategy.get_json()
assert strategy_data["queued"] is True
assert strategy_data["resulting_state"] == "queued"

messages = client.get("/api/chat?unprocessed=1").get_json()["messages"]
intents = [m for m in messages if m["author"] == "user" and m["text"].startswith("[steering-intent]")]
assert len(intents) == 5
assert any("target_type: proposal" in m["text"] for m in intents)
assert any("target_type: claim" in m["text"] for m in intents)
assert any("target_type: topic" in m["text"] for m in intents)
assert any("target_type: objective" in m["text"] for m in intents)
assert any("target_type: strategy" in m["text"] for m in intents)
assert any("focus runtime evidence over prose cleanup on the next dispatch" in m["text"] for m in intents)

operator_log = [
    json.loads(line)
    for line in (state_dir / "logs" / "operator-actions.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
assert operator_log[-1]["action"] == "steering:redirect"
assert operator_log[-1]["target_type"] == "strategy"
assert operator_log[-1]["resulting_state"] == "queued"
assert operator_log[-1]["apply"] == "next-dispatch"

resp = client.get("/api/dashboard/epistemics")
assert resp.status_code == 200, resp.status_code
data = resp.get_json()
assert data["ep_queued_steering_count"] == 5
assert {item["target_type"] for item in data["ep_queued_steering"]} == {"proposal", "claim", "topic", "objective", "strategy"}
assert data["ep_steering_trace_count"] == 5
assert {item["action"] for item in data["ep_steering_trace"]} == {
    "steering:approve",
    "steering:disputed",
    "steering:prioritize",
    "steering:attach",
    "steering:redirect",
}

partial = client.get("/partials/epistemics")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "queued for next dispatch" in text
assert "steering trace" in text
assert "Surface lineage in dashboard" in text
assert "Dispatch cycles need explicit close evidence" in text
assert "focus runtime evidence over prose cleanup on the next dispatch" in text
print("ok")
PY
