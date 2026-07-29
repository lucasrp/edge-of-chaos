"""_hermes_provision - render Hermes skill wrappers for an Edge install.

Hermes (Nous Research) é a 4ª CLI padrão do edge (operador 2026-07-25). Ele descobre
user-skills de HERMES_HOME/skills/<name>/SKILL.md — a MESMA convenção SKILL.md dos
outros harnesses. Os arquivos aqui são wrappers finos que apontam de volta pro contrato
canônico do install (mesmo shape dos wrappers Grok/Codex). Genérico por construção:
nenhum nome de install hardcoded — qualquer usuário do hermes com o edge provisiona igual.
"""
from pathlib import Path
import shutil

import yaml

def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs, keeping repeated apply runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def hermes_prefixes(cfg: dict) -> list:
    """Expose only the install-specific alias; duplicate families add no capability."""
    prefix = cfg.get("skill_prefix") or cfg.get("codename") or cfg.get("name") or "edge"
    return [str(prefix).strip()]

def render_hermes_skill(slug: str, prefix: str, canonical_skill: Path, edge_group=None) -> str:
    """Render a global Hermes wrapper for one canonical Edge skill."""
    name = f"{prefix}-{slug}"
    canonical = str(Path(canonical_skill).expanduser())
    wake_terminal = (
        "5. WAKE TERMINAL INVARIANT: after all four briefs complete, render the canonical "
        "human-facing orientation (do not dump or merely summarize the briefs), then halt and "
        "ask what the operator wants to work on. Do not start work before their reply.\n"
        if slug == "wake" else ""
    )
    mentor_invariant = (
        "5. MENTOR CONTRACT INVARIANT: observe leveling-state and the operator's work first; cite "
        "one state line before any residual question. Render the contract's opt-in portfolio "
        "orientation and use the lint agenda as evidence, not as an opening script. Ask at most one "
        "free-prose residual question, never a menu. After the operator answers, process all "
        "applicable persona writeback, steers, synthesis, and traceable inscription in the same "
        "turn; advice alone is not completion. Do not stop and ask them to say continue. Do not "
        "force a closing question when the path is clear, and never invent a writeback or "
        "inscription merely to satisfy this wrapper.\n"
        "6. HERMES MEMORY ADAPTER (mandatory, provider-agnostic): use the standing memory context "
        "injected by Hermes' configured memory provider (local, Honcho, Mem0, Hindsight, Holographic, "
        "or another supported provider) and combine it with canonical leveling, portfolio recall, "
        "and Cortex communities. Before the first substantive answer, use any available provider-native "
        "profile/context capability for a compact peer snapshot. If the request depends on prior "
        "statements, preferences, relationships, or cross-session patterns, use the available "
        "provider-native search/reasoning capability; Honcho tools are one implementation, not a "
        "requirement. If it names or depends on a specific Hermes conversation, decision, or where "
        "work stopped, call `session_search` and inspect that original session before concluding. "
        "Do not require tools the configured provider does not expose, do not call expensive retrieval "
        "without its trigger, do not treat one memory system as a substitute for another, and never "
        "persist inferred facts without evidence. HERMES HARD GATE: evidence before answering must "
        "include current conversation + injected/provider memory context (or explicit unavailable "
        "marker) + canonical leveling + portfolio recall + Cortex communities (or explicit DARK "
        "marker), plus any retrieval triggered by the request.\n"
        if slug == "mentor" else ""
    )
    return (
        "---\n"
        f"name: {name}\n"
        f"description: \"Edge `{slug}` skill (`/{name}`). Use when the user invokes "
        f"`/{name}`, `@{name}`, or asks for Edge of Chaos {slug}. "
        f"Read the full contract at {canonical} and follow it.\"\n"
        "---\n"
        f"You are running the Edge of Chaos skill **{name}**.\n\n"
        f"1. Read `{canonical}` completely (canonical contract).\n"
        f"2. Follow it as the active skill — do not re-interpret this wrapper.\n"
        f"3. Work from the install edge_home that owns that skills/ tree.\n"
        + (f"4. Set `EDGE_GROUP={edge_group}` for every EoC tool command.\n" if edge_group else "")
        + wake_terminal
        + mentor_invariant
    )


def provision_hermes(cfg: dict, repo: Path, edge_home: Path, hermes_home: Path,
                     edge_group=None) -> list:
    """Idempotently provision HERMES_HOME/skills with prefixed EoC wrappers."""
    repo = Path(repo)
    edge_home = Path(edge_home).expanduser()
    hermes_home = Path(hermes_home).expanduser()
    prefixes = hermes_prefixes(cfg)
    rows = []
    installed = 0

    skills_src = repo / "skills"
    if skills_src.exists():
        skill_dirs = [p for p in sorted(skills_src.iterdir())
                      if p.is_dir() and not p.name.startswith(".")
                      and p.name != "_shared" and (p / "SKILL.md").exists()]
        desired = {f"{prefix}-{skill_dir.name}"
                   for prefix in prefixes for skill_dir in skill_dirs}
        installed_skills = hermes_home / "skills"
        if installed_skills.is_dir():
            for path in installed_skills.iterdir():
                if path.name not in desired and path.is_dir() \
                        and _managed_wrapper(path, repo, edge_home):
                    shutil.rmtree(path)
        for skill_dir in skill_dirs:
            canonical = edge_home / "skills" / skill_dir.name / "SKILL.md"
            for prefix in prefixes:
                dst = hermes_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(
                    dst,
                    render_hermes_skill(
                        slug=skill_dir.name, prefix=prefix, canonical_skill=canonical,
                        edge_group=edge_group),
                )
                installed += 1
    rows.append(f"hermes skills: {installed} wrappers em {hermes_home / 'skills'}")
    return rows


def _managed_wrapper(path, repo, edge_home=None):
    try:
        body = (path / "SKILL.md").read_text()
    except OSError:
        return False
    roots = [Path(repo).resolve() / "skills"]
    if edge_home is not None:
        roots.append(Path(edge_home).resolve() / "skills")
    marker = "Canonical implementation:" in body or "Read the full contract at" in body
    return marker and any(str(root) in body for root in roots)

def reconcile_hermes_profiles(cfg, repo, edge_home, hermes_root):
    """Make profile-local Edge wrappers match Hermes edge_group configuration."""
    import hermes_profiles

    root = Path(hermes_root)
    homes = [("default", root)]
    profiles = root / "profiles"
    if profiles.is_dir():
        homes.extend((p.name, p) for p in profiles.iterdir() if p.is_dir())
    result = {}
    for name, home in homes:
        member = hermes_profiles.membership(root, name)
        if member.enabled:
            result[name] = provision_hermes(
                cfg, repo, edge_home, home, edge_group=member.edge_group)
            continue
        removed = []
        skills = home / "skills"
        if skills.is_dir():
            for path in skills.iterdir():
                if path.is_dir() and _managed_wrapper(path, repo, edge_home):
                    shutil.rmtree(path)
                    removed.append(path.name)
        result[name] = {"skills_removed": removed}
    return result


def configure_hermes_group(hermes_root, edge_group):
    """Seed the EoC group unless Hermes already has an explicit policy."""
    path = Path(hermes_root) / "config.yaml"
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Hermes config must be a mapping: {path}")
    if "edge_group" in cfg:
        return False
    cfg["edge_group"] = edge_group
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    tmp.replace(path)
    return True


def install_hermes_plugin(cfg, repo, edge_home, hermes_root):
    """Install the startup reconciler as a normal Hermes user plugin."""
    plugin = Path(hermes_root) / "plugins" / "edge-of-chaos"
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.yaml").write_text(
        "name: edge-of-chaos\nversion: 1.0.0\ndescription: Reconcile Edge skills across Hermes profiles\n"
    )
    (plugin / "__init__.py").write_text(
        "from pathlib import Path\nimport sys\n\n"
        f"REPO = Path({str(Path(repo))!r})\n"
        f"EDGE_HOME = Path({str(Path(edge_home))!r})\n"
        f"HERMES_ROOT = Path({str(Path(hermes_root))!r})\n"
        "sys.path.insert(0, str(REPO / 'tools'))\n"
        "def register(ctx):\n"
        "    from _hermes_provision import reconcile_hermes_profiles\n"
        f"    reconcile_hermes_profiles({cfg!r}, REPO, EDGE_HOME, HERMES_ROOT)\n"
    )
    return plugin
