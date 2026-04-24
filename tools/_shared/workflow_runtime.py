"""Workflow runtime summaries.

Small operational read model over workflow entries and workflow-health.json.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import ENTRIES_DIR, WORKFLOW_HEALTH_FILE  # noqa: E402

STALE_DAYS = 60
_STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "das", "dos", "para", "por", "em", "no",
    "na", "nos", "nas", "um", "uma", "as", "os", "que", "se", "com", "sem",
    "and", "or", "the", "to", "of", "in", "for", "is", "are", "be", "this",
    "that", "it", "on", "workflow", "procedure", "report", "research",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9à-ÿ]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
    return fm if isinstance(fm, dict) else {}


def _workflow_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not ENTRIES_DIR.exists():
        return rows
    for entry_path in sorted(ENTRIES_DIR.glob("*.md")):
        fm = _read_frontmatter(entry_path)
        tags = fm.get("tags") or []
        if not isinstance(tags, list):
            continue
        tags_norm = {str(tag).strip().lower() for tag in tags}
        if "workflow" not in tags_norm and "workflow-draft" not in tags_norm:
            continue
        title = str(fm.get("title") or entry_path.stem).strip()
        rows.append(
            {
                "slug": entry_path.stem,
                "title": title,
                "path": str(entry_path),
                "href": f"/entry/{entry_path.stem}",
                "tags": sorted(tags_norm),
                "date": str(fm.get("date") or ""),
                "tokens": sorted(_tokenize(title + " " + " ".join(map(str, tags_norm)))),
            }
        )
    return rows


def build_workflow_status() -> dict[str, Any]:
    citations = {}
    if WORKFLOW_HEALTH_FILE.exists():
        try:
            raw = json.loads(WORKFLOW_HEALTH_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                citations = raw.get("citations") or {}
        except Exception:
            citations = {}

    now = _now()
    workflows = []
    broken_total = 0
    stale_total = 0
    for row in _workflow_entries():
        health = citations.get(row["slug"], {}) if isinstance(citations, dict) else {}
        used = int(health.get("used") or 0)
        broken = int(health.get("broken") or 0)
        last_cited = str(health.get("last_cited") or "").strip()
        last_cited_dt = _parse_ts(last_cited)
        stale = False
        if last_cited_dt:
            stale = now - last_cited_dt > timedelta(days=STALE_DAYS)
        elif used == 0 and broken == 0:
            stale = False
        else:
            stale = True
        broken_total += 1 if broken > 0 else 0
        stale_total += 1 if stale else 0
        workflows.append(
            {
                **row,
                "used": used,
                "broken": broken,
                "last_cited": last_cited,
                "stale": stale,
            }
        )

    workflows.sort(key=lambda item: (-item["broken"], -item["used"], item["slug"]))
    payload = {
        "generated_at": now.isoformat(),
        "summary": {
            "workflow_total": len(workflows),
            "cited_total": sum(1 for item in workflows if item["used"] or item["broken"]),
            "broken_total": broken_total,
            "stale_total": stale_total,
            "top_used": [
                {"slug": item["slug"], "title": item["title"], "used": item["used"], "broken": item["broken"]}
                for item in sorted(workflows, key=lambda item: (-item["used"], item["slug"]))[:5]
                if item["used"] > 0
            ],
            "top_broken": [
                {"slug": item["slug"], "title": item["title"], "used": item["used"], "broken": item["broken"]}
                for item in workflows[:5]
                if item["broken"] > 0
            ],
        },
        "workflows": workflows,
    }
    return payload
