"""surfaces_cfg — agent.yaml declaration of transcript surfaces (Claude / Codex / Grok).

The edge digests operator sessions from one or more harness stores. Which stores are live is
phenotype config (agent.yaml `surfaces`), not a code fork. Env overrides still win for hermetic
tests and host paths (EDGE_*_SESSIONS_DIR, CODEX_HOME, GROK_HOME).

Shape (all keys optional; missing `surfaces` block preserves historical defaults):

  surfaces:
    claude:
      enabled: true
    codex:
      enabled: true
      home: "~/.codex"          # sessions under <home>/sessions
    grok:
      enabled: true
      home: "~/.grok"
      # active_sessions: optional path; default <home>/active_sessions.json

Defaults when `surfaces` is absent:
  claude enabled, codex enabled, grok enabled (parity after the third surface landed).
When `surfaces` IS present, each surface defaults to enabled=false unless listed with
enabled:true — so installs opt in by declaration.
"""
from __future__ import annotations

import os
from pathlib import Path

# Historical defaults when agent.yaml has no `surfaces` block at all.
_ABSENT_BLOCK_DEFAULTS = {
    "claude": {"enabled": True},
    "codex": {"enabled": True, "home": "~/.codex"},
    "grok": {"enabled": True, "home": "~/.grok"},
    "hermes": {"enabled": True, "home": "~/.hermes"},
}

# CLI harness homes (relative to $HOME). Presence of the home dir = surface is installed.
_SURFACE_HOMES = {
    "claude": ".claude",
    "codex": ".codex",
    "grok": ".grok",
    "hermes": ".hermes",   # 4ª CLI padrão (operador 2026-07-25)
}


def detect_installed_surfaces(env=None, home=None) -> dict[str, bool]:
    """Which CLI surfaces exist on this host (home directory present).

    Assemble and bootstrap use this so install + film cover **everything installed**
    (Claude, Codex, Grok) — not a single CLI.
    """
    env = os.environ if env is None else env
    home = Path(home).expanduser() if home else Path.home()
    out = {}
    for name, rel in _SURFACE_HOMES.items():
        # env overrides for home paths
        if name == "codex" and env.get("CODEX_HOME"):
            p = Path(os.path.expanduser(env["CODEX_HOME"]))
        elif name == "grok" and env.get("GROK_HOME"):
            p = Path(os.path.expanduser(env["GROK_HOME"]))
        elif name == "hermes" and env.get("HERMES_HOME"):
            p = Path(os.path.expanduser(env["HERMES_HOME"]))
        else:
            p = home / rel
        out[name] = p.is_dir()
    return out


def surfaces_block_for_installed(env=None, home=None) -> dict:
    """Phenotype `surfaces:` block enabling every installed harness."""
    installed = detect_installed_surfaces(env=env, home=home)
    block = {}
    for name, ok in installed.items():
        if not ok:
            continue
        if name == "claude":
            block[name] = {"enabled": True}
        elif name == "codex":
            block[name] = {"enabled": True, "home": "~/.codex"}
        elif name == "grok":
            block[name] = {"enabled": True, "home": "~/.grok"}
        elif name == "hermes":
            block[name] = {"enabled": True, "home": "~/.hermes"}
    return block


def load_agent_cfg(agent_yaml=None) -> dict:
    """Load agent.yaml as a dict. Prefer injectible path for tests."""
    if agent_yaml is None:
        try:
            import _identity
            agent_yaml = _identity.AGENT_YAML
        except Exception:
            agent_yaml = Path(__file__).resolve().parent.parent / "agent.yaml"
    p = Path(agent_yaml)
    if not p.is_file():
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text()) or {}
    except Exception:
        return {}


def surface_entry(name: str, cfg: dict | None = None, agent_yaml=None) -> dict:
    """The agent.yaml entry for one surface name (may be empty)."""
    cfg = load_agent_cfg(agent_yaml) if cfg is None else cfg
    block = cfg.get("surfaces")
    if block is None:
        return dict(_ABSENT_BLOCK_DEFAULTS.get(name, {}))
    if not isinstance(block, dict):
        return {}
    entry = block.get(name)
    if not isinstance(entry, dict):
        # listed as bare true/false?
        if entry is True:
            return {"enabled": True}
        if entry is False:
            return {"enabled": False}
        return {}
    return dict(entry)


def surface_enabled(name: str, cfg: dict | None = None, agent_yaml=None) -> bool:
    """Whether agent.yaml enables this surface for real (non-hermetic) sweeps."""
    entry = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml)
    val = entry.get("enabled", False)
    return bool(val)


def surface_home(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Resolved home dir for an optional surface (codex/grok), or None if unset.

    Precedence for codex: CODEX_HOME env → agent.yaml surfaces.codex.home → ~/.codex
    Precedence for grok:  GROK_HOME env  → agent.yaml surfaces.grok.home  → ~/.grok
    """
    env = os.environ if env is None else env
    env_key = {"codex": "CODEX_HOME", "grok": "GROK_HOME", "hermes": "HERMES_HOME"}.get(name)
    if env_key:
        raw = env.get(env_key)
        if isinstance(raw, str) and raw.strip():
            return Path(os.path.expanduser(raw.strip()))
    entry = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml)
    home = entry.get("home")
    if isinstance(home, str) and home.strip():
        return Path(os.path.expanduser(home.strip()))
    if name == "codex":
        return Path.home() / ".codex"
    if name == "grok":
        return Path.home() / ".grok"
    if name == "hermes":
        return Path.home() / ".hermes"
    return None


def surface_sessions_dir(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Sessions root for codex/grok. Env EDGE_*_SESSIONS_DIR wins when set."""
    env = os.environ if env is None else env
    env_key = {"codex": "EDGE_CODEX_SESSIONS_DIR", "grok": "EDGE_GROK_SESSIONS_DIR"}.get(name)
    if env_key:
        raw = env.get(env_key)
        if isinstance(raw, str) and raw.strip():
            return Path(os.path.expanduser(raw.strip()))
    entry = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml)
    sessions = entry.get("sessions")
    if isinstance(sessions, str) and sessions.strip():
        return Path(os.path.expanduser(sessions.strip()))
    home = surface_home(name, cfg=cfg, agent_yaml=agent_yaml, env=env)
    if home is None:
        return None
    return home / "sessions"


def surface_active_sessions_path(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Grok (and future) live-session index path."""
    env = os.environ if env is None else env
    if name == "grok":
        raw = env.get("EDGE_GROK_ACTIVE_SESSIONS")
        if isinstance(raw, str) and raw.strip():
            return Path(os.path.expanduser(raw.strip()))
    entry = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml)
    raw = entry.get("active_sessions")
    if isinstance(raw, str) and raw.strip():
        return Path(os.path.expanduser(raw.strip()))
    home = surface_home(name, cfg=cfg, agent_yaml=agent_yaml, env=env)
    if home is None:
        return None
    return home / "active_sessions.json"


def include_optional_surface(name: str, project_or_store_dir, explicit_dir,
                             cfg: dict | None = None, agent_yaml=None) -> bool:
    """Whether plan_sweep / quente / topic_threads should join this optional surface.

    Mirrors the Codex hermetic rule:
      - explicit_dir is False → off (tests)
      - explicit_dir is a path → on (tests / override)
      - explicit_dir is None and project_or_store_dir is None → real host; honor agent.yaml
        **and** only film if the surface is installed on the host
      - explicit_dir is None and project_or_store_dir is set → hermetic Claude-only unless
        tests pass explicit_dir

    Assemble rule (operator): pick up **everything installed** — if the harness home exists
    and agent.yaml enables the surface (or no surfaces block → all enabled by default), include it.
    """
    if explicit_dir is False:
        return False
    if explicit_dir is not None:
        return True
    if project_or_store_dir is not None:
        return False
    if not surface_enabled(name, cfg=cfg, agent_yaml=agent_yaml):
        return False
    # Only film surfaces that are actually installed (home dir present)
    installed = detect_installed_surfaces()
    return bool(installed.get(name, False))


def provision_surface(name: str, cfg: dict | None = None, agent_yaml=None) -> bool:
    """Whether edge-apply / bootstrap should provision skills into this surface's home.

    Claude is always provisioned when its home will be written. Codex/Grok: enabled in yaml
    **or** installed on the host (first-run / multi-CLI default — provision everything installed).
    """
    if name == "claude":
        return True
    if surface_enabled(name, cfg=cfg, agent_yaml=agent_yaml):
        return True
    # No yaml / first-run: still provision every installed CLI
    return bool(detect_installed_surfaces().get(name, False))
