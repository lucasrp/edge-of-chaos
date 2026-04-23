"""Dispatch runtime helpers for preflight, request enrichment, and prompt context."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    CLAIMS_DIGEST_FILE,
    CAPABILITIES_STATUS_FILE,
    CONTINUITY_DELTAS_DIR,
    CURRENT_DISPATCH_FILE,
    DISPATCH_QUEUE_FILE,
    EDGE_INSTANCE,
    EDGE_REPO_DIR,
    EDGE_STATE_DIR,
    FIRST_STEPS_FILE,
    HEALTH_CURRENT_FILE,
    ORPHAN_CLAIMS_FILE,
    PREFLIGHT_LOG_FILE,
    THREADS_DIR,
    WORKFLOW_HEALTH_FILE,
)
from .continuity import refresh_continuity_projections  # noqa: E402
from .capability_runtime import build_capability_status, invoke_capability, probe_capability  # noqa: E402
from .protocol_runtime import emit_protocol_step_observed, ensure_compiled_protocol, protocol_context  # noqa: E402
from .skill_inbox import attach_snapshot_to_dispatch  # noqa: E402
from .telemetry import emit_shadow_event, log_event, log_run_step, log_workflow_recommended  # noqa: E402
from .workflow_runtime import build_workflow_status, recommend_workflows  # noqa: E402

REQUEST_SCHEMA_VERSION = 1
RECENT_DUPLICATE_HOURS = 36

_QUERY_KEYS = (
    "query",
    "topic",
    "title",
    "subject",
    "target",
    "question",
    "task",
    "prompt",
    "focus",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_dispatch_state() -> dict[str, Any]:
    if not CURRENT_DISPATCH_FILE.exists():
        raise FileNotFoundError(f"{CURRENT_DISPATCH_FILE} not found")
    return json.loads(CURRENT_DISPATCH_FILE.read_text(encoding="utf-8"))


def write_dispatch_state(state: dict[str, Any]) -> None:
    _write_json(CURRENT_DISPATCH_FILE, state)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _append_preflight_log(name: str, status: str, detail: str = "") -> None:
    PREFLIGHT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{_now_iso()}] procedure: {name} | status: {status}"
    if detail:
        line += f" | detail: {detail}"
    with PREFLIGHT_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _run_subprocess(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd or EDGE_REPO_DIR),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _normalize_skill_name(skill: str | None) -> str:
    raw = str(skill or "").strip().lstrip("/")
    if not raw:
        return ""
    if EDGE_INSTANCE and raw.startswith(f"{EDGE_INSTANCE}-"):
        return raw[len(EDGE_INSTANCE) + 1 :]
    return raw


def _resolve_runtime_policy(skill: str | None, args: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_skill_name(skill)
    explicit = str(args.get("corpus_policy") or "").strip().lower()
    if explicit in {"block", "warn", "off"}:
        corpus_policy = explicit
    elif normalized in {"research", "report", "discovery"}:
        corpus_policy = "warn"
    elif normalized in {"heartbeat", "reflection", "autonomy", "strategy", "blog"}:
        corpus_policy = "off"
    else:
        corpus_policy = "warn"
    return {
        "corpus_policy": corpus_policy,
        "publish_policy": "standard",
        "thread_policy": "auto",
        "continuity_policy": "refresh-if-stale",
    }


def _health_snapshot() -> dict[str, Any]:
    check_script = EDGE_REPO_DIR / "bin" / "edge-check.sh"
    if check_script.exists():
        _run_subprocess([str(check_script)], cwd=EDGE_REPO_DIR)
    payload = _read_json(HEALTH_CURRENT_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    remediation = payload.get("remediation_queue") or []
    dimensions = payload.get("dimensions") or {}
    return {
        "status": payload.get("status", "unknown"),
        "score": int(payload.get("score", 100) or 100),
        "hard_fail": bool(payload.get("hard_fail", False)),
        "updated_at": payload.get("ts") or payload.get("updated_at") or "",
        "remediation_count": len(remediation) if isinstance(remediation, list) else 0,
        "dimensions": {
            name: {
                "status": dim.get("status"),
                "score": dim.get("score"),
            }
            for name, dim in dimensions.items()
            if isinstance(dim, dict)
        },
    }


def _claims_summary() -> tuple[dict[str, Any], dict[str, Any]]:
    projections = refresh_continuity_projections()
    digest = projections.get("digest") or {}
    orphans = projections.get("orphans") or {}
    return (
        {
            "open_total": digest.get("open_total", 0),
            "verified_total": digest.get("verified_total", 0),
            "attention_count": digest.get("attention_count", 0),
            "unthreaded_count": digest.get("unthreaded_count", 0),
            "stale_count": digest.get("stale_count", 0),
            "fanout_ratio": digest.get("fanout_ratio", 0),
            "hot_threads_by_open_claims": digest.get("hot_threads_by_open_claims", [])[:5],
            "oldest_open_claims": digest.get("oldest_open_claims", [])[:5],
            "source_path": str(CLAIMS_DIGEST_FILE),
        },
        {
            "orphan_total": orphans.get("orphan_total", 0),
            "open_orphan_total": orphans.get("open_orphan_total", 0),
            "stale_orphan_total": orphans.get("stale_orphan_total", 0),
            "multi_artifact_orphan_total": orphans.get("multi_artifact_orphan_total", 0),
            "candidate_clusters": orphans.get("candidate_clusters", [])[:5],
            "source_path": str(ORPHAN_CLAIMS_FILE),
        },
    )


def _primitives_status() -> dict[str, Any]:
    code, stdout, _stderr = _run_subprocess([sys.executable, str(EDGE_REPO_DIR / "tools" / "edge-primitives"), "status", "--json"])
    if code != 0 or not stdout:
        return {"health_status": "unknown", "summary": {}, "attention": []}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"health_status": "unknown", "summary": {}, "attention": []}
    summary = payload.get("summary") or {}
    sources = payload.get("sources") or []
    attention = [
        {
            "name": item.get("name"),
            "effective_status": item.get("effective_status"),
            "problems": item.get("problems", []),
            "usage_30d": item.get("usage_30d", 0),
        }
        for item in sources[:5]
        if item.get("effective_status") in {"broken", "degraded"}
    ]
    return {
        "health_status": summary.get("health_status", "unknown"),
        "summary": summary,
        "attention": attention,
    }


def _workflow_status_and_recommendations(query: str | None, *, skill: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status = build_workflow_status()
    recommendations = recommend_workflows(query or "", skill=skill, limit=3)
    return (
        {
            "workflow_total": status.get("summary", {}).get("workflow_total", 0),
            "cited_total": status.get("summary", {}).get("cited_total", 0),
            "broken_total": status.get("summary", {}).get("broken_total", 0),
            "stale_total": status.get("summary", {}).get("stale_total", 0),
            "top_used": status.get("summary", {}).get("top_used", []),
            "top_broken": status.get("summary", {}).get("top_broken", []),
            "source_path": str(WORKFLOW_HEALTH_FILE),
        },
        recommendations,
    )


def _capabilities_status(skill: str | None = None) -> dict[str, Any]:
    payload = build_capability_status(skill=skill)
    summary = payload.get("summary") or {}
    recommended = payload.get("recommended") or []
    attention = [
        {
            "name": item.get("name"),
            "kind": item.get("kind"),
            "effective_status": item.get("effective_status"),
            "description": item.get("description", ""),
        }
        for item in (payload.get("capabilities") or [])
        if item.get("effective_status") in {"broken", "degraded"}
    ][:5]
    return {
        "health_status": summary.get("health_status", "unknown"),
        "summary": summary,
        "recommended": recommended[:5],
        "attention": attention,
        "source_path": str(CAPABILITIES_STATUS_FILE),
    }


def _dispatch_queue_summary() -> dict[str, Any]:
    queue = _read_json(DISPATCH_QUEUE_FILE, [])
    if not isinstance(queue, list):
        queue = []
    head = queue[0] if queue else None
    return {
        "pending_total": len(queue),
        "head": head if isinstance(head, dict) else None,
        "source_path": str(DISPATCH_QUEUE_FILE),
    }


def _onboarding_summary() -> dict[str, Any]:
    steps = _read_json(FIRST_STEPS_FILE, [])
    if not isinstance(steps, list):
        steps = []
    pending = [item for item in steps if isinstance(item, dict) and str(item.get("status")).lower() == "pending"]
    return {
        "total": len(steps),
        "pending_total": len(pending),
        "pending_head": pending[0] if pending else None,
        "source_path": str(FIRST_STEPS_FILE),
    }


def _thread_title(thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return None
    try:
        text = thread_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    match = re.search(r"^title:\s*(.+)$", text, re.M)
    if not match:
        return None
    return match.group(1).strip().strip('"')


def derive_corpus_query(skill: str | None, args: dict[str, Any], primary_thread_id: str | None = None) -> str | None:
    for key in _QUERY_KEYS:
        value = args.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text[:180]
    thread_title = _thread_title(primary_thread_id)
    if thread_title:
        return thread_title[:180]
    normalized = _normalize_skill_name(skill)
    if normalized:
        return normalized.replace("-", " ")
    return None


def _result_date(result: dict[str, Any]) -> str:
    path_value = str(result.get("path") or "").strip()
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_absolute():
        path = EDGE_STATE_DIR / path
    if not path.exists():
        return ""
    if path.suffix == ".md":
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                fm = json.loads("{}")
                try:
                    import yaml  # local optional import

                    fm = yaml.safe_load(parts[1]) or {}
                except Exception:
                    fm = {}
                if isinstance(fm, dict) and fm.get("date"):
                    return str(fm.get("date"))
        except Exception:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _hours_since(value: str) -> float | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_now() - dt.astimezone(timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


def corpus_lookup(query: str | None, *, skill: str | None = None, corpus_policy: str = "warn") -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    if not query:
        return [], {"level": "none", "recent_hits": [], "reason": "no_query"}, []

    try:
        sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "search"))
        from search import search_with_sidecar  # type: ignore

        results, workflows = search_with_sidecar(query, limit=6, wf_limit=3)
    except Exception as exc:
        return [], {"level": "none", "recent_hits": [], "reason": f"search_failed:{exc}"}, []

    hits = []
    recent_hits = []
    for item in results:
        normalized = {
            "title": str(item.get("title") or Path(str(item.get("path") or "")).stem),
            "path": str(item.get("path") or ""),
            "type": str(item.get("type") or ""),
            "score": round(float(item.get("score") or 0), 6),
            "snippet": str(item.get("snippet") or "")[:240],
        }
        normalized["date"] = _result_date(normalized)
        hits.append(normalized)
        age_hours = _hours_since(normalized["date"]) if normalized["date"] else None
        if age_hours is not None and age_hours <= RECENT_DUPLICATE_HOURS:
            recent_hits.append({**normalized, "age_hours": round(age_hours, 2)})

    level = "none"
    reason = "no_recent_hits"
    if recent_hits:
        level = "block" if corpus_policy == "block" else "warn"
        reason = f"{len(recent_hits)} recent similar artifact(s)"
    duplicate_risk = {
        "level": level,
        "reason": reason,
        "corpus_policy": corpus_policy,
        "query": query,
        "recent_hits": recent_hits[:3],
    }
    workflow_recommendations = [
        {
            "slug": Path(str(item.get("path") or "")).stem,
            "title": str(item.get("title") or Path(str(item.get("path") or "")).stem),
            "path": str(item.get("path") or ""),
            "score": round(float(item.get("score") or 0), 6),
            "source": "search_sidecar",
        }
        for item in workflows or []
    ][:3]
    return hits[:6], duplicate_risk, workflow_recommendations


def _record_workflow_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    query: str | None,
    cycle_id: str | None,
    stage: str,
    profile: str,
    skill: str | None,
) -> None:
    for item in recommendations:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        log_workflow_recommended(
            slug,
            title=str(item.get("title") or ""),
            source=str(item.get("source") or ""),
            score=float(item.get("score") or 0.0),
            query=query or "",
            cycle_id=cycle_id,
            stage=stage,
            profile=profile,
            skill=skill or "",
        )


def _step_result(step: dict[str, Any], *, status: str, satisfied: bool, detail: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": step.get("id"),
        "kind": step.get("kind"),
        "status": status,
        "satisfied": satisfied,
        "detail": detail,
    }
    if step.get("note"):
        payload["note"] = step.get("note")
    if extra:
        payload.update(extra)
    return payload


def _execute_preflight_step(
    step: dict[str, Any],
    state: dict[str, Any],
    *,
    skill: str | None,
    stage: str,
) -> dict[str, Any]:
    request = state.setdefault("request", {})
    kind = str(step.get("kind") or "")
    runtime_policy = request.get("runtime_policy") or {}

    if kind == "health.snapshot":
        snapshot = _health_snapshot()
        request["health_snapshot"] = snapshot
        return _step_result(step, status="ok", satisfied=True, detail=f"status={snapshot.get('status')} score={snapshot.get('score')}")

    if kind == "inbox.snapshot":
        inbox = attach_snapshot_to_dispatch(state, skill=skill)
        request["async_inbox"] = inbox
        return _step_result(step, status="ok", satisfied=True, detail=f"unprocessed={inbox.get('unprocessed_total', 0)}")

    if kind == "claims.refresh":
        claims_summary, orphan_summary = _claims_summary()
        request["claims_summary"] = claims_summary
        request["orphan_claims_summary"] = orphan_summary
        return _step_result(
            step,
            status="ok",
            satisfied=True,
            detail=f"open={claims_summary.get('open_total', 0)} orphans={orphan_summary.get('orphan_total', 0)}",
        )

    if kind == "primitives.status":
        primitives = _primitives_status()
        request["primitives_status"] = primitives
        return _step_result(step, status="ok", satisfied=True, detail=f"health={primitives.get('health_status', 'unknown')}")

    if kind == "capabilities.status":
        capabilities = _capabilities_status(skill)
        request["capabilities_status"] = capabilities
        return _step_result(step, status="ok", satisfied=True, detail=f"health={capabilities.get('health_status', 'unknown')}")

    if kind == "corpus.lookup":
        corpus_query = derive_corpus_query(skill, request.get("args", {}) or {}, primary_thread_id=request.get("primary_thread_id"))
        hits, duplicate_risk, workflow_recommendations = corpus_lookup(
            corpus_query,
            skill=skill,
            corpus_policy=str(runtime_policy.get("corpus_policy") or "warn"),
        )
        request["corpus_query"] = corpus_query
        request["corpus_hits"] = hits
        request["duplicate_risk"] = duplicate_risk
        request["workflow_recommendations"] = workflow_recommendations[:3]
        query_state = "searched" if corpus_query else "missing"
        search_failed = str(duplicate_risk.get("reason") or "").startswith("search_failed:")
        return _step_result(
            step,
            status="failed" if search_failed else "ok",
            satisfied=not search_failed,
            detail=f"query={query_state} hits={len(hits)} duplicate={duplicate_risk.get('level')}",
            extra={"corpus_query": corpus_query or "", "corpus_hits": len(hits), "duplicate_risk": duplicate_risk.get("level")},
        )

    if kind == "workflow.status":
        corpus_query = request.get("corpus_query")
        workflow_status, workflow_recommendations = _workflow_status_and_recommendations(corpus_query, skill=skill)
        corpus_workflows = list(request.get("workflow_recommendations") or [])
        if corpus_workflows:
            workflow_recommendations = corpus_workflows + [
                item
                for item in workflow_recommendations
                if str(item.get("slug") or "") not in {str(existing.get("slug") or "") for existing in corpus_workflows}
            ]
        request["workflow_status"] = workflow_status
        request["workflow_recommendations"] = workflow_recommendations[:3]
        _record_workflow_recommendations(
            request["workflow_recommendations"],
            query=corpus_query,
            cycle_id=state.get("cycle_id"),
            stage=stage,
            profile=str(state.get("state", {}).get("preflight_profile") or request.get("preflight_profile") or "standard"),
            skill=skill,
        )
        return _step_result(
            step,
            status="ok",
            satisfied=True,
            detail=f"recommended={len(request['workflow_recommendations'])} broken={workflow_status.get('broken_total', 0)}",
        )

    if kind == "queue.status":
        queue_summary = _dispatch_queue_summary()
        request["dispatch_queue_summary"] = queue_summary
        return _step_result(step, status="ok", satisfied=True, detail=f"pending={queue_summary.get('pending_total', 0)}")

    if kind == "onboarding.status":
        onboarding_summary = _onboarding_summary()
        request["onboarding_summary"] = onboarding_summary
        return _step_result(step, status="ok", satisfied=True, detail=f"pending={onboarding_summary.get('pending_total', 0)}")

    if kind == "capability.probe":
        capability_name = str(step.get("capability") or "")
        try:
            result = probe_capability(capability_name, skill=skill)
            satisfied = result.returncode == 0
            return _step_result(
                step,
                status="ok" if satisfied else "failed",
                satisfied=satisfied,
                detail=f"{capability_name} exit={result.returncode}",
                extra={"capability": capability_name, "exit_code": int(result.returncode)},
            )
        except Exception as exc:
            return _step_result(step, status="failed", satisfied=False, detail=str(exc), extra={"capability": capability_name})

    if kind == "capability.invoke":
        capability_name = str(step.get("capability") or "")
        argv = list(step.get("argv") or [])
        try:
            result = invoke_capability(capability_name, argv, skill=skill)
            satisfied = result.returncode == 0
            return _step_result(
                step,
                status="ok" if satisfied else "failed",
                satisfied=satisfied,
                detail=f"{capability_name} exit={result.returncode}",
                extra={"capability": capability_name, "exit_code": int(result.returncode), "argv": argv},
            )
        except Exception as exc:
            return _step_result(step, status="failed", satisfied=False, detail=str(exc), extra={"capability": capability_name, "argv": argv})

    raise RuntimeError(f"unsupported preflight protocol kind: {kind}")


def enrich_dispatch_state(
    state: dict[str, Any],
    *,
    skill: str | None = None,
    stage: str = "preflight",
    profile: str | None = None,
) -> dict[str, Any]:
    request = state.setdefault("request", {})
    state_block = state.setdefault("state", {})
    skill = skill or request.get("skill")
    args = request.setdefault("args", {})
    request["schema_version"] = REQUEST_SCHEMA_VERSION
    runtime_policy = _resolve_runtime_policy(skill, args)
    request["runtime_policy"] = runtime_policy
    protocol = ensure_compiled_protocol("preflight")
    state_block["preflight_profile"] = profile or request.get("preflight_profile") or "standard"
    state_block["preflight_stage"] = stage
    request["pre_skill_context"] = protocol_context(protocol)
    emit_shadow_event(
        "PreSkillContextLoaded",
        actor="edge-preflight",
        cycle_id=state.get("cycle_id"),
        payload={
            "protocol_stage": "pre_skill",
            "source_hash": protocol.get("source_hash"),
            "compiled_hash": protocol.get("compiled_hash"),
            "context_note_total": len(protocol.get("context_notes") or []),
            "operator_note_total": len(protocol.get("operator_notes") or []),
        },
    )

    evidence: list[dict[str, Any]] = []
    failed_steps = 0
    for step in protocol.get("procedures") or []:
        result = _execute_preflight_step(step, state, skill=skill, stage=stage)
        evidence.append(result)
        if not result.get("satisfied"):
            failed_steps += 1
        emit_protocol_step_observed(
            "preflight",
            step,
            status=str(result.get("status") or "unknown"),
            detail=str(result.get("detail") or ""),
            satisfied=bool(result.get("satisfied")),
            cycle_id=state.get("cycle_id"),
            extra={k: v for k, v in result.items() if k not in {"id", "kind", "note", "status", "satisfied", "detail"}},
        )

    request["preflight_evidence"] = evidence
    primary_thread_id = request.get("primary_thread_id")
    request["dispatch_reason"] = request.get("dispatch_reason") or state_block.get("phase") or "runtime"
    request["linked_threads"] = [primary_thread_id] if primary_thread_id else []
    request.setdefault("duplicate_risk", {"level": "none", "recent_hits": [], "reason": "unchecked"})
    request.setdefault("workflow_recommendations", [])
    request.setdefault("corpus_hits", [])
    request["constraints"] = {
        "degraded_health": (request.get("health_snapshot") or {}).get("status") in {"degraded", "unhealthy", "critical"},
        "has_pending_inbox": (request.get("async_inbox") or {}).get("unprocessed_total", 0) > 0,
        "has_onboarding": (request.get("onboarding_summary") or {}).get("pending_total", 0) > 0,
    }
    state_block["preflight_status"] = "warning" if failed_steps else "completed"
    state_block["preflight_checked_at"] = _now_iso()
    state_block["updated_at"] = state_block["preflight_checked_at"]
    if state_block.get("phase") in {"opened", "preflight_failed"}:
        state_block["phase"] = "preflight_completed"

    claims_summary = request.get("claims_summary") or {}
    orphan_summary = request.get("orphan_claims_summary") or {}
    summary = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "skill": skill,
        "stage": stage,
        "profile": state_block["preflight_profile"],
        "protocol_source_hash": request["pre_skill_context"].get("source_hash"),
        "protocol_compiled_hash": request["pre_skill_context"].get("compiled_hash"),
        "step_total": len(request["pre_skill_context"].get("steps") or []),
        "failed_steps": failed_steps,
        "evidence_total": len(evidence),
        "health_status": (request.get("health_snapshot") or {}).get("status"),
        "health_score": (request.get("health_snapshot") or {}).get("score"),
        "corpus_query": request.get("corpus_query"),
        "corpus_hits": len(request.get("corpus_hits") or []),
        "duplicate_risk": (request.get("duplicate_risk") or {}).get("level"),
        "open_claims": claims_summary.get("open_total", 0),
        "orphans": orphan_summary.get("orphan_total", 0),
        "primitive_health": (request.get("primitives_status") or {}).get("health_status"),
        "capability_health": (request.get("capabilities_status") or {}).get("health_status"),
        "workflow_recommendations": len(request.get("workflow_recommendations") or []),
        "queue_pending": (request.get("dispatch_queue_summary") or {}).get("pending_total", 0),
        "onboarding_pending": (request.get("onboarding_summary") or {}).get("pending_total", 0),
    }
    return summary


def record_preflight(state: dict[str, Any], summary: dict[str, Any], *, status: str = "completed") -> None:
    cycle_id = state.get("cycle_id")
    _append_preflight_log("preflight", status.upper(), json.dumps(summary, ensure_ascii=False))
    event_type = "PreflightCompleted" if status in {"completed", "warning"} else "PreflightFailed"
    emit_shadow_event(event_type, actor="edge-preflight", cycle_id=cycle_id, payload=summary)
    log_run_step("edge-preflight", summary.get("stage", "run"), status, run_id=cycle_id, **summary)
    log_event(
        "dispatch_preflight",
        actor="edge-preflight",
        cycle_id=cycle_id,
        status=status,
        profile=summary.get("profile") or "",
        stage=summary.get("stage") or "",
        skill=summary.get("skill") or "",
        duplicate_risk=summary.get("duplicate_risk") or "none",
        corpus_hits=summary.get("corpus_hits", 0),
    )


def maybe_block_duplicate(state: dict[str, Any]) -> tuple[bool, str | None]:
    request = state.get("request", {}) or {}
    risk = request.get("duplicate_risk") or {}
    if (risk.get("level") or "none") != "block":
        return False, None
    reason = str(risk.get("reason") or "duplicate_risk_block")
    return True, reason


def render_skill_runtime_prompt(skill: str, state: dict[str, Any]) -> str:
    request = state.get("request", {}) or {}
    summary = {
        "schema_version": request.get("schema_version", REQUEST_SCHEMA_VERSION),
        "trigger": request.get("trigger"),
        "execution_policy": request.get("policy"),
        "runtime_policy": request.get("runtime_policy", {}),
        "skill": request.get("skill"),
        "primary_thread_id": request.get("primary_thread_id"),
        "linked_threads": request.get("linked_threads", []),
        "dispatch_reason": request.get("dispatch_reason"),
        "constraints": request.get("constraints", {}),
        "pre_skill_context": request.get("pre_skill_context", {}),
        "preflight_evidence": request.get("preflight_evidence", []),
        "health_snapshot": request.get("health_snapshot", {}),
        "async_inbox": request.get("async_inbox", {}),
        "corpus_query": request.get("corpus_query"),
        "corpus_hits": request.get("corpus_hits", [])[:4],
        "duplicate_risk": request.get("duplicate_risk", {}),
        "claims_summary": request.get("claims_summary", {}),
        "orphan_claims_summary": request.get("orphan_claims_summary", {}),
        "primitives_status": request.get("primitives_status", {}),
        "capabilities_status": request.get("capabilities_status", {}),
        "workflow_status": request.get("workflow_status", {}),
        "workflow_recommendations": request.get("workflow_recommendations", [])[:3],
        "dispatch_queue_summary": request.get("dispatch_queue_summary", {}),
        "onboarding_summary": request.get("onboarding_summary", {}),
        "args": request.get("args", {}),
    }
    return (
        f"{skill}\n\n"
        "Dispatch runtime context below is authoritative for cross-cutting checks already handled by CLI "
        "(health, inbox, corpus, claims, primitives, workflows, queue, onboarding, protocol execution).\n"
        "Do not re-derive those manually unless a field is missing or obviously stale.\n\n"
        "Prefer `edge-cap invoke <capability> -- ...` over direct CLI/tool calls when a capability exists in `capabilities_status`.\n\n"
        "```json\n"
        f"{json.dumps(summary, indent=2, ensure_ascii=False)}\n"
        "```"
    )
