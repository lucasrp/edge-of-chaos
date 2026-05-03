"""Artifact lifecycle supervision for dispatch cycles."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jsonl_runtime import iter_jsonl_reverse
from .skill_policy import canonical_skill_id, skill_requires_artifact_publication
from .telemetry import emit_shadow_event


TRUE_VALUES = {"1", "true", "yes", "ok", "success", "succeeded", "completed", "pass", "passed"}
FALSE_VALUES = {"0", "false", "no", "fail", "failed", "error", "blocked", "aborted"}
PENDING_MARKERS = {"pending", "in flight", "in-flight"}


def iso_ge(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    try:
        left_dt = datetime.fromisoformat(left)
        right_dt = datetime.fromisoformat(right)
    except ValueError:
        return False
    if left_dt.tzinfo is None:
        left_dt = left_dt.replace(tzinfo=timezone.utc)
    if right_dt.tzinfo is None:
        right_dt = right_dt.replace(tzinfo=timezone.utc)
    return left_dt >= right_dt


def _payload(event: dict[str, Any] | None) -> dict[str, Any]:
    payload = (event or {}).get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _artifact(event: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(event.get("artifact") or payload.get("artifact") or payload.get("path") or "").strip()


def _phase_ok(payload: dict[str, Any]) -> bool | None:
    value = payload.get("ok")
    if isinstance(value, bool):
        return value
    if value is not None:
        text = str(value).strip().lower()
        if text in TRUE_VALUES:
            return True
        if text in FALSE_VALUES:
            return False

    status = str(payload.get("status") or "").strip().lower()
    if status in TRUE_VALUES:
        return True
    if status in FALSE_VALUES:
        return False
    return None


def _event_after_threshold(event: dict[str, Any], threshold: str | None) -> bool:
    if not threshold:
        return True
    return iso_ge(str(event.get("ts") or ""), threshold)


def _pipeline_failure_evidence(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    reason = str(payload.get("reason") or payload.get("error") or payload.get("status") or "").strip()
    etype = str(event.get("type") or "")
    if not reason:
        reason = "artifact_write_rejected" if etype == "ArtifactWriteRejected" else "pipeline_phase_failed"
    return {
        "event_type": etype,
        "ts": event.get("ts") or "",
        "artifact": _artifact(event, payload),
        "pipeline": str(payload.get("pipeline") or ""),
        "phase": str(payload.get("phase") or ""),
        "reason": reason,
    }


def _pipeline_evidence_is_pending(payload: dict[str, Any]) -> bool:
    text = " ".join(
        str(payload.get(key) or "").strip().lower()
        for key in ("operation", "reason", "status", "error")
    )
    return any(marker in text for marker in PENDING_MARKERS)


def _is_runtime_stdout_artifact(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("auto_published") is True
        or str(payload.get("pipeline") or "") == "runtime-stdout-artifact"
    )


def _base_result(state: dict[str, Any], *, instance: object) -> dict[str, Any]:
    request = state.get("request", {}) or {}
    state_block = state.get("state", {}) or {}
    skill = request.get("skill") or ""
    canonical_skill = canonical_skill_id(skill, instance=instance)
    return {
        "ok": False,
        "status": "unknown",
        "reason": "unknown",
        "required": skill_requires_artifact_publication(skill, instance=instance),
        "skill": skill,
        "canonical_skill": canonical_skill,
        "cycle_id": state.get("cycle_id") or "",
        "threshold": state_block.get("dispatched_at") or state_block.get("opened_at") or "",
    }


def supervise_artifact_publication(
    state: dict[str, Any],
    *,
    events_path: Path,
    instance: object = "",
) -> dict[str, Any]:
    """Return the artifact lifecycle status for the dispatch state's cycle.

    The invariant is intentionally mechanical: a substantive skill may close as
    completed only when a cycle-local `ArtifactPublished` fact exists. Failed
    pipeline facts enrich the diagnosis, but a durable failure report artifact
    still satisfies the publication requirement.
    """
    result = _base_result(state, instance=instance)
    if not result["required"]:
        result.update({"ok": True, "status": "not_required", "reason": "artifact_not_required"})
        return result

    cycle_id = str(result.get("cycle_id") or "")
    if not cycle_id:
        result.update({"status": "blocked", "reason": "missing_cycle_id"})
        return result

    threshold = str(result.get("threshold") or "") or None
    pipeline_failure: dict[str, Any] | None = None
    pipeline_pending: dict[str, Any] | None = None
    for event in iter_jsonl_reverse(events_path):
        if event.get("cycle_id") != cycle_id:
            continue
        if not _event_after_threshold(event, threshold):
            continue

        etype = str(event.get("type") or "")
        payload = _payload(event)
        artifact = _artifact(event, payload)

        if etype == "ArtifactPublished" and artifact.startswith("blog/entries/"):
            if _is_runtime_stdout_artifact(payload):
                if pipeline_failure is None:
                    pipeline_failure = {
                        "event_type": etype,
                        "ts": event.get("ts") or "",
                        "artifact": artifact,
                        "pipeline": str(payload.get("pipeline") or "runtime-stdout-artifact"),
                        "phase": "",
                        "reason": "runtime_stdout_artifact_rejected",
                    }
                continue
            result.update(
                {
                    "ok": True,
                    "status": "published",
                    "reason": "artifact_published",
                    "artifact": artifact,
                    "artifact_published_at": event.get("ts") or "",
                    "source_skill": payload.get("source_skill") or payload.get("skill") or "",
                }
            )
            return result

        if etype == "ArtifactStanddownRecorded":
            status = str(payload.get("status") or "").strip().lower()
            if status == "standdown" and artifact:
                result.update(
                    {
                        "ok": True,
                        "status": "standdown",
                        "reason": str(payload.get("reason") or "principled_standdown"),
                        "artifact": artifact,
                        "artifact_published_at": event.get("ts") or "",
                        "source_skill": payload.get("source_skill") or payload.get("skill") or "",
                    }
                )
                return result

        if etype == "ArtifactWriteRejected" and pipeline_failure is None and pipeline_pending is None:
            pipeline_failure = _pipeline_failure_evidence(event, payload)
        elif etype == "PhaseCompleted" and _phase_ok(payload) is False and pipeline_failure is None and pipeline_pending is None:
            evidence = _pipeline_failure_evidence(event, payload)
            if _pipeline_evidence_is_pending(payload):
                pipeline_pending = evidence
            else:
                pipeline_failure = evidence

    if pipeline_failure:
        result.update(
            {
                "status": "blocked",
                "reason": "pipeline_blocked_before_publish",
                "pipeline_evidence": pipeline_failure,
            }
        )
        return result

    if pipeline_pending:
        result.update(
            {
                "status": "pending",
                "reason": "pipeline_pending_before_publish",
                "pipeline_evidence": pipeline_pending,
            }
        )
        return result

    result.update({"status": "blocked", "reason": "missing_artifact_published"})
    return result


def event_type_for_result(result: dict[str, Any]) -> str:
    if result.get("ok") and result.get("status") == "not_required":
        return "ArtifactSupervisionSkipped"
    if result.get("ok"):
        return "ArtifactSupervisionCompleted"
    return "ArtifactSupervisionBlocked"


def emit_artifact_supervision_result(result: dict[str, Any], *, actor: str) -> None:
    payload = {}
    for key, value in result.items():
        if key in {"ok", "artifact"} or value is None or value == "":
            continue
        payload[key] = value
    payload["ok"] = bool(result.get("ok"))
    emit_shadow_event(
        event_type_for_result(result),
        actor=actor,
        artifact=str(result.get("artifact") or "") or None,
        cycle_id=str(result.get("cycle_id") or "") or None,
        payload=payload,
    )
