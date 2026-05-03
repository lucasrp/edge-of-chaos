"""Structured runtime protocol compiler/executor helpers for pre/post skill."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    ASSET_INVENTORY_FILE,
    POSTFLIGHT_COMPILED_FILE,
    POSTFLIGHT_PROTOCOL_FILE,
    CAPABILITIES_CONFIG_FILE,
    PREFLIGHT_COMPILED_FILE,
    PREFLIGHT_PROTOCOL_FILE,
    PRIMITIVES_STATUS_FILE,
    SOURCES_MANIFEST_FILE,
)
from .capability_runtime import build_capability_status, build_source_bindings  # noqa: E402
from .telemetry import emit_shadow_event, log_event  # noqa: E402

PROTOCOL_VERSION = 1
_ALLOWED_KINDS: dict[str, set[str]] = {
    "preflight": {
        "health.snapshot",
        "inbox.snapshot",
        "claude.sessions.digest",
        "open_gaps.refresh",
        "self_healing.primitives",
        "primitives.status",
        "capabilities.status",
        "asset_inventory.status",
        "source.bindings",
        "signals.context",
        "corpus.lookup",
        "queue.status",
        "onboarding.status",
        "capability.invoke",
        "capability.probe",
    },
    "postflight": {
        "validate.recent",
        "open_gaps.refresh",
        "pipeline_state.refresh",
        "primitives.status",
        "capabilities.status",
        "source_affordance.digest",
        "curation.digest",
        "briefing.refresh",
        "cycle_health.observe",
        "async_inbox.respond",
        "capability.invoke",
        "capability.probe",
    },
}


class ProtocolCompileError(RuntimeError):
    """The runtime protocol source is invalid or cannot be compiled."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        return _hash_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return "unreadable"


def _hash_primitives_binding_inputs(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _hash_file(path)
    sources = payload.get("sources") if isinstance(payload, dict) else []
    if not isinstance(sources, list):
        sources = []
    relevant = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        relevant.append(
            {
                "name": item.get("name"),
                "roles": list(item.get("roles") or []),
                "primary": bool(item.get("primary")),
                "effective_status": item.get("effective_status"),
                "problems": list(item.get("problems") or []),
                "manifest_status": item.get("manifest_status"),
                "binary_exists": bool(item.get("binary_exists")),
                "binary_path": item.get("binary_path"),
            }
        )
    relevant.sort(key=lambda item: str(item.get("name") or ""))
    return _hash_text(json.dumps({"sources": relevant}, sort_keys=True, ensure_ascii=False))


def _protocol_paths(protocol: str) -> tuple[Path, Path]:
    if protocol == "preflight":
        return PREFLIGHT_PROTOCOL_FILE, PREFLIGHT_COMPILED_FILE
    if protocol == "postflight":
        return POSTFLIGHT_PROTOCOL_FILE, POSTFLIGHT_COMPILED_FILE
    raise ProtocolCompileError(f"unknown protocol: {protocol}")


def _read_compiled(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_notes(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProtocolCompileError(f"{label} must be a list of natural-language strings")
    notes: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            notes.append(text)
    return notes


def _known_capability_rows() -> dict[str, dict[str, Any]]:
    payload = build_capability_status()
    rows = payload.get("capabilities") or []
    return {
        str(item.get("name") or "").strip(): item
        for item in rows
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }


def _dependency_hashes(protocol: str, payload: dict[str, Any]) -> dict[str, str]:
    raw_steps = payload.get("procedures")
    if raw_steps is None:
        raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raw_steps = []
    kinds = {
        str(item.get("kind") or "").strip()
        for item in raw_steps
        if isinstance(item, dict)
    }
    dependencies: dict[str, str] = {}
    if kinds & {"capability.invoke", "capability.probe", "source.bindings"}:
        dependencies[str(CAPABILITIES_CONFIG_FILE)] = _hash_file(CAPABILITIES_CONFIG_FILE)
    if "source.bindings" in kinds:
        dependencies[str(SOURCES_MANIFEST_FILE)] = _hash_file(SOURCES_MANIFEST_FILE)
        dependencies[str(PRIMITIVES_STATUS_FILE)] = _hash_primitives_binding_inputs(PRIMITIVES_STATUS_FILE)
    if "asset_inventory.status" in kinds:
        dependencies[str(ASSET_INVENTORY_FILE)] = _hash_file(ASSET_INVENTORY_FILE)
    return dependencies


def _normalize_step(
    protocol: str,
    raw_step: Any,
    *,
    index: int,
    capability_rows: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(raw_step, dict):
        raise ProtocolCompileError(f"{protocol} procedures[{index}] must be a mapping")
    allowed = _ALLOWED_KINDS[protocol]
    kind = str(raw_step.get("kind") or "").strip()
    if not kind:
        raise ProtocolCompileError(f"{protocol} procedures[{index}] is missing kind")
    if kind not in allowed:
        raise ProtocolCompileError(f"{protocol} procedures[{index}] uses unknown kind: {kind}")

    step_id = str(raw_step.get("id") or kind.replace(".", "-")).strip()
    if not step_id:
        raise ProtocolCompileError(f"{protocol} procedures[{index}] is missing id")

    step: dict[str, Any] = {
        "id": step_id,
        "kind": kind,
    }
    note = str(raw_step.get("note") or "").strip()
    if note:
        step["note"] = note
    warnings: list[str] = []

    if kind in {"capability.invoke", "capability.probe"}:
        capability = str(raw_step.get("capability") or "").strip()
        if not capability:
            raise ProtocolCompileError(f"{protocol} procedures[{index}] requires capability")
        if capability_rows is None:
            capability_rows = _known_capability_rows()
        if capability not in capability_rows:
            raise ProtocolCompileError(f"{protocol} procedures[{index}] references unknown capability: {capability}")
        step["capability"] = capability
        if kind == "capability.invoke":
            argv = raw_step.get("argv") or []
            if argv is None:
                argv = []
            if not isinstance(argv, list):
                raise ProtocolCompileError(f"{protocol} procedures[{index}] argv must be a list")
            step["argv"] = [str(item) for item in argv if str(item).strip()]
        capability_row = capability_rows.get(capability) or {}
        effective_status = str(capability_row.get("effective_status") or "").strip()
        if effective_status in {"degraded", "broken"}:
            warnings.append(f"{capability} currently {effective_status}")

    if kind == "signals.context":
        scope = str(raw_step.get("scope") or "routing").strip() or "routing"
        if scope not in {"routing", "skill", "all"}:
            raise ProtocolCompileError(f"{protocol} procedures[{index}] signals.context scope must be routing, skill, or all")
        step["scope"] = scope
        if raw_step.get("query") is not None:
            step["query"] = str(raw_step.get("query") or "").strip()
        try:
            step["limit"] = max(1, int(raw_step.get("limit") or 12))
        except (TypeError, ValueError) as exc:
            raise ProtocolCompileError(f"{protocol} procedures[{index}] signals.context limit must be an integer") from exc
        step["refresh"] = bool(raw_step.get("refresh", False))

    if kind == "source.bindings":
        payload = build_source_bindings()
        step["source_bindings"] = [
            {
                "source": item.get("source"),
                "capability": item.get("capability"),
                "binding_status": item.get("binding_status"),
                "binding_mode": item.get("binding_mode"),
                "primary": bool(item.get("primary")),
                "roles": list(item.get("roles") or []),
                "warning": item.get("warning") or "",
            }
            for item in payload.get("bindings") or []
            if isinstance(item, dict)
        ]
        for item in payload.get("warnings") or []:
            source = str(item.get("source") or "").strip()
            warning = str(item.get("warning") or "").strip()
            capability = str(item.get("capability") or "").strip()
            if source and warning:
                warnings.append(f"{source}: {warning}{f' ({capability})' if capability else ''}")

    return step, warnings


def compile_protocol(protocol: str) -> dict[str, Any]:
    source_path, compiled_path = _protocol_paths(protocol)
    if not source_path.exists():
        raise ProtocolCompileError(f"{source_path} not found")

    source_text = source_path.read_text(encoding="utf-8")
    source_hash = _hash_text(source_text)
    try:
        payload = yaml.safe_load(source_text) or {}
    except yaml.YAMLError as exc:
        raise ProtocolCompileError(f"{source_path.name} is invalid YAML: {exc}") from exc

    if not isinstance(payload, dict):
        raise ProtocolCompileError(f"{source_path.name} must contain a mapping at the root")

    declared_protocol = str(payload.get("protocol") or protocol).strip() or protocol
    if declared_protocol != protocol:
        raise ProtocolCompileError(f"{source_path.name} declares protocol={declared_protocol}, expected {protocol}")

    context_notes = _normalize_notes(payload.get("context_notes"), label="context_notes")
    operator_notes = _normalize_notes(payload.get("operator_notes"), label="operator_notes")
    raw_steps = payload.get("procedures")
    if raw_steps is None:
        raw_steps = payload.get("steps")
    if raw_steps is None:
        raw_steps = []
    if not isinstance(raw_steps, list):
        raise ProtocolCompileError("procedures must be a list")

    needs_capabilities = any(
        isinstance(item, dict) and str(item.get("kind") or "").strip() in {"capability.invoke", "capability.probe"}
        for item in raw_steps
    )
    capability_rows = _known_capability_rows() if needs_capabilities else None

    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw_step in enumerate(raw_steps):
        step, step_warnings = _normalize_step(
            protocol,
            raw_step,
            index=index,
            capability_rows=capability_rows,
        )
        steps.append(step)
        warnings.extend(step_warnings)

    dependency_hashes = _dependency_hashes(protocol, payload)
    compiled: dict[str, Any] = {
        "version": int(payload.get("version") or PROTOCOL_VERSION),
        "protocol": protocol,
        "source_path": str(source_path),
        "compiled_path": str(compiled_path),
        "source_hash": source_hash,
        "dependency_hashes": dependency_hashes,
        "compiled_at": _now_iso(),
        "context_notes": context_notes,
        "operator_notes": operator_notes,
        "procedures": steps,
        "warnings": warnings,
    }
    compiled_hash = _hash_text(json.dumps(compiled, sort_keys=True, ensure_ascii=False))
    compiled["compiled_hash"] = compiled_hash

    compiled_path.parent.mkdir(parents=True, exist_ok=True)
    compiled_path.write_text(json.dumps(compiled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    emit_shadow_event(
        "ProtocolCompiled",
        actor="protocol-runtime",
        artifact=str(compiled_path),
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        payload={
            "protocol": protocol,
            "source_path": str(source_path),
            "source_hash": source_hash,
            "compiled_hash": compiled_hash,
            "warning_count": len(warnings),
            "procedure_total": len(steps),
        },
    )
    log_event(
        "protocol_compile",
        actor="protocol-runtime",
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        protocol=protocol,
        source_hash=source_hash,
        compiled_hash=compiled_hash,
        warning_count=len(warnings),
        procedure_total=len(steps),
        status="completed",
    )
    return compiled


def ensure_compiled_protocol(protocol: str) -> dict[str, Any]:
    source_path, compiled_path = _protocol_paths(protocol)
    if not source_path.exists():
        raise ProtocolCompileError(f"{source_path} not found")
    source_text = source_path.read_text(encoding="utf-8")
    current_source_hash = _hash_text(source_text)
    try:
        payload = yaml.safe_load(source_text) or {}
    except yaml.YAMLError:
        payload = {}
    current_dependency_hashes = _dependency_hashes(protocol, payload if isinstance(payload, dict) else {})
    compiled = _read_compiled(compiled_path)
    if (
        compiled
        and compiled.get("source_hash") == current_source_hash
        and compiled.get("protocol") == protocol
        and (compiled.get("dependency_hashes") or {}) == current_dependency_hashes
    ):
        return compiled

    reason = "missing_compiled"
    previous_source_hash = ""
    if compiled is not None:
        previous_source_hash = str(compiled.get("source_hash") or "")
        if previous_source_hash and previous_source_hash != current_source_hash:
            reason = "source_hash_changed"
        elif (compiled.get("dependency_hashes") or {}) != current_dependency_hashes:
            reason = "dependency_hash_changed"
        else:
            reason = "invalid_compiled"

    emit_shadow_event(
        "ProtocolDriftObserved",
        actor="protocol-runtime",
        artifact=str(source_path),
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        payload={
            "protocol": protocol,
            "reason": reason,
            "source_path": str(source_path),
            "compiled_path": str(compiled_path),
            "previous_source_hash": previous_source_hash,
            "current_source_hash": current_source_hash,
        },
    )
    log_event(
        "protocol_drift",
        actor="protocol-runtime",
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        protocol=protocol,
        reason=reason,
        previous_source_hash=previous_source_hash,
        current_source_hash=current_source_hash,
    )
    return compile_protocol(protocol)


def emit_protocol_step_observed(
    protocol: str,
    step: dict[str, Any],
    *,
    status: str,
    detail: str,
    satisfied: bool,
    cycle_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "protocol": protocol,
        "protocol_stage": "pre_skill" if protocol == "preflight" else "post_skill",
        "step_id": step.get("id"),
        "kind": step.get("kind"),
        "status": status,
        "satisfied": satisfied,
        "detail": detail,
    }
    if step.get("note"):
        payload["note"] = step.get("note")
    if step.get("capability"):
        payload["capability"] = step.get("capability")
    if extra:
        payload.update(extra)
    emit_shadow_event(
        "ProtocolStepObserved",
        actor="protocol-runtime",
        cycle_id=cycle_id or os.environ.get("EDGE_CYCLE_ID"),
        payload=payload,
    )
    log_event(
        "protocol_step",
        actor="protocol-runtime",
        cycle_id=cycle_id or os.environ.get("EDGE_CYCLE_ID"),
        **payload,
    )
    if not satisfied:
        emit_shadow_event(
            "ProtocolStepAttentionRequired",
            actor="protocol-runtime",
            cycle_id=cycle_id or os.environ.get("EDGE_CYCLE_ID"),
            payload=payload | {"priority": "high"},
        )
        log_event(
            "protocol_step_attention",
            actor="protocol-runtime",
            cycle_id=cycle_id or os.environ.get("EDGE_CYCLE_ID"),
            priority="high",
            **payload,
        )


def protocol_context(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol": protocol.get("protocol"),
        "version": protocol.get("version"),
        "source_path": protocol.get("source_path"),
        "compiled_path": protocol.get("compiled_path"),
        "source_hash": protocol.get("source_hash"),
        "compiled_hash": protocol.get("compiled_hash"),
        "compiled_at": protocol.get("compiled_at"),
        "context_notes": list(protocol.get("context_notes") or []),
        "operator_notes": list(protocol.get("operator_notes") or []),
        "warnings": list(protocol.get("warnings") or []),
        "steps": [
            {
                "id": step.get("id"),
                "kind": step.get("kind"),
                **({"note": step.get("note")} if step.get("note") else {}),
            }
            for step in (protocol.get("procedures") or [])
        ],
        "warning_count": len(protocol.get("warnings") or []),
    }


__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolCompileError",
    "compile_protocol",
    "emit_protocol_step_observed",
    "ensure_compiled_protocol",
    "protocol_context",
]
