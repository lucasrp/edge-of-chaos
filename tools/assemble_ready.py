"""assemble_ready — Assemble wake-readiness bar (tkt-002 / S30.A1).

**Module:** one deep interface for "is the cortex ready for wake?"
**Interface:** ``ready(log=…) -> ReadyReport``; ``AssembleNotReady`` when the gate fails.
**Seam:** predispatch injects ``ready_fn`` (default: this module); not a grounding annotation.
**Depth:** checklist bits (pending drain, relational, …) hide behind ``ready``.

Operator (mentor 2026-07-13): Assemble makes Edge ready for wake; quality > latency; bar
blocks wake. Log is sole source of truth — pending queue is log events (tkt-003), per-item
+ seq high-water (tkt-004 decision). Graph is projection only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import eventlog

# Stable miss codes — contract for tests and wake DARK text (do not rename lightly).
CODE_BAR_NOT_IMPLEMENTED = "ASSEMBLE_BAR_NOT_IMPLEMENTED"
CODE_PENDING_DRAIN = "PENDING_DRAIN"
CODE_RELATIONAL_ACT = "RELATIONAL_ACT"
CODE_PACKAGE = "PACKAGE"
CODE_EMPLOYMENT = "EMPLOYMENT"
CODE_PROJECTIONS = "PROJECTIONS"


@dataclass(frozen=True)
class Miss:
    code: str
    detail: str


@dataclass(frozen=True)
class ReadyReport:
    ok: bool
    misses: tuple[Miss, ...]
    seq: int | None = None


class AssembleNotReady(RuntimeError):
    """Wake aborted: Assemble readiness bar failed (quality > latency)."""

    def __init__(self, report: ReadyReport):
        self.report = report
        if report.misses:
            parts = [f"{m.code}: {m.detail}" for m in report.misses]
            body = "; ".join(parts)
        else:
            body = "(no codes)"
        super().__init__(f"assemble not ready: {body}")


def _log_high_water(log) -> int | None:
    try:
        events = eventlog.read(log=log)
    except Exception:
        return None
    if not events:
        return 0
    seqs = [e.get("seq") for e in events if isinstance(e.get("seq"), int)]
    return max(seqs) if seqs else 0


def check_pending_drain(*, log=eventlog.LOG) -> Miss | None:
    """PENDING_DRAIN: open assembly.* pending items in the log fold (per package_id)."""
    try:
        open_ = eventlog.assembly_pending_open(log=log)
    except Exception as exc:  # noqa: BLE001
        return Miss(
            code=CODE_PENDING_DRAIN,
            detail=f"could not fold assembly pending: {type(exc).__name__}: {exc}",
        )
    if not open_:
        return None
    ids = sorted(open_)
    preview = ", ".join(ids[:5])
    more = f" (+{len(ids) - 5} more)" if len(ids) > 5 else ""
    return Miss(
        code=CODE_PENDING_DRAIN,
        detail=f"{len(ids)} package(s) still open in log: {preview}{more}",
    )


def check_relational_act(*, log=eventlog.LOG) -> Miss | None:
    """Optional future bit (incerto/Threads). Default path: relational work is part of
    draining each package — ``assembly.done`` is only written after that work (tkt-004).
    Empty open queue ⇒ relational complete for the currency window.
    """
    return None


def _default_checks(*, log) -> list[Callable[[], Miss | None]]:
    # Pending open set is the bar: per package_id on the log (sole truth). seq is audit only.
    return [
        lambda: check_pending_drain(log=log),
    ]


def ready(*, log=eventlog.LOG, checks: Iterable[Callable[[], Miss | None]] | None = None) -> ReadyReport:
    """Fail-closed Assemble readiness for wake. Never raises for missing bar pieces — reports misses.

    Default checks: pending drain only (log fold). Relational work is part of marking
    ``assembly.done`` per package (tkt-004 worker), not a second default miss.
    Inject ``checks`` for hermetic tests. ``seq`` is log high-water (audit), not a substitute
    for per-item drain.
    """
    seq = _log_high_water(log)
    misses: list[Miss] = []
    chain = list(checks) if checks is not None else _default_checks(log=log)
    for check in chain:
        try:
            miss = check()
        except Exception as exc:  # noqa: BLE001 — checklist item fails closed as a miss
            misses.append(Miss(
                code="CHECK_RAISED",
                detail=f"{type(exc).__name__}: {exc}",
            ))
            continue
        if miss is not None:
            misses.append(miss)
    return ReadyReport(ok=not misses, misses=tuple(misses), seq=seq)


def assert_ready(*, log=eventlog.LOG, checks=None) -> ReadyReport:
    """Raise AssembleNotReady when not ready; return the report when ok."""
    report = ready(log=log, checks=checks)
    if not report.ok:
        raise AssembleNotReady(report)
    return report
