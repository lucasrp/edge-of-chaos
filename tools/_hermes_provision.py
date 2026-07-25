"""_hermes_provision - render Hermes skill wrappers for an Edge install.

Hermes (Nous Research) é a 4ª CLI padrão do edge (operador 2026-07-25). Ele descobre
user-skills de HERMES_HOME/skills/<name>/SKILL.md — a MESMA convenção SKILL.md dos
outros harnesses. Os arquivos aqui são wrappers finos que apontam de volta pro contrato
canônico do install (mesmo shape dos wrappers Grok/Codex). Genérico por construção:
nenhum nome de install hardcoded — qualquer usuário do hermes com o edge provisiona igual.
"""
from pathlib import Path


def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs, keeping repeated apply runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def hermes_prefixes(cfg: dict) -> list:
    """The Hermes skill names exposed for this install.

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


def render_hermes_skill(*, slug: str, prefix: str, canonical_skill: Path) -> str:
    """Render a global Hermes wrapper for one canonical Edge skill."""
    name = f"{prefix}-{slug}"
    canonical = str(Path(canonical_skill).expanduser())
    return (
        "---\n"
        f"name: {name}\n"
        f"description: \"Edge `{slug}` skill (`/{name}`). Use when the user invokes "
        f"`/{name}`, `@{name}`, or asks for Edge {slug}. "
        f"Read the full contract at {canonical} and follow it.\"\n"
        "---\n"
        f"You are running the Edge skill **{name}**.\n\n"
        f"1. Read `{canonical}` completely (canonical contract).\n"
        f"2. Follow it as the active skill — do not re-interpret this wrapper.\n"
        f"3. Work from the install edge_home that owns that skills/ tree.\n"
    )


def provision_hermes(cfg: dict, repo: Path, edge_home: Path, hermes_home: Path) -> list:
    """Idempotently provision HERMES_HOME/skills with prefixed Edge wrappers."""
    repo = Path(repo)
    edge_home = Path(edge_home).expanduser()
    hermes_home = Path(hermes_home).expanduser()
    prefixes = hermes_prefixes(cfg)
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
                dst = hermes_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(
                    dst,
                    render_hermes_skill(
                        slug=skill_dir.name, prefix=prefix, canonical_skill=canonical),
                )
                installed += 1
    rows.append(f"hermes skills: {installed} wrappers em {hermes_home / 'skills'}")
    return rows
