#!/usr/bin/env python3
"""Normalize blog entry frontmatter before publication."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml


def _yaml_scalar(value: str) -> str:
    text = str(value).strip()
    if re.fullmatch(r"[A-Za-z0-9_.@/-]+", text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _list_literal(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_scalar(value) for value in values) + "]"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _open_gap_threads(frontmatter: dict) -> list[str]:
    threads: list[str] = []
    open_gaps = frontmatter.get("open_gaps", [])
    if isinstance(open_gaps, list):
        for gap in open_gaps:
            if not isinstance(gap, dict):
                continue
            threads.extend(_as_list(gap.get("threads")))
    seen: set[str] = set()
    unique: list[str] = []
    for thread in threads:
        if thread not in seen:
            seen.add(thread)
            unique.append(thread)
    return unique


def _keyword_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _derived_keywords(frontmatter: dict, threads: list[str], expected_report: str) -> list[str]:
    stopwords = {
        "and",
        "com",
        "das",
        "dos",
        "for",
        "para",
        "por",
        "the",
        "uma",
    }
    raw_values: list[str] = []
    raw_values.extend(_as_list(frontmatter.get("tags")))
    raw_values.extend(threads)
    raw_values.append(str(frontmatter.get("title") or ""))
    raw_values.append(Path(expected_report).stem)

    keywords: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in re.split(r"[\s,/|:;()[\]{}]+", raw):
            token = _keyword_token(part)
            if len(token) < 3 or token in stopwords or token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= 12:
                return keywords
    return keywords or ["artifact"]


def _replace_or_append(lines: list[str], key: str, rendered: str) -> tuple[list[str], bool]:
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}:"):
            if not replaced:
                updated.append(rendered)
                replaced = True
            continue
        updated.append(line)
    if replaced:
        return updated, True

    while updated and not updated[-1].strip():
        updated.pop()
    updated.append(rendered)
    return updated, False


def sync_report(entry_path: Path, expected_report: str) -> str:
    raw = entry_path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"missing frontmatter in {entry_path}")

    try:
        parsed = yaml.safe_load(parts[1]) or {}
    except Exception as exc:  # pragma: no cover - exact yaml message varies
        raise ValueError(f"invalid frontmatter YAML in {entry_path}: {exc}") from exc

    lines = parts[1].splitlines()
    changes: list[str] = []

    current = str(parsed.get("report") or "").strip()
    if current == expected_report:
        changes.append(f"report=matched:{expected_report}")
        updated_lines = lines
    else:
        updated_lines, _ = _replace_or_append(lines, "report", f"report: {expected_report}")
        previous = current or "<missing>"
        changes.append(f"report=updated:{previous}->{expected_report}")

    threads = _as_list(parsed.get("threads"))
    if not threads:
        threads = _open_gap_threads(parsed)
        if threads:
            updated_lines, _ = _replace_or_append(
                updated_lines,
                "threads",
                f"threads: {_list_literal(threads)}",
            )
            changes.append(f"threads=derived:{len(threads)}")

    keywords = _as_list(parsed.get("keywords"))
    if not keywords:
        keywords = _derived_keywords(parsed, threads, expected_report)
        updated_lines, _ = _replace_or_append(
            updated_lines,
            "keywords",
            f"keywords: {_list_literal(keywords)}",
        )
        changes.append(f"keywords=derived:{len(keywords)}")

    if changes == [f"report=matched:{expected_report}"]:
        return f"matched:{expected_report}"

    new_frontmatter = "\n".join(updated_lines).strip("\n")
    entry_path.write_text(
        f"{parts[0]}---\n{new_frontmatter}\n---{parts[2]}",
        encoding="utf-8",
    )
    return " ".join(changes)


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
