"""Skill scaffolding — create new skill directories from templates."""

from __future__ import annotations

import re
from pathlib import Path

import click

from edge_of_chaos.config import CONTINUUM_DIR

# Kebab-case: lowercase letters, numbers, hyphens; must start/end with letter/number
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

SKILL_YAML_TEMPLATE = """\
# Skill manifest — edit to match your skill's purpose.
# See: https://github.com/continuum-project/continuum#skills

id: {name}
name: {display_name}
description: "TODO: describe what this skill does"
version: 0.1.0

# When this skill runs. Options: manual, schedule, hook
triggers:
  - manual

# Memory paths or files this skill reads
inputs: []

# Memory paths or files this skill writes
outputs: []

# Permissions the skill needs. Options: read_memory, write_memory, bash, web
capabilities:
  - read_memory

# Prompt file (relative to this directory)
entrypoint: prompt.md
"""

PROMPT_MD_TEMPLATE = """\
# {display_name}

## Context

<!-- Describe the context this skill operates in.
     What project, domain, or situation is relevant? -->

TODO: describe the context.

## Task

<!-- What should the agent do when this skill runs?
     Be specific about inputs, steps, and constraints. -->

TODO: describe the task.

## Output

<!-- What should the agent produce?
     Specify format, location, and any quality criteria. -->

TODO: describe the expected output.
"""


def create_skill(name: str, continuum_dir: Path) -> Path:
    """Create a new skill scaffold under .continuum/skills/local/<name>/.

    Args:
        name: Skill name in kebab-case (e.g. "my-custom-skill").
        continuum_dir: Path to the .continuum directory.

    Returns:
        Path to the created skill directory.

    Raises:
        click.ClickException: If name is invalid or skill already exists.
    """
    # Validate kebab-case
    if not KEBAB_CASE_RE.match(name):
        raise click.ClickException(
            f"Invalid skill name '{name}'. "
            "Use kebab-case: lowercase letters, numbers, and hyphens only "
            "(e.g. 'my-custom-skill')."
        )

    # Check target directory
    skill_dir = continuum_dir / "skills" / "local" / name
    if skill_dir.exists():
        raise click.ClickException(
            f"Skill '{name}' already exists at {skill_dir}"
        )

    # Create directory
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate display name from kebab-case
    display_name = name.replace("-", " ").title()

    # Write skill.yaml
    yaml_content = SKILL_YAML_TEMPLATE.format(name=name, display_name=display_name)
    (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")

    # Write prompt.md
    prompt_content = PROMPT_MD_TEMPLATE.format(display_name=display_name)
    (skill_dir / "prompt.md").write_text(prompt_content, encoding="utf-8")

    # Print instructions
    click.echo(f"Created skill '{name}' at {skill_dir}/")
    click.echo(f"  {skill_dir / 'skill.yaml'}")
    click.echo(f"  {skill_dir / 'prompt.md'}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit skill.yaml to set description and capabilities")
    click.echo(f"  2. Edit prompt.md with your skill's instructions")
    click.echo(f"  3. Run: continuum run {name}")

    return skill_dir
