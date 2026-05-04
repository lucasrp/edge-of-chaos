from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .config import RuntimeConfig
from .context import ContextPacket
from .report_shape import REPORT_SECTION_TITLES, validate_report_markdown
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


def publish_artifact_bundle(
    config: RuntimeConfig,
    *,
    packet: ContextPacket,
    report_markdown: str,
    searches: list[SearchResult],
    reviews: list[ReviewResult],
    thread_id: str,
    thread_title: str,
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
        thread_id=thread_id,
        thread_title=thread_title,
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

    entry_markdown = _render_blog_entry_markdown(spec=spec, report_html_name=blog_report_html_path.name, report_md_name=report_md_path.name, report_spec_name=report_spec_path.name, thread_id=thread_id, kind=packet.kind)
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
    thread_id: str,
    thread_title: str,
    shape: Any | None = None,
) -> dict[str, Any]:
    shape = shape or validate_report_markdown(report_markdown)
    sections = shape.section_map()
    summary = _build_executive_summary(sections)
    metrics = [
        {"value": str(len(packet.observations)), "label": "Context observations"},
        {"value": str(len(searches)), "label": "Search artifacts"},
        {"value": str(len({item.source for item in searches})), "label": "Search sources"},
        {"value": str(len(packet.thread_candidates)), "label": "Recovered threads"},
        {"value": str(len(packet.report_candidates)), "label": "Recovered reports"},
    ]
    bibliography = _build_bibliography(searches)
    return {
        "title": shape.title or "Private Mentor Report",
        "subtitle": f"{packet.kind.title()} beat for thread '{thread_title}'",
        "date": date_slug(),
        "thread": {"id": thread_id, "title": thread_title},
        "kind": packet.kind,
        "request": packet.request,
        "executive_summary": summary,
        "metrics": metrics,
        "sections": [{"title": title, "markdown": sections.get(title, "").strip()} for title in REPORT_SECTION_TITLES],
        "bibliography": bibliography,
        "blog_post": {
            "title": _blog_entry_title(packet=packet, thread_title=thread_title),
            "paragraphs": _build_blog_post_paragraphs(packet=packet, sections=sections, thread_title=thread_title),
        },
    }


def validate_report_spec(spec: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    for field in ["title", "subtitle", "date", "thread", "executive_summary", "metrics", "sections", "bibliography", "blog_post"]:
        if field not in spec:
            issues.append(f"missing spec field: {field}")
    thread = spec.get("thread")
    if not isinstance(thread, dict) or not str(thread.get("id") or "").strip() or not str(thread.get("title") or "").strip():
        issues.append("invalid spec.thread")

    summary = spec.get("executive_summary")
    if not isinstance(summary, list) or len(summary) < 3 or any(not str(item).strip() for item in summary):
        issues.append("executive_summary must have at least 3 non-empty items")

    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or len(metrics) < 3:
        issues.append("metrics must have at least 3 items")
    else:
        for item in metrics:
            if not isinstance(item, dict) or not str(item.get("value") or "").strip() or not str(item.get("label") or "").strip():
                issues.append("invalid metric item")
                break

    sections = spec.get("sections")
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
            if not str(item.get("markdown") or "").strip():
                issues.append(f"empty spec section: {item.get('title')}")
                break

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
        "body{font-family:system-ui,sans-serif;max-width:860px;margin:3rem auto;padding:0 1.2rem;line-height:1.55}"
        "h1{margin-bottom:1.5rem} .entry-card{padding:1rem 0;border-top:1px solid #d7dce4}"
        ".entry-card:first-of-type{border-top:0;padding-top:0}.entry-card h2{margin:.2rem 0}.entry-date{color:#5f6b7a;font-size:.92rem;margin:0}"
        "a{color:#0f5bd8;text-decoration:none}a:hover{text-decoration:underline}"
        "</style>"
        "<h1>edge-of-chaos reports</h1>"
        + "\n".join(rows),
        encoding="utf-8",
    )
    return index


def render_report_html(spec: dict[str, Any]) -> str:
    parts = [
        "<!doctype html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='utf-8'>",
        f"  <title>{html.escape(str(spec.get('title') or 'Private Mentor Report'))}</title>",
        "  <style>"
        "body{font-family:system-ui,sans-serif;max-width:980px;margin:2.5rem auto;padding:0 1.25rem;line-height:1.6;color:#17202a}"
        "header{margin-bottom:2rem}.subtitle{color:#52606d}.meta{color:#52606d;font-size:.95rem}"
        ".summary, .metrics{margin:1.5rem 0}.summary ul{padding-left:1.2rem}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.8rem}"
        ".metric-card{border:1px solid #d7dce4;border-radius:8px;padding:.9rem 1rem;background:#f8fafc}"
        ".metric-value{font-size:1.35rem;font-weight:700}.metric-label{color:#52606d}"
        "section{margin:2rem 0}h2{margin-bottom:.8rem}p{margin:.75rem 0}ul,ol{padding-left:1.35rem}"
        "code{background:#eef2f7;padding:.05rem .35rem;border-radius:4px}blockquote{margin:1rem 0;padding:.75rem 1rem;border-left:3px solid #9db3d8;background:#f8fafc}"
        ".refs li{margin:.45rem 0}"
        "a{color:#0f5bd8;text-decoration:none}a:hover{text-decoration:underline}"
        "  </style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        f"  <h1>{html.escape(str(spec.get('title') or 'Private Mentor Report'))}</h1>",
        f"  <p class='subtitle'>{html.escape(str(spec.get('subtitle') or ''))}</p>",
        f"  <p class='meta'>{html.escape(str(spec.get('date') or ''))} · Thread: {html.escape(str((spec.get('thread') or {}).get('title') or ''))}</p>",
        "</header>",
        "<section class='summary'>",
        "  <h2>Executive Summary</h2>",
        "  <ul>",
    ]
    for item in spec.get("executive_summary") or []:
        parts.append(f"    <li>{_render_inline(str(item))}</li>")
    parts.extend(["  </ul>", "</section>", "<section class='metrics'>"])
    for item in spec.get("metrics") or []:
        parts.append(
            "<div class='metric-card'>"
            f"<div class='metric-value'>{html.escape(str(item.get('value') or ''))}</div>"
            f"<div class='metric-label'>{html.escape(str(item.get('label') or ''))}</div>"
            "</div>"
        )
    parts.append("</section>")
    for section in spec.get("sections") or []:
        title = str(section.get("title") or "")
        parts.append("<section>")
        parts.append(f"  <h2>{html.escape(title)}</h2>")
        parts.append(_render_markdown(str(section.get("markdown") or "")))
        parts.append("</section>")
    parts.append("<section>")
    parts.append("  <h2>References</h2>")
    parts.append("  <ul class='refs'>")
    for item in spec.get("bibliography") or []:
        text = html.escape(str(item.get("text") or ""))
        url = html.escape(str(item.get("url") or ""))
        source = html.escape(str(item.get("source") or ""))
        parts.append(f"    <li><a href='{url}'>{text}</a> <span>({source})</span></li>")
    parts.extend(["  </ul>", "</section>", "</main>", "</body>", "</html>"])
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
        "body{font-family:system-ui,sans-serif;max-width:760px;margin:2.5rem auto;padding:0 1.25rem;line-height:1.65;color:#17202a}"
        "header{margin-bottom:1.8rem}.meta{color:#52606d;font-size:.95rem}.cta{margin-top:1.6rem;padding:1rem 1.1rem;border:1px solid #d7dce4;border-radius:8px;background:#f8fafc}"
        "a{color:#0f5bd8;text-decoration:none}a:hover{text-decoration:underline}"
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


def _build_executive_summary(sections: dict[str, str]) -> list[str]:
    desired = [
        "Situated Delta",
        "Problem Framing and Open Gaps",
        "Why This Matters Now",
    ]
    items = [_section_takeaway(sections.get(title, "")) for title in desired]
    filtered = [item for item in items if item]
    while len(filtered) < 3:
        filtered.append("The beat preserved continuity, explained the live problem, and ended with concrete next steps.")
    return filtered[:3]


def _build_bibliography(searches: list[SearchResult]) -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for result in searches:
        key = str(result.url).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "text": str(result.title or result.url),
                "url": str(result.url),
                "source": str(result.source),
            }
        )
        if len(items) >= 8:
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
        f"Open the full report for the formal problem framing, the Feynman derivation, the search evidence, and the concrete next steps. {next_steps}",
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


def _render_markdown(text: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]
    rendered: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines and all(line.startswith("- ") for line in lines):
            rendered.append("<ul>")
            for line in lines:
                rendered.append(f"<li>{_render_inline(line[2:].strip())}</li>")
            rendered.append("</ul>")
            continue
        if lines and all(_NUMBERED_RE.match(line) for line in lines):
            rendered.append("<ol>")
            for line in lines:
                rendered.append(f"<li>{_render_inline(_NUMBERED_RE.sub('', line).strip())}</li>")
            rendered.append("</ol>")
            continue
        rendered.append(f"<p>{_render_inline(' '.join(lines))}</p>")
    return "\n".join(rendered)


def _render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = _LINK_RE.sub(r"<a href='\2'>\1</a>", escaped)
    escaped = _INLINE_CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC_RE.sub(r"<em>\1</em>", escaped)
    return escaped
