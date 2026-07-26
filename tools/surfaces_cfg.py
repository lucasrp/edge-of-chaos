"""surfaces_cfg — agent.yaml declaration of transcript surfaces (Claude / Codex / Grok).

The edge digests operator sessions from one or more harness stores. Which stores are live is
phenotype config (agent.yaml `surfaces`), not a code fork. Env overrides still win for hermetic
tests and host paths (EDGE_*_SESSIONS_DIR, CODEX_HOME, GROK_HOME).

Hermes-only policy:

  surfaces:
    hermes:
      enabled: true
      home: "~/.hermes"

Detection may inventory legacy CLI homes, but configuration cannot authorize them.
When `surfaces` is absent, only Hermes is enabled.
"""
from __future__ import annotations

import os
from pathlib import Path

import runtime_policy

# Hermes-only defaults when agent.yaml has no `surfaces` block.
_ABSENT_BLOCK_DEFAULTS = {
    "hermes": {"enabled": True},
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
    """Declare Hermes only when a dedicated HERMES_HOME is explicitly installed."""
    env = os.environ if env is None else env
    installed = detect_installed_surfaces(env=env, home=home)
    if not installed.get("hermes"):
        return {}
    raw = env.get("HERMES_HOME")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    dedicated = runtime_policy.require_dedicated_hermes_home(raw.strip())
    return {"hermes": {"enabled": True, "home": str(dedicated)}}


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
    """Whether Hermes-only policy enables this surface for real sweeps."""
    if name not in runtime_policy.ALLOWED_HARNESSES:
        return False
    entry = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml)
    val = entry.get("enabled", False)
    return bool(val)


def surface_home(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Resolve only an explicitly dedicated Hermes home; external surfaces stay opaque."""
    if name not in runtime_policy.ALLOWED_HARNESSES:
        return None
    env = os.environ if env is None else env
    raw = env.get("HERMES_HOME")
    if not isinstance(raw, str) or not raw.strip():
        raw = surface_entry(name, cfg=cfg, agent_yaml=agent_yaml).get("home")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return runtime_policy.require_dedicated_hermes_home(raw.strip())


def surface_sessions_dir(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Return the dedicated Hermes sessions directory, with no external overrides."""
    if name not in runtime_policy.ALLOWED_HARNESSES:
        return None
    home = surface_home(name, cfg=cfg, agent_yaml=agent_yaml, env=env)
    return None if home is None else home / "sessions"


def surface_active_sessions_path(name: str, cfg: dict | None = None, agent_yaml=None, env=None) -> Path | None:
    """Return the dedicated Hermes active-session index path, if configured."""
    if name not in runtime_policy.ALLOWED_HARNESSES:
        return None
    home = surface_home(name, cfg=cfg, agent_yaml=agent_yaml, env=env)
    return None if home is None else home / "active_sessions.json"

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

    Hermes-only rule: external surfaces stay off even when an explicit directory is supplied.
    Hermes itself may still use the generic override semantics below.
    """
    if name not in runtime_policy.ALLOWED_HARNESSES:
        return False
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
    """Whether the Hermes-only derivative may provision this surface."""
    runtime_policy.require_allowed_harness(name)
    effective_cfg = load_agent_cfg(agent_yaml) if cfg is None else cfg
    runtime_policy.require_hermes_only_surfaces(effective_cfg)
    return surface_enabled(name, cfg=effective_cfg)
