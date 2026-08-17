"""Transactional one-shot installer and pre-migration rollback for snapshot administration.

The public CLI has only ``install`` and ``rollback`` and uses fixed production paths. Tests may
inject an isolated layout through the Python API. This module never migrates or deletes snapshots,
never creates a service/timer/sudo rule, and never invokes a credential, LLM, or network.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
from typing import Any, Callable


INSTALL_SCHEMA = "edge.source-snapshot-admin-install-manifest/v1"
RESULT_SCHEMA = "edge.source-snapshot-admin-install-result/v1"
SOURCE_FILES = (
    "source_rotation.py", "source_snapshot_admin.py", "admin_receipt_mediator.py",
    "edge-source-snapshot-admin",
)
LAUNCHER = (
    b"#!/bin/sh\nset -eu\nexec /usr/bin/python3 -B "
    b"/usr/local/libexec/edge-source-snapshot-admin/tools/edge-source-snapshot-admin \"$@\"\n"
)


class SnapshotAdminInstallError(RuntimeError):
    """Installation or rollback cannot proceed without violating an invariant."""


class SnapshotAdminRollbackCommitted(SnapshotAdminInstallError):
    """Rollback committed, but exact quarantine cleanup requires review."""


@dataclass(frozen=True)
class InstallLayout:
    source_dir: Path
    libexec_parent: Path
    sbin_parent: Path
    state_base: Path
    snapshots: Path
    expected_uid: int
    expected_gid: int

    @property
    def package(self) -> Path:
        return self.libexec_parent / "edge-source-snapshot-admin"

    @property
    def launcher(self) -> Path:
        return self.sbin_parent / "edge-source-snapshot-admin"

    @property
    def receipts(self) -> Path:
        return self.state_base / "admin-receipts"

    @property
    def marker(self) -> Path:
        return self.state_base / ".edge-source-snapshot-admin.installing"


DEFAULT_LAYOUT = InstallLayout(
    source_dir=Path(__file__).resolve().parent,
    libexec_parent=Path("/usr/local/libexec"),
    sbin_parent=Path("/usr/local/sbin"),
    state_base=Path("/var/lib/edge-source-collector"),
    snapshots=Path("/var/lib/edge-source-collector/snapshots"),
    expected_uid=0,
    expected_gid=0,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_directory(path: Path, *, uid: int, gid: int, mode: int, label: str) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise SnapshotAdminInstallError(f"{label} must be one existing real absolute directory")
    info = path.stat()
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, mode):
        raise SnapshotAdminInstallError(f"{label} owner or mode is invalid")


def _regular(path: Path, *, uid: int | None = None, gid: int | None = None,
             mode: int | None = None, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise SnapshotAdminInstallError(f"{label} is missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SnapshotAdminInstallError(f"{label} must be one regular non-hard-linked file")
    if uid is not None and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
        uid, gid, mode,
    ):
        raise SnapshotAdminInstallError(f"{label} owner or mode is invalid")
    return info


def _read_source(path: Path) -> bytes:
    _regular(path, label="installer source artifact")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    chunks = []
    try:
        before = os.fstat(fd)
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
        ):
            raise SnapshotAdminInstallError("installer source changed while reading")
    finally:
        os.close(fd)
    return b"".join(chunks)


def _write_file(path: Path, data: bytes, *, uid: int, gid: int, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise SnapshotAdminInstallError("installer write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
    finally:
        os.close(fd)


def _begin(layout: InstallLayout) -> None:
    if layout.marker.exists() or layout.marker.is_symlink():
        raise SnapshotAdminInstallError("prior install transaction marker requires review")
    _write_file(
        layout.marker, b"edge.source-snapshot-admin-install-transaction/v1\n",
        uid=layout.expected_uid, gid=layout.expected_gid, mode=0o600,
    )
    _fsync_dir(layout.state_base)


def _finish(layout: InstallLayout) -> None:
    _regular(
        layout.marker, uid=layout.expected_uid, gid=layout.expected_gid, mode=0o600,
        label="install transaction marker",
    )
    layout.marker.unlink()
    _fsync_dir(layout.state_base)


def _artifact_data(layout: InstallLayout) -> dict[str, tuple[bytes, int]]:
    artifacts = {name: (_read_source(layout.source_dir / name), 0o750 if name ==
                        "edge-source-snapshot-admin" else 0o640) for name in SOURCE_FILES}
    artifacts["__init__.py"] = (b"", 0o640)
    return artifacts


def _manifest(layout: InstallLayout, artifacts: dict[str, tuple[bytes, int]]) -> dict[str, Any]:
    rows = []
    for name in sorted(artifacts):
        data, mode = artifacts[name]
        rows.append({
            "target": str(layout.package / "tools" / name), "mode": f"{mode:04o}",
            "owner": f"{layout.expected_uid}:{layout.expected_gid}", "sha256": _sha(data),
        })
    rows.append({
        "target": str(layout.launcher), "mode": "0750",
        "owner": f"{layout.expected_uid}:{layout.expected_gid}", "sha256": _sha(LAUNCHER),
    })
    return {
        "schema": INSTALL_SCHEMA, "artifacts": rows,
        "directories": [
            {"target": str(layout.package), "mode": "0750"},
            {"target": str(layout.package / "tools"), "mode": "0750"},
            {"target": str(layout.receipts), "mode": "0700"},
            {"target": str(layout.receipts / "pending"), "mode": "0700"},
            {"target": str(layout.receipts / "completed"), "mode": "0700"},
        ],
        "locks": [
            {"target": str(layout.receipts / ".journal.lock"), "mode": "0600"},
            {"target": str(layout.receipts / ".rotation.lock"), "mode": "0600"},
        ],
        "snapshots_touched": False, "service_created": False, "timer_created": False,
        "heartbeat_touched": False, "credential_present": False, "llm_invoked": False,
        "network_used": False,
    }


def _validate_layout(layout: InstallLayout) -> None:
    uid, gid = layout.expected_uid, layout.expected_gid
    _validate_directory(layout.libexec_parent, uid=uid, gid=gid, mode=0o755,
                        label="libexec parent")
    _validate_directory(layout.sbin_parent, uid=uid, gid=gid, mode=0o755,
                        label="sbin parent")
    _validate_directory(layout.state_base, uid=uid, gid=gid, mode=0o711,
                        label="collector state root")
    _validate_directory(layout.snapshots, uid=uid, gid=gid, mode=0o700,
                        label="snapshot root")


def _remove_tree(path: Path) -> None:
    for current, _dirs, files in os.walk(path):
        os.chmod(current, 0o700)
        for name in files:
            os.chmod(Path(current) / name, 0o600)
    shutil.rmtree(path)


def _receipt_records_exist(receipts: Path) -> bool:
    return any(any((receipts / name).iterdir()) for name in ("pending", "completed"))


def _validate_installed(layout: InstallLayout) -> dict[str, Any]:
    uid, gid = layout.expected_uid, layout.expected_gid
    _validate_directory(layout.package, uid=uid, gid=gid, mode=0o750, label="installed package")
    _validate_directory(layout.package / "tools", uid=uid, gid=gid, mode=0o750,
                        label="installed tools package")
    _validate_directory(layout.receipts, uid=uid, gid=gid, mode=0o700, label="receipt root")
    for name in ("pending", "completed"):
        _validate_directory(layout.receipts / name, uid=uid, gid=gid, mode=0o700,
                            label=f"receipt {name} directory")
    manifest_path = layout.package / "INSTALL-MANIFEST.json"
    _regular(manifest_path, uid=uid, gid=gid, mode=0o400, label="install manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotAdminInstallError("install manifest is unreadable or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != INSTALL_SCHEMA:
        raise SnapshotAdminInstallError("install manifest schema is invalid")
    allowed_targets = {
        layout.launcher,
        *(layout.package / "tools" / name for name in (*SOURCE_FILES, "__init__.py")),
    }
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or len(rows) != len(allowed_targets):
        raise SnapshotAdminInstallError("install manifest artifact inventory is invalid")
    expected_files = {manifest_path}
    observed_targets: set[Path] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SnapshotAdminInstallError("install manifest artifact row is invalid")
        target = Path(row.get("target", ""))
        if target not in allowed_targets or target in observed_targets:
            raise SnapshotAdminInstallError("install manifest contains an unexpected target")
        observed_targets.add(target)
        expected_files.add(target)
        mode = int(row["mode"], 8)
        _regular(target, uid=uid, gid=gid, mode=mode, label="installed artifact")
        if _sha(target.read_bytes()) != row.get("sha256"):
            raise SnapshotAdminInstallError("installed artifact hash mismatch")
    if observed_targets != allowed_targets:
        raise SnapshotAdminInstallError("install manifest artifact inventory is incomplete")
    observed_package = {path for path in layout.package.rglob("*") if path.is_file()}
    if observed_package != expected_files - {layout.launcher}:
        expected_package = expected_files - {layout.launcher}
        missing = sorted(str(path.relative_to(layout.package))
                         for path in expected_package - observed_package)
        unexpected = sorted(str(path.relative_to(layout.package))
                            for path in observed_package - expected_package)
        raise SnapshotAdminInstallError(
            f"installed package inventory mismatch; missing={missing}; unexpected={unexpected}"
        )
    for name in (".journal.lock", ".rotation.lock"):
        path = layout.receipts / name
        _regular(path, uid=uid, gid=gid, mode=0o600, label="installed lock")
        if path.stat().st_size != 0:
            raise SnapshotAdminInstallError("installed lock must be empty")
    receipt_entries = {path.name for path in layout.receipts.iterdir()}
    if receipt_entries != {"pending", "completed", ".journal.lock", ".rotation.lock"}:
        raise SnapshotAdminInstallError("receipt root contains an unexpected entry")
    return manifest


def install(
    layout: InstallLayout = DEFAULT_LAYOUT, *,
    fault: Callable[[str], None] | None = None,
    token: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Install an inert fixed-path package; do not run status, preview, apply, or recover."""
    uid, gid = layout.expected_uid, layout.expected_gid
    _validate_layout(layout)
    for target in (layout.package, layout.launcher, layout.receipts):
        if target.exists() or target.is_symlink():
            raise SnapshotAdminInstallError("install target already exists")
    artifacts = _artifact_data(layout)
    manifest = _manifest(layout, artifacts)
    suffix = (token or (lambda: secrets.token_hex(8)))()
    if not re.fullmatch(r"[a-z0-9]{8,32}", suffix):
        raise SnapshotAdminInstallError("installer token is invalid")
    lib_stage = layout.libexec_parent / f".edge-source-snapshot-admin-{suffix}"
    receipt_stage = layout.state_base / f".admin-receipts-{suffix}"
    launcher_stage = layout.sbin_parent / f".edge-source-snapshot-admin-{suffix}"
    published: list[Path] = []
    _begin(layout)
    try:
        lib_stage.mkdir(mode=0o700)
        tools = lib_stage / "tools"
        tools.mkdir(mode=0o700)
        for name, (data, mode) in artifacts.items():
            _write_file(tools / name, data, uid=uid, gid=gid, mode=mode)
        os.chown(tools, uid, gid); os.chmod(tools, 0o750)
        _write_file(lib_stage / "INSTALL-MANIFEST.json", _canonical(manifest) + b"\n",
                    uid=uid, gid=gid, mode=0o400)
        os.chown(lib_stage, uid, gid); os.chmod(lib_stage, 0o750)
        _fsync_dir(tools); _fsync_dir(lib_stage)

        receipt_stage.mkdir(mode=0o700)
        os.chown(receipt_stage, uid, gid)
        for name in ("pending", "completed"):
            child = receipt_stage / name; child.mkdir(mode=0o700); os.chown(child, uid, gid)
        for name in (".journal.lock", ".rotation.lock"):
            _write_file(receipt_stage / name, b"", uid=uid, gid=gid, mode=0o600)
        _fsync_dir(receipt_stage)
        _write_file(launcher_stage, LAUNCHER, uid=uid, gid=gid, mode=0o750)

        if fault: fault("before_package_publish")
        os.replace(lib_stage, layout.package); published.append(layout.package)
        _fsync_dir(layout.libexec_parent)
        if fault: fault("after_package_publish")
        os.replace(receipt_stage, layout.receipts); published.append(layout.receipts)
        _fsync_dir(layout.state_base)
        if fault: fault("after_receipts_publish")
        os.replace(launcher_stage, layout.launcher); published.append(layout.launcher)
        _fsync_dir(layout.sbin_parent)
        if fault: fault("after_launcher_publish")
        installed = _validate_installed(layout)
        _finish(layout)
        return {
            "schema": RESULT_SCHEMA, "operation": "install", "installed": True,
            "manifest_sha256": _sha(_canonical(installed)), "launcher_published_last": True,
            "snapshots_touched": False, "credential_present": False, "llm_invoked": False,
            "network_used": False, "heartbeat_touched": False, "timer_touched": False,
        }
    except BaseException:
        cleanup_ok = True
        try:
            if layout.launcher in published:
                if _sha(layout.launcher.read_bytes()) != _sha(LAUNCHER):
                    raise SnapshotAdminInstallError("published launcher changed during cleanup")
                layout.launcher.unlink(); _fsync_dir(layout.sbin_parent)
            if layout.receipts in published:
                if _receipt_records_exist(layout.receipts):
                    raise SnapshotAdminInstallError("published receipt tree is not empty")
                _remove_tree(layout.receipts); _fsync_dir(layout.state_base)
            if layout.package in published:
                _validate_installed_package_only(layout, manifest)
                _remove_tree(layout.package); _fsync_dir(layout.libexec_parent)
            for staged in (launcher_stage, receipt_stage, lib_stage):
                if staged.is_dir(): _remove_tree(staged)
                elif staged.exists(): staged.unlink()
            _finish(layout)
        except BaseException:
            cleanup_ok = False
        if not cleanup_ok:
            raise SnapshotAdminInstallError("install failed and exact cleanup requires review")
        raise


def _validate_installed_package_only(layout: InstallLayout, manifest: dict[str, Any]) -> None:
    expected = {layout.package / "INSTALL-MANIFEST.json"}
    for row in manifest["artifacts"]:
        target = Path(row["target"])
        if target == layout.launcher:
            continue
        expected.add(target)
        _regular(target, uid=layout.expected_uid, gid=layout.expected_gid,
                 mode=int(row["mode"], 8), label="installed package artifact")
        if _sha(target.read_bytes()) != row["sha256"]:
            raise SnapshotAdminInstallError("installed package artifact changed")
    observed = {path for path in layout.package.rglob("*") if path.is_file()}
    if observed != expected:
        raise SnapshotAdminInstallError("installed package inventory changed")


def rollback(
    layout: InstallLayout = DEFAULT_LAYOUT, *,
    fault: Callable[[str], None] | None = None,
    token: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Remove an unused exact installation; refuse after migration, receipts, or drift."""
    _validate_layout(layout)
    manifest = _validate_installed(layout)
    if _receipt_records_exist(layout.receipts):
        raise SnapshotAdminInstallError("operational receipts exist; install rollback is forbidden")
    if any((layout.snapshots / name).exists() or (layout.snapshots / name).is_symlink()
           for name in ("index.json", "generations", "rotation.pending")):
        raise SnapshotAdminInstallError("snapshot migration state exists; install rollback is forbidden")
    suffix = (token or (lambda: secrets.token_hex(8)))()
    if not re.fullmatch(r"[a-z0-9]{8,32}", suffix):
        raise SnapshotAdminInstallError("rollback token is invalid")
    launcher_q = layout.sbin_parent / f".edge-source-snapshot-admin-rollback-{suffix}"
    package_q = layout.libexec_parent / f".edge-source-snapshot-admin-rollback-{suffix}"
    receipts_q = layout.state_base / f".admin-receipts-rollback-{suffix}"
    moved: list[tuple[Path, Path]] = []
    committed = False
    _begin(layout)
    try:
        os.replace(layout.launcher, launcher_q); moved.append((launcher_q, layout.launcher))
        _fsync_dir(layout.sbin_parent)
        if fault: fault("after_launcher_quarantine")
        os.replace(layout.package, package_q); moved.append((package_q, layout.package))
        _fsync_dir(layout.libexec_parent)
        if fault: fault("after_package_quarantine")
        os.replace(layout.receipts, receipts_q); moved.append((receipts_q, layout.receipts))
        _fsync_dir(layout.state_base)
        committed = True
        if fault: fault("after_rollback_commit")
        launcher_q.unlink(); _fsync_dir(layout.sbin_parent)
        _remove_tree(package_q); _fsync_dir(layout.libexec_parent)
        _remove_tree(receipts_q); _fsync_dir(layout.state_base)
        _finish(layout)
        return {
            "schema": RESULT_SCHEMA, "operation": "rollback", "installed": False,
            "manifest_sha256": _sha(_canonical(manifest)), "snapshots_touched": False,
            "operational_receipts_deleted": False,
            "empty_receipt_infrastructure_removed": True,
            "operational_receipts_existed": False,
            "credential_present": False, "llm_invoked": False, "network_used": False,
            "heartbeat_touched": False, "timer_touched": False,
        }
    except BaseException as exc:
        if not committed:
            try:
                for quarantined, original in reversed(moved):
                    os.replace(quarantined, original); _fsync_dir(original.parent)
                _finish(layout)
            except BaseException as restore_exc:
                raise SnapshotAdminInstallError("rollback pre-commit restoration requires review") \
                    from restore_exc
            raise
        raise SnapshotAdminRollbackCommitted(
            "rollback committed; exact quarantine cleanup requires review"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edge-source-snapshot-admin-install")
    parser.add_argument("operation", choices=("install", "rollback"))
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        print(json.dumps({"schema": RESULT_SCHEMA, "ok": False,
                          "error": "root identity required"}, sort_keys=True), file=sys.stderr)
        return 2
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = install() if args.operation == "install" else rollback()
    except (SnapshotAdminInstallError, OSError) as exc:
        message = str(exc) if isinstance(exc, SnapshotAdminInstallError) \
            else f"filesystem operation failed: {type(exc).__name__}"
        print(json.dumps({"schema": RESULT_SCHEMA, "ok": False, "error": message},
                         sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
