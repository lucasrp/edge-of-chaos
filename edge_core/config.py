from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    agent: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.agent.get("name") or "edge")

    @property
    def codename(self) -> str:
        return str(self.agent.get("codename") or self.name)

    @property
    def language(self) -> str:
        return str(self.agent.get("language") or "pt-BR")

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def blog_entries_dir(self) -> Path:
        return self.root / "blog" / "entries"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def threads_dir(self) -> Path:
        return self.state_dir / "threads"

    @property
    def digests_dir(self) -> Path:
        return self.state_dir / "digests"

    @property
    def ledger_path(self) -> Path:
        return self.state_dir / "events.jsonl"


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "tools" / "edge").exists() or (candidate / ".git").exists():
            return candidate
    return current


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:  # pragma: no cover
        raise RuntimeError(f"PyYAML is required to read {path}: {YAML_IMPORT_ERROR}")
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_config(root: Path | None = None) -> RuntimeConfig:
    root = repo_root(root)
    config_path = root / "agent.yaml"
    if not config_path.exists():
        config_path = root / "agent.yaml.example"
    return RuntimeConfig(root=root, agent=load_yaml(config_path))


def ensure_runtime_dirs(config: RuntimeConfig) -> None:
    for path in [
        config.state_dir,
        config.threads_dir,
        config.digests_dir,
        config.reports_dir,
        config.blog_entries_dir,
        config.root / "logs",
        config.root / "config",
    ]:
        path.mkdir(parents=True, exist_ok=True)
