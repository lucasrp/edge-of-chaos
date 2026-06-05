"""Beat launcher — run the beat as an agent inside Claude Code (ADR-0003).

The launcher does no cognition: it loads the /ed-beat skill body and pipes it into a single
`claude -p -` invocation. Cognition lives in the skill. Interactive dispatch does not use this
at all — the live session runs the skill in-place (never spawns claude -p).
"""
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def resolve_claude_bin() -> str:
    """Find the claude CLI: env override, then PATH, then common install locations."""
    candidates = []
    env_override = os.environ.get("EDGE_CLAUDE_BIN") or os.environ.get("CLAUDE_BIN")
    if env_override:
        candidates.append(env_override)
    path_hit = shutil.which("claude")
    if path_hit:
        candidates.append(path_hit)
    home = Path.home()
    candidates += [str(home / ".local" / "bin" / "claude"), str(home / "bin" / "claude")]
    for hit in sorted((home / ".nvm" / "versions" / "node").glob("*/bin/claude"), reverse=True):
        candidates.append(str(hit))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("claude CLI not found on PATH or common install locations")


def build_beat_command(claude_bin: str) -> list:
    """One beat = one single-shot `claude -p -`, permissions bypassed. No retry, no envelope."""
    return [claude_bin, "-p", "-", "--dangerously-skip-permissions"]


def load_beat_prompt(home) -> str:
    """The /ed-beat skill body (frontmatter stripped), piped as the prompt. home wins over repo."""
    for base in (Path(home) / "skills", REPO / "skills"):
        p = base / "beat" / "SKILL.md"
        if p.exists():
            text = p.read_text()
            if text.startswith("---"):
                parts = text.split("---", 2)
                text = parts[2] if len(parts) >= 3 else text
            return text.strip()
    raise FileNotFoundError("beat skill not found (skills/beat/SKILL.md)")
