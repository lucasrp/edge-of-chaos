#!/usr/bin/env python3
"""Backfill terminal pipeline PhaseCompleted facts for legacy publishes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import STATE_EVENTS_FILE  # noqa: E402

sys.path.insert(0, str(SCRIPT_DIR))
from _shared.telemetry import emit_shadow_event  # noqa: E402


def _load_pipeline_module():
    path = SCRIPT_DIR / "rollup-pipeline-state.py"
    spec = importlib.util.spec_from_file_location("rollup_pipeline_state", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_backfill(limit: int) -> list[dict[str, Any]]:
    module = _load_pipeline_module()
    projection = module.build_projection(limit=max(1, limit))
    return [
        item
        for item in (projection.get("attention_artifacts") or [])
        if item.get("status") == "orphaned_publish"
    ]


def emit_backfills(items: list[dict[str, Any]], *, reason: str) -> list[dict[str, Any]]:
    emitted: list[dict[str, Any]] = []
    for item in items:
        artifact = str(item.get("artifact") or "").strip()
        if not artifact:
            continue
        payload = {
            "pipeline": "consolidate-state",
            "phase": "pipeline",
            "status": "completed",
            "ok": True,
            "reason": reason,
            "backfill": True,
            "source": "backfill-pipeline-phase-events",
            "source_event_lines": item.get("event_lines") or [],
        }
        emit_shadow_event(
            "PhaseCompleted",
            actor="pipeline-state-backfill",
            artifact=artifact,
            cycle_id=item.get("cycle_id") or None,
            payload=payload,
        )
        emitted.append({"artifact": artifact, "cycle_id": item.get("cycle_id") or "", "payload": payload})
    return emitted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill terminal PhaseCompleted facts for legacy ArtifactPublished events")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--reason",
        default="legacy ArtifactPublished before PhaseCompleted instrumentation",
        help="Reason stored in the backfill event payload",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    items = build_backfill(args.limit)
    emitted = [] if args.dry_run else emit_backfills(items, reason=args.reason)
    payload = {
        "ok": True,
        "events_path": str(STATE_EVENTS_FILE),
        "dry_run": bool(args.dry_run),
        "candidate_total": len(items),
        "emitted_total": len(emitted),
        "candidates": items,
        "emitted": emitted,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        action = "would backfill" if args.dry_run else "backfilled"
        print(f"{action}: {payload['emitted_total'] if not args.dry_run else payload['candidate_total']} legacy pipeline publish event(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
