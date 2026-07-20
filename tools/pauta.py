#!/usr/bin/env python3
"""Select an ambient beat topic from direct operator Voice.

The trunk uses this after ``predispatch`` and before it dispatches a producer branch.  The command
intentionally exposes no Direction or Wayfind rows: those surfaces may contextualize a topic after
selection, but cannot originate one.  No vocabulary/profile filter is involved; candidates are the
current structured human-turn corpus produced by the session provenance layer.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


def candidates(log=eventlog.LOG, limit=80):
    rows = list(eventlog.session_topics_at(log=log).get("fragments", {}).values())
    rows.sort(key=lambda row: (str(row.get("ts") or ""), int(row.get("turn") or 0)),
              reverse=True)
    return rows[:limit]


def _print_candidates(rows):
    if not rows:
        print("(nenhuma Voz humana ativa; não publique um artefato ambient)")
        return
    for row in rows:
        print(json.dumps({
            "fragment_id": row.get("fragment_id"),
            "ts": row.get("ts"),
            "surface": row.get("surface"),
            "session_id": row.get("session_id"),
            "turn": row.get("turn"),
            "snippet": row.get("snippet"),
        }, ensure_ascii=False, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Voice-only topic gate for ambient beats; Direction/Wayfind never appear here")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("candidates", help="list active direct-human Voice fragments")
    show.add_argument("--limit", type=int, default=80)
    select = sub.add_parser("select", help="bind one actionable topic to exact Voice fragments")
    select.add_argument("--dispatch-id", required=True)
    select.add_argument("--theme", required=True)
    select.add_argument("--decision", required=True,
                        help="decision/comparison/risk/next movement usable by the reader")
    select.add_argument("--voice-fragment", action="append", required=True,
                        help="active vf:* id from `pauta.py candidates`; repeatable")
    args = parser.parse_args(argv)
    if args.command == "candidates":
        _print_candidates(candidates(limit=max(1, min(args.limit, 500))))
        return 0
    written = eventlog.record_dispatch_theme(
        args.dispatch_id, args.theme, args.decision, args.voice_fragment)
    print(json.dumps({"seq": written.get("seq"), **written.get("payload", {})},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
