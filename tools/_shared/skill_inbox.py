"""Structured async inbox for skills.

Converts the blog chat's async channel into a deterministic contract that
skills can inspect without scraping raw `/api/chat` output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
EDGE_REPO_DIR = SCRIPT_DIR.parent.parent
SEARCH_DIR = EDGE_REPO_DIR / "search"
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "search"))


def _load_dashboard_chat_api():
    if os.environ.get("EDGE_SKILL_INBOX_FORCE_SUBPROCESS") == "1":
        return None, None, None
    try:
        from dashboard_db import add_chat, get_chats, mark_chat_processed  # type: ignore
    except Exception:
        return None, None, None
    return get_chats, add_chat, mark_chat_processed


def _search_python() -> str | None:
    override = str(os.environ.get("EDGE_SEARCH_PYTHON") or "").strip()
    if override:
        return override
    candidate = SEARCH_DIR / ".venv" / "bin" / "python3"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _dashboard_chat_via_subprocess(payload: dict[str, Any]) -> dict[str, Any] | None:
    search_python = _search_python()
    if not search_python:
        return None
    helper = """
import json
import sys
from pathlib import Path

search_dir = Path(sys.argv[1])
payload = json.loads(sys.argv[2])
sys.path.insert(0, str(search_dir))

from dashboard_db import add_chat, get_chats, mark_chat_processed

action = str(payload.get("action") or "").strip()
if action == "snapshot":
    limit = int(payload.get("limit") or 200)
    print(json.dumps({
        "unprocessed": get_chats(unprocessed_only=True, limit=limit),
        "pinned": get_chats(pinned_only=True, limit=min(limit, 50)),
    }))
elif action == "consume":
    processed = []
    for chat_id in payload.get("chat_ids") or []:
        mark_chat_processed(int(chat_id))
        processed.append(int(chat_id))
    print(json.dumps({"processed_ids": processed}))
elif action == "respond_and_consume":
    author = str(payload.get("author") or "system").strip() or "system"
    text = str(payload.get("text") or "").strip()
    if not text:
        raise SystemExit("response text is required")
    reply_id = add_chat(author, text)
    reply_processed = False
    try:
        mark_chat_processed(int(reply_id))
        reply_processed = True
    except Exception:
        pass
    processed = []
    failed = []
    for chat_id in payload.get("chat_ids") or []:
        try:
            mark_chat_processed(int(chat_id))
            processed.append(int(chat_id))
        except Exception:
            failed.append(int(chat_id))
    print(json.dumps({
        "reply_id": reply_id,
        "reply_processed": reply_processed,
        "processed_ids": processed,
        "failed_ids": failed,
    }))
else:
    raise SystemExit(f"unsupported action: {action}")
""".strip()
    env = os.environ.copy()
    env["EDGE_REPO_DIR"] = str(EDGE_REPO_DIR)
    result = subprocess.run(
        [search_python, "-c", helper, str(SEARCH_DIR), json.dumps(payload, ensure_ascii=False)],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, *, limit: int = 180) -> str:
    blob = " ".join(str(text or "").split())
    if len(blob) <= limit:
        return blob
    return blob[: limit - 1] + "…"


def _captured_message_ids(snapshot: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for item in snapshot.get("message_ids") or []:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


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
    get_chats, _, _ = _load_dashboard_chat_api()
    if get_chats is None:
        payload = _dashboard_chat_via_subprocess({"action": "snapshot", "limit": limit}) or {}
        unprocessed = payload.get("unprocessed") or []
        pinned = payload.get("pinned") or []
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
    ids = _captured_message_ids(snapshot)
    processed_ids: list[int] = []
    _, _, mark_chat_processed = _load_dashboard_chat_api()
    if mark_chat_processed is None:
        payload = _dashboard_chat_via_subprocess({"action": "consume", "chat_ids": ids}) or {}
        processed_ids = [int(item) for item in payload.get("processed_ids") or [] if str(item).strip()]
    else:
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


def build_postflight_response_text(state: dict[str, Any], snapshot: dict[str, Any]) -> str:
    """Build a concise dashboard response for captured async operator input."""
    request = state.get("request", {}) or {}
    cycle_id = state.get("cycle_id") or "unknown-cycle"
    skill = request.get("skill") or snapshot.get("skill") or "unknown-skill"
    direct = len(snapshot.get("direct_messages") or [])
    task = len(snapshot.get("task_intents") or [])
    steering = len(snapshot.get("steering_intents") or [])
    runtime = len(snapshot.get("runtime_intents") or [])
    captured_total = len(_captured_message_ids(snapshot))

    lines = [
        f"[postflight] Processed async dashboard input for cycle {cycle_id}.",
        f"Skill: {skill}. Captured: {captured_total} message(s) "
        f"(direct={direct}, task={task}, steering={steering}, runtime={runtime}).",
        "The substantive result belongs to the generated artifact/report; late messages remain queued for the next cycle.",
    ]

    previews: list[str] = []
    for bucket in ("direct_messages", "task_intents", "steering_intents", "runtime_intents"):
        for item in snapshot.get(bucket) or []:
            preview = str(item.get("preview") or item.get("text") or "").strip()
            if preview:
                previews.append(_preview(preview, limit=120))
            if len(previews) >= 3:
                break
        if len(previews) >= 3:
            break
    if previews:
        lines.append("Seen: " + " | ".join(previews))
    return "\n".join(lines)


def acknowledge_captured_inbox(state: dict[str, Any], *, author: str = "system") -> dict[str, Any]:
    """Post a final dashboard acknowledgement, then consume captured user chat ids.

    The captured dispatch snapshot is authoritative. Live chat is intentionally
    not scanned here, so messages that arrive after dispatch remain pending for
    the next cycle.
    """
    request = state.setdefault("request", {})
    snapshot = request.get("async_inbox") or {}
    ids = _captured_message_ids(snapshot)

    if not ids:
        return {
            "ok": True,
            "detail": "no captured async inbox messages",
            "reply_posted": False,
            "processed_ids": [],
            "processed_count": 0,
            "captured_total": 0,
        }

    if int(snapshot.get("processed_count") or 0) >= len(ids) and snapshot.get("response_chat_id"):
        return {
            "ok": True,
            "detail": "captured async inbox already acknowledged",
            "reply_posted": True,
            "reply_id": snapshot.get("response_chat_id"),
            "reply_processed": bool(snapshot.get("response_processed", False)),
            "processed_ids": snapshot.get("processed_message_ids") or [],
            "processed_count": int(snapshot.get("processed_count") or 0),
            "captured_total": len(ids),
        }

    text = build_postflight_response_text(state, snapshot)
    processed_ids: list[int] = []
    failed_ids: list[int] = []
    reply_id: int | None = None
    reply_processed = False
    _, add_chat, mark_chat_processed = _load_dashboard_chat_api()

    try:
        if add_chat is None or mark_chat_processed is None:
            payload = _dashboard_chat_via_subprocess({
                "action": "respond_and_consume",
                "author": author,
                "text": text,
                "chat_ids": ids,
            })
            if not payload:
                raise RuntimeError("dashboard chat API unavailable")
            reply_id = int(payload.get("reply_id"))
            reply_processed = bool(payload.get("reply_processed", False))
            processed_ids = [
                int(item)
                for item in payload.get("processed_ids") or []
                if str(item).strip()
            ]
            failed_ids = [
                int(item)
                for item in payload.get("failed_ids") or []
                if str(item).strip()
            ]
        else:
            reply_id = int(add_chat(author, text))
            try:
                mark_chat_processed(reply_id)
                reply_processed = True
            except Exception:
                pass
            for chat_id in ids:
                try:
                    mark_chat_processed(chat_id)
                    processed_ids.append(chat_id)
                except Exception:
                    failed_ids.append(chat_id)
    except Exception as exc:
        snapshot["response_error"] = str(exc)
        request["async_inbox"] = snapshot
        return {
            "ok": False,
            "detail": f"async inbox response failed: {exc}",
            "reply_posted": reply_id is not None,
            "reply_id": reply_id,
            "reply_processed": reply_processed,
            "processed_ids": processed_ids,
            "failed_ids": failed_ids,
            "processed_count": len(processed_ids),
            "captured_total": len(ids),
        }

    now = now_iso()
    snapshot["response_posted_at"] = now
    snapshot["response_chat_id"] = reply_id
    snapshot["response_author"] = author
    snapshot["response_processed"] = reply_processed
    snapshot["response_text_preview"] = _preview(text)
    snapshot["processed_at"] = now
    snapshot["processed_message_ids"] = processed_ids
    snapshot["processed_count"] = len(processed_ids)
    request["async_inbox"] = snapshot

    ok = reply_processed and len(processed_ids) == len(ids)
    return {
        "ok": ok,
        "detail": f"reply_id={reply_id} reply_processed={reply_processed} processed={len(processed_ids)}/{len(ids)}",
        "reply_posted": True,
        "reply_id": reply_id,
        "reply_processed": reply_processed,
        "processed_ids": processed_ids,
        "failed_ids": failed_ids,
        "processed_count": len(processed_ids),
        "captured_total": len(ids),
    }
