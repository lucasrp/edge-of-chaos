"""Continuum CLI — click-based command interface."""

import click

from continuum import __version__


@click.group()
@click.version_option(version=__version__, prog_name="continuum")
def main():
    """Continuum — local-first runtime for Claude Code.

    Persistent memory, autonomous routines, and intelligent bootstrap
    via transcript scanning.
    """


@main.command()
def init():
    """Initialize continuum in the current directory."""
    from continuum.init import run_init

    run_init()


@main.command()
@click.option("--sanitization", type=click.Choice(["strict", "balanced", "raw"]), default="balanced", help="Sanitization mode.")
@click.option("--max-sessions", type=int, default=200, help="Max sessions to process.")
@click.option("--dry-run", is_flag=True, help="Show what would be extracted without writing.")
def scan(sanitization, max_sessions, dry_run):
    """Scan Claude Code transcripts and create bootstrap memory."""
    click.echo("Not implemented yet.")


@main.command()
@click.argument("skill_id")
def run(skill_id):
    """Run a skill by ID."""
    click.echo("Not implemented yet.")


@main.command()
def status():
    """Show current continuum status."""
    click.echo("Not implemented yet.")


@main.command()
def doctor():
    """Check continuum installation health."""
    click.echo("Not implemented yet.")


@main.group()
def skills():
    """Manage continuum skills."""


@skills.command("list")
def skills_list():
    """List available skills."""
    click.echo("Not implemented yet.")


@skills.command("new")
@click.argument("name")
def skills_new(name):
    """Create a new skill scaffold."""
    click.echo("Not implemented yet.")
