"""Structured async inbox for skills.

Converts the blog chat's async channel into a deterministic contract that
skills can inspect without scraping raw `/api/chat` output.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "search"))


def _load_dashboard_chat_api():
    try:
        from dashboard_db import get_chats, mark_chat_processed  # type: ignore
    except Exception:
        return None, None
    return get_chats, mark_chat_processed


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, *, limit: int = 180) -> str:
    blob = " ".join(str(text or "").split())
    if len(blob) <= limit:
        return blob
    return blob[: limit - 1] + "…"


def _parse_kv_block(prefix: str, text: str) -> dict[str, str] | None:
    raw = str(text or "")
    if not raw.startswith(prefix):
        return None
    payload: dict[str, str] = {}
    for line in raw.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            payload[key] = value
    return payload


def parse_task_intent(text: str) -> dict[str, Any] | None:
    payload = _parse_kv_block("[task-intent]", text)
    if not payload:
        return None
    task_id = payload.get("task")
    action = payload.get("action")
    if not task_id or not action:
        return None
    return {
        "target_type": "task",
        "target_id": task_id,
        "action": action,
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "apply": payload.get("apply"),
        "note": payload.get("note"),
    }


def parse_steering_intent(text: str) -> dict[str, Any] | None:
    payload = _parse_kv_block("[steering-intent]", text)
    if not payload:
        return None
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    action = payload.get("action")
    if not target_type or not target_id or not action:
        return None
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": payload.get("label") or target_id,
        "reference": payload.get("reference"),
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "apply": payload.get("apply"),
        "resulting_state": payload.get("resulting_state"),
        "note": payload.get("note"),
    }


def parse_runtime_intent(text: str) -> dict[str, Any] | None:
    payload = _parse_kv_block("[runtime-intent]", text)
    if not payload:
        return None
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    action = payload.get("action")
    if not target_type or not target_id or not action:
        return None
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": payload.get("label") or target_id,
        "reference": payload.get("reference"),
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "apply": payload.get("apply"),
        "resulting_state": payload.get("resulting_state"),
        "note": payload.get("note"),
    }


def classify_message(message: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    text = str(message.get("text") or "")
    base = {
        "chat_id": message.get("id"),
        "author": message.get("author"),
        "ts": message.get("ts"),
        "text": text,
        "preview": _preview(text),
        "priority": "operator",
    }

    parsed = parse_task_intent(text)
    if parsed:
        return "task_intents", {**base, **parsed}

    parsed = parse_steering_intent(text)
    if parsed:
        return "steering_intents", {**base, **parsed}

    parsed = parse_runtime_intent(text)
    if parsed:
        return "runtime_intents", {**base, **parsed}

    return "direct_messages", {
        **base,
        "kind": "direct_message",
    }


def build_async_inbox_snapshot(*, skill: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Return the structured async inbox contract for the next skill."""
    get_chats, _ = _load_dashboard_chat_api()
    if get_chats is None:
        unprocessed = []
        pinned = []
    else:
        try:
            unprocessed = get_chats(unprocessed_only=True, limit=limit)
        except Exception:
            unprocessed = []
        try:
            pinned = get_chats(pinned_only=True, limit=min(limit, 50))
        except Exception:
            pinned = []

    snapshot: dict[str, Any] = {
        "captured_at": now_iso(),
        "skill": skill,
        "source": "blog-chat",
        "priority": "normal",
        "priority_reason": None,
        "dispatch_guidance": "continue normal routing",
        "unprocessed_total": 0,
        "pinned_total": 0,
        "message_ids": [],
        "direct_messages": [],
        "task_intents": [],
        "steering_intents": [],
        "runtime_intents": [],
        "pinned_messages": [],
    }

    for message in unprocessed:
        if message.get("author") != "user":
            continue
        bucket, item = classify_message(message)
        snapshot[bucket].append(item)
        if message.get("id") is not None:
            snapshot["message_ids"].append(int(message["id"]))

    seen_pins: set[int] = set()
    for message in pinned:
        if message.get("author") != "user":
            continue
        chat_id = message.get("id")
        if chat_id is None:
            continue
        chat_id = int(chat_id)
        if chat_id in seen_pins:
            continue
        seen_pins.add(chat_id)
        snapshot["pinned_messages"].append({
            "chat_id": chat_id,
            "author": message.get("author"),
            "ts": message.get("ts"),
            "text": str(message.get("text") or ""),
            "preview": _preview(message.get("text") or ""),
        })

    snapshot["unprocessed_total"] = len(snapshot["message_ids"])
    snapshot["pinned_total"] = len(snapshot["pinned_messages"])
    if snapshot["unprocessed_total"] > 0:
        snapshot["priority"] = "high"
        snapshot["priority_reason"] = "user_async_input"
        snapshot["dispatch_guidance"] = "user interaction is priority; address async inbox before exploration or rotation"
    elif snapshot["pinned_total"] > 0:
        snapshot["priority"] = "high"
        snapshot["priority_reason"] = "pinned_user_direction"
        snapshot["dispatch_guidance"] = "standing user direction is active; honor pinned guidance before generic exploration"
    return snapshot


def attach_snapshot_to_dispatch(state: dict[str, Any], *, skill: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Attach an async inbox snapshot to a dispatch state dict."""
    request = state.setdefault("request", {})
    state_block = state.setdefault("state", {})
    snapshot = build_async_inbox_snapshot(skill=skill or request.get("skill"), limit=limit)
    request["async_inbox"] = snapshot
    state_block["inbox_captured_at"] = snapshot["captured_at"]
    return snapshot


def get_dispatch_snapshot(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active cycle's captured async inbox, if present."""
    state_block = state.get("state", {}) or {}
    if not state_block.get("active"):
        return None
    request = state.get("request", {}) or {}
    snapshot = request.get("async_inbox")
    if isinstance(snapshot, dict) and snapshot:
        return snapshot
    return None


def consume_captured_inbox(state: dict[str, Any]) -> dict[str, Any]:
    """Mark captured async inbox messages as processed after a successful skill run."""
    request = state.setdefault("request", {})
    snapshot = request.get("async_inbox") or {}
    ids = [int(item) for item in snapshot.get("message_ids", []) if str(item).strip()]
    processed_ids: list[int] = []
    _, mark_chat_processed = _load_dashboard_chat_api()
    if mark_chat_processed is None:
        return {
            "processed_ids": processed_ids,
            "processed_count": 0,
            "captured_total": len(ids),
        }
    for chat_id in ids:
        try:
            mark_chat_processed(chat_id)
            processed_ids.append(chat_id)
        except Exception:
            continue

    if snapshot:
        snapshot["processed_at"] = now_iso()
        snapshot["processed_message_ids"] = processed_ids
        snapshot["processed_count"] = len(processed_ids)
        request["async_inbox"] = snapshot

    return {
        "processed_ids": processed_ids,
        "processed_count": len(processed_ids),
        "captured_total": len(ids),
    }
