#!/usr/bin/env python3
"""rollup-observability — Consolidate operational telemetry into one state file.

Produces `state/observability-rollup.json` from events, failures, threads and
entries. Focus areas:
- lifecycle by run kind and phase
- success/failure by phase
- freshness by actor
- backlog/open loop
- structured blog_publish failure classes
- primitives, sources, and search queries
- database reads/writes
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import ENTRIES_DIR, EVENTS_FILE, LOGS_DIR, SEARCH_DB_FILE, STATE_DIR, THREADS_DIR  # noqa: E402

OUT_PATH = STATE_DIR / "observability-rollup.json"
WINDOW_DAYS = 30


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _frontmatter(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            return {}
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _classify_publish_error(text: str) -> str:
    msg = (text or "").lower()
    if not msg:
        return "unknown"
    rules = [
        ("auth_or_credits", r"invalid|unauthoriz|forbidden|401|403|credits|quota|api key|token"),
        ("validation_or_schema", r"yaml|schema|validation|review-gate|frontmatter|claim|glossary"),
        ("render_or_content", r"render|html|grep|phase 2|phase 3|report generation|quoted error"),
        ("filesystem_or_path", r"no such file|permission denied|read-only|not found|path|directory"),
        ("service_or_http", r"http|curl|connection refused|service=|502|503|504|timeout"),
        ("git_or_state", r"git|commit|dirty|index|sqlite|state_snapshot"),
        ("process_or_exit", r"returned non-zero|exit \d+|killed|signal"),
    ]
    for label, pattern in rules:
        if re.search(pattern, msg):
            return label
    return "unknown"


def _rollup_backlog(today: str) -> dict:
    active = 0
    waiting = 0
    due = 0
    open_gaps = 0

    for path in THREADS_DIR.glob("*.md"):
        fm = _frontmatter(path)
        status = str(fm.get("status", ""))
        if status == "active":
            active += 1
        elif status == "waiting":
            waiting += 1
        resurface = str(fm.get("resurface", ""))
        if status in {"active", "waiting"} and resurface and resurface <= today:
            due += 1

    for path in ENTRIES_DIR.glob("*.md"):
        fm = _frontmatter(path)
        gaps = fm.get("open_gaps", []) or []
        if isinstance(gaps, list):
            open_gaps += len(gaps)

    return {
        "active_threads": active,
        "waiting_threads": waiting,
        "resurface_due": due,
        "open_gaps": open_gaps,
    }


def _rollup_citations(now: datetime) -> dict:
    empty = {
        "available": False,
        "total": 0,
        "top_cited": [],
        "never_cited_30d": 0,
        "recently_cited_7d": 0,
    }
    if not SEARCH_DB_FILE.exists():
        return empty
    try:
        conn = sqlite3.connect(f"file:{SEARCH_DB_FILE}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
    except Exception:
        return empty
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='citations'"
        ).fetchone()
        if not has_table:
            return empty
        total = int(conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0])
        top_cited = [
            {
                "path": row["cited_path"],
                "citations": int(row["citations"]),
                "last_cited": row["last_cited"],
            }
            for row in conn.execute(
                """
                SELECT cited_path, COUNT(*) AS citations, MAX(ts) AS last_cited
                FROM citations
                GROUP BY cited_path
                ORDER BY citations DESC, last_cited DESC
                LIMIT 10
                """
            ).fetchall()
        ]
        cutoff_30 = (now - timedelta(days=30)).isoformat()
        cutoff_7 = (now - timedelta(days=7)).isoformat()
        never_cited_30d = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM documents d
                WHERE d.type IN ('blog', 'report')
                  AND d.updated_at >= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM citations c WHERE c.cited_path = d.path
                  )
                """,
                (cutoff_30,),
            ).fetchone()[0]
        )
        recently_cited_7d = int(
            conn.execute(
                "SELECT COUNT(DISTINCT cited_path) FROM citations WHERE ts >= ?",
                (cutoff_7,),
            ).fetchone()[0]
        )
        return {
            "available": True,
            "total": total,
            "top_cited": top_cited,
            "never_cited_30d": never_cited_30d,
            "recently_cited_7d": recently_cited_7d,
        }
    except Exception:
        return empty
    finally:
        conn.close()


def main() -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WINDOW_DAYS)

    lifecycle: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    phase_outcomes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    freshness_raw: dict[str, datetime] = {}
    primitive_by_source: dict[str, dict] = defaultdict(lambda: {"calls": 0, "ok": 0, "fail": 0, "latencies": [], "last_ts": None})
    primitive_usage_by_source: dict[str, dict] = defaultdict(lambda: {"events": 0, "start": 0, "end": 0, "last_ts": None})
    source_queries: dict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "failed": 0, "total_results": 0, "last_ts": None})
    search_queries = {"total": 0, "with_sidecar": 0, "sidecar_hits": 0}
    db_by_table: dict[str, dict] = defaultdict(lambda: {"reads": 0, "writes": 0, "fail": 0, "latencies": []})
    db_by_op: dict[str, int] = defaultdict(int)

    for ev in _iter_jsonl(EVENTS_FILE):
        ts = _parse_ts(ev.get("ts") or ev.get("timestamp"))
        if ts is None:
            continue

        actor = ev.get("actor") or "unknown"
        if actor not in freshness_raw or ts > freshness_raw[actor]:
            freshness_raw[actor] = ts

        etype = ev.get("type")
        if ts < cutoff:
            continue

        if etype == "run_step":
            run_kind = ev.get("run_kind") or "unknown"
            phase = ev.get("phase") or "unknown"
            status = ev.get("status") or "unknown"
            lifecycle[run_kind][phase][status] += 1
            phase_outcomes[phase][status] += 1
        elif etype == "primitive_call":
            src = ev.get("source") or "unknown"
            bucket = primitive_by_source[src]
            bucket["calls"] += 1
            if ev.get("ok"):
                bucket["ok"] += 1
            else:
                bucket["fail"] += 1
            latency = ev.get("latency_ms")
            if isinstance(latency, (int, float)) and latency >= 0:
                bucket["latencies"].append(int(latency))
            bucket["last_ts"] = ev.get("ts")
        elif etype == "primitive_usage":
            src = ev.get("source") or "unknown"
            bucket = primitive_usage_by_source[src]
            bucket["events"] += 1
            phase = ev.get("phase") or "unknown"
            bucket[phase] = bucket.get(phase, 0) + 1
            bucket["last_ts"] = ev.get("ts")
        elif etype == "source_query":
            intent = ev.get("intent") or "unknown"
            bucket = source_queries[intent]
            status = ev.get("status") or "unknown"
            bucket[status] = bucket.get(status, 0) + 1
            bucket["total_results"] += int(ev.get("total_results") or 0)
            bucket["last_ts"] = ev.get("ts")
        elif etype == "search_query":
            search_queries["total"] += 1
            sidecar_count = int(ev.get("sidecar_count") or 0)
            if sidecar_count > 0:
                search_queries["with_sidecar"] += 1
            search_queries["sidecar_hits"] += sidecar_count
        elif etype == "db_query":
            table = ev.get("table") or "unknown"
            bucket = db_by_table[table]
            if ev.get("write"):
                bucket["writes"] += 1
            else:
                bucket["reads"] += 1
            if not ev.get("ok", True):
                bucket["fail"] += 1
            latency = ev.get("latency_ms")
            if isinstance(latency, (int, float)) and latency >= 0:
                bucket["latencies"].append(int(latency))
            op = ev.get("op") or "unknown"
            db_by_op[op] += 1
    freshness = {
        actor: {
            "last_ts": dt.isoformat(),
            "age_minutes": round((now - dt).total_seconds() / 60.0, 1),
        }
        for actor, dt in sorted(freshness_raw.items(), key=lambda item: item[1], reverse=True)
    }

    primitive_payload = {}
    for src, bucket in primitive_by_source.items():
        calls = bucket["calls"]
        primitive_payload[src] = {
            "calls": calls,
            "ok": bucket["ok"],
            "fail": bucket["fail"],
            "ok_rate": round(bucket["ok"] / calls, 3) if calls else 0.0,
            "avg_ms": round(statistics.mean(bucket["latencies"]), 1) if bucket["latencies"] else 0.0,
            "last_ts": bucket["last_ts"],
        }

    primitive_usage_payload = {
        src: bucket
        for src, bucket in sorted(primitive_usage_by_source.items(), key=lambda item: (-item[1]["events"], item[0]))
    }

    db_payload = {}
    for table, bucket in db_by_table.items():
        db_payload[table] = {
            "reads": bucket["reads"],
            "writes": bucket["writes"],
            "fail": bucket["fail"],
            "avg_ms": round(statistics.mean(bucket["latencies"]), 1) if bucket["latencies"] else 0.0,
        }

    blog_publish = {"total": 0, "by_class": defaultdict(int), "recent": []}
    failures_path = LOGS_DIR / "pipeline-failures.jsonl"
    for row in _iter_jsonl(failures_path):
        if (row.get("operation") or "") != "blog_publish":
            continue
        klass = _classify_publish_error(row.get("error", ""))
        blog_publish["total"] += 1
        blog_publish["by_class"][klass] += 1
        blog_publish["recent"].append({
            "timestamp": row.get("timestamp"),
            "slug": row.get("slug"),
            "class": klass,
            "error": (row.get("error") or "")[:200],
        })
    blog_publish["recent"] = blog_publish["recent"][-10:]
    blog_publish["by_class"] = dict(sorted(blog_publish["by_class"].items(), key=lambda item: -item[1]))

    payload = {
        "window_days": WINDOW_DAYS,
        "generated_at": now.isoformat(),
        "lifecycle": {
            run_kind: {phase: dict(statuses) for phase, statuses in phases.items()}
            for run_kind, phases in lifecycle.items()
        },
        "phase_outcomes": {phase: dict(statuses) for phase, statuses in phase_outcomes.items()},
        "freshness_by_actor": freshness,
        "backlog": _rollup_backlog(now.date().isoformat()),
        "blog_publish_failures": blog_publish,
        "primitives": {
            "calls_by_source": dict(sorted(primitive_payload.items(), key=lambda item: -item[1]["calls"])),
            "usage_events_by_source": primitive_usage_payload,
        },
        "sources": {
            "queries_by_intent": dict(sorted(source_queries.items())),
        },
        "search": {
            "query_stats": search_queries,
        },
        "citations": _rollup_citations(now),
        "database": {
            "by_table": dict(sorted(db_payload.items(), key=lambda item: -(item[1]["reads"] + item[1]["writes"]))),
            "by_op": dict(sorted(db_by_op.items(), key=lambda item: -item[1])),
            "total_reads": sum(item["reads"] for item in db_payload.values()),
            "total_writes": sum(item["writes"] for item in db_payload.values()),
            "total_failures": sum(item["fail"] for item in db_payload.values()),
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
