"""_claude_provision — render the ~/.claude artifacts from agent.yaml (issue #10).

Provisions, idempotently:
  - ~/.claude/CLAUDE.md           (identity: name/codename/mission/voice + memory linkage)
  - ~/.claude/skills/{prefix}-{name}/SKILL.md  for each skills/{name}/SKILL.md
  - ~/.claude/skills/_shared/*                 support docs copied verbatim
  - ~/.claude/projects/{memory_project_dir}/memory/  (seeded only if absent)

The transform for a skill (derived from the live edge install output shape):
  - frontmatter `name: {name}` → `name: {prefix}-{name}`
  - add `user-invocable: true` as the last frontmatter field
  - frontmatter + body literal `{prefix}` → the skill_prefix value

claude_home is always a parameter so tests never touch the real ~/.claude.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_TPL = REPO / "templates" / "CLAUDE.md.tpl"


def render_text(text: str, variables: dict) -> str:
    """Substitute {{var}} from variables (same convention as tools/edge-render)."""
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda m: variables.get(m.group(1), m.group(0)),
        text,
    )


def claude_vars(cfg: dict) -> dict:
    """Identity variables for CLAUDE.md, derived from agent.yaml."""
    return {
        "name": str(cfg.get("name", "")),
        "codename": str(cfg.get("codename", cfg.get("name", ""))),
        "mission": str(cfg.get("mission", "")),
        "voice": str(cfg.get("voice", "")),
        "language": str(cfg.get("language", "")),
        "skill_prefix": str(cfg.get("skill_prefix", cfg.get("codename", ""))),
        "heartbeat_interval": str(cfg.get("heartbeat_interval", "")),
    }


def render_claude_md(cfg: dict) -> str:
    """Render ~/.claude/CLAUDE.md from agent.yaml identity fields."""
    return render_text(CLAUDE_TPL.read_text(), claude_vars(cfg))


def memory_project_dir(cfg: dict) -> str:
    """Claude's per-project memory dir key, derived from agent.yaml `edge_home` (path → dashed key).
    No baked-in install-path literal (#21): the install root is the genotype's, not a tenant's."""
    home = str(cfg.get("edge_home") or "~/edge/")
    expanded = str(Path(home).expanduser())
    return expanded.rstrip("/").replace("/", "-")


def render_skill(content: str, *, name: str, prefix: str) -> str:
    """Render one SKILL.md body into its ~/.claude form. Idempotent on its own output."""
    lines = content.splitlines(keepends=True)
    # Locate the frontmatter block: starts with '---' and closes at the next '---'.
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"skill {name!r}: missing frontmatter opening '---'")
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        raise ValueError(f"skill {name!r}: missing frontmatter closing '---'")

    fm = lines[1:close]
    body = "".join(lines[close + 1:])

    prefixed = f"{prefix}-{name}"
    out_fm = []
    has_user_invocable = False
    for ln in fm:
        if re.match(r"^name:\s", ln):
            ln = f"name: {prefixed}\n"
        if re.match(r"^user-invocable:\s", ln):
            has_user_invocable = True
            ln = "user-invocable: true\n"
        ln = ln.replace("{prefix}", prefix)   # substitute in frontmatter too (e.g. the description)
        out_fm.append(ln)
    if not has_user_invocable:
        out_fm.append("user-invocable: true\n")

    body = body.replace("{prefix}", prefix)

    return "---\n" + "".join(out_fm) + "---\n" + body


def render_agent(content: str, *, name: str, prefix: str) -> str:
    """Render one .claude/agents/{name}.md into its ~/.claude/agents form. Mirrors render_skill but for
    a SUBAGENT: it prefixes `name`, substitutes {prefix}, and PRESERVES `disallowedTools` verbatim (the
    N5/R6 wall — the harness reads this camelCase subagent key to strip mcp__cortex__* from a
    world-reading fan). No `user-invocable` (a subagent is dispatched by type, never slash-invoked)."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"agent {name!r}: missing frontmatter opening '---'")
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        raise ValueError(f"agent {name!r}: missing frontmatter closing '---'")
    fm = lines[1:close]
    body = "".join(lines[close + 1:])
    prefixed = f"{prefix}-{name}"
    out_fm = []
    for ln in fm:
        if re.match(r"^name:\s", ln):
            ln = f"name: {prefixed}\n"
        ln = ln.replace("{prefix}", prefix)
        out_fm.append(ln)
    body = body.replace("{prefix}", prefix)
    return "---\n" + "".join(out_fm) + "---\n" + body


def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs — keeps mtime stable and runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def provision_claude(cfg: dict, repo: Path, claude_home: Path) -> list:
    """Idempotently provision claude_home (CLAUDE.md + prefixed skills + memory seed).

    claude_home is always passed in so tests/smoke-runs never touch the real ~/.claude.
    Returns a list of human-readable status lines.
    """
    repo = Path(repo)
    claude_home = Path(claude_home)
    # Same dual-prefix rule as Codex/Grok: skill_prefix (ed-*) + tool_prefix (edge-*)
    try:
        from _codex_provision import codex_prefixes as _prefixes
        prefixes = _prefixes(cfg)
    except Exception:
        prefixes = [str(cfg.get("skill_prefix", cfg.get("codename", "ed")) or "ed")]
    if not prefixes:
        prefixes = ["ed"]
    rows = []

    # 1. CLAUDE.md
    _write_if_changed(claude_home / "CLAUDE.md", render_claude_md(cfg))
    rows.append(f"CLAUDE.md → {claude_home / 'CLAUDE.md'}")

    # 1a. Retention guard — o Claude Code apaga transcripts velhos (cleanupPeriodDays,
    # default 30) no launch; as sessões SÃO a memória-substrato do edge (caso edgesandbox
    # 2026-07-25: o 1º launch do install comeu o histórico de junho do mentee às 12:02).
    # Só escreve quando o operador ainda não fixou o knob — nunca sobrepõe escolha dele.
    import json as _json
    settings_path = claude_home / "settings.json"
    try:
        settings = _json.loads(settings_path.read_text()) if settings_path.exists() else {}
        if "cleanupPeriodDays" not in settings:
            settings["cleanupPeriodDays"] = 3650
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(_json.dumps(settings, indent=2) + "\n")
            rows.append(f"cleanupPeriodDays=3650 → {settings_path} (retenção de transcripts)")
    except (OSError, ValueError) as e:
        rows.append(f"retention guard skipped: {type(e).__name__}: {e}")

    # 2. skills/{name}/SKILL.md → skills/{prefix}-{name}/SKILL.md for each prefix
    skills_src = repo / "skills"
    installed = 0
    if skills_src.exists():
        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists() or skill_dir.name == "_shared":
                continue
            for prefix in prefixes:
                rendered = render_skill(
                    skill_file.read_text(), name=skill_dir.name, prefix=prefix
                )
                dst = claude_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(dst, rendered)
                installed += 1
    rows.append(
        f"{installed} skills → ~/.claude/skills/ ({', '.join(p + '-*' for p in prefixes)})"
    )

    # 2a. skills/_shared/* → ~/.claude/skills/_shared/*
    # Shared files are support material read by prefixed skills; they are not slash-invocable.
    shared_src = skills_src / "_shared"
    shared_installed = 0
    if shared_src.exists():
        for src in sorted(p for p in shared_src.rglob("*") if p.is_file()):
            rel = src.relative_to(shared_src)
            _write_if_changed(claude_home / "skills" / "_shared" / rel,
                              src.read_text(encoding="utf-8"))
            shared_installed += 1
    rows.append(f"{shared_installed} shared files → ~/.claude/skills/_shared")

    # 2b. .claude/agents/{name}.md → ~/.claude/agents/{prefix}-{name}.md (the mechanical subagent
    # artifacts — e.g. the world-reading `explorer` whose frontmatter `disallowedTools: mcp__cortex__*`
    # is the N5/R6 wall: the harness strips the self door from a world-reading fan BY CONSTRUCTION,
    # not by prose). Prefixed like skills so the dispatch references a real, deployed artifact.
    agents_src = repo / ".claude" / "agents"
    agents_installed = 0
    if agents_src.exists():
        for agent_file in sorted(agents_src.glob("*.md")):
            rendered = render_agent(agent_file.read_text(), name=agent_file.stem, prefix=prefix)
            dst = claude_home / "agents" / f"{prefix}-{agent_file.stem}.md"
            _write_if_changed(dst, rendered)
            agents_installed += 1
    rows.append(f"{agents_installed} agents → ~/.claude/agents/{prefix}-*")

    # 3. seed memory project dir (only if absent)
    mem_dir = claude_home / "projects" / memory_project_dir(cfg) / "memory"
    if not mem_dir.exists():
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text("# MEMORY\n")
        rows.append(f"memory seeded → {mem_dir}")
    else:
        rows.append(f"memory present → {mem_dir} (left as-is)")

    return rows
