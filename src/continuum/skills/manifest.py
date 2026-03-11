"""Skill manifest — dataclass loaded from skill.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Skill:
    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    triggers: list[str] = field(default_factory=lambda: ["manual"])
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    entrypoint: str = "prompt.md"  # relative to skill dir


def load_skill(skill_dir: Path) -> Skill:
    """Load a Skill from a directory containing skill.yaml."""
    yaml_path = skill_dir / "skill.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No skill.yaml in {skill_dir}")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return Skill(**{k: v for k, v in data.items() if k in Skill.__dataclass_fields__})


def discover_skills(continuum_dir: Path) -> list[tuple[Path, Skill]]:
    """Find all skills in core/ and local/ dirs.

    Args:
        continuum_dir: Path to the .continuum directory.

    Returns:
        List of (skill_dir, Skill) tuples, sorted by directory name.
    """
    results: list[tuple[Path, Skill]] = []
    for subdir in ["skills/core", "skills/local"]:
        base = continuum_dir / subdir
        if not base.exists():
            continue
        for skill_dir in sorted(base.iterdir()):
            if skill_dir.is_dir() and (skill_dir / "skill.yaml").exists():
                try:
                    results.append((skill_dir, load_skill(skill_dir)))
                except Exception:
                    pass
    return results
