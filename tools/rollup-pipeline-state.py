#!/usr/bin/env python3
"""rollup-pipeline-state — project publication pipeline state from events.

Reads canonical facts from `state/events/log.jsonl` and writes
`state/projections/pipeline-state.json`.
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
from paths import PIPELINE_STATE_FILE, STATE_EVENTS_FILE  # noqa: E402

PIPELINE_EVENT_TYPES = {"PhaseCompleted", "ArtifactPublished"}
TRUE_VALUES = {"1", "true", "yes", "ok", "success", "succeeded", "completed", "pass", "passed"}
FALSE_VALUES = {"0", "false", "no", "fail", "failed", "error", "blocked", "aborted"}
TERMINAL_PHASES = {"pipeline", "pipeline-end", "pipeline_end"}


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


def _artifact(event: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(event.get("artifact") or payload.get("artifact") or payload.get("path") or "").strip()


def _phase_ok(payload: dict[str, Any]) -> bool | None:
    value = payload.get("ok")
    if isinstance(value, bool):
        return value
    if value is not None:
        text = str(value).strip().lower()
        if text in TRUE_VALUES:
            return True
        if text in FALSE_VALUES:
            return False

    status = str(payload.get("status") or "").strip().lower()
    if status in TRUE_VALUES:
        return True
    if status in FALSE_VALUES:
        return False
    return None


def _is_runtime_stdout_artifact(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("auto_published") is True
        or str(payload.get("pipeline") or "") == "runtime-stdout-artifact"
    )


def _build_empty_artifact(artifact: str) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "status": "unknown",
        "pipeline": "",
        "source_skill": "",
        "hash": "",
        "cycle_id": "",
        "first_event_at": "",
        "last_event_at": "",
        "published_at": "",
        "published": False,
        "runtime_stdout_artifact": False,
        "terminal_phase_status": "",
        "terminal_phase_at": "",
        "phase_counts": {"ok": 0, "failed": 0, "unknown": 0},
        "phases": [],
        "event_counts": {"PhaseCompleted": 0, "ArtifactPublished": 0},
        "event_lines": [],
        "reasons": [],
    }


def _merge_first(target: dict[str, Any], key: str, value: Any) -> None:
    if target.get(key) in {None, ""} and value not in {None, ""}:
        target[key] = value


def _touch_artifact(record: dict[str, Any], event: dict[str, Any]) -> None:
    ts = _timestamp(event)
    if ts:
        _merge_first(record, "first_event_at", ts)
        if not record.get("last_event_at") or ts >= str(record.get("last_event_at") or ""):
            record["last_event_at"] = ts
    record["event_lines"].append(int(event.get("_line") or 0))
    _merge_first(record, "cycle_id", event.get("cycle_id"))


def _apply_phase_completed(record: dict[str, Any], event: dict[str, Any], payload: dict[str, Any]) -> None:
    _touch_artifact(record, event)
    record["event_counts"]["PhaseCompleted"] = int(record["event_counts"].get("PhaseCompleted") or 0) + 1
    _merge_first(record, "pipeline", payload.get("pipeline"))

    runtime_stdout = _is_runtime_stdout_artifact(payload)
    if runtime_stdout:
        record["runtime_stdout_artifact"] = True
    ok = False if runtime_stdout else _phase_ok(payload)
    if ok is True:
        phase_status = "ok"
    elif ok is False:
        phase_status = "failed"
    else:
        phase_status = "unknown"
    record["phase_counts"][phase_status] = int(record["phase_counts"].get(phase_status) or 0) + 1

    reason = str(payload.get("reason") or payload.get("error") or "").strip()
    if runtime_stdout and not reason:
        reason = "runtime_stdout_artifact_rejected"
    if reason:
        record["reasons"].append(reason)

    record["phases"].append(
        {
            "phase": str(payload.get("phase") or ""),
            "pipeline": str(payload.get("pipeline") or ""),
            "status": phase_status,
            "ok": ok,
            "reason": reason,
            "ts": _timestamp(event),
            "line": int(event.get("_line") or 0),
        }
    )
    phase_name = str(payload.get("phase") or "").strip().lower()
    if phase_name in TERMINAL_PHASES:
        record["terminal_phase_status"] = phase_status
        record["terminal_phase_at"] = _timestamp(event)


def _apply_artifact_published(record: dict[str, Any], event: dict[str, Any], payload: dict[str, Any]) -> None:
    _touch_artifact(record, event)
    record["event_counts"]["ArtifactPublished"] = int(record["event_counts"].get("ArtifactPublished") or 0) + 1
    runtime_stdout = _is_runtime_stdout_artifact(payload)
    if runtime_stdout:
        record["runtime_stdout_artifact"] = True
        if "runtime_stdout_artifact_rejected" not in record["reasons"]:
            record["reasons"].append("runtime_stdout_artifact_rejected")
    else:
        record["published"] = True
    if not record.get("published_at") or _timestamp(event) >= str(record.get("published_at") or ""):
        record["published_at"] = _timestamp(event)
    _merge_first(record, "source_skill", payload.get("source_skill") or payload.get("skill"))
    _merge_first(record, "hash", payload.get("hash"))


def _classify(record: dict[str, Any]) -> str:
    phase_total = int(record["event_counts"].get("PhaseCompleted") or 0)
    published = bool(record.get("published"))
    failed = int((record.get("phase_counts") or {}).get("failed") or 0) > 0
    terminal = str(record.get("terminal_phase_status") or "").strip()

    if record.get("runtime_stdout_artifact"):
        return "runtime_bypass"
    if published and phase_total == 0:
        return "orphaned_publish"
    if terminal == "ok":
        return "complete" if published else "partial"
    if terminal == "failed":
        return "failed" if published else "blocked"
    if published and failed:
        return "failed"
    if published and phase_total > 0:
        return "partial"
    if failed:
        return "blocked"
    if phase_total > 0:
        return "partial"
    return "unknown"


def build_projection(limit: int = 50, events_path: Path = STATE_EVENTS_FILE) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    scanned_events = 0
    pipeline_events = 0
    orphan_events_without_artifact = 0

    for event in iter_events(events_path) or []:
        scanned_events += 1
        etype = str(event.get("type") or "")
        if etype not in PIPELINE_EVENT_TYPES:
            continue
        pipeline_events += 1
        payload = _payload(event)
        artifact = _artifact(event, payload)
        if not artifact:
            orphan_events_without_artifact += 1
            continue

        record = artifacts.setdefault(artifact, _build_empty_artifact(artifact))
        if etype == "PhaseCompleted":
            _apply_phase_completed(record, event, payload)
        elif etype == "ArtifactPublished":
            _apply_artifact_published(record, event, payload)

    for record in artifacts.values():
        record["status"] = _classify(record)
        record["phases"] = sorted(record["phases"], key=lambda p: (p.get("ts") or "", p.get("line") or 0))
        record["reasons"] = list(dict.fromkeys(record["reasons"]))

    ordered = sorted(
        artifacts.values(),
        key=lambda item: item.get("last_event_at") or item.get("published_at") or item.get("first_event_at") or "",
        reverse=True,
    )
    attention_statuses = {"partial", "blocked", "failed", "orphaned_publish", "runtime_bypass", "unknown"}
    attention = [item for item in ordered if item.get("status") in attention_statuses]
    counts_by_status: dict[str, int] = {}
    counts_by_pipeline: dict[str, int] = {}
    for item in ordered:
        status = str(item.get("status") or "unknown")
        pipeline = str(item.get("pipeline") or "unknown")
        counts_by_status[status] = counts_by_status.get(status, 0) + 1
        counts_by_pipeline[pipeline] = counts_by_pipeline.get(pipeline, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(PIPELINE_STATE_FILE),
        "state_events_path": str(events_path),
        "summary": {
            "events_scanned": scanned_events,
            "pipeline_events": pipeline_events,
            "artifacts_total": len(ordered),
            "artifacts_attention": len(attention),
            "orphan_events_without_artifact": orphan_events_without_artifact,
            "counts_by_status": counts_by_status,
            "counts_by_pipeline": counts_by_pipeline,
        },
        "recent_artifacts": ordered[:limit],
        "attention_artifacts": attention[:limit],
    }


def write_projection(limit: int = 50) -> dict[str, Any]:
    payload = build_projection(limit=limit)
    PIPELINE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_STATE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project pipeline state from state/events/log.jsonl")
    parser.add_argument("--json", action="store_true", help="Print full JSON projection")
    parser.add_argument("--limit", type=int, default=50, help="Maximum recent/attention artifacts to include")
    parser.add_argument("--no-write", action="store_true", help="Do not write state/projections/pipeline-state.json")
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
            f"{PIPELINE_STATE_FILE} "
            f"(artifacts={summary['artifacts_total']} "
            f"attention={summary['artifacts_attention']} "
            f"complete={counts.get('complete', 0)} "
            f"partial={counts.get('partial', 0)} "
            f"blocked={counts.get('blocked', 0)} "
            f"failed={counts.get('failed', 0)} "
            f"orphaned_publish={counts.get('orphaned_publish', 0)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
