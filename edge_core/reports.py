from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import RuntimeConfig
from .context import ContextPacket
from .reviewers import LLMClient, ReviewResult, summarize_reviews
from .search import SearchResult
from .util import date_slug, slugify, truncate


@dataclass(frozen=True)
class ReportResult:
    text: str
    mode: str
    provider: str
    error: str = ""


def draft_report(packet: ContextPacket, searches: list[SearchResult], thread_id: str) -> ReportResult:
    client = LLMClient(role="report")
    llm_report = _llm_draft_report(client, packet, searches, thread_id)
    if llm_report:
        return ReportResult(text=_normalize_report_text(packet, llm_report), mode="llm", provider=client.last_provider, error=client.last_error)
    observations = "\n".join(f"- **{obs.source}:** {obs.title} — {truncate(obs.detail, 300)}" for obs in packet.observations[:12])
    reports = "\n".join(f"- {item.get('title')} ({item.get('path')})" for item in packet.report_candidates[:6]) or "- No previous report found."
    search_lines = "\n".join(f"- **{result.source}:** {result.title} {result.url} — {truncate(result.summary, 250)}" for result in searches)
    interests = "\n".join(f"- {item.get('area')}: {item.get('connection')}" for item in packet.interests[:5])
    text = f"""# {packet.kind.title()}: {packet.request}

> Status: deterministic scaffold fallback. No LLM returned report text for this draft; this output is only a structural smoke test.

## Thread

This beat continues or creates thread `{thread_id}`.

## Observed Context

{observations}

## Continuity

Candidate reports:

{reports}

## Simple Model

The mentor should start from the observed real work, identify the delta, and turn it into guidance that helps the mentee think and act better. If context is still thin, the report should say so instead of fabricating certainty.

## Broad Search

{search_lines}

## Relevant Phenotypic Interests

{interests or "- No configured interest."}

## Derivation

1. The current request/beat points to: {packet.request}
2. Recent context shows workspace evidence, report history, threads, and sessions.
3. The recommendation must continue a real thread or open a new one with justification.
4. The report must preserve the rite: broad search, adversarial review, Feynman review, and concrete next steps.

## Gaps

- Confirm whether the selected thread represents the correct live line of work.
- Confirm whether the configured external sources were sufficient or whether the runtime fell back locally.
- Confirm whether there is a previous report that should have been recovered but was not.

## Recommendation

Continue with a rich private consultation, anchored in the delta and without mutating the mentee workspace. The next step is to use this report as the basis for updating the thread and improving the next consultation.

## Next Steps

- Review whether the report adheres to the observed real work.
- Update the compact thread with the new understanding.
- If search degraded because credentials were missing, configure the phenotype sources.
"""
    return ReportResult(
        text=text,
        mode="deterministic-scaffold",
        provider=client.last_provider,
        error=client.last_error or "llm:no-report-text",
    )


def revise_report(packet: ContextPacket, searches: list[SearchResult], thread_id: str, draft: str, reviews: list[ReviewResult], *, stage: str) -> ReportResult:
    client = LLMClient(role="report")
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
        "stage": stage,
        "draft": draft[:14000],
        "review_feedback": feedback,
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "search_results": [result.__dict__ for result in searches[:10]],
        "first_steps": packet.first_steps,
        "interests": packet.interests,
    }
    text = client.complete_text(
        system=(
            "You are edge-of-chaos v2 revising a mentor report in a fixed straight-line rite. "
            "Rewrite the report in Markdown using the reviewer feedback as input, not as a pass/fail gate. "
            "Keep the mentor/mentee relationship, situated delta, continuity, broad-search evidence, adversarial pushback, "
            "Feynman derivation, explicit gaps, and concrete next steps. Return only the report."
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


def finalize_report(config: RuntimeConfig, *, packet: ContextPacket, draft: str, reviews: list[ReviewResult], thread_id: str) -> Path:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(f"{packet.kind}-{packet.request}")[:90]
    path = config.reports_dir / f"{date_slug()}-{slug}.md"
    final = draft.rstrip() + "\n\n## Reviews\n\n" + summarize_reviews(reviews) + "\n"
    path.write_text(final, encoding="utf-8")
    config.blog_entries_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, config.blog_entries_dir / path.name)
    return path


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


def build_blog(config: RuntimeConfig) -> Path:
    entries = sorted(config.blog_entries_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for path in entries:
        title = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        rows.append(f'<li><a href="entries/{html.escape(path.name)}">{html.escape(title)}</a></li>')
    index = config.root / "blog" / "index.html"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "<!doctype html><meta charset='utf-8'><title>edge reports</title>"
        "<style>body{font-family:system-ui;margin:3rem;max-width:820px}li{margin:.6rem 0}</style>"
        "<h1>edge-of-chaos reports</h1><ul>" + "\n".join(rows) + "</ul>",
        encoding="utf-8",
    )
    return index


def _llm_draft_report(client: LLMClient, packet: ContextPacket, searches: list[SearchResult], thread_id: str) -> str | None:
    prompt = {
        "kind": packet.kind,
        "request": packet.request,
        "thread_id": thread_id,
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "first_steps": packet.first_steps,
        "seed_threads": packet.seed_threads,
        "interests": packet.interests,
        "routines": packet.routines,
        "search_results": [result.__dict__ for result in searches[:10]],
    }
    text = client.complete_text(
        system=(
            "You are edge-of-chaos v2, a private Feynman mentor. Write a rich private mentor report in Markdown. "
            "Do not write dashboard copy. Do not sound like a product brochure. "
            "The report must be situated in the observed work, continue or justify the thread, explain the simple model, "
            "derive the reasoning, cite search/source evidence including unavailable sources, state gaps, give pushback, "
            "and end with concrete next steps. Keep it useful, specific, and honest."
        ),
        prompt=str(prompt)[:22000],
    )
    return text or None


def _normalize_report_text(packet: ContextPacket, text: str) -> str:
    text = _strip_fallback_status(text.strip())
    if not text.lstrip().startswith("#"):
        text = f"# {packet.kind.title()}: {packet.request}\n\n{text}"
    return text


def _strip_fallback_status(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith("> status:") and ("fallback" in lower or "smoke-test" in lower):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
