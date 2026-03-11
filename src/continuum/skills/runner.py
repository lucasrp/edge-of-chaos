"""Skill runner — execute skills and log runs."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

from continuum.config import CONTINUUM_DIR
from continuum.skills.manifest import Skill, discover_skills


def _find_skill(skill_id: str, root: Path) -> tuple[Path, Skill] | None:
    """Find a skill by its ID in core/ and local/ directories."""
    continuum_dir = root / CONTINUUM_DIR
    for skill_dir, skill in discover_skills(continuum_dir):
        if skill.id == skill_id:
            return skill_dir, skill
    return None


def _create_run_dir(skill_id: str, root: Path) -> Path:
    """Create a timestamped run directory under .continuum/runtime/runs/."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / CONTINUUM_DIR / "runtime" / "runs" / f"{timestamp}_{skill_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_manifest(run_dir: Path, skill: Skill, skill_dir: Path) -> None:
    """Write manifest.json for a run."""
    data = {
        "skill_id": skill.id,
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "entrypoint": skill.entrypoint,
        "skill_dir": str(skill_dir),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def _write_status(run_dir: Path, status: str, exit_code: int = 0, error: str = "") -> None:
    """Write status.json for a run."""
    data = {
        "status": status,
        "exit_code": exit_code,
        "error": error,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "status.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def run_skill(skill_id: str, root: Path | None = None) -> bool:
    """Find and execute a skill by ID.

    For prompt.md-based skills, attempts to shell out to
    ``claude -p <prompt_content> --max-turns 15``.  If the ``claude``
    CLI is not available, falls back to printing the prompt.

    Each run is logged to .continuum/runtime/runs/<timestamp>_<skill-id>/
    with manifest.json, output.txt, and status.json.

    Args:
        skill_id: The skill identifier to run.
        root: Project root (default: cwd).

    Returns:
        True if the skill completed successfully, False otherwise.
    """
    if root is None:
        root = Path.cwd()

    result = _find_skill(skill_id, root)
    if result is None:
        click.echo(f"Error: skill '{skill_id}' not found.")
        click.echo("Run 'continuum skills list' to see available skills.")
        return False

    skill_dir, skill = result
    prompt_path = skill_dir / skill.entrypoint

    if not prompt_path.exists():
        click.echo(f"Error: entrypoint '{skill.entrypoint}' not found in {skill_dir}")
        return False

    prompt_content = prompt_path.read_text(encoding="utf-8")

    # Create run directory
    run_dir = _create_run_dir(skill_id, root)
    _write_manifest(run_dir, skill, skill_dir)

    click.echo(f"Running skill: {skill.name} ({skill.id})")
    click.echo(f"  Version: {skill.version}")
    click.echo(f"  Run dir: {run_dir.relative_to(root)}")
    click.echo()

    # Try to shell out to claude CLI
    claude_bin = shutil.which("claude")
    if claude_bin:
        click.echo("Executing via claude CLI...")
        try:
            proc = subprocess.run(
                [claude_bin, "-p", prompt_content, "--max-turns", "15"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(root),
            )
            output = proc.stdout + proc.stderr
            (run_dir / "output.txt").write_text(output, encoding="utf-8")

            if proc.returncode == 0:
                _write_status(run_dir, "success", exit_code=0)
                click.echo(output)
                click.echo(f"\nSkill completed successfully.")
                return True
            else:
                _write_status(run_dir, "failed", exit_code=proc.returncode, error=proc.stderr)
                click.echo(output)
                click.echo(f"\nSkill failed with exit code {proc.returncode}.")
                return False

        except subprocess.TimeoutExpired:
            _write_status(run_dir, "timeout", exit_code=-1, error="Timed out after 600s")
            click.echo("Error: skill execution timed out after 600 seconds.")
            return False
        except Exception as e:
            _write_status(run_dir, "error", exit_code=-1, error=str(e))
            click.echo(f"Error running skill: {e}")
            return False
    else:
        # claude CLI not available — print the prompt as fallback
        click.echo("claude CLI not found — printing prompt content:\n")
        click.echo("─" * 60)
        click.echo(prompt_content)
        click.echo("─" * 60)

        (run_dir / "output.txt").write_text(
            "[claude CLI not available — prompt printed to stdout]\n\n" + prompt_content,
            encoding="utf-8",
        )
        _write_status(run_dir, "fallback", exit_code=0, error="claude CLI not available")
        return True
