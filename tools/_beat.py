"""Beat launcher — run the beat as an agent inside Claude Code (ADR-0003).

The launcher does no cognition: it loads the /ed-beat skill body and pipes it into a single
`claude -p -` invocation. Cognition lives in the skill. Interactive dispatch does not use this
at all — the live session runs the skill in-place (never spawns claude -p).
"""
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def next_producer(roster, state_path) -> str:
    """Advance the round-robin cursor strictly and return whose turn it is (ADR-0012).

    The beat carries ONLY rotation state — no judgment, no queue-jump. Given roster
    ["report","map","plan"] and a fresh cursor, successive calls return report, map, plan,
    report, ... The cursor (the next index to serve) is persisted to `state_path` as JSON;
    the path is injectable so tests use a temp file.
    """
    state_path = Path(state_path)
    try:
        idx = json.loads(state_path.read_text())["next"]
    except (FileNotFoundError, ValueError, KeyError):
        idx = 0
    idx %= len(roster)
    producer = roster[idx]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"next": (idx + 1) % len(roster)}))
    return producer


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


def build_beat_env(home) -> dict:
    """The dispatch env = the launcher env + the install's secrets, so the beat's **agentic** source
    calls (the `via` specs in agent.yaml: exa/x/hn/arxiv/github) AND the graph leg have credentials.
    Without this the `claude -p` child inherits a key-less env and the world-leg darkens — only the
    python tools that touch `_identity` self-load secrets; the agent's own `via`-spec calls do not.
    ADR-0011: never block — a missing secrets dir just returns the base env (the leg darkens, the
    beat still runs)."""
    import _secrets
    try:
        _secrets.load_env(Path(home) / "secrets")
    except Exception:
        pass
    return dict(os.environ)


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
