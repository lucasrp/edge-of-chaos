"""Hermetic primitives for manual rotation of sealed source snapshots.

This module has no CLI, service, timer, heartbeat, network, credential, or source-collection
integration.  Callers must supply already sealed generations and an explicit lock path.  Installed
state migration remains a separate operator-gated work package.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
from typing import Any, Callable, Iterator


INDEX_SCHEMA = "edge.source-snapshot-index/v1"
MANIFEST_SCHEMA = "edge.source-stage-manifest/v1"
MIGRATION_PREVIEW_SCHEMA = "edge.source-snapshot-migration-preview/v1"
RECOVERY_STATUS_SCHEMA = "edge.source-snapshot-recovery-status/v1"
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


class SourceRotationError(RuntimeError):
    """Snapshot rotation state is unsafe or inconsistent."""


class RotationCommittedCleanupRequired(SourceRotationError):
    """The new index committed, but removal of unreferenced evidence did not finish."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise SourceRotationError(f"{label} must be a stable safe identifier")
    return value


def _directory(path: str | os.PathLike[str], *, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise SourceRotationError(f"{label} must be absolute")
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise SourceRotationError(f"{label} may not contain a symlink")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_dir():
        raise SourceRotationError(f"{label} must be an existing directory")
    return resolved


def _regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise SourceRotationError(f"{label} is missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SourceRotationError(f"{label} must be one regular non-hard-linked file")
    return info


def _hash_file(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    digest = hashlib.sha256()
    size = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise SourceRotationError("generation contains a non-regular or hard-linked file")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise SourceRotationError("generation changed during validation")
    finally:
        os.close(fd)
    return digest.hexdigest(), size


def validate_generation(
    generation: str | os.PathLike[str],
    *,
    expected_uid: int,
    expected_gid: int,
    require_sealed_modes: bool = True,
) -> dict[str, Any]:
    """Validate manifest integrity, exact contents, hashes, ownership and sealed modes."""
    root = _directory(generation, label="generation")
    manifest_path = root / "manifest.json"
    _regular_file(manifest_path, label="generation manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceRotationError("generation manifest is unreadable or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise SourceRotationError("generation manifest schema is invalid")
    supplied_hash = manifest.get("manifest_sha256")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if supplied_hash != hashlib.sha256(_canonical_json(core)).hexdigest():
        raise SourceRotationError("generation manifest integrity check failed")
    if any(manifest.get(flag) is not False
           for flag in ("credential_present", "llm_invoked", "network_used")):
        raise SourceRotationError("generation authority assertions are invalid")
    files = manifest.get("files")
    summary = manifest.get("summary")
    if not isinstance(files, list) or not isinstance(summary, dict):
        raise SourceRotationError("generation manifest shape is invalid")

    expected: dict[Path, dict[str, Any]] = {}
    total_bytes = 0
    for row in files:
        if not isinstance(row, dict):
            raise SourceRotationError("generation file row is invalid")
        source = _safe_id(row.get("source"), label="manifest source")
        relative = PurePosixPath(row.get("relative_path", ""))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise SourceRotationError("manifest relative path is unsafe")
        target = Path("sources") / source / Path(*relative.parts)
        if target in expected:
            raise SourceRotationError("manifest contains a duplicate file")
        if not isinstance(row.get("size"), int) or isinstance(row.get("size"), bool) \
                or row["size"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
            raise SourceRotationError("manifest file metadata is invalid")
        expected[target] = row
        total_bytes += row["size"]

    observed: set[Path] = set()
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        current_info = current_path.lstat()
        if (stat.S_IMODE(current_info.st_mode) != 0o500 if require_sealed_modes else False) \
                or current_info.st_uid != expected_uid or current_info.st_gid != expected_gid:
            raise SourceRotationError("generation directory owner or mode is invalid")
        for dirname in dirs:
            if (current_path / dirname).is_symlink():
                raise SourceRotationError("generation contains a symlink")
        for name in names:
            path = current_path / name
            if path.is_symlink():
                raise SourceRotationError("generation contains a symlink")
            info = _regular_file(path, label="generation file")
            if (stat.S_IMODE(info.st_mode) != 0o400 if require_sealed_modes else False) \
                    or info.st_uid != expected_uid or info.st_gid != expected_gid:
                raise SourceRotationError("generation file owner or mode is invalid")
            relative_path = path.relative_to(root)
            if relative_path == Path("manifest.json"):
                continue
            observed.add(relative_path)
            row = expected.get(relative_path)
            if row is None:
                raise SourceRotationError("generation contains an unexpected file")
            digest, size = _hash_file(path)
            if digest != row["sha256"] or size != row["size"]:
                raise SourceRotationError("generation file integrity check failed")
    if observed != set(expected):
        raise SourceRotationError("generation is missing a manifested file")
    if summary.get("included_files") != len(files) or summary.get("included_bytes") != total_bytes:
        raise SourceRotationError("generation summary does not match its files")
    return manifest


def seal_generation(path: str | os.PathLike[str], *, uid: int, gid: int) -> None:
    """Seal a synthetic/private candidate; production callers must mediate this as root."""
    root = _directory(path, label="candidate")
    for current, dirs, files in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in files:
            target = current_path / name
            _regular_file(target, label="candidate file")
            os.chown(target, uid, gid)
            os.chmod(target, 0o400)
        for name in dirs:
            target = current_path / name
            if target.is_symlink():
                raise SourceRotationError("candidate contains a symlink")
            os.chown(target, uid, gid)
            os.chmod(target, 0o500)
    os.chown(root, uid, gid)
    os.chmod(root, 0o500)


def _index_payload(*, current: str, previous: str | None, hashes: dict[str, str],
                   committed_at: str) -> dict[str, Any]:
    current = _safe_id(current, label="current generation")
    if previous is not None:
        previous = _safe_id(previous, label="previous generation")
        if previous == current:
            raise SourceRotationError("current and previous generations must differ")
    if set(hashes) != ({current} if previous is None else {current, previous}):
        raise SourceRotationError("index hashes must exactly cover referenced generations")
    if not isinstance(committed_at, str) or not committed_at.strip():
        raise SourceRotationError("commit timestamp is required")
    payload = {
        "schema": INDEX_SCHEMA, "current": current, "previous": previous,
        "manifest_sha256": {key: hashes[key] for key in sorted(hashes)},
        "committed_at": committed_at,
    }
    payload["index_sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return payload


def _load_index(root: Path, *, expected_uid: int, expected_gid: int) -> dict[str, Any] | None:
    path = root / "index.json"
    if not path.exists():
        return None
    info = _regular_file(path, label="snapshot index")
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
        expected_uid, expected_gid, 0o400
    ):
        raise SourceRotationError("snapshot index owner or mode is invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceRotationError("snapshot index is unreadable or invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema") != INDEX_SCHEMA:
        raise SourceRotationError("snapshot index schema is invalid")
    supplied = payload.get("index_sha256")
    core = {key: value for key, value in payload.items() if key != "index_sha256"}
    if supplied != hashlib.sha256(_canonical_json(core)).hexdigest():
        raise SourceRotationError("snapshot index integrity check failed")
    current = _safe_id(payload.get("current"), label="current generation")
    previous = payload.get("previous")
    if previous is not None:
        _safe_id(previous, label="previous generation")
        if previous == current:
            raise SourceRotationError("current and previous generations must differ")
    expected_keys = {current} if previous is None else {current, previous}
    hashes = payload.get("manifest_sha256")
    if not isinstance(hashes, dict) or set(hashes) != expected_keys or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in hashes.values()
    ):
        raise SourceRotationError("snapshot index hash map is invalid")
    return payload


def _write_index(root: Path, payload: dict[str, Any]) -> None:
    target = root / "index.json"
    temporary = root / f".index-{secrets.token_hex(8)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        data = _canonical_json(payload) + b"\n"
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise SourceRotationError("index write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, 0o400)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, target)
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _transaction_marker(root: Path) -> Path:
    return root / "rotation.pending"


def _begin_transaction(root: Path) -> None:
    marker = _transaction_marker(root)
    if marker.exists() or marker.is_symlink():
        raise SourceRotationError("a prior snapshot transaction requires review")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o400)
    try:
        os.write(fd, b"edge.source-snapshot-transaction/v1\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _finish_transaction(root: Path) -> None:
    marker = _transaction_marker(root)
    _regular_file(marker, label="rotation transaction marker")
    marker.unlink()
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def rotation_lock(lock_path: str | os.PathLike[str]) -> Iterator[None]:
    """Take a nonblocking exclusive lock for one complete state transition."""
    path = Path(lock_path)
    if not path.is_absolute() or path.is_symlink():
        raise SourceRotationError("rotation lock path must be absolute and not a symlink")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)
        ) != (os.geteuid(), os.getegid(), 0o600):
            raise SourceRotationError("rotation lock owner, mode, or type is invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SourceRotationError("another snapshot operation holds the lock") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _validate_indexed_generations(root: Path, index: dict[str, Any], *, uid: int,
                                  gid: int) -> None:
    generations = root / "generations"
    for generation_id in filter(None, (index["current"], index["previous"])):
        manifest = validate_generation(
            generations / generation_id, expected_uid=uid, expected_gid=gid
        )
        if manifest["manifest_sha256"] != index["manifest_sha256"][generation_id]:
            raise SourceRotationError("indexed manifest hash does not match generation")


def _remove_unreferenced_generation(path: Path) -> None:
    """Make only one already-unreferenced sealed tree traversably removable, then delete it."""
    for current, dirs, _files in os.walk(path, topdown=False, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink() or any((current_path / name).is_symlink() for name in dirs):
            raise SourceRotationError("retention target contains a symlink")
        os.chmod(current_path, 0o700)
    shutil.rmtree(path)


def _rotate_candidate_locked(
    snapshots_root: str | os.PathLike[str],
    *, candidate: str | os.PathLike[str], generation_id: str, committed_at: str,
    expected_uid: int, expected_gid: int,
    fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Publish one sealed candidate and atomically advance a valid existing index."""
    root = _directory(snapshots_root, label="snapshots_root")
    generation_id = _safe_id(generation_id, label="generation_id")
    generations = root / "generations"
    if not generations.is_dir() or generations.is_symlink():
        raise SourceRotationError("generations directory is missing or unsafe")
    index = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
    if index is None:
        raise SourceRotationError("initial snapshot index is required")
    _validate_indexed_generations(root, index, uid=expected_uid, gid=expected_gid)
    referenced = {index["current"]} | ({index["previous"]} if index["previous"] else set())
    candidate_path = _directory(candidate, label="candidate")
    if candidate_path.parent != generations or not candidate_path.name.startswith(".candidate-"):
        raise SourceRotationError("candidate must be a named private child of generations")
    observed = {entry.name for entry in generations.iterdir() if entry.is_dir()}
    if observed != referenced | {candidate_path.name}:
        raise SourceRotationError("unexplained or missing generation blocks rotation")
    manifest = validate_generation(
        candidate_path, expected_uid=expected_uid, expected_gid=expected_gid
    )
    destination = generations / generation_id
    if destination.exists() or destination.is_symlink() or generation_id in referenced:
        raise SourceRotationError("generation destination already exists")
    old_previous = index["previous"]
    committed = False
    published = False
    _begin_transaction(root)
    try:
        if fault:
            fault("before_publish")
        os.replace(candidate_path, destination)
        published = True
        if fault:
            fault("after_publish")
        hashes = {
            generation_id: manifest["manifest_sha256"],
            index["current"]: index["manifest_sha256"][index["current"]],
        }
        new_index = _index_payload(
            current=generation_id, previous=index["current"], hashes=hashes,
            committed_at=committed_at,
        )
        if fault:
            fault("before_index_commit")
        _write_index(root, new_index)
        committed = True
        if fault:
            fault("after_index_commit")
        loaded = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
        if loaded != new_index:
            raise SourceRotationError("committed index did not reopen exactly")
        _validate_indexed_generations(root, loaded, uid=expected_uid, gid=expected_gid)
        if old_previous is not None:
            retired = generations / old_previous
            if retired.name in {loaded["current"], loaded["previous"]}:
                raise SourceRotationError("retention target is still referenced")
            if fault:
                fault("before_retention_cleanup")
            _remove_unreferenced_generation(retired)
        if fault:
            fault("after_retention_cleanup")
        _finish_transaction(root)
        return new_index
    except BaseException as exc:
        if committed:
            raise RotationCommittedCleanupRequired(
                "new snapshot committed; cleanup or post-commit verification requires review"
            ) from exc
        cleanup_target = destination if published else candidate_path
        try:
            _remove_unreferenced_generation(cleanup_target)
            _finish_transaction(root)
        except BaseException as cleanup_exc:
            raise SourceRotationError(
                "pre-commit failure preserved the index but candidate cleanup requires review"
            ) from cleanup_exc
        raise


def rotate_candidate(
    snapshots_root: str | os.PathLike[str],
    *, lock_path: str | os.PathLike[str], candidate: str | os.PathLike[str],
    generation_id: str, committed_at: str, expected_uid: int, expected_gid: int,
    fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Lock and publish one sealed candidate through the complete rotation transaction."""
    with rotation_lock(lock_path):
        return _rotate_candidate_locked(
            snapshots_root, candidate=candidate, generation_id=generation_id,
            committed_at=committed_at, expected_uid=expected_uid,
            expected_gid=expected_gid, fault=fault,
        )


def _rollback_index_locked(
    snapshots_root: str | os.PathLike[str], *, committed_at: str,
    expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Atomically exchange current and previous after validating both generations."""
    root = _directory(snapshots_root, label="snapshots_root")
    index = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
    if index is None or index.get("previous") is None:
        raise SourceRotationError("rollback requires a valid previous generation")
    _validate_indexed_generations(root, index, uid=expected_uid, gid=expected_gid)
    new_index = _index_payload(
        current=index["previous"], previous=index["current"],
        hashes=dict(index["manifest_sha256"]), committed_at=committed_at,
    )
    _begin_transaction(root)
    try:
        _write_index(root, new_index)
        loaded = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
        if loaded != new_index:
            raise SourceRotationError("rollback index did not reopen exactly")
        _validate_indexed_generations(root, loaded, uid=expected_uid, gid=expected_gid)
        _finish_transaction(root)
        return new_index
    except BaseException as exc:
        raise RotationCommittedCleanupRequired(
            "rollback state requires review before another snapshot operation"
        ) from exc


def rollback_index(
    snapshots_root: str | os.PathLike[str], *, lock_path: str | os.PathLike[str],
    committed_at: str, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Lock and atomically exchange the two validated logical roles."""
    with rotation_lock(lock_path):
        return _rollback_index_locked(
            snapshots_root, committed_at=committed_at, expected_uid=expected_uid,
            expected_gid=expected_gid,
        )


def _initialize_index_for_generation_locked(
    snapshots_root: str | os.PathLike[str], *, generation_id: str, committed_at: str,
    expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Create the first index around one already published and independently sealed generation."""
    root = _directory(snapshots_root, label="snapshots_root")
    generation_id = _safe_id(generation_id, label="generation_id")
    if _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid) is not None:
        raise SourceRotationError("snapshot index already exists")
    generations = root / "generations"
    if not generations.is_dir() or generations.is_symlink():
        raise SourceRotationError("generations directory is missing or unsafe")
    observed = [entry.name for entry in generations.iterdir()]
    if observed != [generation_id]:
        raise SourceRotationError("initial index requires exactly one named generation")
    manifest = validate_generation(
        generations / generation_id, expected_uid=expected_uid, expected_gid=expected_gid
    )
    payload = _index_payload(
        current=generation_id, previous=None,
        hashes={generation_id: manifest["manifest_sha256"]}, committed_at=committed_at,
    )
    _begin_transaction(root)
    try:
        _write_index(root, payload)
        loaded = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
        if loaded != payload:
            raise SourceRotationError("initial index did not reopen exactly")
        _finish_transaction(root)
        return payload
    except BaseException as exc:
        raise RotationCommittedCleanupRequired(
            "initial index state requires review before another snapshot operation"
        ) from exc


def initialize_index_for_generation(
    snapshots_root: str | os.PathLike[str], *, lock_path: str | os.PathLike[str],
    generation_id: str, committed_at: str, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Lock and initialize an index around one independently sealed generation."""
    with rotation_lock(lock_path):
        return _initialize_index_for_generation_locked(
            snapshots_root, generation_id=generation_id, committed_at=committed_at,
            expected_uid=expected_uid, expected_gid=expected_gid,
        )


def _positive_size(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SourceRotationError(f"{label} must be a non-negative integer")
    return value


def capacity_status(
    path: str | os.PathLike[str], *, max_candidate_bytes: int, safety_margin_bytes: int,
) -> dict[str, int | bool]:
    """Return a read-only capacity gate for one bounded candidate plus a fixed margin."""
    root = _directory(path, label="capacity path")
    maximum = _positive_size(max_candidate_bytes, label="max_candidate_bytes")
    margin = _positive_size(safety_margin_bytes, label="safety_margin_bytes")
    required = maximum + margin
    free = shutil.disk_usage(root).free
    return {
        "max_candidate_bytes": maximum, "safety_margin_bytes": margin,
        "required_free_bytes": required, "observed_free_bytes": free,
        "sufficient": free >= required,
    }


def _preview_binding_payload(preview: dict[str, Any]) -> dict[str, Any]:
    """Return only stable, operator-reviewed migration authority."""
    core = {key: value for key, value in preview.items()
            if key not in {"preview_sha256", "observation_sha256"}}
    capacity = dict(core.get("capacity", {}))
    capacity.pop("observed_free_bytes", None)
    capacity.pop("sufficient", None)
    core["capacity"] = capacity
    return core


def _preview_observation_payload(preview: dict[str, Any]) -> dict[str, Any]:
    """Return the full point-in-time evidence, excluding only its own digest."""
    return {key: value for key, value in preview.items() if key != "observation_sha256"}


def preview_legacy_migration(
    snapshots_root: str | os.PathLike[str], *, generation_id: str,
    expected_uid: int, expected_gid: int, max_candidate_bytes: int,
    safety_margin_bytes: int,
) -> dict[str, Any]:
    """Validate the legacy snapshot and produce a content-bound, read-only migration preview."""
    root = _directory(snapshots_root, label="snapshots_root")
    generation_id = _safe_id(generation_id, label="generation_id")
    if _transaction_marker(root).exists() or _transaction_marker(root).is_symlink():
        raise SourceRotationError("a prior snapshot transaction requires review")
    if _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid) is not None:
        raise SourceRotationError("legacy migration requires an absent snapshot index")
    generations = root / "generations"
    if generations.exists() or generations.is_symlink():
        raise SourceRotationError("legacy migration requires an absent generations directory")
    legacy = root / "current"
    manifest = validate_generation(
        legacy, expected_uid=expected_uid, expected_gid=expected_gid
    )
    capacity = capacity_status(
        root, max_candidate_bytes=max_candidate_bytes,
        safety_margin_bytes=safety_margin_bytes,
    )
    payload = {
        "schema": MIGRATION_PREVIEW_SCHEMA,
        "generation_id": generation_id,
        "legacy_manifest_sha256": manifest["manifest_sha256"],
        "included_files": manifest["summary"]["included_files"],
        "included_bytes": manifest["summary"]["included_bytes"],
        "capacity": capacity,
        "content_read": True,
        "state_changed": False,
        "legacy_retained": True,
    }
    payload["preview_sha256"] = hashlib.sha256(
        _canonical_json(_preview_binding_payload(payload))
    ).hexdigest()
    payload["observation_sha256"] = hashlib.sha256(
        _canonical_json(_preview_observation_payload(payload))
    ).hexdigest()
    return payload


def _validate_migration_preview(preview: Any) -> dict[str, Any]:
    if not isinstance(preview, dict) or preview.get("schema") != MIGRATION_PREVIEW_SCHEMA:
        raise SourceRotationError("migration preview schema is invalid")
    supplied = preview.get("preview_sha256")
    if supplied != hashlib.sha256(
        _canonical_json(_preview_binding_payload(preview))
    ).hexdigest():
        raise SourceRotationError("migration preview integrity check failed")
    observed = preview.get("observation_sha256")
    if observed != hashlib.sha256(
        _canonical_json(_preview_observation_payload(preview))
    ).hexdigest():
        raise SourceRotationError("migration preview observation integrity check failed")
    _safe_id(preview.get("generation_id"), label="preview generation_id")
    if not re.fullmatch(r"[0-9a-f]{64}", str(preview.get("legacy_manifest_sha256", ""))):
        raise SourceRotationError("migration preview manifest hash is invalid")
    if preview.get("content_read") is not True or preview.get("state_changed") is not False \
            or preview.get("legacy_retained") is not True:
        raise SourceRotationError("migration preview assertions are invalid")
    capacity = preview.get("capacity")
    if not isinstance(capacity, dict):
        raise SourceRotationError("migration preview capacity is invalid")
    for key in ("max_candidate_bytes", "safety_margin_bytes", "required_free_bytes",
                "observed_free_bytes"):
        _positive_size(capacity.get(key), label=f"preview {key}")
    if capacity["required_free_bytes"] != (
        capacity["max_candidate_bytes"] + capacity["safety_margin_bytes"]
    ) or capacity.get("sufficient") is not (
        capacity["observed_free_bytes"] >= capacity["required_free_bytes"]
    ):
        raise SourceRotationError("migration preview capacity arithmetic is invalid")
    _positive_size(preview.get("included_files"), label="preview included_files")
    _positive_size(preview.get("included_bytes"), label="preview included_bytes")
    return preview


def _copy_file_exact(source: Path, destination: Path, *, expected_hash: str | None,
                     expected_size: int | None) -> None:
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise SourceRotationError("legacy copy source is not one regular file")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0), 0o600)
        digest = hashlib.sha256()
        copied = 0
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                copied += len(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(target_fd, view)
                    if written <= 0:
                        raise SourceRotationError("legacy copy write made no progress")
                    view = view[written:]
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        after = os.fstat(source_fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise SourceRotationError("legacy snapshot changed during copying")
        if expected_hash is not None and digest.hexdigest() != expected_hash:
            raise SourceRotationError("legacy copied file hash does not match preview")
        if expected_size is not None and copied != expected_size:
            raise SourceRotationError("legacy copied file size does not match preview")
    finally:
        os.close(source_fd)


def _copy_legacy_generation(legacy: Path, candidate: Path,
                            manifest: dict[str, Any]) -> None:
    candidate.mkdir(mode=0o700)
    complete = False
    try:
        _copy_file_exact(
            legacy / "manifest.json", candidate / "manifest.json",
            expected_hash=None, expected_size=None,
        )
        for row in manifest["files"]:
            relative = PurePosixPath(row["relative_path"])
            source_relative = Path("sources") / row["source"] / Path(*relative.parts)
            _copy_file_exact(
                legacy / source_relative, candidate / source_relative,
                expected_hash=row["sha256"], expected_size=row["size"],
            )
        complete = True
    finally:
        if not complete:
            shutil.rmtree(candidate, ignore_errors=True)


def apply_legacy_migration(
    snapshots_root: str | os.PathLike[str], *, lock_path: str | os.PathLike[str],
    preview: dict[str, Any], committed_at: str, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Copy and index one preview-bound legacy snapshot while retaining the legacy tree."""
    checked = _validate_migration_preview(preview)
    with rotation_lock(lock_path):
        root = _directory(snapshots_root, label="snapshots_root")
        if _transaction_marker(root).exists() or _transaction_marker(root).is_symlink():
            raise SourceRotationError("a prior snapshot transaction requires review")
        if _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid) is not None:
            raise SourceRotationError("legacy migration requires an absent snapshot index")
        if (root / "generations").exists() or (root / "generations").is_symlink():
            raise SourceRotationError("legacy migration requires an absent generations directory")
        legacy = root / "current"
        manifest = validate_generation(
            legacy, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if manifest["manifest_sha256"] != checked["legacy_manifest_sha256"] \
                or manifest["summary"]["included_files"] != checked["included_files"] \
                or manifest["summary"]["included_bytes"] != checked["included_bytes"]:
            raise SourceRotationError("legacy snapshot drifted after migration preview")
        capacity = capacity_status(
            root,
            max_candidate_bytes=checked["capacity"]["max_candidate_bytes"],
            safety_margin_bytes=checked["capacity"]["safety_margin_bytes"],
        )
        if not capacity["sufficient"]:
            raise SourceRotationError("insufficient free space for bounded migration")
        generation_id = checked["generation_id"]
        generations = root / "generations"
        generations.mkdir(mode=0o700)
        os.chown(generations, expected_uid, expected_gid)
        candidate = generations / f".candidate-{generation_id}"
        final = generations / generation_id
        published = False
        try:
            _copy_legacy_generation(legacy, candidate, manifest)
            seal_generation(candidate, uid=expected_uid, gid=expected_gid)
            copied = validate_generation(
                candidate, expected_uid=expected_uid, expected_gid=expected_gid
            )
            fresh_legacy = validate_generation(
                legacy, expected_uid=expected_uid, expected_gid=expected_gid
            )
            if copied["manifest_sha256"] != checked["legacy_manifest_sha256"] \
                    or fresh_legacy["manifest_sha256"] != checked["legacy_manifest_sha256"]:
                raise SourceRotationError("legacy snapshot changed during migration")
            os.replace(candidate, final)
            published = True
            index = _initialize_index_for_generation_locked(
                root, generation_id=generation_id, committed_at=committed_at,
                expected_uid=expected_uid, expected_gid=expected_gid,
            )
            try:
                os.chmod(generations, 0o500)
            except BaseException as exc:
                _begin_transaction(root)
                raise RotationCommittedCleanupRequired(
                    "migration committed; generation-root sealing requires review"
                ) from exc
            return {
                "schema": "edge.source-snapshot-migration-result/v1",
                "preview_sha256": checked["preview_sha256"],
                "index_sha256": index["index_sha256"],
                "current": index["current"], "previous": index["previous"],
                "legacy_retained": (root / "current").is_dir(),
            }
        except BaseException:
            cleanup = final if published and not (root / "index.json").exists() else candidate
            if cleanup.exists() and not _transaction_marker(root).exists():
                _remove_unreferenced_generation(cleanup)
            if generations.exists() and not any(generations.iterdir()):
                generations.rmdir()
            raise


def inspect_pending_transaction(
    snapshots_root: str | os.PathLike[str], *, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Read and classify a transaction marker without changing snapshot state."""
    root = _directory(snapshots_root, label="snapshots_root")
    marker = _transaction_marker(root)
    if not marker.exists() and not marker.is_symlink():
        return {"schema": RECOVERY_STATUS_SCHEMA, "status": "clean", "state_changed": False}
    info = _regular_file(marker, label="rotation transaction marker")
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
        expected_uid, expected_gid, 0o400
    ) or marker.read_bytes() != b"edge.source-snapshot-transaction/v1\n":
        raise SourceRotationError("rotation transaction marker is invalid")
    index = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
    if index is None:
        return {
            "schema": RECOVERY_STATUS_SCHEMA, "status": "blocked_missing_index",
            "state_changed": False,
        }
    _validate_indexed_generations(root, index, uid=expected_uid, gid=expected_gid)
    referenced = {index["current"]} | ({index["previous"]} if index["previous"] else set())
    generations = root / "generations"
    observed = {entry.name for entry in generations.iterdir()} if generations.is_dir() else set()
    extras = sorted(observed - referenced)
    missing = sorted(referenced - observed)
    status = "recoverable_clean" if not extras and not missing else "blocked_generation_mismatch"
    return {
        "schema": RECOVERY_STATUS_SCHEMA, "status": status,
        "index_sha256": index["index_sha256"],
        "current": index["current"], "previous": index["previous"],
        "extra_generation_ids": extras, "missing_generation_ids": missing,
        "state_changed": False,
    }


def clear_recovered_transaction(
    snapshots_root: str | os.PathLike[str], *, lock_path: str | os.PathLike[str],
    expected_index_sha256: str, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Clear only a marker whose fully validated state exactly matches operator-reviewed status."""
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_index_sha256)):
        raise SourceRotationError("expected index hash is invalid")
    with rotation_lock(lock_path):
        root = _directory(snapshots_root, label="snapshots_root")
        status = inspect_pending_transaction(
            root, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if status.get("status") != "recoverable_clean":
            raise SourceRotationError("pending transaction is not safe to clear")
        if status.get("index_sha256") != expected_index_sha256:
            raise SourceRotationError("pending transaction changed after review")
        _finish_transaction(root)
        return {
            "schema": "edge.source-snapshot-recovery-result/v1",
            "cleared_index_sha256": expected_index_sha256,
            "state_changed": True,
        }


def snapshot_status(
    snapshots_root: str | os.PathLike[str], *, expected_uid: int, expected_gid: int,
) -> dict[str, Any]:
    """Return a content-free integrity/freshness shape for legacy or indexed snapshot state."""
    root = _directory(snapshots_root, label="snapshots_root")
    if _transaction_marker(root).exists() or _transaction_marker(root).is_symlink():
        return inspect_pending_transaction(
            root, expected_uid=expected_uid, expected_gid=expected_gid
        )
    index = _load_index(root, expected_uid=expected_uid, expected_gid=expected_gid)
    if index is None:
        legacy = root / "current"
        manifest = validate_generation(
            legacy, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if (root / "generations").exists() or (root / "generations").is_symlink():
            raise SourceRotationError("legacy state contains an unexpected generations directory")
        return {
            "schema": "edge.source-snapshot-status/v1", "status": "legacy_valid",
            "current": "legacy", "previous": None,
            "manifest_sha256": manifest["manifest_sha256"],
            "included_files": manifest["summary"]["included_files"],
            "included_bytes": manifest["summary"]["included_bytes"],
            "transaction_pending": False, "state_changed": False,
        }
    _validate_indexed_generations(root, index, uid=expected_uid, gid=expected_gid)
    generations = root / "generations"
    referenced = {index["current"]} | ({index["previous"]} if index["previous"] else set())
    observed = {entry.name for entry in generations.iterdir()} if generations.is_dir() else set()
    if observed != referenced:
        raise SourceRotationError("indexed state contains an unexplained or missing generation")
    return {
        "schema": "edge.source-snapshot-status/v1", "status": "indexed_valid",
        "current": index["current"], "previous": index["previous"],
        "index_sha256": index["index_sha256"],
        "manifest_sha256": dict(index["manifest_sha256"]),
        "transaction_pending": False, "state_changed": False,
    }
