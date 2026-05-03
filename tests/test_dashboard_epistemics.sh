#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-epistemics-XXXXXX)"
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

mkdir -p "$TMP_STATE/blog/entries" "$TMP_STATE/state/signals" "$TMP_STATE/threads" "$TMP_STATE/topics"

if [ -f "$STRATEGY_FILE" ]; then cp "$STRATEGY_FILE" "$STRATEGY_BACKUP"; fi

cat >"$STRATEGY_FILE" <<'MD'
# Strategy

Stabilize runtime visibility while tightening epistemic curation.

- make hidden belief-state visible in the dashboard
- connect active threads to operator direction
- reduce ambiguity between artifacts and steering state
MD

cat >"$TMP_STATE/topics/dispatch.md" <<'MD'
# Dispatch transparency
MD

cat >"$TMP_STATE/topics/lineage.md" <<'MD'
# Knowledge lineage
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-claims-a.md" <<'MD'
---
title: "Dispatch evidence review"
date: "2026-04-20"
open_gaps:
  - "Pre-skill is still not instrumented"
claims:
  - claim: "!Pre-skill is still not instrumented"
    status: open
threads:
  - runtime-transparency
report: dispatch-evidence.html
---
body
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-claims-b.md" <<'MD'
---
title: "Strategy alignment note"
date: "2026-04-20"
open_gaps: []
claims:
  - claim: "Strategy alignment has an explicit steering surface"
    status: verified
threads:
  - strategy-alignment
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

cat >"$TMP_STATE/threads/strategy-alignment.md" <<'MD'
---
id: strategy-alignment
title: "Strategy alignment"
status: proposed
owner: ed
goal: "Make direction explicit and inspectable"
---
## Next
Link active work to strategy.
MD

cat >"$TMP_STATE/state/proposals.json" <<'JSON'
[
  {"id":"prop-1","title":"Surface lineage in dashboard","type":"execution","status":"active","created":"2026-04-20T20:00:00+00:00","updated":"2026-04-20T20:10:00+00:00","evidence":["Dispatch evidence review","Strategy alignment note"],"cost":"medium"},
  {"id":"prop-2","title":"Promote open gap tracker","type":"experiment","status":"active","created":"2026-04-20T20:05:00+00:00","updated":"2026-04-20T20:12:00+00:00","evidence":["Pre-skill is still not instrumented"]}
]
JSON

cat >"$TMP_STATE/state/signals/decision.md" <<'MD'
- Approved dashboard lineage slice
- Deferred planning board cleanup
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

assert data["ep_open_gaps"]["open_total"] == 1
assert data["ep_open_gaps"]["entries_with_gaps"] == 1
assert data["ep_strategy"]["available"] is True
assert data["ep_strategy"]["topics_total"] == 2
assert len(data["ep_strategy"]["objectives"]) >= 2
assert data["ep_proposals"]["active_count"] == 2
assert len(data["ep_proposals"]["decisions"]) == 2
assert len(data["ep_lineage"]) >= 2

partial = client.get("/partials/epistemics")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "epistemic & steering" in text
assert "Dispatch evidence review" in text
assert "Surface lineage in dashboard" in text
assert "Runtime transparency" in text
print("ok")
PY
