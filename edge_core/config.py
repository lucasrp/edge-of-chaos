from __future__ import annotations

from dataclasses import dataclass
import os
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
        return str(self.agent.get("language") or "en-US")

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def blog_entries_dir(self) -> Path:
        return self.root / "blog" / "entries"

    @property
    def blog_reports_dir(self) -> Path:
        return self.root / "blog" / "reports"

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

    @property
    def chat_digest_path(self) -> Path:
        return self.state_dir / "chat-digest.md"

    @property
    def chat_digest_cursor_path(self) -> Path:
        return self.state_dir / "chat-digest-cursor.json"


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


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_local_env(root: Path) -> None:
    if os.environ.get("EDGE_DISABLE_LOCAL_ENV") == "1":
        return
    candidates = [
        root / ".env",
        root / "secrets" / "keys.env",
        Path.home() / "edge" / "secrets" / "openai.env",
        Path.home() / "edge" / "secrets" / "xai.env",
        Path.home() / "edge" / "secrets" / "exa.env",
        Path.home() / "edge" / "secrets" / "x-api.env",
        Path.home() / "edge" / "secrets" / "keys.env",
        root.parent / "keys" / "openai.env",
        root.parent / "keys" / "xai.env",
        root.parent / "keys" / "exa.env",
        root.parent / "keys" / "keys.env",
        root / ".env.defaults",
    ]
    for path in candidates:
        _load_env_file(path)


def load_config(root: Path | None = None) -> RuntimeConfig:
    root = repo_root(root)
    load_local_env(root)
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
        config.blog_reports_dir,
        config.root / "logs",
        config.root / "config",
    ]:
        path.mkdir(parents=True, exist_ok=True)
