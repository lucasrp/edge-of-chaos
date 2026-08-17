"""Durable fixed-path receipt journal for state-changing snapshot administration.

Status and preview remain zero-write. Apply and recover create a durable intent before mutation,
then a durable completion record before clearing that intent. No service, timer, network, LLM,
credential, arbitrary path, or force interface exists here.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Callable, Iterator

from tools import source_rotation as rotation
from tools import source_snapshot_admin as admin


INTENT_SCHEMA = "edge.source-snapshot-admin-intent/v1"
COMPLETION_SCHEMA = "edge.source-snapshot-admin-completion/v1"
MEDIATED_SCHEMA = "edge.source-snapshot-admin-mediated-receipt/v1"
TXID = re.compile(r"[a-z0-9][a-z0-9_-]{15,63}")


@dataclass(frozen=True)
class JournalConfig:
    root: Path
    lock_path: Path
    expected_uid: int
    expected_gid: int


DEFAULT_JOURNAL = JournalConfig(
    root=Path("/var/lib/edge-source-collector/admin-receipts"),
    lock_path=Path("/var/lib/edge-source-collector/admin-receipts/.journal.lock"),
    expected_uid=0,
    expected_gid=0,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc(clock: Callable[[], datetime]) -> str:
    return clock().astimezone(timezone.utc).isoformat()


def _validate_directory(path: Path, *, uid: int, gid: int, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise rotation.SourceRotationError(f"{label} must be one existing real absolute directory")
    info = path.stat()
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, 0o700):
        raise rotation.SourceRotationError(f"{label} owner or mode is invalid")
    return path


def _journal_directories(config: JournalConfig) -> tuple[Path, Path, Path]:
    root = _validate_directory(
        config.root, uid=config.expected_uid, gid=config.expected_gid, label="receipt root"
    )
    pending = _validate_directory(
        root / "pending", uid=config.expected_uid, gid=config.expected_gid,
        label="pending receipt directory",
    )
    completed = _validate_directory(
        root / "completed", uid=config.expected_uid, gid=config.expected_gid,
        label="completed receipt directory",
    )
    return root, pending, completed


def _regular_record(path: Path, *, uid: int, gid: int, label: str) -> dict[str, Any]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise rotation.SourceRotationError(f"{label} is missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (
        info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)
    ) != (uid, gid, 0o400):
        raise rotation.SourceRotationError(f"{label} owner, mode, or type is invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise rotation.SourceRotationError(f"{label} is unreadable or invalid") from exc
    if not isinstance(value, dict):
        raise rotation.SourceRotationError(f"{label} must contain one object")
    return value


def _list_records(directory: Path, *, uid: int, gid: int, label: str) -> list[Path]:
    records = []
    for path in directory.iterdir():
        if path.is_symlink() or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{15,63}\.json", path.name):
            raise rotation.SourceRotationError(f"{label} contains an unexpected entry")
        _regular_record(path, uid=uid, gid=gid, label=label)
        records.append(path)
    return sorted(records)


def _write_record(directory: Path, transaction_id: str, payload: dict[str, Any]) -> Path:
    if not TXID.fullmatch(transaction_id):
        raise rotation.SourceRotationError("journal transaction identifier is invalid")
    target = directory / f"{transaction_id}.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o400)
    try:
        data = _canonical(payload) + b"\n"
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise rotation.SourceRotationError("journal write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return target


def _remove_record(path: Path) -> None:
    parent = path.parent
    path.unlink()
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def _journal_lock(path: Path) -> Iterator[None]:
    if not path.is_absolute() or path.is_symlink():
        raise rotation.SourceRotationError("journal lock path must be absolute and not a symlink")
    try:
        fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError as exc:
        raise rotation.SourceRotationError("precreated journal lock is missing") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)
        ) != (os.geteuid(), os.getegid(), 0o600):
            raise rotation.SourceRotationError("journal lock owner, mode, or type is invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise rotation.SourceRotationError("another journal operation holds the lock") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _intent(command: str, reviewed_hash: str, transaction_id: str,
            created_at: str) -> dict[str, Any]:
    payload = {
        "schema": INTENT_SCHEMA, "transaction_id": transaction_id,
        "command": command, "reviewed_sha256": reviewed_hash,
        "created_at": created_at,
    }
    payload["intent_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


def _validate_intent(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != INTENT_SCHEMA or not TXID.fullmatch(str(value.get("transaction_id", ""))):
        raise rotation.SourceRotationError("pending journal intent is invalid")
    if value.get("command") not in {"apply", "recover"} or not re.fullmatch(
        r"[0-9a-f]{64}", str(value.get("reviewed_sha256", ""))
    ):
        raise rotation.SourceRotationError("pending journal intent command is invalid")
    supplied = value.get("intent_sha256")
    core = {key: item for key, item in value.items() if key != "intent_sha256"}
    if supplied != hashlib.sha256(_canonical(core)).hexdigest():
        raise rotation.SourceRotationError("pending journal intent integrity check failed")
    return value


def _completion(transaction_id: str, intent: dict[str, Any], *, outcome: str,
                completed_at: str, admin_receipt: dict[str, Any] | None) -> dict[str, Any]:
    payload = {
        "schema": COMPLETION_SCHEMA, "transaction_id": transaction_id,
        "intent_sha256": intent["intent_sha256"], "command": intent["command"],
        "outcome": outcome, "completed_at": completed_at,
        "admin_receipt": admin_receipt,
        "credential_present": False, "llm_invoked": False, "network_used": False,
        "heartbeat_touched": False, "timer_touched": False,
    }
    payload["completion_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


def _validate_completion(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != COMPLETION_SCHEMA or not TXID.fullmatch(
        str(value.get("transaction_id", ""))
    ):
        raise rotation.SourceRotationError("completed journal receipt is invalid")
    if value.get("command") not in {"apply", "recover"} or value.get("outcome") not in {
        "completed", "reconciled", "rejected-before-commit",
    }:
        raise rotation.SourceRotationError("completed journal receipt outcome is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("intent_sha256", ""))):
        raise rotation.SourceRotationError("completed journal intent hash is invalid")
    if any(value.get(flag) is not False for flag in (
        "credential_present", "llm_invoked", "network_used", "heartbeat_touched", "timer_touched",
    )):
        raise rotation.SourceRotationError("completed journal authority assertions are invalid")
    supplied = value.get("completion_sha256")
    core = {key: item for key, item in value.items() if key != "completion_sha256"}
    if supplied != hashlib.sha256(_canonical(core)).hexdigest():
        raise rotation.SourceRotationError("completed journal receipt integrity check failed")
    return value


def _status_with_journal(receipt: dict[str, Any], pending: list[Path]) -> dict[str, Any]:
    enriched = dict(receipt)
    enriched["journal"] = {
        "pending_transactions": [path.stem for path in pending],
        "pending_count": len(pending), "state_changed": False,
    }
    enriched["schema"] = MEDIATED_SCHEMA
    return enriched


def _prevalidate_change(args: Any, config: admin.AdminConfig) -> tuple[str, dict[str, Any]]:
    if args.command == "apply":
        reviewed = admin._sha256(args.preview_sha256, label="preview hash")
        preview = rotation.preview_legacy_migration(
            config.snapshots_root, generation_id=config.generation_id,
            expected_uid=config.expected_uid, expected_gid=config.expected_gid,
            max_candidate_bytes=config.max_candidate_bytes,
            safety_margin_bytes=config.safety_margin_bytes,
        )
        if preview["preview_sha256"] != reviewed:
            raise rotation.SourceRotationError("live preview does not match reviewed preview hash")
        return reviewed, preview
    reviewed = admin._sha256(args.index_sha256, label="index hash")
    state = rotation.inspect_pending_transaction(
        config.snapshots_root, expected_uid=config.expected_uid,
        expected_gid=config.expected_gid,
    )
    if state.get("status") != "recoverable_clean" or state.get("index_sha256") != reviewed:
        raise rotation.SourceRotationError("pending state does not match reviewed clean index")
    return reviewed, state


def _execute_prevalidated_change(
    argv: list[str], *, args: Any, prepared: dict[str, Any], config: admin.AdminConfig,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    if args.command == "apply":
        result = rotation.apply_legacy_migration(
            config.snapshots_root, lock_path=config.lock_path, preview=prepared,
            committed_at=_utc(clock), expected_uid=config.expected_uid,
            expected_gid=config.expected_gid,
        )
        result["reviewed_preview_sha256"] = args.preview_sha256
        return admin._receipt("apply", result, changed=True)
    return admin.execute(argv, config=config, now=clock)


def _reconcile_pending(
    argv: list[str], *, args: Any, config: admin.AdminConfig, journal: JournalConfig,
    pending_path: Path, completed_dir: Path, clock: Callable[[], datetime],
    fault: Callable[[str], None] | None,
) -> dict[str, Any]:
    if args.command != "recover":
        raise rotation.SourceRotationError("unresolved journal intent blocks state-changing command")
    reviewed = admin._sha256(args.index_sha256, label="index hash")
    intent = _validate_intent(_regular_record(
        pending_path, uid=journal.expected_uid, gid=journal.expected_gid,
        label="pending journal intent",
    ))
    state = rotation.snapshot_status(
        config.snapshots_root, expected_uid=config.expected_uid,
        expected_gid=config.expected_gid,
    )
    if state.get("index_sha256") != reviewed or state.get("status") not in {
        "indexed_valid", "recoverable_clean",
    }:
        raise rotation.SourceRotationError("current index does not match reviewed recovery hash")
    completed_path = completed_dir / pending_path.name
    if completed_path.exists() or completed_path.is_symlink():
        completion = _validate_completion(_regular_record(
            completed_path, uid=journal.expected_uid, gid=journal.expected_gid,
            label="completed journal receipt",
        ))
        if completion.get("intent_sha256") != intent["intent_sha256"]:
            raise rotation.SourceRotationError("completed receipt does not match pending intent")
        _remove_record(pending_path)
        return {
            "schema": MEDIATED_SCHEMA, "command": "recover", "ok": True,
            "state_changed": True, "result": {
                "journal_reconciled": True, "snapshot_recovery_invoked": False,
                "index_sha256": reviewed,
            },
        }
    snapshot_receipt = None
    if state["status"] == "recoverable_clean":
        snapshot_receipt = admin.execute(argv, config=config, now=clock)
    if fault:
        fault("after_reconciliation_admin")
    completion = _completion(
        intent["transaction_id"], intent, outcome="reconciled",
        completed_at=_utc(clock), admin_receipt=snapshot_receipt,
    )
    _write_record(completed_dir, intent["transaction_id"], completion)
    if fault:
        fault("after_reconciliation_completion")
    _remove_record(pending_path)
    return {
        "schema": MEDIATED_SCHEMA, "command": "recover", "ok": True,
        "state_changed": True, "result": {
            "journal_reconciled": True,
            "snapshot_recovery_invoked": snapshot_receipt is not None,
            "index_sha256": reviewed,
        },
    }


def execute_durable(
    argv: list[str], *, config: admin.AdminConfig = admin.DEFAULT_CONFIG,
    journal: JournalConfig = DEFAULT_JOURNAL,
    now: Callable[[], datetime] | None = None,
    transaction_id: Callable[[], str] | None = None,
    fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute one command with durable intent/completion semantics for mutations."""
    args = admin.parse_operator_args(argv)
    clock = now or (lambda: datetime.now(timezone.utc))
    tx_factory = transaction_id or (lambda: "tx_" + secrets.token_hex(16))
    _root, pending_dir, completed_dir = _journal_directories(journal)
    with _journal_lock(journal.lock_path):
        pending = _list_records(
            pending_dir, uid=journal.expected_uid, gid=journal.expected_gid,
            label="pending receipt directory",
        )
        completed_records = _list_records(
            completed_dir, uid=journal.expected_uid, gid=journal.expected_gid,
            label="completed receipt directory",
        )
        for path in pending:
            intent = _validate_intent(_regular_record(
                path, uid=journal.expected_uid, gid=journal.expected_gid,
                label="pending journal intent",
            ))
            if intent["transaction_id"] != path.stem:
                raise rotation.SourceRotationError("pending journal filename does not match intent")
        for path in completed_records:
            completion = _validate_completion(_regular_record(
                path, uid=journal.expected_uid, gid=journal.expected_gid,
                label="completed journal receipt",
            ))
            if completion["transaction_id"] != path.stem:
                raise rotation.SourceRotationError("completed journal filename does not match receipt")
        if args.command in {"status", "preview"}:
            return _status_with_journal(admin.execute(argv, config=config, now=clock), pending)
        if pending:
            if len(pending) != 1:
                raise rotation.SourceRotationError("multiple unresolved journal intents require review")
            return _reconcile_pending(
                argv, args=args, config=config, journal=journal,
                pending_path=pending[0], completed_dir=completed_dir, clock=clock, fault=fault,
            )
        reviewed, prepared = _prevalidate_change(args, config)
        txid = tx_factory()
        if not TXID.fullmatch(txid):
            raise rotation.SourceRotationError("generated transaction identifier is invalid")
        intent = _intent(args.command, reviewed, txid, _utc(clock))
        intent_path = _write_record(pending_dir, txid, intent)
        if fault:
            fault("after_intent")
        try:
            receipt = _execute_prevalidated_change(
                argv, args=args, prepared=prepared, config=config, clock=clock,
            )
            if fault:
                fault("after_admin")
            completion = _completion(
                txid, intent, outcome="completed", completed_at=_utc(clock),
                admin_receipt=receipt,
            )
            _write_record(completed_dir, txid, completion)
            if fault:
                fault("after_completion")
            _remove_record(intent_path)
            mediated = dict(receipt)
            mediated["schema"] = MEDIATED_SCHEMA
            mediated["journal"] = {
                "transaction_id": txid,
                "completion_sha256": completion["completion_sha256"],
                "pending": False,
            }
            return mediated
        except rotation.RotationCommittedCleanupRequired:
            raise
        except rotation.SourceRotationError:
            rejected = _completion(
                txid, intent, outcome="rejected-before-commit", completed_at=_utc(clock),
                admin_receipt=None,
            )
            _write_record(completed_dir, txid, rejected)
            _remove_record(intent_path)
            raise


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        print(json.dumps({"schema": MEDIATED_SCHEMA, "ok": False,
                          "error": "root identity required"}, sort_keys=True), file=sys.stderr)
        return 2
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        receipt = execute_durable(arguments)
    except (rotation.SourceRotationError, OSError) as exc:
        message = str(exc) if isinstance(exc, rotation.SourceRotationError) \
            else f"filesystem operation failed: {type(exc).__name__}"
        print(json.dumps({"schema": MEDIATED_SCHEMA, "ok": False,
                          "error": message}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0
