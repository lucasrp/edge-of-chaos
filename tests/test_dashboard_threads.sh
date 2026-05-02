#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-threads-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p \
    "$TMP_STATE/threads" \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/state/events" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/notes" \
    "$TMP_STATE/search"

cat >"$TMP_STATE/threads/attention-thread.md" <<'MD'
---
id: attention-thread
title: "Attention Thread"
type: investigation
status: active
owner: ed
created: 2026-04-18
updated: 2026-04-18
resurface: 2026-04-19
goal: "Explain queue latency drift"
done_when: "root cause and mitigation are documented"
---

## Context

Latency is drifting and nobody can tell why.

## Next step

[definir]
MD

cat >"$TMP_STATE/threads/healthy-thread.md" <<'MD'
---
id: healthy-thread
title: "Healthy Thread"
type: execution
status: active
owner: ed
created: 2026-04-19
updated: 2026-04-20
resurface: 2026-04-26
goal: "Ship queue diagnostics"
done_when: "report and benchmark are linked"
---

## Context

The queue diagnostics slice is moving and has current evidence.

## Next step

Compare the new benchmark against the previous dispatch.
MD

cat >"$TMP_STATE/threads/waiting-thread.md" <<'MD'
---
id: waiting-thread
title: "Waiting Thread"
type: investigation
status: waiting
owner: roberto
created: 2026-04-19
updated: 2026-04-20
resurface: 2026-04-25
---

## Context

Waiting on an external benchmark before dispatching the next step.

## Next step

Re-run the benchmark once the external sample lands.
MD

cat >"$TMP_STATE/threads/proposed-thread.md" <<'MD'
---
id: proposed-thread
title: "Proposed Thread"
type: investigation
status: proposed
owner: ed
created: 2026-04-20
updated: 2026-04-20
resurface: 2026-04-27
---

## Context

This candidate has not been activated yet.
MD

cat >"$TMP_STATE/threads/done-thread.md" <<'MD'
---
id: done-thread
title: "Done Thread"
type: investigation
status: done
owner: ed
created: 2026-04-15
updated: 2026-04-20
resurface: 2026-05-01
---

## Context

This thread is already complete.
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-healthy.md" <<'MD'
---
title: "Measured queue latency"
date: 2026-04-20
threads:
  - healthy-thread
open_gaps:
  - "Need benchmark on smaller archive"
report: healthy-report.html
note: healthy-note.md
---

Benchmark run with the new queue diagnostics.
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-waiting.md" <<'MD'
---
title: "Collected external sample"
date: 2026-04-20
threads:
  - waiting-thread
open_gaps: []
---

Waiting for the external benchmark to land.
MD

cat >"$TMP_STATE/reports/healthy-report.html" <<'HTML'
<html><body>healthy report</body></html>
HTML

cat >"$TMP_STATE/notes/healthy-note.md" <<'MD'
# healthy note
MD

cat >"$TMP_STATE/logs/events.jsonl" <<'JSONL'
{"timestamp":"2026-04-20T21:00:00+00:00","type":"skill_dispatched","summary":"advanced synthesis","thread_id":"healthy-thread","skill":"research","artifacts":["healthy-report.html"]}
{"timestamp":"2026-04-20T21:11:00+00:00","type":"thread_updated","summary":"waiting for external benchmark","thread_id":"waiting-thread","skill":"review"}
JSONL

cat >"$TMP_STATE/state/events/log.jsonl" <<'JSONL'
{"ts":"2026-04-20T21:00:00+00:00","type":"SkillDispatched","cycle_id":"cycle-healthy","payload":{"thread_id":"healthy-thread","skill":"research","summary":"advanced synthesis","artifacts":["healthy-report.html"]}}
{"ts":"2026-04-20T21:11:00+00:00","type":"ThreadUpdated","cycle_id":"cycle-waiting","payload":{"thread_id":"waiting-thread","summary":"waiting for external benchmark","skill":"review"}}
JSONL

cat >"$TMP_STATE/logs/operator-actions.jsonl" <<'JSONL'
{"ts":"2026-04-20T21:05:00Z","actor":"operator","target_id":"healthy-thread","action":"thread:worked","target_type":"thread","label":"Healthy Thread","reference":"healthy-thread","resulting_state":"applied","value":"2026-04-27"}
{"ts":"2026-04-20T21:12:00Z","actor":"operator","target_id":"waiting-thread","action":"thread:waiting","target_type":"thread","label":"Waiting Thread","reference":"waiting-thread","resulting_state":"applied","reason":"external benchmark"}
JSONL

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

threads_partial = client.get("/partials/threads")
assert threads_partial.status_code == 200, threads_partial.status_code
threads_html = threads_partial.get_data(as_text=True)
assert "needs attention" in threads_html
assert "in progress" in threads_html
assert "waiting" in threads_html
assert "Attention Thread" in threads_html
assert "Healthy Thread" in threads_html
assert "external benchmark" in threads_html
assert "last evidence" in threads_html
assert "last beat" in threads_html
assert "no next step" in threads_html

detail = client.get("/thread/healthy-thread")
assert detail.status_code == 200, detail.status_code
detail_html = detail.get_data(as_text=True)
assert "Operational Snapshot" in detail_html
assert "Beat History" in detail_html
assert "advanced synthesis" in detail_html
assert "cycle-healthy" in detail_html
assert "Operator Actions" in detail_html

status_strip = client.get("/partials/status-strip")
assert status_strip.status_code == 200, status_strip.status_code
strip_html = status_strip.get_data(as_text=True)
assert "1 waiting" in strip_html

waiting = client.post(
    "/api/threads/proposed-thread/action",
    json={"action": "waiting", "reason": "operator review"},
)
assert waiting.status_code == 200, waiting.status_code
waiting_data = waiting.get_json()
assert waiting_data["new_status"] == "waiting"

updated_thread = (state_dir / "threads" / "proposed-thread.md").read_text(encoding="utf-8")
assert "status: waiting" in updated_thread

operator_log = [
    json.loads(line)
    for line in (state_dir / "logs" / "operator-actions.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
assert operator_log[-1]["action"] == "thread:waiting"
assert operator_log[-1]["reason"] == "operator review"
assert operator_log[-1]["target_type"] == "thread"
print("ok")
PY
