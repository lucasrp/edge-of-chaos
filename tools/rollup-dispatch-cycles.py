#!/usr/bin/env python3
"""rollup-dispatch-cycles — project dispatch lifecycle facts from the event log.

Reads canonical facts from `state/events/log.jsonl` and writes
`state/projections/dispatch-cycles.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import DISPATCH_CYCLES_FILE, STATE_EVENTS_FILE  # noqa: E402

DISPATCH_EVENT_TYPES = {"CycleStarted", "SkillDispatched", "CycleClosed"}
SUCCESS_CLOSE_STATUSES = {"completed", "ok", "success", "succeeded", ""}


def iter_events(path: Path = STATE_EVENTS_FILE):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event["_line"] = line_no
            yield event


def _timestamp(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    return str(event.get("ts") or event.get("timestamp") or "")


def _payload(event: dict[str, Any] | None) -> dict[str, Any]:
    payload = (event or {}).get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _merge_first(target: dict[str, Any], key: str, value: Any) -> None:
    if target.get(key) in {None, ""} and value not in {None, ""}:
        target[key] = value


def _build_empty_cycle(cycle_id: str) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "trigger": "",
        "skill": "",
        "thread_id": "",
        "primary_thread_id": "",
        "phase": "unknown",
        "status": "orphaned",
        "opened_at": "",
        "dispatched_at": "",
        "closed_at": "",
        "close_status": "",
        "close_reason": "",
        "event_counts": {"CycleStarted": 0, "SkillDispatched": 0, "CycleClosed": 0},
        "event_lines": [],
    }


def _apply_event(cycle: dict[str, Any], event: dict[str, Any]) -> None:
    etype = str(event.get("type") or "")
    payload = _payload(event)
    cycle["event_counts"][etype] = int(cycle["event_counts"].get(etype, 0)) + 1
    cycle["event_lines"].append(int(event.get("_line") or 0))

    _merge_first(cycle, "trigger", payload.get("trigger"))
    _merge_first(cycle, "skill", payload.get("skill"))
    _merge_first(cycle, "thread_id", payload.get("thread_id"))
    _merge_first(cycle, "primary_thread_id", payload.get("primary_thread_id") or payload.get("thread_id"))

    if etype == "CycleStarted":
        _merge_first(cycle, "opened_at", _timestamp(event))
        if not cycle.get("phase") or cycle.get("phase") == "unknown":
            cycle["phase"] = "opened"
    elif etype == "SkillDispatched":
        _merge_first(cycle, "dispatched_at", _timestamp(event))
        if cycle.get("phase") != "closed":
            cycle["phase"] = "dispatched"
    elif etype == "CycleClosed":
        _merge_first(cycle, "closed_at", _timestamp(event))
        cycle["phase"] = "closed"
        cycle["close_status"] = str(payload.get("close_status") or "")
        cycle["close_reason"] = str(payload.get("reason") or payload.get("close_reason") or "")


def _classify(cycle: dict[str, Any]) -> str:
    counts = cycle.get("event_counts") or {}
    started = int(counts.get("CycleStarted") or 0) > 0
    dispatched = int(counts.get("SkillDispatched") or 0) > 0
    closed = int(counts.get("CycleClosed") or 0) > 0
    close_status = str(cycle.get("close_status") or "").lower()

    if closed and close_status not in SUCCESS_CLOSE_STATUSES:
        return "failed"
    if closed and dispatched:
        return "closed"
    if closed and not dispatched:
        return "missing_dispatch"
    if dispatched and not closed:
        return "missing_close"
    if started and not dispatched:
        return "missing_dispatch"
    return "orphaned"


def build_projection(limit: int = 50, events_path: Path = STATE_EVENTS_FILE) -> dict[str, Any]:
    cycles: dict[str, dict[str, Any]] = {}
    scanned_events = 0
    dispatch_events = 0
    orphan_events_without_cycle = 0

    for event in iter_events(events_path) or []:
        scanned_events += 1
        etype = str(event.get("type") or "")
        if etype not in DISPATCH_EVENT_TYPES:
            continue
        dispatch_events += 1
        cycle_id = str(event.get("cycle_id") or "")
        if not cycle_id:
            orphan_events_without_cycle += 1
            continue
        cycle = cycles.setdefault(cycle_id, _build_empty_cycle(cycle_id))
        _apply_event(cycle, event)

    for cycle in cycles.values():
        cycle["status"] = _classify(cycle)
        if not cycle.get("primary_thread_id"):
            cycle["primary_thread_id"] = cycle.get("thread_id", "")

    ordered_cycles = sorted(
        cycles.values(),
        key=lambda c: c.get("closed_at") or c.get("dispatched_at") or c.get("opened_at") or "",
        reverse=True,
    )
    incomplete_statuses = {"missing_dispatch", "missing_close", "failed", "orphaned"}
    incomplete_cycles = [c for c in ordered_cycles if c.get("status") in incomplete_statuses]
    counts_by_status: dict[str, int] = {}
    counts_by_trigger: dict[str, int] = {}
    for cycle in ordered_cycles:
        status = str(cycle.get("status") or "unknown")
        trigger = str(cycle.get("trigger") or "unknown")
        counts_by_status[status] = counts_by_status.get(status, 0) + 1
        counts_by_trigger[trigger] = counts_by_trigger.get(trigger, 0) + 1

    projection = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(DISPATCH_CYCLES_FILE),
        "state_events_path": str(events_path),
        "summary": {
            "events_scanned": scanned_events,
            "dispatch_events": dispatch_events,
            "cycles_total": len(ordered_cycles),
            "cycles_incomplete": len(incomplete_cycles),
            "orphan_events_without_cycle": orphan_events_without_cycle,
            "counts_by_status": counts_by_status,
            "counts_by_trigger": counts_by_trigger,
        },
        "recent_cycles": ordered_cycles[:limit],
        "incomplete_cycles": incomplete_cycles[:limit],
    }
    return projection


def write_projection(limit: int = 50) -> dict[str, Any]:
    payload = build_projection(limit=limit)
    DISPATCH_CYCLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_CYCLES_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project dispatch cycles from state/events/log.jsonl")
    parser.add_argument("--json", action="store_true", help="Print full JSON projection")
    parser.add_argument("--limit", type=int, default=50, help="Maximum recent/incomplete cycles to include")
    parser.add_argument("--no-write", action="store_true", help="Do not write state/projections/dispatch-cycles.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    limit = max(1, args.limit)
    payload = build_projection(limit=limit) if args.no_write else write_projection(limit=limit)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        summary = payload["summary"]
        counts = summary["counts_by_status"]
        print(
            "OK: "
            f"{DISPATCH_CYCLES_FILE} "
            f"(cycles={summary['cycles_total']} "
            f"incomplete={summary['cycles_incomplete']} "
            f"closed={counts.get('closed', 0)} "
            f"failed={counts.get('failed', 0)} "
            f"missing_dispatch={counts.get('missing_dispatch', 0)} "
            f"missing_close={counts.get('missing_close', 0)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

