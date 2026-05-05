from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .util import now_iso, truncate


def _normalize_message(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    try:
        message_id = int(raw.get("id") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "id": message_id,
        "author": str(raw.get("author") or "user").strip() or "user",
        "text": text,
        "ts": str(raw.get("ts") or now_iso()),
        "processed": bool(raw.get("processed")),
        "pinned": bool(raw.get("pinned")),
    }


def _load_messages(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    messages: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        normalized = _normalize_message(parsed)
        if normalized:
            messages.append(normalized)
    messages.sort(key=lambda item: (str(item.get("ts") or ""), int(item.get("id") or 0)))
    return messages


def _rewrite_messages(path: Path, messages: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for message in messages:
            handle.write(json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n")


def message_count(config: RuntimeConfig) -> int:
    return len(_load_messages(config.async_chat_path))


def list_messages(
    config: RuntimeConfig,
    *,
    unprocessed_only: bool = False,
    pinned_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    messages = _load_messages(config.async_chat_path)
    if unprocessed_only:
        messages = [item for item in messages if not item.get("processed")]
    if pinned_only:
        messages = [item for item in messages if item.get("pinned")]
    if limit > 0:
        messages = messages[-limit:]
    return messages


def add_message(
    config: RuntimeConfig,
    *,
    author: str,
    text: str,
    processed: bool = False,
    pinned: bool = False,
) -> dict[str, Any]:
    message_text = str(text or "").strip()
    if not message_text:
        raise ValueError("chat text is required")
    messages = _load_messages(config.async_chat_path)
    next_id = max((int(item.get("id") or 0) for item in messages), default=0) + 1
    row = {
        "id": next_id,
        "author": str(author or "user").strip() or "user",
        "text": message_text,
        "ts": now_iso(),
        "processed": bool(processed),
        "pinned": bool(pinned),
    }
    config.async_chat_path.parent.mkdir(parents=True, exist_ok=True)
    with config.async_chat_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def _update_message(config: RuntimeConfig, message_id: int, **changes: Any) -> dict[str, Any] | None:
    messages = _load_messages(config.async_chat_path)
    updated: dict[str, Any] | None = None
    for item in messages:
        if int(item.get("id") or 0) != int(message_id):
            continue
        item.update(changes)
        updated = item
        break
    if updated is None:
        return None
    _rewrite_messages(config.async_chat_path, messages)
    return updated


def mark_processed(config: RuntimeConfig, message_id: int) -> dict[str, Any] | None:
    return _update_message(config, int(message_id), processed=True)


def pin_message(config: RuntimeConfig, message_id: int) -> dict[str, Any] | None:
    return _update_message(config, int(message_id), pinned=True)


def unpin_message(config: RuntimeConfig, message_id: int) -> dict[str, Any] | None:
    return _update_message(config, int(message_id), pinned=False)


def inbox_snapshot(config: RuntimeConfig, *, limit: int = 200) -> dict[str, Any]:
    pinned = list_messages(config, pinned_only=True, limit=min(limit, 80))
    unprocessed = list_messages(config, unprocessed_only=True, limit=limit)
    combined: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in [*pinned, *unprocessed]:
        message_id = int(item.get("id") or 0)
        if message_id in seen:
            continue
        seen.add(message_id)
        combined.append(item)
    combined.sort(key=lambda item: (str(item.get("ts") or ""), int(item.get("id") or 0)))
    return {"messages": combined[-limit:], "unprocessed": unprocessed, "pinned": pinned}


def snapshot_excerpt(messages: list[dict[str, Any]], *, limit: int = 6) -> str:
    lines: list[str] = []
    for item in messages[-limit:]:
        flags = []
        if item.get("pinned"):
            flags.append("pinned")
        if not item.get("processed"):
            flags.append("pending")
        label = f"[{', '.join(flags)}] " if flags else ""
        lines.append(f"- {label}{item.get('author')}: {truncate(str(item.get('text') or ''), 180)}")
    return "\n".join(lines)


def acknowledge_messages(
    config: RuntimeConfig,
    *,
    messages: list[dict[str, Any]],
    cycle_id: str,
    kind: str,
    request: str,
) -> dict[str, Any]:
    pending_ids = [int(item.get("id") or 0) for item in messages if int(item.get("id") or 0) > 0 and not bool(item.get("processed"))]
    processed: list[int] = []
    for message_id in pending_ids:
        if mark_processed(config, message_id):
            processed.append(message_id)
    if not processed:
        return {"processed_ids": [], "reply_id": None}
    summary = truncate(request.strip() or f"{kind} beat", 180)
    reply = add_message(
        config,
        author="edge",
        text=f"Cycle {cycle_id} completed after checking async chat guidance for {summary}.",
        processed=True,
    )
    return {"processed_ids": processed, "reply_id": int(reply.get("id") or 0)}
