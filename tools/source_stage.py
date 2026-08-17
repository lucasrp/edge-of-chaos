"""Deterministic, credential-free source staging primitives.

This module has no CLI, network or service integration.  It plans an explicit filesystem
allowlist from caller-selected roots and can materialize that plan into an atomic, hashed snapshot.
Live-source selection and system provisioning remain separate operator-gated work packages.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
from typing import Any, Callable


PLAN_SCHEMA = "edge.source-stage-plan/v1"
MANIFEST_SCHEMA = "edge.source-stage-manifest/v1"
GENERATED_DIRS = frozenset({
    ".cache", ".git", ".mypy_cache", ".obsidian", ".pytest_cache", ".ruff_cache",
    ".tox", ".venv", "__pycache__", "build", "dist", "node_modules", "venv",
})
GENERATED_FILES = frozenset({".ds_store", "desktop.ini"})
ALLOWED_SUFFIXES = frozenset({
    ".css", ".docx", ".html", ".in", ".js", ".json", ".md", ".pdf",
    ".png", ".py", ".sh", ".sha256", ".toml", ".txt", ".vbs", ".yaml", ".yml",
})
ALLOWED_EXACT_FILES = frozenset({
    ".dockerignore", ".gitignore", "cargo.lock", "composer.lock", "dockerfile",
    "pipfile.lock", "poetry.lock", "uv.lock", "yarn.lock",
})
SECRET_EXACT = frozenset({
    ".env", ".env.local", ".env.production", "auth.json", "credentials.json",
    "id_ed25519", "id_rsa", "secrets.json",
})
SECRET_MARKERS = ("credential", "secret", "token")
RUNTIME_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".pid", ".log")
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
MAX_FILES = 100_000
MAX_BYTES = 2 * 1024 * 1024 * 1024


class SourceStageError(RuntimeError):
    """A source snapshot could not be planned or built safely."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _secret_like(name: str) -> bool:
    lowered = name.lower()
    return (lowered in SECRET_EXACT or lowered.startswith(".env.")
            or any(marker in lowered for marker in SECRET_MARKERS))


def _runtime_like(name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith(".lock") and lowered not in ALLOWED_EXACT_FILES:
        return True
    if lowered.endswith(RUNTIME_SUFFIXES):
        return True
    return any(
        lowered.endswith(database_suffix + sidecar)
        for database_suffix in (".db", ".sqlite", ".sqlite3")
        for sidecar in SQLITE_SIDECARS
    )


def _generated_directory(name: str) -> bool:
    return name in GENERATED_DIRS or name.lower().startswith(".tmp.")


def _safe_name(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise SourceStageError("source name must be a stable lowercase identifier")
    return value


def _absolute_directory(value: Any, *, label: str, require_exists: bool = True) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise SourceStageError(f"{label} must be a non-empty absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise SourceStageError(f"{label} must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise SourceStageError(f"{label} may not contain a symlink")
    resolved = path.resolve(strict=False)
    if require_exists and not resolved.is_dir():
        raise SourceStageError(f"{label} must be an existing directory")
    return resolved


def _overlap(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _open_directory_chain(path: Path) -> int:
    if not path.is_absolute():
        raise SourceStageError("source directory must be absolute")
    path_only = getattr(os, "O_PATH", os.O_RDONLY)
    current = os.open("/", path_only | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(
                part,
                path_only | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _open_source_nofollow(path: Path) -> int:
    parent_fd = _open_directory_chain(path.parent)
    try:
        return os.open(
            path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd
        )
    finally:
        os.close(parent_fd)


def build_stage_plan(
    sources: list[dict[str, Any]],
    *,
    stage_root: str | os.PathLike[str],
    max_files: int = MAX_FILES,
    max_bytes: int = MAX_BYTES,
) -> dict[str, Any]:
    """Plan an allowlisted snapshot without reading regular-file content."""
    if not isinstance(sources, list) or not sources:
        raise SourceStageError("at least one source is required")
    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
        raise SourceStageError("max_files must be a positive integer")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise SourceStageError("max_bytes must be a positive integer")
    destination = _absolute_directory(stage_root, label="stage_root", require_exists=False)

    normalized: list[tuple[str, Path]] = []
    names: set[str] = set()
    for row in sources:
        if not isinstance(row, dict):
            raise SourceStageError("each source must be a mapping")
        name = _safe_name(row.get("name"))
        root = _absolute_directory(row.get("path"), label=f"source {name}")
        if name in names or any(_overlap(root, existing) for _, existing in normalized):
            raise SourceStageError("source names and roots must be unique and non-overlapping")
        if _overlap(root, destination):
            raise SourceStageError("stage_root may not overlap a source")
        names.add(name)
        normalized.append((name, root))

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    total_bytes = 0
    for name, root in sorted(normalized):
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_dirs = []
            for dirname in sorted(dirs):
                candidate = current_path / dirname
                rel = candidate.relative_to(root).as_posix()
                if candidate.is_symlink():
                    raise SourceStageError(f"symlink rejected in source {name}: {rel}")
                if _generated_directory(dirname):
                    excluded.append({"source": name, "relative_path": rel,
                                     "reason": "generated-directory"})
                else:
                    kept_dirs.append(dirname)
            dirs[:] = kept_dirs
            for filename in sorted(files):
                candidate = current_path / filename
                rel = candidate.relative_to(root).as_posix()
                st = candidate.lstat()
                if stat.S_ISLNK(st.st_mode):
                    raise SourceStageError(f"symlink rejected in source {name}: {rel}")
                if not stat.S_ISREG(st.st_mode):
                    raise SourceStageError(f"non-regular file rejected in source {name}: {rel}")
                if st.st_nlink != 1:
                    raise SourceStageError(f"hard-linked file rejected in source {name}: {rel}")
                if _secret_like(filename):
                    excluded.append({"source": name, "relative_path": rel,
                                     "reason": "secret-like-name"})
                    continue
                if filename.lower() in GENERATED_FILES:
                    excluded.append({"source": name, "relative_path": rel,
                                     "reason": "generated-file"})
                    continue
                if _runtime_like(filename):
                    excluded.append({"source": name, "relative_path": rel,
                                     "reason": "runtime-artifact"})
                    continue
                suffix = candidate.suffix.lower()
                if not (suffix in ALLOWED_SUFFIXES or filename.lower() in ALLOWED_EXACT_FILES):
                    excluded.append({"source": name, "relative_path": rel,
                                     "reason": "unsupported-file-type"})
                    continue
                included.append({
                    "source": name, "relative_path": rel, "size": st.st_size,
                    "mtime_ns": st.st_mtime_ns, "device": st.st_dev, "inode": st.st_ino,
                })
                total_bytes += st.st_size
                if len(included) > max_files or total_bytes > max_bytes:
                    raise SourceStageError("planned snapshot exceeds its explicit bound")

    plan = {
        "schema": PLAN_SCHEMA,
        "sources": [{"name": name, "path": str(root)} for name, root in sorted(normalized)],
        "included": sorted(included, key=lambda row: (row["source"], row["relative_path"])),
        "excluded": sorted(excluded, key=lambda row: (row["source"], row["relative_path"])),
        "limits": {"max_files": max_files, "max_bytes": max_bytes},
        "summary": {"included_files": len(included), "included_bytes": total_bytes,
                    "excluded_entries": len(excluded)},
        "content_read": False,
    }
    plan["plan_sha256"] = hashlib.sha256(_canonical_json(plan)).hexdigest()
    return plan


def _copy_planned_file(source: Path, target: Path, expected: dict[str, Any]) -> str:
    source_fd = _open_source_nofollow(source)
    try:
        before = os.fstat(source_fd)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        planned = (expected["device"], expected["inode"], expected["size"], expected["mtime_ns"])
        if identity != planned or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise SourceStageError("source changed after planning")
        target.parent.mkdir(parents=True, exist_ok=True)
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0), 0o400)
        digest = hashlib.sha256()
        copied = 0
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(target_fd, view)
                    if written <= 0:
                        raise SourceStageError("snapshot write made no progress")
                    view = view[written:]
                copied += len(chunk)
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        after = os.fstat(source_fd)
        if copied != expected["size"] or (after.st_dev, after.st_ino, after.st_size,
                                          after.st_mtime_ns) != identity:
            raise SourceStageError("source changed while copying")
        return digest.hexdigest()
    finally:
        os.close(source_fd)


def materialize_stage(
    plan: dict[str, Any],
    *,
    stage_root: str | os.PathLike[str],
    snapshot_id: str,
    before_copy: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Atomically publish one complete snapshot from a previously reviewed plan."""
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise SourceStageError("invalid stage plan")
    supplied_hash = plan.get("plan_sha256")
    core = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if supplied_hash != hashlib.sha256(_canonical_json(core)).hexdigest():
        raise SourceStageError("stage plan integrity check failed")
    if not isinstance(snapshot_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", snapshot_id):
        raise SourceStageError("snapshot_id must be a stable safe identifier")
    if before_copy is not None and not callable(before_copy):
        raise SourceStageError("before_copy must be callable")
    root = _absolute_directory(stage_root, label="stage_root", require_exists=True)
    final = root / snapshot_id
    if final.exists() or final.is_symlink():
        raise SourceStageError("snapshot destination already exists")
    source_roots = {row["name"]: Path(row["path"]) for row in plan["sources"]}
    temp = root / f".stage-{snapshot_id}-{secrets.token_hex(8)}"
    temp.mkdir(mode=0o700)
    published = False
    try:
        if before_copy is not None:
            before_copy()
        files = []
        for row in plan["included"]:
            relative = PurePosixPath(row["relative_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise SourceStageError("planned relative path escapes its source")
            source = source_roots[row["source"]] / Path(*relative.parts)
            target = temp / "sources" / row["source"] / Path(*relative.parts)
            try:
                digest = _copy_planned_file(source, target, row)
            except (OSError, SourceStageError) as exc:
                reason = exc.strerror if isinstance(exc, OSError) else str(exc)
                raise SourceStageError(
                    f"copy failed for {row['source']}:{row['relative_path']}: {reason}"
                ) from exc
            files.append({"source": row["source"], "relative_path": row["relative_path"],
                          "size": row["size"], "sha256": digest})
        manifest = {
            "schema": MANIFEST_SCHEMA, "snapshot_id": snapshot_id,
            "plan_sha256": supplied_hash, "files": files,
            "excluded": plan["excluded"], "summary": plan["summary"],
            "credential_present": False, "llm_invoked": False, "network_used": False,
        }
        manifest["manifest_sha256"] = hashlib.sha256(_canonical_json(manifest)).hexdigest()
        manifest_path = temp / "manifest.json"
        manifest_path.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(manifest_path, 0o400)
        os.replace(temp, final)
        published = True
        return manifest
    except OSError as exc:
        raise SourceStageError(f"filesystem refused source staging: {exc.strerror}") from exc
    finally:
        if not published:
            shutil.rmtree(temp, ignore_errors=True)
