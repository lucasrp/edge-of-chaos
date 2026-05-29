"""core_identity — assemble the immutable identity core.

The core is injected when the agent is invoked AS edge (a skill runs or a beat
fires), never into a bare Claude Code session. Single source: the three
core-memory files. Keep this module dependency-free so both the dispatch runtime
and edge-apply can import it.
"""

from __future__ import annotations

from pathlib import Path

CORE_FILES = ("personality.md", "method.md", "rules-core.md")

CORE_HEADER = (
    "=== IDENTITY CORE (immutable) ===\n"
    "Who you are, how you reason, and how you operate edge. This precedes the "
    "situational context that follows and is authoritative over it. Read it "
    "first.\n"
)


def render_core_identity(memory_dir) -> str:
    """Concatenate the three core-memory files into one immutable block.

    Returns an empty string if none of the files exist, so callers degrade
    gracefully instead of breaking the dispatch/apply path.
    """
    memory_dir = Path(memory_dir)
    parts: list[str] = []
    for name in CORE_FILES:
        try:
            text = (memory_dir / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(text)
    if not parts:
        return ""
    return CORE_HEADER + "\n" + "\n\n---\n\n".join(parts) + "\n"


def inject_after_frontmatter(content: str, core: str) -> str:
    """Insert `core` after a leading YAML frontmatter block, or at the very top
    if there is none. Keeps the frontmatter (name/description) intact so the
    skill loader still parses it.
    """
    if not core:
        return content
    block = f"\n{core}\n"
    if content.startswith("---"):
        first_nl = content.find("\n")
        close = content.find("\n---", first_nl) if first_nl != -1 else -1
        if close != -1:
            close_line_end = content.find("\n", close + 1)
            if close_line_end == -1:
                close_line_end = len(content) - 1
            return content[: close_line_end + 1] + block + content[close_line_end + 1 :]
    return core + "\n\n" + content
