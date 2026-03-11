"""Continuum configuration — load/save continuum.toml."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[import,no-redef]

CONTINUUM_DIR = ".continuum"
CONFIG_PATH = f"{CONTINUUM_DIR}/config/continuum.toml"


@dataclass
class ProjectConfig:
    name: str = ""
    domain: str = ""
    language: str = "en"


@dataclass
class ScannerConfig:
    enabled: bool = True
    sanitization: str = "balanced"  # strict | balanced | raw


@dataclass
class SkillsConfig:
    prefix: str = "cx"


@dataclass
class SchedulerConfig:
    enabled: bool = False


@dataclass
class Config:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)


def _merge_section(dc: Any, data: dict) -> None:
    """Update a dataclass instance from a dict, ignoring unknown keys."""
    for f in fields(dc):
        if f.name in data:
            setattr(dc, f.name, data[f.name])


def load_config(root: Path | None = None) -> Config:
    """Load config from .continuum/config/continuum.toml.

    Falls back to defaults for any missing field or missing file.
    """
    if root is None:
        root = Path.cwd()

    config_file = root / CONFIG_PATH

    cfg = Config()

    if config_file.exists():
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
        if "project" in raw:
            _merge_section(cfg.project, raw["project"])
        if "scanner" in raw:
            _merge_section(cfg.scanner, raw["scanner"])
        if "skills" in raw:
            _merge_section(cfg.skills, raw["skills"])
        if "scheduler" in raw:
            _merge_section(cfg.scheduler, raw["scheduler"])

    return cfg


def generate_toml(cfg: Config) -> str:
    """Serialize a Config to TOML string (manual, no heavy deps)."""
    lines = [
        "[project]",
        f'name = "{cfg.project.name}"',
        f'domain = "{cfg.project.domain}"',
        f'language = "{cfg.project.language}"',
        "",
        "[scanner]",
        f"enabled = {'true' if cfg.scanner.enabled else 'false'}",
        f'sanitization = "{cfg.scanner.sanitization}"',
        "",
        "[skills]",
        f'prefix = "{cfg.skills.prefix}"',
        "",
        "[scheduler]",
        f"enabled = {'true' if cfg.scheduler.enabled else 'false'}",
    ]
    return "\n".join(lines) + "\n"


def save_config(cfg: Config, root: Path | None = None) -> Path:
    """Write config to .continuum/config/continuum.toml. Returns path written."""
    if root is None:
        root = Path.cwd()

    config_file = root / CONFIG_PATH
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(generate_toml(cfg), encoding="utf-8")
    return config_file
