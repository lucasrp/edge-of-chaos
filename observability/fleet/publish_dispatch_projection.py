#!/usr/bin/env python3
"""Publish the local dispatch-cycle projection to Fleet Loki.

This is intentionally independent from the AcessoVerde Grafana stack. Each
fleet host runs this one-shot publisher against its own local Edge event log and
pushes a compact projection event to the shared Fleet Loki datasource.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISPATCH_EVENT_TYPES = {"CycleStarted", "SkillDispatched", "CycleClosed"}
SUCCESS_CLOSE_STATUSES = {"completed", "ok", "success", "succeeded", ""}

HOME = Path.home()
EDGE_DIR = Path(os.environ.get("EDGE_DIR", str(HOME / "edge"))).expanduser()
EDGE_STATE_DIR = Path(os.environ.get("EDGE_STATE_DIR", str(EDGE_DIR))).expanduser()
DEFAULT_EVENTS_PATH = EDGE_STATE_DIR / "state" / "events" / "log.jsonl"

JOB = os.environ.get("SHIPPER_JOB", "edge-fleet")
HOST = os.environ.get("EDGE_HOST", socket.gethostname())
LOKI_URL = os.environ.get("LOKI_URL", "").rstrip("/")
LOKI_USER = os.environ.get("LOKI_USER", "")
LOKI_TOKEN = os.environ.get("LOKI_TOKEN", "")


def branding_value(key: str) -> str:
    branding_path = EDGE_DIR / "config" / "branding.yaml"
    if not branding_path.exists():
        return ""
    for raw_line in branding_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line.startswith(f"{key}:"):
            continue
        return line.split(":", 1)[1].strip().strip("'\"")
    return ""


INSTANCE = os.environ.get("EDGE_INSTANCE") or branding_value("codename") or branding_value("agent_name") or HOST


def iter_events(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event["_line"] = line_no
            yield event


def timestamp(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    return str(event.get("ts") or event.get("timestamp") or "")


def payload(event: dict[str, Any] | None) -> dict[str, Any]:
    raw = (event or {}).get("payload") or {}
    return raw if isinstance(raw, dict) else {}


def merge_first(target: dict[str, Any], key: str, value: Any) -> None:
    if target.get(key) in {None, ""} and value not in {None, ""}:
        target[key] = value


def build_empty_cycle(cycle_id: str) -> dict[str, Any]:
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


def apply_event(cycle: dict[str, Any], event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "")
    body = payload(event)
    cycle["event_counts"][event_type] = int(cycle["event_counts"].get(event_type, 0)) + 1
    cycle["event_lines"].append(int(event.get("_line") or 0))

    merge_first(cycle, "trigger", body.get("trigger"))
    merge_first(cycle, "skill", body.get("skill"))
    merge_first(cycle, "thread_id", body.get("thread_id"))
    merge_first(cycle, "primary_thread_id", body.get("primary_thread_id") or body.get("thread_id"))

    if event_type == "CycleStarted":
        merge_first(cycle, "opened_at", timestamp(event))
        if not cycle.get("phase") or cycle.get("phase") == "unknown":
            cycle["phase"] = "opened"
    elif event_type == "SkillDispatched":
        merge_first(cycle, "dispatched_at", timestamp(event))
        if cycle.get("phase") != "closed":
            cycle["phase"] = "dispatched"
    elif event_type == "CycleClosed":
        merge_first(cycle, "closed_at", timestamp(event))
        cycle["phase"] = "closed"
        cycle["close_status"] = str(body.get("close_status") or "")
        cycle["close_reason"] = str(body.get("reason") or body.get("close_reason") or "")


def classify(cycle: dict[str, Any]) -> str:
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


def build_projection(events_path: Path, limit: int) -> dict[str, Any]:
    cycles: dict[str, dict[str, Any]] = {}
    scanned_events = 0
    dispatch_events = 0
    orphan_events_without_cycle = 0

    for event in iter_events(events_path) or []:
        scanned_events += 1
        event_type = str(event.get("type") or "")
        if event_type not in DISPATCH_EVENT_TYPES:
            continue
        dispatch_events += 1
        cycle_id = str(event.get("cycle_id") or "")
        if not cycle_id:
            orphan_events_without_cycle += 1
            continue
        cycle = cycles.setdefault(cycle_id, build_empty_cycle(cycle_id))
        apply_event(cycle, event)

    for cycle in cycles.values():
        cycle["status"] = classify(cycle)
        if not cycle.get("primary_thread_id"):
            cycle["primary_thread_id"] = cycle.get("thread_id", "")

    ordered_cycles = sorted(
        cycles.values(),
        key=lambda item: item.get("closed_at") or item.get("dispatched_at") or item.get("opened_at") or "",
        reverse=True,
    )
    incomplete_statuses = {"missing_dispatch", "missing_close", "failed", "orphaned"}
    incomplete_cycles = [cycle for cycle in ordered_cycles if cycle.get("status") in incomplete_statuses]

    counts_by_status: dict[str, int] = {}
    counts_by_trigger: dict[str, int] = {}
    counts_by_skill: dict[str, int] = {}
    for cycle in ordered_cycles:
        status = str(cycle.get("status") or "unknown")
        trigger = str(cycle.get("trigger") or "unknown")
        skill = str(cycle.get("skill") or "unknown")
        counts_by_status[status] = counts_by_status.get(status, 0) + 1
        counts_by_trigger[trigger] = counts_by_trigger.get(trigger, 0) + 1
        counts_by_skill[skill] = counts_by_skill.get(skill, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "state_events_path": str(events_path),
        "summary": {
            "events_scanned": scanned_events,
            "dispatch_events": dispatch_events,
            "cycles_total": len(ordered_cycles),
            "cycles_incomplete": len(incomplete_cycles),
            "orphan_events_without_cycle": orphan_events_without_cycle,
            "counts_by_status": counts_by_status,
            "counts_by_trigger": counts_by_trigger,
            "counts_by_skill": counts_by_skill,
        },
        "recent_cycles": ordered_cycles[:limit],
        "incomplete_cycles": incomplete_cycles[:limit],
    }


def base_event(event_type: str, now: str) -> dict[str, Any]:
    return {
        "ts": now,
        "type": event_type,
        "actor": "fleet-dispatch-projection",
        "host": HOST,
        "instance": INSTANCE,
    }


def build_projection_events(events_path: Path, limit: int) -> list[dict[str, Any]]:
    projection = build_projection(events_path=events_path, limit=limit)
    summary = projection["summary"]
    by_status = summary.get("counts_by_status", {})
    now = datetime.now(timezone.utc).isoformat()
    events = []
    summary_event = {
        **base_event("DispatchCycleProjectionPublished", now),
        "summary_cycles_total": int(summary.get("cycles_total") or 0),
        "summary_cycles_incomplete": int(summary.get("cycles_incomplete") or 0),
        "summary_closed": int(by_status.get("closed") or 0),
        "summary_failed": int(by_status.get("failed") or 0),
        "summary_missing_dispatch": int(by_status.get("missing_dispatch") or 0),
        "summary_missing_close": int(by_status.get("missing_close") or 0),
        "summary_orphaned": int(by_status.get("orphaned") or 0),
        "payload": {
            "job": JOB,
            "projection": projection,
        },
    }
    events.append(summary_event)

    metric_values = {
        "cycles_total": summary_event["summary_cycles_total"],
        "cycles_incomplete": summary_event["summary_cycles_incomplete"],
        "closed": summary_event["summary_closed"],
        "failed": summary_event["summary_failed"],
        "missing_dispatch": summary_event["summary_missing_dispatch"],
        "missing_close": summary_event["summary_missing_close"],
        "orphaned": summary_event["summary_orphaned"],
    }
    for metric, count in metric_values.items():
        events.append(
            {
                **base_event("DispatchCycleMetricPublished", now),
                "metric": metric,
                "count": int(count or 0),
                "_loki_line": str(int(count or 0)),
            }
        )

    for status, count in sorted((summary.get("counts_by_status") or {}).items()):
        events.append(
            {
                **base_event("DispatchCycleStatusCountPublished", now),
                "status": str(status),
                "count": int(count or 0),
                "_loki_line": str(int(count or 0)),
            }
        )
    for skill, count in sorted((summary.get("counts_by_skill") or {}).items()):
        events.append(
            {
                **base_event("DispatchCycleSkillCountPublished", now),
                "skill": str(skill),
                "count": int(count or 0),
                "_loki_line": str(int(count or 0)),
            }
        )
    for trigger, count in sorted((summary.get("counts_by_trigger") or {}).items()):
        events.append(
            {
                **base_event("DispatchCycleTriggerCountPublished", now),
                "trigger": str(trigger),
                "count": int(count or 0),
                "_loki_line": str(int(count or 0)),
            }
        )
    return events


def loki_timestamp(ts: str) -> str:
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return str(int(parsed.timestamp() * 1_000_000_000))


def ensure_push_url(url: str) -> str:
    if url.endswith("/loki/api/v1/push"):
        return url
    return url + "/loki/api/v1/push"


def label_value(value: Any) -> str:
    return str(value or "unknown").replace("\n", " ")[:180]


def push_events(events: list[dict[str, Any]]) -> None:
    if not (LOKI_URL and LOKI_USER and LOKI_TOKEN):
        raise RuntimeError("missing Loki credentials")

    streams: dict[tuple[tuple[str, str], ...], list[list[str]]] = {}
    for event in events:
        stream = {
            "job": JOB,
            "host": HOST,
            "instance": INSTANCE,
            "type": label_value(event.get("type")),
            "actor": label_value(event.get("actor")),
        }
        for key in ("metric", "status", "skill", "trigger"):
            if event.get(key) not in {None, ""}:
                stream[key] = label_value(event.get(key))
        line = str(event["_loki_line"]) if "_loki_line" in event else json.dumps(event, separators=(",", ":"))
        label_items = tuple(sorted(stream.items()))
        streams.setdefault(label_items, []).append(
            [loki_timestamp(str(event.get("ts") or "")), line]
        )

    body = json.dumps(
        {
            "streams": [
                {
                    "stream": dict(label_items),
                    "values": values,
                }
                for label_items, values in streams.items()
            ]
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(ensure_push_url(LOKI_URL), data=body, method="POST")
    auth = base64.b64encode(f"{LOKI_USER}:{LOKI_TOKEN}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", "Basic " + auth)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Loki push failed with status {response.status}")


def publish_once(events_path: Path, limit: int, dry_run: bool) -> int:
    events = build_projection_events(events_path=events_path, limit=limit)
    summary_event = events[0]
    if dry_run:
        print(json.dumps({"events": events}, indent=2, sort_keys=True))
        return 0
    push_events(events)
    print(
        "published dispatch projection: "
        f"instance={INSTANCE} "
        f"cycles={summary_event['summary_cycles_total']} "
        f"incomplete={summary_event['summary_cycles_incomplete']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish dispatch-cycle projection to Fleet Loki")
    parser.add_argument("--events-path", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("PROJECTION_LIMIT", "50")))
    parser.add_argument("--dry-run", action="store_true", help="Print the projection event without pushing to Loki")
    parser.add_argument("--loop", action="store_true", help="Publish forever at --interval seconds")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("PROJECTION_INTERVAL_SECONDS", "300")),
        help="Loop interval in seconds",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    events_path = args.events_path.expanduser()
    limit = max(1, args.limit)
    if not args.loop:
        return publish_once(events_path=events_path, limit=limit, dry_run=args.dry_run)

    while True:
        try:
            publish_once(events_path=events_path, limit=limit, dry_run=args.dry_run)
        except urllib.error.HTTPError as exc:
            print(f"publish failed: http {exc.code}", file=sys.stderr)
        except Exception as exc:
            print(f"publish failed: {exc}", file=sys.stderr)
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
