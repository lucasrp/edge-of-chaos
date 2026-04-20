"""Action endpoints for heartbeat, threads, and task interventions."""

import json
from datetime import datetime, timezone

import yaml
from flask import Blueprint, jsonify, request

from blog.services import LOGS_DIR, STATE_DIR, TASKS_LOG_FILE, TASKS_SNAPSHOT_FILE, THREADS_DIR

actions_bp = Blueprint('actions', __name__)

OPERATOR_LOG = LOGS_DIR / "operator-actions.jsonl"
HEARTBEAT_TRIGGER_FILE = STATE_DIR / "heartbeat-trigger.json"
HEARTBEAT_RATE_LIMIT_SECONDS = 600
VALID_TASK_ACTIONS = {
    "note",
    "acknowledge",
    "block",
    "unblock",
    "prioritize",
    "deprioritize",
    "ready",
    "done",
    "defer",
}


def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_operator_action(target_id, action, reason=None, value=None):
    entry = {
        "ts": _now_str(),
        "actor": "operator",
        "target_id": target_id,
        "action": action,
    }
    if reason:
        entry["reason"] = reason
    if value is not None:
        entry["value"] = value
    OPERATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(OPERATOR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _append_jsonl(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_task_snapshot():
    if not TASKS_SNAPSHOT_FILE.exists():
        return {"version": 1, "tasks": []}
    try:
        raw = json.loads(TASKS_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "tasks": []}

    if isinstance(raw, list):
        return {"version": 1, "tasks": raw}
    if isinstance(raw, dict):
        tasks = raw.get("tasks")
        if tasks is None and isinstance(raw.get("items"), list):
            tasks = raw["items"]
        if not isinstance(tasks, list):
            tasks = []
        return {"version": raw.get("version", 1), "tasks": tasks}
    return {"version": 1, "tasks": []}


def _write_task_snapshot(snapshot):
    TASKS_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_SNAPSHOT_FILE.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _default_task(task_id):
    return {
        "id": task_id,
        "title": task_id,
        "summary": "",
        "status": "todo",
        "priority": "P2",
        "owner": "operator",
        "blocked": False,
        "criteria": [],
        "history": [],
    }


def _priority_shift(priority, direction):
    ladder = ["P0", "P1", "P2", "P3"]
    current = str(priority or "P2").upper()
    if current not in ladder:
        current = "P2"
    index = ladder.index(current)
    if direction == "up":
        index = max(0, index - 1)
    elif direction == "down":
        index = min(len(ladder) - 1, index + 1)
    return ladder[index]


def _apply_task_action(task, action, reason=None, value=None):
    ts = _now_str()
    old_status = str(task.get("status") or "todo")
    old_priority = str(task.get("priority") or "P2").upper()

    if action == "acknowledge":
        task["status"] = "acknowledged" if old_status in {"", "todo", "deferred"} else old_status
        task["acknowledged_at"] = ts
    elif action == "block":
        task["blocked"] = True
        task["status"] = "blocked"
        if reason:
            task["block_reason"] = reason
    elif action == "unblock":
        task["blocked"] = False
        task.pop("block_reason", None)
        if old_status == "blocked":
            task["status"] = "ready"
    elif action == "prioritize":
        task["priority"] = _priority_shift(task.get("priority"), "up")
    elif action == "deprioritize":
        task["priority"] = _priority_shift(task.get("priority"), "down")
    elif action == "ready":
        task["blocked"] = False
        task.pop("block_reason", None)
        task["status"] = "ready"
    elif action == "done":
        task["blocked"] = False
        task.pop("block_reason", None)
        task["status"] = "done"
        task["completed_at"] = ts
    elif action == "defer":
        task["blocked"] = False
        task["status"] = "deferred"

    task["updated_at"] = ts

    history = task.get("history")
    if not isinstance(history, list):
        history = []
    history_entry = {
        "ts": ts,
        "actor": "operator",
        "action": action,
    }
    if reason:
        history_entry["reason"] = reason
    if value is not None:
        history_entry["value"] = value
    history.append(history_entry)
    task["history"] = history

    return {
        "ts": ts,
        "old_status": old_status,
        "new_status": task.get("status"),
        "old_priority": old_priority,
        "new_priority": task.get("priority"),
        "blocked": bool(task.get("blocked")),
    }


@actions_bp.route('/api/heartbeat/trigger', methods=['POST'])
def heartbeat_trigger():
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if HEARTBEAT_TRIGGER_FILE.exists():
        try:
            prev = json.loads(HEARTBEAT_TRIGGER_FILE.read_text(encoding="utf-8"))
            prev_ts = datetime.fromisoformat(prev["ts"].replace("Z", "+00:00"))
            elapsed = (now - prev_ts).total_seconds()
            if elapsed < HEARTBEAT_RATE_LIMIT_SECONDS:
                return jsonify({"error": "Rate limited.", "retry_after_seconds": int(HEARTBEAT_RATE_LIMIT_SECONDS - elapsed)}), 429
        except Exception:
            pass
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_TRIGGER_FILE.write_text(json.dumps({"ts": now_str, "actor": "operator"}, ensure_ascii=False), encoding="utf-8")
    _log_operator_action("heartbeat", "trigger")
    return jsonify({"ok": True, "triggered_at": now_str}), 200


VALID_THREAD_ACTIONS = {"active", "dormant", "done"}


@actions_bp.route('/api/threads/<thread_id>/action', methods=['POST'])
def thread_action(thread_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    reason = data.get("reason")
    if not action or action not in VALID_THREAD_ACTIONS:
        return jsonify({"error": f"Invalid action. Must be one of: {', '.join(sorted(VALID_THREAD_ACTIONS))}"}), 400
    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return jsonify({"error": f"Thread {thread_id} not found"}), 404
    raw = thread_path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return jsonify({"error": "Invalid frontmatter"}), 400
    try:
        fm = yaml.safe_load(parts[1])
    except Exception:
        return jsonify({"error": "Failed to parse frontmatter"}), 400
    old_status = fm.get("status")
    fm["status"] = action
    fm["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True).rstrip("\n")
    thread_path.write_text(f"---\n{new_fm}\n---{parts[2]}", encoding="utf-8")
    _log_operator_action(thread_id, f"thread:{action}", reason=reason)
    return jsonify({"ok": True, "thread_id": thread_id, "old_status": old_status, "new_status": action}), 200


@actions_bp.route('/api/tasks/<task_id>/action', methods=['POST'])
def task_action(task_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip() or None
    value = data.get("value")

    if action not in VALID_TASK_ACTIONS:
        return jsonify({"error": f"Invalid action. Must be one of: {', '.join(sorted(VALID_TASK_ACTIONS))}"}), 400

    snapshot = _load_task_snapshot()
    tasks = snapshot["tasks"]

    task = None
    for item in tasks:
        if isinstance(item, dict) and str(item.get("id") or item.get("task_id") or "") == task_id:
            task = item
            break
    if task is None:
        task = _default_task(task_id)
        tasks.append(task)

    mutation = _apply_task_action(task, action, reason=reason, value=value)
    snapshot["tasks"] = tasks
    _write_task_snapshot(snapshot)

    event = {
        "ts": mutation["ts"],
        "actor": "operator",
        "task_id": task_id,
        "action": action,
        "status": task.get("status"),
        "priority": task.get("priority"),
        "blocked": bool(task.get("blocked")),
    }
    if reason:
        event["reason"] = reason
    if value is not None:
        event["value"] = value

    _append_jsonl(TASKS_LOG_FILE, event)
    _log_operator_action(task_id, f"task:{action}", reason=reason, value=value)

    return jsonify({
        "ok": True,
        "task_id": task_id,
        "task": task,
        **mutation,
    }), 200
