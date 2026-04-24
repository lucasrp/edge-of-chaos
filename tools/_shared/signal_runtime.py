"""Runtime signal aggregation for heartbeat routing and preflight context."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    CAPABILITIES_STATUS_FILE,
    CURRENT_DISPATCH_FILE,
    DISPATCH_QUEUE_FILE,
    EDGE_REPO_DIR,
    HEALTH_CURRENT_FILE,
    PRIMITIVES_STATUS_FILE,
    RENDER_INSTALL_DRIFT_FILE,
    STATE_EVENTS_FILE,
    WORKFLOW_HEALTH_FILE,
)
from .capability_runtime import build_capability_status, build_configured_integrations  # noqa: E402

SIGNAL_SCHEMA_VERSION = 1
DEFAULT_LIMIT = 12
HIGH_PRIORITY_SEVERITIES = {"critical", "warning"}
HIGH_PRIORITY_EFFECTS = {"gate", "route"}
ALWAYS_INCLUDE_IDS = {"health.current", "primitives.health", "capabilities.health"}

SEVERITY_SCORE = {
    "critical": 100,
    "warning": 70,
    "info": 35,
}
DECISION_SCORE = {
    "gate": 30,
    "route": 20,
    "inform": 0,
}
STATUS_SEVERITY = {
    "critical": "critical",
    "unhealthy": "critical",
    "fail": "critical",
    "failed": "critical",
    "broken": "critical",
    "degraded": "warning",
    "warning": "warning",
    "warn": "warning",
    "healthy": "info",
    "ok": "info",
    "available": "info",
    "active": "info",
    "probed": "info",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}


def iter_jsonl_tail(path: Path, limit: int = 80) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, limit))
    try:
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
    except OSError:
        return []
    return list(rows)


def status_to_severity(status: Any, *, default: str = "info") -> str:
    return STATUS_SEVERITY.get(str(status or "").strip().lower(), default)


def normalize_terms(query: str | None) -> list[str]:
    if not query:
        return []
    terms = []
    for term in re.findall(r"[\w.-]+", query.lower()):
        if len(term) >= 3 and term not in {"the", "and", "for", "com", "uma", "que", "para"}:
            terms.append(term)
    return sorted(set(terms))


def text_blob(value: Any) -> str:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(text_blob(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(text_blob(v) for v in value)
    return str(value).lower()


def classify_failure(problems: list[Any], row: dict[str, Any]) -> list[str]:
    text = " ".join(str(item or "") for item in problems).lower()
    classes: list[str] = []
    if any(token in text for token in ("credential", "secret", "token", "api_key", "env")):
        classes.append("missing_credentials")
    if any(token in text for token in ("declared_not_activated", "not_activated", "manifest_requires", "required_command_missing", "optional_command_missing")):
        classes.append("missing_install_time_materialization")
    if "last_probe_failed" in text or row.get("last_probe_ok") is False:
        classes.append("broken_probe")
    if "untracked_local_artifact" in text or "binary_without_meta" in text:
        classes.append("contract_drift")
    if not classes and problems:
        classes.append("degraded_provider_or_unknown")
    return sorted(set(classes))


def make_signal(
    *,
    signal_id: str,
    source: str,
    kind: str,
    summary: str,
    severity: str = "info",
    decision_effect: str = "inform",
    evidence: dict[str, Any] | None = None,
    surface: str = "edge",
    operation: str = "signals",
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "source": source,
        "surface": surface,
        "operation": operation,
        "kind": kind,
        "decision_effect": decision_effect,
        "severity": severity,
        "summary": summary,
        "evidence": evidence or {},
    }


def load_primitives_status(*, refresh: bool = False) -> dict[str, Any]:
    cached = read_json(PRIMITIVES_STATUS_FILE, {})
    if isinstance(cached, dict) and cached and not refresh and "_read_error" not in cached:
        return cached

    tool = EDGE_REPO_DIR / "tools" / "edge-primitives"
    if not tool.exists():
        return cached if isinstance(cached, dict) and cached else {"summary": {"health_status": "unknown"}, "sources": []}
    result = subprocess.run(
        [sys.executable, str(tool), "status", "--json"],
        cwd=str(EDGE_REPO_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"summary": {"health_status": "fail"}, "sources": [], "error": result.stderr.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"summary": {"health_status": "fail"}, "sources": [], "error": "invalid edge-primitives json"}


def load_capabilities_status(*, skill: str | None = None, refresh: bool = False) -> dict[str, Any]:
    cached = read_json(CAPABILITIES_STATUS_FILE, {})
    if isinstance(cached, dict) and cached and not refresh and "_read_error" not in cached:
        return cached
    return build_capability_status(skill=skill)


def collect_health_signal(signals: list[dict[str, Any]]) -> None:
    payload = read_json(HEALTH_CURRENT_FILE, {})
    if not payload:
        signals.append(
            make_signal(
                signal_id="health.missing",
                source="health",
                kind="snapshot",
                summary="No health/current.json snapshot is available.",
                severity="warning",
                decision_effect="route",
                evidence={"path": str(HEALTH_CURRENT_FILE)},
            )
        )
        return
    if isinstance(payload, dict) and payload.get("_read_error"):
        signals.append(
            make_signal(
                signal_id="health.read_error",
                source="health",
                kind="snapshot",
                summary="Health snapshot could not be read.",
                severity="warning",
                decision_effect="route",
                evidence=payload,
            )
        )
        return

    status = str(payload.get("status") or payload.get("health_status") or "unknown")
    score = payload.get("score")
    severity = status_to_severity(status, default="warning")
    decision_effect = "gate" if severity == "critical" else "route" if severity == "warning" else "inform"
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    attention_dimensions = [
        {"name": name, "status": value.get("status"), "detail": value.get("detail", "")}
        for name, value in dimensions.items()
        if isinstance(value, dict) and str(value.get("status") or "ok") != "ok"
    ][:6]
    summary = f"Health status is {status}"
    if score is not None:
        summary += f" with score {score}"
    signals.append(
        make_signal(
            signal_id="health.current",
            source="health",
            kind="snapshot",
            summary=summary + ".",
            severity=severity,
            decision_effect=decision_effect,
            evidence={
                "status": status,
                "score": score,
                "hard_fail": payload.get("hard_fail"),
                "attention_dimensions": attention_dimensions,
                "path": str(HEALTH_CURRENT_FILE),
            },
        )
    )


def collect_primitives_signal(signals: list[dict[str, Any]], *, refresh: bool = False) -> None:
    payload = load_primitives_status(refresh=refresh)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    sources = payload.get("sources") if isinstance(payload, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(sources, list):
        sources = []
    health_status = str(summary.get("health_status") or "unknown")
    attention = [
        {
            "name": item.get("name"),
            "effective_status": item.get("effective_status"),
            "problems": list(item.get("problems") or []),
            "failure_classes": classify_failure(list(item.get("problems") or []), item),
            "description": item.get("description", ""),
        }
        for item in sources
        if isinstance(item, dict) and item.get("effective_status") in {"broken", "degraded"}
    ][:8]
    severity = status_to_severity(health_status, default="warning" if attention else "info")
    if attention and severity == "info":
        severity = "warning"
    decision_effect = "gate" if severity == "critical" else "route" if severity == "warning" else "inform"
    signals.append(
        make_signal(
            signal_id="primitives.health",
            source="primitives",
            kind="status",
            summary=(
                f"Primitive health is {health_status}; "
                f"broken={summary.get('broken_total', 0)} degraded={summary.get('degraded_total', 0)}."
            ),
            severity=severity,
            decision_effect=decision_effect,
            evidence={
                "summary": summary,
                "attention": attention,
                "path": str(PRIMITIVES_STATUS_FILE),
                "prevents": [
                    "reliable edge-sources / edge-signals expansion for affected surfaces",
                    "operator-visible confidence that requested integrations were materialized",
                ] if attention else [],
            },
        )
    )


def collect_capabilities_signal(signals: list[dict[str, Any]], *, skill: str | None = None, refresh: bool = False) -> None:
    payload = load_capabilities_status(skill=skill, refresh=refresh)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    capabilities = payload.get("capabilities") if isinstance(payload, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(capabilities, list):
        capabilities = []
    integrations = build_configured_integrations(skill=skill)
    unbound = integrations.get("unbound_integrations") or []
    health_status = str(summary.get("health_status") or "unknown")
    attention = [
        {
            "name": item.get("name"),
            "kind": item.get("kind"),
            "roles": list(item.get("roles") or []),
            "effective_status": item.get("effective_status"),
            "problems": list(item.get("problems") or []),
            "failure_classes": classify_failure(list(item.get("problems") or []), item),
            "description": item.get("description", ""),
        }
        for item in capabilities
        if isinstance(item, dict) and item.get("effective_status") in {"broken", "degraded"}
    ][:8]
    severity = status_to_severity(health_status, default="warning" if attention or unbound else "info")
    if (attention or unbound) and severity == "info":
        severity = "warning"
    decision_effect = "gate" if severity == "critical" else "route" if severity == "warning" else "inform"
    signals.append(
        make_signal(
            signal_id="capabilities.health",
            source="capabilities",
            kind="status",
            summary=(
                f"Capability health is {health_status}; "
                f"broken={summary.get('broken_total', 0)} degraded={summary.get('degraded_total', 0)} "
                f"unbound_integrations={len(unbound)}."
            ),
            severity=severity,
            decision_effect=decision_effect,
            evidence={
                "summary": summary,
                "attention": attention,
                "unbound_integrations": unbound[:8],
                "integrations_summary": integrations.get("summary") or {},
                "path": str(CAPABILITIES_STATUS_FILE),
                "prevents": [
                    "using affected capabilities through edge-context, edge-search, edge-signals, or edge-cap",
                    "separating reasoning failure from substrate failure in reports",
                ] if attention or unbound else [],
            },
        )
    )


def collect_dispatch_signals(signals: list[dict[str, Any]]) -> None:
    dispatch = read_json(CURRENT_DISPATCH_FILE, {})
    if isinstance(dispatch, dict) and dispatch and "_read_error" not in dispatch:
        state = dispatch.get("state") or {}
        request = dispatch.get("request") or {}
        active = bool(state.get("active"))
        dispatched = bool(state.get("skill_dispatched"))
        severity = "warning" if active and not dispatched else "info"
        decision_effect = "route" if active and not dispatched else "inform"
        signals.append(
            make_signal(
                signal_id="dispatch.current",
                source="dispatch",
                kind="snapshot",
                summary=(
                    f"Current dispatch active={active} skill_dispatched={dispatched} "
                    f"skill={request.get('skill') or ''}."
                ),
                severity=severity,
                decision_effect=decision_effect,
                evidence={
                    "cycle_id": dispatch.get("cycle_id"),
                    "active": active,
                    "skill_dispatched": dispatched,
                    "phase": state.get("phase"),
                    "skill": request.get("skill"),
                    "trigger": request.get("trigger"),
                    "path": str(CURRENT_DISPATCH_FILE),
                },
            )
        )

    queue = read_json(DISPATCH_QUEUE_FILE, [])
    queue_items = queue if isinstance(queue, list) else queue.get("items", []) if isinstance(queue, dict) else []
    pending = [item for item in queue_items if isinstance(item, dict) and str(item.get("status") or "pending") in {"pending", "queued"}]
    if pending:
        signals.append(
            make_signal(
                signal_id="dispatch.queue",
                source="dispatch_queue",
                kind="snapshot",
                summary=f"Dispatch queue has {len(pending)} pending item(s).",
                severity="warning",
                decision_effect="route",
                evidence={"pending": pending[:5], "path": str(DISPATCH_QUEUE_FILE)},
            )
        )


def collect_workflow_signal(signals: list[dict[str, Any]]) -> None:
    payload = read_json(WORKFLOW_HEALTH_FILE, {})
    if not isinstance(payload, dict) or not payload:
        return
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    broken = int(summary.get("broken_total", 0) or 0)
    stale = int(summary.get("stale_total", 0) or 0)
    ignored = int(summary.get("ignored_30d", 0) or 0)
    severity = "warning" if broken or stale else "info"
    signals.append(
        make_signal(
            signal_id="workflow.health",
            source="workflow",
            kind="status",
            summary=f"Workflow health: broken={broken} stale={stale} ignored_30d={ignored}.",
            severity=severity,
            decision_effect="route" if severity == "warning" else "inform",
            evidence={"summary": summary, "path": str(WORKFLOW_HEALTH_FILE)},
        )
    )


def collect_render_install_signal(signals: list[dict[str, Any]]) -> None:
    payload = read_json(RENDER_INSTALL_DRIFT_FILE, {})
    if not isinstance(payload, dict) or not payload:
        return
    summary = payload.get("summary") or {}
    if not isinstance(summary, dict):
        return
    drift_total = sum(
        int(summary.get(key, 0) or 0)
        for key in ("rendered_without_install", "install_without_render", "hash_mismatches", "missing_on_disk", "doctor_fail")
    )
    warning_total = int(summary.get("doctor_warn", 0) or 0)
    if not drift_total and not warning_total:
        return
    signals.append(
        make_signal(
            signal_id="render_install.drift",
            source="render_install",
            kind="status",
            summary=f"Render/apply drift detected: hard={drift_total} warnings={warning_total}.",
            severity="critical" if int(summary.get("doctor_fail", 0) or 0) else "warning",
            decision_effect="gate" if int(summary.get("doctor_fail", 0) or 0) else "route",
            evidence={"summary": summary, "path": str(RENDER_INSTALL_DRIFT_FILE)},
        )
    )


def collect_recent_event_signals(signals: list[dict[str, Any]]) -> None:
    rows = iter_jsonl_tail(STATE_EVENTS_FILE, limit=120)
    attention_types = Counter()
    examples: list[dict[str, Any]] = []
    for row in rows:
        event_type = str(row.get("type") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload_error = any(
            str(payload.get(key) or "").strip()
            for key in ("error", "error_class", "error_fingerprint", "stderr_tail")
        )
        is_attention = (
            any(token in event_type.lower() for token in ("failed", "missing", "timeout", "bypass"))
            or "ok" in payload and payload.get("ok") is False
            or "exit_code" in payload and payload.get("exit_code") not in (0, None)
            or payload_error
        )
        if not is_attention:
            continue
        attention_types[event_type or "unknown"] += 1
        if len(examples) < 8:
            examples.append({"ts": row.get("ts"), "type": event_type, "payload": payload})
    if attention_types:
        signals.append(
            make_signal(
                signal_id="events.attention",
                source="state_events",
                kind="delta",
                summary=f"Recent state events contain {sum(attention_types.values())} attention event(s).",
                severity="warning",
                decision_effect="route",
                evidence={
                    "counts_by_type": dict(attention_types.most_common(8)),
                    "examples": examples,
                    "path": str(STATE_EVENTS_FILE),
                },
            )
        )


def rank_and_filter(signals: list[dict[str, Any]], *, query: str | None, limit: int) -> list[dict[str, Any]]:
    terms = normalize_terms(query)
    ranked = []
    for index, signal in enumerate(signals):
        blob = text_blob(signal)
        matched = not terms or any(term in blob for term in terms)
        keep = (
            matched
            or signal.get("id") in ALWAYS_INCLUDE_IDS
            or signal.get("severity") in HIGH_PRIORITY_SEVERITIES
            or signal.get("decision_effect") in HIGH_PRIORITY_EFFECTS
        )
        if not keep:
            continue
        score = SEVERITY_SCORE.get(str(signal.get("severity") or "info"), 0)
        score += DECISION_SCORE.get(str(signal.get("decision_effect") or "inform"), 0)
        if matched and terms:
            score += 40
        if signal.get("id") in {"health.current", "primitives.health", "capabilities.health"}:
            score += 10
        enriched = dict(signal)
        enriched["query_match"] = bool(matched)
        enriched["score"] = score
        enriched["_index"] = index
        ranked.append(enriched)
    ranked.sort(key=lambda item: (-int(item.get("score") or 0), item.get("_index", 0), item.get("id", "")))
    output = []
    for item in ranked[: max(1, limit)]:
        item.pop("_index", None)
        output.append(item)
    return output


def build_report_warning(signals: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = [
        signal
        for signal in signals
        if signal.get("id") in {"primitives.health", "capabilities.health"}
        and signal.get("severity") in {"critical", "warning"}
    ]
    if not relevant:
        return {"required": False, "items": []}
    items = []
    for signal in relevant:
        evidence = signal.get("evidence") or {}
        items.append(
            {
                "signal_id": signal.get("id"),
                "summary": signal.get("summary"),
                "broken_or_degraded": evidence.get("attention") or [],
                "what_it_prevented": evidence.get("prevents") or [],
                "fallbacks_used": [],
                "recovery_status": "repair install/materialization/probe path, then re-run edge-signals",
            }
        )
    return {
        "required": True,
        "title": "Primitive health warning",
        "items": items,
    }


def build_signal_context(
    *,
    query: str | None = None,
    scope: str = "routing",
    limit: int = DEFAULT_LIMIT,
    skill: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    collect_health_signal(signals)
    collect_primitives_signal(signals, refresh=refresh)
    collect_capabilities_signal(signals, skill=skill, refresh=refresh)
    collect_dispatch_signals(signals)
    collect_workflow_signal(signals)
    collect_render_install_signal(signals)
    collect_recent_event_signals(signals)

    filtered = rank_and_filter(signals, query=query, limit=limit)
    severity_counts = Counter(str(signal.get("severity") or "info") for signal in filtered)
    effect_counts = Counter(str(signal.get("decision_effect") or "inform") for signal in filtered)
    primitive_signal = next((item for item in signals if item.get("id") == "primitives.health"), {})
    capability_signal = next((item for item in signals if item.get("id") == "capabilities.health"), {})
    summary = {
        "signal_total": len(filtered),
        "available_signal_total": len(signals),
        "critical_total": severity_counts.get("critical", 0),
        "warning_total": severity_counts.get("warning", 0),
        "info_total": severity_counts.get("info", 0),
        "gating_total": effect_counts.get("gate", 0),
        "routing_total": effect_counts.get("route", 0),
        "primitive_health": ((primitive_signal.get("evidence") or {}).get("summary") or {}).get("health_status", "unknown"),
        "capability_health": ((capability_signal.get("evidence") or {}).get("summary") or {}).get("health_status", "unknown"),
        "report_warning_required": build_report_warning(filtered).get("required", False),
    }
    return {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "query": query or "",
        "scope": scope,
        "skill": skill or "",
        "summary": summary,
        "signals": filtered,
        "report_warning": build_report_warning(filtered),
    }


__all__ = ["build_signal_context", "build_report_warning"]
