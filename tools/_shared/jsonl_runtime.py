"""Bounded JSONL readers for runtime gates."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

DEFAULT_JSONL_TAIL_BYTES = 16 * 1024 * 1024
DEFAULT_JSONL_TAIL_ROWS = 5000


def jsonl_tail_bytes() -> int:
    raw = os.environ.get("EDGE_JSONL_TAIL_BYTES", str(DEFAULT_JSONL_TAIL_BYTES))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_JSONL_TAIL_BYTES
    return max(4096, value)


def iter_jsonl_reverse(
    path: Path,
    *,
    max_bytes: int | None = None,
    max_rows: int = DEFAULT_JSONL_TAIL_ROWS,
) -> Iterator[dict[str, Any]]:
    """Yield JSONL rows newest-first from a bounded tail window.

    Runtime close gates only need evidence for the current cycle, which is
    always near the end of append-only event logs. Reading the full log can be
    pathological on long-lived agents.
    """
    if not path.exists():
        return
    limit_bytes = jsonl_tail_bytes() if max_bytes is None else max(4096, int(max_bytes))
    try:
        size = path.stat().st_size
        start = max(0, size - limit_bytes)
        with path.open("rb") as handle:
            if start:
                handle.seek(start)
                handle.readline()
            data = handle.read()
    except OSError:
        return

    yielded = 0
    for raw_line in reversed(data.splitlines()):
        if yielded >= max_rows:
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            yielded += 1
            yield row
