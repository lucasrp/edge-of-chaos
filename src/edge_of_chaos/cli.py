"""Continuum CLI — click-based command interface."""

import click

from edge_of_chaos import __version__


@click.group()
@click.version_option(version=__version__, prog_name="continuum")
def main():
    """Edge of Chaos — local-first runtime for Claude Code.

    Persistent memory, autonomous routines, and intelligent bootstrap
    via transcript scanning.
    """


@main.command()
def init():
    """Initialize continuum in the current directory."""
    from edge_of_chaos.init import run_init

    run_init()


@main.command()
@click.option("--sanitization", type=click.Choice(["strict", "balanced", "raw"]), default="balanced", help="Sanitization mode.")
@click.option("--max-sessions", type=int, default=200, help="Max sessions to process.")
@click.option("--dry-run", is_flag=True, help="Show what would be extracted without writing.")
def scan(sanitization, max_sessions, dry_run):
    """Scan Claude Code transcripts and create bootstrap memory."""
    from edge_of_chaos.scan import run_scan

    run_scan(
        sanitization=sanitization,
        max_sessions=max_sessions,
        dry_run=dry_run,
    )


@main.command()
@click.argument("skill_id")
def run(skill_id):
    """Run a skill by ID."""
    from edge_of_chaos.skills.runner import run_skill

    run_skill(skill_id)


@main.command()
def status():
    """Show current continuum status."""
    from edge_of_chaos.status import run_status

    run_status()


@main.command()
def doctor():
    """Check continuum installation health."""
    import sys as _sys

    from edge_of_chaos.doctor import run_doctor

    _sys.exit(run_doctor())


@main.group()
def skills():
    """Manage continuum skills."""


@skills.command("list")
def skills_list():
    """List available skills."""
    from pathlib import Path

    from edge_of_chaos.config import CONTINUUM_DIR
    from edge_of_chaos.skills.manifest import discover_skills

    root = Path.cwd()
    continuum_dir = root / CONTINUUM_DIR

    if not continuum_dir.exists():
        click.echo("No .continuum/ directory found. Run 'continuum init' first.")
        return

    found = discover_skills(continuum_dir)
    if not found:
        click.echo("No skills found.")
        click.echo("  Core skills go in .continuum/skills/core/")
        click.echo("  Local skills go in .continuum/skills/local/")
        click.echo("  Create one with: continuum skills new <name>")
        return

    click.echo(f"Available skills ({len(found)}):\n")
    for skill_dir, skill in found:
        # Determine if core or local
        location = "core" if "/skills/core/" in str(skill_dir) else "local"
        triggers = ", ".join(skill.triggers)
        click.echo(f"  {skill.id}  [{location}]  v{skill.version}")
        if skill.description:
            click.echo(f"    {skill.description}")
        click.echo(f"    triggers: {triggers}  entrypoint: {skill.entrypoint}")


@skills.command("new")
@click.argument("name")
def skills_new(name):
    """Create a new skill scaffold."""
    from pathlib import Path

    from edge_of_chaos.config import CONTINUUM_DIR
    from edge_of_chaos.skills.scaffold import create_skill

    root = Path.cwd()
    continuum_dir = root / CONTINUUM_DIR

    if not continuum_dir.exists():
        click.echo("No .continuum/ directory found. Run 'continuum init' first.")
        raise SystemExit(1)

    create_skill(name, continuum_dir)
