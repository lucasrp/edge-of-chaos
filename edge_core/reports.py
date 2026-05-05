from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import RuntimeConfig
from .context import ContextPacket
from .llm_client import LLMClient
from .report_shape import REPORT_SECTION_TITLES
from .reviewers import ReviewResult, summarize_reviews
from .search import SearchResult
from .util import truncate


@dataclass(frozen=True)
class ReportResult:
    text: str
    mode: str
    provider: str
    error: str = ""


def required_report_shape_text() -> str:
    return "\n".join(f"## {title}" for title in REPORT_SECTION_TITLES)


def draft_report(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> ReportResult:
    client = LLMClient(role="report")
    llm_report = _llm_draft_report(client, packet, searches, primary_thread)
    if llm_report:
        return ReportResult(text=_normalize_report_text(packet, llm_report), mode="llm", provider=client.last_provider, error=client.last_error)
    thread_id = primary_thread["thread_id"]
    selected_thread = _selected_thread_payload(packet, primary_thread)
    observations = "\n".join(
        f"- { _safe_scaffold_text(obs.source) }: { _safe_scaffold_text(obs.title) } — { _safe_scaffold_text(truncate(obs.detail, 300)) }"
        for obs in packet.observations[:12]
    )
    reports = "\n".join(
        f"- {_safe_scaffold_text(str(item.get('title') or 'report'))} ({_safe_scaffold_text(str(item.get('path') or ''))})"
        for item in packet.report_candidates[:6]
    ) or "- No previous report found."
    operator_pressure = _safe_scaffold_text(packet.operator_pressure or "No explicit operator pressure was present for this beat.")
    operator_chat = "\n".join(
        f"- {_safe_scaffold_text(str(item.get('author') or 'user'))}: {_safe_scaffold_text(truncate(str(item.get('text') or ''), 220))}"
        for item in packet.operator_messages[:6]
    ) or "- No async operator chat message was present for this beat."
    search_lines = "\n".join(
        f"- {_safe_scaffold_text(result.source)} [{_safe_scaffold_text(result.status)} / {_safe_scaffold_text(result.fetch_status)}]: {_safe_scaffold_text(result.title)} {_safe_scaffold_text(result.url)} — {_safe_scaffold_text(truncate(result.summary, 250))}"
        for result in searches
    )
    interests = "\n".join(f"- {_safe_scaffold_text(str(item.get('area') or 'interest'))}: {_safe_scaffold_text(str(item.get('connection') or ''))}" for item in packet.interests[:5])
    lineage_line = f"This beat continues thread `{thread_id}` from the currently observed continuity evidence."
    if selected_thread["grounded"]:
        lineage_line = f"This beat continues thread `{thread_id}` from an authoritative thread read: {_safe_scaffold_text(str(selected_thread['authoritative_excerpt']))}"
    text = f"""# Private Mentor Report

## Lineage

{lineage_line}

## Situated Delta

{observations}

Operator pressure shaping this beat:

{operator_pressure}

Recent async operator chat:

{operator_chat}

## Problem Framing and Open Gaps

Before broad search, the mentor should formalize the live problem and the gaps that keep the explanation weak. Candidate reports:

{reports}

## Simple Model

The mentor should start from the observed real work, identify the delta, and turn it into guidance that helps the mentee think and act better. If context is still thin, the report should say so instead of fabricating certainty.

## Feynman Derivation

1. The current request/beat points to: {packet.request or packet.kind}
2. Recent context shows workspace evidence, report history, threads, and sessions.
3. The recommendation must continue a real thread or open a new one with justification.
4. The report must preserve the rite: broad search, adversarial review, Feynman review, and concrete next steps.

## Why This Matters Now

If the mentor loses the live problem framing before search, the report drifts into generic advice. This section exists to keep the explanation tied to the mentee's current work.

## Broad Search

{search_lines}

## Adversarial Pushback

The current explanation is only as strong as the continuity evidence and search quality. If either is thin, the report must say so plainly.

## Recommended Next Steps

- Review whether the report adheres to the observed real work.
- Update the compact thread with the new understanding.
- If search degraded because credentials were missing, configure the phenotype sources.

## What I Don't Know

- Confirm whether the selected thread represents the correct live line of work.
- Confirm whether the configured external sources were sufficient or whether the runtime fell back locally.
- Confirm whether there is a previous report that should have been recovered but was not.

## Contextualization and Glossary

Context: this is a private mentor report for an active line of work, not a public article.

- `delta`: what changed in the mentee's current situation.
- `thread`: the continuity line that carries the work across beats.
- `Feynman`: derive simply, expose gaps, and only then widen the search.
- `interests`: {interests or "No configured interest."}
"""
    return ReportResult(
        text=text,
        mode="deterministic-scaffold",
        provider=client.last_provider,
        error=client.last_error or "llm:no-report-text",
    )


def revise_report(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str], draft: str, reviews: list[ReviewResult], *, stage: str) -> ReportResult:
    client = LLMClient(role="report")
    thread_id = primary_thread["thread_id"]
    feedback = [
        {
            "reviewer": review.reviewer,
            "status": review.status,
            "summary": review.summary,
            "data": review.data,
        }
        for review in reviews
    ]
    prompt = {
        "kind": packet.kind,
        "request": packet.request,
        "thread_id": thread_id,
        "selected_thread": _selected_thread_payload(packet, primary_thread),
        "stage": stage,
        "draft": draft[:14000],
        "review_feedback": feedback,
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "search_results": _search_payload(searches, limit=14),
        "authoritative_reads": packet.authoritative_reads[:10],
        "first_steps": packet.first_steps,
        "interests": packet.interests,
        "operator_pressure": packet.operator_pressure,
        "operator_messages": packet.operator_messages[:8],
    }
    text = client.complete_text(
        system=(
            "You are edge-of-chaos v2 revising a mentor report in a fixed straight-line rite. "
            "Rewrite the report in Markdown using the reviewer feedback as input, not as a pass/fail gate. "
            "Keep the mentor/mentee relationship, situated delta, continuity, problem framing before search, broad-search evidence, "
            "adversarial pushback, Feynman derivation, why-this-matters-now, explicit gaps, and concrete next steps. "
            "Search telemetry is not the same as search evidence: unavailable/no_results/failed entries constrain coverage, while fetched entries with reading_note carry substantive evidence. "
            "If fetched evidence exists, use it. Do not claim nothing was retrieved when fetched entries or search-digest entries are present. "
            "When fetched workspace-search or search-digest evidence exists, the Broad Search section must name at least two concrete findings and explain how they changed the judgement. "
            "Start with the exact Markdown title `# Private Mentor Report`. "
            "If selected_thread.grounded is true, anchor the Lineage section to that concrete thread and its excerpt. "
            "Do not claim thread_candidates is empty when the selected_thread says otherwise. "
            "Do not call the selected thread a placeholder when selected_thread.grounded is true. "
            "Use this exact section order and titles:\n"
            f"{required_report_shape_text()}\n"
            "Return only the report."
        ),
        prompt=json.dumps(prompt, ensure_ascii=False)[:26000],
    )
    if not text:
        return ReportResult(
            text=draft,
            mode="unchanged",
            provider=client.last_provider,
            error=client.last_error or "llm:no-revised-text",
        )
    return ReportResult(text=_normalize_report_text(packet, text), mode="llm", provider=client.last_provider, error=client.last_error)

def append_report_utility(config: RuntimeConfig, *, report_path: Path, utility: ReviewResult) -> Path:
    path = config.state_dir / "report-utility.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "report": str(report_path),
        "reviewer": utility.reviewer,
        "summary": utility.summary,
        "data": utility.data,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path
def _llm_draft_report(client: LLMClient, packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> str | None:
    thread_id = primary_thread["thread_id"]
    prompt = {
        "kind": packet.kind,
        "request": packet.request,
        "thread_id": thread_id,
        "selected_thread": _selected_thread_payload(packet, primary_thread),
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "first_steps": packet.first_steps,
        "seed_threads": packet.seed_threads,
        "interests": packet.interests,
        "routines": packet.routines,
        "authoritative_reads": packet.authoritative_reads[:10],
        "search_results": _search_payload(searches, limit=14),
        "operator_pressure": packet.operator_pressure,
        "operator_messages": packet.operator_messages[:8],
    }
    text = client.complete_text(
        system=(
            "You are edge-of-chaos v2, a private Feynman mentor. Write a rich private mentor report in Markdown. "
            "Do not write dashboard copy. Do not sound like a product brochure. "
            "The report must be situated in the observed work, continue or justify the thread, formalize the problem and open gaps before search, "
            "explain the simple model, derive the reasoning in Feynman style, explain why this matters now, cite search/source evidence including "
            "unavailable sources, give adversarial pushback, state what is still unknown, and end with concrete next steps. "
            "Treat search telemetry separately from search evidence. Only fetched entries with reading notes or concrete local-state excerpts count as evidence. "
            "If fetched evidence exists, incorporate it into the explanation instead of leaving Broad Search as a to-do list. "
            "When fetched workspace-search or search-digest evidence exists, the Broad Search section must name at least two concrete findings and explain how they changed the judgement. "
            "Start with the exact Markdown title `# Private Mentor Report`. "
            "If selected_thread.grounded is true, the Lineage section must continue that exact thread concretely from its authoritative excerpt. "
            "Do not say the thread list is empty when selected_thread.thread_candidate_count is non-zero. "
            "Do not call the selected thread a placeholder when selected_thread.grounded is true. "
            "Use this exact section order and titles:\n"
            f"{required_report_shape_text()}\n"
            "Keep it useful, specific, and honest."
        ),
        prompt=json.dumps(prompt, ensure_ascii=False)[:22000],
    )
    return text or None


def _normalize_report_text(packet: ContextPacket, text: str) -> str:
    text = _strip_fallback_status(text.strip())
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line.startswith("# "):
        title = "Private Mentor Report"
        if packet.request.strip():
            title = "Private Mentor Report"
        text = f"# {title}\n\n{text}"
    return text


def _strip_fallback_status(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith("> status:") and ("fallback" in lower or "smoke-test" in lower):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _safe_scaffold_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("```", "'''")
    value = value.replace("`", "'")
    value = value.replace("**", "")
    value = value.replace("__", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines = []
    for raw_line in value.splitlines():
        line = raw_line.replace("\t", " ").rstrip()
        if line.lstrip().startswith("#"):
            line = line.lstrip("#").strip()
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _selected_thread_payload(packet: ContextPacket, primary_thread: dict[str, str]) -> dict[str, object]:
    thread_id = str(primary_thread.get("thread_id") or "")
    thread_title = str(primary_thread.get("title") or thread_id)
    read = next((item for item in packet.authoritative_reads if str(item.get("path") or "").endswith(f"/state/threads/{thread_id}.md")), None)
    return {
        "action": str(primary_thread.get("action") or "create"),
        "thread_id": thread_id,
        "title": thread_title,
        "thread_candidate_count": len(packet.thread_candidates),
        "grounded": read is not None,
        "authoritative_excerpt": truncate(str((read or {}).get("excerpt") or ""), 500),
    }


def _search_payload(searches: list[SearchResult], *, limit: int) -> list[dict[str, Any]]:
    def priority(result: SearchResult) -> tuple[int, int, str]:
        if result.source == "search-digest":
            rank = 0
        elif result.fetch_status == "fetched" and result.reading_note:
            rank = 1
        elif result.fetch_status == "fetched":
            rank = 2
        elif result.source == "workspace-search" and result.status == "retrieved":
            rank = 3
        elif result.source == "local-state":
            rank = 4
        elif result.status in {"retrieved", "context"}:
            rank = 5
        else:
            rank = 9
        return (rank, -int(result.round_index or 0), result.source)

    payload: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    local_state_count = 0
    telemetry_count = 0
    ordered = sorted(searches, key=priority)
    for result in ordered:
        key = (
            result.source,
            result.title,
            truncate(result.query or "", 120),
            int(result.round_index or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        if result.source == "local-state":
            local_state_count += 1
            if local_state_count > 4:
                continue
        if result.status in {"failed", "no_results", "unavailable"}:
            telemetry_count += 1
            if telemetry_count > 4:
                continue
        payload.append(
            {
                "source": result.source,
                "title": result.title,
                "url": result.url,
                "query": result.query,
                "status": result.status,
                "round_index": result.round_index,
                "fetch_status": result.fetch_status,
                "summary": truncate(result.summary, 320),
                "fetched_excerpt": truncate(result.fetched_excerpt, 420),
                "reading_note": result.reading_note,
            }
        )
        if len(payload) >= limit:
            break
    return payload
