#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-submenu-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"
TMP_HOME="$TMP_BASE/home"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/state/signals" \
    "$TMP_STATE/threads" \
    "$TMP_STATE/topics" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/search"

cat >"$TMP_STATE/blog/entries/2026-04-21-dashboard.md" <<'MD'
---
title: "Dashboard shakedown"
date: "2026-04-21"
claims:
  - "Dashboard sections should load independently"
threads:
  - dashboard-split
report: dashboard-shakedown.html
---
body
MD

cat >"$TMP_STATE/threads/dashboard-split.md" <<'MD'
---
id: dashboard-split
title: "Dashboard split"
status: active
owner: ed
goal: "Keep the dashboard readable and fast"
---
## Next
Split the dashboard into focused sections.
MD

cat >"$TMP_STATE/reports/dashboard-shakedown.html" <<'HTML'
<html><body>report</body></html>
HTML

cat >"$TMP_STATE/state/proposals.json" <<'JSON'
[
  {
    "id": "prop-dashboard-split",
    "title": "Split dashboard by section",
    "type": "execution",
    "status": "active",
    "created": "2026-04-21T02:00:00+00:00",
    "updated": "2026-04-21T02:05:00+00:00",
    "evidence": ["Dashboard shakedown"]
  }
]
JSON

HOME="$TMP_HOME" MEMORY_PROJECT_DIR="test-project" EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
import os
import sys

edge_dir = os.environ["EDGE_REPO_DIR"]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()

overview = client.get("/dashboard")
assert overview.status_code == 200, overview.status_code
overview_html = overview.get_data(as_text=True)
assert "dashboard-subnav" in overview_html
assert 'hx-get="/partials/dashboard-section?section=runtime"' in overview_html
assert 'hx-get="/partials/alerts"' in overview_html
assert 'hx-get="/partials/pipeline"' in overview_html
assert "proposals console" not in overview_html
assert "task interventions" not in overview_html

runtime = client.get("/dashboard?section=runtime")
assert runtime.status_code == 200, runtime.status_code
runtime_html = runtime.get_data(as_text=True)
assert "runtime transparency" in runtime_html
assert 'hx-get="/partials/alerts"' not in runtime_html

work = client.get("/dashboard?section=work")
assert work.status_code == 200, work.status_code
work_html = work.get_data(as_text=True)
assert "task interventions" in work_html
assert "runtime transparency" not in work_html

epistemics = client.get("/dashboard?section=epistemics")
assert epistemics.status_code == 200, epistemics.status_code
epistemics_html = epistemics.get_data(as_text=True)
assert "epistemic & steering" in epistemics_html
assert "proposals console" in epistemics_html
assert "attention required" not in epistemics_html

threads = client.get("/dashboard?section=threads")
assert threads.status_code == 200, threads.status_code
threads_html = threads.get_data(as_text=True)
assert '<h2 class="dash-section-title">threads</h2>' in threads_html
assert "proposals console" not in threads_html

knowledge = client.get("/dashboard?section=knowledge")
assert knowledge.status_code == 200, knowledge.status_code
knowledge_html = knowledge.get_data(as_text=True)
assert "knowledge clusters" in knowledge_html
assert "epistemic & steering" not in knowledge_html

fallback = client.get("/dashboard?section=unknown")
assert fallback.status_code == 200, fallback.status_code
fallback_html = fallback.get_data(as_text=True)
assert 'hx-get="/partials/alerts"' in fallback_html

runtime_partial = client.get("/partials/dashboard-section?section=runtime")
assert runtime_partial.status_code == 200, runtime_partial.status_code
runtime_partial_html = runtime_partial.get_data(as_text=True)
assert "runtime transparency" in runtime_partial_html
assert "dashboard-status-strip" not in runtime_partial_html
assert 'hx-get="/partials/alerts"' not in runtime_partial_html

fallback_partial = client.get("/partials/dashboard-section?section=unknown")
assert fallback_partial.status_code == 200, fallback_partial.status_code
assert 'hx-get="/partials/alerts"' in fallback_partial.get_data(as_text=True)
print("ok")
PY
