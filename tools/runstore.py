"""runstore — durable, CONTENT-ADDRESSED record of internal measurement runs (slice S3a, for R8).

ADR-0006: the append-only eventlog is the ONLY durable source of truth. A measurement run is recorded
as a `run.recorded` event whose payload carries {run_id, values, address}, where `address` =
sha256(canonical {run_id, values}). The internal-evidence ref (S3/R8) is (address, metric, value): the
ADDRESS is what the ref commits to, so resolution returns ONLY a record whose RECOMPUTED address equals
the cited address. A forged or tampered record (any different values, or a different run_id) has a
different address and therefore cannot satisfy a cited address without a sha256 collision — true
content-addressing, not a self-consistent checksum. The eventlog is the store; a published-Artefato blob
is transient/prunable and is never consulted, so pruning/editing an Artefato can neither alter nor break
verification. Reads fail CLOSED (None / (False, reason)); the write contract raises on malformed input.
"""
import hashlib
import json
import math

import eventlog

RUN_EVENT = "run.recorded"


def _canonical(run_id, values) -> str:
    # allow_nan=False: NaN/Infinity are not valid evidence and must never serialize into the address.
    return json.dumps({"run_id": run_id, "values": values},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_address(run_id, values) -> str:
    """The content address: sha256 over the canonical {run_id, values}. Binds BOTH so a record only
    resolves under its own true address."""
    return hashlib.sha256(_canonical(run_id, values).encode()).hexdigest()


def _validate(run_id, values):
    """WRITE-side contract: run_id a non-empty str; values a non-empty flat dict[str, finite non-bool
    number]. Raises ValueError on any violation (the caller is internal code recording its own run)."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(values, dict) or not values:
        raise ValueError("values must be a non-empty dict of metric->number")
    for k, v in values.items():
        if not isinstance(k, str):
            raise ValueError(f"metric name must be a string, got {k!r}")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"value for {k!r} must be a non-bool number, got {v!r}")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"value for {k!r} must be finite, got {v!r}")


def record_run(run_id, values, log=eventlog.LOG):
    """Record a measurement run as a content-addressed append-only event. Returns its content ADDRESS
    (the handle an internal-evidence ref cites). Raises ValueError on malformed input."""
    _validate(run_id, values)
    address = content_address(run_id, values)
    eventlog.append(RUN_EVENT, run_id, {"run_id": run_id, "values": values, "address": address}, log=log)
    return address


def resolve(address, log=eventlog.LOG):
    """Return the recorded payload whose RECOMPUTED content address equals `address`, or None. Forgery-
    and tamper-resistant: a record with any altered run_id/values has a different address and cannot
    match a cited one. Never raises (a broken/degraded log → None, fail-closed)."""
    if not isinstance(address, str) or not address:
        return None
    try:
        events = eventlog.read(types=[RUN_EVENT], log=log)
    except Exception:  # noqa: BLE001 — a broken log is "unresolved", never a crash
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        p = ev.get("payload")
        if not (isinstance(p, dict) and isinstance(p.get("run_id"), str)
                and isinstance(p.get("values"), dict)):
            continue
        try:
            _validate(p["run_id"], p["values"])   # READ-side: re-apply the write contract so a directly-
            #                                       appended schema-invalid record (bool/string/NaN/...)
            #                                       can never resolve and attest (Codex S3a #2).
            if content_address(p["run_id"], p["values"]) == address:
                return p
        except (ValueError, TypeError):
            continue  # malformed / non-serializable values → not a valid record, fail-closed
    return None


def attest_value(address, metric, value, log=eventlog.LOG):
    """R8 internal-evidence check: (True, "ok") iff `address` resolves to an intact content-addressed
    record AND its `metric` equals `value`. Fail-closed (False, reason) on a non-numeric cited value /
    unresolved address / missing metric / value mismatch. The internal-evidence ref is (address, metric,
    value)."""
    # the CITED value must itself be a finite non-bool number — else `True == 1` / NaN games could
    # satisfy a numeric ref (Codex S3a #2).
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
            isinstance(value, float) and not math.isfinite(value)):
        return False, f"cited value must be a finite non-bool number, got {value!r}"
    # the cited metric must be a non-empty string — an unhashable metric (list/dict) would raise on the
    # `in` membership check below; fail closed instead of crashing (Codex S3a #3).
    if not isinstance(metric, str) or not metric:
        return False, f"cited metric must be a non-empty string, got {metric!r}"
    run = resolve(address, log=log)
    if run is None:
        return False, f"address {address!r} does not resolve to a recorded run"
    values = run.get("values", {})
    if metric not in values:
        return False, f"metric {metric!r} not recorded at {address!r}"
    recorded = values[metric]
    if recorded != value:
        return False, f"value mismatch for {metric!r}: cited {value!r} != recorded {recorded!r}"
    return True, "ok"
