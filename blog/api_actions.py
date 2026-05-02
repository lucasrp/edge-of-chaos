"""Action endpoints for heartbeat, threads, and queued operator interventions."""

import json
from datetime import datetime, timezone

import yaml
from flask import Blueprint, jsonify, request

from blog.services import LOGS_DIR, STATE_DIR, THREADS_DIR

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


def _log_operator_action(target_id, action, reason=None, value=None, **extra):
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
    for key, item in extra.items():
        if item is not None:
            entry[key] = item
    OPERATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(OPERATOR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _build_task_intent_text(task_id, action, reason=None, value=None):
    lines = [
        "[task-intent]",
        f"task: {task_id}",
        f"action: {action}",
        "apply: next-dispatch",
    ]
    if reason:
        lines.append(f"reason: {reason}")
    if value is not None:
        lines.append(f"value: {value}")
    lines.append("note: queue this operator task intervention for the next dispatch; do not apply it immediately")
    return "\n".join(lines)


def _parse_task_intent_text(text):
    if not text or not str(text).startswith("[task-intent]"):
        return None
    data = {}
    for line in str(text).splitlines()[1:]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if key:
            data[key] = value
    task_id = data.get("task")
    action = data.get("action")
    if not task_id or not action:
        return None
    return {
        "task_id": task_id,
        "action": action,
        "reason": data.get("reason"),
        "value": data.get("value"),
        "apply": data.get("apply"),
        "note": data.get("note"),
    }


def _find_pending_task_intent(task_id, action, reason=None, value=None):
    from dashboard_db import get_chats

    for message in get_chats(unprocessed_only=True, limit=200):
        if message.get("author") != "user":
            continue
        parsed = _parse_task_intent_text(message.get("text", ""))
        if not parsed:
            continue
        if parsed["task_id"] != task_id or parsed["action"] != action:
            continue
        if (parsed.get("reason") or None) != reason:
            continue
        if (parsed.get("value") or None) != (None if value is None else str(value)):
            continue
        return message
    return None


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


VALID_THREAD_ACTIONS = {"active", "waiting", "dormant", "done"}
VALID_STEERING_ACTIONS = {
    "proposal": {"approve", "reject", "defer", "request-revision"},
    "topic": {"promote", "prioritize", "defer"},
    "objective": {"attach", "retire", "defer"},
    "strategy": {"align", "reprioritize", "redirect", "review-drift"},
}
VALID_RUNTIME_ACTIONS = {
    "dispatch": {"require-review", "retry", "halt", "safe-to-continue"},
    "evidence": {"confirm", "dispute", "incomplete", "needs-instrumentation"},
    "primitive": {"confirm-failure", "needs-guardrail", "stable", "defer"},
    "autonomy": {
        "accept-delta",
        "dispute-delta",
        "confirm-unstable",
        "codify-accepted",
        "codify-deferred",
        "promote-task",
    },
}


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
    _log_operator_action(
        thread_id,
        f"thread:{action}",
        reason=reason,
        target_type="thread",
        label=fm.get("title") or thread_id,
        reference=thread_id,
        resulting_state="applied",
    )
    return jsonify({"ok": True, "thread_id": thread_id, "old_status": old_status, "new_status": action}), 200


@actions_bp.route('/api/tasks/<task_id>/action', methods=['POST'])
def task_action(task_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip() or None
    value = data.get("value")

    if action not in VALID_TASK_ACTIONS:
        return jsonify({"error": f"Invalid action. Must be one of: {', '.join(sorted(VALID_TASK_ACTIONS))}"}), 400

    existing = _find_pending_task_intent(task_id, action, reason=reason, value=value)
    if existing:
        return jsonify({
            "ok": True,
            "queued": True,
            "duplicate": True,
            "task_id": task_id,
            "chat_id": existing.get("id"),
        }), 200

    from dashboard_db import add_chat

    intent_text = _build_task_intent_text(task_id, action, reason=reason, value=None if value is None else str(value))
    chat_id = add_chat("user", intent_text)
    _log_operator_action(
        task_id,
        f"task-intent:{action}",
        reason=reason,
        value=value,
        target_type="task",
        label=task_id,
        resulting_state="queued",
        apply="next-dispatch",
    )
    return jsonify({
        "ok": True,
        "queued": True,
        "duplicate": False,
        "task_id": task_id,
        "chat_id": chat_id,
        "dispatch_mode": "next-dispatch",
    }), 200


def _build_steering_intent_text(target_type, target_id, action, label=None, reference=None, reason=None, value=None):
    lines = [
        "[steering-intent]",
        f"target_type: {target_type}",
        f"target_id: {target_id}",
        f"action: {action}",
        "apply: next-dispatch",
        "resulting_state: queued",
    ]
    if label:
        lines.append(f"label: {label}")
    if reference:
        lines.append(f"reference: {reference}")
    if reason:
        lines.append(f"reason: {reason}")
    if value is not None:
        lines.append(f"value: {value}")
    lines.append("note: queue this operator epistemic steering decision for the next dispatch; do not apply it immediately")
    return "\n".join(lines)


def _parse_steering_intent_text(text):
    if not text or not str(text).startswith("[steering-intent]"):
        return None
    data = {}
    for line in str(text).splitlines()[1:]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if key:
            data[key] = value
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    action = data.get("action")
    if not target_type or not target_id or not action:
        return None
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": data.get("label"),
        "reference": data.get("reference"),
        "reason": data.get("reason"),
        "value": data.get("value"),
        "apply": data.get("apply"),
        "resulting_state": data.get("resulting_state"),
        "note": data.get("note"),
    }


def _find_pending_steering_intent(target_type, target_id, action, reason=None, value=None):
    from dashboard_db import get_chats

    for message in get_chats(unprocessed_only=True, limit=200):
        if message.get("author") != "user":
            continue
        parsed = _parse_steering_intent_text(message.get("text", ""))
        if not parsed:
            continue
        if parsed["target_type"] != target_type or parsed["target_id"] != target_id or parsed["action"] != action:
            continue
        if (parsed.get("reason") or None) != reason:
            continue
        if (parsed.get("value") or None) != (None if value is None else str(value)):
            continue
        return message
    return None


@actions_bp.route('/api/steering/<target_type>/<path:target_id>/action', methods=['POST'])
def steering_action(target_type, target_id):
    target_type = str(target_type or "").strip().lower()
    if target_type not in VALID_STEERING_ACTIONS:
        return jsonify({"error": f"Invalid target_type. Must be one of: {', '.join(sorted(VALID_STEERING_ACTIONS))}"}), 400

    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip() or None
    value = data.get("value")
    label = str(data.get("label") or "").strip() or target_id
    reference = str(data.get("reference") or "").strip() or None

    if action not in VALID_STEERING_ACTIONS[target_type]:
        valid = ", ".join(sorted(VALID_STEERING_ACTIONS[target_type]))
        return jsonify({"error": f"Invalid action for {target_type}. Must be one of: {valid}"}), 400
    if not reason:
        return jsonify({"error": "A rationale is required for epistemic steering actions."}), 400

    existing = _find_pending_steering_intent(target_type, target_id, action, reason=reason, value=value)
    if existing:
        return jsonify({
            "ok": True,
            "queued": True,
            "duplicate": True,
            "target_type": target_type,
            "target_id": target_id,
            "chat_id": existing.get("id"),
        }), 200

    from dashboard_db import add_chat

    intent_text = _build_steering_intent_text(
        target_type,
        target_id,
        action,
        label=label,
        reference=reference,
        reason=reason,
        value=None if value is None else str(value),
    )
    chat_id = add_chat("user", intent_text)
    _log_operator_action(
        target_id,
        f"steering:{action}",
        reason=reason,
        value=value,
        target_type=target_type,
        label=label,
        reference=reference,
        resulting_state="queued",
        apply="next-dispatch",
    )
    return jsonify({
        "ok": True,
        "queued": True,
        "duplicate": False,
        "target_type": target_type,
        "target_id": target_id,
        "chat_id": chat_id,
        "dispatch_mode": "next-dispatch",
        "resulting_state": "queued",
    }), 200


def _build_runtime_intent_text(target_type, target_id, action, label=None, reference=None, reason=None, value=None):
    lines = [
        "[runtime-intent]",
        f"target_type: {target_type}",
        f"target_id: {target_id}",
        f"action: {action}",
        "apply: next-dispatch",
        "resulting_state: queued",
    ]
    if label:
        lines.append(f"label: {label}")
    if reference:
        lines.append(f"reference: {reference}")
    if reason:
        lines.append(f"reason: {reason}")
    if value is not None:
        lines.append(f"value: {value}")
    lines.append("note: queue this operator runtime/autonomy intervention for the next dispatch; do not apply it immediately")
    return "\n".join(lines)


def _parse_runtime_intent_text(text):
    if not text or not str(text).startswith("[runtime-intent]"):
        return None
    data = {}
    for line in str(text).splitlines()[1:]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if key:
            data[key] = value
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    action = data.get("action")
    if not target_type or not target_id or not action:
        return None
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": data.get("label"),
        "reference": data.get("reference"),
        "reason": data.get("reason"),
        "value": data.get("value"),
        "apply": data.get("apply"),
        "resulting_state": data.get("resulting_state"),
        "note": data.get("note"),
    }


def _find_pending_runtime_intent(target_type, target_id, action, reason=None, value=None):
    from dashboard_db import get_chats

    for message in get_chats(unprocessed_only=True, limit=200):
        if message.get("author") != "user":
            continue
        parsed = _parse_runtime_intent_text(message.get("text", ""))
        if not parsed:
            continue
        if parsed["target_type"] != target_type or parsed["target_id"] != target_id or parsed["action"] != action:
            continue
        if (parsed.get("reason") or None) != reason:
            continue
        if (parsed.get("value") or None) != (None if value is None else str(value)):
            continue
        return message
    return None


@actions_bp.route('/api/runtime/<target_type>/<path:target_id>/action', methods=['POST'])
def runtime_action(target_type, target_id):
    target_type = str(target_type or "").strip().lower()
    if target_type not in VALID_RUNTIME_ACTIONS:
        return jsonify({"error": f"Invalid target_type. Must be one of: {', '.join(sorted(VALID_RUNTIME_ACTIONS))}"}), 400

    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip() or None
    value = data.get("value")
    label = str(data.get("label") or "").strip() or target_id
    reference = str(data.get("reference") or "").strip() or None

    if action not in VALID_RUNTIME_ACTIONS[target_type]:
        valid = ", ".join(sorted(VALID_RUNTIME_ACTIONS[target_type]))
        return jsonify({"error": f"Invalid action for {target_type}. Must be one of: {valid}"}), 400
    if not reason:
        return jsonify({"error": "A rationale is required for runtime/autonomy interventions."}), 400

    existing = _find_pending_runtime_intent(target_type, target_id, action, reason=reason, value=value)
    if existing:
        return jsonify({
            "ok": True,
            "queued": True,
            "duplicate": True,
            "target_type": target_type,
            "target_id": target_id,
            "chat_id": existing.get("id"),
        }), 200

    from dashboard_db import add_chat

    intent_text = _build_runtime_intent_text(
        target_type,
        target_id,
        action,
        label=label,
        reference=reference,
        reason=reason,
        value=None if value is None else str(value),
    )
    chat_id = add_chat("user", intent_text)
    _log_operator_action(
        target_id,
        f"runtime:{action}",
        reason=reason,
        value=value,
        target_type=target_type,
        label=label,
        reference=reference,
        resulting_state="queued",
        apply="next-dispatch",
    )
    return jsonify({
        "ok": True,
        "queued": True,
        "duplicate": False,
        "target_type": target_type,
        "target_id": target_id,
        "chat_id": chat_id,
        "dispatch_mode": "next-dispatch",
        "resulting_state": "queued",
    }), 200
