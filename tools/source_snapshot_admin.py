"""Fixed-path operator interface for sealed source-snapshot administration.

Repository code only: creating this module does not install or invoke the interface.  The real CLI
has no path, force, timer, retention, delete, or arbitrary configuration flags.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable

from tools import source_rotation as rotation


RECEIPT_SCHEMA = "edge.source-snapshot-admin-receipt/v1"


@dataclass(frozen=True)
class AdminConfig:
    snapshots_root: Path
    lock_path: Path
    expected_uid: int
    expected_gid: int
    generation_id: str
    max_candidate_bytes: int
    safety_margin_bytes: int


DEFAULT_CONFIG = AdminConfig(
    snapshots_root=Path("/var/lib/edge-source-collector/snapshots"),
    lock_path=Path("/var/lib/edge-source-collector/admin-receipts/.rotation.lock"),
    expected_uid=0,
    expected_gid=0,
    generation_id="pb6i-initial-20260814",
    max_candidate_bytes=5 * 1024 * 1024,
    safety_margin_bytes=64 * 1024 * 1024,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edge-source-snapshot-admin",
        description="Manual fixed-policy administration of the sealed source snapshot.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="validate and report current state without writing")
    commands.add_parser("preview", help="produce a read-only legacy migration preview")
    apply = commands.add_parser("apply", help="apply exactly one reviewed migration preview")
    apply.add_argument("--preview-sha256", required=True, metavar="SHA256")
    recover = commands.add_parser("recover", help="clear one clean reviewed transaction marker")
    recover.add_argument("--index-sha256", required=True, metavar="SHA256")
    return parser


def parse_operator_args(argv: list[str]) -> argparse.Namespace:
    """Parse the intentionally tiny public command surface for an outer root mediator."""
    return _parser().parse_args(argv)


def _sha256(value: str, *, label: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value or ""):
        raise rotation.SourceRotationError(f"{label} must be one lowercase SHA-256")
    return value


def _receipt(command: str, result: dict, *, changed: bool) -> dict:
    return {
        "schema": RECEIPT_SCHEMA,
        "command": command,
        "ok": True,
        "result": result,
        "state_changed": changed,
        "credential_present": False,
        "llm_invoked": False,
        "network_used": False,
        "heartbeat_touched": False,
        "timer_touched": False,
    }


def execute(
    argv: list[str], *, config: AdminConfig = DEFAULT_CONFIG,
    now: Callable[[], datetime] | None = None,
) -> dict:
    """Execute one fixed-policy command; tests may inject only a private in-process layout."""
    args = parse_operator_args(argv)
    clock = now or (lambda: datetime.now(timezone.utc))
    if args.command == "status":
        result = rotation.snapshot_status(
            config.snapshots_root, expected_uid=config.expected_uid,
            expected_gid=config.expected_gid,
        )
        return _receipt("status", result, changed=False)
    if args.command == "preview":
        result = rotation.preview_legacy_migration(
            config.snapshots_root, generation_id=config.generation_id,
            expected_uid=config.expected_uid, expected_gid=config.expected_gid,
            max_candidate_bytes=config.max_candidate_bytes,
            safety_margin_bytes=config.safety_margin_bytes,
        )
        return _receipt("preview", result, changed=False)
    if args.command == "apply":
        reviewed = _sha256(args.preview_sha256, label="preview hash")
        preview = rotation.preview_legacy_migration(
            config.snapshots_root, generation_id=config.generation_id,
            expected_uid=config.expected_uid, expected_gid=config.expected_gid,
            max_candidate_bytes=config.max_candidate_bytes,
            safety_margin_bytes=config.safety_margin_bytes,
        )
        if preview["preview_sha256"] != reviewed:
            raise rotation.SourceRotationError("live preview does not match reviewed preview hash")
        result = rotation.apply_legacy_migration(
            config.snapshots_root, lock_path=config.lock_path, preview=preview,
            committed_at=clock().astimezone(timezone.utc).isoformat(),
            expected_uid=config.expected_uid, expected_gid=config.expected_gid,
        )
        result["reviewed_preview_sha256"] = reviewed
        return _receipt("apply", result, changed=True)
    reviewed = _sha256(args.index_sha256, label="index hash")
    status = rotation.inspect_pending_transaction(
        config.snapshots_root, expected_uid=config.expected_uid,
        expected_gid=config.expected_gid,
    )
    if status.get("status") != "recoverable_clean" or status.get("index_sha256") != reviewed:
        raise rotation.SourceRotationError("pending state does not match reviewed clean index")
    result = rotation.clear_recovered_transaction(
        config.snapshots_root, lock_path=config.lock_path,
        expected_index_sha256=reviewed, expected_uid=config.expected_uid,
        expected_gid=config.expected_gid,
    )
    return _receipt("recover", result, changed=True)


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        print(json.dumps({"schema": RECEIPT_SCHEMA, "ok": False,
                          "error": "root identity required"}, sort_keys=True), file=sys.stderr)
        return 2
    try:
        receipt = execute(list(sys.argv[1:] if argv is None else argv))
    except rotation.SourceRotationError as exc:
        print(json.dumps({"schema": RECEIPT_SCHEMA, "ok": False,
                          "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
