"""_claude_provision — render the ~/.claude artifacts from agent.yaml (issue #10).

Provisions, idempotently:
  - ~/.claude/CLAUDE.md           (identity: name/codename/mission/voice + memory linkage)
  - ~/.claude/skills/{prefix}-{name}/SKILL.md  for each skills/{name}/SKILL.md
  - ~/.claude/projects/{memory_project_dir}/memory/  (seeded only if absent)

The transform for a skill (derived from the live edge-next output shape):
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
    """Claude's per-project memory dir key, derived from edge_home (path → dashed key)."""
    home = str(cfg.get("edge_home", "~/edge-next/"))
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
    prefix = str(cfg.get("skill_prefix", cfg.get("codename", "")))
    rows = []

    # 1. CLAUDE.md
    _write_if_changed(claude_home / "CLAUDE.md", render_claude_md(cfg))
    rows.append(f"CLAUDE.md → {claude_home / 'CLAUDE.md'}")

    # 2. skills/{name}/SKILL.md → skills/{prefix}-{name}/SKILL.md
    skills_src = repo / "skills"
    installed = 0
    if skills_src.exists():
        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            rendered = render_skill(skill_file.read_text(), name=skill_dir.name, prefix=prefix)
            dst = claude_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
            _write_if_changed(dst, rendered)
            installed += 1
    rows.append(f"{installed} skills → ~/.claude/skills/{prefix}-*")

    # 3. seed memory project dir (only if absent)
    mem_dir = claude_home / "projects" / memory_project_dir(cfg) / "memory"
    if not mem_dir.exists():
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text("# MEMORY\n")
        rows.append(f"memory seeded → {mem_dir}")
    else:
        rows.append(f"memory present → {mem_dir} (left as-is)")

    return rows
