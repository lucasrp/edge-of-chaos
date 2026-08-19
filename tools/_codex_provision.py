"""_codex_provision - render Codex skill wrappers for an Edge install.

Codex discovers global user skills from CODEX_HOME/skills (default ~/.codex/skills).
The canonical Edge contracts stay under the installed Edge tree's skills/<slug>/SKILL.md;
the Codex files are thin wrappers that point back to those canonical contracts.
"""
from pathlib import Path


def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs, keeping repeated apply runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def codex_prefixes(cfg: dict) -> list:
    """The Codex skill names exposed for this install.

    tool_prefix keeps the stable family alias (edge-*). skill_prefix is the install's
    operator-facing alias (ed-* for the edge-of-chaos branch, roberto-* on Roberto's install).
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


def render_codex_skill(*, slug: str, prefix: str, canonical_skill: Path) -> str:
    """Render a global Codex wrapper for one canonical Edge skill."""
    name = f"{prefix}-{slug}"
    canonical = str(Path(canonical_skill).expanduser())
    # "Use when" makes the skill discoverable in the Codex picker (same bar as official skills).
    return (
        "---\n"
        f"name: {name}\n"
        # O Codex invoca skill por `@nome`, NUNCA por slash (palavra do operador, 2026-08-16).
        # Anunciar `/nome` aqui ensina o modelo a sugerir um comando que não existe nesta
        # superfície — e a description é justamente o que decide quando a skill ativa. O grok é
        # o oposto (barra), e por isso os dois provisionadores divergem de propósito.
        f"description: \"Edge `{slug}` (`@{name}`). Use when the user invokes "
        f"`@{name}` or asks for Edge {slug} (wake, mentor, beat, report, …). "
        f"Then read `{canonical}` completely and follow that contract.\"\n"
        "---\n"
        f"You are running the Edge skill **{name}**.\n\n"
        f"1. Read `{canonical}` completely (canonical contract).\n"
        f"2. Follow it as the active skill — do not re-interpret this wrapper.\n"
        f"3. Work from the install `edge_home` that owns that `skills/` tree.\n"
    )


def provision_codex(cfg: dict, repo: Path, edge_home: Path, codex_home: Path) -> list:
    """Idempotently provision CODEX_HOME/skills with prefixed Edge wrappers."""
    repo = Path(repo)
    edge_home = Path(edge_home).expanduser()
    codex_home = Path(codex_home).expanduser()
    prefixes = codex_prefixes(cfg)
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
                dst = codex_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(
                    dst,
                    render_codex_skill(
                        slug=skill_dir.name,
                        prefix=prefix,
                        canonical_skill=canonical,
                    ),
                )
                installed += 1

    rows.append(f"{installed} skills -> {codex_home / 'skills'} ({', '.join(prefixes)}-*)")
    return rows
