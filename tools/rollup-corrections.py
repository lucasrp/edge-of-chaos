#!/usr/bin/env python3
"""rollup-corrections — Operator correction detector + rollup (issue #226 item 4).

Reads Claude session jsonl files (~/.claude/projects/*/*.jsonl), detects
correction patterns in user messages (don't / stop / actually / no / again),
emits one `operator_correction` event per match to `logs/events.jsonl`, and
produces `state/operator-corrections.json` with the 30d trend.

Idempotent: tracks last-processed message id per session in
`state/.corrections-cursor.json` so re-running doesn't double-count.

Consumer: /ed-reflection.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "tools"))
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import EVENTS_FILE, STATE_DIR  # noqa: E402
from _shared.telemetry import log_operator_correction  # noqa: E402

OUT_PATH = STATE_DIR / "operator-corrections.json"
CURSOR_PATH = STATE_DIR / ".corrections-cursor.json"
WINDOW_DAYS = 30

SESSIONS_GLOB = Path.home() / ".claude" / "projects"

# Patterns -> category. Order matters: first match wins.
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(stop|para de|chega de)\b", re.I),                          "course_correction"),
    (re.compile(r"\b(don'?t|nao faça|não faça|nao deve|não deve)\b", re.I),    "course_correction"),
    (re.compile(r"\b(actually|na verdade|na real)\b", re.I),                   "scope_drift"),
    (re.compile(r"\b(again|de novo|outra vez)\b", re.I),                       "repeat_request"),
    (re.compile(r"\b(no|nao|não)[\s,!.]", re.I),                               "rejection"),
    (re.compile(r"\b(over.?engineer|too much|exagerou|exagerado)\b", re.I),    "over_engineering"),
    (re.compile(r"\b(wrong tool|errou|errado)\b", re.I),                       "wrong_tool"),
]


def _load_cursor() -> dict[str, int]:
    if not CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(CURSOR_PATH.read_text())
    except Exception:
        return {}


def _save_cursor(cursor: dict[str, int]) -> None:
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(cursor, indent=2))


def _classify(text: str) -> str | None:
    for pat, cat in PATTERNS:
        if pat.search(text):
            return cat
    return None


def _iter_user_messages(jsonl: Path):
    """Yield (idx, ts, text) for each user message in a session jsonl."""
    try:
        with open(jsonl, encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "user":
                    continue
                ts = msg.get("timestamp") or ""
                content = msg.get("message", {})
                if isinstance(content, dict):
                    text = content.get("content", "")
                    if isinstance(text, list):
                        text = " ".join(p.get("text", "") for p in text if isinstance(p, dict))
                else:
                    text = str(content or "")
                if not text or not isinstance(text, str):
                    continue
                yield idx, ts, text
    except FileNotFoundError:
        return


def main() -> int:
    cursor = _load_cursor()
    new_corrections = 0
    sessions_scanned = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    for jsonl in SESSIONS_GLOB.rglob("*.jsonl"):
        sessions_scanned += 1
        sid = jsonl.stem
        last_idx = cursor.get(sid, -1)
        max_seen = last_idx
        for idx, ts, text in _iter_user_messages(jsonl):
            if idx <= last_idx:
                continue
            max_seen = max(max_seen, idx)
            if len(text) < 10 or len(text) > 2000:
                continue
            category = _classify(text)
            if not category:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except Exception:
                dt = None
            if dt and dt < cutoff:
                continue
            log_operator_correction(
                session_id=sid,
                trigger=text[:200],
                category=category,
                msg_idx=idx,
                source_file=jsonl.name,
            )
            new_corrections += 1
        if max_seen > last_idx:
            cursor[sid] = max_seen

    _save_cursor(cursor)

    # Now build the rollup from events.jsonl (includes prior runs).
    by_category: dict[str, int] = defaultdict(int)
    by_session: dict[str, int] = defaultdict(int)
    samples: list[dict] = []
    total = 0
    if EVENTS_FILE.exists():
        with open(EVENTS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") != "operator_correction":
                    continue
                ts = ev.get("ts") or ""
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if dt < cutoff:
                    continue
                cat = ev.get("category") or "other"
                sid = ev.get("session_id") or "unknown"
                by_category[cat] += 1
                by_session[sid] += 1
                total += 1
                if len(samples) < 5:
                    samples.append({"ts": ts, "category": cat, "trigger": ev.get("trigger", "")[:140]})

    payload = {
        "window_days": WINDOW_DAYS,
        "total": total,
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "top_sessions": dict(sorted(by_session.items(), key=lambda x: -x[1])[:5]),
        "recent_samples": samples,
        "sessions_scanned": sessions_scanned,
        "new_this_run": new_corrections,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"OK: {OUT_PATH} ({total} corrections / {WINDOW_DAYS}d, +{new_corrections} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
