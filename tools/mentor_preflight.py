#!/usr/bin/env python3
"""Read-only EoC mentor preflight composed from canonical Edge sources."""
import json
import os
import re

import cortex
import quente
import recall
import sessions


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()[:900]


def work_from_window(selected):
    work = []
    for meta in selected:
        turns = sessions.read_turns(meta["path"], surface=meta["surface"])
        goals = [_clean(turn.text) for turn in turns
                 if turn.role == "human" and turn.text.strip()
                 and not any(marker in turn.text[:200] for marker in quente.SCAFFOLDING)]
        outcomes = [_clean(turn.text) for turn in turns if turn.role == "edge" and turn.text.strip()]
        work.append({
            "session_id": meta["id"],
            "surface": meta["surface"],
            "updated_at": meta.get("last", ""),
            "user_goal": goals[0] if goals else "",
            "outcome": outcomes[-1] if outcomes else "",
        })
    return work


def collect(group=None, db_path=None):
    group = group or os.environ.get("EDGE_GROUP") or "default"
    selected, _window_start = quente.select_window(
        k=3, max_age_days=7, hermes_dir=db_path,
    )
    return {
        "group": group,
        "leveling": recall.compose_mentee_persona_brief(),
        "portfolio_recall": recall.compose_portfolio_recall_brief(group=group)[:8000],
        "recent_hermes_work": work_from_window(selected),
        "communities": cortex.communities(group),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, default=str))
