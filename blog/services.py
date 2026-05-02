"""Shared service helpers for dashboard and action blueprints."""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from hashlib import sha1
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
    EVENTS_FILE,
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


def _claim_id(artifact_filename, text):
    seed = f"{artifact_filename}:{text}".encode("utf-8", errors="ignore")
    return f"claim-{sha1(seed).hexdigest()[:12]}"


def _claim_surface_id(text):
    return _surface_id("claim", str(text or "").strip().lower())


def _surface_id(prefix, *parts):
    seed = "||".join(str(part).strip() for part in parts if str(part).strip())
    return f"{prefix}-{sha1(seed.encode('utf-8', errors='ignore')).hexdigest()[:12]}"


def _surface_href(target_type, reference=None, target_id=None):
    reference = str(reference or "").strip()
    target_id = str(target_id or "").strip()
    if not target_type or not reference:
        if target_type == "proposal" and target_id:
            return f"/proposal/{target_id}"
        return None
    if target_type == "claim" and reference.endswith(".md"):
        return f"/blog/entries/{reference}"
    if target_type in {"objective", "thread"}:
        return f"/thread/{reference}"
    if target_type == "proposal":
        proposal_id = target_id or reference
        return f"/proposal/{proposal_id}" if proposal_id else None
    return None


def _parse_ts_value(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


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
            "id": "pre-skill",
            "status": "observed" if pre_events else "gap",
            "color": "green" if pre_events else "red",
            "detail": f"{len(pre_events)} explicit pre-skill events" if pre_events else "no explicit pre-skill runtime evidence in shadow log yet",
            "protocol_status": current.get("preflight_status", "unknown"),
            "reference": current.get("cycle_id"),
        },
        "post_skill": {
            "id": "post-skill",
            "status": "observed" if post_events else "gap",
            "color": "green" if post_events else "red",
            "detail": f"{len(post_events)} explicit post-skill events" if post_events else "no explicit post-skill runtime evidence in shadow log yet",
            "protocol_status": current.get("postflight_status", "unknown"),
            "reference": current.get("cycle_id"),
        },
        "skill_runs": runs,
        "skill_runs_total": len(runs),
        "silent_skips_total": total_silent,
        "explicit_skips_total": total_explicit,
    }


def load_primitive_runtime_summary(limit=5):
    """Summarize primitives using the canonical primitives-status read model."""
    def _normalize_effective_status(value):
        status = str(value or "unknown")
        if status in {"declared", "contract-only", "drifted"}:
            return "degraded"
        return status

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
        sources = [
            {
                **item,
                "effective_status": _normalize_effective_status(item.get("effective_status")),
                "id": item.get("name"),
                "reference": item.get("name"),
            }
            for item in sources
            if isinstance(item, dict)
        ]
        degraded_total = int(summary.get("degraded_total", 0) or 0)
        if not degraded_total:
            degraded_total = int(summary.get("declared_only_total", 0) or 0) + int(summary.get("contract_only_total", 0) or 0) + int(summary.get("drifted_total", 0) or 0)
        top_used = sorted(sources, key=lambda item: (-int(item.get("usage_30d", 0) or 0), item.get("name", "")))
        return {
            "available": True,
            "window_days": int(summary.get("window_days", 30) or 30),
            "health_status": summary.get("health_status", "unknown"),
            "health_color": "red" if summary.get("health_status") == "fail" else "yellow" if summary.get("health_status") == "degraded" else "green",
            "declared_total": int(summary.get("declared_total", 0) or 0),
            "degraded_total": degraded_total,
            "active_total": int(summary.get("active_total", 0) or 0),
            "probed_total": int(summary.get("probed_total", 0) or 0),
            "broken_total": int(summary.get("broken_total", 0) or 0),
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
        "degraded_total": status_counts.get("declared", 0) + status_counts.get("contract-only", 0) + status_counts.get("degraded", 0),
        "active_total": status_counts.get("active", 0),
        "probed_total": 0,
        "broken_total": 0,
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
                "recovered": [],
                "codify_now": [],
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
                "recovered": [],
                "codify_now": [],
            }
        caps = [{
            "id": _surface_id("cap", row[0].strip()),
            "name": row[0].strip(),
            "level": int(row[1]),
            "reference": row[0].strip(),
        } for row in rows]
        avg = round(sum(cap["level"] for cap in caps) / len(caps), 1)
        gaps = sorted(caps, key=lambda cap: cap["level"])[:3]
        next_steps = []
        if FRONTIER_FILE.exists():
            frontier = FRONTIER_FILE.read_text(encoding="utf-8")
            for match in re.finditer(r'### (?!~~)(GAP-\d+): (.+)', frontier):
                next_steps.append({
                    "id": match.group(1),
                    "title": match.group(2),
                    "reference": match.group(1),
                })
        hotspots = load_hotspots()
        recovered = []
        for item in hotspots.get("recovered_but_unstable", [])[:3]:
            if not isinstance(item, dict):
                continue
            signature = str(item.get("signature") or "").strip()
            if not signature:
                continue
            recovered.append({
                "id": _surface_id("recovered", signature),
                "signature": signature,
                "count": int(item.get("count", 0) or 0),
                "last_seen": item.get("last_seen"),
                "last_seen_short": _short_ts(item.get("last_seen")),
                "reference": signature,
            })
        codify_now = []
        for item in hotspots.get("codify_now", [])[:3]:
            if not isinstance(item, dict):
                continue
            signature = str(item.get("signature") or "").strip()
            if not signature:
                continue
            codify_now.append({
                "id": _surface_id("codify", signature),
                "signature": signature,
                "count": int(item.get("count", 0) or 0),
                "last_seen": item.get("last_seen"),
                "last_seen_short": _short_ts(item.get("last_seen")),
                "reference": signature,
            })
        return {
            "available": True,
            "avg": avg,
            "total": len(caps),
            "gaps": gaps,
            "next_steps": next_steps[:4],
            "recovered": recovered,
            "codify_now": codify_now,
        }
    except Exception:
        return {
            "available": False,
            "avg": None,
            "total": 0,
            "gaps": [],
            "next_steps": [],
            "recovered": [],
            "codify_now": [],
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
        target_type = str(entry.get("target_type") or "").strip() or None
        reference = str(entry.get("reference") or "").strip() or None
        actions.append({
            "target_id": target_id,
            "action": action,
            "display_action": action.split(":", 1)[1] if ":" in action else action,
            "target_type": target_type,
            "label": entry.get("label") or target_id,
            "reference": reference,
            "href": entry.get("href") or _surface_href(target_type, reference=reference, target_id=target_id),
            "resulting_state": entry.get("resulting_state"),
            "apply": entry.get("apply"),
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
        messages = get_chats(unprocessed_only=True, limit=200)
    except Exception:
        return []

    intents = []
    for message in messages:
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


def _parse_steering_intent_message(text):
    if not text or not str(text).startswith("[steering-intent]"):
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
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    action = payload.get("action")
    if not target_type or not target_id or not action:
        return None
    reference = payload.get("reference")
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": payload.get("label") or target_id,
        "reference": reference,
        "href": _surface_href(target_type, reference=reference, target_id=target_id),
        "resulting_state": payload.get("resulting_state"),
        "apply": payload.get("apply"),
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "note": payload.get("note"),
    }


def load_queued_steering_intents(limit=8):
    """Read queued epistemic steering intents from the async chat inbox."""
    try:
        from dashboard_db import get_chats
        messages = get_chats(unprocessed_only=True, limit=200)
    except Exception:
        return []

    intents = []
    for message in messages:
        if message.get("author") != "user":
            continue
        parsed = _parse_steering_intent_message(message.get("text", ""))
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


def load_epistemic_steering(limit_actions=8):
    """Build queued steering and steering trace read models."""
    queued = load_queued_steering_intents(limit=limit_actions)
    trace = [
        item for item in load_operator_actions(limit=200)
        if item["action"].startswith("steering:")
    ][:limit_actions]
    return {
        "queued": queued,
        "queued_count": len(queued),
        "trace": trace,
        "trace_count": len(trace),
    }


def _parse_runtime_intent_message(text):
    if not text or not str(text).startswith("[runtime-intent]"):
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
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    action = payload.get("action")
    if not target_type or not target_id or not action:
        return None
    reference = payload.get("reference")
    return {
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "label": payload.get("label") or target_id,
        "reference": reference,
        "href": _surface_href(target_type, reference=reference, target_id=target_id),
        "resulting_state": payload.get("resulting_state"),
        "apply": payload.get("apply"),
        "reason": payload.get("reason"),
        "value": payload.get("value"),
        "note": payload.get("note"),
    }


def load_queued_runtime_intents(limit=8):
    """Read queued runtime/autonomy interventions from the async chat inbox."""
    try:
        from dashboard_db import get_chats
        messages = get_chats(unprocessed_only=True, limit=200)
    except Exception:
        return []

    intents = []
    for message in messages:
        if message.get("author") != "user":
            continue
        parsed = _parse_runtime_intent_message(message.get("text", ""))
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


def _match_followup_task(value):
    needle = str(value or "").strip().lower()
    if not needle:
        return None
    for task in load_tasks_snapshot()["tasks"]:
        hay = " ".join([task["id"], task["title"]]).lower()
        if needle in hay or task["id"].lower() == needle:
            return {
                "type": "task",
                "id": task["id"],
                "label": task["title"],
                "href": "/dashboard",
            }
    return None


def _match_followup_proposal(value):
    needle = str(value or "").strip().lower()
    if not needle:
        return None
    for proposal in load_json_safe(PROPOSALS_FILE, []):
        if not isinstance(proposal, dict):
            continue
        title = str(proposal.get("title") or "").strip()
        proposal_id = str(proposal.get("id") or "").strip()
        hay = " ".join([proposal_id, title]).lower()
        if needle in hay or proposal_id.lower() == needle:
            return {
                "type": "proposal",
                "id": proposal_id or needle,
                "label": title or proposal_id or needle,
                "href": "/dashboard",
            }
    return None


def _find_downstream_cycles(after_ts, exclude_cycle_id=None, limit=2):
    after_dt = _parse_ts_value(after_ts)
    if not after_dt:
        return []
    matches = []
    for cycle in load_recent_dispatch_cycles(limit=24):
        cycle_id = cycle.get("cycle_id")
        if exclude_cycle_id and cycle_id == exclude_cycle_id:
            continue
        cycle_ts = _parse_ts_value(cycle.get("opened_at")) or _parse_ts_value(cycle.get("last_ts"))
        if not cycle_ts or cycle_ts <= after_dt:
            continue
        matches.append({
            "cycle_id": cycle_id,
            "skill": cycle.get("skill"),
            "trigger": cycle.get("trigger"),
            "last_ts_short": cycle.get("last_ts_short"),
        })
        if len(matches) >= limit:
            break
    return matches


def load_runtime_interventions(limit_actions=8):
    """Build queued runtime interventions and a lineage-oriented trace."""
    queued = load_queued_runtime_intents(limit=limit_actions)
    trace = [
        item for item in load_operator_actions(limit=200)
        if item["action"].startswith("runtime:")
    ][:limit_actions]

    lineage = []
    for item in trace:
        followup = None
        if item["display_action"] == "promote-task":
            followup = _match_followup_task(item.get("value"))
        lineage.append({
            **item,
            "downstream_cycles": _find_downstream_cycles(item.get("ts"), exclude_cycle_id=item.get("reference") or item.get("target_id")),
            "downstream_target": followup,
        })

    return {
        "queued": queued,
        "queued_count": len(queued),
        "trace": trace,
        "trace_count": len(trace),
        "lineage": lineage,
        "lineage_count": len(lineage),
    }


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
            open_gaps = fm.get("open_gaps", [])
            if isinstance(open_gaps, str):
                open_gaps = [open_gaps]
            if not isinstance(open_gaps, list):
                open_gaps = []
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
                "claims": [],
                "open_gaps": open_gaps,
                "threads": [str(t).strip() for t in threads if str(t).strip()],
                "report": fm.get("report"),
            })
        except Exception:
            continue
    return records


CLAIM_STALE_DAYS = 14
CLAIM_ACTION_COPY = {
    "promote": {
        "label": "Turn into proposal",
        "detail": "Escalate this claim into explicit work for the next dispatch.",
    },
    "verified": {
        "label": "Mark supported",
        "detail": "Treat the claim as sufficiently supported by current evidence.",
    },
    "disputed": {
        "label": "Mark contested",
        "detail": "Keep the claim explicitly contested until evidence improves.",
    },
    "stale": {
        "label": "Needs fresh evidence",
        "detail": "Ask the next dispatch to refresh or strengthen the evidence.",
    },
}


def _claim_action_copy(action):
    action = str(action or "").strip().lower()
    meta = CLAIM_ACTION_COPY.get(action)
    if meta:
        return dict(meta)
    label = action.replace("-", " ").strip() or "take action"
    return {
        "label": label.capitalize(),
        "detail": "Queue a steering action for the next dispatch.",
    }


def _decorate_claim_action(item, action_key):
    if not item:
        return None
    meta = _claim_action_copy(action_key)
    return {
        **item,
        "action_label": meta["label"],
        "action_detail": meta["detail"],
    }


def _claim_evidence_strength(support_count, reports_count, single_source):
    if support_count >= 3 or (support_count >= 2 and reports_count >= 1):
        return {
            "label": "grounded",
            "detail": "Multiple artifacts and at least some published evidence support this claim.",
        }
    if support_count >= 2 or reports_count >= 1:
        return {
            "label": "moderate",
            "detail": "There is more than one signal, but the support still has visible gaps.",
        }
    if single_source:
        return {
            "label": "thin",
            "detail": "This claim currently hangs on a single artifact.",
        }
    return {
        "label": "unknown",
        "detail": "No reliable support strength could be derived.",
    }


def _claim_linked_work_summary(thread_links):
    if not thread_links:
        return "No linked thread yet."
    titles = [item["title"] for item in thread_links[:2]]
    summary = ", ".join(titles)
    remaining = len(thread_links) - len(titles)
    if remaining > 0:
        summary += f" +{remaining} more"
    return summary


def _claim_why_now(kind, no_thread, no_report, stale, stale_days):
    reasons = []
    if kind == "gap":
        reasons.append("This claim is still an open evidence gap.")
    if no_thread:
        reasons.append("No thread currently owns it.")
    if no_report:
        reasons.append("There is no published report backing it yet.")
    if stale:
        days = stale_days if stale_days is not None else "?"
        reasons.append(f"The latest evidence is {days}d old.")
    if reasons:
        return " ".join(reasons)
    return "This claim is supported, linked, and not asking for immediate intervention."


def _claim_recommended_action(kind, no_thread, no_report, stale, single_source, queued_steering):
    if queued_steering:
        return None
    if no_thread:
        return {
            "action": "promote",
            "label": CLAIM_ACTION_COPY["promote"]["label"],
            "reason": "No continuity surface owns this claim yet, so it should become explicit work.",
        }
    if kind == "gap":
        return {
            "action": "disputed",
            "label": CLAIM_ACTION_COPY["disputed"]["label"],
            "reason": "Keep it explicitly contested until the supporting evidence becomes stronger.",
        }
    if stale or no_report or single_source:
        return {
            "action": "stale",
            "label": CLAIM_ACTION_COPY["stale"]["label"],
            "reason": "The evidence is too thin, too old, or insufficiently published to leave untouched.",
        }
    return None


def _build_claim_operator_action_index(limit_per_claim=6):
    rollup = {}
    for item in load_operator_actions(limit=200):
        if item.get("target_type") != "claim":
            continue
        claim_id = str(item.get("target_id") or "").strip()
        if not claim_id:
            continue
        bucket = rollup.setdefault(claim_id, [])
        if len(bucket) < limit_per_claim:
            bucket.append(_decorate_claim_action(item, item.get("display_action")))
    return rollup


def _build_claim_queued_intent_index(limit_per_claim=6):
    rollup = {}
    for item in load_queued_steering_intents(limit=200):
        if item.get("target_type") != "claim":
            continue
        claim_id = str(item.get("target_id") or "").strip()
        if not claim_id:
            continue
        bucket = rollup.setdefault(claim_id, [])
        if len(bucket) < limit_per_claim:
            bucket.append(_decorate_claim_action(item, item.get("action")))
    return rollup


def _claim_occurrence_records():
    records = []
    for entry in _entry_records():
        for raw_claim in entry["claims"]:
            text = raw_claim.get("claim", "") if isinstance(raw_claim, dict) else str(raw_claim)
            status = raw_claim.get("status") if isinstance(raw_claim, dict) else None
            is_gap = str(text).startswith("!") or status in {"open", "disputed", "stale"}
            clean_text = str(text).lstrip("! ").strip()
            if not clean_text:
                continue
            records.append({
                "claim_id": _claim_surface_id(clean_text),
                "claim_occurrence_id": _claim_id(entry["filename"], clean_text),
                "text": clean_text,
                "kind": "gap" if is_gap else "verified",
                "kind_color": "red" if is_gap else "green",
                "artifact_title": entry["title"],
                "artifact_filename": entry["filename"],
                "artifact_href": f"/blog/entries/{entry['filename']}",
                "threads": entry["threads"],
                "reference": entry["filename"],
                "report": entry["report"],
                "date": entry["date"],
                "_sort_ts": _parse_ts_value(entry["date"]),
            })
    return records


def _claim_records():
    claims = {}
    operator_index = _build_claim_operator_action_index()
    queued_index = _build_claim_queued_intent_index()
    thread_index = {
        item["id"]: item
        for item in load_threads_enriched().get("threads", [])
    }
    today = date.today()

    for item in _claim_occurrence_records():
        claim_id = item["claim_id"]
        bucket = claims.setdefault(claim_id, {
            "claim_id": claim_id,
            "text": item["text"],
            "occurrences": [],
            "threads": set(),
            "report_files": set(),
            "artifact_files": set(),
            "verified_occurrences": 0,
            "gap_occurrences": 0,
            "latest_occurrence": None,
        })
        bucket["occurrences"].append(item)
        bucket["threads"].update(item.get("threads") or [])
        if item.get("report"):
            bucket["report_files"].add(item["report"])
        bucket["artifact_files"].add(item["artifact_filename"])
        if item["kind"] == "gap":
            bucket["gap_occurrences"] += 1
        else:
            bucket["verified_occurrences"] += 1
        bucket["latest_occurrence"] = _latest_item(bucket["latest_occurrence"], dict(item))

    records = []
    for claim_id, bucket in claims.items():
        occurrences = bucket["occurrences"]
        occurrences.sort(key=lambda row: row.get("_sort_ts") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        latest = bucket["latest_occurrence"] or (occurrences[0] if occurrences else None)
        kind = "gap" if bucket["gap_occurrences"] > 0 else "verified"
        kind_color = "red" if kind == "gap" else "green"
        latest_ts = _parse_ts_value(latest.get("date")) if latest else None
        latest_date = latest_ts.date() if latest_ts else _parse_date_value(latest.get("date") if latest else None)
        stale_days = (today - latest_date).days if latest_date else None
        stale = stale_days is not None and stale_days >= CLAIM_STALE_DAYS
        no_thread = len(bucket["threads"]) == 0
        no_report = len(bucket["report_files"]) == 0
        single_source = len(bucket["artifact_files"]) == 1
        reports_count = len(bucket["report_files"])
        thread_links = [
            {
                "id": tid,
                "title": thread_index.get(tid, {}).get("title", tid),
                "status": thread_index.get(tid, {}).get("status"),
                "href": f"/thread/{tid}",
            }
            for tid in sorted(bucket["threads"])
        ]
        evidence_strength = _claim_evidence_strength(
            support_count=len(bucket["artifact_files"]),
            reports_count=reports_count,
            single_source=single_source,
        )
        flags = []
        attention_score = 0
        if kind == "gap":
            flags.append({"kind": "warn", "label": "open gap", "detail": "claim is still open, disputed, or stale"})
            attention_score += 5
        if no_thread:
            flags.append({"kind": "warn", "label": "no thread", "detail": "claim is not linked to any continuity surface"})
            attention_score += 3
        if no_report:
            flags.append({"kind": "warn", "label": "no report", "detail": "claim has no published report evidence"})
            attention_score += 2
        if single_source:
            flags.append({"kind": "muted", "label": "single source", "detail": "claim appears in only one artifact"})
            attention_score += 1
        if stale:
            flags.append({"kind": "warn", "label": "stale", "detail": f"{stale_days}d since last supporting artifact"})
            attention_score += 2

        recent_operator_action = (operator_index.get(claim_id) or [None])[0]
        queued_steering = (queued_index.get(claim_id) or [None])[0]
        why_now = _claim_why_now(
            kind=kind,
            no_thread=no_thread,
            no_report=no_report,
            stale=stale,
            stale_days=stale_days,
        )
        best_evidence = {
            "label": latest.get("artifact_title") if latest else None,
            "href": latest.get("artifact_href") if latest else None,
            "date_short": _short_ts(latest.get("date")) if latest else "",
            "report": latest.get("report") if latest else None,
        } if latest else None
        recommended_action = _claim_recommended_action(
            kind=kind,
            no_thread=no_thread,
            no_report=no_report,
            stale=stale,
            single_source=single_source,
            queued_steering=queued_steering,
        )
        support_summary_parts = [
            f"{len(bucket['artifact_files'])} artifact{'s' if len(bucket['artifact_files']) != 1 else ''}",
            f"{reports_count} report{'s' if reports_count != 1 else ''}",
        ]
        if thread_links:
            support_summary_parts.append(_claim_linked_work_summary(thread_links))
        else:
            support_summary_parts.append("no linked thread")

        records.append({
            "claim_id": claim_id,
            "text": bucket["text"],
            "kind": kind,
            "kind_color": kind_color,
            "judgment_label": "needs support" if kind == "gap" else "supported",
            "verified_occurrences": bucket["verified_occurrences"],
            "gap_occurrences": bucket["gap_occurrences"],
            "support_count": len(bucket["artifact_files"]),
            "reports_count": reports_count,
            "threads": sorted(bucket["threads"]),
            "thread_links": thread_links,
            "reference": latest.get("artifact_filename") if latest else None,
            "artifact_title": latest.get("artifact_title") if latest else None,
            "artifact_filename": latest.get("artifact_filename") if latest else None,
            "artifact_href": latest.get("artifact_href") if latest else None,
            "report": latest.get("report") if latest else None,
            "date": latest.get("date") if latest else None,
            "date_short": _short_ts(latest.get("date")) if latest else "",
            "latest_artifact_title": latest.get("artifact_title") if latest else None,
            "latest_artifact_href": latest.get("artifact_href") if latest else None,
            "latest_artifact_filename": latest.get("artifact_filename") if latest else None,
            "latest_report": latest.get("report") if latest else None,
            "best_evidence": best_evidence,
            "why_now": why_now,
            "support_summary": " · ".join(support_summary_parts),
            "linked_work_summary": _claim_linked_work_summary(thread_links),
            "evidence_strength_label": evidence_strength["label"],
            "evidence_strength_detail": evidence_strength["detail"],
            "recommended_action": recommended_action,
            "flags": flags,
            "no_thread": no_thread,
            "no_report": no_report,
            "single_source": single_source,
            "stale": stale,
            "stale_days": stale_days,
            "needs_attention": bool(kind == "gap" or no_thread or no_report or stale),
            "attention_score": attention_score,
            "recent_operator_action": recent_operator_action,
            "queued_steering": queued_steering,
            "occurrences": occurrences,
        })

    records.sort(
        key=lambda item: (
            not item.get("needs_attention"),
            -(item.get("attention_score") or 0),
            item.get("date") or "",
            item.get("text") or "",
        ),
        reverse=False,
    )
    return records


def _load_legacy_claims_dashboard(limit=6):
    """Summarize claims into an operator-facing dashboard workbench."""
    claims = _claim_records()
    verified_total = len([item for item in claims if item["kind"] == "verified"])
    open_total = len([item for item in claims if item["kind"] == "gap"])
    attention = [item for item in claims if item["needs_attention"]]
    verified_recent = [item for item in claims if item["kind"] == "verified" and not item["needs_attention"]]
    queued_count = len([item for item in claims if item.get("queued_steering")])
    return {
        "total": verified_total + open_total,
        "verified_total": verified_total,
        "open_total": open_total,
        "attention_count": len(attention),
        "unthreaded_count": len([item for item in claims if item["no_thread"]]),
        "no_report_count": len([item for item in claims if item["no_report"]]),
        "queued_count": queued_count,
        "attention": attention[:limit],
        "verified_recent": verified_recent[:limit],
        "recent": claims[:limit],
    }


def load_open_gaps_dashboard(limit=6):
    """Summarize unresolved open gaps from entry frontmatter."""
    gaps = []
    entries_with_gaps = 0
    for entry in _entry_records():
        entry_gaps = entry.get("open_gaps") or []
        if entry_gaps:
            entries_with_gaps += 1
        for position, gap in enumerate(entry_gaps):
            text = str(gap.get("text") if isinstance(gap, dict) else gap).strip()
            if not text:
                continue
            gaps.append({
                "gap_id": _surface_id("gap", f"{entry['filename']}:{position}:{text}"),
                "text": text,
                "entry_title": entry["title"],
                "entry_href": f"/entry/{entry['slug']}",
                "reference": entry["filename"],
                "threads": entry.get("threads") or [],
                "date": entry.get("date"),
            })
    return {
        "open_total": len(gaps),
        "entries_with_gaps": entries_with_gaps,
        "attention_count": len(gaps),
        "attention": gaps[:limit],
        "recent": gaps[:limit],
    }


def load_claim_detail(claim_id):
    """Load a single aggregated claim surface with support and steering history."""
    claim = next((item for item in _claim_records() if item["claim_id"] == claim_id), None)
    if not claim:
        return None

    thread_index = {
        item["id"]: item
        for item in load_threads_enriched().get("threads", [])
    }

    reports = []
    for report in sorted({row.get("report") for row in claim["occurrences"] if row.get("report")}):
        report_path = REPORTS_DIR / report
        reports.append({
            "filename": report,
            "exists": report_path.exists(),
            "url": f"/reports/{report}" if report_path.exists() else None,
        })

    occurrences = []
    for row in claim["occurrences"]:
        occurrences.append({
            "claim_occurrence_id": row["claim_occurrence_id"],
            "artifact_title": row["artifact_title"],
            "artifact_filename": row["artifact_filename"],
            "artifact_href": row["artifact_href"],
            "report": row.get("report"),
            "threads": row.get("threads", []),
            "date": row.get("date"),
            "date_short": _short_ts(row.get("date")),
            "kind": row.get("kind"),
            "kind_color": row.get("kind_color"),
        })

    return {
        **{key: value for key, value in claim.items() if key != "occurrences"},
        "occurrences": occurrences,
        "reports": reports,
        "thread_links": claim.get("thread_links") or [
            {
                "id": tid,
                "title": thread_index.get(tid, {}).get("title", tid),
                "status": thread_index.get(tid, {}).get("status"),
                "href": f"/thread/{tid}",
            }
            for tid in claim.get("threads", [])
        ],
        "operator_actions": _build_claim_operator_action_index(limit_per_claim=12).get(claim_id, []),
        "queued_steering": _build_claim_queued_intent_index(limit_per_claim=12).get(claim_id, []),
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
                topics.append({
                    "id": fp.stem,
                    "name": fp.stem,
                    "title": heading,
                    "reference": fp.name,
                })
            except Exception:
                continue

    thread_data = load_threads_enriched()
    objectives = []
    for thread in thread_data.get("threads", []):
        if thread.get("status") not in {"active", "proposed"}:
            continue
        objectives.append({
            "id": thread["id"],
            "thread_id": thread["id"],
            "title": thread["title"],
            "goal": thread.get("goal") or thread["title"],
            "status": thread.get("status"),
            "next_step": thread.get("next_step"),
            "reference": thread["id"],
            "href": f"/thread/{thread['id']}",
        })

    return {
        "available": STRATEGY_FILE.exists(),
        "strategy_id": "global",
        "strategy_reference": "config/strategy.md",
        "summary": " ".join(summary_lines[:2]).strip(),
        "priorities": priorities[:4],
        "topics": topics[:limit_topics],
        "topics_total": len(topics),
        "objectives": objectives[:limit_objectives],
    }


PROPOSAL_STALE_DAYS = 14


def _build_proposal_operator_action_index(limit_per_proposal=6):
    rollup = {}
    for item in load_operator_actions(limit=200):
        if item.get("target_type") != "proposal":
            continue
        proposal_id = str(item.get("target_id") or "").strip()
        if not proposal_id:
            continue
        bucket = rollup.setdefault(proposal_id, [])
        if len(bucket) < limit_per_proposal:
            bucket.append(item)
    return rollup


def _build_proposal_queued_intent_index(limit_per_proposal=6):
    rollup = {}
    for item in load_queued_steering_intents(limit=200):
        if item.get("target_type") != "proposal":
            continue
        proposal_id = str(item.get("target_id") or "").strip()
        if not proposal_id:
            continue
        bucket = rollup.setdefault(proposal_id, [])
        if len(bucket) < limit_per_proposal:
            bucket.append(item)
    return rollup


def _normalize_claim_text(raw_claim):
    text = raw_claim.get("claim", "") if isinstance(raw_claim, dict) else str(raw_claim)
    return str(text).lstrip("! ").strip()


def _proposal_revisions_count(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(str(value).strip()))
    except Exception:
        return 0


def _proposal_decision_log(limit=8):
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
    return decisions


def _proposal_records():
    proposals_raw = load_json_safe(PROPOSALS_FILE, [])
    if not isinstance(proposals_raw, list):
        proposals_raw = []

    thread_items = {
        item["id"]: item
        for item in load_threads_enriched().get("threads", [])
    }
    thread_lookup = {}
    for thread_id, thread in thread_items.items():
        for key in {thread_id.lower(), str(thread.get("title") or "").strip().lower()}:
            if key:
                thread_lookup[key] = thread_id

    claim_items = []
    claim_by_text = {}
    claim_by_id = {}
    for claim in claim_items:
        claim_by_id[claim["claim_id"]] = claim
        claim_by_text[claim["text"].strip().lower()] = claim

    entry_lookup = {}
    for entry in _entry_records():
        keys = {
            entry["filename"].strip().lower(),
            entry["slug"].strip().lower(),
            str(entry.get("title") or "").strip().lower(),
        }
        for key in keys:
            if key:
                entry_lookup[key] = entry

    operator_index = _build_proposal_operator_action_index(limit_per_proposal=12)
    queued_index = _build_proposal_queued_intent_index(limit_per_proposal=12)
    today = date.today()
    records = []

    for proposal in proposals_raw:
        if not isinstance(proposal, dict):
            continue
        proposal_id = str(proposal.get("id") or "").strip()
        if not proposal_id:
            continue

        title = str(proposal.get("title") or "untitled").strip()
        status = str(proposal.get("status") or "active").strip().lower()
        proposal_type = str(proposal.get("type") or "proposal").strip() or "proposal"
        created = str(proposal.get("created") or "").strip() or None
        updated = str(proposal.get("updated") or created or "").strip() or None
        rationale = str(
            proposal.get("rationale")
            or proposal.get("hypothesis")
            or proposal.get("summary")
            or proposal.get("why")
            or ""
        ).strip() or None
        action_text = str(
            proposal.get("action")
            or proposal.get("scope")
            or proposal.get("next_step")
            or ""
        ).strip() or None
        impact = str(
            proposal.get("impact")
            or proposal.get("expected_value")
            or proposal.get("expected_impact")
            or ""
        ).strip() or None
        risk = str(
            proposal.get("risk")
            or proposal.get("risks")
            or proposal.get("operational_risk")
            or ""
        ).strip() or None
        cost = str(proposal.get("cost") or "").strip() or None
        revisions_count = _proposal_revisions_count(proposal.get("revisions"))

        evidence_items = _normalize_string_list(proposal.get("evidence") or [])
        evidence_links = []
        linked_threads = {}
        linked_claims = {}
        report_files = set()

        explicit_threads = _normalize_string_list(proposal.get("threads") or proposal.get("thread"))
        for raw_thread in explicit_threads:
            thread_id = thread_lookup.get(raw_thread.lower(), raw_thread)
            thread = thread_items.get(thread_id)
            if thread:
                linked_threads[thread_id] = {
                    "id": thread_id,
                    "title": thread.get("title", thread_id),
                    "status": thread.get("status"),
                    "href": f"/thread/{thread_id}",
                }
            else:
                linked_threads[thread_id] = {
                    "id": thread_id,
                    "title": raw_thread,
                    "status": None,
                    "href": f"/thread/{thread_id}",
                }

        explicit_legacy_refs = _normalize_string_list(proposal.get("claims") or proposal.get("claim"))
        for raw_claim in explicit_legacy_refs:
            claim = claim_by_id.get(raw_claim) or claim_by_text.get(raw_claim.lstrip("! ").strip().lower())
            if claim:
                linked_claims[claim["claim_id"]] = {
                    "claim_id": claim["claim_id"],
                    "text": claim["text"],
                    "kind": claim["kind"],
                    "href": "#",
                }

        for evidence in evidence_items:
            key = evidence.strip().lower()
            entry = entry_lookup.get(key)
            claim = claim_by_text.get(evidence.lstrip("! ").strip().lower())

            if entry:
                evidence_links.append({
                    "label": entry["title"],
                    "href": f"/blog/entries/{entry['filename']}",
                    "kind": "artifact",
                })
                if entry.get("report"):
                    report_files.add(entry["report"])
                for thread_id in entry.get("threads", []):
                    thread = thread_items.get(thread_id)
                    linked_threads[thread_id] = {
                        "id": thread_id,
                        "title": thread.get("title", thread_id) if thread else thread_id,
                        "status": thread.get("status") if thread else None,
                        "href": f"/thread/{thread_id}",
                    }
                for raw_claim in entry.get("claims", []):
                    clean_claim = _normalize_claim_text(raw_claim)
                    if not clean_claim:
                        continue
                    matched_claim = claim_by_text.get(clean_claim.lower())
                    if matched_claim:
                        linked_claims[matched_claim["claim_id"]] = {
                            "claim_id": matched_claim["claim_id"],
                            "text": matched_claim["text"],
                            "kind": matched_claim["kind"],
                            "href": "#",
                        }
            elif claim:
                evidence_links.append({
                    "label": claim["text"],
                    "href": "#",
                    "kind": "claim",
                })
                linked_claims[claim["claim_id"]] = {
                    "claim_id": claim["claim_id"],
                    "text": claim["text"],
                    "kind": claim["kind"],
                    "href": "#",
                }
                for thread_id in claim.get("threads", []):
                    thread = thread_items.get(thread_id)
                    linked_threads[thread_id] = {
                        "id": thread_id,
                        "title": thread.get("title", thread_id) if thread else thread_id,
                        "status": thread.get("status") if thread else None,
                        "href": f"/thread/{thread_id}",
                    }
            else:
                evidence_links.append({
                    "label": evidence,
                    "href": None,
                    "kind": "note",
                })

        operator_actions = operator_index.get(proposal_id, [])
        queued_steering = queued_index.get(proposal_id, [])
        recent_operator_action = operator_actions[0] if operator_actions else None
        queued_action = queued_steering[0]["action"] if queued_steering else None
        recent_action = recent_operator_action["display_action"] if recent_operator_action else None

        updated_ts = _parse_ts_value(updated)
        updated_date = updated_ts.date() if updated_ts else _parse_date_value(updated)
        stale_days = (today - updated_date).days if updated_date else None
        stale = stale_days is not None and stale_days >= PROPOSAL_STALE_DAYS
        low_evidence = len(evidence_items) <= 1
        no_links = not linked_threads and not linked_claims
        needs_revision = status in {"needs_revision", "needs-revision", "revision", "revision-requested"} or queued_action == "request-revision" or recent_action == "request-revision"
        approved_waiting = status == "approved" or queued_action == "approve"
        deferred = status in {"deferred", "parked", "on-hold"} or queued_action == "defer"
        decided_recently = status in {"rejected", "rejected_recent", "done"} or queued_action == "reject" or recent_action == "reject"
        needs_decision = status == "active" and not needs_revision and not approved_waiting and not deferred and not decided_recently

        flags = []
        attention_score = 0
        if needs_revision:
            flags.append({"kind": "warn", "label": "needs revision", "detail": "proposal is blocked on a revision request"})
            attention_score += 5
        if low_evidence:
            flags.append({"kind": "warn", "label": "low evidence", "detail": "proposal has one or zero explicit evidence items"})
            attention_score += 3
        if no_links:
            flags.append({"kind": "muted", "label": "unlinked", "detail": "proposal is not linked to any claim or thread"})
            attention_score += 2
        if stale:
            flags.append({"kind": "warn", "label": "stale", "detail": f"{stale_days}d since last update"})
            attention_score += 2
        if approved_waiting:
            flags.append({"kind": "ok", "label": "queued", "detail": "proposal is approved or queued for the next dispatch"})
        if deferred:
            flags.append({"kind": "muted", "label": "deferred", "detail": "proposal is explicitly parked"})

        if needs_revision:
            lane = "needs_revision"
            status_badge = "needs-revision"
            status_label = "needs revision"
        elif approved_waiting:
            lane = "approved_waiting"
            status_badge = "approved"
            status_label = "approved"
        elif deferred:
            lane = "deferred"
            status_badge = "deferred"
            status_label = "deferred"
        elif decided_recently:
            lane = "recently_decided"
            status_badge = "decided"
            status_label = "decided"
        else:
            lane = "needs_decision"
            status_badge = "needs-decision"
            status_label = "needs decision"

        records.append({
            "id": proposal_id,
            "title": title,
            "type": proposal_type,
            "status": status,
            "status_label": status_label,
            "status_badge": status_badge,
            "lane": lane,
            "href": f"/proposal/{proposal_id}",
            "created": created,
            "created_short": _short_ts(created),
            "updated": updated,
            "updated_short": _short_ts(updated),
            "_sort_ts": updated_ts.timestamp() if updated_ts else 0,
            "reference": evidence_items[0] if evidence_items else proposal_id,
            "rationale": rationale,
            "action_text": action_text,
            "impact": impact,
            "risk": risk,
            "cost": cost,
            "revisions_count": revisions_count,
            "evidence_count": len(evidence_items),
            "evidence_preview": evidence_items[:2],
            "evidence_links": evidence_links,
            "linked_threads": list(linked_threads.values())[:6],
            "linked_threads_count": len(linked_threads),
            "linked_claims": list(linked_claims.values())[:6],
            "linked_claims_count": len(linked_claims),
            "reports_count": len(report_files),
            "reports": sorted(report_files),
            "flags": flags,
            "low_evidence": low_evidence,
            "no_links": no_links,
            "stale": stale,
            "stale_days": stale_days,
            "needs_attention": bool(needs_decision or needs_revision or low_evidence or stale or no_links),
            "attention_score": attention_score,
            "needs_decision": needs_decision,
            "needs_revision": needs_revision,
            "approved_waiting": approved_waiting,
            "deferred": deferred,
            "decided_recently": decided_recently,
            "recent_operator_action": recent_operator_action,
            "queued_steering": queued_steering[0] if queued_steering else None,
            "operator_actions": operator_actions[:8],
            "queued_steering_items": queued_steering[:8],
        })

    records.sort(
        key=lambda item: (
            {
                "needs_revision": 0,
                "needs_decision": 1,
                "approved_waiting": 2,
                "deferred": 3,
                "recently_decided": 4,
            }.get(item["lane"], 5),
            -int(item.get("attention_score") or 0),
            -(item.get("_sort_ts") or 0),
            item.get("title") or "",
        ),
        reverse=False,
    )
    for item in records:
        item.pop("_sort_ts", None)
    return records


def load_proposals_dashboard(limit=5):
    """Summarize proposals into a decision console read model."""
    proposals = _proposal_records()
    active = sorted(
        [item for item in proposals if item["status"] == "active"],
        key=lambda item: item.get("updated") or "",
        reverse=True,
    )
    needs_decision = [item for item in proposals if item["lane"] == "needs_decision"]
    needs_revision = [item for item in proposals if item["lane"] == "needs_revision"]
    approved_waiting = [item for item in proposals if item["lane"] == "approved_waiting"]
    deferred = [item for item in proposals if item["lane"] == "deferred"]
    recently_decided = [item for item in proposals if item["lane"] == "recently_decided"]
    return {
        "total": len(proposals),
        "active_count": len(active),
        "queued_count": len([item for item in proposals if item.get("queued_steering")]),
        "low_evidence_count": len([item for item in proposals if item["low_evidence"]]),
        "needs_decision_count": len(needs_decision),
        "needs_revision_count": len(needs_revision),
        "approved_waiting_count": len(approved_waiting),
        "deferred_count": len(deferred),
        "active": active[:limit],
        "needs_decision": needs_decision[:limit],
        "needs_revision": needs_revision[:limit],
        "approved_waiting_execution": approved_waiting[:limit],
        "deferred": deferred[:limit],
        "recently_decided": recently_decided[:limit],
        "decisions": _proposal_decision_log(limit=limit),
    }


def load_proposal_detail(proposal_id):
    """Load a single proposal with linked evidence and steering history."""
    proposal = next((item for item in _proposal_records() if item["id"] == proposal_id), None)
    if not proposal:
        return None

    decision_hits = []
    title_needle = proposal["title"].strip().lower()
    for item in _proposal_decision_log(limit=50):
        if title_needle and title_needle in item.lower():
            decision_hits.append(item)

    return {
        **proposal,
        "decision_log": decision_hits,
    }


def load_lineage_dashboard(limit=6):
    """Build recent claim -> thread -> artifact lineage rows."""
    lineage = []
    for item in _claim_occurrence_records():
        lineage.append({
            "claim_id": item["claim_id"],
            "claim": item["text"],
            "claim_status": item["kind"],
            "claim_color": item["kind_color"],
            "threads": item["threads"],
            "artifact_title": item["artifact_title"],
            "artifact_filename": item["artifact_filename"],
            "artifact_href": item["artifact_href"],
            "report": item["report"],
            "date": item["date"],
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
        "open_gaps_summary": {}, "persistent_gaps": []
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

THREAD_EVIDENCE_STALE_DAYS = 7
THREAD_HISTORY_LIMIT = 8
THREAD_DETAIL_HISTORY_LIMIT = 20
THREAD_NEXT_STEP_PLACEHOLDERS = {
    "[definir]",
    "[define]",
    "definir",
    "todo",
    "tbd",
    "pending",
}


def _normalize_string_list(value):
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        items = [str(part).strip() for part in value]
    else:
        return []
    return [item for item in items if item]


def _extract_section_first_line(raw_body, heading_patterns):
    pattern = r"^##\s+(?:" + "|".join(heading_patterns) + r")\s*$"
    match = re.search(pattern, raw_body, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    after = raw_body[match.end():]
    for line in after.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _extract_thread_summary(raw_body):
    for line in raw_body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("```", "-", "*")):
            continue
        return stripped
    return None


def _parse_date_value(value):
    parsed = _parse_ts_value(value)
    return parsed.date() if parsed else None


def _latest_item(current, candidate):
    if not candidate:
        return current
    if not current:
        return candidate

    candidate_ts = candidate.get("_sort_ts")
    current_ts = current.get("_sort_ts")
    if candidate_ts and current_ts:
        return candidate if candidate_ts > current_ts else current
    if candidate_ts and not current_ts:
        return candidate
    return current


def _build_thread_entry_rollup():
    rollup = {}
    if not ENTRIES_DIR.exists():
        return rollup

    for fp in ENTRIES_DIR.glob("*.md"):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            thread_ids = _normalize_string_list(fm.get("threads", []))
            if not thread_ids:
                continue

            open_gaps = _normalize_string_list(fm.get("open_gaps", []))
            gaps_count = len(open_gaps)
            report_file = str(fm.get("report") or "").strip() or None
            note_file = str(fm.get("note") or "").strip() or None
            entry_date = str(fm.get("date") or "").strip() or None
            entry_sort_ts = _parse_ts_value(entry_date) or _parse_ts_value(fm.get("updated"))
            evidence = {
                "kind": "entry",
                "label": str(fm.get("title") or fp.stem),
                "slug": fp.stem,
                "href": f"/entry/{fp.stem}",
                "ts": entry_date,
                "report": report_file,
                "note": note_file,
                "_sort_ts": entry_sort_ts,
            }

            for thread_id in thread_ids:
                bucket = rollup.setdefault(thread_id, {
                    "entries_count": 0,
                    "open_gaps_count": 0,
                    "gaps_count": 0,
                    "report_files": set(),
                    "last_evidence": None,
                })
                bucket["entries_count"] += 1
                bucket["open_gaps_count"] += gaps_count
                bucket["gaps_count"] += gaps_count
                if report_file:
                    bucket["report_files"].add(report_file)
                bucket["last_evidence"] = _latest_item(bucket["last_evidence"], dict(evidence))
        except Exception:
            continue

    for bucket in rollup.values():
        bucket["reports_count"] = len(bucket.pop("report_files", set()))
        if bucket.get("last_evidence"):
            bucket["last_evidence"]["ts_short"] = _short_ts(bucket["last_evidence"].get("ts"))
            bucket["last_evidence"].pop("_sort_ts", None)
    return rollup


def _normalize_thread_event(row):
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    thread_id = str(row.get("thread_id") or payload.get("thread_id") or "").strip()
    if not thread_id:
        return None

    ts = row.get("timestamp") or row.get("ts")
    event_type = str(row.get("type") or "").strip()
    skill = str(row.get("skill") or payload.get("skill") or "").strip() or None
    cycle_id = str(row.get("cycle_id") or payload.get("cycle_id") or "").strip() or None
    artifacts = row.get("artifacts") or payload.get("artifacts") or payload.get("artifact") or []
    if isinstance(artifacts, str):
        artifacts = [artifacts]
    elif isinstance(artifacts, list):
        artifacts = [str(item).strip() for item in artifacts if str(item).strip()]
    else:
        artifacts = []

    summary = str(row.get("summary") or payload.get("summary") or "").strip()
    normalized_type = re.sub(r"[^a-z0-9]+", "", event_type.lower())
    if not summary:
        if normalized_type == "skilldispatched" and skill:
            summary = f"Dispatched /{skill}"
        elif normalized_type in {"artifactpublished", "artifactcreated"} and artifacts:
            summary = f"Published {artifacts[0]}"
        elif normalized_type == "threadupdated":
            summary = "Thread updated"
        else:
            summary = event_type or "event"

    return {
        "thread_id": thread_id,
        "ts": ts,
        "ts_short": _short_ts(ts),
        "type": event_type,
        "summary": summary,
        "skill": skill,
        "cycle_id": cycle_id,
        "artifacts": artifacts,
        "_sort_ts": _parse_ts_value(ts),
        "_normalized_type": normalized_type,
    }


def _build_thread_event_rollup(limit_history=THREAD_HISTORY_LIMIT):
    rollup = {}
    seen = set()

    for path in (STATE_EVENTS_FILE, EVENTS_FILE):
        for row in _iter_jsonl(path):
            event = _normalize_thread_event(row)
            if not event:
                continue
            dedupe_key = (
                event["thread_id"],
                event.get("ts"),
                event.get("_normalized_type"),
                event.get("summary"),
                event.get("skill"),
                tuple(event.get("artifacts") or []),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rollup.setdefault(event["thread_id"], {"history": []})["history"].append(event)

    min_ts = datetime.min.replace(tzinfo=timezone.utc)
    for bucket in rollup.values():
        bucket["history"].sort(key=lambda item: item.get("_sort_ts") or min_ts, reverse=True)
        bucket["history"] = bucket["history"][:limit_history]
        for item in bucket["history"]:
            item.pop("_sort_ts", None)
            item.pop("_normalized_type", None)
        bucket["last_event"] = bucket["history"][0] if bucket["history"] else None
        bucket["last_dispatch"] = next(
            (
                item for item in bucket["history"]
                if item.get("skill") or re.sub(r"[^a-z0-9]+", "", str(item.get("type") or "").lower()) == "skilldispatched"
            ),
            None,
        )
    return rollup


def _build_thread_operator_action_index(limit_per_thread=6):
    rollup = {}
    for item in load_operator_actions(limit=200):
        action = str(item.get("action") or "").strip()
        thread_id = str(item.get("target_id") or "").strip()
        if not thread_id or not action.startswith("thread:"):
            continue
        bucket = rollup.setdefault(thread_id, [])
        if len(bucket) < limit_per_thread:
            bucket.append(item)
    return rollup


def _parse_next_step(raw_body):
    """Extract first non-empty line after a next-step heading."""
    return _extract_section_first_line(
        raw_body,
        [
            r"Próximo passo",
            r"Next",
            r"Next step",
            r"Refined next step",
        ],
    )


def load_threads_enriched(status_filter=None):
    """Load threads with operational metadata for dashboard triage."""
    if not THREADS_DIR.exists():
        return {
            "threads": [],
            "stats": {
                "total": 0,
                "active": 0,
                "waiting": 0,
                "dormant": 0,
                "done": 0,
                "proposed": 0,
                "resurface_due": 0,
            },
        }

    entry_rollup = _build_thread_entry_rollup()
    event_rollup = _build_thread_event_rollup()
    operator_rollup = _build_thread_operator_action_index()
    today = date.today()
    threads = []
    stats = {"total": 0, "active": 0, "waiting": 0, "dormant": 0, "done": 0, "proposed": 0, "resurface_due": 0}

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
            body = parts[2]
            next_step = _parse_next_step(body)
            thread_summary = fm.get("goal") or _extract_thread_summary(body)
            entry_data = entry_rollup.get(thread_id) or entry_rollup.get(fp.stem, {})
            event_data = event_rollup.get(thread_id) or event_rollup.get(fp.stem, {})
            operator_actions = operator_rollup.get(thread_id) or operator_rollup.get(fp.stem, [])
            waiting_reason = next(
                (
                    item.get("reason")
                    for item in operator_actions
                    if item.get("action") == "thread:waiting" and item.get("reason")
                ),
                None,
            )

            # Resurface check
            resurface_str = fm.get("resurface")
            resurface_due = False
            resurface_days_overdue = None
            if resurface_str:
                try:
                    rd = date.fromisoformat(str(resurface_str))
                    resurface_due = rd <= today
                    if rd <= today:
                        resurface_days_overdue = max(0, (today - rd).days)
                except (ValueError, TypeError):
                    pass

            next_step_normalized = (next_step or "").strip().lower()
            no_next_step = status in {"active", "waiting"} and (
                not next_step or next_step_normalized in THREAD_NEXT_STEP_PLACEHOLDERS
            )
            last_evidence = entry_data.get("last_evidence")
            last_dispatch = event_data.get("last_dispatch")
            last_dispatch_ts = _parse_ts_value(last_dispatch.get("ts")) if last_dispatch else None
            last_evidence_ts = _parse_ts_value(last_evidence.get("ts")) if last_evidence else None
            last_touched_candidates = [
                _parse_ts_value(fm.get("updated")),
                last_evidence_ts,
                last_dispatch_ts,
                _parse_ts_value(operator_actions[0].get("ts")) if operator_actions else None,
            ]
            last_touched_candidates = [item for item in last_touched_candidates if item]
            last_touched = max(last_touched_candidates) if last_touched_candidates else None

            no_recent_evidence = False
            days_since_evidence = None
            if status in {"active", "waiting"}:
                reference_ts = last_evidence_ts or last_dispatch_ts
                if reference_ts is None:
                    no_recent_evidence = True
                else:
                    days_since_evidence = max(0, (today - reference_ts.date()).days)
                    no_recent_evidence = days_since_evidence >= THREAD_EVIDENCE_STALE_DAYS

            closure_ready = (
                status in {"active", "waiting"}
                and bool(fm.get("done_when"))
                and entry_data.get("reports_count", 0) > 0
                and entry_data.get("gaps_count", 0) == 0
                and not no_next_step
            )

            flags = []
            attention_reasons = []
            if resurface_due and status in {"active", "waiting"}:
                label = "resurface due"
                detail = f"{resurface_days_overdue}d overdue" if resurface_days_overdue else "due today"
                flags.append({"kind": "warn", "label": label, "detail": detail})
                attention_reasons.append(label)
            if status == "waiting":
                flags.append({"kind": "warn", "label": "waiting", "detail": waiting_reason or "awaiting follow-up"})
            if no_next_step:
                flags.append({"kind": "warn", "label": "no next step", "detail": "operator cannot tell what advances this thread"})
                attention_reasons.append("no next step")
            if no_recent_evidence:
                detail = "no linked evidence yet" if days_since_evidence is None else f"{days_since_evidence}d since last evidence"
                flags.append({"kind": "warn", "label": "no recent evidence", "detail": detail})
                attention_reasons.append("no recent evidence")
            if entry_data.get("gaps_count", 0) > 0:
                flags.append({"kind": "muted", "label": f"{entry_data.get('gaps_count', 0)} open gaps", "detail": "claims still unresolved"})
            if closure_ready:
                flags.append({"kind": "ok", "label": "closure-ready", "detail": "done_when has support with no open gaps"})

            attention_score = 0
            if resurface_due:
                attention_score += 5 + min(resurface_days_overdue or 0, 3)
            if no_next_step:
                attention_score += 4
            if no_recent_evidence:
                attention_score += 3

            stats["total"] += 1
            if status in stats:
                stats[status] += 1
            if resurface_due and status in {"active", "waiting"}:
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
                "summary": thread_summary,
                "done_when": fm.get("done_when"),
                "entries_count": entry_data.get("entries_count", 0),
                "reports_count": entry_data.get("reports_count", 0),
                "claims_count": entry_data.get("claims_count", 0),
                "verified_count": entry_data.get("verified_count", 0),
                "gaps_count": entry_data.get("gaps_count", 0),
                "resurface_due": resurface_due,
                "resurface_days_overdue": resurface_days_overdue,
                "next_step": next_step,
                "no_next_step": no_next_step,
                "no_recent_evidence": no_recent_evidence,
                "days_since_evidence": days_since_evidence,
                "closure_ready": closure_ready,
                "waiting_reason": waiting_reason,
                "flags": flags,
                "attention_reasons": attention_reasons,
                "attention_summary": ", ".join(attention_reasons[:2]) if attention_reasons else None,
                "attention_score": attention_score,
                "needs_attention": status in {"active", "waiting"} and attention_score > 0,
                "last_evidence": last_evidence,
                "last_event": event_data.get("last_event"),
                "last_dispatch": last_dispatch,
                "last_skill": last_dispatch.get("skill") if last_dispatch else None,
                "last_cycle_id": last_dispatch.get("cycle_id") if last_dispatch else None,
                "recent_operator_action": operator_actions[0] if operator_actions else None,
                "last_touched": last_touched.isoformat() if last_touched else None,
                "last_touched_short": _short_ts(last_touched.isoformat()) if last_touched else None,
            })
        except Exception:
            continue

    if status_filter:
        threads = [t for t in threads if t["status"] == status_filter]

    threads.sort(
        key=lambda item: (
            item.get("status") == "done",
            item.get("status") == "dormant",
            item.get("status") == "proposed",
            item.get("status") != "waiting" and not item.get("needs_attention"),
            -(item.get("attention_score") or 0),
            item.get("resurface") or "",
            item.get("updated") or "",
        )
    )
    return {"threads": threads, "stats": stats}


def load_thread_detail(thread_id):
    """Load full detail for a single thread with evidence and operator history."""
    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return None

    enriched_map = {item["id"]: item for item in load_threads_enriched().get("threads", [])}
    enriched = enriched_map.get(thread_id, {})
    event_history = (
        _build_thread_event_rollup(limit_history=THREAD_DETAIL_HISTORY_LIMIT)
        .get(thread_id, {})
        .get("history", [])
    )
    operator_actions = _build_thread_operator_action_index(limit_per_thread=12).get(thread_id, [])

    raw = thread_path.read_text(encoding="utf-8", errors="replace")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    body_md = parts[2].strip()
    body_html = markdown.markdown(body_md, extensions=["tables", "fenced_code"])

    # Collect all entries linked to this thread
    entries = []
    all_gaps = []
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
                entry_gaps = efm.get("open_gaps", [])
                if isinstance(entry_gaps, str):
                    entry_gaps = [entry_gaps]
                if not isinstance(entry_gaps, list):
                    entry_gaps = []
                report_file = efm.get("report", "")
                note_file = efm.get("note", "")
                if report_file:
                    reports_set.add(report_file)
                entries.append({
                    "slug": fp.stem,
                    "title": efm.get("title", fp.stem),
                    "date": str(efm.get("date", "")),
                    "tags": efm.get("tags", []),
                    "open_gaps": entry_gaps,
                    "report": report_file,
                    "note": note_file,
                })
                all_gaps.extend(entry_gaps)
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
        "summary": enriched.get("summary"),
        "flags": enriched.get("flags", []),
        "attention_summary": enriched.get("attention_summary"),
        "next_step": enriched.get("next_step"),
        "waiting_reason": enriched.get("waiting_reason"),
        "last_evidence": enriched.get("last_evidence"),
        "last_dispatch": enriched.get("last_dispatch"),
        "last_skill": enriched.get("last_skill"),
        "last_cycle_id": enriched.get("last_cycle_id"),
        "recent_operator_action": enriched.get("recent_operator_action"),
        "body_html": body_html,
        "entries": entries,
        "entries_count": len(entries),
        "reports": reports,
        "open_gaps": all_gaps,
        "claims": [],
        "claims_verified": [],
        "claims_gaps": all_gaps,
        "claims_count": 0,
        "verified_count": 0,
        "gaps_count": len(all_gaps),
        "event_history": event_history,
        "operator_actions": operator_actions,
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
