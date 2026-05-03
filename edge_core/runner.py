from __future__ import annotations

import uuid
from typing import Any
from dataclasses import dataclass

from .config import RuntimeConfig, ensure_runtime_dirs
from .context import assemble_context
from .ledger import Ledger
from .reports import append_report_utility, build_blog, draft_report, finalize_report, revise_report
from .reviewers import ReviewResult, adversarial_review, classify_report_utility, context_search_review, feynman_review
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


def _search_hints(reviews: list[ReviewResult]) -> list[str]:
    hints: list[str] = []
    for review in reviews:
        data = review.data if isinstance(review.data, dict) else {}
        for key in ["suggested_queries", "search_queries", "recommended_queries"]:
            raw = data.get(key)
            if isinstance(raw, list):
                hints.extend(str(item) for item in raw if item)
            elif isinstance(raw, str):
                hints.append(raw)
        sources = data.get("suggested_sources")
        if isinstance(sources, list) and sources:
            hints.append(" ".join(str(item) for item in sources if item))
    return hints[:12]


def _list_from_data(data: dict[str, Any], key: str) -> list[str]:
    raw = data.get(key)
    if isinstance(raw, list):
        return [str(item) for item in raw if item][:6]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


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
    record(
        "StateLoaded",
        observations=len(packet.observations),
        threads=len(packet.thread_candidates),
        reports=len(packet.report_candidates),
        delta_sources=len(packet.delta_source_manifest),
        search_sources=len(packet.search_source_manifest),
    )
    record("DeliveryCompleted", stage="context-pack", observations=len(packet.observations))

    context_review_1 = context_search_review(packet, [], round_index=1)
    record("ContinuitySearchReviewed", round=1, reviewer=context_review_1.reviewer, summary=context_review_1.summary, data=context_review_1.data)
    searches_1 = broad_search(config, packet, hints=_search_hints([context_review_1]))
    record("BroadSearchCompleted", round=1, sources=sorted({result.source for result in searches_1}), results=len(searches_1))
    record("DeliveryCompleted", stage="evidence-pack-v1", search_results=len(searches_1))

    context_review_2 = context_search_review(packet, searches_1, round_index=2)
    record("ContinuitySearchReviewed", round=2, reviewer=context_review_2.reviewer, summary=context_review_2.summary, data=context_review_2.data)
    searches_2 = broad_search(config, packet, hints=_search_hints([context_review_1, context_review_2]))
    searches = searches_1 + searches_2
    record("BroadSearchCompleted", round=2, sources=sorted({result.source for result in searches_2}), results=len(searches_2))
    record("DeliveryCompleted", stage="evidence-pack-v2", search_results=len(searches))

    thread_id = thread_id_from_review(context_review_2.data, packet.request)
    draft_1 = draft_report(packet, searches, thread_id)
    record("ReportDrafted", version=1, chars=len(draft_1), thread_id=thread_id)
    record("DeliveryCompleted", stage="draft-v1", chars=len(draft_1))

    adversarial_1 = adversarial_review(draft_1, packet, searches, round_index=1)
    record("AdversarialSearchReviewed", round=1, reviewer=adversarial_1.reviewer, summary=adversarial_1.summary, data=adversarial_1.data)
    searches_3 = broad_search(config, packet, hints=_search_hints([context_review_1, context_review_2, adversarial_1]))
    searches = searches + searches_3
    record("BroadSearchCompleted", round=3, sources=sorted({result.source for result in searches_3}), results=len(searches_3))
    draft_2 = revise_report(packet, searches, thread_id, draft_1, [adversarial_1], stage="adversarial-search")
    record("ReportRevised", version=2, chars=len(draft_2), source="adversarial-search")
    record("DeliveryCompleted", stage="draft-v2", chars=len(draft_2))

    adversarial_2 = adversarial_review(draft_2, packet, searches, round_index=2)
    record("AdversarialReviewed", round=2, reviewer=adversarial_2.reviewer, summary=adversarial_2.summary, data=adversarial_2.data)
    draft_3 = revise_report(packet, searches, thread_id, draft_2, [adversarial_2], stage="adversarial")
    record("ReportRevised", version=3, chars=len(draft_3), source="adversarial")
    record("DeliveryCompleted", stage="draft-v3", chars=len(draft_3))

    feynman = feynman_review(draft_3, packet, searches)
    record("FeynmanReviewed", reviewer=feynman.reviewer, summary=feynman.summary, data=feynman.data)
    final_report = revise_report(packet, searches, thread_id, draft_3, [feynman], stage="feynman-final")
    record("FinalReportPrepared", chars=len(final_report))

    reviews = [context_review_1, context_review_2, adversarial_1, adversarial_2, feynman]
    report_path = finalize_report(config, packet=packet, draft=final_report, reviews=reviews, thread_id=thread_id)
    record("ReportWritten", path=str(report_path), thread_id=thread_id)
    utility = classify_report_utility(final_report, packet, reviews)
    utility_path = append_report_utility(config, report_path=report_path, utility=utility)
    record("ReportUtilityClassified", reviewer=utility.reviewer, summary=utility.summary, data=utility.data, path=str(utility_path))
    primary_thread = primary_thread_from_review(context_review_2.data, packet.request)
    utility_data = utility.data if isinstance(utility.data, dict) else {}

    thread_path = update_thread(
        config,
        thread_id=thread_id,
        title=primary_thread["title"],
        report_path=report_path,
        summary=str(utility_data.get("summary") or f"{kind} beat: {packet.request}"),
        decisions=[f"Utility: {utility_data.get('utility_label', 'unclassified')}"],
        next_steps=_list_from_data(utility_data, "recommended_followups") or ["Continue the thread from the final report's next steps."],
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
