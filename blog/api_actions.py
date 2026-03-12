"""Action endpoints for operator task management, heartbeat trigger, and thread actions."""

import json
from datetime import datetime, timezone

import yaml
from flask import Blueprint, jsonify, request

from blog.services import (
    TASKS_SNAPSHOT, TASKS_JSONL, LOGS_DIR, STATE_DIR, THREADS_DIR,
    load_tasks_snapshot,
)

actions_bp = Blueprint('actions', __name__)

OPERATOR_LOG = LOGS_DIR / "operator-actions.jsonl"
VALID_ACTIONS = {"done", "blocked", "doing", "todo", "note", "reprioritize"}
HEARTBEAT_TRIGGER_FILE = STATE_DIR / "heartbeat-trigger.json"
HEARTBEAT_RATE_LIMIT_SECONDS = 600  # 10 minutes


def _log_operator_action(task_id, action, reason=None, value=None):
    """Append action to operator-actions.jsonl."""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": "operator",
        "task_id": task_id,
        "action": action,
    }
    if reason:
        entry["reason"] = reason
    if value is not None:
        entry["value"] = value
    OPERATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(OPERATOR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _append_task_event(task_id, op, **kwargs):
    """Append event to tasks.jsonl."""
    event = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "op": op,
        "task_id": task_id,
        "updated_by": "operator",
    }
    event.update(kwargs)
    with open(TASKS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _save_snapshot(snap):
    """Write tasks snapshot atomically."""
    tmp = TASKS_SNAPSHOT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(TASKS_SNAPSHOT)


@actions_bp.route('/api/tasks/<task_id>/action', methods=['POST'])
def task_action(task_id):
    """Execute an action on a task."""
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    reason = data.get("reason")
    value = data.get("value")

    if not action or action not in VALID_ACTIONS:
        return jsonify({"error": f"Invalid action. Must be one of: {', '.join(sorted(VALID_ACTIONS))}"}), 400

    snap = load_tasks_snapshot()
    if task_id not in snap:
        return jsonify({"error": f"Task {task_id} not found"}), 404

    task = snap[task_id]
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if action in ("done", "blocked", "doing", "todo"):
        old_status = task.get("status")
        task["status"] = action
        task["updated_at"] = now_str
        if reason:
            task["notes"] = (task.get("notes", "") + f" | {reason}").strip(" |")
        # Append to task history
        hist_entry = {"ts": now_str, "op": "update", "task_id": task_id,
                       "updated_by": "operator", "status": action}
        if reason:
            hist_entry["reason"] = reason
        task.setdefault("history", []).append(hist_entry)
        if action == "done":
            task["resolution"] = reason or "Marked done by operator"
            hist_entry["op"] = "resolve"
            hist_entry["resolution"] = task["resolution"]
        _append_task_event(task_id, "resolve" if action == "done" else "update",
                           status=action, **({"reason": reason} if reason else {}))

    elif action == "note":
        if not value:
            return jsonify({"error": "Note action requires 'value' field"}), 400
        task["notes"] = (task.get("notes", "") + f" | {value}").strip(" |")
        task["updated_at"] = now_str
        task.setdefault("history", []).append({
            "ts": now_str, "op": "note", "task_id": task_id,
            "updated_by": "operator", "note": value,
        })
        _append_task_event(task_id, "note", note=value)

    elif action == "reprioritize":
        if not value or value not in ("P0", "P1", "P2", "P3"):
            return jsonify({"error": "Reprioritize requires 'value' in P0-P3"}), 400
        task["priority"] = value
        task["updated_at"] = now_str
        task.setdefault("history", []).append({
            "ts": now_str, "op": "update", "task_id": task_id,
            "updated_by": "operator", "priority": value,
        })
        _append_task_event(task_id, "update", priority=value)

    snap[task_id] = task
    _save_snapshot(snap)
    _log_operator_action(task_id, action, reason=reason, value=value)

    return jsonify({"ok": True, "task": task}), 200


@actions_bp.route('/api/heartbeat/trigger', methods=['POST'])
def heartbeat_trigger():
    """Manually trigger a heartbeat. Rate-limited to 1 per 10 minutes."""
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Check rate limit
    if HEARTBEAT_TRIGGER_FILE.exists():
        try:
            prev = json.loads(HEARTBEAT_TRIGGER_FILE.read_text(encoding="utf-8"))
            prev_ts = datetime.fromisoformat(prev["ts"].replace("Z", "+00:00"))
            elapsed = (now - prev_ts).total_seconds()
            if elapsed < HEARTBEAT_RATE_LIMIT_SECONDS:
                remaining = int(HEARTBEAT_RATE_LIMIT_SECONDS - elapsed)
                return jsonify({
                    "error": "Rate limited. Try again later.",
                    "retry_after_seconds": remaining,
                }), 429
        except Exception:
            pass  # Corrupted file -- allow trigger

    # Write trigger file
    trigger = {"ts": now_str, "actor": "operator"}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_TRIGGER_FILE.write_text(
        json.dumps(trigger, ensure_ascii=False), encoding="utf-8"
    )

    # Log action
    _log_operator_action("heartbeat", "trigger")

    return jsonify({"ok": True, "triggered_at": now_str}), 200


VALID_THREAD_ACTIONS = {"active", "dormant", "done"}


@actions_bp.route('/api/threads/<thread_id>/action', methods=['POST'])
def thread_action(thread_id):
    """Change a thread's status."""
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    reason = data.get("reason")

    if not action or action not in VALID_THREAD_ACTIONS:
        return jsonify({
            "error": f"Invalid action. Must be one of: {', '.join(sorted(VALID_THREAD_ACTIONS))}"
        }), 400

    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return jsonify({"error": f"Thread {thread_id} not found"}), 404

    # Parse YAML frontmatter and body
    raw = thread_path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return jsonify({"error": "Thread file has invalid frontmatter"}), 400

    try:
        fm = yaml.safe_load(parts[1])
    except Exception:
        return jsonify({"error": "Failed to parse thread frontmatter"}), 400

    old_status = fm.get("status")
    fm["status"] = action
    fm["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Rebuild file: --- frontmatter --- body
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True).rstrip("\n")
    new_content = f"---\n{new_fm}\n---{parts[2]}"
    thread_path.write_text(new_content, encoding="utf-8")

    # Log action
    _log_operator_action(thread_id, f"thread:{action}", reason=reason)

    return jsonify({
        "ok": True,
        "thread_id": thread_id,
        "old_status": old_status,
        "new_status": action,
    }), 200
