"""usage_log: helper for primitives to log their invocations.

Every primitive should call log_invocation() at entry and exit. The log
accumulates at $EDGE_HOME/state/source-usage.jsonl (one JSON object per
line) and is the raw material for diversity analysis and discovery
tracking.

Intentionally minimal: append-only, no rotation (leave to future), no
schema enforcement (primitives can add fields). The goal is a low-friction
hook, not telemetry infrastructure.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _log_path() -> Path:
    edge_home = os.environ.get("EDGE_HOME", str(Path.home() / "edge"))
    return Path(edge_home).expanduser() / "state" / "source-usage.jsonl"


def log_invocation(
    source_name: str,
    phase: str,  # "start" | "end"
    *,
    input_summary: str = "",
    duration_ms: int | None = None,
    ok: bool | None = None,
    result_count: int | None = None,
    error: str | None = None,
    task_context: str | None = None,
) -> None:
    """Append a single log entry. Never raises — logging must not break the tool."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source_name,
            "codename": os.environ.get("EDGE_CODENAME", "unknown"),
            "phase": phase,
            "task_context": task_context or os.environ.get("EDGE_TASK_CONTEXT", ""),
        }
        if input_summary:
            entry["input_summary"] = input_summary
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if ok is not None:
            entry["ok"] = ok
        if result_count is not None:
            entry["result_count"] = result_count
        if error:
            entry["error"] = error

        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        # Logging failure must not break the tool. Emit to stderr as a hint.
        print(f"[usage_log] warning: could not write log entry: {exc}", file=sys.stderr)
