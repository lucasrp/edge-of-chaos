"""Continuum status — show current state of the installation."""

from __future__ import annotations

import datetime
from pathlib import Path

import click

from edge_of_chaos.config import CONTINUUM_DIR


def _count_files(directory: Path) -> int:
    """Count files (non-directory) in a directory, non-recursively."""
    if not directory.is_dir():
        return 0
    return sum(1 for f in directory.iterdir() if f.is_file())


def _last_modified(directory: Path) -> str:
    """Return the last modified date of any file in the directory, or 'n/a'."""
    if not directory.is_dir():
        return "n/a"
    latest = None
    for f in directory.iterdir():
        if f.is_file():
            mtime = f.stat().st_mtime
            if latest is None or mtime > latest:
                latest = mtime
    if latest is None:
        return "n/a"
    return datetime.datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M")


def _list_skills(skills_dir: Path) -> list[str]:
    """List skill names (directories containing skill.yaml) under a dir."""
    if not skills_dir.is_dir():
        return []
    names = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "skill.yaml").is_file():
            names.append(child.name)
    return names


def _format_run_dir(run_dir: Path) -> str | None:
    """Format a run directory entry as 'skill_name  status  timestamp'.

    Expects run dirs named like: 2026-03-11T10-30-00_skill-name
    or containing a status file / metadata.
    """
    if not run_dir.is_dir():
        return None

    # Try to extract skill name and timestamp from directory name
    name = run_dir.name

    # Check for a status file
    status = "unknown"
    status_file = run_dir / "status"
    if status_file.is_file():
        status = status_file.read_text(encoding="utf-8").strip() or "unknown"
    elif (run_dir / "result.md").is_file():
        status = "completed"

    # Use dir modification time as timestamp
    mtime = datetime.datetime.fromtimestamp(run_dir.stat().st_mtime)
    timestamp = mtime.strftime("%Y-%m-%d %H:%M")

    return f"  {name:<40s} {status:<12s} {timestamp}"


def run_status(root: Path | None = None) -> None:
    """Show current continuum status."""
    if root is None:
        root = Path.cwd()

    continuum_dir = root / CONTINUUM_DIR

    if not continuum_dir.is_dir():
        click.echo("Edge of Chaos is not initialized in this directory.")
        click.echo("Run `continuum init` to get started.")
        return

    click.echo("Continuum status\n")

    # --- Memory stats ---
    click.echo(click.style("Memory:", bold=True))
    memory_layers = ["bootstrap", "working", "consolidated"]
    for layer in memory_layers:
        layer_dir = continuum_dir / "memory" / layer
        count = _count_files(layer_dir)
        modified = _last_modified(layer_dir)
        click.echo(f"  {layer:<16s} {count:>3d} files   last modified: {modified}")

    click.echo()

    # --- Bootstrap status ---
    click.echo(click.style("Bootstrap:", bold=True))
    bootstrap_dir = continuum_dir / "memory" / "bootstrap"
    if _count_files(bootstrap_dir) > 0:
        click.echo("  scanned")
    else:
        click.echo("  not scanned")

    click.echo()

    # --- Skills available ---
    click.echo(click.style("Skills:", bold=True))
    core_skills = _list_skills(continuum_dir / "skills" / "core")
    local_skills = _list_skills(continuum_dir / "skills" / "local")

    if core_skills:
        click.echo("  core:")
        for s in core_skills:
            click.echo(f"    - {s}")
    else:
        click.echo("  core:  (none)")

    if local_skills:
        click.echo("  local:")
        for s in local_skills:
            click.echo(f"    - {s}")
    else:
        click.echo("  local: (none)")

    click.echo()

    # --- Last 5 runs ---
    click.echo(click.style("Recent runs:", bold=True))
    runs_dir = continuum_dir / "runtime" / "runs"
    if not runs_dir.is_dir():
        click.echo("  (no runs directory)")
        return

    run_dirs = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )[:5]

    if not run_dirs:
        click.echo("  (no runs yet)")
    else:
        for rd in run_dirs:
            line = _format_run_dir(rd)
            if line:
                click.echo(line)
