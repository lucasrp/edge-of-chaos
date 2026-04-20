#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-interventions-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_STATE/state" "$TMP_STATE/logs" "$TMP_STATE/blog/entries" "$TMP_STATE/search"

cat >"$TMP_STATE/state/tasks.snapshot.json" <<'JSON'
{
  "version": 1,
  "tasks": [
    {
      "id": "TASK-20260309-001",
      "title": "Dispatch operator feedback",
      "status": "todo",
      "priority": "P1",
      "owner": "ed",
      "blocked": false,
      "criteria": ["operator feedback queued"]
    }
  ]
}
JSON

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

note = client.post(
    "/api/tasks/TASK-20260309-001/action",
    json={"action": "note", "value": "integration-test-ping"},
)
assert note.status_code == 200, note.status_code
note_data = note.get_json()
assert note_data["queued"] is True
assert note_data["duplicate"] is False

blocked = client.post(
    "/api/tasks/TASK-20260309-001/action",
    json={"action": "block", "reason": "waiting on operator"},
)
assert blocked.status_code == 200, blocked.status_code
blocked_data = blocked.get_json()
assert blocked_data["queued"] is True
assert blocked_data["dispatch_mode"] == "next-dispatch"

snapshot = json.loads((state_dir / "state" / "tasks.snapshot.json").read_text(encoding="utf-8"))
assert snapshot["tasks"][0]["id"] == "TASK-20260309-001"
assert snapshot["tasks"][0]["status"] == "todo"
assert snapshot["tasks"][0]["blocked"] is False

messages = client.get("/api/chat?unprocessed=1").get_json()["messages"]
intents = [m for m in messages if m["author"] == "user" and m["text"].startswith("[task-intent]")]
assert len(intents) == 2
assert "integration-test-ping" in intents[0]["text"]
assert "waiting on operator" in intents[1]["text"]

operator_log = [
    json.loads(line)
    for line in (state_dir / "logs" / "operator-actions.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
assert operator_log[-1]["action"] == "task-intent:block"

resp = client.get("/api/dashboard/interventions")
assert resp.status_code == 200, resp.status_code
data = resp.get_json()
assert data["tasks_total"] == 1
assert data["task_attention_count"] == 1
assert data["tasks"][0]["status"] == "todo"
assert data["queued_task_count"] == 2
assert {item["action"] for item in data["queued_task_intents"]} == {"note", "block"}
assert data["operator_actions"][0]["action"] == "task-intent:block"

partial = client.get("/partials/interventions")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "task interventions" in text
assert "queued for next dispatch" in text
assert "TASK-20260309-001" in text
assert "integration-test-ping" in text
assert "waiting on operator" in text
print("ok")
PY
