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
    authoritative_reads: list[dict[str, Any]] = field(default_factory=list)
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
            "authoritative_reads": self.authoritative_reads,
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


def _is_noise_path(path: Path) -> bool:
    noise_parts = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
    if any(part in noise_parts for part in path.parts):
        return True
    if path.suffix in {".pyc", ".pyo", ".sqlite", ".db", ".png", ".jpg", ".jpeg", ".gif", ".zip"}:
        return True
    return False


def _is_context_file(path: Path) -> bool:
    return path.suffix.lower() in {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh"}


def _read_snippet(path: Path, limit: int = 900) -> str:
    try:
        return truncate(path.read_text(encoding="utf-8", errors="ignore"), limit)
    except OSError:
        return ""


def _recent_files(directory: Path, pattern: str, limit: int) -> list[Path]:
    if not directory.exists():
        return []
    paths = list(directory.glob(pattern))
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:limit]


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
    thread_files = _recent_files(config.threads_dir, "*.md", 12)
    report_files = _recent_files(config.reports_dir, "*.md", 12)
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
            {"name": "chat_digest", "kind": "genotypic_context_projection", "enabled": True, "available": config.chat_digest_path.exists(), "path": str(config.chat_digest_path)},
            {
                "name": "threads",
                "kind": "state_projection",
                "enabled": True,
                "available": bool(thread_files),
                "item_count": len(thread_files),
                "path": str(config.threads_dir),
                "sample_paths": [str(path.name) for path in thread_files[:3]],
            },
            {
                "name": "reports",
                "kind": "state_projection",
                "enabled": True,
                "available": bool(report_files),
                "item_count": len(report_files),
                "path": str(config.reports_dir),
                "sample_paths": [str(path.name) for path in report_files[:3]],
            },
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
    workspace_available = False
    for item in config.agent.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        path = _workspace_path(config.root, str(item.get("path") or "."))
        if path.exists():
            workspace_available = True
            break
    manifest.append(
        {
            "name": "workspace-search",
            "kind": "search",
            "enabled": workspace_available,
            "available": workspace_available,
            "credential": "not_required",
        }
    )
    for item in configured:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        env_key = credential_env.get(name)
        available = True if env_key is None else bool(os.environ.get(env_key))
        credential = "not_required" if env_key is None else ("configured" if available else "missing")
        if name == "x" and not available and os.environ.get("XAI_API_KEY"):
            credential = "missing_x_bearer_token_xai_key_present"
        manifest.append(
            {
                "name": name,
                "kind": str(item.get("kind") or "search"),
                "enabled": item.get("enabled", True) is not False,
                "available": available,
                "credential": credential,
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
            code, stat = _run(["git", "diff", "--stat", "HEAD~5..HEAD"], path)
            if code == 0 and stat:
                observations.append(Observation("git", f"{name}: recent commit diff stat", truncate(stat, 1200), str(path)))
            code, changed = _run(["git", "diff", "--name-only", "HEAD~5..HEAD"], path)
            changed_files = [line.strip() for line in changed.splitlines() if line.strip()] if code == 0 else []
        else:
            changed_files = []
        recent_files: list[str] = []
        try:
            files = [p for p in path.rglob("*") if p.is_file() and not _is_noise_path(p)]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            recent_files = [str(p.relative_to(path)) for p in files[:8]]
        except OSError:
            recent_files = []
        if recent_files:
            observations.append(Observation("filesystem", f"{name}: recent files", "\n".join(recent_files), str(path)))
        snippets = []
        snippet_candidates = []
        for relative in [*changed_files, *recent_files]:
            if relative not in snippet_candidates:
                snippet_candidates.append(relative)
        for relative in snippet_candidates:
            candidate = path / relative
            if _is_context_file(candidate):
                snippet = _read_snippet(candidate)
                if snippet:
                    snippets.append(f"## {relative}\n{snippet}")
            if len(snippets) >= 5:
                break
        if snippets:
            observations.append(Observation("filesystem", f"{name}: recent file snippets", "\n\n".join(snippets), str(path)))
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


def load_chat_digest(config: RuntimeConfig) -> list[Observation]:
    if not config.chat_digest_path.exists():
        return []
    snippet = _read_snippet(config.chat_digest_path, limit=2400)
    if not snippet:
        return []
    return [Observation("chat_digest", "Claude chat digest", snippet, str(config.chat_digest_path))]


def load_threads(config: RuntimeConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not config.threads_dir.exists():
        return candidates
    for path in _recent_files(config.threads_dir, "*.md", 12):
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), path.stem.replace("-", " ").title())
        candidates.append({"id": path.stem, "title": title, "path": str(path), "summary": truncate(text, 1000)})
    return candidates


def load_reports(config: RuntimeConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    paths = _recent_files(config.reports_dir, "*.md", 12)
    paths += _recent_files(config.reports_dir, "*.yaml", 12)
    paths += _recent_files(config.blog_entries_dir, "*.md", 12)
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths[:12]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), "")
        if not title:
            title = next((line.split(":", 1)[1].strip().strip("'\"") for line in text.splitlines() if line.startswith("title:")), path.stem)
        candidates.append({"title": title, "path": str(path), "summary": truncate(text, 900)})
    return candidates


def load_authoritative_reads(config: RuntimeConfig, ledger: Ledger) -> list[dict[str, Any]]:
    reads: list[dict[str, Any]] = []
    for path in _recent_files(config.threads_dir, "*.md", 4):
        reads.append(
            {
                "source": "thread",
                "path": str(path),
                "title": path.stem,
                "excerpt": _read_snippet(path, limit=1200),
            }
        )
    for path in _recent_files(config.reports_dir, "*.md", 4):
        reads.append(
            {
                "source": "report",
                "path": str(path),
                "title": path.stem,
                "excerpt": _read_snippet(path, limit=1000),
            }
        )
    for path in _recent_files(config.reports_dir, "*.yaml", 4):
        reads.append(
            {
                "source": "report_spec",
                "path": str(path),
                "title": path.stem,
                "excerpt": _read_snippet(path, limit=1000),
            }
        )
    if config.ledger_path.exists():
        recent = ledger.read_recent(20)
        if recent:
            reads.append(
                {
                    "source": "events",
                    "path": str(config.ledger_path),
                    "title": "recent events",
                    "excerpt": truncate("\n".join(str(item) for item in recent), 1200),
                }
            )
    if config.chat_digest_cursor_path.exists():
        reads.append(
            {
                "source": "chat_digest_cursor",
                "path": str(config.chat_digest_cursor_path),
                "title": "chat digest cursor",
                "excerpt": _read_snippet(config.chat_digest_cursor_path, limit=400),
            }
        )
    return reads


def assemble_context(config: RuntimeConfig, ledger: Ledger, *, kind: str, request: str) -> ContextPacket:
    observations = []
    observations.append(Observation("request", "current request", request or f"autonomous {kind} beat"))
    observations.extend(load_workspace_observations(config))
    observations.extend(load_chat_digest(config))
    return ContextPacket(
        request=request or f"Run a {kind} beat",
        kind=kind,
        observations=observations,
        authoritative_reads=load_authoritative_reads(config, ledger),
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
