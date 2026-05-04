from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .context import ContextPacket
from .llm_client import LLMClient
from .report_shape import REPORT_SECTION_TITLES, validate_report_markdown
from .search import SearchResult
from .util import slugify, truncate


@dataclass
class ReviewResult:
    status: str
    reviewer: str
    summary: str
    data: dict[str, Any]


def context_search_review(packet: ContextPacket, searches: list[SearchResult], *, round_index: int) -> ReviewResult:
    client = LLMClient(role="review")
    required_sections = [
        "Problem Framing and Open Gaps",
        "Why This Matters Now",
        "Broad Search",
        "Feynman Derivation",
    ]
    prompt = json.dumps(
        {
            "round": round_index,
            "context": packet.as_dict(),
            "search_results": [result.__dict__ for result in searches[:12]],
            "required_sections": required_sections,
        },
        ensure_ascii=False,
    )[:22000]
    llm = client.complete_json(
        system=(
            "You are the continuity/context/search reviewer for a private Feynman mentor. "
            "Inspect the delta source manifest and the search source manifest. Judge continuity, loader sufficiency, "
            "source coverage, search terms, and whether the right sources were attempted. Also judge whether the loaded context is strong enough "
            "to support the mandatory report sections around problem framing, why-this-matters-now, broad search, and Feynman derivation. Return JSON with "
            "primary_thread, continuity_assessment, loader_notes, search_assessment, suggested_queries, suggested_sources, "
            "missing_context, section_support, required_local_reads, and summary. "
            "Prefer the work that is hottest in the current workspace evidence (recent files, current diffs, recent experiment outputs) over older prepared threads that have little live evidence this round. "
            "If the only existing thread is generic, recursive, stale relative to the current delta, or clearly off-domain relative to the loaded work, you may propose primary_thread.action=create for a more concrete live line of work. "
            "Do not infer local thread/report contents from an empty directory alone: if authoritative_reads is empty and manifest item_count is 0, treat that as absent local evidence, not unread local evidence. Do not decide pass/fail; give material for the next straight-line step."
        ),
        prompt=prompt,
    )
    if llm:
        llm["round"] = round_index
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        return ReviewResult("completed", "llm:context-search", str(llm.get("summary") or llm.get("reason") or "context/search reviewed"), llm)

    has_observations = len(packet.observations) >= 2
    search_count = len(searches)
    thread_id = "general-continuity"
    title = "General Continuity"
    action = "create"
    default_heartbeat = packet.kind == "heartbeat" and packet.request == "Run a heartbeat beat"
    seed_text = ""
    if packet.seed_threads:
        seed = packet.seed_threads[0]
        seed_text = f"{seed.get('title', '')} {seed.get('context', '')}"
    request_text = (seed_text if default_heartbeat and seed_text else packet.request).lower()
    if packet.thread_candidates:
        scored: list[tuple[int, dict[str, Any]]] = []
        request_terms = {term for term in slugify(request_text).split("-") if len(term) > 3}
        for candidate in packet.thread_candidates:
            haystack = slugify(f"{candidate.get('id', '')} {candidate.get('summary', '')}")
            score = sum(1 for term in request_terms if term in haystack)
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] > 0:
            thread_id = str(scored[0][1].get("id") or thread_id)
            title = thread_id.replace("-", " ").title()
            action = "continue"
    if action == "create" and (default_heartbeat or not packet.request) and packet.seed_threads:
        seed = packet.seed_threads[0]
        title = str(seed.get("title") or "Seed Thread")
        thread_id = slugify(title, "seed-thread")[:80]
    elif action == "create" and packet.request:
        thread_id = slugify(packet.request, "general-continuity")[:80]
        title = thread_id.replace("-", " ").title()
    data = {
        "round": round_index,
        "primary_thread": {"action": action, "thread_id": thread_id, "title": title},
        "continuity_assessment": "local fallback continues a thread only on textual overlap; otherwise it creates from request or seed_threads.",
        "loader_notes": "Context has enough observations for a situated beat." if has_observations else "Context is thin.",
        "search_assessment": "Local fallback cannot judge source quality; it preserves configured source manifests for reviewers.",
        "suggested_queries": [packet.request],
        "suggested_sources": [item.get("name") for item in packet.search_source_manifest if item.get("enabled")],
        "missing_context": [] if has_observations else ["No workspace or session observations were available."],
        "section_support": {
            "Problem Framing and Open Gaps": "supported" if has_observations else "under-supported: thin live context",
            "Why This Matters Now": "supported" if has_observations else "under-supported: unclear current delta",
            "Broad Search": "supported" if search_count > 0 else "under-supported: no search results yet",
            "Feynman Derivation": "supported" if has_observations and search_count > 0 else "under-supported: derivation will be weak until context and search are richer",
        },
        "summary": "Local context/search review completed.",
        "mode": "local-fallback",
    }
    return ReviewResult("completed", "local:context-search", data["summary"], data)


def context_readiness(packet: ContextPacket, *, attempt: int) -> ReviewResult:
    return context_search_review(packet, [], round_index=attempt)


def adversarial_review(report: str, packet: ContextPacket | None = None, searches: list[SearchResult] | None = None, *, round_index: int = 1) -> ReviewResult:
    client = LLMClient(role="review")
    payload: Any = report[:16000]
    if packet is not None:
        payload = {
            "round": round_index,
            "report": report[:14000],
            "context": packet.as_dict(),
            "search_results": [result.__dict__ for result in (searches or [])[:12]],
        }
    llm = client.complete_json(
        system=(
            "You are an adversarial reviewer. Find weak assumptions, missing evidence, and overreach. "
            "Also inspect the delta/search source manifests, current search results, fetched reading notes, and whether the mandatory report shape is being used meaningfully. "
            "Treat search broadly: surface coverage, API availability, fetched evidence quality, missed angles, and domain vocabulary that should have been explored. "
            "Return JSON with summary, weak_assumptions, missing_evidence, search_assessment, section_repairs, suggested_queries, suggested_sources, and recommended_repairs."
        ),
        prompt=json.dumps(payload, ensure_ascii=False)[:22000] if isinstance(payload, dict) else payload,
    )
    if llm:
        llm["round"] = round_index
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        return ReviewResult("completed", "llm:adversarial", str(llm.get("summary") or "adversarial review completed"), llm)
    configured_sources = [str(item.get("name")) for item in ((packet.search_source_manifest if packet else []) or []) if item.get("enabled")]
    summary = "Local fallback: challenge generic claims, missing source diversity, weak continuity, and recommendations not tied to the observed delta."
    return ReviewResult(
        "completed",
        "local:adversarial",
        summary,
        {
            "summary": summary,
            "mode": "local-fallback",
            "round": round_index,
            "search_assessment": "Local fallback cannot verify coverage quality, but it preserves the configured search surfaces for the next broad search pass.",
            "suggested_queries": [packet.request] if packet and packet.request else [],
            "suggested_sources": configured_sources,
            "recommended_repairs": [],
        },
    )


def feynman_review(report: str, packet: ContextPacket | None = None, searches: list[SearchResult] | None = None) -> ReviewResult:
    client = LLMClient(role="review")
    payload: Any = report[:16000]
    if packet is not None:
        payload = {
            "report": report[:14000],
            "context": packet.as_dict(),
            "search_results": [result.__dict__ for result in (searches or [])[:12]],
        }
    llm = client.complete_json(
        system=(
            "You are a Feynman reviewer. Check simplicity, derivation, gaps, and honest uncertainty. "
            "Also inspect whether the report's search/source use supports the explanation, whether the fetched reading notes were used well, whether the search manifests show missed exploration, and whether the mandatory sections actually carry useful reasoning. "
            "Treat search broadly: terms, sources, APIs, fetched evidence, and domain-specific surfaces that should have been touched. "
            "Return JSON with summary, simplicity, derivation, gaps, honest_uncertainty, section_repairs, search_assessment, suggested_queries, suggested_sources, and repair_notes."
        ),
        prompt=json.dumps(payload, ensure_ascii=False)[:22000] if isinstance(payload, dict) else payload,
    )
    if llm:
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        return ReviewResult("completed", "llm:feynman-review", str(llm.get("summary") or "Feynman review completed"), llm)
    has_gap = "gap" in report.lower() or "lacuna" in report.lower()
    summary = "Local fallback: explanation is acceptable if it states the simple model, evidence, gaps, and next step."
    if not has_gap:
        summary += " Add an explicit gap section."
    configured_sources = [str(item.get("name")) for item in ((packet.search_source_manifest if packet else []) or []) if item.get("enabled")]
    return ReviewResult(
        "completed",
        "local:feynman-review",
        summary,
        {
            "summary": summary,
            "mode": "local-fallback",
            "explicit_gap_seen": has_gap,
            "search_assessment": "Local fallback checks only whether the explanation acknowledges evidence and uncertainty; configured search surfaces are preserved for the next pass.",
            "suggested_queries": [packet.request] if packet and packet.request else [],
            "suggested_sources": configured_sources,
            "repair_notes": [],
        },
    )


def classify_report_utility(report: str, packet: ContextPacket, reviews: list[ReviewResult]) -> ReviewResult:
    client = LLMClient(role="utility")
    llm = client.complete_json(
        system=(
            "Classify this generated mentor report for future curation. Return JSON with utility_score 0-5, "
            "utility_label, curation_tags, evergreen_value, actionability, novelty, continuity_value, summary, "
            "recommended_followups. This classification never blocks publication."
        ),
        prompt=json.dumps(
            {
                "report": report[:14000],
                "context": packet.as_dict(),
                "reviews": [{"reviewer": review.reviewer, "summary": review.summary, "data": review.data} for review in reviews],
            },
            ensure_ascii=False,
        )[:22000],
    )
    if llm:
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        return ReviewResult("completed", "llm:report-utility", str(llm.get("summary") or "utility classified"), llm)
    score = 2 if "deterministic scaffold fallback" in report.lower() else 3
    data = {
        "utility_score": score,
        "utility_label": "low" if score <= 2 else "medium",
        "curation_tags": [packet.kind, "local-fallback" if score <= 2 else "mentor-report"],
        "summary": "Local fallback utility classification.",
        "recommended_followups": [],
        "mode": "local-fallback",
    }
    return ReviewResult("completed", "local:report-utility", data["summary"], data)


def summarize_reviews(reviews: list[ReviewResult]) -> str:
    return "\n".join(f"- **{review.reviewer}:** {truncate(review.summary, 500)}" for review in reviews)


def report_shape_review(report: str, *, stage: str) -> ReviewResult:
    check = validate_report_markdown(report)
    seen_titles = [title for title, _body in check.sections]
    missing = [title for title in REPORT_SECTION_TITLES if title not in seen_titles]
    summary = "Report shape satisfies the mandatory artifact sections." if check.passed else "Report shape is missing or weakening mandatory artifact sections."
    data = {
        "stage": stage,
        "passed": check.passed,
        "issues": check.issues,
        "required_sections": REPORT_SECTION_TITLES,
        "seen_sections": seen_titles,
        "missing_sections": missing,
        "title": check.title,
        "summary": summary,
        "mode": "deterministic-shape-check",
    }
    return ReviewResult("completed", "deterministic:report-shape", summary, data)
