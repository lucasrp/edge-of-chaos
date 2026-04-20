"""Shared service helpers for dashboard and action blueprints."""

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import markdown
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import (  # noqa: E402
    AUTONOMY_CAPABILITIES_FILE,
    BRIEFING_FILE,
    CURRENT_DISPATCH_FILE,
    CURADORIA_CANDIDATES_FILE as CURADORIA_CANDIDATES,
    EDGE_REPO_DIR,
    ENTRIES_DIR,
    EXECUTION_LEDGER_FILE as EXECUTION_LEDGER,
    FRONTIER_FILE,
    GIT_SIGNALS_FILE as GIT_SIGNALS,
    LOGS_DIR,
    OPS_HOTSPOTS,
    PRIMITIVES_STATUS_FILE,
    PROPOSALS_FILE,
    REPORTS_DIR,
    SIGNALS_DIR,
    SKILL_STEPS_FILE,
    SOURCES_MANIFEST_FILE,
    STATE_EVENTS_FILE,
    STATE_DIR,
    TASKS_SNAPSHOT_FILE,
    TOPICS_DIR,
    THREADS_DIR,
)

ROOT = EDGE_REPO_DIR
OPERATOR_ACTIONS_FILE = LOGS_DIR / "operator-actions.jsonl"
PRIMITIVE_USAGE_ROLLUP_FILE = STATE_DIR / "primitive-usage-rollup.json"
STRATEGY_FILE = ROOT / "config" / "strategy.md"


def load_json_safe(path, default=None):
    """Load a JSON file, returning default on any error."""
    if default is None:
        default = {}
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _load_yaml_safe(path, default=None):
    if default is None:
        default = {}
    try:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if data is not None else default
    except Exception:
        pass
    return default


def _iter_jsonl(path):
    try:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows
    except Exception:
        return []


def _short_ts(value):
    if not value:
        return ""
    return str(value).replace("T", " ")[:16]


def _find_shadow_markers(*markers):
    matches = []
    marker_set = tuple(str(marker).lower() for marker in markers)
    for event in _iter_jsonl(STATE_EVENTS_FILE):
        blob = json.dumps(event, ensure_ascii=False).lower()
        if any(marker in blob for marker in marker_set):
            matches.append(event)
    return matches


def load_current_dispatch_state():
    """Best-effort current dispatch cycle state."""
    state = load_json_safe(CURRENT_DISPATCH_FILE, {})
    request = state.get("request", {}) or {}
    state_block = state.get("state", {}) or {}
    if not state:
        return {
            "available": False,
            "active": False,
            "cycle_id": None,
            "trigger": None,
            "skill": None,
            "phase": "no-dispatch",
            "phase_label": "no dispatch",
            "phase_color": "muted",
            "preflight_status": "unknown",
            "skill_status": "unknown",
            "postflight_status": "unknown",
            "close_status": None,
            "opened_at_short": "",
            "dispatched_at_short": "",
            "closed_at_short": "",
            "updated_at_short": "",
        }

    active = bool(state_block.get("active"))
    close_status = state_block.get("close_status")
    phase = state_block.get("phase") or ("active" if active else "closed")
    if active:
        phase_label = phase.replace("_", " ")
        phase_color = "green" if state_block.get("skill_dispatched") else "yellow"
    else:
        phase_label = close_status or "closed"
        phase_color = "green" if close_status == "completed" else "yellow"

    return {
        "available": True,
        "active": active,
        "cycle_id": state.get("cycle_id"),
        "trigger": request.get("trigger"),
        "skill": request.get("skill"),
        "phase": phase,
        "phase_label": phase_label,
        "phase_color": phase_color,
        "preflight_status": state_block.get("preflight_status", "unknown"),
        "skill_status": state_block.get("skill_status", "unknown"),
        "postflight_status": state_block.get("postflight_status", "unknown"),
        "close_status": close_status,
        "opened_at_short": _short_ts(state_block.get("opened_at")),
        "dispatched_at_short": _short_ts(state_block.get("dispatched_at")),
        "closed_at_short": _short_ts(state_block.get("closed_at")),
        "updated_at_short": _short_ts(state_block.get("updated_at")),
    }


def load_recent_dispatch_cycles(limit=6):
    """Aggregate recent dispatch cycles from the shadow event log."""
    cycles = {}
    for event in _iter_jsonl(STATE_EVENTS_FILE)[-400:]:
        cycle_id = str(event.get("cycle_id") or "").strip()
        if not cycle_id:
            continue
        event_type = event.get("type")
        if event_type not in {"CycleStarted", "SkillDispatched", "CycleClosed"}:
            continue
        payload = event.get("payload", {}) or {}
        item = cycles.setdefault(cycle_id, {
            "cycle_id": cycle_id,
            "trigger": None,
            "skill": None,
            "opened_at": None,
            "dispatched_at": None,
            "closed_at": None,
            "close_status": None,
            "event_count": 0,
        })
        item["event_count"] += 1
        ts = event.get("ts")
        if event_type == "CycleStarted":
            item["opened_at"] = item["opened_at"] or ts
            item["trigger"] = payload.get("trigger") or payload.get("requested_trigger") or item["trigger"]
        elif event_type == "SkillDispatched":
            item["dispatched_at"] = ts
            item["skill"] = payload.get("skill") or item["skill"]
            item["trigger"] = payload.get("trigger") or item["trigger"]
        elif event_type == "CycleClosed":
            item["closed_at"] = ts
            item["close_status"] = payload.get("close_status")
            item["skill"] = payload.get("skill") or item["skill"]
            item["trigger"] = payload.get("trigger") or item["trigger"]

    current = load_current_dispatch_state()
    if current["available"] and current["cycle_id"] not in cycles:
        cycles[current["cycle_id"]] = {
            "cycle_id": current["cycle_id"],
            "trigger": current["trigger"],
            "skill": current["skill"],
            "opened_at": current["opened_at_short"],
            "dispatched_at": current["dispatched_at_short"],
            "closed_at": current["closed_at_short"],
            "close_status": current["close_status"],
            "event_count": 0,
            "from_current_dispatch": True,
            "active": current["active"],
        }

    items = []
    for cycle in cycles.values():
        active = bool(cycle.get("active")) or (cycle.get("opened_at") and not cycle.get("closed_at"))
        has_dispatch = bool(cycle.get("dispatched_at"))
        has_close = bool(cycle.get("closed_at"))
        if has_dispatch and has_close:
            health_label = cycle.get("close_status") or "complete"
            health_color = "green" if cycle.get("close_status") == "completed" else "yellow"
        elif active and has_dispatch:
            health_label = "in progress"
            health_color = "yellow"
        elif active:
            health_label = "missing dispatch"
            health_color = "red"
        else:
            health_label = "partial"
            health_color = "red"

        last_ts = cycle.get("closed_at") or cycle.get("dispatched_at") or cycle.get("opened_at") or ""
        items.append({
            **cycle,
            "active": active,
            "health_label": health_label,
            "health_color": health_color,
            "opened_at_short": _short_ts(cycle.get("opened_at")),
            "dispatched_at_short": _short_ts(cycle.get("dispatched_at")),
            "closed_at_short": _short_ts(cycle.get("closed_at")),
            "last_ts": last_ts,
            "last_ts_short": _short_ts(last_ts),
        })

    items.sort(key=lambda item: item.get("last_ts") or "", reverse=True)
    return items[:limit]


def load_skill_evidence_summary(limit=5):
    """Summarize skill-step observability and explicit pre/post gaps."""
    runs = []
    total_silent = 0
    total_explicit = 0
    for entry in reversed(_iter_jsonl(SKILL_STEPS_FILE)):
        if entry.get("event") != "end" or "expected" not in entry:
            continue
        silent = len(entry.get("silent_skips", []))
        explicit = int(entry.get("explicit_skips", 0) or 0)
        total_silent += silent
        total_explicit += explicit
        runs.append({
            "skill": entry.get("skill"),
            "completion_pct": entry.get("completion_pct", 0),
            "silent_skips": silent,
            "explicit_skips": explicit,
            "ts_short": _short_ts(entry.get("ts")),
        })
        if len(runs) >= limit:
            break

    pre_events = _find_shadow_markers("preskill", "pre_skill")
    post_events = _find_shadow_markers("postskill", "post_skill")
    current = load_current_dispatch_state()
    return {
        "pre_skill": {
            "status": "observed" if pre_events else "gap",
            "color": "green" if pre_events else "red",
            "detail": f"{len(pre_events)} explicit pre-skill events" if pre_events else "no explicit pre-skill runtime evidence in shadow log yet",
            "protocol_status": current.get("preflight_status", "unknown"),
        },
        "post_skill": {
            "status": "observed" if post_events else "gap",
            "color": "green" if post_events else "red",
            "detail": f"{len(post_events)} explicit post-skill events" if post_events else "no explicit post-skill runtime evidence in shadow log yet",
            "protocol_status": current.get("postflight_status", "unknown"),
        },
        "skill_runs": runs,
        "skill_runs_total": len(runs),
        "silent_skips_total": total_silent,
        "explicit_skips_total": total_explicit,
    }


def load_primitive_runtime_summary(limit=5):
    """Summarize primitives using the canonical primitives-status read model."""
    payload = load_json_safe(PRIMITIVES_STATUS_FILE, None)
    if not payload and (ROOT / "tools" / "edge-primitives").exists():
        try:
            result = subprocess.run(
                [str(ROOT / "tools" / "edge-primitives"), "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            payload = json.loads(result.stdout)
        except Exception:
            payload = None

    if payload and isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        summary = payload["summary"]
        sources = payload.get("sources", []) if isinstance(payload.get("sources"), list) else []
        top_used = sorted(sources, key=lambda item: (-int(item.get("usage_30d", 0) or 0), item.get("name", "")))
        return {
            "available": True,
            "window_days": int(summary.get("window_days", 30) or 30),
            "health_status": summary.get("health_status", "unknown"),
            "health_color": "red" if summary.get("health_status") == "fail" else "yellow" if summary.get("health_status") == "degraded" else "green",
            "declared_total": int(summary.get("declared_total", 0) or 0),
            "contract_only_total": int(summary.get("contract_only_total", 0) or 0),
            "active_total": int(summary.get("active_total", 0) or 0),
            "probed_total": int(summary.get("probed_total", 0) or 0),
            "broken_total": int(summary.get("broken_total", 0) or 0),
            "drifted_total": int(summary.get("drifted_total", 0) or 0),
            "usage_30d_total": int(summary.get("usage_30d_total", 0) or 0),
            "counts_by_effective_status": summary.get("counts_by_effective_status", {}) or {},
            "top_sources": sources[:limit],
            "top_used": top_used[:limit],
        }

    # Legacy fallback while instances converge on primitives-status.json.
    usage = load_json_safe(PRIMITIVE_USAGE_ROLLUP_FILE, {
        "window_days": 30,
        "total_calls": 0,
        "by_source": {},
    })
    manifest = _load_yaml_safe(SOURCES_MANIFEST_FILE, {"sources": []})
    sources = manifest.get("sources", []) or []
    status_counts = {}
    for item in sources:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    top_used = []
    top_failing = []
    for source, data in (usage.get("by_source", {}) or {}).items():
        row = {
            "source": source,
            "calls": int(data.get("calls", 0) or 0),
            "fail": int(data.get("fail", 0) or 0),
            "ok_rate": data.get("ok_rate", 0.0),
            "avg_ms": int(data.get("avg_ms", 0) or 0),
        }
        top_used.append(row)
        if row["fail"] > 0:
            top_failing.append(row)

    top_used.sort(key=lambda item: (-item["calls"], item["source"]))
    top_failing.sort(key=lambda item: (-item["fail"], -item["calls"], item["source"]))

    lifecycle_types = {
        "PrimitiveMissingObserved",
        "PrimitiveContractWritten",
        "PrimitiveMaterialized",
        "PrimitiveProbeCompleted",
        "PrimitiveManifestUpdated",
    }
    lifecycle = []
    for event in reversed(_iter_jsonl(STATE_EVENTS_FILE)):
        if event.get("type") not in lifecycle_types:
            continue
        payload = event.get("payload", {}) or {}
        lifecycle.append({
            "type": event.get("type"),
            "source": payload.get("source"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "ts_short": _short_ts(event.get("ts")),
        })
        if len(lifecycle) >= limit:
            break

    return {
        "available": False,
        "window_days": usage.get("window_days", 30),
        "health_status": "unknown",
        "health_color": "muted",
        "declared_total": len(sources),
        "contract_only_total": status_counts.get("contract-only", 0),
        "active_total": status_counts.get("active", 0),
        "probed_total": 0,
        "broken_total": 0,
        "drifted_total": 0,
        "usage_30d_total": int(usage.get("total_calls", 0) or 0),
        "counts_by_effective_status": status_counts,
        "top_sources": [],
        "top_used": top_used[:limit],
        "lifecycle": lifecycle,
    }


def load_autonomy_summary():
    """Read autonomy capability/frontier files for operator-facing summary."""
    try:
        if not AUTONOMY_CAPABILITIES_FILE.exists():
            return {
                "available": False,
                "avg": None,
                "total": 0,
                "gaps": [],
                "next_steps": [],
            }
        content = AUTONOMY_CAPABILITIES_FILE.read_text(encoding="utf-8")
        rows = re.findall(r'^\|\s*\d+\s*\|([^|]+)\|\s*(\d+)\s*\|', content, re.MULTILINE)
        if not rows:
            return {
                "available": False,
                "avg": None,
                "total": 0,
                "gaps": [],
                "next_steps": [],
            }
        caps = [{"name": row[0].strip(), "level": int(row[1])} for row in rows]
        avg = round(sum(cap["level"] for cap in caps) / len(caps), 1)
        gaps = sorted(caps, key=lambda cap: cap["level"])[:3]
        next_steps = []
        if FRONTIER_FILE.exists():
            frontier = FRONTIER_FILE.read_text(encoding="utf-8")
            for match in re.finditer(r'### (?!~~)(GAP-\d+): (.+)', frontier):
                next_steps.append({"id": match.group(1), "title": match.group(2)})
        return {
            "available": True,
            "avg": avg,
            "total": len(caps),
            "gaps": gaps,
            "next_steps": next_steps[:4],
        }
    except Exception:
        return {
            "available": False,
            "avg": None,
            "total": 0,
            "gaps": [],
            "next_steps": [],
        }


def _task_priority_rank(priority):
    priority = str(priority or "P2").upper()
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(priority, 2)


def _normalize_task_entry(entry):
    if not isinstance(entry, dict):
        return None
    task_id = str(entry.get("id") or entry.get("task_id") or "").strip()
    if not task_id:
        return None

    history = entry.get("history", [])
    if not isinstance(history, list):
        history = []
    latest = history[-1] if history else {}
    if not isinstance(latest, dict):
        latest = {}

    priority = str(entry.get("priority") or "P2").upper()
    if priority not in {"P0", "P1", "P2", "P3"}:
        priority = "P2"

    status = str(entry.get("status") or "todo").lower()
    blocked = bool(entry.get("blocked"))
    if blocked and status not in {"done", "deferred"}:
        status = "blocked"

    title = str(entry.get("title") or entry.get("summary") or task_id).strip()
    summary = str(entry.get("summary") or "").strip()
    owner = str(entry.get("owner") or "operator").strip()
    updated_at = entry.get("updated_at") or latest.get("ts")
    criteria = entry.get("criteria", [])
    if isinstance(criteria, str):
        criteria = [criteria]
    if not isinstance(criteria, list):
        criteria = []

    return {
        "id": task_id,
        "title": title,
        "summary": summary,
        "status": status,
        "blocked": blocked,
        "priority": priority,
        "priority_rank": _task_priority_rank(priority),
        "priority_class": f"prio-{priority.lower()}",
        "owner": owner,
        "criteria": [str(item).strip() for item in criteria if str(item).strip()],
        "updated_at": updated_at,
        "updated_at_short": _short_ts(updated_at),
        "history": history,
        "history_count": len(history),
        "latest_action": latest.get("action"),
        "latest_reason": latest.get("reason"),
        "latest_value": latest.get("value"),
        "note_preview": str(latest.get("value") or "").strip(),
        "status_badge": {
            "done": "status-badge-done",
            "blocked": "status-badge-blocked",
            "ready": "status-badge-doing",
            "doing": "status-badge-doing",
            "acknowledged": "status-badge-doing",
            "deferred": "status-badge-todo",
            "todo": "status-badge-todo",
        }.get(status, "status-badge-todo"),
    }


def load_tasks_snapshot():
    """Load task snapshot with a tolerant shape for operator-facing interventions."""
    raw = load_json_safe(TASKS_SNAPSHOT_FILE, {"version": 1, "tasks": []})
    if isinstance(raw, list):
        tasks_raw = raw
        version = 1
    elif isinstance(raw, dict):
        tasks_raw = raw.get("tasks")
        if tasks_raw is None and isinstance(raw.get("items"), list):
            tasks_raw = raw["items"]
        version = raw.get("version", 1)
    else:
        tasks_raw = []
        version = 1

    if not isinstance(tasks_raw, list):
        tasks_raw = []

    tasks = []
    for item in tasks_raw:
        normalized = _normalize_task_entry(item)
        if normalized:
            tasks.append(normalized)

    tasks.sort(key=lambda item: (item["status"] == "done", item["blocked"] is False, item["priority_rank"], item["updated_at"] or ""), reverse=False)
    return {"version": version, "tasks": tasks}


def load_operator_actions(limit=8):
    """Load recent operator actions from the durable operator log."""
    actions = []
    for entry in reversed(_iter_jsonl(OPERATOR_ACTIONS_FILE)):
        if not isinstance(entry, dict):
            continue
        target_id = str(entry.get("target_id") or "").strip()
        action = str(entry.get("action") or "").strip()
        if not target_id or not action:
            continue
        actions.append({
            "target_id": target_id,
            "action": action,
            "reason": entry.get("reason"),
            "value": entry.get("value"),
            "ts": entry.get("ts"),
            "ts_short": _short_ts(entry.get("ts")),
        })
        if len(actions) >= limit:
            break
    return actions


def _parse_task_intent_message(text):
    if not text or not str(text).startswith("[task-intent]"):
        return None
    payload = {}
    for line in str(text).splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            payload[key] = value
    task_id = payload.get("task")
    action = payload.get("action")
    if not task_id or not action:
        return None
    return {
        "task_id": task_id,
        "action": action,
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "apply": payload.get("apply"),
        "note": payload.get("note"),
    }


def load_queued_task_intents(limit=8):
    """Read queued task interventions from the async chat inbox."""
    try:
        from dashboard_db import get_chats
    except Exception:
        return []

    intents = []
    for message in get_chats(unprocessed_only=True, limit=200):
        if message.get("author") != "user":
            continue
        parsed = _parse_task_intent_message(message.get("text", ""))
        if not parsed:
            continue
        intents.append({
            **parsed,
            "chat_id": message.get("id"),
            "processed": bool(message.get("processed")),
            "pinned": bool(message.get("pinned")),
            "ts": message.get("ts"),
            "ts_short": _short_ts(message.get("ts")),
        })
        if len(intents) >= limit:
            break
    return intents


def load_task_interventions(limit_tasks=6, limit_actions=8):
    """Build the task intervention read model for the dashboard."""
    snapshot = load_tasks_snapshot()
    tasks = snapshot["tasks"]
    attention = [task for task in tasks if task["status"] != "done"]
    if not attention:
        attention = tasks
    attention.sort(key=lambda item: (item["blocked"] is False, item["priority_rank"], item["updated_at"] or ""), reverse=False)
    queued = load_queued_task_intents(limit=limit_actions)
    operator_actions = load_operator_actions(limit=limit_actions)
    return {
        "tasks": attention[:limit_tasks],
        "tasks_total": len(tasks),
        "task_attention_count": len([task for task in tasks if task["status"] != "done"]),
        "queued_task_intents": queued,
        "queued_task_count": len(queued),
        "operator_actions": operator_actions,
        "operator_actions_total": len(operator_actions),
    }


def _entry_records():
    records = []
    if not ENTRIES_DIR.exists():
        return records
    for fp in sorted(ENTRIES_DIR.glob("*.md"), reverse=True):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            claims = fm.get("claims", [])
            if isinstance(claims, str):
                claims = [claims]
            if not isinstance(claims, list):
                claims = []
            threads = fm.get("threads", [])
            if isinstance(threads, str):
                threads = [t.strip() for t in threads.split(",") if t.strip()]
            if not isinstance(threads, list):
                threads = []
            records.append({
                "path": fp,
                "filename": fp.name,
                "slug": fp.stem,
                "title": fm.get("title", fp.stem),
                "date": str(fm.get("date", "")),
                "claims": claims,
                "threads": [str(t).strip() for t in threads if str(t).strip()],
                "report": fm.get("report"),
            })
        except Exception:
            continue
    return records


def load_claims_dashboard(limit=6):
    """Summarize claim state from entry frontmatter."""
    verified_total = 0
    open_total = 0
    recent = []
    for entry in _entry_records():
        for raw_claim in entry["claims"]:
            text = raw_claim.get("claim", "") if isinstance(raw_claim, dict) else str(raw_claim)
            status = raw_claim.get("status") if isinstance(raw_claim, dict) else None
            is_gap = str(text).startswith("!") or status in {"open", "disputed", "stale"}
            clean_text = str(text).lstrip("! ").strip()
            if not clean_text:
                continue
            if is_gap:
                open_total += 1
            else:
                verified_total += 1
            if len(recent) < limit:
                recent.append({
                    "text": clean_text,
                    "kind": "gap" if is_gap else "verified",
                    "kind_color": "red" if is_gap else "green",
                    "artifact_title": entry["title"],
                    "artifact_filename": entry["filename"],
                    "threads": entry["threads"],
                    "date": entry["date"],
                })
    return {
        "total": verified_total + open_total,
        "verified_total": verified_total,
        "open_total": open_total,
        "recent": recent,
    }


def load_strategy_dashboard(limit_topics=5, limit_objectives=5):
    """Summarize strategy text, topics, and active objectives."""
    summary_lines = []
    priorities = []
    if STRATEGY_FILE.exists():
        try:
            for line in STRATEGY_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("<!--"):
                    continue
                if stripped.startswith(("- ", "* ")):
                    priorities.append(stripped[2:].strip())
                elif not stripped.startswith("#") and len(summary_lines) < 2:
                    summary_lines.append(stripped)
        except Exception:
            pass

    topics = []
    if TOPICS_DIR.exists():
        for fp in sorted(TOPICS_DIR.glob("*.md")):
            try:
                raw = fp.read_text(encoding="utf-8", errors="replace")
                heading = next((line.lstrip("# ").strip() for line in raw.splitlines() if line.startswith("# ")), fp.stem)
                topics.append({"name": fp.stem, "title": heading})
            except Exception:
                continue

    thread_data = load_threads_enriched()
    objectives = []
    for thread in thread_data.get("threads", []):
        if thread.get("status") not in {"active", "proposed"}:
            continue
        objectives.append({
            "thread_id": thread["id"],
            "title": thread["title"],
            "goal": thread.get("goal") or thread["title"],
            "status": thread.get("status"),
            "next_step": thread.get("next_step"),
        })

    return {
        "available": STRATEGY_FILE.exists(),
        "summary": " ".join(summary_lines[:2]).strip(),
        "priorities": priorities[:4],
        "topics": topics[:limit_topics],
        "topics_total": len(topics),
        "objectives": objectives[:limit_objectives],
    }


def load_proposals_dashboard(limit=5):
    """Summarize active proposals and recent decisions."""
    active = []
    for proposal in load_json_safe(PROPOSALS_FILE, []):
        if proposal.get("status") != "active":
            continue
        active.append({
            "id": proposal.get("id"),
            "title": proposal.get("title", "untitled"),
            "type": proposal.get("type", "proposal"),
            "updated_short": _short_ts(proposal.get("updated") or proposal.get("created")),
            "evidence_count": len(proposal.get("evidence", []) or []),
            "cost": proposal.get("cost"),
        })
    active.sort(key=lambda item: item.get("updated_short", ""), reverse=True)

    decisions = []
    decision_path = SIGNALS_DIR / "decision.md"
    if decision_path.exists():
        try:
            for line in reversed(decision_path.read_text(encoding="utf-8", errors="replace").splitlines()):
                stripped = line.strip()
                if stripped.startswith(("- ", "* ")):
                    decisions.append(stripped[2:].strip())
                if len(decisions) >= limit:
                    break
        except Exception:
            pass

    return {
        "active_count": len(active),
        "active": active[:limit],
        "decisions": decisions,
    }


def load_lineage_dashboard(limit=6):
    """Build recent claim -> thread -> artifact lineage rows."""
    lineage = []
    for entry in _entry_records():
        for raw_claim in entry["claims"]:
            text = raw_claim.get("claim", "") if isinstance(raw_claim, dict) else str(raw_claim)
            status = raw_claim.get("status") if isinstance(raw_claim, dict) else None
            clean_text = str(text).lstrip("! ").strip()
            if not clean_text:
                continue
            is_gap = str(text).startswith("!") or status in {"open", "disputed", "stale"}
            lineage.append({
                "claim": clean_text,
                "claim_status": "gap" if is_gap else "verified",
                "claim_color": "red" if is_gap else "green",
                "threads": entry["threads"],
                "artifact_title": entry["title"],
                "artifact_filename": entry["filename"],
                "report": entry["report"],
                "date": entry["date"],
            })
            if len(lineage) >= limit:
                return lineage
    return lineage


def load_hotspots():
    return load_json_safe(OPS_HOTSPOTS, {
        "incidents": [], "top_pain": [],
        "recovered_but_unstable": [], "codify_now": []
    })


def load_git_signals():
    return load_json_safe(GIT_SIGNALS, {
        "fix_chains": [], "duplicate_slugs": [],
        "pipeline_failures": [], "state_violations": [],
        "thread_coverage": {}, "skill_distribution": {},
        "claims_summary": {}, "persistent_gaps": []
    })


def load_curadoria():
    return load_json_safe(CURADORIA_CANDIDATES, {
        "total_docs": 0, "stale_candidates": 0,
        "archive_auto": [], "merge_review": [],
        "strengthen_targets": []
    })


def get_publish_commits(limit=10):
    """Get last N git commits matching 'publish:' pattern."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--oneline",
             "--grep=publish:", f"-{limit}", "--format=%H|%s|%aI"],
            capture_output=True, text=True, timeout=5
        )
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            hash_val, subject, timestamp = parts
            # Parse status from subject: publish: slug [state:ok|partial|failed]
            status = "ok"
            if "[state:partial]" in subject:
                status = "partial"
            elif "[state:failed]" in subject:
                status = "failed"
            # Extract slug
            slug = subject.replace("publish:", "").strip()
            slug = slug.split("[")[0].strip()

            commits.append({
                "hash": hash_val,
                "slug": slug,
                "status": status,
                "subject": subject,
                "timestamp": timestamp,
            })
        return commits
    except Exception:
        return []


def get_error_pressure_24h():
    """Count failures in last 24h from execution-ledger.jsonl."""
    failures = 0
    tool_failures = {}
    try:
        if not EXECUTION_LEDGER.exists():
            return {"failures_24h": 0, "top_failing_tool": None}
        now = datetime.now(timezone.utc)
        for line in EXECUTION_LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
                if (now - ts).total_seconds() > 86400:
                    continue
                if not entry.get("ok", True):
                    failures += 1
                    tool = entry.get("tool", "unknown")
                    tool_failures[tool] = tool_failures.get(tool, 0) + 1
            except Exception:
                continue
    except Exception:
        pass

    top_tool = None
    if tool_failures:
        top_tool = max(tool_failures, key=tool_failures.get)

    return {"failures_24h": failures, "top_failing_tool": top_tool}


def get_production_stats():
    """Count entries, reports, and today's publications."""
    total_entries = 0
    total_reports = 0
    published_today = 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        if ENTRIES_DIR.exists():
            for fp in ENTRIES_DIR.glob("*.md"):
                total_entries += 1
                raw = fp.read_text(encoding="utf-8", errors="replace")
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        import yaml
                        fm = yaml.safe_load(parts[1])
                        if fm and fm.get("report"):
                            total_reports += 1
                        if fm and str(fm.get("date", "")) == today_str:
                            published_today += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return {
        "entries_total": total_entries,
        "reports_total": total_reports,
        "published_today": published_today,
    }

def get_briefing_html(max_lines=50):
    """Load first max_lines of briefing.md and render as HTML. Returns None if missing."""
    try:
        if not BRIEFING_FILE.exists():
            return None
        lines = BRIEFING_FILE.read_text(encoding="utf-8").splitlines()[:max_lines]
        md_text = "\n".join(lines)
        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        return None


def get_heartbeat_status():
    """Check heartbeat health: healthy/late/stalled."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "claude-heartbeat.timer"],
            capture_output=True, text=True, timeout=3
        )
        if result.stdout.strip() == "active":
            return {"status": "healthy", "color": "green"}
    except Exception:
        pass
    # Check last heartbeat log file timestamp
    try:
        logs = sorted(LOGS_DIR.glob("heartbeat-*.log"), reverse=True)
        if logs:
            mtime = datetime.fromtimestamp(logs[0].stat().st_mtime, tz=timezone.utc)
            hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
            if hours < 3:
                return {"status": "healthy", "color": "green"}
            elif hours < 6:
                return {"status": "late", "color": "yellow"}
            else:
                return {"status": "stalled", "color": "red"}
    except Exception:
        pass
    return {"status": "unknown", "color": "yellow"}


# ─── Threads ───

def _build_entries_thread_index():
    """Build {thread_id: count} from entry frontmatter."""
    index = {}
    if not ENTRIES_DIR.exists():
        return index
    for fp in ENTRIES_DIR.glob("*.md"):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue
            threads = fm.get("threads", [])
            if isinstance(threads, str):
                threads = [t.strip() for t in threads.split(",")]
            if not isinstance(threads, list):
                continue
            for tid in threads:
                tid = str(tid).strip()
                if tid:
                    index[tid] = index.get(tid, 0) + 1
        except Exception:
            continue
    return index


def _parse_next_step(raw_body):
    """Extract first non-empty line after ## Próximo passo or ## Next."""
    match = re.search(r"^##\s+(?:Próximo passo|Next)\s*$", raw_body, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    after = raw_body[match.end():]
    for line in after.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def load_threads_enriched(status_filter=None):
    """Load threads with enriched metadata (entries_count, resurface_due, next_step)."""
    if not THREADS_DIR.exists():
        return {"threads": [], "stats": {"total": 0, "active": 0, "dormant": 0, "done": 0, "proposed": 0, "resurface_due": 0}}

    entries_index = _build_entries_thread_index()
    today = date.today()
    threads = []
    stats = {"total": 0, "active": 0, "dormant": 0, "done": 0, "proposed": 0, "resurface_due": 0}

    for fp in sorted(THREADS_DIR.glob("*.md")):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue

            thread_id = fm.get("id", fp.stem)
            status = fm.get("status", "active")
            entries_count = entries_index.get(thread_id, 0) or entries_index.get(fp.stem, 0)
            next_step = _parse_next_step(parts[2])

            # Resurface check
            resurface_str = fm.get("resurface")
            resurface_due = False
            if resurface_str:
                try:
                    rd = date.fromisoformat(str(resurface_str))
                    resurface_due = rd <= today
                except (ValueError, TypeError):
                    pass

            stats["total"] += 1
            if status in stats:
                stats[status] += 1
            if resurface_due and status == "active":
                stats["resurface_due"] += 1

            threads.append({
                "id": thread_id,
                "title": fm.get("title", fp.stem),
                "type": fm.get("type", "investigation"),
                "status": status,
                "owner": fm.get("owner", "unknown"),
                "created": str(fm.get("created", "")),
                "updated": str(fm.get("updated", "")),
                "resurface": str(resurface_str) if resurface_str else None,
                "goal": fm.get("goal"),
                "done_when": fm.get("done_when"),
                "entries_count": entries_count,
                "resurface_due": resurface_due,
                "next_step": next_step,
            })
        except Exception:
            continue

    if status_filter:
        threads = [t for t in threads if t["status"] == status_filter]

    return {"threads": threads, "stats": stats}


def load_thread_detail(thread_id):
    """Load full detail for a single thread: metadata, body, linked entries, reports, claims."""
    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return None

    raw = thread_path.read_text(encoding="utf-8", errors="replace")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    body_md = parts[2].strip()
    body_html = markdown.markdown(body_md, extensions=["tables", "fenced_code"])

    # Collect all entries linked to this thread
    entries = []
    all_claims = []
    reports_set = set()
    if ENTRIES_DIR.exists():
        for fp in sorted(ENTRIES_DIR.glob("*.md"), key=lambda p: p.name, reverse=True):
            try:
                eraw = fp.read_text(encoding="utf-8", errors="replace")
                eparts = eraw.split("---", 2)
                if len(eparts) < 3:
                    continue
                efm = yaml.safe_load(eparts[1])
                if not efm:
                    continue
                threads = efm.get("threads", [])
                if isinstance(threads, str):
                    threads = [t.strip() for t in threads.split(",")]
                if not isinstance(threads, list):
                    continue
                if thread_id not in [str(t).strip() for t in threads]:
                    continue
                entry_claims = efm.get("claims", [])
                if isinstance(entry_claims, str):
                    entry_claims = [entry_claims]
                if not isinstance(entry_claims, list):
                    entry_claims = []
                report_file = efm.get("report", "")
                note_file = efm.get("note", "")
                if report_file:
                    reports_set.add(report_file)
                entries.append({
                    "slug": fp.stem,
                    "title": efm.get("title", fp.stem),
                    "date": str(efm.get("date", "")),
                    "tags": efm.get("tags", []),
                    "claims": entry_claims,
                    "report": report_file,
                    "note": note_file,
                })
                all_claims.extend(entry_claims)
            except Exception:
                continue

    # Check which reports exist on disk
    reports = []
    for rf in sorted(reports_set):
        rpath = REPORTS_DIR / rf
        reports.append({
            "filename": rf,
            "exists": rpath.exists(),
            "url": f"/reports/{rf}" if rpath.exists() else None,
        })

    # Separate claims by type
    verified = [c for c in all_claims if not str(c).startswith("!")]
    gaps = [c for c in all_claims if str(c).startswith("!")]

    return {
        "id": fm.get("id", thread_id),
        "title": fm.get("title", thread_id),
        "type": fm.get("type", "investigation"),
        "status": fm.get("status", "active"),
        "owner": fm.get("owner", "unknown"),
        "created": str(fm.get("created", "")),
        "updated": str(fm.get("updated", "")),
        "resurface": str(fm.get("resurface", "")),
        "goal": fm.get("goal"),
        "done_when": fm.get("done_when"),
        "body_html": body_html,
        "entries": entries,
        "entries_count": len(entries),
        "reports": reports,
        "claims": all_claims,
        "claims_verified": verified,
        "claims_gaps": gaps,
        "claims_count": len(all_claims),
        "verified_count": len(verified),
        "gaps_count": len(gaps),
    }


_GENERIC_TAGS = {
    "pesquisa", "descoberta", "lazer", "reflexao", "execucao", "estrategia",
    "planejamento", "workflow", "anti-pattern", "relatorio", "calibracao",
    "blog", "heartbeat", "auditoria",
}


def compute_thread_candidates():
    """Detect recurring tags in entries that don't have a corresponding thread."""
    if not ENTRIES_DIR.exists():
        return []

    thread_ids = set()
    if THREADS_DIR.exists():
        for fp in THREADS_DIR.glob("*.md"):
            thread_ids.add(fp.stem)

    tag_entries = {}
    for fp in sorted(ENTRIES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            if not isinstance(tags, list):
                continue
            entry_info = {
                "title": fm.get("title", fp.stem),
                "date": str(fm.get("date", "")),
                "slug": fp.stem,
            }
            for tag in tags:
                tag = str(tag).strip().lower()
                if tag and tag not in _GENERIC_TAGS and tag not in thread_ids:
                    tag_entries.setdefault(tag, []).append(entry_info)
        except Exception:
            continue

    candidates = []
    for tag, entries in sorted(tag_entries.items(), key=lambda x: -len(x[1])):
        if len(entries) >= 3:
            candidates.append({
                "tag": tag,
                "entry_count": len(entries),
                "recent_entries": entries[:3],
            })

    return candidates
