#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-proposals-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"
TMP_HOME="$TMP_BASE/home"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/threads" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/state/signals" \
    "$TMP_STATE/search" \
    "$TMP_HOME/.claude/projects/test-project/memory/topics"

cat >"$TMP_HOME/.claude/projects/test-project/memory/topics/dispatch.md" <<'MD'
# Dispatch transparency
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-dispatch.md" <<'MD'
---
title: "Dispatch evidence review"
date: "2026-04-20"
claims:
  - "Dispatch cycles need explicit close evidence"
threads:
  - runtime-transparency
report: dispatch-evidence.html
---
body
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-gap.md" <<'MD'
---
title: "Gap tracking note"
date: "2026-04-20"
claims:
  - "!Pre-skill is still not instrumented"
threads:
  - runtime-transparency
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

cat >"$TMP_STATE/reports/dispatch-evidence.html" <<'HTML'
<html><body>report</body></html>
HTML

cat >"$TMP_STATE/state/proposals.json" <<'JSON'
[
  {
    "id": "prop-1",
    "title": "Surface lineage in dashboard",
    "type": "execution",
    "status": "active",
    "created": "2026-04-20T20:00:00+00:00",
    "updated": "2026-04-20T20:10:00+00:00",
    "hypothesis": "Operators need decision-ready proposals instead of a flat ideas list.",
    "action": "Put lineage and downstream state next to the proposal itself.",
    "impact": "Cuts decision latency in the dashboard.",
    "risk": "Could surface weak evidence too aggressively.",
    "evidence": ["Dispatch evidence review", "Dispatch cycles need explicit close evidence"],
    "cost": "medium"
  },
  {
    "id": "prop-2",
    "title": "Promote claim gap tracker",
    "type": "experiment",
    "status": "active",
    "created": "2026-04-20T20:05:00+00:00",
    "updated": "2026-04-20T20:12:00+00:00",
    "hypothesis": "Gap claims should ask for revision instead of silently aging.",
    "action": "Turn gap claims into revision queues.",
    "evidence": ["Pre-skill is still not instrumented"],
    "cost": "low"
  },
  {
    "id": "prop-3",
    "title": "Queue operator-visible evidence",
    "type": "execution",
    "status": "approved",
    "created": "2026-04-19T12:00:00+00:00",
    "updated": "2026-04-20T19:00:00+00:00",
    "evidence": ["Dispatch evidence review"],
    "cost": "low"
  },
  {
    "id": "prop-4",
    "title": "Archive old workflow board",
    "type": "execution",
    "status": "deferred",
    "created": "2026-04-18T12:00:00+00:00",
    "updated": "2026-04-18T13:00:00+00:00",
    "evidence": []
  }
]
JSON

cat >"$TMP_STATE/state/signals/decision.md" <<'MD'
- Approved dashboard lineage slice
- Deferred workflow board cleanup
MD

HOME="$TMP_HOME" MEMORY_PROJECT_DIR="test-project" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
import os
import sys

edge_dir = os.environ["EDGE_REPO_DIR"]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()

resp = client.get("/api/dashboard/epistemics")
assert resp.status_code == 200, resp.status_code
data = resp.get_json()
proposals = data["ep_proposals"]

assert proposals["total"] == 4
assert proposals["needs_decision_count"] == 2
assert proposals["approved_waiting_count"] == 1
assert proposals["deferred_count"] == 1
assert proposals["low_evidence_count"] == 3

prop_1 = next(item for item in proposals["needs_decision"] if item["id"] == "prop-1")
assert prop_1["linked_claims_count"] >= 1
assert prop_1["linked_threads_count"] >= 1

revision = client.post(
    "/api/steering/proposal/prop-2/action",
    json={
        "action": "request-revision",
        "reason": "the evidence is still too thin for a direct approval",
        "label": "Promote claim gap tracker",
        "reference": "Pre-skill is still not instrumented",
    },
)
assert revision.status_code == 200, revision.status_code
assert revision.get_json()["queued"] is True

resp = client.get("/api/dashboard/epistemics")
assert resp.status_code == 200, resp.status_code
data = resp.get_json()
proposals = data["ep_proposals"]
assert proposals["needs_revision_count"] == 1
assert proposals["queued_count"] == 1

detail = client.get("/proposal/prop-2")
assert detail.status_code == 200, detail.status_code
detail_html = detail.get_data(as_text=True)
assert "Proposal Snapshot" in detail_html
assert "Queued Steering" in detail_html
assert "Pre-skill is still not instrumented" in detail_html

partial = client.get("/partials/epistemics")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "proposals console" in text
assert "needs decision" in text
assert "needs revision" in text
assert "approved / waiting execution" in text
assert "deferred / parked" in text
assert "Surface lineage in dashboard" in text
assert "Queue operator-visible evidence" in text
print("ok")
PY
