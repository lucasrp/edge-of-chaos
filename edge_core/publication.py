from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import html
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .config import RuntimeConfig
from .context import ContextPacket
from .report_shape import REPORT_SECTION_TITLES, validate_report_markdown, validate_section_body
from .reviewers import ReviewResult, summarize_reviews
from .search import SearchResult
from .util import date_slug, slugify, truncate


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: list[str]


@dataclass(frozen=True)
class PublishedArtifacts:
    report_markdown_path: Path
    report_spec_path: Path
    report_html_path: Path
    blog_entry_markdown_path: Path
    blog_entry_html_path: Path
    blog_report_html_path: Path


_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_NUMBERED_RE = re.compile(r"^\d+\.\s+")
_EMPTY_THREAD_CLAIM_RE = re.compile(r"(thread_candidates?\s+(?:arrived\s+)?empty|empty\s+thread_candidates?)", flags=re.I)
_SVG_BLOCK_TYPES = {"bar-chart", "line-chart", "raw-html"}


def publish_artifact_bundle(
    config: RuntimeConfig,
    *,
    packet: ContextPacket,
    report_markdown: str,
    searches: list[SearchResult],
    reviews: list[ReviewResult],
    thread_id: str,
    thread_title: str,
    thread_action: str,
) -> PublishedArtifacts:
    request_slug = packet.request.strip() or f"run-a-{packet.kind}-beat"
    stem = f"{date_slug()}-{slugify(f'{packet.kind}-{request_slug}')[:90]}"
    report_md_path = config.reports_dir / f"{stem}.md"
    report_spec_path = config.reports_dir / f"{stem}.yaml"
    report_html_path = config.reports_dir / f"{stem}.html"
    blog_entry_md_path = config.blog_entries_dir / f"{stem}.md"
    blog_entry_html_path = config.blog_entries_dir / f"{stem}.html"
    blog_report_html_path = config.blog_reports_dir / report_html_path.name

    report_shape = validate_report_markdown(report_markdown)
    spec = build_report_spec(
        packet=packet,
        report_markdown=report_markdown,
        searches=searches,
        reviews=reviews,
        thread_id=thread_id,
        thread_title=thread_title,
        thread_action=thread_action,
        shape=report_shape,
    )
    report_shape_result = validate_report_spec(spec)
    blog_shape_result = validate_blog_post(spec.get("blog_post"))
    if not report_shape_result.passed or not blog_shape_result.passed:
        issues = [*report_shape_result.issues, *blog_shape_result.issues]
        raise RuntimeError(f"artifact validation failed: {'; '.join(issues)}")

    config.reports_dir.mkdir(parents=True, exist_ok=True)
    config.blog_entries_dir.mkdir(parents=True, exist_ok=True)
    config.blog_reports_dir.mkdir(parents=True, exist_ok=True)

    report_md = report_markdown.rstrip() + "\n\n## Reviews\n\n" + summarize_reviews(reviews) + "\n"
    report_md_path.write_text(report_md, encoding="utf-8")
    report_spec_path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    report_html_path.write_text(render_report_html(spec), encoding="utf-8")
    shutil.copyfile(report_html_path, blog_report_html_path)

    entry_markdown = _render_blog_entry_markdown(
        spec=spec,
        report_html_name=blog_report_html_path.name,
        report_md_name=report_md_path.name,
        report_spec_name=report_spec_path.name,
        thread_id=thread_id,
        kind=packet.kind,
    )
    blog_entry_md_path.write_text(entry_markdown, encoding="utf-8")

    metadata, body = _parse_frontmatter(entry_markdown)
    blog_entry_html_path.write_text(
        render_blog_entry_html(metadata=metadata, body=body, report_href=f"../reports/{blog_report_html_path.name}"),
        encoding="utf-8",
    )
    return PublishedArtifacts(
        report_markdown_path=report_md_path,
        report_spec_path=report_spec_path,
        report_html_path=report_html_path,
        blog_entry_markdown_path=blog_entry_md_path,
        blog_entry_html_path=blog_entry_html_path,
        blog_report_html_path=blog_report_html_path,
    )


def build_report_spec(
    *,
    packet: ContextPacket,
    report_markdown: str,
    searches: list[SearchResult],
    reviews: list[ReviewResult],
    thread_id: str,
    thread_title: str,
    thread_action: str,
    shape: Any | None = None,
) -> dict[str, Any]:
    shape = shape or validate_report_markdown(report_markdown)
    section_map = shape.section_map()
    thread_read_confirmed = any(str(item.get("path") or "").endswith(f"/state/threads/{thread_id}.md") for item in packet.authoritative_reads)
    metrics = _build_metrics(packet, searches, reviews)
    sections = _build_sections(packet=packet, sections=section_map, searches=searches, reviews=reviews, metrics=metrics)
    bibliography = _build_bibliography(searches)
    visualization_count = _count_visualizations(sections)
    return {
        "title": shape.title or "Private Mentor Report",
        "subtitle": f"{packet.kind.title()} beat for thread '{thread_title}'",
        "date": date_slug(),
        "thread": {"id": thread_id, "title": thread_title, "action": thread_action},
        "kind": packet.kind,
        "request": packet.request,
        "executive_summary": _build_executive_summary(section_map),
        "metrics": metrics,
        "sections": sections,
        "bibliography": bibliography,
        "evidence": {
            "thread_read_confirmed": thread_read_confirmed,
            "thread_candidate_count": len(packet.thread_candidates),
            "authoritative_paths": [str(item.get("path") or "") for item in packet.authoritative_reads[:12] if str(item.get("path") or "").strip()],
            "visualization_count": visualization_count,
            "search_feedback_rounds": _search_feedback_round_count(reviews),
        },
        "blog_post": {
            "title": _blog_entry_title(packet=packet, thread_title=thread_title),
            "paragraphs": _build_blog_post_paragraphs(packet=packet, sections=section_map, thread_title=thread_title),
        },
    }


def validate_report_spec(spec: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    for field in ["title", "subtitle", "date", "thread", "executive_summary", "metrics", "sections", "bibliography", "evidence", "blog_post"]:
        if field not in spec:
            issues.append(f"missing spec field: {field}")

    thread = spec.get("thread")
    if not isinstance(thread, dict) or not str(thread.get("id") or "").strip() or not str(thread.get("title") or "").strip():
        issues.append("invalid spec.thread")
    elif str(thread.get("action") or "").strip() not in {"create", "continue"}:
        issues.append("invalid spec.thread.action")

    summary = spec.get("executive_summary")
    if not isinstance(summary, list) or len(summary) < 3 or any(not str(item).strip() for item in summary):
        issues.append("executive_summary must have at least 3 non-empty items")

    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or len(metrics) < 4:
        issues.append("metrics must have at least 4 items")
    else:
        for item in metrics:
            if not isinstance(item, dict) or not str(item.get("value") or "").strip() or not str(item.get("label") or "").strip():
                issues.append("invalid metric item")
                break

    sections = spec.get("sections")
    joined_markdown = ""
    visualization_count = 0
    broad_search_feedback = 0
    if not isinstance(sections, list):
        issues.append("sections must be a list")
    else:
        titles = [str(item.get("title") or "").strip() for item in sections if isinstance(item, dict)]
        cursor = -1
        for required in REPORT_SECTION_TITLES:
            try:
                cursor = titles.index(required, cursor + 1)
            except ValueError:
                issues.append(f"missing spec section: {required}")
        for item in sections:
            if not isinstance(item, dict):
                issues.append("invalid section entry")
                break
            title = str(item.get("title") or "").strip()
            lead = str(item.get("lead") or "").strip()
            body = str(item.get("markdown") or "").strip()
            blocks = item.get("blocks")
            if not lead or len(re.sub(r"\s+", " ", lead)) < 40:
                issues.append(f"missing or thin lead: {title}")
            if not body:
                issues.append(f"empty spec section: {title}")
            else:
                issues.extend(validate_section_body(title, body))
                joined_markdown += "\n\n" + body
            if not isinstance(blocks, list) or not blocks:
                issues.append(f"missing section blocks: {title}")
                continue
            visualization_count += sum(1 for block in blocks if _is_visual_block(block))
            if title == "Broad Search":
                broad_search_feedback = sum(1 for block in blocks if str(block.get("type") or "") == "callout" and str(block.get("title") or "").startswith("Search Feedback"))
            if title == "Contextualization and Glossary" and not any(str(block.get("type") or "") == "glossary" for block in blocks):
                issues.append("last section must include glossary block")
            if title == "What I Don't Know" and not any(str(block.get("type") or "") in {"list", "table", "callout"} for block in blocks):
                issues.append("What I Don't Know needs explicit gap blocks")
            if title == "Broad Search":
                block_types = {str(block.get("type") or "") for block in blocks}
                if "table" not in block_types:
                    issues.append("Broad Search must include source coverage table")
                if not block_types.intersection({"bar-chart", "line-chart", "raw-html"}):
                    issues.append("Broad Search must include at least one visualization")

    bibliography = spec.get("bibliography")
    if not isinstance(bibliography, list) or not bibliography:
        issues.append("bibliography must be non-empty")
    else:
        for item in bibliography:
            if not isinstance(item, dict):
                issues.append("invalid bibliography item")
                break
            for field in ["text", "url", "source"]:
                if not str(item.get(field) or "").strip():
                    issues.append(f"bibliography item missing {field}")
                    break

    evidence = spec.get("evidence")
    if not isinstance(evidence, dict):
        issues.append("invalid evidence block")
    else:
        authoritative_paths = evidence.get("authoritative_paths")
        if not isinstance(authoritative_paths, list) or not authoritative_paths:
            issues.append("evidence.authoritative_paths must be non-empty")
        thread_candidate_count = evidence.get("thread_candidate_count")
        if not isinstance(thread_candidate_count, int) or thread_candidate_count < 0:
            issues.append("evidence.thread_candidate_count must be a non-negative integer")
        thread_read_confirmed = evidence.get("thread_read_confirmed")
        if not isinstance(thread_read_confirmed, bool):
            issues.append("evidence.thread_read_confirmed must be boolean")
        elif isinstance(thread, dict) and str(thread.get("action") or "") == "continue" and not thread_read_confirmed:
            issues.append("continued thread lacks authoritative in-beat read")
        if isinstance(thread_candidate_count, int) and thread_candidate_count > 0 and _EMPTY_THREAD_CLAIM_RE.search(joined_markdown):
            issues.append("report claims empty thread candidates despite non-empty evidence bundle")
        if int(evidence.get("visualization_count") or 0) < 1:
            issues.append("report spec requires at least one visualization")
        if int(evidence.get("search_feedback_rounds") or 0) < 5:
            issues.append("report spec requires search feedback from every LLM review stage")

    if visualization_count < 1:
        issues.append("report spec requires at least one visualization block")
    if broad_search_feedback < 5:
        issues.append("Broad Search must preserve reviewer search feedback from every LLM review stage")
    return ValidationResult(passed=not issues, issues=issues)


def validate_blog_post(blog_post: Any) -> ValidationResult:
    issues: list[str] = []
    if not isinstance(blog_post, dict):
        return ValidationResult(False, ["blog_post must be a mapping"])
    if not str(blog_post.get("title") or "").strip():
        issues.append("blog_post.title is required")
    paragraphs = blog_post.get("paragraphs")
    if not isinstance(paragraphs, list) or not (2 <= len(paragraphs) <= 4):
        issues.append("blog_post.paragraphs must have 2 to 4 items")
    else:
        for paragraph in paragraphs:
            text = str(paragraph or "").strip()
            if not text:
                issues.append("blog_post contains an empty paragraph")
                continue
            if text.startswith("#") or text.startswith("- ") or "```" in text:
                issues.append("blog_post paragraphs must be plain invitation prose")
                break
    return ValidationResult(passed=not issues, issues=issues)


def build_blog(config: RuntimeConfig) -> Path:
    entries = sorted(config.blog_entries_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    config.blog_reports_dir.mkdir(parents=True, exist_ok=True)
    for path in entries:
        metadata, body = _parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        title = str(metadata.get("title") or path.stem)
        report_html = str(metadata.get("report_html") or "")
        entry_html = path.with_suffix(".html")
        entry_html.write_text(
            render_blog_entry_html(metadata=metadata, body=body, report_href=f"../reports/{report_html}" if report_html else "../"),
            encoding="utf-8",
        )
        excerpt = truncate(" ".join(_paragraphs_from_body(body)[:1]), 180)
        date = str(metadata.get("date") or "")
        rows.append(
            "<article class='entry-card'>"
            f"<p class='entry-date'>{html.escape(date)}</p>"
            f"<h2><a href='entries/{html.escape(entry_html.name)}'>{html.escape(title)}</a></h2>"
            f"<p>{html.escape(excerpt)}</p>"
            "</article>"
        )
    index = config.root / "blog" / "index.html"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "<!doctype html><meta charset='utf-8'><title>edge reports</title>"
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700&display=swap');"
        "body{font-family:'Libre Franklin',system-ui,sans-serif;max-width:980px;margin:3rem auto;padding:0 1.4rem;line-height:1.65;color:#374151;background:#f9fafb}"
        "h1{margin-bottom:1.75rem;color:#1a3560}.entry-card{padding:1.15rem 0;border-top:1px solid #dbe4f2}"
        ".entry-card:first-of-type{border-top:0;padding-top:0}.entry-card h2{margin:.25rem 0;color:#1a3560}.entry-date{color:#6b7280;font-size:.92rem;margin:0}"
        "a{color:#1c519b;text-decoration:none}a:hover{text-decoration:underline}"
        "</style>"
        "<h1>edge-of-chaos reports</h1>"
        + "\n".join(rows),
        encoding="utf-8",
    )
    return index


def render_report_html(spec: dict[str, Any]) -> str:
    title = html.escape(str(spec.get("title") or "Private Mentor Report"))
    subtitle = html.escape(str(spec.get("subtitle") or ""))
    date_text = html.escape(str(spec.get("date") or ""))
    thread_title = html.escape(str((spec.get("thread") or {}).get("title") or ""))
    parts = [
        "<!doctype html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"  <title>{title}</title>",
        "  <style>",
        _report_css(),
        "  </style>",
        "</head>",
        "<body>",
        "  <header class='report-header'>",
        "    <div class='header-content'>",
        "      <div class='header-text'>",
        f"        <h1>{title}</h1>",
        f"        <p class='subtitle'>{subtitle}</p>",
        f"        <p class='meta'>{date_text} · Thread: {thread_title}</p>",
        "      </div>",
        "    </div>",
        "    <div class='header-stripe'></div>",
        "  </header>",
        "  <main class='report-content'>",
        "    <section class='section'>",
        "      <h2 class='section-title'>Executive Summary</h2>",
        "      <div class='card'><ul class='summary-list'>",
    ]
    for item in spec.get("executive_summary") or []:
        parts.append(f"        <li>{_render_inline(str(item))}</li>")
    parts.extend(["      </ul></div>", "    </section>"])

    parts.append("    <section class='section'>")
    parts.append("      <h2 class='section-title'>Metrics</h2>")
    parts.append(_render_block({"type": "metrics-grid", "items": spec.get("metrics") or []}))
    metrics_chart = {
        "type": "bar-chart",
        "title": "Artifact Metrics Snapshot",
        "unit": "count",
        "items": [{"label": str(item.get("label") or ""), "value": _safe_int(item.get("value"))} for item in (spec.get("metrics") or [])[:6]],
    }
    parts.append(_render_block(metrics_chart))
    parts.append("    </section>")

    for section in spec.get("sections") or []:
        parts.append(_render_section(section))

    parts.append("    <section class='section'>")
    parts.append("      <h2 class='section-title'>References</h2>")
    parts.append("      <p class='section-lead'>Sources that shaped the report, including external search results and local evidence surfaced during the beat.</p>")
    parts.append(_render_block({"type": "bibliography", "references": spec.get("bibliography") or []}))
    parts.append("    </section>")
    parts.extend(["  </main>", "</body>", "</html>"])
    return "\n".join(parts) + "\n"


def render_blog_entry_html(*, metadata: dict[str, Any], body: str, report_href: str) -> str:
    title = html.escape(str(metadata.get("title") or "edge-of-chaos entry"))
    paragraphs = _paragraphs_from_body(body)
    parts = [
        "<!doctype html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='utf-8'>",
        f"  <title>{title}</title>",
        "  <style>"
        "@import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700&display=swap');"
        "body{font-family:'Libre Franklin',system-ui,sans-serif;max-width:760px;margin:2.5rem auto;padding:0 1.25rem;line-height:1.65;color:#17202a;background:#f9fafb}"
        "header{margin-bottom:1.8rem}.meta{color:#52606d;font-size:.95rem}.cta{margin-top:1.6rem;padding:1rem 1.1rem;border:1px solid #d7dce4;border-radius:8px;background:#f8fafc}"
        "a{color:#1c519b;text-decoration:none}a:hover{text-decoration:underline}"
        "  </style>",
        "</head>",
        "<body>",
        "<header>",
        f"  <h1>{title}</h1>",
        f"  <p class='meta'>{html.escape(str(metadata.get('date') or ''))}</p>",
        "</header>",
    ]
    for paragraph in paragraphs:
        parts.append(f"<p>{_render_inline(paragraph)}</p>")
    parts.append(
        "<div class='cta'>"
        f"<p><strong>Open the full report:</strong> <a href='{html.escape(report_href)}'>{html.escape(str(metadata.get('report_html') or 'report.html'))}</a></p>"
        "</div>"
    )
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts) + "\n"


def _build_metrics(packet: ContextPacket, searches: list[SearchResult], reviews: list[ReviewResult]) -> list[dict[str, str]]:
    feedback_count = _search_feedback_round_count(reviews)
    raw_searches = [item for item in searches if item.source != "search-digest"]
    fetched_count = sum(1 for item in raw_searches if item.fetch_status == "fetched")
    return [
        {"value": str(len(packet.observations)), "label": "Context observations"},
        {"value": str(len(raw_searches)), "label": "Search artifacts"},
        {"value": str(fetched_count), "label": "Fetched documents"},
        {"value": str(len({item.source for item in raw_searches})), "label": "Search sources"},
        {"value": str(len(packet.thread_candidates)), "label": "Recovered threads"},
        {"value": str(feedback_count), "label": "Search feedback rounds"},
        {"value": str(len(packet.authoritative_reads)), "label": "Authoritative reads"},
    ]


def _build_sections(
    *,
    packet: ContextPacket,
    sections: dict[str, str],
    searches: list[SearchResult],
    reviews: list[ReviewResult],
    metrics: list[dict[str, str]],
) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []
    for title in REPORT_SECTION_TITLES:
        body = sections.get(title, "").strip()
        if title == "Lineage":
            built.append(_build_lineage_section(packet, title, body))
        elif title == "Broad Search":
            built.append(_build_broad_search_section(packet, title, body, searches, reviews, metrics))
        elif title == "Adversarial Pushback":
            built.append(_build_adversarial_section(title, body, reviews))
        elif title == "What I Don't Know":
            built.append(_build_unknowns_section(title, body))
        elif title == "Contextualization and Glossary":
            built.append(_build_glossary_section(title, body))
        else:
            built.append(_build_generic_section(title, body))
    return built


def _build_lineage_section(packet: ContextPacket, title: str, body: str) -> dict[str, Any]:
    rows: list[list[str]] = []
    for candidate in packet.report_candidates[:3]:
        rows.append([
            str(candidate.get("title") or Path(str(candidate.get("path") or "")).name),
            _first_sentence(str(candidate.get("summary") or "")),
            "Recent artifact that materially informs the current beat.",
        ])
    for item in packet.authoritative_reads[:2]:
        if str(item.get("source") or "") == "thread":
            rows.append([
                str(item.get("title") or "thread"),
                _first_sentence(str(item.get("excerpt") or "")),
                "Authoritative thread read that grounds continuity.",
            ])
    blocks = _markdown_to_blocks(body)
    if rows:
        blocks.append(
            {
                "type": "table",
                "title": "Reasoning Lineage",
                "headers": ["Previous Action", "What It Brought", "Connection to This Work"],
                "rows": rows,
            }
        )
    return {"title": title, "lead": _section_lead(title, body), "markdown": body, "blocks": blocks}


def _build_broad_search_section(
    packet: ContextPacket,
    title: str,
    body: str,
    searches: list[SearchResult],
    reviews: list[ReviewResult],
    metrics: list[dict[str, str]],
) -> dict[str, Any]:
    raw_searches = [result for result in searches if result.source != "search-digest"]
    counts = Counter(result.source for result in raw_searches)
    feedback = _search_feedback_entries(reviews)
    fetched = [result for result in raw_searches if result.fetch_status == "fetched"]
    digests = [result for result in searches if result.source == "search-digest" and result.reading_note]
    blocks: list[dict[str, Any]] = [
        {
            "type": "metrics-grid",
            "items": [
                {"value": str(len(raw_searches)), "label": "Total search artifacts"},
                {"value": str(len(fetched)), "label": "Fetched documents"},
                {"value": str(len(counts)), "label": "Sources touched"},
                {"value": str(sum(1 for item in packet.search_source_manifest if item.get("available"))), "label": "Available surfaces"},
                {"value": str(sum(1 for item in packet.search_source_manifest if not item.get("available"))), "label": "Unavailable surfaces"},
            ],
        },
        {
            "type": "table",
            "title": "Search Surface Manifest",
            "headers": ["Surface", "Enabled", "Available", "Credential", "Notes"],
            "rows": [
                [
                    str(item.get("name") or ""),
                    "yes" if item.get("enabled", True) else "no",
                    "yes" if item.get("available") else "no",
                    str(item.get("credential") or "n/a"),
                    _surface_note(item, metrics),
                ]
                for item in packet.search_source_manifest
            ],
        },
        {
            "type": "bar-chart",
            "title": "Search Results by Source",
            "unit": "artifacts",
            "items": [{"label": source, "value": count} for source, count in counts.most_common()],
        },
    ]
    blocks.extend(_markdown_to_blocks(body))
    if fetched:
        rows = []
        for result in fetched[:8]:
            note = result.reading_note if isinstance(result.reading_note, dict) else {}
            rows.append(
                [
                    result.source,
                    truncate(result.title, 90),
                    truncate(str(note.get("summary") or result.summary), 180),
                    truncate(str(note.get("why_it_matters") or result.fetched_excerpt), 180),
                ]
            )
        blocks.append(
            {
                "type": "table",
                "title": "Fetched Evidence",
                "headers": ["Source", "Document", "What It Says", "Why It Matters"],
                "rows": rows,
            }
        )
        for result in fetched[:4]:
            note = result.reading_note if isinstance(result.reading_note, dict) else {}
            claims = note.get("useful_claims") if isinstance(note, dict) else []
            title_text = f"Reading Note — {result.source}: {truncate(result.title, 70)}"
            blocks.append(
                {
                    "type": "callout",
                    "variant": "info",
                    "title": title_text,
                    "text": truncate(str(note.get("summary") or result.summary), 420),
                }
            )
            if claims:
                blocks.append(
                    {
                        "type": "list",
                        "title": f"{title_text} — Useful Claims",
                        "items": [truncate(str(item), 240) for item in claims[:4]],
                    }
                )
    for digest in digests[:3]:
        note = digest.reading_note if isinstance(digest.reading_note, dict) else {}
        blocks.append(
            {
                "type": "callout",
                "variant": "info",
                "title": digest.title,
                "text": truncate(str(note.get("summary") or digest.summary), 500),
            }
        )
        evidence = note.get("evidence_worth_using") if isinstance(note, dict) else []
        if evidence:
            blocks.append(
                {
                    "type": "list",
                    "title": f"{digest.title} — Evidence Worth Using",
                    "items": [truncate(str(item), 260) for item in evidence[:5]],
                }
            )
    for entry in feedback:
        blocks.append(
            {
                "type": "callout",
                "variant": "info",
                "title": entry["title"],
                "text": entry["summary"],
            }
        )
        if entry["queries"]:
            blocks.append(
                {
                    "type": "list",
                    "title": f"{entry['title']} — Suggested Queries",
                    "items": entry["queries"],
                }
            )
        if entry["surfaces"]:
            blocks.append(
                {
                    "type": "list",
                    "title": f"{entry['title']} — Suggested Surfaces",
                    "items": entry["surfaces"],
                }
            )
    source_rows = []
    for result in raw_searches[:12]:
        source_rows.append([result.source, truncate(result.title, 90), truncate(result.summary, 180)])
    if source_rows:
        blocks.append({"type": "table", "title": "Observed Search Artifacts", "headers": ["Source", "Artifact", "Signal"], "rows": source_rows})
    return {"title": title, "lead": _section_lead(title, body, fallback="This section preserves the multi-round search flow: surface availability, reviewer feedback about missed exploration, and the resulting evidence bundle that the report actually used."), "markdown": body, "blocks": blocks}


def _build_adversarial_section(title: str, body: str, reviews: list[ReviewResult]) -> dict[str, Any]:
    blocks = _markdown_to_blocks(body)
    for review in reviews:
        if "adversarial" not in review.reviewer:
            continue
        label = f"Adversarial Review Round {review.data.get('round')}" if isinstance(review.data, dict) and review.data.get("round") else "Adversarial Review"
        blocks.append({"type": "callout", "variant": "warning", "title": label, "text": review.summary})
    return {"title": title, "lead": _section_lead(title, body), "markdown": body, "blocks": blocks}


def _build_unknowns_section(title: str, body: str) -> dict[str, Any]:
    bullets = _extract_bullets(body)
    blocks = _markdown_to_blocks(body)
    if bullets:
        rows = [[item, "Resolve with direct read, fresh search, or explicit operator confirmation."] for item in bullets]
        blocks.append({"type": "table", "title": "Open Gaps", "headers": ["Unknown", "Need"], "rows": rows})
    blocks.append({"type": "callout", "variant": "danger", "title": "Do Not Collapse Uncertainty", "text": "Unknowns remain first-class output. They should shape the next beat rather than being rounded away by prose."})
    return {"title": title, "lead": _section_lead(title, body), "markdown": body, "blocks": blocks}


def _build_glossary_section(title: str, body: str) -> dict[str, Any]:
    blocks = _markdown_to_blocks(body)
    glossary_terms = _extract_glossary_terms(body)
    blocks.append({"type": "glossary", "context": "This section keeps the report readable even when the body stays dense and domain-specific.", "terms": glossary_terms})
    return {"title": title, "lead": _section_lead(title, body), "markdown": body, "blocks": blocks}


def _build_generic_section(title: str, body: str) -> dict[str, Any]:
    return {"title": title, "lead": _section_lead(title, body), "markdown": body, "blocks": _markdown_to_blocks(body)}


def _build_executive_summary(sections: dict[str, str]) -> list[str]:
    desired = ["Situated Delta", "Problem Framing and Open Gaps", "Why This Matters Now"]
    items = [_section_takeaway(sections.get(title, "")) for title in desired]
    filtered = [item for item in items if item]
    while len(filtered) < 3:
        filtered.append("The beat preserved continuity, surfaced search pressure, and ended with concrete next steps.")
    return filtered[:3]


def _build_bibliography(searches: list[SearchResult]) -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for result in searches:
        if result.source == "search-digest":
            continue
        if result.status not in {"retrieved", "context"}:
            continue
        key = str(result.url).strip() or f"{result.source}:{result.title}"
        if key in seen:
            continue
        seen.add(key)
        items.append({"text": str(result.title or result.url or result.source), "url": str(result.url or "https://example.invalid"), "source": str(result.source)})
        if len(items) >= 12:
            break
    if not items:
        items.append({"text": "No external source survived validation", "url": "https://example.invalid", "source": "runtime"})
    return items


def _blog_entry_title(*, packet: ContextPacket, thread_title: str) -> str:
    request = packet.request.strip() or f"{packet.kind} beat"
    return f"{request.title()} · {thread_title}"


def _build_blog_post_paragraphs(*, packet: ContextPacket, sections: dict[str, str], thread_title: str) -> list[str]:
    delta = _section_takeaway(sections.get("Situated Delta", ""))
    why_now = _section_takeaway(sections.get("Why This Matters Now", ""))
    next_steps = _section_takeaway(sections.get("Recommended Next Steps", ""))
    request = packet.request.strip() or f"{packet.kind} beat"
    return [
        f"This entry sits on the thread '{thread_title}' and captures what changed in the current {request}. {delta}",
        f"{why_now}",
        f"Open the full report for the formal problem framing, the Feynman derivation, the search feedback loops, and the concrete next steps. {next_steps}",
    ]


def _render_blog_entry_markdown(*, spec: dict[str, Any], report_html_name: str, report_md_name: str, report_spec_name: str, thread_id: str, kind: str) -> str:
    blog_post = spec.get("blog_post") or {}
    paragraphs = blog_post.get("paragraphs") or []
    frontmatter = {
        "date": spec.get("date"),
        "title": blog_post.get("title"),
        "report_html": report_html_name,
        "report_markdown": report_md_name,
        "report_spec": report_spec_name,
        "thread_id": thread_id,
        "tags": [kind, "mentor-report"],
        "status": "approved",
    }
    body = "\n\n".join(str(item).strip() for item in paragraphs if str(item).strip())
    return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}\n---\n\n{body}\n"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    if not value.startswith("---\n"):
        return {}, value.strip()
    parts = value.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, value.strip()
    metadata = yaml.safe_load(parts[0][4:]) or {}
    return metadata if isinstance(metadata, dict) else {}, parts[1].strip()


def _paragraphs_from_body(body: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", body.strip()) if block.strip()]


def _section_takeaway(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", normalized)
    if match:
        return truncate(match.group(1), 220)
    return truncate(normalized, 220)


def _section_lead(title: str, body: str, fallback: str | None = None) -> str:
    first = _first_sentence(body)
    if len(first) >= 40:
        return first
    if fallback:
        return fallback
    return {
        "Lineage": "This section shows the chain of prior artifacts and reads that made the current beat legible, so continuity remains evidence-backed rather than gestural.",
        "Situated Delta": "This section isolates what changed in the current situation and separates concrete movement from background noise before the report widens its explanation.",
        "Problem Framing and Open Gaps": "This section states the live problem before solutions expand and keeps the missing evidence visible instead of letting later prose flatten it.",
        "Simple Model": "This section compresses the moving parts into a simple model that can survive scrutiny before the report adds search pressure or recommendations.",
        "Feynman Derivation": "This section derives the explanation from first principles, showing where the reasoning holds and where it still depends on open questions.",
        "Why This Matters Now": "This section explains the timing pressure: why the issue is worth attention in the current beat rather than as generic background context.",
        "Broad Search": "This section preserves the broad search loop explicitly: surfaces available, reviewer feedback about missed exploration, and what evidence actually made it into the bundle.",
        "Adversarial Pushback": "This section keeps the strongest objections inside the report so the final recommendation has to survive contact with criticism.",
        "Recommended Next Steps": "This section turns the report into executable movement by naming the smallest next actions that would reduce uncertainty or improve the mentee's position.",
        "What I Don't Know": "This section keeps unresolved uncertainty explicit so the report does not pretend to know more than the evidence can support.",
        "Contextualization and Glossary": "This section translates the dense parts of the report back into shared context and practical definitions so the artifact stays reusable.",
    }.get(title, "This section explains what matters, what evidence was used, and how the reader should interpret the blocks below.")


def _markdown_to_blocks(text: str) -> list[dict[str, Any]]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", (text or "").strip()) if block.strip()]
    rendered: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("- ") for line in lines):
            rendered.append({"type": "list", "items": [line.lstrip()[2:].strip() for line in lines]})
            continue
        if all(_NUMBERED_RE.match(line.strip()) for line in lines):
            rendered.append({"type": "list", "ordered": True, "items": [_NUMBERED_RE.sub("", line.strip()).strip() for line in lines]})
            continue
        rendered.append({"type": "paragraph", "text": " ".join(line.strip() for line in lines)})
    return rendered or [{"type": "paragraph", "text": text.strip() or "No content."}]


def _extract_bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _extract_glossary_terms(text: str) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []
    for item in _extract_bullets(text):
        clean = item
        if clean.startswith("`") and "`:" in clean:
            term, definition = clean.split("`:", 1)
            terms.append({"term": term.strip("` ").strip(), "definition": definition.strip()})
            continue
        if ":" in clean:
            term, definition = clean.split(":", 1)
            terms.append({"term": term.strip("` ").strip(), "definition": definition.strip()})
    if not terms:
        terms.append({"term": "context", "definition": "No explicit glossary terms were parsed from the current report body; the glossary remains as a readable context anchor."})
    return terms[:12]


def _first_sentence(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", normalized)
    if match:
        return truncate(match.group(1), 280)
    return truncate(normalized, 280)


def _search_feedback_entries(reviews: list[ReviewResult]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for review in reviews:
        reviewer = str(review.reviewer)
        data = review.data if isinstance(review.data, dict) else {}
        if "context-search" not in reviewer and "adversarial" not in reviewer and "feynman-review" not in reviewer:
            continue
        round_label = data.get("round")
        title = "Search Feedback"
        if "context-search" in reviewer:
            title = f"Search Feedback — Continuity Round {round_label or '?'}"
        elif "adversarial" in reviewer:
            title = f"Search Feedback — Adversarial Round {round_label or '?'}"
        elif "feynman-review" in reviewer:
            title = "Search Feedback — Feynman Review"
        entries.append(
            {
                "title": title,
                "summary": truncate(str(review.summary or ""), 420),
                "queries": _normalize_suggestions(data, ["suggested_queries", "search_queries", "recommended_queries"]),
                "surfaces": _normalize_suggestions(data, ["suggested_sources"]),
            }
        )
    return entries


def _normalize_suggestions(data: dict[str, Any], keys: list[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = data.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    if item.get("query"):
                        values.append(str(item.get("query")))
                    elif item.get("name"):
                        values.append(str(item.get("name")))
                    elif item.get("source"):
                        values.append(str(item.get("source")))
                    elif item.get("why"):
                        values.append(str(item.get("why")))
                elif item:
                    values.append(str(item))
        elif isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped[:6]


def _search_feedback_round_count(reviews: list[ReviewResult]) -> int:
    count = 0
    for review in reviews:
        if "context-search" in review.reviewer or "adversarial" in review.reviewer or "feynman-review" in review.reviewer:
            count += 1
    return count


def _surface_note(item: dict[str, Any], metrics: list[dict[str, str]]) -> str:
    name = str(item.get("name") or "")
    if item.get("available"):
        return f"{name} was visible to the broad search loop and available for reviewer critique."
    return f"{name} was unavailable; reviewers should treat missing exploration here as configuration or surface loss, not as silent success."


def _count_visualizations(sections: list[dict[str, Any]]) -> int:
    count = 0
    for section in sections:
        for block in section.get("blocks") or []:
            if _is_visual_block(block):
                count += 1
    return count


def _is_visual_block(block: dict[str, Any]) -> bool:
    block_type = str(block.get("type") or "")
    if block_type in {"bar-chart", "line-chart"}:
        return True
    if block_type == "raw-html" and "<svg" in str(block.get("content") or ""):
        return True
    return False


def _render_section(section: dict[str, Any]) -> str:
    title = html.escape(str(section.get("title") or "Section"))
    lead = str(section.get("lead") or "").strip()
    parts = ["    <section class='section'>", f"      <h2 class='section-title'>{title}</h2>"]
    if lead:
        parts.append(f"      <p class='section-lead'>{_render_inline(lead)}</p>")
    for block in section.get("blocks") or []:
        parts.append(_render_block(block))
    parts.append("    </section>")
    return "\n".join(parts)


def _render_block(block: dict[str, Any]) -> str:
    block_type = str(block.get("type") or "paragraph")
    if block_type == "paragraph":
        return f"      <p>{_render_inline(str(block.get('text') or ''))}</p>"
    if block_type == "subsection":
        return f"      <h3 class='subsection-title'>{_render_inline(str(block.get('title') or ''))}</h3>"
    if block_type == "list":
        tag = "ol" if block.get("ordered") else "ul"
        items = "".join(f"<li>{_render_inline(str(item))}</li>" for item in block.get("items") or [])
        title = f"<p class='block-title'>{_render_inline(str(block.get('title') or ''))}</p>" if block.get("title") else ""
        return f"      <div class='block'>{title}<{tag}>{items}</{tag}></div>"
    if block_type == "callout":
        variant = html.escape(str(block.get("variant") or "info"))
        title = f"<strong>{_render_inline(str(block.get('title') or ''))}</strong><br>" if block.get("title") else ""
        return f"      <div class='callout callout-{variant}'>{title}{_render_inline(str(block.get('text') or ''))}</div>"
    if block_type == "table":
        title = f"<p class='block-title'>{_render_inline(str(block.get('title') or ''))}</p>" if block.get("title") else ""
        headers = "".join(f"<th>{_render_inline(str(item))}</th>" for item in block.get("headers") or [])
        rows = []
        for row in block.get("rows") or []:
            cells = "".join(f"<td>{_render_inline(str(cell))}</td>" for cell in row)
            rows.append(f"<tr>{cells}</tr>")
        return f"      <div class='table-wrapper'>{title}<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    if block_type == "metrics-grid":
        cards = []
        for item in block.get("items") or []:
            value = _render_inline(str(item.get("value") or ""))
            label = _render_inline(str(item.get("label") or ""))
            cards.append(f"<div class='metric-card'><div class='metric-value'>{value}</div><div class='metric-label'>{label}</div></div>")
        return "      <div class='metrics-grid'>" + "".join(cards) + "</div>"
    if block_type == "bar-chart":
        return _render_bar_chart(block)
    if block_type == "line-chart":
        return _render_line_chart(block)
    if block_type == "glossary":
        terms = []
        for term in block.get("terms") or []:
            terms.append(f"<dt>{_render_inline(str(term.get('term') or ''))}</dt><dd>{_render_inline(str(term.get('definition') or ''))}</dd>")
        context = f"<p>{_render_inline(str(block.get('context') or ''))}</p>" if block.get("context") else ""
        return f"      <div class='glossary-block'>{context}<dl>{''.join(terms)}</dl></div>"
    if block_type == "bibliography":
        items = []
        for ref in block.get("references") or []:
            text = _render_inline(str(ref.get("text") or ""))
            url = html.escape(str(ref.get("url") or ""))
            source = _render_inline(str(ref.get("source") or ""))
            items.append(f"<li><span>{text}</span> <a href='{url}'>source</a> <span class='ref-source'>({source})</span></li>")
        return "      <div class='bibliography'><ol>" + "".join(items) + "</ol></div>"
    if block_type == "raw-html":
        return "      " + str(block.get("content") or "")
    return f"      <p>{_render_inline(str(block.get('text') or block))}</p>"


def _render_bar_chart(block: dict[str, Any]) -> str:
    items = block.get("items") or []
    values = [_safe_float(item.get("value")) for item in items] or [0.0]
    max_value = max(values) or 1.0
    width = 700
    height = max(220, 70 + len(items) * 36)
    title = str(block.get("title") or "")
    unit = str(block.get("unit") or "")
    y = 40
    svg = [
        f"<div class='chart-block'><p class='block-title'>{_render_inline(title)}</p>",
        f"<svg role='img' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg' style='max-width:100%;height:auto;display:block;margin:8px 0 14px;'>",
        f"<title>{html.escape(title)}</title>",
    ]
    for item, value in zip(items, values):
        bar_width = int((value / max_value) * 420)
        label = str(item.get("label") or "")
        color = _chart_color(item)
        svg.extend(
            [
                f"<text x='20' y='{y+14}' font-family='Segoe UI,sans-serif' font-size='12' fill='#374151'>{html.escape(label)}</text>",
                f"<rect x='200' y='{y}' width='{bar_width}' height='20' rx='4' fill='{color}'></rect>",
                f"<text x='{212 + bar_width}' y='{y+14}' font-family='Segoe UI,sans-serif' font-size='12' fill='#1a3560'>{html.escape(_format_number(value))}{html.escape(unit)}</text>",
            ]
        )
        y += 34
    svg.append("</svg>")
    table_rows = "".join(
        f"<tr><td>{_render_inline(str(item.get('label') or ''))}</td><td>{html.escape(_format_number(_safe_float(item.get('value'))))}{html.escape(unit)}</td></tr>"
        for item in items
    )
    svg.append(f"<div class='table-wrapper'><table><thead><tr><th>Item</th><th>Value</th></tr></thead><tbody>{table_rows}</tbody></table></div></div>")
    return "      " + "".join(svg)


def _render_line_chart(block: dict[str, Any]) -> str:
    points = block.get("points") or block.get("items") or []
    values = [_safe_float(point.get("value")) for point in points] or [0.0]
    max_value = max(values) or 1.0
    width = 700
    height = 280
    left = 60
    top = 30
    chart_width = 560
    chart_height = 170
    title = str(block.get("title") or "")
    unit = str(block.get("unit") or "")
    coords = []
    denom = max(len(points) - 1, 1)
    for idx, point in enumerate(points):
        x = left + int(chart_width * idx / denom)
        y = top + int(chart_height - (chart_height * (_safe_float(point.get("value")) / max_value)))
        coords.append((x, y, point))
    path = " ".join(("M" if idx == 0 else "L") + f" {x} {y}" for idx, (x, y, _point) in enumerate(coords))
    svg = [
        f"<div class='chart-block'><p class='block-title'>{_render_inline(title)}</p>",
        f"<svg role='img' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg' style='max-width:100%;height:auto;display:block;margin:8px 0 14px;'>",
        f"<title>{html.escape(title)}</title>",
        f"<line x1='{left}' y1='{top + chart_height}' x2='{left + chart_width}' y2='{top + chart_height}' stroke='#94a3b8' stroke-width='1'></line>",
        f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top + chart_height}' stroke='#94a3b8' stroke-width='1'></line>",
        f"<path d='{path}' fill='none' stroke='#1c519b' stroke-width='3'></path>",
    ]
    for x, y, point in coords:
        svg.append(f"<circle cx='{x}' cy='{y}' r='4' fill='#1c519b'></circle>")
        svg.append(f"<text x='{x}' y='{top + chart_height + 18}' text-anchor='middle' font-family='Segoe UI,sans-serif' font-size='11' fill='#374151'>{html.escape(str(point.get('label') or ''))}</text>")
        svg.append(f"<text x='{x}' y='{y - 8}' text-anchor='middle' font-family='Segoe UI,sans-serif' font-size='11' fill='#1a3560'>{html.escape(_format_number(_safe_float(point.get('value'))))}{html.escape(unit)}</text>")
    svg.append("</svg>")
    table_rows = "".join(
        f"<tr><td>{_render_inline(str(point.get('label') or ''))}</td><td>{html.escape(_format_number(_safe_float(point.get('value'))))}{html.escape(unit)}</td></tr>"
        for point in points
    )
    svg.append(f"<div class='table-wrapper'><table><thead><tr><th>Point</th><th>Value</th></tr></thead><tbody>{table_rows}</tbody></table></div></div>")
    return "      " + "".join(svg)


def _report_css() -> str:
    return """
@import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');
:root{
  --brand-blue:#1c519b;--brand-blue-dark:#1a3560;--brand-green:#008c44;--brand-yellow:#ffcb05;
  --blue-50:#f2f6fd;--blue-100:#e1eafb;--blue-200:#c3d5f7;--blue-700:#1a3560;--blue-900:#1c2c4a;
  --gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-500:#6b7280;--gray-700:#374151;--gray-900:#111827;
}
*{box-sizing:border-box}
body{margin:0;font-family:'Libre Franklin',system-ui,sans-serif;font-size:15px;line-height:1.6;color:var(--gray-700);background:var(--gray-50)}
.report-header{background:var(--blue-900);color:white}
.header-content{max-width:1100px;margin:0 auto;padding:32px 40px;display:flex;align-items:center;gap:32px}
.header-text h1{font-size:30px;font-weight:700;line-height:1.18;margin:0 0 6px}
.subtitle{font-size:16px;color:rgba(255,255,255,.92);margin:0 0 6px}
.meta{font-size:13px;color:rgba(255,255,255,.76);margin:0}
.header-stripe{height:4px;background:linear-gradient(to right,var(--brand-green),var(--brand-yellow),var(--brand-blue))}
.report-content{max-width:1100px;margin:0 auto;padding:40px}
.section{margin-bottom:40px}
.section-title{font-size:22px;font-weight:600;color:var(--blue-700);border-bottom:2px solid var(--blue-200);padding-bottom:8px;margin-bottom:20px}
.section-lead{font-size:16px;line-height:1.7;color:var(--gray-700);margin:-4px 0 18px;max-width:860px}
.subsection-title{font-size:18px;font-weight:600;color:var(--blue-700);margin-top:24px;margin-bottom:12px}
.card,.block,.table-wrapper,.chart-block,.glossary-block,.bibliography{background:white;border:1px solid var(--gray-200);border-radius:8px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.summary-list{padding-left:20px}
.summary-list li{margin:.45rem 0}
.block-title{font-size:14px;font-weight:600;color:var(--gray-900);margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:14px}
thead th{background:#1b3158;color:white;font-weight:600;padding:10px 14px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.3px}
tbody td{padding:10px 14px;border-bottom:1px solid var(--gray-200);vertical-align:top}
tbody tr:nth-child(even){background:var(--blue-50)}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:16px}
.metric-card{background:white;border:1px solid var(--gray-200);border-radius:8px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.metric-value{font-size:30px;font-weight:700;color:var(--blue-700);line-height:1;margin-bottom:4px}
.metric-label{font-size:13px;color:var(--gray-500);font-weight:500}
.callout{padding:16px 20px;border-radius:6px;border-left:4px solid;margin-bottom:16px;font-size:14px;background:white}
.callout-info{background:var(--blue-50);border-color:var(--brand-blue)}
.callout-success{background:#def7ec;border-color:var(--brand-green)}
.callout-warning{background:#fdf6b2;border-color:#d69e2e}
.callout-danger{background:#fde8e8;border-color:#e53e3e}
code{background:#eef2f7;padding:.05rem .35rem;border-radius:4px}
ul,ol{padding-left:20px}
li{margin:.4rem 0}
dl{display:grid;grid-template-columns:minmax(180px,240px) 1fr;gap:12px 18px}
dt{font-weight:600;color:var(--gray-900)}
dd{margin:0}
.ref-source{color:var(--gray-500)}
a{color:var(--brand-blue);text-decoration:none}
a:hover{text-decoration:underline}
@media (max-width: 800px){
  .report-content{padding:24px}
  .header-content{padding:24px}
  dl{grid-template-columns:1fr}
}
"""


def _render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = _LINK_RE.sub(r"<a href='\2'>\1</a>", escaped)
    escaped = _INLINE_CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC_RE.sub(r"<em>\1</em>", escaped)
    return escaped


def _safe_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else 0.0


def _safe_int(value: Any) -> int:
    return int(round(_safe_float(value)))


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _chart_color(item: dict[str, Any]) -> str:
    colors = {
        "danger": "#e53e3e",
        "warning": "#ed8936",
        "success": "#38a169",
        "highlight": "#805ad5",
        "neutral": "#718096",
        "info": "#2b6cb0",
        "normal": "#2b6cb0",
    }
    raw = str(item.get("variant") or item.get("status") or "").lower()
    return colors.get(raw, "#2b6cb0")
