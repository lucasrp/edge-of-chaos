from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .llm_client import LLMClient
from .util import now_iso, truncate


def refresh_chat_digest(config: RuntimeConfig) -> dict[str, Any]:
    settings = ((config.agent.get("context") or {}).get("claude_sessions") or {})
    digest_settings = settings.get("digest") if isinstance(settings.get("digest"), dict) else {}
    if settings.get("enabled", True) is False or digest_settings.get("enabled", True) is False:
        return {"status": "skipped", "reason": "claude_sessions_disabled"}

    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return {"status": "skipped", "reason": "claude_projects_missing", "path": str(base)}

    max_files = int(digest_settings.get("max_delta_files") or settings.get("max_files") or 8)
    max_delta_chars = int(digest_settings.get("max_delta_chars") or 28000)
    files = _recent_session_files(config, base, max_files)
    cursor = _load_cursor(config.chat_digest_cursor_path)
    changed = [path for path in files if cursor.get(str(path)) != _signature(path)]

    if not changed and config.chat_digest_path.exists():
        return {"status": "unchanged", "path": str(config.chat_digest_path), "files_seen": len(files)}

    previous = _read(config.chat_digest_path, limit=12000)
    deltas = []
    for path in changed:
        rendered = _render_session_delta(path)
        if rendered:
            deltas.append(rendered)
        if sum(len(item) for item in deltas) >= max_delta_chars:
            break

    if not deltas and config.chat_digest_path.exists():
        _write_cursor(config.chat_digest_cursor_path, files)
        return {"status": "unchanged", "path": str(config.chat_digest_path), "files_seen": len(files)}

    client = LLMClient(role="digest")
    prompt = json.dumps(
        {
            "previous_digest": previous,
            "new_chat_deltas": deltas,
            "required_shape": [
                "Current operator direction",
                "Domain/project vocabulary",
                "Open mentor threads",
                "Decisions and constraints",
                "Mistakes to avoid",
                "Recent delta",
                "What the next beat must remember",
            ],
        },
        ensure_ascii=False,
    )[: max_delta_chars + 14000]
    text = client.complete_text(
        system=(
            "You maintain a compact genotypic chat digest for edge-of-chaos, a private Feynman mentor. "
            "Read the previous digest and only the new chat deltas. Produce a fresh Markdown digest. "
            "Preserve durable operator direction, domain vocabulary, decisions, open questions, mistakes to avoid, "
            "and the current project delta. Ignore runtime prompts, reviewer instructions, tool listings, queue metadata, "
            "and boilerplate. Be concise but specific enough for the next beat to continue the real mentor/mentee relation."
        ),
        prompt=prompt,
    )
    if not text:
        text = _local_digest(previous, deltas)
    if not text.lstrip().startswith("#"):
        text = "# Chat Digest\n\n" + text.strip()
    config.chat_digest_path.parent.mkdir(parents=True, exist_ok=True)
    config.chat_digest_path.write_text(text.rstrip() + "\n", encoding="utf-8")
    _write_cursor(config.chat_digest_cursor_path, files)
    result = {
        "status": "updated",
        "path": str(config.chat_digest_path),
        "files_seen": len(files),
        "files_changed": len(changed),
        "llm_provider": client.last_provider,
    }
    if client.model:
        result["model"] = client.model
    if client.last_error:
        result["llm_error"] = client.last_error
    return result


def _recent_session_files(config: RuntimeConfig, base: Path, max_files: int) -> list[Path]:
    workspace_slugs = []
    for item in config.agent.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or ".")
        path = Path(raw_path)
        if not path.is_absolute():
            path = config.root / path
        workspace_slugs.append("-" + str(path.resolve()).strip("/").replace("/", "-"))
    try:
        files = [path for path in base.rglob("*.jsonl") if path.is_file()]
    except OSError:
        return []
    files.sort(
        key=lambda path: (
            any(slug and slug in str(path.parent) for slug in workspace_slugs),
            path.stat().st_mtime,
        ),
        reverse=True,
    )
    return files[:max_files]


def _render_session_delta(path: Path) -> str:
    lines = _read(path, limit=90000).splitlines()[-500:]
    rendered = [f"## {path.name}"]
    for raw in lines:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        role = _role(event)
        if not role:
            continue
        text = _message_text(event)
        if not text or _looks_like_runtime_prompt(text):
            continue
        timestamp = event.get("timestamp") or ""
        cwd = event.get("cwd") or ""
        branch = event.get("gitBranch") or ""
        context = " ".join(str(item) for item in [timestamp, cwd, branch] if item)
        rendered.append(f"{role.upper()} {context}\n{truncate(text, 1800)}")
    if len(rendered) == 1:
        return ""
    return truncate("\n\n".join(rendered), 7000)


def _role(event: dict[str, Any]) -> str:
    if event.get("type") in {"user", "assistant"}:
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        return str(message.get("role") or event.get("type") or "")
    return ""


def _message_text(event: dict[str, Any]) -> str:
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _looks_like_runtime_prompt(text: str) -> bool:
    head = " ".join(text.lower().split())[:900]
    markers = [
        "you are edge-of-chaos v2",
        "you are an adversarial reviewer",
        "you are the continuity/context/search reviewer",
        "you are a feynman reviewer",
        "classify this generated mentor report",
        "return only one valid json object",
        "reply with ok only",
        "deferred_tools_delta",
        "skill_listing",
    ]
    return any(marker in head for marker in markers)


def _load_cursor(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    processed = data.get("processed") if isinstance(data, dict) else {}
    return processed if isinstance(processed, dict) else {}


def _write_cursor(path: Path, files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": now_iso(),
        "processed": {str(file): _signature(file) for file in files},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def _read(path: Path, *, limit: int) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _local_digest(previous: str, deltas: list[str]) -> str:
    return (
        "# Chat Digest\n\n"
        "## Current Operator Direction\n\n"
        "Local fallback could not call an LLM digest. Preserve the previous digest and review the new deltas manually.\n\n"
        "## Previous Digest\n\n"
        f"{truncate(previous or 'No previous digest.', 4000)}\n\n"
        "## Recent Delta\n\n"
        f"{truncate(chr(10).join(deltas) or 'No readable chat delta.', 5000)}\n"
    )
