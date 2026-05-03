from __future__ import annotations

import uuid
from dataclasses import dataclass

from .config import RuntimeConfig, ensure_runtime_dirs
from .context import ContextPacket, assemble_context
from .ledger import Ledger
from .reports import build_blog, draft_report, finalize_report
from .reviewers import adversarial_review, context_readiness, feynman_review, general_review
from .search import broad_search
from .threads import rebuild_digest, thread_id_from_review, update_thread
from .util import now_iso


@dataclass
class BeatResult:
    cycle_id: str
    report_path: str
    thread_id: str
    status: str


def _ready_context(packet: ContextPacket, ledger: Ledger) -> tuple[str, dict]:
    last = {}
    for attempt in [1, 2]:
        review = context_readiness(packet, attempt=attempt)
        ledger.append("ContextReadinessReviewed", attempt=attempt, status=review.status, reviewer=review.reviewer, data=review.data)
        last = review.data
        if review.status == "pass":
            return thread_id_from_review(review.data, packet.request), review.data
        if attempt == 1:
            ledger.append("ContextReadinessRepairAttempted", instructions=review.data.get("repair_instructions") or [])
    return thread_id_from_review(last, packet.request), last


def run_beat(config: RuntimeConfig, *, kind: str, request: str = "") -> BeatResult:
    ensure_runtime_dirs(config)
    ledger = Ledger(config.ledger_path)
    cycle_id = f"cycle-{now_iso()}-{uuid.uuid4().hex[:8]}"
    ledger.append("CycleOpened", cycle_id=cycle_id, kind=kind, request=request)

    packet = assemble_context(config, ledger, kind=kind, request=request)
    ledger.append("DeltaPrepared", cycle_id=cycle_id, observations=len(packet.observations), threads=len(packet.thread_candidates), reports=len(packet.report_candidates))

    thread_id, readiness = _ready_context(packet, ledger)
    searches = broad_search(config, packet)
    ledger.append("BroadSearchCompleted", cycle_id=cycle_id, sources=sorted({result.source for result in searches}), results=len(searches))

    draft = draft_report(packet, searches, thread_id)
    reviews = [
        adversarial_review(draft),
        general_review(draft, packet),
        feynman_review(draft),
    ]
    for review in reviews:
        ledger.append("ReportReviewed", cycle_id=cycle_id, reviewer=review.reviewer, status=review.status, summary=review.summary, data=review.data)

    report_path = finalize_report(config, packet=packet, draft=draft, reviews=reviews, thread_id=thread_id)
    ledger.append("ReportWritten", cycle_id=cycle_id, path=str(report_path), thread_id=thread_id)

    thread_path = update_thread(
        config,
        thread_id=thread_id,
        title=str(((readiness.get("primary_thread") or {}).get("title")) or thread_id),
        report_path=report_path,
        summary=f"{kind} beat: {packet.request}",
        decisions=["Keep context absorption and reviews in the runtime rite."],
        next_steps=["Use the next beat to deepen this thread with more observed context."],
    )
    ledger.append("ThreadUpdated", cycle_id=cycle_id, thread_id=thread_id, path=str(thread_path))
    digest = rebuild_digest(config)
    ledger.append("DigestRebuilt", cycle_id=cycle_id, path=str(digest))
    index = build_blog(config)
    ledger.append("BlogBuilt", cycle_id=cycle_id, path=str(index))
    ledger.append("CycleClosed", cycle_id=cycle_id, status="completed")
    return BeatResult(cycle_id=cycle_id, report_path=str(report_path), thread_id=thread_id, status="completed")
