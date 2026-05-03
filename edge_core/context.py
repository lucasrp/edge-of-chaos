from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .ledger import Ledger
from .util import truncate


@dataclass
class Observation:
    source: str
    title: str
    detail: str
    path: str | None = None


@dataclass
class ContextPacket:
    request: str
    kind: str
    observations: list[Observation] = field(default_factory=list)
    delta_source_manifest: list[dict[str, Any]] = field(default_factory=list)
    search_source_manifest: list[dict[str, Any]] = field(default_factory=list)
    thread_candidates: list[dict[str, Any]] = field(default_factory=list)
    report_candidates: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    first_steps: list[str] = field(default_factory=list)
    seed_threads: list[dict[str, Any]] = field(default_factory=list)
    interests: list[dict[str, Any]] = field(default_factory=list)
    routines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "kind": self.kind,
            "observations": [obs.__dict__ for obs in self.observations],
            "delta_source_manifest": self.delta_source_manifest,
            "search_source_manifest": self.search_source_manifest,
            "thread_candidates": self.thread_candidates,
            "report_candidates": self.report_candidates,
            "recent_events": self.recent_events,
            "first_steps": self.first_steps,
            "seed_threads": self.seed_threads,
            "interests": self.interests,
            "routines": self.routines,
        }


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return result.returncode, (result.stdout or result.stderr or "").strip()


def _workspace_path(root: Path, raw: str) -> Path:
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def build_delta_source_manifest(config: RuntimeConfig) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = [{"name": "request", "kind": "runtime", "enabled": True, "available": True}]
    for item in config.agent.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        path = _workspace_path(config.root, str(item.get("path") or "."))
        manifest.append(
            {
                "name": str(item.get("name") or item.get("path") or "workspace"),
                "kind": str(item.get("kind") or "workspace"),
                "enabled": True,
                "available": path.exists(),
                "path": str(path),
            }
        )
    claude_settings = ((config.agent.get("context") or {}).get("claude_sessions") or {})
    claude_base = Path.home() / ".claude" / "projects"
    manifest.append(
        {
            "name": "claude_sessions",
            "kind": "genotypic_context",
            "enabled": claude_settings.get("enabled", True) is not False,
            "available": claude_base.exists(),
            "path": str(claude_base),
        }
    )
    manifest.extend(
        [
            {"name": "threads", "kind": "state_projection", "enabled": True, "available": config.threads_dir.exists(), "path": str(config.threads_dir)},
            {"name": "reports", "kind": "state_projection", "enabled": True, "available": config.reports_dir.exists(), "path": str(config.reports_dir)},
            {"name": "events", "kind": "ledger", "enabled": True, "available": config.ledger_path.exists(), "path": str(config.ledger_path)},
            {"name": "first_steps", "kind": "phenotype", "enabled": True, "available": bool(config.agent.get("first_steps"))},
            {"name": "seed_threads", "kind": "phenotype", "enabled": True, "available": bool(config.agent.get("seed_threads"))},
            {"name": "interests", "kind": "phenotype", "enabled": True, "available": bool(config.agent.get("interests"))},
        ]
    )
    return manifest


def build_search_source_manifest(config: RuntimeConfig) -> list[dict[str, Any]]:
    credential_env = {
        "exa": "EXA_API_KEY",
        "x": "X_BEARER_TOKEN",
        "github": None,
        "hackernews": None,
    }
    configured = config.agent.get("sources") or []
    manifest: list[dict[str, Any]] = []
    for item in configured:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        env_key = credential_env.get(name)
        available = True if env_key is None else bool(os.environ.get(env_key))
        manifest.append(
            {
                "name": name,
                "kind": str(item.get("kind") or "search"),
                "enabled": item.get("enabled", True) is not False,
                "available": available,
                "credential": "not_required" if env_key is None else ("configured" if available else "missing"),
            }
        )
    return manifest


def load_workspace_observations(config: RuntimeConfig) -> list[Observation]:
    observations: list[Observation] = []
    for item in config.agent.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("path") or "workspace")
        path = _workspace_path(config.root, str(item.get("path") or "."))
        if not path.exists():
            observations.append(Observation("workspace", name, "configured path does not exist", str(path)))
            continue
        if (path / ".git").exists():
            code, status = _run(["git", "status", "--short"], path)
            if code == 0 and status:
                observations.append(Observation("git", f"{name}: working tree changes", truncate(status, 1200), str(path)))
            code, log = _run(["git", "log", "--oneline", "--max-count=5"], path)
            if code == 0 and log:
                observations.append(Observation("git", f"{name}: recent commits", truncate(log, 1200), str(path)))
        recent_files: list[str] = []
        try:
            files = [p for p in path.rglob("*") if p.is_file() and ".git" not in p.parts]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            recent_files = [str(p.relative_to(path)) for p in files[:8]]
        except OSError:
            recent_files = []
        if recent_files:
            observations.append(Observation("filesystem", f"{name}: recent files", "\n".join(recent_files), str(path)))
    return observations


def load_claude_sessions(config: RuntimeConfig) -> list[Observation]:
    settings = ((config.agent.get("context") or {}).get("claude_sessions") or {})
    if settings.get("enabled", True) is False:
        return []
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    max_files = int(settings.get("max_files") or 6)
    try:
        files = [p for p in base.rglob("*") if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    observations: list[Observation] = []
    for path in files[:max_files]:
        try:
            snippet = truncate(path.read_text(encoding="utf-8", errors="ignore"), 500)
        except OSError:
            snippet = ""
        observations.append(Observation("claude_session", path.name, snippet, str(path)))
    return observations


def load_threads(config: RuntimeConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not config.threads_dir.exists():
        return candidates
    for path in sorted(config.threads_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        candidates.append({"id": path.stem, "path": str(path), "summary": truncate(text, 1000)})
    return candidates


def load_reports(config: RuntimeConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    paths = list(config.reports_dir.glob("*.md")) if config.reports_dir.exists() else []
    paths += list(config.blog_entries_dir.glob("*.md")) if config.blog_entries_dir.exists() else []
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths[:12]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
        candidates.append({"title": title, "path": str(path), "summary": truncate(text, 900)})
    return candidates


def assemble_context(config: RuntimeConfig, ledger: Ledger, *, kind: str, request: str) -> ContextPacket:
    observations = []
    observations.append(Observation("request", "current request", request or f"autonomous {kind} beat"))
    observations.extend(load_workspace_observations(config))
    observations.extend(load_claude_sessions(config))
    return ContextPacket(
        request=request or f"Run a {kind} beat",
        kind=kind,
        observations=observations,
        delta_source_manifest=build_delta_source_manifest(config),
        search_source_manifest=build_search_source_manifest(config),
        thread_candidates=load_threads(config),
        report_candidates=load_reports(config),
        recent_events=ledger.read_recent(25),
        first_steps=[str(item) for item in (config.agent.get("first_steps") or [])],
        seed_threads=[item for item in (config.agent.get("seed_threads") or []) if isinstance(item, dict)],
        interests=[item for item in (config.agent.get("interests") or []) if isinstance(item, dict)],
        routines=[str(item) for item in (config.agent.get("routines") or [])],
    )
