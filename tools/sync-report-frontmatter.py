#!/usr/bin/env python3
"""Synchronize a blog entry's frontmatter report field."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def sync_report(entry_path: Path, expected_report: str) -> str:
    raw = entry_path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"missing frontmatter in {entry_path}")

    try:
        parsed = yaml.safe_load(parts[1]) or {}
    except Exception as exc:  # pragma: no cover - exact yaml message varies
        raise ValueError(f"invalid frontmatter YAML in {entry_path}: {exc}") from exc

    current = str(parsed.get("report") or "").strip()
    if current == expected_report:
        return f"matched:{expected_report}"

    lines = parts[1].splitlines()
    updated_lines: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("report:"):
            if not replaced:
                updated_lines.append(f"report: {expected_report}")
                replaced = True
            continue
        updated_lines.append(line)

    if not replaced:
        while updated_lines and not updated_lines[-1].strip():
            updated_lines.pop()
        updated_lines.append(f"report: {expected_report}")

    new_frontmatter = "\n".join(updated_lines).strip("\n")
    entry_path.write_text(
        f"{parts[0]}---\n{new_frontmatter}\n---{parts[2]}",
        encoding="utf-8",
    )
    previous = current or "<missing>"
    return f"updated:{previous}->{expected_report}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path)
    parser.add_argument("expected_report")
    args = parser.parse_args()

    try:
        result = sync_report(args.entry, args.expected_report)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 65

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
