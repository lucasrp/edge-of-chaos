#!/usr/bin/env python3
"""rollup-health-v2 — compute the event-backed health v2 snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from _shared.health_runtime import build_health_snapshot, write_health_snapshot  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute health v2 snapshot from runtime facts and projections")
    parser.add_argument("--write", action="store_true", help="Write to health/current.json in addition to printing")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.write:
        payload = write_health_snapshot()
    else:
        payload = build_health_snapshot()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
