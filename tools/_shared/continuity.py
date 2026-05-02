"""Entry/thread continuity facts and open-gap projections."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .telemetry import current_actor, current_cycle_id, emit_shadow_event

SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = SCRIPT_DIR.parent.parent / "config"
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))

try:
    from paths import (  # type: ignore
        CONTINUITY_DELTAS_DIR,
        ENTRIES_DIR,
        OPEN_GAPS_DIGEST_FILE,
        STATE_EVENTS_FILE,
        THREADS_DIR,
    )
except ImportError:  # pragma: no cover
    _ROOT = Path.home() / "edge"
    ENTRIES_DIR = _ROOT / "blog" / "entries"
    STATE_EVENTS_FILE = _ROOT / "state" / "events" / "log.jsonl"
    THREADS_DIR = _ROOT / "threads"
    OPEN_GAPS_DIGEST_FILE = _ROOT / "state" / "projections" / "open-gaps-digest.json"
    CONTINUITY_DELTAS_DIR = _ROOT / "state" / "projections" / "continuity-deltas"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_frontmatter(entry_path: Path) -> tuple[dict[str, Any], str]:
    raw = entry_path.read_text(encoding="utf-8", errors="replace")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, parts[2]


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.fromisoformat(raw + "T00:00:00+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _entry_href(entry_path: Path) -> str:
    return f"/entry/{entry_path.stem}"


def _gap_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("gap") or value.get("text") or "").strip()
    return str(value).lstrip("! ").strip()


def _extract_open_gaps(fm: dict[str, Any]) -> list[str]:
    gaps = [_gap_text(item) for item in (fm.get("open_gaps") or [])]
    # Compatibility for old entries: do not write this format anymore, but read
    # unresolved historical gaps until the phenotype migration runs.
    for item in fm.get("claims") or []:
        if isinstance(item, str) and item.startswith("!"):
            gaps.append(_gap_text(item))
        elif isinstance(item, dict) and str(item.get("status", "")).strip().lower() in {"open", "unverified", "disputed"}:
            gaps.append(_gap_text(item))
    seen: set[str] = set()
    unique: list[str] = []
    for gap in gaps:
        key = re.sub(r"\s+", " ", gap).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(gap)
    return unique


def _gap_occurrences(entries_dir: Path = ENTRIES_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not entries_dir.exists():
        return rows
    for entry_path in sorted(entries_dir.glob("*.md")):
        try:
            fm, _body = _read_frontmatter(entry_path)
        except Exception:
            continue
        gaps = _extract_open_gaps(fm)
        if not gaps:
            continue
        threads = _normalize_string_list(fm.get("threads") or [])
        report = str(fm.get("report") or "").strip() or None
        title = str(fm.get("title") or entry_path.stem).strip()
        date_value = str(fm.get("date") or "").strip()
        date_dt = _parse_ts(date_value) or datetime.fromtimestamp(entry_path.stat().st_mtime, timezone.utc)
        for position, text in enumerate(gaps):
            rows.append(
                {
                    "gap_id": "gap-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80],
                    "text": text,
                    "threads": list(threads),
                    "artifact_filename": entry_path.name,
                    "artifact_slug": entry_path.stem,
                    "artifact_href": _entry_href(entry_path),
                    "artifact_title": title,
                    "report": report,
                    "date": date_dt.isoformat(),
                    "position": position,
                }
            )
    return rows


def build_open_gaps_digest(entries_dir: Path = ENTRIES_DIR) -> dict[str, Any]:
    gaps = _gap_occurrences(entries_dir)
    thread_counter: Counter[str] = Counter()
    entries_with_gaps: set[str] = set()
    for item in gaps:
        entries_with_gaps.add(str(item.get("artifact_filename") or ""))
        for thread_id in item.get("threads") or []:
            thread_counter[thread_id] += 1
    oldest = sorted(gaps, key=lambda item: item.get("date") or "")[:10]
    recent = sorted(gaps, key=lambda item: item.get("date") or "", reverse=True)[:10]
    return {
        "built_at": _now().isoformat(),
        "version": 1,
        "open_total": len(gaps),
        "entries_with_gaps": len(entries_with_gaps),
        "hot_threads_by_open_gaps": [
            {"thread_id": thread_id, "open_gaps": count}
            for thread_id, count in thread_counter.most_common(8)
        ],
        "oldest_open_gaps": oldest,
        "recent_open_gaps": recent,
        "gaps": gaps,
    }


def refresh_continuity_projections(entries_dir: Path = ENTRIES_DIR) -> dict[str, Any]:
    digest = build_open_gaps_digest(entries_dir)
    _write_json(OPEN_GAPS_DIGEST_FILE, digest)
    return {"open_gaps": digest}


def emit_continuity_facts_for_entry(
    entry_path: Path,
    *,
    primary_thread_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    fm, _body = _read_frontmatter(entry_path)
    threads = _normalize_string_list(fm.get("threads") or [])
    open_gaps = _extract_open_gaps(fm)
    title = str(fm.get("title") or entry_path.stem)
    artifact = f"blog/entries/{entry_path.name}"

    emit_shadow_event(
        "ArtifactPublished",
        actor="continuity",
        artifact=artifact,
        cycle_id=cycle_id or current_cycle_id(),
        payload={
            "title": title,
            "thread_id": primary_thread_id or (threads[0] if threads else None),
            "threads": threads,
            "open_gaps_count": len(open_gaps),
        },
    )

    touched = []
    for thread_id in dict.fromkeys(([primary_thread_id] if primary_thread_id else []) + threads):
        if not thread_id:
            continue
        touched.append(thread_id)
        emit_shadow_event(
            "ThreadTouched",
            actor="continuity",
            artifact=artifact,
            cycle_id=cycle_id or current_cycle_id(),
            payload={
                "thread_id": thread_id,
                "reason": "artifact_published",
                "title": title,
            },
        )

    for position, text in enumerate(open_gaps):
        emit_shadow_event(
            "OpenGapObserved",
            actor=current_actor(),
            artifact=artifact,
            cycle_id=cycle_id or current_cycle_id(),
            payload={
                "text": text,
                "threads": threads,
                "position": position,
                "title": title,
            },
        )

    return {
        "threads": touched,
        "open_gaps": open_gaps,
        "open_gaps_count": len(open_gaps),
    }


def build_continuity_delta(entry_path: Path, digest: dict[str, Any]) -> dict[str, Any]:
    fm, _body = _read_frontmatter(entry_path)
    threads = _normalize_string_list(fm.get("threads") or [])
    open_gaps = _extract_open_gaps(fm)
    primary_thread = threads[0] if threads else None
    hot_threads = digest.get("hot_threads_by_open_gaps") or []
    hot_thread = next((item for item in hot_threads if item.get("thread_id") == primary_thread), None)

    if primary_thread and open_gaps:
        summary = (
            f"Este artifact avança a thread `{primary_thread}` com {len(open_gaps)} gap(s) em aberto. "
            "A continuidade passa a apontar para o entry original, preservando contexto e fontes."
        )
        next_step = f"Atacar os gaps remanescentes em `{primary_thread}`."
    elif primary_thread:
        summary = (
            f"Este artifact avança a thread `{primary_thread}` sem abrir gaps explícitos."
        )
        next_step = f"Continuar aprofundando `{primary_thread}` quando houver novo sinal."
    elif open_gaps:
        summary = (
            "Este artifact registra gaps sem thread. Use edge-search sobre o entry original para decidir "
            "se eles pertencem a uma thread existente."
        )
        next_step = "Associar o artifact a uma thread existente ou promover uma nova thread."
    else:
        summary = "Este artifact foi publicado sem gaps abertos explícitos."
        next_step = "Nenhuma ação de continuidade exigida."

    return {
        "built_at": _now().isoformat(),
        "slug": entry_path.stem,
        "primary_thread": primary_thread,
        "linked_threads": threads,
        "open_gaps_total": len(open_gaps),
        "hot_thread_snapshot": hot_thread,
        "summary": summary,
        "next_step": next_step,
    }


def process_publication_continuity(
    entry_path: Path,
    *,
    primary_thread_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    facts = emit_continuity_facts_for_entry(entry_path, primary_thread_id=primary_thread_id, cycle_id=cycle_id)
    projections = refresh_continuity_projections()
    delta = build_continuity_delta(entry_path, projections["open_gaps"])
    CONTINUITY_DELTAS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(CONTINUITY_DELTAS_DIR / f"{entry_path.stem}.json", delta)
    return {
        "facts": facts,
        "open_gaps": projections["open_gaps"],
        "delta": delta,
    }
