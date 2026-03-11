"""Continuum doctor — health checks for the installation."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from edge_of_chaos.config import CONTINUUM_DIR, CONFIG_PATH

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[import,no-redef]


def _check(label: str, ok: bool) -> bool:
    """Print a PASS/FAIL line and return the boolean."""
    if ok:
        click.echo(click.style("  PASS", fg="green") + f"  {label}")
    else:
        click.echo(click.style("  FAIL", fg="red") + f"  {label}")
    return ok


def run_doctor(root: Path | None = None) -> int:
    """Run all health checks. Returns 0 if all pass, 1 if any fail."""
    if root is None:
        root = Path.cwd()

    click.echo("Continuum doctor\n")

    all_ok = True

    # 1. .continuum/ directory exists
    continuum_dir = root / CONTINUUM_DIR
    if not _check(".continuum/ directory exists", continuum_dir.is_dir()):
        all_ok = False

    # 2. continuum.toml exists and is valid TOML
    config_file = root / CONFIG_PATH
    toml_exists = config_file.is_file()
    if not _check("continuum.toml exists", toml_exists):
        all_ok = False
        toml_valid = False
    else:
        try:
            tomllib.loads(config_file.read_text(encoding="utf-8"))
            toml_valid = True
        except Exception:
            toml_valid = False
        if not _check("continuum.toml is valid TOML", toml_valid):
            all_ok = False

    # 3. Memory directories exist
    memory_dirs = ["memory/bootstrap", "memory/working", "memory/consolidated"]
    for md in memory_dirs:
        path = continuum_dir / md
        if not _check(f"{md}/ exists", path.is_dir()):
            all_ok = False

    # 4. Skills directories exist
    skills_dirs = ["skills/core", "skills/local"]
    for sd in skills_dirs:
        path = continuum_dir / sd
        if not _check(f"{sd}/ exists", path.is_dir()):
            all_ok = False

    # 5. At least one skill is installed
    skill_count = 0
    for skills_dir_name in ["skills/core", "skills/local"]:
        skills_path = continuum_dir / skills_dir_name
        if skills_path.is_dir():
            for child in skills_path.iterdir():
                if child.is_dir() and (child / "skill.yaml").is_file():
                    skill_count += 1
    if not _check(f"At least one skill installed ({skill_count} found)", skill_count > 0):
        all_ok = False

    # 6. claude CLI is available in PATH
    claude_found = shutil.which("claude") is not None
    if not _check("claude CLI available in PATH", claude_found):
        all_ok = False

    # Summary
    click.echo()
    if all_ok:
        click.echo(click.style("All checks passed.", fg="green"))
    else:
        click.echo(click.style("Some checks failed.", fg="red"))

    return 0 if all_ok else 1
