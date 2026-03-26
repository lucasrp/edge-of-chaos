"""Action endpoints for heartbeat trigger and thread actions."""

import json
from datetime import datetime, timezone

import yaml
from flask import Blueprint, jsonify, request

from blog.services import LOGS_DIR, STATE_DIR, THREADS_DIR

actions_bp = Blueprint('actions', __name__)

OPERATOR_LOG = LOGS_DIR / "operator-actions.jsonl"
HEARTBEAT_TRIGGER_FILE = STATE_DIR / "heartbeat-trigger.json"
HEARTBEAT_RATE_LIMIT_SECONDS = 600


def _log_operator_action(target_id, action, reason=None, value=None):
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
