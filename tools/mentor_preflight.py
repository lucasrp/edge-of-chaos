#!/usr/bin/env python3
"""Read-only EoC mentor preflight: leveling + portfolio recall + Cortex communities."""
import json
import os
import re
import sqlite3
import time

import cortex
import recall


def recent_hermes_work(db_path=None, days=7, limit=20, now=None):
    db_path = db_path or os.environ.get("HERMES_STATE_DB", "/home/dqx-agent/.hermes/state.db")
    cutoff = (now or time.time()) - days * 86400
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT id, started_at, title FROM sessions "
        "WHERE started_at >= ? AND COALESCE(title, '') <> '' "
        "ORDER BY started_at DESC", (cutoff,)
    )
    seen, work = set(), []
    for session_id, started_at, title in rows:
        if re.search(r"(?:Steve (?:Wake|Mentor)|preflight|configura.+mentor|installa?tion|gateway|contexto do Hermes)", title, re.I):
            continue
        key = re.sub(r"\s+#\d+$", "", title).casefold()
        if key in seen:
            continue
        seen.add(key)
        user_goal = db.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
            "AND COALESCE(content, '') <> '' ORDER BY id LIMIT 1", (session_id,)
        ).fetchone()
        outcome = db.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'assistant' "
            "AND tool_name IS NULL AND COALESCE(content, '') <> '' ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        clean = lambda row: re.sub(r"\s+", " ", row[0]).strip()[:1000] if row else ""
        work.append({"session_id": session_id, "started_at": started_at,
                     "title": title, "user_goal": clean(user_goal),
                     "outcome": clean(outcome)})
        if len(work) == limit:
            break
    return work


def collect(group=None, db_path=None):
    group = group or os.environ.get("EDGE_GROUP") or "default"
    work = recent_hermes_work(db_path=db_path)[:10]
    for index, item in enumerate(work, 1):
        item["front_id"] = f"F{index:02d}"
        item["user_goal"] = str(item.get("user_goal", ""))[:900]
        item["outcome"] = str(item.get("outcome", ""))[:900]
    return {
        "group": group,
        "leveling": recall.compose_mentee_persona_brief(),
        "portfolio_recall": recall.compose_portfolio_recall_brief(group=group)[:8000],
        "recent_hermes_work": work,
        "communities": cortex.communities(group),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, default=str))
