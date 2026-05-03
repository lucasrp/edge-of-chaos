"""Curated corpus citation helpers for edge-memory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import EDGE_REPO_DIR, EDGE_STATE_DIR, ENTRIES_DIR, REPORTS_DIR  # noqa: E402

from db import ensure_db  # noqa: E402

CITATION_BOOST_FACTOR = 0.1
REFERENCE_KEYS = (
    "corpus_references",
    "citations",
    "references",
    "bibliography",
    "source_entries",
    "related_entries",
)
DICT_PATH_KEYS = ("cited_path", "path", "entry", "report", "source_path", "source", "url")
PATH_RE = re.compile(
    r"(?P<path>(?:/?(?:[\w.-]+/)*[\w.-]+|[\w.-]+)\.(?:md|html))",
    re.I,
)


def _read_yamlish(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            data = yaml.safe_load(raw) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    if not raw.startswith("---"):
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _iter_reference_specs(value: Any, *, inherited_context: str = "curated_reference") -> Iterable[tuple[str, str]]:
    if value is None:
        return
    if isinstance(value, dict):
        context = str(value.get("context") or value.get("role") or inherited_context).strip() or inherited_context
        for key in DICT_PATH_KEYS:
            if key in value:
                yield from _iter_reference_specs(value.get(key), inherited_context=context)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_reference_specs(item, inherited_context=inherited_context)
        return

    text = str(value or "").strip()
    if not text:
        return
    markdown_target = re.search(r"\[[^\]]+\]\(([^)]+)\)", text)
    if markdown_target:
        text = markdown_target.group(1).strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", text, flags=re.I):
        return
    matches = list(PATH_RE.finditer(text))
    if matches:
        for match in matches:
            yield match.group("path"), inherited_context
    else:
        yield text.strip("`'\" "), inherited_context


def references_from_artifacts(paths: list[Path]) -> list[tuple[str, str]]:
    """Extract curated corpus reference paths from entry/report metadata."""
    refs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        fm = _read_yamlish(path)
        for key in REFERENCE_KEYS:
            for raw_path, context in _iter_reference_specs(fm.get(key)):
                item = (raw_path, context)
                if item not in seen:
                    seen.add(item)
                    refs.append(item)
    return refs


def _candidate_paths(raw_path: str) -> list[Path]:
    raw = str(raw_path or "").strip().strip("`'\"")
    if not raw:
        return []
    path = Path(raw).expanduser()
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend(
            [
                EDGE_STATE_DIR / path,
                EDGE_REPO_DIR / path,
                ENTRIES_DIR / path.name if path.suffix == ".md" else EDGE_STATE_DIR / path,
                REPORTS_DIR / path.name if path.suffix == ".html" else EDGE_STATE_DIR / path,
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _known_document_path(raw_path: str, conn) -> str | None:
    candidates = [str(path.resolve(strict=False)) for path in _candidate_paths(raw_path)]
    if not candidates:
        return None
    placeholders = ",".join("?" for _ in candidates)
    row = conn.execute(
        f"SELECT path FROM documents WHERE path IN ({placeholders}) LIMIT 1",
        candidates,
    ).fetchone()
    if row:
        return str(row["path"])
    basename = Path(str(raw_path)).name
    if basename:
        row = conn.execute(
            "SELECT path FROM documents WHERE path LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%/{basename}",),
        ).fetchone()
        if row:
            return str(row["path"])
    return None


def _normalize_source_path(source_path: str) -> str:
    candidates = _candidate_paths(source_path)
    if candidates:
        return str(candidates[0].resolve(strict=False))
    return str(source_path)


def record_citations(
    source_path: str,
    references: Iterable[str | tuple[str, str]],
    *,
    default_context: str = "curated_reference",
    conn=None,
) -> dict[str, Any]:
    """Record idempotent curated citations for one produced artifact."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()
    inserted = 0
    skipped = 0
    unknown: list[str] = []
    source = _normalize_source_path(source_path)
    ts = datetime.now(timezone.utc).isoformat()
    try:
        for item in references:
            if isinstance(item, tuple):
                raw_path, context = item
            else:
                raw_path, context = str(item), default_context
            cited = _known_document_path(str(raw_path), conn)
            if not cited:
                unknown.append(str(raw_path))
                skipped += 1
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO citations (source_path, cited_path, ts, context)
                VALUES (?, ?, ?, ?)
                """,
                (source, cited, ts, str(context or default_context)),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
        return {"inserted": inserted, "skipped": skipped, "unknown": unknown}
    finally:
        if own_conn:
            conn.close()


def citation_counts_for_paths(paths: Iterable[str], conn) -> dict[str, int]:
    unique = [path for path in dict.fromkeys(str(item) for item in paths if str(item))]
    if not unique:
        return {}
    placeholders = ",".join("?" for _ in unique)
    rows = conn.execute(
        f"""
        SELECT cited_path, COUNT(*) AS citation_count
        FROM citations
        WHERE cited_path IN ({placeholders})
        GROUP BY cited_path
        """,
        unique,
    ).fetchall()
    return {str(row["cited_path"]): int(row["citation_count"]) for row in rows}


def apply_citation_boost(results: list[dict], conn, *, boost_factor: float = CITATION_BOOST_FACTOR) -> list[dict]:
    """Annotate and rank results using curated citation counts."""
    counts = citation_counts_for_paths((item.get("path") for item in results), conn)
    boosted: list[dict] = []
    for item in results:
        path = str(item.get("path") or "")
        citation_count = int(counts.get(path, 0))
        base_score = float(item.get("score") or 0.0)
        multiplier = 1 + (boost_factor * citation_count)
        boosted_score = base_score * multiplier
        enriched = dict(item)
        enriched["base_score"] = round(base_score, 6)
        enriched["citation_count"] = citation_count
        enriched["citation_boost"] = round(multiplier, 6)
        enriched["boosted_score"] = round(boosted_score, 6)
        enriched["score"] = round(boosted_score, 6)
        boosted.append(enriched)
    boosted.sort(key=lambda item: (float(item.get("boosted_score") or 0.0), int(item.get("citation_count") or 0)), reverse=True)
    return boosted


def main() -> int:
    parser = argparse.ArgumentParser(description="Record curated corpus citations")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record citations from explicit paths")
    record.add_argument("--source", required=True, help="Produced artifact path")
    record.add_argument("--context", default="curated_reference")
    record.add_argument("paths", nargs="+", help="Cited corpus paths")

    artifacts = sub.add_parser("record-artifact", help="Extract citations from entry/report metadata")
    artifacts.add_argument("--source", required=True, help="Produced artifact path")
    artifacts.add_argument("artifacts", nargs="+", help="Entry/report files to scan")

    args = parser.parse_args()
    if args.command == "record":
        result = record_citations(args.source, args.paths, default_context=args.context)
    else:
        refs = references_from_artifacts([Path(item) for item in args.artifacts])
        result = record_citations(args.source, refs)
        result["references_found"] = len(refs)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
