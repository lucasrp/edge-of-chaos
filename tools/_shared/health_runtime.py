"""Health runtime — event-backed health v2 dimensions and cycle observations."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    CAPABILITIES_STATUS_FILE,
    HEALTH_CURRENT_FILE,
    HEALTH_DIR,
    OPEN_GAPS_DIGEST_FILE,
    PRIMITIVES_STATUS_FILE,
    STATE_EVENTS_FILE,
    THREADS_DIR,
)
from .capability_runtime import build_capability_status  # noqa: E402
from .jsonl_runtime import iter_jsonl_reverse  # noqa: E402
from .telemetry import emit_shadow_event  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _iter_events(*paths: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(_read_jsonl(path))
    return rows


def _status_from_score(score: int, *, hard_fail: bool = False) -> str:
    if hard_fail:
        return "critical"
    if score < 40:
        return "critical"
    if score < 70:
        return "unhealthy"
    if score < 85:
        return "degraded"
    return "healthy"


def _dimension_status(score: int, *, hard_fail: bool = False) -> str:
    if hard_fail or score < 25:
        return "fail"
    if score < 60:
        return "degraded"
    return "ok"


def _component_score(status: str | None) -> int | None:
    mapping = {
        "ok": 100,
        "healthy": 100,
        "degraded": 60,
        "warning": 60,
        "fail": 0,
        "critical": 0,
        "unknown": None,
    }
    return mapping.get(str(status or "").strip().lower(), None)


def _weighted_score(weights: dict[str, int], values: dict[str, str]) -> int:
    total = 0
    max_total = 0
    for key, weight in weights.items():
        score = _component_score(values.get(key))
        if score is None:
            continue
        total += int(score * weight / 100)
        max_total += weight
    if max_total <= 0:
        return 100
    return max(0, min(100, round(total * 100 / max_total)))


def _load_raw_components(health_dir: Path = HEALTH_DIR) -> dict[str, dict[str, Any]]:
    raw_dir = health_dir / "raw"
    payload: dict[str, dict[str, Any]] = {}
    if not raw_dir.exists():
        return payload
    for path in sorted(raw_dir.glob("*.json")):
        data = _read_json(path, {})
        if isinstance(data, dict):
            payload[path.stem] = data
    return payload


def _infra_dimension(raw: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    weights = {
        "disk": 10,
        "fs_rw": 15,
        "sqlite": 15,
        "blog": 10,
        "index": 5,
        "consolidate": 5,
        "git": 5,
        "heartbeat": 15,
        "mini_repos": 5,
        "primitives": 15,
    }
    values = {name: str((raw.get(name) or {}).get("status") or "unknown") for name in weights}
    score = _weighted_score(weights, values)
    hard_fail = any(str((raw.get(name) or {}).get("status")) == "critical" for name in {"disk", "fs_rw", "sqlite"})
    detail_parts = [
        f"{name}={values[name]}"
        for name in ["disk", "fs_rw", "sqlite", "blog", "heartbeat", "primitives"]
        if values.get(name) != "unknown"
    ]
    return (
        {
            "status": _dimension_status(score, hard_fail=hard_fail),
            "score": score,
            "detail": " ".join(detail_parts) if detail_parts else "no infra data",
            "components": {
                name: {
                    "status": str((raw.get(name) or {}).get("status") or "unknown"),
                    "detail": str((raw.get(name) or {}).get("detail") or ""),
                }
                for name in weights
            },
        },
        hard_fail,
    )


def _cycle_window(events: list[dict[str, Any]], *, days: int = 7) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(days=days)
    return [row for row in events if (_parse_ts(row.get("ts") or row.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]


def _runtime_flow_dimension(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _cycle_window(events, days=7)
    counts = Counter(row.get("type") for row in rows)
    cycles_started = counts.get("CycleStarted", 0)
    cycles_closed = counts.get("CycleClosed", 0)
    dispatched = counts.get("SkillDispatched", 0)
    skill_runs = counts.get("SkillRunCompleted", 0)
    preflight_completed = counts.get("PreflightCompleted", 0)
    preflight_failed = counts.get("PreflightFailed", 0)
    postflight_completed = counts.get("PostflightCompleted", 0)
    postflight_failed = counts.get("PostflightFailed", 0)
    timeouts = counts.get("HeartbeatDispatchTimedOut", 0)

    completion_rate = cycles_closed / cycles_started if cycles_started else 1.0
    dispatch_rate = dispatched / cycles_started if cycles_started else 1.0
    preflight_success_rate = preflight_completed / max(preflight_completed + preflight_failed, 1)
    postflight_success_rate = postflight_completed / max(postflight_completed + postflight_failed, 1)
    timeout_penalty = min(timeouts / max(cycles_started, 1), 1.0) if cycles_started else 0.0
    if cycles_started == 0 and cycles_closed == 0 and dispatched == 0 and postflight_completed == 0 and postflight_failed == 0:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no recent cycle evidence",
            "metrics": {
                "window_days": 7,
                "cycles_started": 0,
                "cycles_closed": 0,
                "skill_dispatched": 0,
                "skill_runs_completed": 0,
                "preflight_completed": preflight_completed,
                "preflight_failed": preflight_failed,
                "postflight_completed": 0,
                "postflight_failed": 0,
                "heartbeat_dispatch_timeouts": timeouts,
                "completion_rate": 0.0,
                "dispatch_rate": 0.0,
                "preflight_success_rate": round(preflight_success_rate, 3),
                "postflight_success_rate": 0.0,
            },
        }

    score = round(
        completion_rate * 35
        + dispatch_rate * 20
        + preflight_success_rate * 15
        + postflight_success_rate * 20
        + (1.0 - timeout_penalty) * 10
    )
    score = max(0, min(100, score))
    return {
        "status": _dimension_status(score),
        "score": score,
        "detail": (
            f"started={cycles_started} closed={cycles_closed} dispatched={dispatched} "
            f"skill_runs={skill_runs} postflight_fail={postflight_failed} timeouts={timeouts}"
        ),
        "metrics": {
            "window_days": 7,
            "cycles_started": cycles_started,
            "cycles_closed": cycles_closed,
            "skill_dispatched": dispatched,
            "skill_runs_completed": skill_runs,
            "preflight_completed": preflight_completed,
            "preflight_failed": preflight_failed,
            "postflight_completed": postflight_completed,
            "postflight_failed": postflight_failed,
            "heartbeat_dispatch_timeouts": timeouts,
            "completion_rate": round(completion_rate, 3),
            "dispatch_rate": round(dispatch_rate, 3),
            "preflight_success_rate": round(preflight_success_rate, 3),
            "postflight_success_rate": round(postflight_success_rate, 3),
        },
    }


def _active_threads() -> tuple[int, int]:
    active = 0
    due = 0
    today = _now().date().isoformat()
    for path in THREADS_DIR.glob("*.md"):
        fm = _read_frontmatter(path)
        status = str(fm.get("status") or "").strip().lower()
        if status not in {"active", "waiting"}:
            continue
        active += 1
        resurface = str(fm.get("resurface") or "").strip()
        if resurface and resurface <= today:
            due += 1
    return active, due


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _thread_touch_counts(events: list[dict[str, Any]], *, days: int = 7) -> tuple[int, list[str]]:
    cutoff = _now() - timedelta(days=days)
    touched: set[str] = set()
    for row in events:
        if row.get("type") != "ThreadTouched":
            continue
        dt = _parse_ts(row.get("ts"))
        if not dt or dt < cutoff:
            continue
        payload = row.get("payload") or {}
        thread_id = str(payload.get("thread_id") or "").strip()
        if thread_id:
            touched.add(thread_id)
    return len(touched), sorted(touched)


def _continuity_dimension(events: list[dict[str, Any]], open_gaps_digest: dict[str, Any]) -> dict[str, Any]:
    active_threads, due_threads = _active_threads()
    touched_7d, touched_threads = _thread_touch_counts(events, days=7)
    renewal_rate = touched_7d / active_threads if active_threads else 1.0
    open_total = int(open_gaps_digest.get("open_total", 0) or 0)
    entries_with_gaps = int(open_gaps_digest.get("entries_with_gaps", 0) or 0)
    hot_threads = open_gaps_digest.get("hot_threads_by_open_gaps") or []
    gaps = open_gaps_digest.get("gaps") or []
    cutoff = _now() - timedelta(days=30)
    stale_total = 0
    thread_refs = 0
    if isinstance(gaps, list):
        for item in gaps:
            if not isinstance(item, dict):
                continue
            dt = _parse_ts(item.get("date"))
            if dt and dt < cutoff:
                stale_total += 1
            thread_refs += len(item.get("threads") or [])
    fanout_ratio = thread_refs / open_total if open_total else 0.0
    if active_threads == 0 and open_total == 0 and stale_total == 0:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no continuity evidence yet",
            "metrics": {
                "active_threads": 0,
                "touched_threads_7d": touched_7d,
                "touched_thread_ids_7d": [],
                "renewal_rate_7d": 0.0,
                "due_threads": 0,
                "open_gaps": 0,
                "entries_with_gaps": 0,
                "stale_open_gaps": 0,
                "hot_threads_with_gaps": 0,
                "fanout_ratio_30d": 0.0,
            },
        }

    score = 100
    if fanout_ratio > 2.0:
        score -= 25
    elif fanout_ratio > 1.2:
        score -= 10
    if stale_total > 10:
        score -= 20
    elif stale_total > 3:
        score -= 10
    if active_threads and renewal_rate < 0.3:
        score -= 20
    elif active_threads and renewal_rate < 0.6:
        score -= 10
    if due_threads > 3:
        score -= 15
    elif due_threads > 0:
        score -= 5
    score = max(0, min(100, score))

    return {
        "status": _dimension_status(score),
        "score": score,
        "detail": (
            f"open_gaps={open_total} entries_with_gaps={entries_with_gaps} stale={stale_total} "
            f"threads_active={active_threads} touched_7d={touched_7d} due={due_threads}"
        ),
        "metrics": {
            "active_threads": active_threads,
            "touched_threads_7d": touched_7d,
            "touched_thread_ids_7d": touched_threads[:10],
            "renewal_rate_7d": round(renewal_rate, 3),
            "due_threads": due_threads,
            "open_gaps": open_total,
            "entries_with_gaps": entries_with_gaps,
            "stale_open_gaps": stale_total,
            "hot_threads_with_gaps": len(hot_threads),
            "fanout_ratio_30d": round(fanout_ratio, 2),
        },
    }


def _capability_events(events: list[dict[str, Any]], *, days: int = 30) -> tuple[Counter[str], Counter[str], Counter[str], Counter[str]]:
    cutoff = _now() - timedelta(days=days)
    capability_invokes = Counter()
    capability_invoke_fail = Counter()
    capability_probe_fail = Counter()
    primitive_probe_fail = Counter()
    for row in events:
        dt = _parse_ts(row.get("ts"))
        if not dt or dt < cutoff:
            continue
        etype = row.get("type")
        payload = row.get("payload") or {}
        if etype == "CapabilityInvocationObserved":
            name = str(payload.get("capability") or "").strip()
            if name:
                capability_invokes[name] += 1
                if not payload.get("ok", False):
                    capability_invoke_fail[name] += 1
        elif etype == "CapabilityProbeCompleted":
            name = str(payload.get("capability") or "").strip()
            if name and not payload.get("ok", False):
                capability_probe_fail[name] += 1
        elif etype == "PrimitiveProbeCompleted":
            source = str(payload.get("source") or "").strip()
            if source and not payload.get("ok", False):
                primitive_probe_fail[source] += 1
    return capability_invokes, capability_invoke_fail, capability_probe_fail, primitive_probe_fail


def _capabilities_dimension(events: list[dict[str, Any]], capabilities_status: dict[str, Any], primitives_status: dict[str, Any]) -> dict[str, Any]:
    cap_summary = capabilities_status.get("summary") or {}
    cap_rows = capabilities_status.get("capabilities") or []
    primitive_summary = primitives_status.get("summary") or {}
    sources = primitives_status.get("sources") or []
    capability_invokes, capability_invoke_fail, capability_probe_fail, primitive_probe_fail = _capability_events(events)

    available = int(cap_summary.get("available_total", 0) or 0)
    degraded = int(cap_summary.get("degraded_total", 0) or 0)
    # Exclude suspended primitives from broken/degraded counts — suspended is
    # an intentional operator decision, not an operational failure.
    suspended_names = {
        str(s.get("name"))
        for s in sources
        if str(s.get("manifest_status", "")).lower() == "suspended"
    }
    broken = sum(
        1
        for row in cap_rows
        if str(row.get("effective_status")) == "broken"
        and str(row.get("manifest_status", "")).lower() != "suspended"
        and str(row.get("primitive_name") or row.get("name", "")) not in suspended_names
    )
    primitive_broken = sum(
        1
        for s in sources
        if str(s.get("effective_status")) == "broken"
        and str(s.get("manifest_status", "")).lower() != "suspended"
    )
    primitive_degraded = sum(
        1
        for s in sources
        if str(s.get("effective_status")) == "degraded"
        and str(s.get("manifest_status", "")).lower() != "suspended"
    )
    never_used_available = sum(
        1
        for row in cap_rows
        if str(row.get("effective_status")) in {"available", "active", "probed"} and int(row.get("invoke_30d", 0) or 0) == 0
    )
    primitive_never_used = sum(
        1
        for row in sources
        if str(row.get("effective_status")) in {"active", "probed"} and int(row.get("usage_30d", 0) or 0) == 0
    )
    total_invocations = sum(capability_invokes.values())
    total_invoke_fail = sum(capability_invoke_fail.values())
    invoke_fail_rate = total_invoke_fail / total_invocations if total_invocations else 0.0
    if available == 0 and degraded == 0 and broken == 0 and primitive_broken == 0 and primitive_degraded == 0 and total_invocations == 0:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no capability evidence yet",
            "metrics": {
                "available_capabilities": 0,
                "degraded_capabilities": 0,
                "broken_capabilities": 0,
                "degraded_primitives": 0,
                "broken_primitives": 0,
                "never_used_available_capabilities": 0,
                "never_used_primitives": 0,
                "capability_invocations_30d": 0,
                "capability_invoke_fail_30d": 0,
                "capability_invoke_fail_rate_30d": 0.0,
                "capability_probe_fail_30d": 0,
                "primitive_probe_fail_30d": 0,
            },
        }

    score = 100
    score -= min(broken * 15, 40)
    score -= min(degraded * 8, 20)
    score -= min(primitive_broken * 15, 30)
    score -= min(primitive_degraded * 8, 20)
    if available > 0:
        score -= min(round((never_used_available / max(available, 1)) * 20), 20)
    if total_invocations:
        score -= min(round(invoke_fail_rate * 30), 30)
    score = max(0, min(100, score))
    status = _dimension_status(score)
    if broken or primitive_broken:
        status = "fail"
    elif status == "ok" and (degraded or primitive_degraded):
        status = "degraded"

    return {
        "status": status,
        "score": score,
        "detail": (
            f"available={available} degraded={degraded} broken={broken} "
            f"primitive_broken={primitive_broken} primitive_degraded={primitive_degraded}"
        ),
        "metrics": {
            "available_capabilities": available,
            "degraded_capabilities": degraded,
            "broken_capabilities": broken,
            "degraded_primitives": primitive_degraded,
            "broken_primitives": primitive_broken,
            "never_used_available_capabilities": never_used_available,
            "never_used_primitives": primitive_never_used,
            "capability_invocations_30d": total_invocations,
            "capability_invoke_fail_30d": total_invoke_fail,
            "capability_invoke_fail_rate_30d": round(invoke_fail_rate, 3),
            "capability_probe_fail_30d": sum(capability_probe_fail.values()),
            "primitive_probe_fail_30d": sum(primitive_probe_fail.values()),
        },
    }


def _renewal_dimension(events: list[dict[str, Any]], open_gaps_digest: dict[str, Any]) -> dict[str, Any]:
    rows = _cycle_window(events, days=30)
    counts = Counter(row.get("type") for row in rows)
    threads_touched_30d, _ = _thread_touch_counts(events, days=30)
    active_threads, _ = _active_threads()
    cluster_touch_rate = threads_touched_30d / active_threads if active_threads else 1.0
    open_total = int(open_gaps_digest.get("open_total", 0) or 0)
    gaps = open_gaps_digest.get("gaps") or []
    thread_refs = sum(len(item.get("threads") or []) for item in gaps if isinstance(item, dict))
    fanout_ratio = thread_refs / open_total if open_total else 0.0
    observed_30d = counts.get("OpenGapObserved", 0)
    primitive_updates = counts.get("PrimitiveManifestUpdated", 0) + counts.get("PrimitiveMaterialized", 0)
    primitive_probes = counts.get("PrimitiveProbeCompleted", 0)
    if active_threads == 0 and threads_touched_30d == 0 and open_total == 0 and observed_30d == 0 and primitive_updates == 0 and primitive_probes == 0:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no renewal evidence yet",
            "metrics": {
                "cluster_touch_rate_30d": 0.0,
                "threads_touched_30d": 0,
                "active_clusters": 0,
                "open_gaps": 0,
                "observed_open_gaps_30d": 0,
                "fanout_ratio_30d": round(fanout_ratio, 2),
                "primitive_updates_30d": 0,
                "primitive_probes_30d": 0,
            },
        }

    score = 100
    if cluster_touch_rate < 0.3 and active_threads:
        score -= 20
    elif cluster_touch_rate < 0.6 and active_threads:
        score -= 10
    if fanout_ratio > 2.0:
        score -= 20
    elif fanout_ratio > 1.2:
        score -= 10
    if primitive_updates == 0 and primitive_probes == 0:
        score -= 10
    if open_total > 50:
        score -= 20
    elif open_total > 20:
        score -= 10
    score = max(0, min(100, score))

    return {
        "status": _dimension_status(score),
        "score": score,
        "detail": (
            f"clusters_touched_30d={threads_touched_30d} active_clusters={active_threads} "
            f"open_gaps={open_total} observed_30d={observed_30d} primitive_updates_30d={primitive_updates}"
        ),
        "metrics": {
            "cluster_touch_rate_30d": round(cluster_touch_rate, 3),
            "threads_touched_30d": threads_touched_30d,
            "active_clusters": active_threads,
            "open_gaps": open_total,
            "observed_open_gaps_30d": observed_30d,
            "fanout_ratio_30d": round(fanout_ratio, 2),
            "primitive_updates_30d": primitive_updates,
            "primitive_probes_30d": primitive_probes,
        },
    }


def _substrate_discipline_dimension(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _cycle_window(events, days=30)
    counts = Counter(row.get("type") for row in rows)
    primitive_bypass = counts.get("PrimitiveBypassObserved", 0)
    secret_bypass = counts.get("SecretBypassObserved", 0)
    api_bypass = counts.get("ApiBypassObserved", 0)
    cli_bypass = counts.get("CliBypassObserved", 0)
    if primitive_bypass == 0 and secret_bypass == 0 and api_bypass == 0 and cli_bypass == 0:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no substrate-discipline evidence yet",
            "metrics": {
                "primitive_bypass_30d": 0,
                "secret_bypass_30d": 0,
                "api_bypass_30d": 0,
                "cli_bypass_30d": 0,
            },
        }
    score = 100 - min(primitive_bypass * 8, 40) - min(secret_bypass * 20, 40) - min(api_bypass * 10, 30) - min(cli_bypass * 10, 30)
    score = max(0, min(100, score))
    return {
        "status": _dimension_status(score),
        "score": score,
        "detail": (
            f"primitive_bypass_30d={primitive_bypass} secret_bypass_30d={secret_bypass} "
            f"api_bypass_30d={api_bypass} cli_bypass_30d={cli_bypass}"
        ),
        "metrics": {
            "primitive_bypass_30d": primitive_bypass,
            "secret_bypass_30d": secret_bypass,
            "api_bypass_30d": api_bypass,
            "cli_bypass_30d": cli_bypass,
        },
    }


def _api_runtime_dimension(raw: dict[str, dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    provider_rows = _cycle_window(events, days=7)
    provider_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in provider_rows:
        if row.get("type") != "ProviderProbeCompleted":
            continue
        payload = row.get("payload") or {}
        provider = str(payload.get("provider") or "unknown")
        provider_counts[provider]["total"] += 1
        if payload.get("ok", False):
            provider_counts[provider]["ok"] += 1
        else:
            provider_counts[provider]["fail"] += 1

    exa_status = "unknown"
    openai_status = "unknown"
    quality_detail = str((raw.get("quality") or {}).get("detail") or "")
    for token in quality_detail.split():
        if token.startswith("exa="):
            exa_status = token.split("=", 1)[1]
        elif token.startswith("openai="):
            openai_status = token.split("=", 1)[1]
    if exa_status == "unknown" and openai_status == "unknown" and not provider_counts:
        return {
            "status": "unknown",
            "score": 50,
            "detail": "no provider probe evidence yet",
            "metrics": {
                "provider_probe_window_days": 7,
                "providers": {},
            },
        }

    statuses = {"exa": exa_status, "openai": openai_status}
    weights = {"exa": 50, "openai": 50}
    score = _weighted_score(weights, statuses)
    return {
        "status": _dimension_status(score),
        "score": score,
        "detail": f"exa={exa_status} openai={openai_status}",
        "metrics": {
            "provider_probe_window_days": 7,
            "providers": {
                provider: {
                    "total": counts.get("total", 0),
                    "ok": counts.get("ok", 0),
                    "fail": counts.get("fail", 0),
                }
                for provider, counts in sorted(provider_counts.items())
            },
        },
    }


def _legacy_sections(raw: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    infra = {}
    for comp in ["disk", "fs_rw", "sqlite", "blog", "index", "consolidate", "git", "heartbeat", "mini_repos", "primitives"]:
        if comp in raw:
            infra[comp] = {
                "status": raw[comp].get("status", "unknown"),
                "detail": raw[comp].get("detail", ""),
            }
    content = {"status": "unknown", "detail": ""}
    if "content" in raw:
        content = {"status": raw["content"].get("status", "unknown"), "detail": raw["content"].get("detail", "")}
    quality = {"status": "unknown", "detail": ""}
    if "quality" in raw:
        quality = {"status": raw["quality"].get("status", "unknown"), "detail": raw["quality"].get("detail", "")}
    return infra, content, quality


def _remediation_queue(dimensions: dict[str, dict[str, Any]], raw: dict[str, dict[str, Any]], *, health_dir: Path = HEALTH_DIR) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if dimensions["runtime_flow"]["status"] != "ok":
        queue.append({"domain": "runtime_flow", "priority": 1, "action": "inspect dispatch lifecycle stalls/timeouts", "detail": dimensions["runtime_flow"]["detail"]})
    if dimensions["continuity"]["status"] != "ok":
        queue.append({"domain": "continuity", "priority": 2, "action": "recycle overdue threads and close or route open gaps", "detail": dimensions["continuity"]["detail"]})
    if dimensions["capabilities"]["status"] != "ok":
        queue.append({"domain": "capabilities", "priority": 2, "action": "repair broken capabilities/primitives and improve adoption", "detail": dimensions["capabilities"]["detail"]})
    if dimensions["substrate_discipline"]["status"] != "ok":
        queue.append({"domain": "substrate_discipline", "priority": 2, "action": "reduce raw primitive/capability bypasses", "detail": dimensions["substrate_discipline"]["detail"]})
    if dimensions["api_runtime"]["status"] != "ok":
        queue.append({"domain": "api_runtime", "priority": 2, "action": "repair provider credentials or upstream API access", "detail": dimensions["api_runtime"]["detail"]})
    if str((raw.get("disk") or {}).get("status")) == "critical":
        queue.insert(0, {"domain": "infra", "priority": 0, "action": "free disk space immediately", "detail": str((raw.get("disk") or {}).get("detail") or "")})
    raw_dir = health_dir / "raw"
    for name in ("content-remediation.json", "quality-remediation.json"):
        path = raw_dir / name
        data = _read_json(path, [])
        if isinstance(data, list):
            queue.extend(item for item in data if isinstance(item, dict))
    return sorted(queue, key=lambda item: (item.get("priority", 99), item.get("domain", "")))


def build_health_snapshot() -> dict[str, Any]:
    raw = _load_raw_components()
    events = _iter_events(STATE_EVENTS_FILE)
    infra, hard_fail = _infra_dimension(raw)
    open_gaps_digest = _read_json(OPEN_GAPS_DIGEST_FILE, {})
    capabilities_status = _read_json(CAPABILITIES_STATUS_FILE, {})
    if not isinstance(capabilities_status, dict) or "summary" not in capabilities_status:
        capabilities_status = build_capability_status()
    primitives_status = _read_json(PRIMITIVES_STATUS_FILE, {})

    dimensions = {
        "infra": infra,
        "runtime_flow": _runtime_flow_dimension(events),
        "continuity": _continuity_dimension(events, open_gaps_digest),
        "capabilities": _capabilities_dimension(events, capabilities_status, primitives_status),
        "renewal": _renewal_dimension(events, open_gaps_digest),
        "substrate_discipline": _substrate_discipline_dimension(events),
        "api_runtime": _api_runtime_dimension(raw, events),
    }

    weights = {
        "infra": 15,
        "runtime_flow": 20,
        "continuity": 18,
        "capabilities": 20,
        "renewal": 12,
        "substrate_discipline": 5,
        "api_runtime": 5,
    }
    total = sum(dim["score"] * weights[name] for name, dim in dimensions.items())
    score = round(total / sum(weights.values()))
    status = _status_from_score(score, hard_fail=hard_fail)
    infra_legacy, content_legacy, quality_legacy = _legacy_sections(raw)
    remediation = _remediation_queue(dimensions, raw)
    return {
        "schema_version": 2,
        "ts": _now().isoformat(),
        "status": status,
        "score": score,
        "hard_fail": hard_fail,
        "dimensions": dimensions,
        "infra": infra_legacy,
        "content": content_legacy,
        "quality": quality_legacy,
        "remediation_queue": remediation,
    }


def write_health_snapshot(path: Path = HEALTH_CURRENT_FILE) -> dict[str, Any]:
    payload = build_health_snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    emit_shadow_event(
        "HealthSnapshotComputed",
        actor="edge-check",
        payload={
            "status": payload["status"],
            "score": payload["score"],
            "hard_fail": payload["hard_fail"],
            "dimensions": {
                name: {"status": dim.get("status"), "score": dim.get("score")}
                for name, dim in payload["dimensions"].items()
            },
        },
    )
    return payload


def _events_for_cycle(cycle_id: str, path: Path = STATE_EVENTS_FILE) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl_reverse(path) if str(row.get("cycle_id") or "") == cycle_id]


def observe_cycle_health_events(state: dict[str, Any], *, path: Path = STATE_EVENTS_FILE) -> dict[str, Any]:
    cycle_id = str(state.get("cycle_id") or "").strip()
    if not cycle_id:
        return {"primitive_bypass": 0}
    rows = _events_for_cycle(cycle_id, path=path)
    existing_bypass = {
        str((row.get("payload") or {}).get("source") or "")
        for row in rows
        if row.get("type") == "PrimitiveBypassObserved"
    }

    primitive_invocations = Counter()
    capability_invocations = Counter()
    for row in rows:
        payload = row.get("payload") or {}
        if row.get("type") == "PrimitiveInvocationObserved":
            source = str(payload.get("source") or "").strip()
            if source:
                primitive_invocations[source] += 1
        elif row.get("type") == "CapabilityInvocationObserved":
            capability = str(payload.get("capability") or "").strip()
            if capability:
                capability_invocations[capability] += 1

    primitive_bypass = 0
    for source, count in primitive_invocations.items():
        capability_name = f"source.{source}"
        if capability_invocations.get(capability_name, 0) > 0 or source in existing_bypass:
            continue
        emit_shadow_event(
            "PrimitiveBypassObserved",
            actor="edge-postflight",
            cycle_id=cycle_id,
            payload={
                "source": source,
                "capability": capability_name,
                "reason": "primitive_used_without_capability_wrapper",
                "primitive_invocations": count,
                "capability_invocations": capability_invocations.get(capability_name, 0),
            },
        )
        primitive_bypass += 1

    return {"primitive_bypass": primitive_bypass}


__all__ = [
    "build_health_snapshot",
    "observe_cycle_health_events",
    "write_health_snapshot",
]
