#!/usr/bin/env python3
"""rollup-workflow-funnel — Workflow lifecycle funnel (issue #226 item 3).

Reads `workflow_transition` events from `logs/events.jsonl` and produces
`state/workflow-funnel.json` counting transitions: claim → cluster → draft →
approved → cited → broken → healed → retired.

Consumers: /ed-corpus-curation procedures, /ed-autonomy.
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

OUT_PATH = STATE_DIR / "workflow-funnel.json"
WINDOW_DAYS = 60

STATES = ("claim", "cluster", "draft", "approved", "cited", "broken", "healed", "retired")


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
    transitions: dict[str, int] = defaultdict(int)
    state_count: dict[str, int] = defaultdict(int)
    by_slug_state: dict[str, str] = {}

    for ev in _iter_events():
        if ev.get("type") != "workflow_transition":
            continue
        try:
            dt = datetime.fromisoformat((ev.get("ts") or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if dt < cutoff:
            continue
        frm = ev.get("from") or "unknown"
        to = ev.get("to") or "unknown"
        slug = ev.get("slug") or ""
        transitions[f"{frm}->{to}"] += 1
        if slug:
            by_slug_state[slug] = to

    for state in by_slug_state.values():
        state_count[state] += 1

    payload = {
        "window_days": WINDOW_DAYS,
        "current_state": {s: state_count.get(s, 0) for s in STATES},
        "transitions": dict(sorted(transitions.items(), key=lambda x: -x[1])),
        "tracked_workflows": len(by_slug_state),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH} ({len(by_slug_state)} workflows, {sum(transitions.values())} transitions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
