from __future__ import annotations

import uuid
from dataclasses import dataclass

from .config import RuntimeConfig, ensure_runtime_dirs
from .context import ContextPacket, assemble_context
from .ledger import Ledger
from .reports import build_blog, draft_report, finalize_report
from .reviewers import adversarial_review, context_readiness, feynman_review, general_review, method_review
from .rite import verify_rite
from .search import broad_search
from .threads import primary_thread_from_review, rebuild_digest, thread_id_from_review, update_thread
from .util import now_iso


@dataclass
class BeatResult:
    cycle_id: str
    report_path: str
    thread_id: str
    status: str


def _ready_context(packet: ContextPacket, record) -> tuple[str, dict]:
    last = {}
    for attempt in [1, 2]:
        review = context_readiness(packet, attempt=attempt)
        record("ContextReadinessReviewed", attempt=attempt, status=review.status, reviewer=review.reviewer, data=review.data)
        last = review.data
        if review.status == "pass":
            return thread_id_from_review(review.data, packet.request), review.data
        if attempt == 1:
            record("ContextReadinessRepairAttempted", instructions=review.data.get("repair_instructions") or [])
    return thread_id_from_review(last, packet.request), last


def run_beat(config: RuntimeConfig, *, kind: str, request: str = "") -> BeatResult:
    ensure_runtime_dirs(config)
    ledger = Ledger(config.ledger_path)
    cycle_events = []

    def record(event_type: str, **payload):
        event = ledger.append(event_type, cycle_id=cycle_id, **payload)
        cycle_events.append(event)
        return event

    cycle_id = f"cycle-{now_iso()}-{uuid.uuid4().hex[:8]}"
    record("CycleOpened", kind=kind, request=request)

    packet = assemble_context(config, ledger, kind=kind, request=request)
    record("DeltaPrepared", observations=len(packet.observations), threads=len(packet.thread_candidates), reports=len(packet.report_candidates))

    thread_id, readiness = _ready_context(packet, record)
    searches = broad_search(config, packet)
    search_sources = sorted({result.source for result in searches})
    record("BroadSearchCompleted", sources=search_sources, results=len(searches))

    draft = draft_report(packet, searches, thread_id)
    record("ReportDrafted", chars=len(draft), thread_id=thread_id)
    reviews = [
        adversarial_review(draft),
        general_review(draft, packet),
        feynman_review(draft),
        method_review(draft, packet, search_sources),
    ]
    for review in reviews:
        record("ReportReviewed", reviewer=review.reviewer, status=review.status, summary=review.summary, data=review.data)

    report_path = finalize_report(config, packet=packet, draft=draft, reviews=reviews, thread_id=thread_id)
    record("ReportWritten", path=str(report_path), thread_id=thread_id)
    primary_thread = primary_thread_from_review(readiness, packet.request)

    thread_path = update_thread(
        config,
        thread_id=thread_id,
        title=primary_thread["title"],
        report_path=report_path,
        summary=f"{kind} beat: {packet.request}",
        decisions=["Keep context absorption and reviews in the runtime rite."],
        next_steps=["Use the next beat to deepen this thread with more observed context."],
    )
    record("ThreadUpdated", thread_id=thread_id, path=str(thread_path))
    digest = rebuild_digest(config)
    record("DigestRebuilt", path=str(digest))
    index = build_blog(config)
    record("BlogBuilt", path=str(index))
    rite = verify_rite(cycle_events)
    if not rite.passed:
        record("RiteVerificationFailed", **rite.as_dict())
        raise RuntimeError(f"beat rite failed: {', '.join(rite.missing)}")
    record("RiteVerified", **rite.as_dict())
    record("CycleClosed", status="completed")
    return BeatResult(cycle_id=cycle_id, report_path=str(report_path), thread_id=thread_id, status="completed")
