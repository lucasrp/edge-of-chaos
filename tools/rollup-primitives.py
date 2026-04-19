#!/usr/bin/env python3
"""rollup-primitives — Aggregate telemetry_snapshots into a small JSON.

Reads `telemetry_snapshots` table (one row per primitive call) and writes
`state/primitive-usage-rollup.json` with 30-day per-source counters.

Consumers: /ed-autonomy (fan-out check), /ed-reflection (failure rates).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import SEARCH_DB_FILE, STATE_DIR  # noqa: E402

DB_PATH = SEARCH_DB_FILE
OUT_PATH = STATE_DIR / "primitive-usage-rollup.json"
WINDOW_DAYS = 30


def main() -> int:
    if not DB_PATH.exists():
        print(f"db not found: {DB_PATH}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT
              source,
              COUNT(*)            AS calls,
              SUM(ok)             AS ok,
              SUM(fail)           AS fail,
              AVG(NULLIF(avg_ms, 0)) AS avg_ms,
              MAX(ts)             AS last_ts
            FROM telemetry_snapshots
            WHERE ts >= datetime('now', '-{WINDOW_DAYS} days')
            GROUP BY source
            ORDER BY calls DESC
            """
        ).fetchall()
    finally:
        conn.close()

    by_source = {}
    total_calls = 0
    for src, calls, ok, fail, avg_ms, last_ts in rows:
        ok = int(ok or 0)
        fail = int(fail or 0)
        calls = int(calls or 0)
        by_source[src] = {
            "calls": calls,
            "ok": ok,
            "fail": fail,
            "ok_rate": round(ok / calls, 3) if calls else 0.0,
            "avg_ms": int(avg_ms) if avg_ms else 0,
            "last_ts": last_ts,
        }
        total_calls += calls

    payload = {
        "window_days": WINDOW_DAYS,
        "total_calls": total_calls,
        "by_source": by_source,
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH} ({total_calls} calls across {len(by_source)} sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
