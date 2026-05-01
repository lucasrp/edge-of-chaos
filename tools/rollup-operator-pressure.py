#!/usr/bin/env python3
"""rollup-operator-pressure — refresh the operator-pressure CQRS projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))

from paths import OPERATOR_PRESSURE_PROJECTION_FILE  # noqa: E402
from _shared.operator_pressure import (  # noqa: E402
    build_operator_pressure_projection,
    write_operator_pressure_projection,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project recent Claude sessions into operator-pressure read models")
    parser.add_argument("--json", action="store_true", help="Print full JSON projection")
    parser.add_argument("--no-write", action="store_true", help="Build the projection without writing state files or emitting events")
    parser.add_argument("--projection-path", type=Path, default=OPERATOR_PRESSURE_PROJECTION_FILE)
    parser.add_argument("--project-dir", type=Path, default=None, help="Override Claude project directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = (
        build_operator_pressure_projection(
            project_dir=args.project_dir,
            projection_path=args.projection_path,
            write_layers=False,
            emit_events=False,
            allow_llm=False,
        )
        if args.no_write
        else write_operator_pressure_projection(project_dir=args.project_dir, projection_path=args.projection_path)
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        summary = payload.get("summary") or {}
        print(
            "OK: "
            f"{args.projection_path} "
            f"(status={payload.get('status')} "
            f"items={summary.get('item_total', 0)} "
            f"sessions={summary.get('session_total', 0)} "
            f"messages={summary.get('message_total', 0)} "
            f"render={summary.get('render_mode', '')})"
        )
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
