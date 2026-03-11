"""Parse Claude Code JSONL transcripts into structured Session objects."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolCall:
    """A tool invocation extracted from an assistant message."""

    name: str
    args_summary: str = ""  # brief summary of arguments


@dataclass
class Message:
    """A single message (human or assistant) from a transcript."""

    role: str  # "human" or "assistant" (normalized to "human"/"assistant")
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    files_mentioned: list[str] = field(default_factory=list)
    commands_mentioned: list[str] = field(default_factory=list)


@dataclass
class Session:
    """A parsed transcript session."""

    source_path: Path
    project_path: str = ""
    messages: list[Message] = field(default_factory=list)
    parse_errors: int = 0

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def human_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "human"]

    @property
    def assistant_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "assistant"]


# Patterns for extracting file paths and shell commands from text
_FILE_PATTERN = re.compile(
    r'(?:^|[\s`"\'])(/(?:[\w./-]+)+\.[\w]+)', re.MULTILINE
)
_COMMAND_PATTERN = re.compile(
    r'(?:^|\s)(?:(?:sudo|npm|pip|git|cd|ls|cat|mkdir|rm|cp|mv|python|node|cargo|go|make|docker|kubectl)\s+\S+)',
    re.MULTILINE,
)


def _extract_text_from_content(content) -> str:
    """Extract plain text from a message's content field.

    Content can be:
    - A string
    - A list of content blocks (each with "type" and "text"/"name" fields)
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts)

    return ""


def _extract_tool_calls(content) -> list[ToolCall]:
    """Extract tool call info from content blocks."""
    calls = []

    if not isinstance(content, list):
        return calls

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "unknown")
            # Summarize args briefly
            tool_input = block.get("input", {})
            args_summary = ""
            if isinstance(tool_input, dict):
                # Take first key-value or command for common tools
                if "command" in tool_input:
                    cmd = str(tool_input["command"])
                    args_summary = cmd[:120]
                elif "file_path" in tool_input:
                    args_summary = str(tool_input["file_path"])
                elif "pattern" in tool_input:
                    args_summary = str(tool_input["pattern"])
                elif tool_input:
                    first_key = next(iter(tool_input))
                    val = str(tool_input[first_key])
                    args_summary = f"{first_key}={val[:80]}"

            calls.append(ToolCall(name=name, args_summary=args_summary))

    return calls


def _extract_files(text: str) -> list[str]:
    """Extract file paths mentioned in text."""
    if not text:
        return []
    matches = _FILE_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _extract_commands(text: str) -> list[str]:
    """Extract shell commands mentioned in text."""
    if not text:
        return []
    matches = _COMMAND_PATTERN.findall(text)
    return [m.strip() for m in matches]


def _derive_project_path(source_path: Path) -> str:
    """Derive the project identifier from transcript file path."""
    parts = source_path.parts
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            return parts[i + 1]
    return "unknown"


def parse_transcript(path: Path, max_messages: int = 0) -> Session:
    """Parse a single .jsonl transcript file into a Session.

    Args:
        path: Path to the .jsonl file.
        max_messages: Max messages to parse (0 = unlimited).

    Returns:
        Session object with parsed messages.
    """
    session = Session(
        source_path=path,
        project_path=_derive_project_path(path),
    )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"Warning: could not read {path}: {e}", file=sys.stderr)
        return session

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            session.parse_errors += 1
            continue

        if not isinstance(data, dict):
            session.parse_errors += 1
            continue

        msg_type = data.get("type", "")

        # Only process human/user and assistant messages
        if msg_type not in ("human", "user", "assistant"):
            continue

        # Normalize "user" -> "human"
        role = "human" if msg_type in ("human", "user") else "assistant"

        # Content can be at data["content"] (simple format) or
        # data["message"]["content"] (Claude Code real format)
        content = data.get("content")
        if content is None:
            msg_obj = data.get("message", {})
            if isinstance(msg_obj, dict):
                content = msg_obj.get("content", "")
            else:
                content = ""

        text_content = _extract_text_from_content(content)
        tool_calls = _extract_tool_calls(content) if role == "assistant" else []
        files = _extract_files(text_content)
        commands = _extract_commands(text_content)

        msg = Message(
            role=role,
            text=text_content,
            tool_calls=tool_calls,
            files_mentioned=files,
            commands_mentioned=commands,
        )
        session.messages.append(msg)

        if max_messages and len(session.messages) >= max_messages:
            break

    return session


def parse_transcripts(
    paths: list[Path],
    max_sessions: int = 0,
    max_messages_per_session: int = 0,
) -> list[Session]:
    """Parse multiple transcript files into Session objects.

    Args:
        paths: List of .jsonl file paths.
        max_sessions: Limit number of sessions to parse (0 = unlimited).
        max_messages_per_session: Limit messages per session (0 = unlimited).

    Returns:
        List of Session objects.
    """
    sessions = []
    limit = max_sessions if max_sessions > 0 else len(paths)

    for path in paths[:limit]:
        session = parse_transcript(path, max_messages=max_messages_per_session)
        sessions.append(session)

    return sessions


def report_parse_stats(sessions: list[Session]) -> dict:
    """Generate parsing stats for display.

    Returns dict with:
        total_sessions: int
        total_messages: int
        total_human: int
        total_assistant: int
        total_tool_calls: int
        total_parse_errors: int
        top_projects: list[tuple[str, int]]  (project, message count) sorted desc
    """
    total_messages = sum(s.message_count for s in sessions)
    total_human = sum(len(s.human_messages) for s in sessions)
    total_assistant = sum(len(s.assistant_messages) for s in sessions)
    total_tool_calls = sum(
        len(tc)
        for s in sessions
        for m in s.assistant_messages
        for tc in [m.tool_calls]
    )
    total_errors = sum(s.parse_errors for s in sessions)

    # Aggregate by project
    project_counts: dict[str, int] = {}
    for s in sessions:
        project_counts[s.project_path] = (
            project_counts.get(s.project_path, 0) + s.message_count
        )

    top_projects = sorted(project_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "total_sessions": len(sessions),
        "total_messages": total_messages,
        "total_human": total_human,
        "total_assistant": total_assistant,
        "total_tool_calls": total_tool_calls,
        "total_parse_errors": total_errors,
        "top_projects": top_projects,
    }
