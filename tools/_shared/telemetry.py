"""Telemetry helpers — passive writers, no LLM friction.

Append-only event logging to `logs/events.jsonl` plus targeted writes to the
`telemetry_snapshots` SQLite table. Readers (rollup scripts in tools/) digest
these into small JSON files that skills consume.

Design rules (issue #226):
- Writers MUST NOT prompt, decide, or call LLMs. Pure observation.
- Failures are swallowed — telemetry MUST NOT break the caller.
- Consumers never read raw events — always pre-digested rollups.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import EVENTS_FILE, SEARCH_DIR  # noqa: E402

DB_PATH = SEARCH_DIR / "edge-memory.db"

# --- Price table (USD per 1M tokens). Missing models map to 0 cost rather than
# block the call; rollup flags unknown models separately.
# Keep this table small — update when new models are added to agent.yaml.
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    # model: (input_per_1m, output_per_1m)
    "gpt-5.4":                 (5.00, 15.00),
    "gpt-5.4-pro":            (15.00, 60.00),
    "gpt-4.1-mini":            (0.40, 1.60),
    "gpt-4o":                  (2.50, 10.00),
    "gpt-4o-mini":             (0.15, 0.60),
    "text-embedding-3-small":  (0.02, 0.00),
    "text-embedding-3-large":  (0.13, 0.00),
    "grok-4.20-multi-agent-beta-0309": (5.00, 15.00),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return estimated cost in USD. Unknown models return 0.0."""
    price = _PRICE_PER_M.get(model)
    if price is None:
        return 0.0
    ti, to = price
    return round((tokens_in / 1_000_000) * ti + (tokens_out / 1_000_000) * to, 6)


def current_skill() -> str | None:
    """Best-effort current skill name. Reads env var set by skill runner."""
    return os.environ.get("ED_SKILL") or os.environ.get("CLAUDE_SKILL") or None


def current_beat() -> str | None:
    """Current heartbeat rotation number, if tracked by state/beat-rotation.json."""
    return os.environ.get("ED_BEAT") or None


def _append_event(event: dict[str, Any]) -> None:
    """Append a JSON line to EVENTS_FILE. Swallows all errors."""
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_event(event_type: str, **fields: Any) -> None:
    """Append a typed event to events.jsonl. Always includes ts + type."""
    event = {"ts": datetime.now(timezone.utc).isoformat(), "type": event_type}
    event.update(fields)
    _append_event(event)


def log_llm_call(
    *,
    router: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    caller: str | None = None,
    cost_usd: float | None = None,
    **extra: Any,
) -> None:
    """Telemetry for a single LLM call. Derives cost if not passed."""
    if cost_usd is None:
        cost_usd = estimate_cost_usd(model, tokens_in, tokens_out)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "llm_call",
        router=router,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        caller=caller or _detect_caller(),
        **extra,
    )


def _detect_caller() -> str:
    """Best-effort caller detection from sys.argv[0]."""
    try:
        return Path(sys.argv[0]).name
    except Exception:
        return "unknown"


def _ensure_telemetry_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS telemetry_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
            source TEXT NOT NULL,
            calls INTEGER DEFAULT 0,
            ok INTEGER DEFAULT 0,
            fail INTEGER DEFAULT 0,
            avg_ms INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            notes TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_snapshots(ts);
        CREATE INDEX IF NOT EXISTS idx_telemetry_source ON telemetry_snapshots(source);
    """)


def log_primitive_call(
    source: str,
    *,
    ok: bool,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    notes: dict[str, Any] | None = None,
) -> None:
    """Insert one row into telemetry_snapshots per primitive call.

    Called by edge-sources/edge-x/edge-hn/etc. as a side-effect. All errors
    swallowed — telemetry never breaks the primitive.
    """
    try:
        if not DB_PATH.exists():
            return
        conn = sqlite3.connect(str(DB_PATH), timeout=2.0)
        try:
            _ensure_telemetry_table(conn)
            conn.execute(
                """
                INSERT INTO telemetry_snapshots
                (source, calls, ok, fail, avg_ms, cost_usd, notes)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    1 if ok else 0,
                    0 if ok else 1,
                    int(latency_ms),
                    float(cost_usd),
                    json.dumps(notes or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


@contextmanager
def time_primitive(source: str, notes: dict[str, Any] | None = None):
    """Context manager that times a primitive block and logs success/failure.

    Usage:
        with time_primitive("x", notes={"q": query}):
            ...call X API...
    """
    t0 = time.monotonic()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        dt_ms = int((time.monotonic() - t0) * 1000)
        log_primitive_call(source, ok=ok, latency_ms=dt_ms, notes=notes)


def log_workflow_transition(
    slug: str,
    from_state: str,
    to_state: str,
    *,
    approved_by: str | None = None,
    **extra: Any,
) -> None:
    """Workflow lifecycle event: claim → cluster → draft → approved → cited → broken → healed → retired."""
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "workflow_transition",
        slug=slug,
        **{"from": from_state, "to": to_state},
        approved_by=approved_by,
        **extra,
    )


def log_resolution(
    *,
    obj_type: str,  # claim | friction | workflow_broken | issue | thread
    obj_id: str,
    opened_at: str | None,
    resolution: str,
    **extra: Any,
) -> None:
    """Time-to-resolution event. Duration derived from opened_at if present."""
    duration_h: float | None = None
    if opened_at:
        try:
            start = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            duration_h = round((now - start).total_seconds() / 3600.0, 2)
        except Exception:
            duration_h = None
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        f"{obj_type}_resolved",
        obj_type=obj_type,
        id=obj_id,
        opened_at=opened_at,
        duration_h=duration_h,
        resolution=resolution,
        **extra,
    )


def log_operator_correction(
    *,
    session_id: str,
    trigger: str,
    category: str,
    **extra: Any,
) -> None:
    """Operator correction event (scope_drift | wrong_tool | over_engineering | other)."""
    log_event(
        "operator_correction",
        session_id=session_id,
        trigger=trigger,
        category=category,
        **extra,
    )


__all__ = [
    "log_event",
    "log_llm_call",
    "log_primitive_call",
    "time_primitive",
    "log_workflow_transition",
    "log_resolution",
    "log_operator_correction",
    "estimate_cost_usd",
    "current_skill",
    "current_beat",
]
