#!/usr/bin/env python3
"""
Convert structured YAML to HTML content (<main>) for reports.

Usage:
    python3 yaml_to_html.py spec.yaml --output /tmp/content.html
    python3 yaml_to_html.py spec.yaml  # stdout

The YAML defines sections, blocks, and content. This script generates HTML
for <main class="report-content"> — generate_report.py handles the rest
(CSS, SVG, header, footer).
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Text rendering helpers
# ---------------------------------------------------------------------------

def render_text(s: str) -> str:
    """Escape HTML, then convert **bold**, *italic*, `code`, [text](url) markers."""
    if not s:
        return ""
    s = html.escape(str(s))
    # Markdown links: [text](url) — after escape, brackets/parens are preserved
    s = re.sub(
        r'\[(.+?)\]\((.+?)\)',
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        s,
    )
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.+?)\*', r'<em>\1</em>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    # Convert &mdash; &rarr; &larr; markers (already escaped by html.escape)
    s = s.replace('--', '&mdash;')
    s = s.replace('-&gt;', '&rarr;')
    s = s.replace('&lt;-', '&larr;')
    return s


def render_pre(s: str) -> str:
    """Escape HTML only (for preformatted content)."""
    return html.escape(str(s)) if s else ""


def badge_html(text: str, variant: str = "neutral") -> str:
    """Generate a badge span."""
    return f'<span class="badge badge-{variant}">{html.escape(str(text))}</span>'


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

RENDERERS = {}


def renderer(block_type: str):
    """Decorator to register a block renderer."""
    def wrap(fn):
        RENDERERS[block_type] = fn
        return fn
    return wrap


@renderer("paragraph")
def render_paragraph(b):
    style = f' style="{b["style"]}"' if b.get("style") else ""
    return f'<p{style}>{render_text(b["text"])}</p>'


@renderer("subsection")
def render_subsection(b):
    return f'<h3 class="subsection-title">{render_text(b["title"])}</h3>'


@renderer("concept-grid")
def render_concept_grid(b):
    items = b.get("items", []) or b.get("concepts", [])
    cells = []
    for item in items:
        cells.append(
            f'<div class="callout callout-info">'
            f'<strong>{render_text(item.get("name", item.get("title", "(no name)")))}</strong><br>'
            f'{render_text(item.get("text") or item.get("description") or "")}'
            f'</div>'
        )
    # Pair items in 2-column grids
    parts = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i+2]
        parts.append(f'<div class="comparison-grid">{"".join(pair)}</div>')
    return "\n".join(parts)


@renderer("callout")
def render_callout(b):
    variant = b.get("variant") or b.get("style", "info")
    title_html = ""
    if b.get("title"):
        title_html = f'<strong>{render_text(b["title"])}</strong><br>'
    return (
        f'<div class="callout callout-{variant}">'
        f'{title_html}{render_text(b["text"])}'
        f'</div>'
    )


@renderer("card")
def render_card(b):
    parts = ['<div class="card">']
    title = b.get("title") or b.get("label", "")
    if title or b.get("badge"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(title)}</span>')
        if b.get("badge"):
            bc = b.get("badge_class", "neutral")
            parts.append(badge_html(b["badge"], bc))
        parts.append('</div>')
    if b.get("text"):
        parts.append(f'<p style="font-size: 14px;">{render_text(b["text"])}</p>')
    bullets = b.get("bullets", [])
    if bullets:
        parts.append('<ul style="font-size: 14px; padding-left: 20px;">')
        for item in bullets:
            parts.append(f'<li>{render_text(str(item))}</li>')
        parts.append('</ul>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("numbered-card")
def render_numbered_card(b):
    items = b.get("items", [])
    if items:
        all_parts = []
        for i, item in enumerate(items, 1):
            all_parts.append(_render_single_numbered_card(item, default_num=i))
        return "\n".join(all_parts)
    return _render_single_numbered_card(b)


def _render_single_numbered_card(b, default_num=""):
    num = b.get("number", default_num)
    classes = ["card"]
    if b.get("card_class"):
        classes.append(b["card_class"])
    cls = " ".join(classes)
    parts = [f'<div class="{cls}" data-iter="{html.escape(str(num))}">']
    parts.append('<div class="card-header">')
    parts.append(f'<span class="card-title">{render_text(b.get("title", ""))}</span>')
    if b.get("badge"):
        bc = b.get("badge_class", "neutral")
        parts.append(badge_html(b["badge"], bc))
    parts.append('</div>')
    if b.get("text"):
        parts.append(f'<p style="font-size: 14px;">{render_text(b["text"])}</p>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("flow-example")
def render_flow_example(b):
    input_label = b.get("input_label", "Input")
    output_label = b.get("output_label", "Output")
    parts = ['<div class="card">']
    if b.get("label"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(b["label"])}</span>')
        parts.append('</div>')

    # Input pre (yellow)
    parts.append(
        f'<p style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">'
        f'{render_text(input_label)}:</p>'
    )
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 12px; '
        f'line-height: 1.55; background: #FDF6B2; padding: 12px; border-radius: 6px; '
        f'border-left: 3px solid #D69E2E;">'
        f'{render_pre(b["input"])}</pre>'
    )

    # Output pre (green)
    parts.append(
        f'<p style="font-size: 13px; font-weight: 600; margin-top: 12px; '
        f'margin-bottom: 8px;">{render_text(output_label)}:</p>'
    )
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 12px; '
        f'line-height: 1.55; background: #DEF7EC; padding: 12px; border-radius: 6px; '
        f'border-left: 3px solid var(--accent-green);">'
        f'{render_pre(b["output"])}</pre>'
    )

    # Optional code block (gray)
    if b.get("code"):
        parts.append(
            f'<pre style="font-family: \'Courier New\', monospace; font-size: 13px; '
            f'line-height: 1.55; background: var(--gray-50); padding: 16px; '
            f'border-radius: 6px; overflow-x: auto; margin-top: 12px;">'
            f'{render_pre(b["code"])}</pre>'
        )

    parts.append('</div>')
    return "\n".join(parts)


@renderer("comparison")
def render_comparison(b):
    def _side(side):
        p = [f'<div class="card">']
        p.append('<div class="card-header">')
        p.append(f'<span class="card-title">{render_text(side.get("title", ""))}</span>')
        if side.get("badge"):
            bc = side.get("badge_class", "neutral")
            p.append(badge_html(side["badge"], bc))
        p.append('</div>')
        if side.get("pre"):
            p.append(
                f'<pre style="font-family: \'Courier New\', monospace; font-size: 12px; '
                f'line-height: 1.6; margin-top: 8px;">'
                f'{render_pre(side["pre"])}</pre>'
            )
        bullets = side.get("bullets") or side.get("items")
        if bullets:
            p.append(
                '<ul style="padding-left: 20px; font-size: 13px; line-height: 1.7; '
                'margin-top: 8px;">'
            )
            for bullet in bullets:
                p.append(f'<li>{render_text(bullet)}</li>')
            p.append('</ul>')
        if side.get("text"):
            p.append(f'<p style="font-size: 14px;">{render_text(side["text"])}</p>')
        p.append('</div>')
        return "\n".join(p)

    return (
        f'<div class="comparison-grid">\n'
        f'{_side(b.get("before", b.get("left", {})))}\n'
        f'{_side(b.get("after", b.get("right", {})))}\n'
        f'</div>'
    )


@renderer("table")
def render_table(b):
    highlight = set(b.get("highlight_rows", []))
    score_row_idx = b.get("score_row")
    parts = ['<div class="table-wrapper">', '<table>', '<thead>', '<tr>']
    for h in b.get("headers", []):
        parts.append(f'<th>{render_text(h)}</th>')
    parts.append('</tr></thead><tbody>')
    for i, row in enumerate(b.get("rows", [])):
        tr_class = ""
        if i == score_row_idx:
            tr_class = ' class="score-row"'
        elif i in highlight:
            tr_class = ' style="background: #DEF7EC;"'
        parts.append(f'<tr{tr_class}>')
        for cell in row:
            parts.append(f'<td>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return "\n".join(parts)


@renderer("comparison-table")
def render_comparison_table(b):
    parts = ['<div class="table-wrapper">', '<table>', '<thead>', '<tr>']
    for h in b.get("headers", []):
        parts.append(f'<th>{render_text(h)}</th>')
    parts.append('</tr></thead><tbody>')
    for row in b["rows"]:
        cells = row.get("cells", [])
        classes = row.get("classes", [])
        parts.append('<tr>')
        for j, cell in enumerate(cells):
            cls = classes[j] if j < len(classes) else ""
            td_cls = f' class="{cls}"' if cls else ""
            parts.append(f'<td{td_cls}>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    if b.get("score_row"):
        sr = b["score_row"]
        cells = sr.get("cells", [])
        classes = sr.get("classes", [])
        parts.append('<tr class="score-row">')
        for j, cell in enumerate(cells):
            cls = classes[j] if j < len(classes) else ""
            td_cls = f' class="{cls}"' if cls else ""
            parts.append(f'<td{td_cls}>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')
    if b.get("note"):
        parts.append(
            f'<p style="font-size: 12px; color: var(--gray-500); margin-top: 4px;">'
            f'{render_text(b["note"])}</p>'
        )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("risk-table")
def render_risk_table(b):
    prob_badge = {
        "alta": "danger", "media": "warning", "baixa": "success",
        "high": "danger", "medium": "warning", "low": "success",
    }
    parts = ['<div class="table-wrapper">', '<table>', '<thead>', '<tr>']
    parts.append('<th>Risk</th><th>Probability</th><th>Mitigation</th>')
    parts.append('</tr></thead><tbody>')
    for row in b["rows"]:
        prob = row.get("probability", "medium")
        variant = prob_badge.get(prob.lower(), "neutral")
        parts.append('<tr>')
        parts.append(f'<td>{render_text(row["risk"])}</td>')
        parts.append(f'<td>{badge_html(prob, variant)}</td>')
        parts.append(f'<td>{render_text(row["mitigation"])}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return "\n".join(parts)


@renderer("code-block")
def render_code_block(b):
    parts = ['<div class="card">']
    if b.get("label") or b.get("badge"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(b.get("label", ""))}</span>')
        if b.get("badge"):
            bc = b.get("badge_class", "info")
            parts.append(badge_html(b["badge"], bc))
        parts.append('</div>')
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 13px; '
        f'line-height: 1.55; background: var(--gray-50); padding: 16px; '
        f'border-radius: 6px; overflow-x: auto;">'
        f'{render_pre(b["content"])}</pre>'
    )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("ascii-diagram")
def render_ascii_diagram(b):
    parts = ['<div class="card">']
    if b.get("title"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(b["title"])}</span>')
        parts.append('</div>')
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 13px; '
        f'line-height: 1.6; background: var(--gray-50); padding: 16px; '
        f'border-radius: 6px; overflow-x: auto;">'
        f'{render_pre(b["content"])}</pre>'
    )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("template-block")
def render_template_block(b):
    parts = ['<div class="card">']
    if b.get("title"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(b["title"])}</span>')
        parts.append('</div>')
    if b.get("description"):
        parts.append(
            f'<p style="font-size: 13px; color: var(--gray-500); margin-bottom: 8px;">'
            f'{render_text(b["description"])}</p>'
        )
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 12px; '
        f'line-height: 1.55; background: var(--gray-50); padding: 16px; '
        f'border-radius: 6px; overflow-x: auto;">'
        f'{render_pre(b["content"])}</pre>'
    )
    if b.get("note"):
        parts.append(
            f'<div class="callout callout-info" style="margin-top: 12px;">'
            f'{render_text(b["note"])}</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("next-steps-grid")
def render_next_steps_grid(b):
    parts = ['<div class="next-steps-grid">']
    steps = b.get("steps", []) or b.get("items", [])
    # Support now/next/later grouping (flatten into steps)
    if not steps:
        for phase_key in ("now", "next", "later"):
            phase_items = b.get(phase_key, [])
            if isinstance(phase_items, list):
                for item in phase_items:
                    if isinstance(item, dict):
                        item.setdefault("phase", phase_key)
                    steps.append(item)
            elif isinstance(phase_items, str):
                steps.append({"title": phase_items, "phase": phase_key})
    for step in steps:
        # Normalize: string -> dict
        if isinstance(step, str):
            step = {"title": step}
        parts.append('<div class="next-step-card">')
        # Support both "number" and "phase"/"priority" as the badge
        badge = step.get("number") or step.get("phase") or step.get("priority") or step.get("owner") or ""
        title = step.get("title") or step.get("action") or ""
        parts.append(
            f'<span class="step-number">{html.escape(str(badge))}</span>'
            f'<span class="step-title">{render_text(title)}</span>'
        )
        desc = step.get("description") or step.get("text") or step.get("detail") or ""
        deadline = step.get("deadline") or ""
        if deadline:
            desc = f"{desc} ({deadline})" if desc else deadline
        if desc:
            parts.append(f'<p class="step-desc">{render_text(desc)}</p>')
        parts.append('</div>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("metrics-grid")
def render_metrics_grid_block(b):
    return _render_metrics_items(b.get("items", []) or b.get("metrics", []))


@renderer("list")
def render_list(b):
    tag = "ol" if b.get("ordered") else "ul"
    style = b.get("style", "padding-left: 20px; font-size: 14px; line-height: 1.7;")
    parts = [f'<{tag} style="{style}">']
    for item in b.get("items", []):
        parts.append(f'<li>{render_text(item)}</li>')
    parts.append(f'</{tag}>')
    return "\n".join(parts)


@renderer("diff-block")
def render_diff_block(b):
    parts = ['<div class="diff-block">']
    if b.get("header"):
        parts.append(
            f'<div class="diff-block-header">{render_text(b["header"])}</div>'
        )
    for line in b.get("lines", []):
        line_type = line.get("type", "context")
        css_class = f"diff-{line_type}"
        prefix = {"insert": "+ ", "delete": "- ", "context": "  "}.get(line_type, "  ")
        parts.append(
            f'<div class="{css_class}">{prefix}{render_pre(line["text"])}</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("raw-html")
def render_raw_html(b):
    return b.get("content", b.get("html", ""))


# ---------------------------------------------------------------------------
# Feynman method blocks
# ---------------------------------------------------------------------------

@renderer("derivation")
def render_derivation(b):
    """Block for 'what I derived from scratch' — purple-bordered card."""
    parts = ['<div class="derivation">']
    parts.append('<div class="derivation-header">')
    parts.append('<span class="derivation-icon">D</span>')
    title = b.get("title", "Derivation")
    parts.append(f'<span class="derivation-title">{render_text(title)}</span>')
    parts.append('</div>')
    if b.get("text"):
        parts.append(f'<p>{render_text(b["text"])}</p>')
    bullets = b.get("bullets") or b.get("steps", [])
    if bullets:
        parts.append('<ul>')
        for bullet in bullets:
            parts.append(f'<li>{render_text(bullet)}</li>')
        parts.append('</ul>')
    if b.get("code"):
        parts.append(f'<pre>{render_pre(b["code"])}</pre>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("gap-marker")
def render_gap_marker(b):
    """Individual [GAP: ...] callout — amber/orange styling."""
    gap_id = b.get("id", "")
    label = f'GAP{" #" + str(gap_id) if gap_id else ""}'
    parts = ['<div class="gap-marker">']
    parts.append(f'<span class="gap-marker-label">{html.escape(label)}</span>')
    parts.append(f'{render_text(b["text"])}')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("gap-table")
def render_gap_table(b):
    """Table of all gaps with status tracking (resolved/partial/open)."""
    # Fallback: if YAML uses headers/rows (table format), delegate to table renderer
    if not b.get("gaps") and b.get("headers") and b.get("rows"):
        return render_table(b)
    status_cls = {
        "resolvido": "gap-status-resolved",
        "resolved": "gap-status-resolved",
        "parcial": "gap-status-partial",
        "partial": "gap-status-partial",
        "aberto": "gap-status-open",
        "open": "gap-status-open",
    }
    parts = ['<div class="table-wrapper">', '<table>', '<thead>', '<tr>']
    parts.append('<th>#</th><th>Gap</th><th>What I need to know</th><th>Status</th>')
    parts.append('</tr></thead><tbody>')
    for row in b.get("gaps", []):
        num = row.get("id", "")
        desc = row.get("description", "")
        need = row.get("need", "")
        status = row.get("status", "open")
        cls = status_cls.get(status.lower(), "gap-status-open")
        parts.append('<tr>')
        parts.append(f'<td style="font-weight:600;text-align:center;">{html.escape(str(num))}</td>')
        parts.append(f'<td>{render_text(desc)}</td>')
        parts.append(f'<td>{render_text(need)}</td>')
        parts.append(f'<td><span class="{cls}">{html.escape(status.upper())}</span></td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return "\n".join(parts)


@renderer("gap-resolution")
def render_gap_resolution(b):
    """Links a gap to its resolution — amber header, green answer."""
    gap_id = b.get("gap_id", "")
    gap_label = f'Gap #{gap_id}' if gap_id else "Gap"
    parts = ['<div class="gap-resolution">']
    # Header: the gap
    parts.append('<div class="gap-resolution-header">')
    parts.append(f'<span class="gap-marker-label">{html.escape(gap_label)}</span>')
    parts.append(f'{render_text(b.get("gap", ""))}')
    parts.append('</div>')
    # Body: context/evidence (optional)
    if b.get("text"):
        parts.append(f'<div class="gap-resolution-body">{render_text(b["text"])}</div>')
    # Answer: what was found
    if b.get("answer"):
        parts.append(f'<div class="gap-resolution-answer">{render_text(b["answer"])}</div>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("bibliography")
def render_bibliography(b):
    """Bibliography block — numbered references with source badges and clickable URLs."""
    parts = ['<div class="bibliography">']
    if b.get("title"):
        parts.append(f'<h3>{render_text(b["title"])}</h3>')
    refs = b.get("references", [])
    if refs:
        parts.append('<ol class="bibliography-list">')
        for ref in refs:
            if isinstance(ref, str):
                # Simple string reference
                parts.append(f'<li>{render_text(ref)}</li>')
            else:
                # Structured: {text, url?, source?}
                text = render_text(ref.get("text", ""))
                url = ref.get("url", "")
                source = ref.get("source", "")
                li_parts = [text]
                if url:
                    escaped_url = html.escape(url)
                    li_parts.append(
                        f' <a href="{escaped_url}" target="_blank" '
                        f'rel="noopener" class="bibliography-url">{escaped_url}</a>'
                    )
                if source:
                    variant = {
                        "websearch": "info", "web": "info",
                        "x": "neutral", "twitter": "neutral",
                        "arxiv": "success", "paper": "success", "semantic scholar": "success",
                        "github": "neutral", "hackernews": "warning", "hn": "warning",
                        "blog": "neutral", "docs": "info",
                    }.get(source.lower(), "neutral")
                    li_parts.append(f' {badge_html(source, variant)}')
                parts.append(f'<li>{"".join(li_parts)}</li>')
        parts.append('</ol>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("glossary")
def render_glossary(b):
    """Glossary block — contextualisation paragraph + definition list."""
    parts = ['<div class="glossary">']
    if b.get("context"):
        parts.append(f'<div class="glossary-context">{render_text(b["context"])}</div>')
    terms = b.get("terms") or b.get("items", [])
    if terms:
        parts.append('<dl>')
        for t in terms:
            parts.append(f'<dt>{render_text(t.get("term", ""))}</dt>')
            parts.append(f'<dd>{render_text(t.get("definition", ""))}</dd>')
        parts.append('</dl>')
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Block schemas — co-located with renderers, one entry per block type
# ---------------------------------------------------------------------------

BLOCK_SCHEMAS = {
    "paragraph": {
        "required": ["text"],
        "optional": ["style"],
        "synonyms": {},
        "container_field": None,
    },
    "subsection": {
        "required": ["title"],
        "optional": [],
        "synonyms": {},
        "container_field": None,
    },
    "concept-grid": {
        "required": [],
        "optional": ["items", "concepts"],
        "synonyms": {"concepts": "items"},
        "container_field": ("items", "concepts"),
    },
    "callout": {
        "required": ["text"],
        "optional": ["variant", "style", "title"],
        "synonyms": {},
        "container_field": None,
    },
    "card": {
        "required": [],
        "optional": ["title", "badge", "badge_class", "text", "bullets", "label"],
        "synonyms": {"label": "title"},
        "container_field": None,
    },
    "numbered-card": {
        "required": [],
        "optional": ["items", "number", "title", "badge", "badge_class", "text", "card_class"],
        "synonyms": {},
        "container_field": None,
    },
    "flow-example": {
        "required": ["input", "output"],
        "optional": ["label", "input_label", "output_label", "code"],
        "synonyms": {},
        "container_field": None,
    },
    "comparison": {
        "required": [],
        "optional": ["before", "after", "left", "right"],
        "synonyms": {"left": "before", "right": "after"},
        "container_field": None,
    },
    "table": {
        "required": ["headers", "rows"],
        "optional": ["highlight_rows", "score_row"],
        "synonyms": {},
        "container_field": ("rows",),
    },
    "comparison-table": {
        "required": ["headers", "rows"],
        "optional": ["score_row", "note"],
        "synonyms": {},
        "container_field": ("rows",),
    },
    "risk-table": {
        "required": ["rows"],
        "optional": [],
        "synonyms": {},
        "container_field": ("rows",),
    },
    "code-block": {
        "required": ["content"],
        "optional": ["label", "badge", "badge_class"],
        "synonyms": {},
        "container_field": None,
    },
    "ascii-diagram": {
        "required": ["content"],
        "optional": ["title"],
        "synonyms": {},
        "container_field": None,
    },
    "template-block": {
        "required": ["content"],
        "optional": ["title", "description", "note"],
        "synonyms": {},
        "container_field": None,
    },
    "next-steps-grid": {
        "required": [],
        "optional": ["steps", "items", "now", "next", "later"],
        "synonyms": {"items": "steps"},
        "container_field": ("steps", "items", "now", "next", "later"),
    },
    "metrics-grid": {
        "required": [],
        "optional": ["items", "metrics"],
        "synonyms": {"metrics": "items"},
        "container_field": ("items", "metrics"),
    },
    "list": {
        "required": [],
        "optional": ["items", "ordered", "style"],
        "synonyms": {},
        "container_field": ("items",),
    },
    "diff-block": {
        "required": [],
        "optional": ["header", "lines"],
        "synonyms": {},
        "container_field": ("lines",),
    },
    "raw-html": {
        "required": [],
        "optional": ["content", "html"],
        "synonyms": {"html": "content"},
        "container_field": None,
    },
    "derivation": {
        "required": [],
        "optional": ["title", "text", "bullets", "code", "label"],
        "synonyms": {"steps": "bullets", "label": "title"},
        "container_field": None,
    },
    "gap-marker": {
        "required": ["text"],
        "optional": ["id"],
        "synonyms": {},
        "container_field": None,
    },
    "gap-table": {
        "required": [],
        "optional": ["gaps", "headers", "rows"],
        "synonyms": {},
        "container_field": ("gaps", "headers"),
    },
    "gap-resolution": {
        "required": [],
        "optional": ["gap_id", "gap", "text", "answer"],
        "synonyms": {},
        "container_field": None,
    },
    "bibliography": {
        "required": [],
        "optional": ["title", "references"],
        "synonyms": {},
        "container_field": ("references",),
    },
    "glossary": {
        "required": [],
        "optional": ["context", "terms"],
        "synonyms": {"items": "terms"},
        "container_field": ("terms", "items"),
    },
}


def _validate_block(block_type: str, block: dict) -> list:
    """Validate block against its schema. Returns list of warning messages."""
    schema = BLOCK_SCHEMAS.get(block_type)
    if schema is None:
        return []
    warnings = []
    present = {k for k in block if k != "type"}
    known = set(schema["required"]) | set(schema["optional"]) | set(schema.get("synonyms", {}).keys())

    # Missing required fields
    for field in schema["required"]:
        if field not in block:
            warnings.append(f"Missing required field: '{field}'")

    # Unknown fields (probable typo)
    unknown = present - known
    if unknown:
        warnings.append(f"Unknown field(s) (possible typo): {sorted(unknown)}")

    # Empty container
    container = schema.get("container_field")
    if container:
        has_data = any(block.get(f) for f in container)
        if not has_data:
            warnings.append(
                f"Empty container: none of {container} have data. "
                f"Fields present: {sorted(present)}"
            )

    return warnings


def _is_empty_render(block_type: str, result: str) -> bool:
    """Check if rendered HTML has no visible text content (post-render catch-all)."""
    schema = BLOCK_SCHEMAS.get(block_type)
    if schema is None or not schema.get("container_field"):
        return False
    text = re.sub(r'<[^>]+>', '', result).strip()
    return len(text) == 0


# ---------------------------------------------------------------------------
# Section / top-level renderers
# ---------------------------------------------------------------------------

_validation_error_count = 0
_RENDER_LOG = Path(os.environ.get("YAML_RENDER_LOG", Path.home() / "edge/logs/yaml-render.jsonl"))
_current_source: str | None = None  # set by caller (main or external)


def _log_render_event(block_type: str, event: str, detail: str, fields: list[str] | None = None):
    """Append a structured event to the persistent render log."""
    try:
        _RENDER_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": _current_source,
            "block_type": block_type,
            "event": event,
            "detail": detail,
        }
        if fields:
            entry["fields"] = fields
        with open(_RENDER_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break rendering


def get_validation_error_count() -> int:
    """Return the number of validation errors encountered during rendering."""
    return _validation_error_count


def render_block(block: dict) -> str:
    """Dispatch a single block to its renderer."""
    global _validation_error_count
    block_type = block.get("type", "paragraph")
    fn = RENDERERS.get(block_type)
    if fn is None:
        _log_render_event(block_type, "unknown_block_type", f"Block type '{block_type}' has no renderer")
        return f'<!-- unknown block type: {html.escape(block_type)} -->'

    # Check for synonym usage (log before validation normalizes them away)
    schema = BLOCK_SCHEMAS.get(block_type)
    if schema:
        for syn, canonical in schema.get("synonyms", {}).items():
            if syn in block and canonical not in block:
                _log_render_event(block_type, "synonym_used",
                                  f"'{syn}' used instead of '{canonical}' -- accepted via synonym",
                                  fields=sorted(k for k in block if k != "type"))

    # Pre-render validation
    warnings = _validate_block(block_type, block)
    error_html = ""
    if warnings:
        _validation_error_count += len(warnings)
        for w in warnings:
            print(f"ERROR block [{block_type}]: {w}", file=sys.stderr)
            # Classify and log each warning
            if "Unknown" in w:
                _log_render_event(block_type, "unknown_fields", w,
                                  fields=sorted(k for k in block if k != "type"))
            elif "required" in w:
                _log_render_event(block_type, "missing_required", w)
            elif "Empty container" in w:
                _log_render_event(block_type, "empty_container", w,
                                  fields=sorted(k for k in block if k != "type"))
        error_html = (
            f'<div style="border:2px solid #DC2626;background:#FEF2F2;padding:8px;'
            f'border-radius:6px;margin:8px 0;font-size:13px;color:#991B1B;">'
            f'ERROR block [{html.escape(block_type)}]: '
            + "<br>".join(html.escape(w) for w in warnings)
            + '</div>'
        )

    result = fn(block)

    # Post-render empty check (catch-all for bugs schema didn't predict)
    if not warnings and _is_empty_render(block_type, result):
        _validation_error_count += 1
        present = sorted(k for k in block if k != "type")
        msg = f"ERROR block [{block_type}]: rendered empty (post-render). Fields: {present}"
        print(msg, file=sys.stderr)
        _log_render_event(block_type, "empty_render", msg, fields=present)
        error_html = (
            f'<div style="border:2px solid #DC2626;background:#FEF2F2;padding:8px;'
            f'border-radius:6px;margin:8px 0;font-size:13px;color:#991B1B;">'
            f'ERROR block [{html.escape(block_type)}]: rendered empty. '
            f'Fields present: {html.escape(str(present))}'
            + '</div>'
        )

    return error_html + result if error_html else result


def _normalize_section_blocks(section: dict) -> list:
    """Extract blocks from a section, handling alternate YAML formats.

    Supports:
    1. Standard: section has 'blocks' list
    2. Shorthand: section has 'type' and 'content'/'text' at section level
    3. Metrics shorthand: section has 'type: metrics-grid' and 'metrics'
    4. Next-steps shorthand: section has 'type: next-steps-grid' and 'steps'
    5. Table shorthand: section has 'type: table' and 'headers'/'rows'
    6. Callout shorthand: section has 'type: callout' and 'content'/'text'
    """
    if section.get("blocks"):
        return section["blocks"]

    # Shorthand: type + content/text at section level
    sec_type = section.get("type")
    if not sec_type:
        return []

    block = {"type": sec_type}

    # Map 'content' to the field the renderer expects
    content = section.get("content") or section.get("text") or ""
    if sec_type == "paragraph" and content:
        block["text"] = content
    elif sec_type == "callout":
        block["text"] = content
        if section.get("style"):
            block["variant"] = section["style"]
        if section.get("variant"):
            block["variant"] = section["variant"]
    elif sec_type == "table":
        block["headers"] = section.get("headers", [])
        block["rows"] = section.get("rows", [])
        if section.get("highlight_rows"):
            block["highlight_rows"] = section["highlight_rows"]
    elif sec_type == "metrics-grid":
        block["items"] = section.get("metrics", section.get("items", []))
    elif sec_type == "next-steps-grid":
        block["steps"] = section.get("steps", section.get("items", []))
    elif content:
        block["text"] = content

    # Copy any extra keys the renderer might need
    for key in ("items", "steps", "ordered", "variant",
                "headers", "rows", "number", "badge", "badge_class"):
        if key in section and key not in block:
            block[key] = section[key]

    if block.get("text") or block.get("items") or block.get("steps") \
       or block.get("headers") or block.get("content"):
        title = section.get("title", "(no title)")
        print(f"WARNING: section '{title}' uses shorthand format (type/content at section level). "
              f"Correct format: blocks: [{{type: ..., text: ...}}]. Auto-converted.",
              file=sys.stderr)
        return [block]

    return []


def render_section(section: dict) -> str:
    """Render a section with title and blocks."""
    parts = ['<div class="section">']
    if section.get("title"):
        parts.append(f'<h2 class="section-title">{render_text(section["title"])}</h2>')
    blocks = _normalize_section_blocks(section)
    if not blocks and section.get("title"):
        print(f"WARNING: section '{section['title']}' has no content (no blocks, no type/content). "
              f"Check the YAML.", file=sys.stderr)
    for block in blocks:
        parts.append(render_block(block))
    parts.append('</div>')
    return "\n".join(parts)


def render_executive_summary(items: list) -> str:
    """Render executive summary block."""
    parts = [
        '<div class="executive-summary">',
        '<h3>Executive Summary</h3>',
        '<ul>',
    ]
    for item in items:
        parts.append(f'<li>{render_text(item)}</li>')
    parts.append('</ul></div>')
    return "\n".join(parts)


def _render_metrics_items(items: list) -> str:
    """Render a metrics grid from a list of {value, label} items."""
    parts = ['<div class="metrics-grid">']
    for m in items:
        parts.append(
            f'<div class="metric-card">'
            f'<div class="metric-value">{render_text(m["value"])}</div>'
            f'<div class="metric-label">{render_text(m["label"])}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def yaml_to_html(yaml_path: str) -> str:
    """Read a YAML spec and return HTML string for <main> content."""
    with open(yaml_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    parts = []

    # Executive summary
    if spec.get("executive_summary"):
        parts.append(render_executive_summary(spec["executive_summary"]))

    # Top-level metrics
    if spec.get("metrics"):
        parts.append(_render_metrics_items(spec["metrics"]))

    # Main numbered sections
    for section in spec.get("sections", []):
        parts.append(render_section(section))

    # Additional sections
    for section in spec.get("additional_sections", []):
        parts.append(render_section(section))

    # Top-level bibliography (auto-rendered as last section)
    if spec.get("bibliography"):
        bib_section = {
            "title": "References",
            "blocks": [{
                "type": "bibliography",
                "references": spec["bibliography"],
            }],
        }
        parts.append(render_section(bib_section))

    return "\n\n".join(parts)


def load_spec(yaml_path: str) -> dict:
    """Load and return the YAML spec dict."""
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert YAML spec to HTML content for reports"
    )
    parser.add_argument("input", help="YAML spec file")
    parser.add_argument("--output", "-o", help="Output HTML file (default: stdout)")
    parser.add_argument("--strict", action="store_true", default=True,
                        help="Exit 1 on validation errors (default: True)")
    parser.add_argument("--no-strict", action="store_true",
                        help="Allow validation errors (emit warning but don't block)")
    args = parser.parse_args()

    global _current_source
    _current_source = Path(args.input).name

    result = yaml_to_html(args.input)

    n_errors = get_validation_error_count()
    if n_errors > 0:
        if not args.no_strict:
            print(f"BLOCKED: {n_errors} rendering error(s) in YAML. Fix and try again.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"WARNING: {n_errors} rendering error(s) (--no-strict, continuing)", file=sys.stderr)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
        print(f"Content HTML written: {out} ({out.stat().st_size / 1024:.1f}KB)")
    else:
        print(result)


if __name__ == "__main__":
    main()
