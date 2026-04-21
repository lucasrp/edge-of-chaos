"""Telemetry helpers — passive writers, no LLM friction.

Append-only event logging to `logs/events.jsonl` plus targeted writes to the
`telemetry_snapshots` SQLite table. Readers (rollup scripts in tools/) digest
these into small JSON files that skills consume.

Design rules (issue #226):
- Writers MUST NOT prompt, decide, or call LLMs. Pure observation.
- Failures are swallowed — telemetry MUST NOT break the caller.
- Consumers never read raw events — always pre-digested rollups.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from hashlib import sha256
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import CURRENT_DISPATCH_FILE, EVENTS_FILE, SEARCH_DB_FILE, STATE_EVENTS_FILE  # noqa: E402

DB_PATH = SEARCH_DB_FILE
_LAST_SHADOW_HASH: str | None = None

# --- Price table (USD per 1M tokens). Missing models map to 0 cost rather than
# block the call; rollup flags unknown models separately.
# Keep this table small — update when new models are added to runtime routers.
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    # model: (input_per_1m, output_per_1m)
    "gpt-5.4":                 (5.00, 15.00),
    "gpt-5.4-pro":            (15.00, 60.00),
    "gpt-4.1-mini":            (0.40, 1.60),
    "gpt-4o":                  (2.50, 10.00),
    "gpt-4o-mini":             (0.15, 0.60),
    "text-embedding-3-small":  (0.02, 0.00),
    "text-embedding-3-large":  (0.13, 0.00),
    "grok-4.20-multi-agent-beta-0309": (5.00, 15.00),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return estimated cost in USD. Unknown models return 0.0."""
    price = _PRICE_PER_M.get(model)
    if price is None:
        return 0.0
    ti, to = price
    return round((tokens_in / 1_000_000) * ti + (tokens_out / 1_000_000) * to, 6)


def current_skill() -> str | None:
    """Best-effort current skill name. Reads env var set by skill runner."""
    return os.environ.get("ED_SKILL") or os.environ.get("CLAUDE_SKILL") or None


def current_beat() -> str | None:
    """Current heartbeat rotation number, if tracked by state/beat-rotation.json."""
    return os.environ.get("ED_BEAT") or None


def current_cycle_id() -> str | None:
    """Best-effort cycle id for heartbeat or user-triggered runs."""
    cycle_id = (
        os.environ.get("EDGE_CYCLE_ID")
        or os.environ.get("ED_CYCLE_ID")
        or os.environ.get("CLAUDE_CYCLE_ID")
    )
    if cycle_id:
        return cycle_id

    try:
        if CURRENT_DISPATCH_FILE.exists():
            state = json.loads(CURRENT_DISPATCH_FILE.read_text(encoding="utf-8"))
            state_block = state.get("state", {}) or {}
            if state_block.get("active"):
                file_cycle_id = state.get("cycle_id")
                if file_cycle_id:
                    return str(file_cycle_id)
    except Exception:
        pass

    beat = current_beat()
    if beat:
        return f"beat:{beat}"

    session_id = os.environ.get("EDGE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if session_id:
        return f"session:{session_id}"

    return None


def current_actor() -> str:
    """Best-effort logical emitter identity."""
    return (
        os.environ.get("EDGE_CODENAME")
        or os.environ.get("HOSTNAME")
        or os.environ.get("EDGE_ACTOR")
        or _detect_caller()
    )


def _append_event(event: dict[str, Any]) -> None:
    """Append a JSON line to EVENTS_FILE. Swallows all errors."""
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def emit_shadow_event(
    event_type: str,
    *,
    actor: str | None = None,
    artifact: str | None = None,
    cycle_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a normalized shadow event to state/events/log.jsonl."""
    global _LAST_SHADOW_HASH
    try:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "actor": actor or current_actor(),
            "payload": payload or {},
            "prev_hash": _LAST_SHADOW_HASH or "sha256:root",
        }
        if artifact:
            event["artifact"] = artifact
        if cycle_id or current_cycle_id():
            event["cycle_id"] = cycle_id or current_cycle_id()

        STATE_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(event, ensure_ascii=False)
        with open(STATE_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(raw + "\n")
        _LAST_SHADOW_HASH = f"sha256:{sha256(raw.encode('utf-8')).hexdigest()}"
    except Exception:
        pass


def log_event(event_type: str, **fields: Any) -> None:
    """Append a typed event to events.jsonl. Always includes ts + type."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "actor": fields.pop("actor", current_actor()),
    }
    event.update(fields)
    _append_event(event)
    emit_shadow_event(
        "LegacyTelemetryObserved",
        actor=_detect_caller(),
        cycle_id=fields.get("cycle_id"),
        artifact=fields.get("artifact"),
        payload={"legacy_type": event_type, **fields},
    )


def log_llm_call(
    *,
    router: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    caller: str | None = None,
    cost_usd: float | None = None,
    **extra: Any,
) -> None:
    """Telemetry for a single LLM call. Derives cost if not passed."""
    if cost_usd is None:
        cost_usd = estimate_cost_usd(model, tokens_in, tokens_out)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "llm_call",
        router=router,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        caller=caller or _detect_caller(),
        **extra,
    )


def log_run_step(
    run_kind: str,
    phase: str,
    status: str,
    *,
    run_id: str | None = None,
    **extra: Any,
) -> None:
    """Generic lifecycle event for deterministic runs and pipeline phases."""
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "run_step",
        run_kind=run_kind,
        phase=phase,
        status=status,
        run_id=run_id or current_cycle_id(),
        **extra,
    )


def log_render_produced(
    artifact: str | os.PathLike[str],
    *,
    source_template: str,
    hash_value: str,
    residual_count: int = 0,
    dry_run: bool = False,
    **extra: Any,
) -> None:
    """Record one rendered artifact and dual-write the canonical shadow fact."""
    artifact_str = os.fspath(artifact)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "render_produced",
        artifact=artifact_str,
        source_template=source_template,
        hash=hash_value,
        residual_count=residual_count,
        dry_run=dry_run,
        **extra,
    )
    emit_shadow_event(
        "RenderProduced",
        actor=_detect_caller(),
        artifact=artifact_str,
        cycle_id=extra.get("cycle_id"),
        payload={
            "source_template": source_template,
            "hash": hash_value,
            "residual_count": residual_count,
            "dry_run": dry_run,
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_install_applied(
    artifact: str | os.PathLike[str],
    *,
    source_template: str,
    action: str,
    kind: str,
    hash_value: str | None = None,
    dry_run: bool = False,
    **extra: Any,
) -> None:
    """Record one install-time materialization and dual-write the canonical fact."""
    artifact_str = os.fspath(artifact)
    payload = {
        "source_template": source_template,
        "action": action,
        "kind": kind,
        "dry_run": dry_run,
    }
    if hash_value:
        payload["hash"] = hash_value
    payload.update({k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}})

    log_event(
        "install_applied",
        artifact=artifact_str,
        source_template=source_template,
        action=action,
        kind=kind,
        hash=hash_value or "",
        dry_run=dry_run,
        **extra,
    )
    emit_shadow_event(
        "InstallApplied",
        actor=_detect_caller(),
        artifact=artifact_str,
        cycle_id=extra.get("cycle_id"),
        payload=payload,
    )


def log_install_check(
    check_id: str,
    status: str,
    *,
    detail: str,
    artifact: str | os.PathLike[str] | None = None,
    severity: str | None = None,
    **extra: Any,
) -> None:
    """Record one install verification check and its canonical shadow fact."""
    artifact_str = os.fspath(artifact) if artifact is not None else None
    log_event(
        "install_check",
        check_id=check_id,
        status=status,
        severity=severity or status,
        detail=detail,
        artifact=artifact_str or "",
        **extra,
    )
    emit_shadow_event(
        "InstallCheckObserved",
        actor=_detect_caller(),
        artifact=artifact_str,
        cycle_id=extra.get("cycle_id"),
        payload={
            "check_id": check_id,
            "status": status,
            "severity": severity or status,
            "detail": detail,
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_search_query(
    query: str,
    *,
    mode: str,
    status: str,
    result_count: int = 0,
    workflow_count: int = 0,
    doc_type: str | None = None,
    **extra: Any,
) -> None:
    """Structured search/workflow-recall event."""
    query_norm = re.sub(r"\s+", " ", query.lower()).strip()
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "search_query",
        query_norm=query_norm[:160],
        query_len=len(query.strip()),
        mode=mode,
        status=status,
        result_count=result_count,
        workflow_count=workflow_count,
        doc_type=doc_type or "",
        **extra,
    )


def log_source_query(
    query: str,
    *,
    intent: str,
    status: str,
    sources: list[str],
    total_results: int = 0,
    ok_sources: int = 0,
    failed_sources: int = 0,
    wildcard_source: str | None = None,
    **extra: Any,
) -> None:
    """Structured edge-sources query event."""
    query_norm = re.sub(r"\s+", " ", query.lower()).strip()
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "source_query",
        query_norm=query_norm[:160],
        query_len=len(query.strip()),
        intent=intent,
        status=status,
        sources=sources,
        source_count=len(sources),
        total_results=total_results,
        ok_sources=ok_sources,
        failed_sources=failed_sources,
        wildcard_source=wildcard_source,
        **extra,
    )


def _detect_caller() -> str:
    """Best-effort caller detection from sys.argv[0]."""
    try:
        return Path(sys.argv[0]).name
    except Exception:
        return "unknown"


def _classify_sql(statement: str) -> dict[str, Any]:
    """Classify SQL into a compact, low-cardinality telemetry shape."""
    cleaned = re.sub(r"\s+", " ", (statement or "").strip())
    if not cleaned:
        return {"should_log": False}

    upper = cleaned.upper()
    op = upper.split(" ", 1)[0]
    write = False

    if op == "WITH":
        if " INSERT INTO " in upper:
            op = "INSERT"
            write = True
        elif " UPDATE " in upper:
            op = "UPDATE"
            write = True
        elif " DELETE FROM " in upper:
            op = "DELETE"
            write = True
        elif " REPLACE INTO " in upper:
            op = "REPLACE"
            write = True
        else:
            op = "SELECT"
    elif op in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
        write = True
    elif op != "SELECT":
        return {"should_log": False}

    table = ""
    patterns = {
        "SELECT": r"\bFROM\s+([A-Za-z_][\w.]*)",
        "INSERT": r"\bINTO\s+([A-Za-z_][\w.]*)",
        "REPLACE": r"\bINTO\s+([A-Za-z_][\w.]*)",
        "UPDATE": r"\bUPDATE\s+([A-Za-z_][\w.]*)",
        "DELETE": r"\bFROM\s+([A-Za-z_][\w.]*)",
    }
    pattern = patterns.get(op)
    if pattern:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            table = match.group(1)

    return {
        "should_log": True,
        "op": op,
        "table": table,
        "write": write,
        "statement": cleaned[:160],
    }


def log_db_query(
    *,
    db_name: str,
    statement: str,
    latency_ms: int,
    ok: bool = True,
    rows: int | None = None,
    batch_size: int | None = None,
    error: str | None = None,
    caller: str | None = None,
    **extra: Any,
) -> None:
    """Telemetry for DB reads/writes. Ignores non-query/non-DML statements."""
    meta = _classify_sql(statement)
    if not meta.get("should_log"):
        return
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    event = {
        "db": db_name,
        "op": meta["op"],
        "table": meta["table"],
        "write": meta["write"],
        "latency_ms": latency_ms,
        "ok": ok,
        "statement": meta["statement"],
        "caller": caller or _detect_caller(),
    }
    if rows is not None and rows >= 0:
        event["rows"] = rows
    if batch_size is not None:
        event["batch_size"] = batch_size
    if error:
        event["error"] = error[:240]
    event.update(extra)
    log_event("db_query", **event)


def _ensure_telemetry_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS telemetry_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
            source TEXT NOT NULL,
            calls INTEGER DEFAULT 0,
            ok INTEGER DEFAULT 0,
            fail INTEGER DEFAULT 0,
            avg_ms INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            notes TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_snapshots(ts);
        CREATE INDEX IF NOT EXISTS idx_telemetry_source ON telemetry_snapshots(source);
    """)


def log_primitive_missing(
    source: str,
    *,
    operation: str | None = None,
    exit_code: int = 127,
    detail: str = "",
    **extra: Any,
) -> None:
    """Record that a declared primitive is missing or an operation is absent."""
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    event_type = "PrimitiveOperationMissingObserved" if exit_code == 77 else "PrimitiveMissingObserved"
    legacy_type = "primitive_operation_missing" if exit_code == 77 else "primitive_missing"
    log_event(
        legacy_type,
        source=source,
        operation=operation or "",
        exit_code=exit_code,
        detail=detail,
        **extra,
    )
    emit_shadow_event(
        event_type,
        actor=_detect_caller(),
        cycle_id=extra.get("cycle_id"),
        payload={
            "source": source,
            "operation": operation or "",
            "exit_code": exit_code,
            "detail": detail,
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_primitive_contract_written(
    source: str,
    *,
    meta_path: str | os.PathLike[str],
    status: str = "contract-only",
    hash_value: str | None = None,
    **extra: Any,
) -> None:
    """Record the contract-writing step for an on-demand primitive."""
    meta_path_str = os.fspath(meta_path)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "primitive_contract",
        source=source,
        meta_path=meta_path_str,
        status=status,
        hash=hash_value or "",
        **extra,
    )
    emit_shadow_event(
        "PrimitiveContractWritten",
        actor=_detect_caller(),
        artifact=meta_path_str,
        cycle_id=extra.get("cycle_id"),
        payload={
            "source": source,
            "status": status,
            **({"hash": hash_value} if hash_value else {}),
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_primitive_materialized(
    source: str,
    *,
    binary_path: str | os.PathLike[str],
    hash_value: str | None = None,
    **extra: Any,
) -> None:
    """Record that a primitive executable became materialized and runnable."""
    binary_path_str = os.fspath(binary_path)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "primitive_materialized",
        source=source,
        binary_path=binary_path_str,
        hash=hash_value or "",
        **extra,
    )
    emit_shadow_event(
        "PrimitiveMaterialized",
        actor=_detect_caller(),
        artifact=binary_path_str,
        cycle_id=extra.get("cycle_id"),
        payload={
            "source": source,
            **({"hash": hash_value} if hash_value else {}),
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_primitive_probe_completed(
    source: str,
    *,
    command: list[str],
    exit_code: int,
    ok: bool,
    **extra: Any,
) -> None:
    """Record the probe step that validates a primitive contract or executable."""
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "primitive_probe",
        source=source,
        command=command,
        exit_code=exit_code,
        ok=ok,
        **extra,
    )
    emit_shadow_event(
        "PrimitiveProbeCompleted",
        actor=_detect_caller(),
        cycle_id=extra.get("cycle_id"),
        payload={
            "source": source,
            "command": command,
            "exit_code": exit_code,
            "ok": ok,
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_primitive_manifest_updated(
    source: str,
    *,
    manifest_path: str | os.PathLike[str],
    status: str,
    **extra: Any,
) -> None:
    """Record that the primitive lifecycle manifest was updated."""
    manifest_path_str = os.fspath(manifest_path)
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "primitive_manifest",
        source=source,
        manifest_path=manifest_path_str,
        status=status,
        **extra,
    )
    emit_shadow_event(
        "PrimitiveManifestUpdated",
        actor=_detect_caller(),
        artifact=manifest_path_str,
        cycle_id=extra.get("cycle_id"),
        payload={
            "source": source,
            "status": status,
            **{k: v for k, v in extra.items() if k not in {"cycle_id", "artifact"}},
        },
    )


def log_primitive_call(
    source: str,
    *,
    ok: bool,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    notes: dict[str, Any] | None = None,
) -> None:
    """Insert one row into telemetry_snapshots per primitive call.

    Called by edge-sources/edge-x/edge-hn/etc. as a side-effect. All errors
    swallowed — telemetry never breaks the primitive.
    """
    try:
        log_event(
            "primitive_call",
            source=source,
            ok=ok,
            latency_ms=int(latency_ms),
            cost_usd=float(cost_usd),
            notes=notes or {},
            skill=current_skill(),
            beat=current_beat(),
        )
        if not DB_PATH.exists():
            return
        conn = sqlite3.connect(str(DB_PATH), timeout=2.0)
        try:
            _ensure_telemetry_table(conn)
            conn.execute(
                """
                INSERT INTO telemetry_snapshots
                (source, calls, ok, fail, avg_ms, cost_usd, notes)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    1 if ok else 0,
                    0 if ok else 1,
                    int(latency_ms),
                    float(cost_usd),
                    json.dumps(notes or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


@contextmanager
def time_primitive(source: str, notes: dict[str, Any] | None = None):
    """Context manager that times a primitive block and logs success/failure.

    Usage:
        with time_primitive("x", notes={"q": query}):
            ...call X API...
    """
    t0 = time.monotonic()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        dt_ms = int((time.monotonic() - t0) * 1000)
        log_primitive_call(source, ok=ok, latency_ms=dt_ms, notes=notes)


def log_workflow_transition(
    slug: str,
    from_state: str,
    to_state: str,
    *,
    approved_by: str | None = None,
    **extra: Any,
) -> None:
    """Workflow lifecycle event: claim → cluster → draft → approved → cited → broken → healed → retired."""
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        "workflow_transition",
        slug=slug,
        **{"from": from_state, "to": to_state},
        approved_by=approved_by,
        **extra,
    )


def log_resolution(
    *,
    obj_type: str,  # claim | friction | workflow_broken | issue | thread
    obj_id: str,
    opened_at: str | None,
    resolution: str,
    **extra: Any,
) -> None:
    """Time-to-resolution event. Duration derived from opened_at if present."""
    duration_h: float | None = None
    if opened_at:
        try:
            start = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            duration_h = round((now - start).total_seconds() / 3600.0, 2)
        except Exception:
            duration_h = None
    extra.setdefault("skill", current_skill())
    extra.setdefault("beat", current_beat())
    log_event(
        f"{obj_type}_resolved",
        obj_type=obj_type,
        id=obj_id,
        opened_at=opened_at,
        duration_h=duration_h,
        resolution=resolution,
        **extra,
    )


def log_operator_correction(
    *,
    session_id: str,
    trigger: str,
    category: str,
    **extra: Any,
) -> None:
    """Operator correction event (scope_drift | wrong_tool | over_engineering | other)."""
    log_event(
        "operator_correction",
        session_id=session_id,
        trigger=trigger,
        category=category,
        **extra,
    )


__all__ = [
    "log_event",
    "log_llm_call",
    "log_primitive_contract_written",
    "log_primitive_call",
    "log_primitive_manifest_updated",
    "log_primitive_materialized",
    "log_primitive_missing",
    "log_primitive_probe_completed",
    "time_primitive",
    "log_workflow_transition",
    "log_resolution",
    "log_operator_correction",
    "estimate_cost_usd",
    "current_skill",
    "current_beat",
]
