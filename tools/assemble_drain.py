"""assemble_drain — drain assembly.pending queue (tkt-004 / R1=C).

**Module:** process open packages from the log fold; write done/failed only after relational step.
**Interface:** ``drain(log=…, relational_fn=…, budget=…) -> DrainResult``
**Seam:** predispatch injects ``drain_fn`` (budgeted open attempt); worker uses same module.
**Depth:** queue iteration + pens hide behind ``drain``; relational work is an injected adapter.

Locked: log sole truth; per package_id; done only after relational ok; failed clears open (R2=A).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import eventlog


@dataclass(frozen=True)
class RelationalOutcome:
    ok: bool
    reason: str = ""
    incerteza: str | None = None  # descriptive note for mentor; not a score


@dataclass(frozen=True)
class DrainResult:
    done: tuple[str, ...]
    failed: tuple[str, ...]
    skipped: tuple[str, ...]  # over budget
    incertezas: tuple[tuple[str, str], ...]  # (package_id, note)


def _default_relational(pkg: dict) -> RelationalOutcome:
    """v1 stub: descriptive pass — real Graph/Thread materialization deepens later (tkt-004).

    Still invoked *before* done so the order contract is real and injectable for tests.
    """
    return RelationalOutcome(ok=True, reason="stub-relational-pass")


def drain(
    *,
    log=eventlog.LOG,
    relational_fn: Callable[[dict], RelationalOutcome] | None = None,
    budget: int = 20,
    by: str | None = "assemble_drain",
) -> DrainResult:
    """Drain open assembly packages from the log fold (per package_id).

    For each package (up to ``budget``): run relational step → done or failed.
    Never writes done without a successful relational outcome.
    """
    if budget < 1:
        raise ValueError("budget must be >= 1")
    rel = relational_fn or _default_relational
    open_ = eventlog.assembly_pending_open(log=log)
    # stable order for tests / fairness
    items = [open_[k] for k in sorted(open_)]
    done: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    incertezas: list[tuple[str, str]] = []

    for i, pkg in enumerate(items):
        pid = pkg["package_id"]
        if i >= budget:
            skipped.append(pid)
            continue
        try:
            outcome = rel(pkg)
        except Exception as exc:  # noqa: BLE001 — package fails closed
            eventlog.mark_assembly_failed(
                pid, reason=f"relational raised: {type(exc).__name__}: {exc}", by=by, log=log,
            )
            failed.append(pid)
            continue
        if not isinstance(outcome, RelationalOutcome):
            eventlog.mark_assembly_failed(
                pid, reason="relational_fn returned non-RelationalOutcome", by=by, log=log,
            )
            failed.append(pid)
            continue
        if outcome.incerteza:
            incertezas.append((pid, outcome.incerteza))
        if outcome.ok:
            eventlog.mark_assembly_done(pid, by=by, log=log)
            done.append(pid)
        else:
            reason = outcome.reason.strip() if outcome.reason else "relational incomplete"
            eventlog.mark_assembly_failed(pid, reason=reason, by=by, log=log)
            failed.append(pid)

    return DrainResult(
        done=tuple(done),
        failed=tuple(failed),
        skipped=tuple(skipped),
        incertezas=tuple(incertezas),
    )
