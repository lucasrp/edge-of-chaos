"""_envconf — load repo-root .env tunables into os.environ and read typed EDGE_* settings.

A best-effort loader so close/conductor/etc. tunables (review-loop bounds, thresholds) live in ONE
`.env` at the repo root instead of hardcoded magic numbers. The existing process environment ALWAYS
wins (never overwritten), so a per-host `secrets/*.env`, a `/goal`/CI export, or an explicit env var
overrides the `.env` file. No-op when `.env` is absent (defaults in code still apply).
"""
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def load_dotenv(path=None):
    """Source KEY=value lines from the repo-root `.env` (or `path`) into os.environ WITHOUT overwriting
    values already set. Returns the keys it set; no-op if the file is absent. Never raises."""
    env_file = Path(path) if path else (_REPO / ".env")
    set_keys = []
    try:
        text = env_file.read_text()
    except OSError:
        return set_keys
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        # Only EDGE_* tunables (Codex S1 #23): a repo .env must NEVER inject unrelated process config
        # (API keys, endpoints, db vars) — those belong to secrets/*.env / the real environment.
        if k.startswith("EDGE_") and k not in os.environ:
            os.environ[k] = v
            set_keys.append(k)
    return set_keys


# load once on import so any module importing _envconf sees the .env values.
load_dotenv()


def env_int(name, default):
    """Read an int env var with a fallback. A missing or malformed value yields the default; never raises."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)
