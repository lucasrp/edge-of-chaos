"""_grok_provision - render Grok skill wrappers for an Edge install.

Grok discovers user skills from GROK_HOME/skills (default ~/.grok/skills), plus project
`.agents/skills`. The canonical Edge contracts stay under the installed Edge tree's
skills/<slug>/SKILL.md; the Grok files are thin wrappers that point back to those contracts
(same shape as Codex wrappers).
"""
from pathlib import Path


def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs, keeping repeated apply runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def grok_prefixes(cfg: dict) -> list:
    """The Grok skill names exposed for this install.

    tool_prefix keeps the stable family alias (edge-*). skill_prefix is the install's
    operator-facing alias (ed-* for the edge-of-chaos branch).
    """
    raw = [
        cfg.get("tool_prefix") or "edge",
        cfg.get("skill_prefix") or cfg.get("codename") or cfg.get("name") or "edge",
    ]
    out = []
    for item in raw:
        prefix = str(item).strip()
        if prefix and prefix not in out:
            out.append(prefix)
    return out


def render_grok_skill(*, slug: str, prefix: str, canonical_skill: Path) -> str:
    """Render a global Grok wrapper for one canonical Edge skill."""
    name = f"{prefix}-{slug}"
    canonical = str(Path(canonical_skill).expanduser())
    return (
        "---\n"
        f"name: {name}\n"
        f"description: Edge wrapper for {slug}. Select @{name} in the skills picker "
        f"(or ask for `{name}` by name) to follow the canonical {canonical} contract.\n"
        "---\n"
        f"Select this skill as `@{name}` (or name `{name}` in the prompt). Then read "
        f"`{canonical}` completely and follow it as the active Edge skill. This wrapper "
        f"exposes the global Grok skill name `{name}`; do not duplicate or reinterpret "
        "the canonical contract here.\n"
    )


def provision_grok(cfg: dict, repo: Path, edge_home: Path, grok_home: Path) -> list:
    """Idempotently provision GROK_HOME/skills with prefixed Edge wrappers."""
    repo = Path(repo)
    edge_home = Path(edge_home).expanduser()
    grok_home = Path(grok_home).expanduser()
    prefixes = grok_prefixes(cfg)
    rows = []
    installed = 0

    skills_src = repo / "skills"
    if skills_src.exists():
        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists() or skill_dir.name == "_shared":
                continue
            canonical = edge_home / "skills" / skill_dir.name / "SKILL.md"
            for prefix in prefixes:
                dst = grok_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(
                    dst,
                    render_grok_skill(
                        slug=skill_dir.name,
                        prefix=prefix,
                        canonical_skill=canonical,
                    ),
                )
                installed += 1

    rows.append(f"{installed} skills -> {grok_home / 'skills'} ({', '.join(prefixes)}-*)")
    return rows
