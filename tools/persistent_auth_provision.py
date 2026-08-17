"""Atomic, content-free provisioning primitive for a supported Codex auth bundle.

This module has no CLI and is not called by the heartbeat.  It copies opaque bytes from an
already-openable regular source into ``auth.json`` below a caller-selected private directory while
emitting metadata that contains neither paths nor content fingerprints.  Service creation,
privilege changes and selection of any real source are deliberately outside this module.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
from typing import Callable


class AuthProvisionError(RuntimeError):
    """The auth bundle could not be placed without weakening the boundary."""


MAX_AUTH_BYTES = 16 * 1024 * 1024


def _require_regular_private(st, *, label: str, uid: int, mode: int) -> None:
    if not stat.S_ISREG(st.st_mode):
        raise AuthProvisionError(f"{label} must be a regular file")
    if st.st_uid != uid:
        raise AuthProvisionError(f"{label} has an unexpected owner")
    if stat.S_IMODE(st.st_mode) != mode:
        raise AuthProvisionError(f"{label} has an unexpected mode")
    if st.st_nlink != 1:
        raise AuthProvisionError(f"{label} must have exactly one hard link")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise AuthProvisionError("temporary auth write made no progress")
        view = view[written:]


def _open_directory_chain(path: Path) -> int:
    """Open an absolute directory one component at a time without following symlinks."""
    if not path.is_absolute():
        raise AuthProvisionError("directory path must be absolute")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current
            )
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _open_source_nofollow(path: Path) -> int:
    """Open a source file through a symlink-free parent chain."""
    parent_fd = _open_directory_chain(path.parent)
    try:
        return os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def provision_auth_bundle(
    source: str | os.PathLike[str],
    codex_home: str | os.PathLike[str],
    *,
    expected_uid: int,
    expected_gid: int,
    before_replace: Callable[[], None] | None = None,
) -> dict:
    """Atomically replace ``auth.json`` with opaque bytes under a private home.

    ``before_replace`` is a hermetic crash-injection seam.  Production callers must omit it.
    The returned receipt intentionally excludes paths, content, hashes and token-shaped fields.
    """
    if not isinstance(expected_uid, int) or isinstance(expected_uid, bool) or expected_uid < 0:
        raise AuthProvisionError("expected_uid must be a non-negative integer")
    if not isinstance(expected_gid, int) or isinstance(expected_gid, bool) or expected_gid < 0:
        raise AuthProvisionError("expected_gid must be a non-negative integer")
    if before_replace is not None and not callable(before_replace):
        raise AuthProvisionError("before_replace must be callable")

    source_path = Path(source)
    home_path = Path(codex_home)
    if not source_path.is_absolute() or not home_path.is_absolute():
        raise AuthProvisionError("source and codex_home must be absolute")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    source_fd = home_fd = temp_fd = None
    temp_name = f".auth.json.tmp-{secrets.token_hex(12)}"
    replaced = False
    try:
        source_fd = _open_source_nofollow(source_path)
        source_stat = os.fstat(source_fd)
        _require_regular_private(
            source_stat, label="source auth bundle", uid=expected_uid, mode=0o600
        )
        if not 0 < source_stat.st_size <= MAX_AUTH_BYTES:
            raise AuthProvisionError("source auth bundle size is outside the safe bound")

        home_fd = _open_directory_chain(home_path)
        home_stat = os.fstat(home_fd)
        if home_stat.st_uid != expected_uid or home_stat.st_gid != expected_gid:
            raise AuthProvisionError("codex_home has unexpected ownership")
        if stat.S_IMODE(home_stat.st_mode) != 0o700:
            raise AuthProvisionError("codex_home must have mode 0700")

        try:
            current = os.stat("auth.json", dir_fd=home_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None:
            _require_regular_private(
                current, label="existing auth bundle", uid=expected_uid, mode=0o600
            )

        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
            dir_fd=home_fd,
        )
        copied = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_AUTH_BYTES:
                raise AuthProvisionError("source auth bundle exceeded the safe bound while copying")
            _write_all(temp_fd, chunk)
        if copied != source_stat.st_size:
            raise AuthProvisionError("source auth bundle changed while copying")
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None

        staged = os.stat(temp_name, dir_fd=home_fd, follow_symlinks=False)
        _require_regular_private(
            staged, label="staged auth bundle", uid=expected_uid, mode=0o600
        )
        if before_replace is not None:
            before_replace()
        os.replace(temp_name, "auth.json", src_dir_fd=home_fd, dst_dir_fd=home_fd)
        replaced = True
        os.fsync(home_fd)

        final = os.stat("auth.json", dir_fd=home_fd, follow_symlinks=False)
        _require_regular_private(
            final, label="installed auth bundle", uid=expected_uid, mode=0o600
        )
        return {
            "schema": "edge.persistent-auth-provision/v1",
            "installed": True,
            "atomic_replace": True,
            "directory_synced": True,
            "owner_verified": True,
            "mode": "0600",
            "single_link": True,
            "content_reported": False,
            "content_fingerprint_reported": False,
        }
    except OSError as exc:
        raise AuthProvisionError(f"filesystem refused auth provisioning: {exc.strerror}") from exc
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if home_fd is not None:
            if not replaced:
                try:
                    os.unlink(temp_name, dir_fd=home_fd)
                except FileNotFoundError:
                    pass
            os.close(home_fd)
        if source_fd is not None:
            os.close(source_fd)
