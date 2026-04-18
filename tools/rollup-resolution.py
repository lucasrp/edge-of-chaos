#!/usr/bin/env python3
"""rollup-resolution — Time-to-resolution rollup (issue #226 item 5).

Reads `*_resolved` events from `logs/events.jsonl` and produces
`state/resolution-rollup.json` with median, p95 and counts per object type
(claim, friction, workflow_broken, issue, thread). Also reports stale items
that were opened > 30d ago and are still unresolved (best-effort — works
when an `obj_open` event matched the id).

Consumers: /ed-reflection (resolution decay), /ed-autonomy (stale resurface).
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import EVENTS_FILE, STATE_DIR  # noqa: E402

OUT_PATH = STATE_DIR / "resolution-rollup.json"
WINDOW_DAYS = 90

OBJ_TYPES = ("claim", "friction", "workflow_broken", "issue", "thread")


def _iter_events():
    if not EVENTS_FILE.exists():
        return
    with open(EVENTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(sorted(values), n=100)[int(pct) - 1], 2)


def main() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    durations: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    for ev in _iter_events():
        etype = ev.get("type", "")
        if not etype.endswith("_resolved"):
            continue
        ts = ev.get("ts")
        try:
            dt = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if dt < cutoff:
            continue

        obj_type = ev.get("obj_type") or etype.removesuffix("_resolved")
        counts[obj_type] += 1
        d = ev.get("duration_h")
        if isinstance(d, (int, float)):
            durations[obj_type].append(float(d))

    summary: dict[str, dict] = {}
    for obj_type in OBJ_TYPES:
        durs = durations.get(obj_type, [])
        summary[obj_type] = {
            "resolved_count": counts.get(obj_type, 0),
            "median_h": round(statistics.median(durs), 2) if durs else 0.0,
            "p95_h": _percentile(durs, 95) if durs else 0.0,
            "max_h": round(max(durs), 2) if durs else 0.0,
        }

    payload = {
        "window_days": WINDOW_DAYS,
        "by_type": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH} ({sum(counts.values())} resolution events / {WINDOW_DAYS}d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
