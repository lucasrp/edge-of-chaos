#!/usr/bin/env python3
"""rollup-affordances — build the learned source/channel affordance digest."""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import SOURCE_AFFORDANCE_DIGEST_FILE, STATE_EVENTS_FILE  # noqa: E402

WINDOW_DAYS = 90
CONFIDENCE_AT = 10


def parse_ts(value: Any) -> datetime | None:
    try:
        raw = str(value or "").strip().replace("Z", "+00:00")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def iter_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def build_digest(events: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_seconds = WINDOW_DAYS * 24 * 60 * 60
    odi_index: dict[str, dict[str, Any]] = {}
    buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(lambda: {
        "scores": [],
        "recent_odis": deque(maxlen=8),
        "contexts": defaultdict(int),
        "reasons": deque(maxlen=5),
    }))

    for row in events:
        event_type = str(row.get("type") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        ts = parse_ts(row.get("ts"))
        if ts and (now - ts).total_seconds() > cutoff_seconds:
            continue

        if event_type == "OdiObserved":
            odi_id = str(payload.get("odi_id") or "").strip()
            if odi_id:
                odi_index[odi_id] = {
                    "odi_id": odi_id,
                    "source_id": payload.get("source_id"),
                    "primitive": payload.get("primitive"),
                    "context": payload.get("context"),
                    "title": payload.get("title"),
                    "url": payload.get("url"),
                    "rank": payload.get("rank"),
                    "score": payload.get("score"),
                    "ts": row.get("ts"),
                }
            continue

        if event_type != "SourceAffordanceEvaluated":
            continue

        source_id = str(payload.get("source_id") or "").strip()
        affordance = str(payload.get("affordance") or "").strip()
        if not source_id or not affordance:
            continue
        try:
            score = max(1.0, min(5.0, float(payload.get("score") or 0)))
        except (TypeError, ValueError):
            continue

        bucket = buckets[source_id][affordance]
        bucket["scores"].append(score)
        context = str(payload.get("context") or "").strip()
        if context:
            bucket["contexts"][context] += 1
        reason = str(payload.get("reason") or "").strip()
        if reason:
            bucket["reasons"].append(reason)
        odi_id = str(payload.get("odi_id") or "").strip()
        if odi_id:
            bucket["recent_odis"].appendleft({
                **odi_index.get(odi_id, {"odi_id": odi_id}),
                "judgment": reason,
                "evaluation_score": score,
                "evaluation_context": context,
            })

    sources: dict[str, Any] = {}
    for source_id, by_affordance in sorted(buckets.items()):
        affordances = {}
        for affordance, bucket in sorted(by_affordance.items()):
            scores = list(bucket["scores"])
            evidence_count = len(scores)
            avg_5 = round(sum(scores) / evidence_count, 3) if evidence_count else 0.0
            affordances[affordance] = {
                "score": round(avg_5 / 5.0, 3) if avg_5 else 0.0,
                "score_5": avg_5,
                "confidence": round(min(1.0, evidence_count / CONFIDENCE_AT), 3),
                "evidence_count": evidence_count,
                "top_contexts": [
                    {"context": key, "count": count}
                    for key, count in sorted(bucket["contexts"].items(), key=lambda item: (-item[1], item[0]))[:5]
                ],
                "recent_reasons": list(bucket["reasons"]),
                "recent_odis": list(bucket["recent_odis"]),
            }
        sources[source_id] = {
            "source_id": source_id,
            "learned_affordances": affordances,
        }

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "window_days": WINDOW_DAYS,
        "source_count": len(sources),
        "sources": sources,
    }


def main() -> int:
    digest = build_digest(iter_events(STATE_EVENTS_FILE))
    SOURCE_AFFORDANCE_DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_AFFORDANCE_DIGEST_FILE.write_text(json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OK: {SOURCE_AFFORDANCE_DIGEST_FILE} ({digest['source_count']} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
