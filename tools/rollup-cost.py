#!/usr/bin/env python3
"""rollup-cost — Derive cost-rollup.json from llm_call events.

Reads `logs/events.jsonl`, filters `type == "llm_call"`, aggregates into
`state/cost-rollup.json` with per-day, per-skill, per-model breakdowns and
a monthly burn estimate.

Consumers: /ed-strategy (budget gating), /ed-autonomy (per-artifact cost).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import EVENTS_FILE, STATE_DIR  # noqa: E402

OUT_PATH = STATE_DIR / "cost-rollup.json"
WINDOW_DAYS = 30


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


def main() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    by_day: dict[str, dict] = defaultdict(lambda: {"usd": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0})
    by_skill: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_router: dict[str, float] = defaultdict(float)

    total_usd = 0.0
    total_calls = 0
    unknown_models: set[str] = set()

    for ev in _iter_events():
        if ev.get("type") != "llm_call":
            continue
        ts = ev.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt < cutoff:
            continue

        day = dt.date().isoformat()
        cost = float(ev.get("cost_usd") or 0.0)
        skill = ev.get("skill") or "unknown"
        model = ev.get("model") or "unknown"
        router = ev.get("router") or "unknown"
        ti = int(ev.get("tokens_in") or 0)
        to = int(ev.get("tokens_out") or 0)

        by_day[day]["usd"] += cost
        by_day[day]["calls"] += 1
        by_day[day]["tokens_in"] += ti
        by_day[day]["tokens_out"] += to
        by_skill[skill] += cost
        by_model[model] += cost
        by_router[router] += cost
        total_usd += cost
        total_calls += 1
        if cost == 0.0 and (ti or to):
            unknown_models.add(model)

    by_day_list = sorted(
        ({"date": d, **{k: round(v, 4) if isinstance(v, float) else v for k, v in vals.items()}}
         for d, vals in by_day.items()),
        key=lambda r: r["date"],
    )

    daily_avg = total_usd / WINDOW_DAYS if total_usd else 0.0
    payload = {
        "window_days": WINDOW_DAYS,
        "total_usd": round(total_usd, 4),
        "total_calls": total_calls,
        "monthly_burn_estimate_usd": round(daily_avg * 30, 2),
        "by_day": by_day_list,
        "by_skill": {k: round(v, 4) for k, v in sorted(by_skill.items(), key=lambda x: -x[1])},
        "by_model": {k: round(v, 4) for k, v in sorted(by_model.items(), key=lambda x: -x[1])},
        "by_router": {k: round(v, 4) for k, v in sorted(by_router.items(), key=lambda x: -x[1])},
        "unknown_models": sorted(unknown_models),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH} (${total_usd:.4f} / {total_calls} calls / {WINDOW_DAYS}d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
