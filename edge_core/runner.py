from __future__ import annotations

import uuid
from typing import Any
from dataclasses import dataclass

from .async_chat import acknowledge_messages
from .chat_digest import refresh_chat_digest
from .config import RuntimeConfig, ensure_runtime_dirs
from .context import assemble_context
from .ledger import Ledger
from .publication import build_blog, build_report_spec, publish_artifact_bundle, validate_blog_post, validate_report_spec
from .reports import append_report_utility, draft_report, revise_report
from .reviewers import ReviewResult, adversarial_review, classify_report_utility, context_search_review, feynman_review, report_shape_review
from .rite import verify_rite
from .search import broad_search
from .threads import choose_primary_thread, initial_seed_thread, rebuild_digest, update_thread
from .util import now_iso


@dataclass
class BeatResult:
    kind: str
    cycle_id: str
    report_path: str
    thread_id: str
    status: str


ROUTED_BEAT_ORDER = ("discovery", "research", "report")


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


def route_heartbeat(config: RuntimeConfig, *, request: str = "") -> tuple[str, str, str]:
    lowered = request.lower()
    explicit_routes = [
        ("research", ("research", "investigate", "e2e", "experiment")),
        ("discovery", ("discovery", "discover", "notice", "inspect", "explore")),
        ("report", ("report", "summarize", "summary", "synthesis")),
    ]
    for kind, tokens in explicit_routes:
        if any(token in lowered for token in tokens):
            return kind, request or f"Autonomous {kind} beat", f"request-explicit:{kind}"
    ledger = Ledger(config.ledger_path)
    recent = [
        event
        for event in ledger.read_recent(200)
        if event.get("type") == "CycleOpened" and str(event.get("kind") or "") in ROUTED_BEAT_ORDER
    ]
    if recent:
        last_kind = str(recent[-1].get("kind") or ROUTED_BEAT_ORDER[-1])
        try:
            next_index = (ROUTED_BEAT_ORDER.index(last_kind) + 1) % len(ROUTED_BEAT_ORDER)
        except ValueError:
            next_index = 0
    else:
        next_index = 0
    kind = ROUTED_BEAT_ORDER[next_index]
    routed_request = request or f"Autonomous {kind} beat"
    return kind, routed_request, "round-robin"


def run_beat(config: RuntimeConfig, *, kind: str, request: str = "", trigger: str = "direct", requested_kind: str | None = None) -> BeatResult:
    if kind == "heartbeat":
        raise ValueError("heartbeat is a router and must call run_heartbeat(), not run_beat().")
    ensure_runtime_dirs(config)
    ledger = Ledger(config.ledger_path)
    cycle_events = []

    def record(event_type: str, **payload):
        event = ledger.append(event_type, cycle_id=cycle_id, **payload)
        cycle_events.append(event)
        return event

    cycle_id = f"cycle-{now_iso()}-{uuid.uuid4().hex[:8]}"
    record("CycleOpened", kind=kind, request=request, trigger=trigger, requested_kind=requested_kind or kind)

    chat_digest = refresh_chat_digest(config)
    record("ChatDigestRefreshed", **chat_digest)
    packet = assemble_context(config, ledger, kind=kind, request=request)
    record(
        "OperatorContextLoaded",
        operator_pressure_present=bool(packet.operator_pressure.strip()),
        async_chat_messages=len(packet.operator_messages),
    )
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
    searches_1 = broad_search(config, packet, hints=_search_hints([context_review_1]), round_index=1)
    record("BroadSearchCompleted", round=1, sources=sorted({result.source for result in searches_1}), results=len(searches_1))
    record("DeliveryCompleted", stage="evidence-pack-v1", search_results=len(searches_1))

    context_review_2 = context_search_review(packet, searches_1, round_index=2)
    record("ContinuitySearchReviewed", round=2, reviewer=context_review_2.reviewer, summary=context_review_2.summary, data=context_review_2.data)
    searches_2 = broad_search(config, packet, hints=_search_hints([context_review_1, context_review_2]), round_index=2)
    searches = searches_1 + searches_2
    record("BroadSearchCompleted", round=2, sources=sorted({result.source for result in searches_2}), results=len(searches_2))
    record("DeliveryCompleted", stage="evidence-pack-v2", search_results=len(searches))

    if packet.thread_candidates:
        primary_thread = choose_primary_thread(context_review_2.data, packet.request, packet.thread_candidates)
    else:
        primary_thread = initial_seed_thread(config)
    thread_id = primary_thread["thread_id"]
    draft_1_result = draft_report(packet, searches, primary_thread)
    draft_1 = draft_1_result.text
    record(
        "ReportDrafted",
        version=1,
        chars=len(draft_1),
        thread_id=thread_id,
        mode=draft_1_result.mode,
        llm_provider=draft_1_result.provider,
        llm_error=draft_1_result.error,
    )
    shape_review_1 = report_shape_review(draft_1, stage="draft-v1")
    record("ReportShapeReviewed", version=1, reviewer=shape_review_1.reviewer, summary=shape_review_1.summary, data=shape_review_1.data)
    record("DeliveryCompleted", stage="draft-v1", chars=len(draft_1))

    adversarial_1 = adversarial_review(draft_1, packet, searches, round_index=1)
    record("AdversarialSearchReviewed", round=1, reviewer=adversarial_1.reviewer, summary=adversarial_1.summary, data=adversarial_1.data)
    searches_3 = broad_search(config, packet, hints=_search_hints([context_review_1, context_review_2, adversarial_1]), round_index=3)
    searches = searches + searches_3
    record("BroadSearchCompleted", round=3, sources=sorted({result.source for result in searches_3}), results=len(searches_3))
    draft_2_result = revise_report(packet, searches, primary_thread, draft_1, [shape_review_1, adversarial_1], stage="adversarial-search")
    draft_2 = draft_2_result.text
    record(
        "ReportRevised",
        version=2,
        chars=len(draft_2),
        source="adversarial-search",
        mode=draft_2_result.mode,
        llm_provider=draft_2_result.provider,
        llm_error=draft_2_result.error,
    )
    shape_review_2 = report_shape_review(draft_2, stage="draft-v2")
    record("ReportShapeReviewed", version=2, reviewer=shape_review_2.reviewer, summary=shape_review_2.summary, data=shape_review_2.data)
    record("DeliveryCompleted", stage="draft-v2", chars=len(draft_2))

    adversarial_2 = adversarial_review(draft_2, packet, searches, round_index=2)
    record("AdversarialReviewed", round=2, reviewer=adversarial_2.reviewer, summary=adversarial_2.summary, data=adversarial_2.data)
    draft_3_result = revise_report(packet, searches, primary_thread, draft_2, [shape_review_2, adversarial_2], stage="adversarial")
    draft_3 = draft_3_result.text
    record(
        "ReportRevised",
        version=3,
        chars=len(draft_3),
        source="adversarial",
        mode=draft_3_result.mode,
        llm_provider=draft_3_result.provider,
        llm_error=draft_3_result.error,
    )
    shape_review_3 = report_shape_review(draft_3, stage="draft-v3")
    record("ReportShapeReviewed", version=3, reviewer=shape_review_3.reviewer, summary=shape_review_3.summary, data=shape_review_3.data)
    record("DeliveryCompleted", stage="draft-v3", chars=len(draft_3))

    feynman = feynman_review(draft_3, packet, searches)
    record("FeynmanReviewed", reviewer=feynman.reviewer, summary=feynman.summary, data=feynman.data)
    final_report_result = revise_report(packet, searches, primary_thread, draft_3, [shape_review_3, feynman], stage="feynman-final")
    final_report = final_report_result.text
    record(
        "FinalReportPrepared",
        chars=len(final_report),
        mode=final_report_result.mode,
        llm_provider=final_report_result.provider,
        llm_error=final_report_result.error,
    )
    final_shape_review = report_shape_review(final_report, stage="final")
    record("ReportShapeReviewed", version=4, reviewer=final_shape_review.reviewer, summary=final_shape_review.summary, data=final_shape_review.data)
    if not bool(final_shape_review.data.get("passed")):
        record("ReportShapeValidationFailed", issues=final_shape_review.data.get("issues") or [])
        raise RuntimeError(f"report shape validation failed: {', '.join(final_shape_review.data.get('issues') or [])}")

    reviews = [context_review_1, context_review_2, shape_review_1, adversarial_1, shape_review_2, adversarial_2, shape_review_3, feynman, final_shape_review]
    spec = build_report_spec(
        packet=packet,
        report_markdown=final_report,
        searches=searches,
        reviews=reviews,
        thread_id=thread_id,
        thread_title=primary_thread["title"],
        thread_action=primary_thread["action"],
    )
    spec_check = validate_report_spec(spec)
    blog_check = validate_blog_post(spec.get("blog_post"))
    artifact_issues = [*spec_check.issues, *blog_check.issues]
    record(
        "ArtifactBundleValidated",
        report_spec_passed=spec_check.passed,
        blog_post_passed=blog_check.passed,
        issues=artifact_issues,
    )
    if artifact_issues:
        raise RuntimeError(f"artifact bundle validation failed: {', '.join(artifact_issues)}")

    published = publish_artifact_bundle(
        config,
        packet=packet,
        report_markdown=final_report,
        searches=searches,
        reviews=reviews,
        thread_id=thread_id,
        thread_title=primary_thread["title"],
        thread_action=primary_thread["action"],
    )
    record(
        "ReportWritten",
        path=str(published.report_html_path),
        markdown_path=str(published.report_markdown_path),
        spec_path=str(published.report_spec_path),
        blog_entry_path=str(published.blog_entry_markdown_path),
        blog_entry_html=str(published.blog_entry_html_path),
        thread_id=thread_id,
    )
    utility = classify_report_utility(final_report, packet, reviews)
    utility_path = append_report_utility(config, report_path=published.report_html_path, utility=utility)
    record("ReportUtilityClassified", reviewer=utility.reviewer, summary=utility.summary, data=utility.data, path=str(utility_path))
    utility_data = utility.data if isinstance(utility.data, dict) else {}

    thread_path = update_thread(
        config,
        thread_id=thread_id,
        title=primary_thread["title"],
        report_path=published.report_markdown_path,
        summary=str(utility_data.get("summary") or f"{kind} beat: {packet.request}"),
        decisions=[f"Utility: {utility_data.get('utility_label', 'unclassified')}"],
        next_steps=_list_from_data(utility_data, "recommended_followups") or ["Continue the thread from the final report's next steps."],
    )
    record("ThreadUpdated", thread_id=thread_id, path=str(thread_path))
    digest = rebuild_digest(config)
    record("DigestRebuilt", path=str(digest))
    index = build_blog(config)
    record("BlogBuilt", path=str(index))
    async_ack = acknowledge_messages(config, messages=packet.operator_messages, cycle_id=cycle_id, kind=kind, request=packet.request)
    if async_ack.get("processed_ids"):
        record(
            "AsyncChatAcknowledged",
            processed=len(async_ack.get("processed_ids") or []),
            processed_ids=async_ack.get("processed_ids") or [],
            reply_id=async_ack.get("reply_id"),
        )
    rite = verify_rite(cycle_events)
    if not rite.passed:
        record("RiteVerificationFailed", **rite.as_dict())
        raise RuntimeError(f"beat rite failed: {', '.join(rite.missing)}")
    record("RiteVerified", **rite.as_dict())
    record("CycleClosed", status="completed")
    return BeatResult(kind=kind, cycle_id=cycle_id, report_path=str(published.report_html_path), thread_id=thread_id, status="completed")


def run_heartbeat(config: RuntimeConfig, *, request: str = "") -> BeatResult:
    kind, routed_request, reason = route_heartbeat(config, request=request)
    ledger = Ledger(config.ledger_path)
    ledger.append("HeartbeatRouted", requested=request, routed_kind=kind, routed_request=routed_request, reason=reason)
    return run_beat(config, kind=kind, request=routed_request, trigger="heartbeat", requested_kind="heartbeat")
