"""The one canonical element-vocabulary renderer (Close architecture, ADR-0012/0013).

A structured-spec dict in, an HTML string out. This is the single source of the block
palette — de-YAML'd from the legacy `yaml_to_html.py` (the vocabulary used to live in
three places: a markdown doc, that renderer, and base.css; this cures the DRY to one).

The palette is ONE registry: structural blocks (paragraph, table, card, callout, …),
planning blocks (next-steps-grid, flow-example, …) and the Feynman blocks (derivation,
gap-marker, gap-table, gap-resolution) are all ordinary elements — reach for any of them
anywhere, none is a mandatory section. The class hooks match the neutralized base.css.

Pure Python: no YAML loading, no config/paths imports, no render-log file deps. Import-clean
on bare python3. An unknown block type degrades to an HTML comment — it never raises.
"""
import copy
import hashlib
import html
import json
import re
from html.parser import HTMLParser

import visual_recipes


# ---------------------------------------------------------------------------
# URL safety — ONE allowlist for every generated href/src (markdown links,
# bibliography URLs, the raw-html sanitizer). The publisher serves pages publicly,
# so source-influenced URLs must never emit an executable scheme.
# ---------------------------------------------------------------------------

# Safe schemes: http(s), mailto, tel, #anchors, relative paths, and scheme-less.
# Unsafe (javascript:, script-bearing data:, mixed-case, leading-whitespace/control
# variants) fail this — `[^:]*$` rejects any colon-bearing value not on the allowlist.
_SAFE_URL = re.compile(r"^(?:https?:|mailto:|tel:|#|/|\./|\.\./|[^:]*$)", re.IGNORECASE)


def safe_url(url: str) -> str:
    """Return `url` if it uses a safe scheme, else "" — the single gate for every
    generated href/src. Strips leading/trailing whitespace+control chars before the
    check so `\\tjavascript:` style smuggling is caught."""
    if not url:
        return ""
    return url if _SAFE_URL.match(str(url).strip()) else ""


# ---------------------------------------------------------------------------
# Text rendering helpers
# ---------------------------------------------------------------------------

def _md_link(m):
    """[text](url) → anchor, but only for a safe URL; otherwise plain text fallback."""
    text, url = m.group(1), m.group(2)
    cleaned = safe_url(html.unescape(url))
    if not cleaned:
        return f"{text} ({url})"
    return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'


def render_text(s: str) -> str:
    """Escape HTML, then convert **bold**, *italic*, `code`, [text](url) markers."""
    if not s:
        return ""
    s = html.escape(str(s))
    # Pass through a SAFELIST of inline formatting tags the producer may emit as raw HTML
    # (the rest stays escaped — e.g. a literal `<slug>` is still shown verbatim, and no tag
    # with attributes, `<script>`, or an `on*` handler can slip through). Both opening and
    # closing forms, optional self-close for void tags. This is what lets a spec write
    # `<b>…</b>` / `<code>…</code>` without it rendering as literal text.
    s = re.sub(
        r'&lt;(/?)(b|i|strong|em|code|u|s|sub|sup|mark|small|br)\s*/?&gt;',
        lambda m: f'<{m.group(1)}{m.group(2).lower()}>', s, flags=re.IGNORECASE,
    )
    # Markdown links: [text](url) — after escape, brackets/parens are preserved.
    # The URL is gated through safe_url; an unsafe scheme degrades to plain text.
    s = re.sub(r'\[(.+?)\]\((.+?)\)', _md_link, s)
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


# ---------------------------------------------------------------------------
# Attribute safety — spec-controlled values must never break out of their
# attribute quote. EVERY interpolated class/data-*/title/id/etc. value goes
# through `attr_value`; freeform `style` goes through `safe_style`.
# ---------------------------------------------------------------------------

def attr_value(value) -> str:
    """Escape a spec-controlled value for use inside a double-quoted HTML attribute.
    Neutralizes the quote-break (`"`) so a payload can never close the attribute and
    inject a new one (e.g. an on*= event handler)."""
    return html.escape(str(value), quote=True)


# A single CSS declaration: `prop: value` with a safe-char allowlist. Disallows the
# quote chars, angle brackets, parens, semicolons inside the value — anything that
# could break out of the attribute or smuggle url()/expression()/behavior payloads.
_CSS_DECL = re.compile(r"^\s*[a-zA-Z-]+\s*:\s*[A-Za-z0-9 #%.,\-_/]+\s*$")


def safe_style(value) -> str:
    """Allowlist a freeform `style` value to `prop: value;` declarations whose tokens
    use only safe characters. Any declaration with quotes, angle brackets, parens
    (url()/expression()), or other breakout chars is dropped. Returns the kept
    declarations joined by `; ` (already attribute-quote-safe)."""
    kept = []
    for decl in str(value).split(";"):
        if decl.strip() and _CSS_DECL.match(decl):
            kept.append(decl.strip())
    return "; ".join(kept)


def badge_html(text: str, variant: str = "neutral") -> str:
    """Generate a badge span."""
    return f'<span class="badge badge-{attr_value(variant)}">{html.escape(str(text))}</span>'


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
    safe = safe_style(b["style"]) if b.get("style") else ""
    style = f' style="{safe}"' if safe else ""
    return f'<p{style}>{render_text(b.get("text", ""))}</p>'


@renderer("subsection")
def render_subsection(b):
    return f'<h3 class="subsection-title">{render_text(b["title"])}</h3>'


@renderer("concept-grid")
def render_concept_grid(b):
    items = b.get("items", []) or b.get("concepts", [])
    cells = []
    for item in items:
        if not isinstance(item, dict):  # fail-closed: a non-dict item has no name/text
            continue
        cells.append(
            f'<div class="callout callout-info">'
            f'<strong>{render_text(item.get("name", item.get("title", "(sem nome)")))}</strong><br>'
            f'{render_text(item.get("text") or item.get("description") or item.get("definition") or "")}'
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
        f'<div class="callout callout-{attr_value(variant)}">'
        f'{title_html}{render_text(b.get("text", ""))}'
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
        classes.append(attr_value(b["card_class"]))
    cls = " ".join(classes)
    parts = [f'<div class="{cls}" data-iter="{attr_value(num)}">']
    parts.append('<div class="card-header">')
    parts.append(f'<span class="card-title">{render_text(b.get("title", ""))}</span>')
    if b.get("badge"):
        bc = b.get("badge_class", "neutral")
        parts.append(badge_html(b["badge"], bc))
    parts.append('</div>')
    nc_text = b.get("text") or b.get("description") or b.get("content") or b.get("body") or ""
    if nc_text:
        parts.append(f'<p style="font-size: 14px;">{render_text(nc_text)}</p>')
    parts.append('</div>')
    return "\n".join(parts)


@renderer("flow-example")
def render_flow_example(b):
    # No hardcoded English "Input"/"Output" (structure not strings): the labels render ONLY if the
    # producer supplies them (in-language); the yellow/green styling already distinguishes the two.
    input_label = b.get("input_label", "")
    output_label = b.get("output_label", "")
    parts = ['<div class="card">']
    if b.get("label"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(b["label"])}</span>')
        parts.append('</div>')

    # Input pre (yellow)
    if input_label:
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
    if output_label:
        parts.append(
            f'<p style="font-size: 13px; font-weight: 600; margin-top: 12px; '
            f'margin-bottom: 8px;">{render_text(output_label)}:</p>'
        )
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 12px; '
        f'line-height: 1.55; background: #DEF7EC; padding: 12px; border-radius: 6px; '
        f'border-left: 3px solid var(--brand-green, #38a169);">'
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
    # Structural transform: flat left_*/right_* fields → nested before/after objects.
    # Build a local view; never mutate the caller's (proof-bound) block dict.
    before = dict(b.get("before") or b.get("left") or {})
    after = dict(b.get("after") or b.get("right") or {})
    for src, dst in [("left", before), ("right", after)]:
        if f"{src}_title" in b:
            dst.setdefault("title", b[f"{src}_title"])
        if f"{src}_items" in b:
            dst.setdefault("bullets", b[f"{src}_items"])

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
        side_text = side.get("text") or side.get("content") or side.get("description") or ""
        if side_text:
            # Support multiline: split on newlines for readability
            for line in str(side_text).split("\n"):
                line = line.strip()
                if line:
                    p.append(f'<p style="font-size: 14px;">{render_text(line)}</p>')
        p.append('</div>')
        return "\n".join(p)

    return (
        f'<div class="comparison-grid">\n'
        f'{_side(before)}\n'
        f'{_side(after)}\n'
        f'</div>'
    )


@renderer("table")
def render_table(b):
    highlight = set(b.get("highlight_rows", []))
    score_row_idx = b.get("score_row")
    parts = ['<div class="table-wrapper">']
    if b.get("title"):
        parts.append(f'<p style="font-weight:600;font-size:14px;margin-bottom:8px;">{render_text(b["title"])}</p>')
    parts.extend(['<table>', '<thead>', '<tr>'])
    for h in b.get("headers", []):
        parts.append(f'<th>{render_text(h)}</th>')
    parts.append('</tr></thead><tbody>')
    rows = b.get("rows", [])
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, (list, tuple)):  # fail-closed: a non-iterable row has no cells
            continue
        tr_class = ""
        if i == score_row_idx:
            tr_class = ' class="score-row"'
        elif i in highlight:
            tr_class = ' style="background: #DEF7EC;"'
        parts.append(f'<tr{tr_class}>')
        for cell in row:
            parts.append(f'<td>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')
    if b.get("note"):
        parts.append(
            f'<p style="font-size: 12px; color: var(--gray-500); margin-top: 4px;">'
            f'{render_text(b["note"])}</p>'
        )
    parts.append('</div>')
    return "\n".join(parts)


@renderer("comparison-table")
def render_comparison_table(b):
    parts = ['<div class="table-wrapper">', '<table>', '<thead>', '<tr>']
    for h in b.get("headers", []):
        parts.append(f'<th>{render_text(h)}</th>')
    parts.append('</tr></thead><tbody>')
    for row in b.get("rows", []):
        if not isinstance(row, dict):  # fail-closed: a non-dict row has no cells/classes
            continue
        cells = row.get("cells", [])
        classes = row.get("classes", [])
        if not isinstance(classes, list):  # classes must index by column — degrade if not a list
            classes = []
        parts.append('<tr>')
        for j, cell in enumerate(cells if isinstance(cells, list) else []):
            cls = classes[j] if j < len(classes) else ""
            td_cls = f' class="{attr_value(cls)}"' if cls else ""
            parts.append(f'<td{td_cls}>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    sr = b.get("score_row")
    if isinstance(sr, dict):  # fail-closed: only a dict score_row carries cells/classes
        cells = sr.get("cells", [])
        classes = sr.get("classes", [])
        if not isinstance(classes, list):
            classes = []
        parts.append('<tr class="score-row">')
        for j, cell in enumerate(cells if isinstance(cells, list) else []):
            cls = classes[j] if j < len(classes) else ""
            td_cls = f' class="{attr_value(cls)}"' if cls else ""
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
    parts.append('<th>Risco</th><th>Probabilidade</th><th>Mitigacao</th>')
    parts.append('</tr></thead><tbody>')
    for row in b["rows"]:
        prob = row.get("probability", "media")
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
    content = b.get("content") or b.get("code", "")
    label = b.get("label") or b.get("title", "")
    parts = ['<div class="card">']
    if label or b.get("badge"):
        parts.append('<div class="card-header">')
        parts.append(f'<span class="card-title">{render_text(label)}</span>')
        if b.get("badge"):
            bc = b.get("badge_class", "info")
            parts.append(badge_html(b["badge"], bc))
        parts.append('</div>')
    parts.append(
        f'<pre style="font-family: \'Courier New\', monospace; font-size: 13px; '
        f'line-height: 1.55; background: var(--gray-50); padding: 16px; '
        f'border-radius: 6px; overflow-x: auto;">'
        f'{render_pre(content)}</pre>'
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


# ---------------------------------------------------------------------------
# Visual recipe set — the `chart` (Vega-Lite) and `diagram` (full Vega) blocks of the shared rich
# producer protocol (docs/specs/visual-recipe-set.md). The writer NEVER emits Vega: it emits the
# edge's own tiny schema (data + light config); `visual_recipes` expands that into the chosen
# CLOSED recipe's spec, `vl-convert` renders it to SVG (pure-Python, no system binary, no root),
# and the SVG is allowlist-SANITIZED before inlining — no script, no event handlers, no
# foreignObject, no external href/image. Both blocks are capability-gated on `vl-convert` (absent →
# the block degrades to a comment, never a crash, never raw passthrough) and FAIL CLOSED on a
# malformed payload (a clear comment from the recipe validator, never a blank chart, never a raise).
# Store the SCHEMA, never the SVG (the SVG is a re-rendered projection — ADR-0006).
# ---------------------------------------------------------------------------


def _vl_convert():
    """Import vl-convert lazily so the module is import-clean where the wheel is absent (the gate is
    defense; the wheel is present by default). Returns the module, or None when not installed."""
    try:
        import vl_convert  # noqa: PLC0415 — capability probe, intentionally local
        return vl_convert
    except ImportError:
        return None


def diagram_available() -> bool:
    """True iff the visual backend (`vl-convert`) is importable — the chart/diagram capability."""
    return _vl_convert() is not None


def _sanitize_svg(svg: str) -> str:
    """Strip everything script/network-capable from vl-convert-generated SVG before inlining:
    <script>, on* event handlers, <foreignObject>, <image>, and any non-fragment href/xlink:href.
    The inlined SVG must be inert. This is the trust boundary — applied to EVERY vl-convert SVG
    (chart and diagram). (Vega/vl-convert output is well-formed and predictable; this is an
    allowlist-leaning strip, not a general HTML sanitizer.)"""
    svg = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", svg, flags=re.I | re.S)
    svg = re.sub(r"<script\b[^>]*/?>", "", svg, flags=re.I)
    svg = re.sub(r"<foreignObject\b.*?</foreignObject\s*>", "", svg, flags=re.I | re.S)
    svg = re.sub(r"<image\b[^>]*/?>", "", svg, flags=re.I)
    # event handlers — quoted (double/single) AND unquoted values
    svg = re.sub(r"\son[a-zA-Z]+\s*=\s*\"[^\"]*\"", "", svg, flags=re.I)
    svg = re.sub(r"\son[a-zA-Z]+\s*=\s*'[^']*'", "", svg, flags=re.I)
    svg = re.sub(r"\son[a-zA-Z]+\s*=\s*[^\s>]+", "", svg, flags=re.I)
    # href / xlink:href — keep ONLY same-document #fragments; strip external/js, quoted or unquoted
    svg = re.sub(r"\s(?:xlink:)?href\s*=\s*\"(?!#)[^\"]*\"", "", svg, flags=re.I)
    svg = re.sub(r"\s(?:xlink:)?href\s*=\s*'(?!#)[^']*'", "", svg, flags=re.I)
    svg = re.sub(r"\s(?:xlink:)?href\s*=\s*(?![\"']?#)[^\s>]+", "", svg, flags=re.I)
    return svg


def _render_vega(builder, payload, kind, vega_to_svg):
    """Shared chart/diagram render path. `builder(payload) -> (spec, error)`; `vega_to_svg` is the
    vl-convert function for the backend (vegalite_to_svg / vega_to_svg). Returns the inlined,
    sanitized `<div class="kind">…</div>`, or a clear comment on a malformed payload / render
    failure. NEVER raises — a renderer must never crash the page."""
    if not isinstance(payload, dict):
        return f"<!-- {kind}: payload must be a mapping -->"
    spec, error = builder(payload)
    if error:
        return f"<!-- {kind}: {html.escape(str(error))} -->"
    try:
        raw = vega_to_svg(json.dumps(spec))
    except Exception as e:  # noqa: BLE001 — never let a renderer crash the page
        return f"<!-- {kind}: render failed: {html.escape(type(e).__name__)} -->"
    svg = _sanitize_svg(raw)
    return f'<div class="{kind}">{svg}</div>'


def chart_renderable(block: dict) -> bool:
    """True iff a `chart` block would ACTUALLY render to a visual: vl-convert importable, the recipe
    VALIDATES, AND it actually renders (build spec + vl-convert succeeds). Gates (visual-coverage,
    the presentation floor) use this so a malformed/blank chart never satisfies a visual obligation."""
    return _renderable(block, visual_recipes.build_chart, "vegalite_to_svg")


def diagram_renderable(block: dict) -> bool:
    """True iff a `diagram` block would ACTUALLY render to a visual: vl-convert importable, the
    recipe VALIDATES, AND it actually renders. The authoritative renderable check the gates use so a
    non-rendering diagram (no vl-convert, malformed topology, unknown layout) never satisfies a
    visual obligation."""
    return _renderable(block, visual_recipes.build_diagram, "vega_to_svg")


def _renderable(block, builder, fn_name) -> bool:
    if not isinstance(block, dict):
        return False
    vl = _vl_convert()
    if vl is None:
        return False
    spec, error = builder(block)
    if error:
        return False
    try:
        getattr(vl, fn_name)(json.dumps(spec))
    except Exception:  # noqa: BLE001
        return False
    return True


@renderer("chart")
def render_chart(b):
    vl = _vl_convert()
    if vl is None:
        return "<!-- chart unavailable: vl-convert not installed -->"
    return _render_vega(visual_recipes.build_chart, b, "chart", vl.vegalite_to_svg)


@renderer("diagram")
def render_diagram(b):
    vl = _vl_convert()
    if vl is None:
        return "<!-- diagram unavailable: vl-convert not installed -->"
    return _render_vega(visual_recipes.build_diagram, b, "diagram", vl.vega_to_svg)


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
    raw_steps = b.get("steps", []) or b.get("items", [])
    steps = list(raw_steps) if isinstance(raw_steps, list) else []
    # Support now/next/later grouping (flatten into steps)
    if not steps:
        for phase_key in ("now", "next", "later"):
            phase_items = b.get(phase_key, [])
            if isinstance(phase_items, list):
                for item in phase_items:
                    if isinstance(item, dict):
                        # Build a new dict; never mutate the caller's item.
                        item = {"phase": phase_key, **item}
                    steps.append(item)
            elif isinstance(phase_items, str):
                steps.append({"title": phase_items, "phase": phase_key})
    for step in steps:
        # Normalize: string → dict; a non-dict/non-str step (int, None) is skipped (fail-closed).
        if isinstance(step, str):
            step = {"title": step}
        elif not isinstance(step, dict):
            continue
        parts.append('<div class="next-step-card">')
        # Support both "number" and "phase"/"priority" as the badge
        badge = step.get("number") or step.get("phase") or step.get("priority") or step.get("owner") or ""
        title = step.get("title") or step.get("action") or step.get("label") or ""
        parts.append(
            f'<span class="step-number">{html.escape(str(badge))}</span>'
            f'<span class="step-title">{render_text(title)}</span>'
        )
        desc = step.get("description") or step.get("text") or step.get("detail") or step.get("content") or ""
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
    style = safe_style(b.get("style", "padding-left: 20px; font-size: 14px; line-height: 1.7;"))
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
        if not isinstance(line, dict):  # fail-closed: a non-dict line has no type/text
            continue
        line_type = line.get("type", "context")
        css_class = f"diff-{attr_value(line_type)}"
        prefix = {"insert": "+ ", "delete": "- ", "context": "  "}.get(line_type, "  ")
        parts.append(
            f'<div class="{css_class}">{prefix}{render_pre(line.get("text", ""))}</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# Tags dropped wholesale — content too (executable / framing). Allowlist everything else.
_RAW_HTML_DROP_TAGS = frozenset({
    "script", "iframe", "foreignobject", "object", "embed", "link", "meta",
    "style", "base", "form", "input", "button", "textarea",
})
# URL-bearing attributes whose value must use a safe scheme (no javascript:/data:-script).
_RAW_HTML_URL_ATTRS = frozenset({"href", "src", "xlink:href", "action", "formaction"})


class _RawHtmlSanitizer(HTMLParser):
    """De-fang a raw-html block while keeping benign HTML and inline SVG. Drops dangerous
    tags (and their content), strips on*= event handlers, and rejects script-bearing URL
    schemes (javascript:/data:) on href/src-style attributes. Allowlist-style."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._suppress_depth = 0  # >0 while inside a dropped tag's subtree

    def _safe_attrs(self, attrs):
        kept = []
        for name, value in attrs:
            lname = name.lower()
            value = value or ""
            if lname.startswith("on"):  # event handler — never safe
                continue
            if lname in _RAW_HTML_URL_ATTRS and not safe_url(value):
                continue
            kept.append((name, value))
        return kept

    def handle_starttag(self, tag, attrs):
        if self._suppress_depth:
            return
        if tag.lower() in _RAW_HTML_DROP_TAGS:
            self._suppress_depth = 1
            return
        rendered = "".join(
            f' {name}="{html.escape(value, quote=True)}"' for name, value in self._safe_attrs(attrs)
        )
        self.out.append(f"<{tag}{rendered}>")

    def handle_startendtag(self, tag, attrs):
        if self._suppress_depth:
            return
        if tag.lower() in _RAW_HTML_DROP_TAGS:
            return
        rendered = "".join(
            f' {name}="{html.escape(value, quote=True)}"' for name, value in self._safe_attrs(attrs)
        )
        self.out.append(f"<{tag}{rendered}/>")

    def handle_endtag(self, tag):
        if self._suppress_depth:
            if tag.lower() in _RAW_HTML_DROP_TAGS:
                self._suppress_depth = 0
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._suppress_depth:
            return
        self.out.append(html.escape(data, quote=False))


def sanitize_raw_html(content: str) -> str:
    """Render-time sanitizer for raw-html blocks (the publisher serves pages publicly)."""
    if not content:
        return ""
    parser = _RawHtmlSanitizer()
    parser.feed(str(content))
    parser.close()
    return "".join(parser.out)


@renderer("raw-html")
def render_raw_html(b):
    return sanitize_raw_html(b.get("content", b.get("html", "")))


# ---------------------------------------------------------------------------
# Feynman method blocks — ordinary palette elements (reachable, never mandatory)
# ---------------------------------------------------------------------------

@renderer("derivation")
def render_derivation(b):
    """Block for 'what I derived from scratch' — purple-bordered card. The header renders ONLY when
    the spec carries a `title` — no hardcoded-language default (structure not strings); the icon-only
    header still marks the block visually when untitled."""
    parts = ['<div class="derivation">']
    title = b.get("title")
    parts.append('<div class="derivation-header">')
    parts.append('<span class="derivation-icon">D</span>')
    if title:
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
    """A gap callout — amber/orange styling IS the marker (structure not strings: no hardcoded "GAP").
    The gap text is the one semantic field; `label`/`description` are synonyms for it (see BLOCK_SCHEMAS),
    so they are NOT a separate badge — they would be canonicalized into `text` before this renderer runs.
    An optional structural `id` (language-neutral) renders as a "#id" tag."""
    parts = ['<div class="gap-marker">']
    if b.get("id"):
        parts.append(f'<span class="gap-marker-label">#{html.escape(str(b["id"]))}</span>')
    parts.append(f'{render_text(b["text"])}')
    parts.append('</div>')
    return "\n".join(parts)


_GAP_STATUS_CLS = {
    "resolvido": "gap-status-resolved", "resolved": "gap-status-resolved",
    "parcial": "gap-status-partial", "partial": "gap-status-partial",
    "aberto": "gap-status-open", "open": "gap-status-open",
}


@renderer("gap-table")
def render_gap_table(b):
    """Gaps, language-agnostic (structure not strings). TWO shapes, no hybrid guessing:
      (1) `gaps` — a list of semantic dicts {description, need?, status?} → a clean list with ZERO
          hardcoded chrome (the producer never has to name columns; status text is its own in-language
          value, only the CSS color is mapped; an absent status renders no badge).
      (2) `headers`+`rows` — explicit pre-laid-out cells → the generic labeled table verbatim.
    There is deliberately no `headers`+`gaps`(dicts) path: positionally mapping in-language headers onto
    a fixed dict schema misaligns the moment the producer's column order differs (e.g. an `id` column).
    A producer who wants labeled columns supplies `rows`; otherwise the dict list is the canonical form."""
    # Shape (2): custom labeled table — rows are already cells, so they can never misalign.
    if b.get("headers") and b.get("rows"):
        return render_table(b)
    gaps = b.get("gaps", [])

    def _badge(status):
        if not status:
            return ""
        cls = _GAP_STATUS_CLS.get(str(status).lower(), "gap-status-open")
        return f' <span class="{cls}">{html.escape(str(status).upper())}</span>'

    # Shape (1): language-agnostic list (zero hardcoded chrome). Headers without rows are ignored —
    # the gaps still render in full; only the unusable column labels are dropped.
    parts = ['<div class="gap-table"><ul>']
    for row in gaps:
        # An `id` is language-neutral chrome and pairs with gap-resolution.gap_id — keep it as a "#id" tag.
        idtag = (f'<span class="gap-marker-label">#{html.escape(str(row["id"]))}</span> '
                 if row.get("id") else "")
        desc = render_text(row.get("description", ""))
        need = f' — {render_text(row.get("need", ""))}' if row.get("need") else ""
        parts.append(f'<li>{idtag}{desc}{need}{_badge(row.get("status", ""))}</li>')
    parts.append('</ul></div>')
    return "\n".join(parts)


@renderer("gap-resolution")
def render_gap_resolution(b):
    """Links a gap to its resolution — amber header, green answer."""
    # No hardcoded "Gap" label (structure not strings): a producer may pass `label` in-language; else
    # the styling marks it. An `gap_id` shows as "#id".
    label = (b.get("label") or "").strip()
    if b.get("gap_id"):
        label = (f'{label} #{b["gap_id"]}').strip()
    parts = ['<div class="gap-resolution">']
    # Header: the gap
    parts.append('<div class="gap-resolution-header">')
    if label:
        parts.append(f'<span class="gap-marker-label">{html.escape(label)}</span>')
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
                    if safe_url(url):
                        li_parts.append(
                            f' <a href="{escaped_url}" target="_blank" '
                            f'rel="noopener" class="bibliography-url">{escaped_url}</a>'
                        )
                    else:
                        # Unsafe scheme — show the URL as plain text, no executable href.
                        li_parts.append(
                            f' <span class="bibliography-url">{escaped_url}</span>'
                        )
                if source:
                    variant = {
                        "websearch": "info", "web": "info",
                        "x": "neutral", "twitter": "neutral",
                        "arxiv": "success", "paper": "success", "semantic scholar": "success",
                        "github": "neutral", "hackernews": "warning", "hn": "warning",
                        "moltbook": "info", "blog": "neutral", "docs": "info",
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

# ---------------------------------------------------------------------------
# Evidence — the verbatim-quote block (Phase 0: evidence-safety + authenticity).
# A claim discharges by paraphrase; an EVIDENCE item discharges only by a verbatim
# quote PROVABLY copied from its cited source. The block carries source_ref + anchor
# (sha256 of the verbatim span); verify_evidence checks the anchor matches the stored
# text AND (when a source corpus is supplied) that the quote is the cited source's span.
# ---------------------------------------------------------------------------

@renderer("evidence")
def render_evidence(b):
    """A verbatim source quote with attribution, rendered as a blockquote. The quote is
    HTML-escaped ONLY (never markdown-transformed), so the displayed span stays byte-faithful
    to the anchored/verified text — `**x**`, backticks, `--`, and `[a](b)` survive literally."""
    raw = b.get("quote_text") or b.get("quote") or b.get("text") or ""
    quote = html.escape(raw if isinstance(raw, str) else "", quote=False)
    attribution = b.get("attribution") or b.get("source_ref") or b.get("source") or ""
    cite = f'<cite>{render_text(attribution)}</cite>' if attribution else ""
    return (
        # white-space:pre-wrap keeps newlines and runs of spaces — the displayed span must stay
        # byte-faithful to the anchored quote, and HTML would otherwise collapse them.
        f'<blockquote class="callout callout-info evidence">'
        f'<span class="evidence-quote" style="white-space:pre-wrap">{quote}</span>'
        f'{("<br>" + cite) if cite else ""}'
        f'</blockquote>'
    )


def evidence_anchor(text: str) -> str:
    """The canonical anchor for a verbatim span: a sha256 hexdigest of its UTF-8 bytes."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def verify_evidence(block: dict, sources: dict | None = None) -> tuple[bool, str]:
    """Prove an evidence block is authentic, not merely preserved. Returns (ok, reason).

    Checks, in order:
      1. anchor integrity  — `anchor` must equal sha256(quote_text) (tamper check);
      2. source presence   — `source_ref` must resolve in the supplied `sources` corpus;
      3. span authenticity — quote_text must appear verbatim in the cited source text.
    `sources` is source_ref -> full source text. When None, only the anchor check runs
    (preservation-only mode); pass the corpus to prove the quote was copied, not fabricated.
    """
    quote = block.get("quote_text") or block.get("quote") or block.get("text") or ""
    if not isinstance(quote, str) or not quote:
        return False, "evidence quote_text is missing or not a string"
    ref = block.get("source_ref") or block.get("source")
    if not isinstance(ref, str) or not ref.strip():
        return False, "evidence source_ref is missing or blank"
    if block.get("anchor") != evidence_anchor(quote):
        return False, "anchor mismatch: quote_text does not match its anchor (tampered)"
    if sources is None:
        return True, ""
    if ref not in sources:
        return False, f"source_ref {ref!r} resolves to no cited source"
    if quote not in sources[ref]:
        return False, "quote_text is not a verbatim span of the cited source (fabricated or altered)"
    return True, ""


def is_evidence_discharged(block: dict, sources: dict | None = None) -> bool:
    """The discharge predicate the close/producer gate calls. Discharge **requires** the source
    corpus: an evidence item that cannot be proven against its cited source does not discharge —
    anchor-only preservation (a self-consistent hash) is NOT proof of authenticity, so a fabricated
    quote can never discharge. Paraphrase (text not in the cited source span) never discharges."""
    if sources is None:
        return False
    return verify_evidence(block, sources)[0]


BLOCK_SCHEMAS = {
    "paragraph": {
        "required": ["text"],
        "optional": ["style"],
        "synonyms": {"content": "text", "description": "text", "body": "text"},
    },
    "evidence": {
        "required": ["quote_text", "source_ref", "anchor"],
        "optional": ["attribution"],
        "synonyms": {"text": "quote_text", "quote": "quote_text", "source": "source_ref"},
    },
    "chart": {
        "required": ["chart", "data"],
        "optional": ["title", "x_label", "y_label", "before_label", "after_label",
                     "horizontal", "facet", "v"],
        "synonyms": {"recipe": "chart", "values": "data", "rows": "data"},
    },
    "diagram": {
        "required": ["layout", "nodes"],
        "optional": ["edges", "title", "orientation", "v"],
        "synonyms": {"recipe": "layout", "links": "edges"},
    },
    "subsection": {
        "required": ["title"],
        "optional": [],
        "synonyms": {},
    },
    "concept-grid": {
        "required": [],
        "optional": ["items", "concepts"],
        "synonyms": {"concepts": "items"},
    },
    "callout": {
        "required": ["text"],
        "optional": ["variant", "style", "title"],
        "synonyms": {},
    },
    "card": {
        "required": [],
        "optional": ["title", "badge", "badge_class", "text", "bullets", "label"],
        "synonyms": {"label": "title"},
    },
    "numbered-card": {
        "required": [],
        "optional": ["items", "number", "title", "badge", "badge_class", "text", "card_class"],
        "synonyms": {"content": "text", "description": "text", "body": "text", "badge_variant": "badge_class"},
    },
    "flow-example": {
        "required": ["input", "output"],
        "optional": ["label", "input_label", "output_label", "code"],
        "synonyms": {},
    },
    "comparison": {
        "required": [],
        "optional": ["before", "after", "left", "right", "left_title", "left_items", "right_title", "right_items", "title"],
        "synonyms": {"left": "before", "right": "after"},
    },
    "table": {
        "required": ["headers", "rows"],
        "optional": ["highlight_rows", "score_row", "title", "note"],
        "synonyms": {"columns": "headers"},
    },
    "comparison-table": {
        "required": ["headers", "rows"],
        "optional": ["score_row", "note"],
        "synonyms": {},
    },
    "risk-table": {
        "required": ["rows"],
        "optional": [],
        "synonyms": {},
    },
    "code-block": {
        "required": ["content"],
        "optional": ["label", "badge", "badge_class"],
        "synonyms": {"code": "content", "title": "label"},
    },
    "ascii-diagram": {
        "required": ["content"],
        "optional": ["title"],
        "synonyms": {},
    },
    "template-block": {
        "required": ["content"],
        "optional": ["title", "description", "note"],
        "synonyms": {},
    },
    "next-steps-grid": {
        "required": [],
        "optional": ["steps", "items", "now", "next", "later"],
        "synonyms": {"items": "steps"},
    },
    "metrics-grid": {
        "required": [],
        "optional": ["items", "metrics"],
        "synonyms": {"metrics": "items"},
    },
    "list": {
        "required": [],
        "optional": ["items", "ordered", "style"],
        "synonyms": {},
    },
    "diff-block": {
        "required": [],
        "optional": ["header", "lines"],
        "synonyms": {"title": "header", "label": "header"},
    },
    "raw-html": {
        "required": [],
        "optional": ["content", "html"],
        "synonyms": {"html": "content", "text": "content"},
    },
    "derivation": {
        "required": [],
        "optional": ["title", "text", "bullets", "code", "label"],
        "synonyms": {"steps": "bullets", "label": "title", "conclusion": "text"},
    },
    "gap-marker": {
        "required": ["text"],
        "optional": ["id"],
        "synonyms": {"label": "text", "description": "text"},
    },
    "gap-table": {
        "required": [],
        "optional": ["gaps", "headers", "rows"],
        "synonyms": {},
    },
    "gap-resolution": {
        "required": [],
        "optional": ["gap_id", "gap", "text", "answer"],
        "synonyms": {"title": "gap", "question": "gap", "resolution": "answer"},
    },
    "bibliography": {
        "required": [],
        "optional": ["title", "references"],
        "synonyms": {},
    },
    "glossary": {
        "required": [],
        "optional": ["context", "terms"],
        "synonyms": {"items": "terms"},
    },
}


# ---------------------------------------------------------------------------
# Block type aliases — forgiving names funnel into the canonical palette
# ---------------------------------------------------------------------------

_BLOCK_TYPE_ALIASES = {
    # Paragraph aliases
    "text": "paragraph",
    "p": "paragraph",
    "body": "paragraph",
    # Table aliases
    "key-value": "table",
    "kv": "table",
    "data-table": "table",
    "stat-row": "table",
    # Metrics aliases
    "metrics": "metrics-grid",
    "metric-card": "metrics-grid",
    "metric-cards": "metrics-grid",
    "kpi-row": "metrics-grid",
    "kpi-grid": "metrics-grid",
    "stats": "metrics-grid",
    # Card aliases
    "numbered-cards": "numbered-card",
    "step-card": "numbered-card",
    "steps": "next-steps-grid",
    # Code aliases
    "code": "code-block",
    "code-snippet": "code-block",
    # Raw HTML aliases
    "custom-html": "raw-html",
    "html": "raw-html",
    "svg": "raw-html",
    # List aliases
    "bullet-list": "list",
    "bullets": "list",
    "ordered-list": "list",
    # Comparison aliases
    "pros-cons": "comparison",
    "compare": "comparison",
    # Callout aliases
    "note": "callout",
    "warning": "callout",
    "info": "callout",
    "alert": "callout",
    "tip": "callout",
    # Evidence aliases — the verbatim-quote block
    "quote": "evidence",
    "blockquote": "evidence",
    "verbatim": "evidence",
    # Diagram aliases — the Vega graph-layout illustration block (dag/force)
    "graph": "diagram",
    "dag": "diagram",
    "force-graph": "diagram",
    "network": "diagram",
    # Chart aliases — the Vega-Lite data-chart block (line/sparkline/bar/scatter/slopegraph)
    "vega-lite": "chart",
    "vegalite": "chart",
    "plot": "chart",
    "graph-chart": "chart",
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def canonical_block(block: dict):
    """Return `(block_type, normalized_block)`: the canonical type (aliases resolved) and a NEW
    block dict with field synonyms normalized to the canonical fields each renderer reads
    (e.g. `content`→`text` for paragraph, `text`→`content` for raw-html). Returns `(None, block)`
    for a non-dict / non-string-type block. PURE — never mutates the caller's block.

    The single source of truth for canonicalization, shared by `render_block` and the substance
    predicate (`tools/blocks.py`) so the gate sees the SAME canonical fields the renderer reads."""
    if not isinstance(block, dict):
        return None, block
    block_type = block.get("type", "paragraph")
    if not isinstance(block_type, str):
        return None, block
    if block_type in _BLOCK_TYPE_ALIASES:
        block_type = _BLOCK_TYPE_ALIASES[block_type]
        block = {**block, "type": block_type}
    schema = BLOCK_SCHEMAS.get(block_type)
    if schema:
        synonyms = schema.get("synonyms", {})
        if any(syn in block and canonical not in block
               for syn, canonical in synonyms.items()):
            block = dict(block)
            for syn, canonical in synonyms.items():
                if syn in block and canonical not in block:
                    block[canonical] = block.pop(syn)
    return block_type, block


def render_block(block: dict) -> str:
    """Dispatch a single block to its renderer.

    Unknown block type → an HTML comment, never an exception. Field synonyms are
    normalized to the canonical field the renderer expects (via `canonical_block`).

    PURE w.r.t. its input: alias-type rewrites and synonym normalization build a NEW
    block dict, so the caller's proof-bound block is never mutated.
    """
    if not isinstance(block, dict):  # fail-closed: a non-dict block degrades, never crashes
        return "<!-- malformed block: not a mapping -->"
    raw_type = block.get("type", "paragraph")
    if not isinstance(raw_type, str):  # a non-string type can't alias/dispatch — degrade
        return f'<!-- malformed block type: {html.escape(str(raw_type))} -->'
    block_type, block = canonical_block(block)
    fn = RENDERERS.get(block_type)
    if fn is None:
        return f'<!-- unknown block type: {html.escape(block_type)} -->'
    try:
        return fn(block)
    except Exception:  # fail-closed backstop: any malformed payload (e.g. `lines: null`, a
        # non-dict nested entry) degrades to a comment — render NEVER crashes the page.
        return f'<!-- block render error: {html.escape(block_type)} -->'


def render_section(section: dict) -> str:
    """Render a section with title and blocks."""
    if not isinstance(section, dict):  # fail-closed: a non-dict section degrades, never crashes
        return ""
    parts = ['<div class="section">']
    if section.get("title"):
        parts.append(f'<h2 class="section-title">{render_text(section["title"])}</h2>')
    for block in (section.get("blocks") or []):  # `or []` — an explicit null blocks is not iterable
        parts.append(render_block(block))
    parts.append('</div>')
    return "\n".join(parts)


def render_executive_summary(items: list, title: str = "") -> str:
    """Render executive summary block. No hardcoded "Resumo Executivo" heading (structure not
    strings): the heading renders ONLY if the producer supplies `title` (in-language)."""
    parts = ['<div class="executive-summary">']
    if title:
        parts.append(f'<h3>{render_text(title)}</h3>')
    parts.append('<ul>')
    for item in items:
        parts.append(f'<li>{render_text(item)}</li>')
    parts.append('</ul></div>')
    return "\n".join(parts)


_METRIC_QUANT_RE = re.compile(r"\d")  # a metric VALUE must carry a digit (42%, 3x, 30ms, 9) — not "pré-CSS"


def _metric_value_is_quantitative(v) -> bool:
    """A metric card's value is real iff it is a number (incl. 0) or a digit-bearing token; a purely
    textual value ("pré-CSS", "célula") is a filler card masquerading as a metric (D-D)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_METRIC_QUANT_RE.search(v))


def quantitative_metric_items(items) -> list:
    """The metric items with a QUANTITATIVE value AND a nonblank label — the only renderable cards.
    The single source of truth for "what is a real metric card", shared by the render seam (below) and
    the substance gate (`tools/blocks.py`), so top-level `content.metrics` and block-level `metrics-grid`
    filter filler identically (D-D)."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not _metric_value_is_quantitative(it.get("value")):
            continue
        label = it.get("label")
        if isinstance(label, (int, float)) and not isinstance(label, bool) or str(label or "").strip():
            out.append(it)
    return out


def _render_metrics_items(items: list) -> str:
    """Render a metrics grid from a list of {value, label} items. Filler cards (non-quantitative value
    or blank label) are dropped at this seam so BOTH top-level `content.metrics` and block-level
    `metrics-grid` are filtered identically (D-D). Returns "" if no real card survives."""
    real = quantitative_metric_items(items)
    if not real:
        return ""
    parts = ['<div class="metrics-grid">']
    for m in real:
        parts.append(
            f'<div class="metric-card">'
            f'<div class="metric-value">{render_text(m.get("value", ""))}</div>'
            f'<div class="metric-label">{render_text(m.get("label", ""))}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def spec_to_html(spec: dict) -> str:
    """Convert a structured-spec dict to an HTML string (the <main> content).

    Spec shape (mirrors the legacy):
        {"executive_summary": [...], "metrics": [{value,label}, ...],
         "sections": [{"title": ..., "blocks": [{"type": ...}, ...]}, ...],
         "additional_sections": [...], "bibliography": [...]}
    Everything is optional. Sections are FREE: any block type may appear in any
    section — the Feynman blocks are palette elements, not mandatory sections.

    PURE w.r.t. its input: the publisher verifies the close proof over `spec` and THEN
    renders, so rendering must never mutate the proof-bound object (a post-render retry
    or audit recomputes a digest that must still match). Deep-copy at the entry detaches
    the whole subtree before any normalization touches it.
    """
    spec = copy.deepcopy(spec)
    parts = []

    if spec.get("executive_summary"):
        parts.append(render_executive_summary(
            spec["executive_summary"], spec.get("executive_summary_title", "")))

    if spec.get("metrics"):
        metrics_html = _render_metrics_items(spec["metrics"])  # filler-filtered; "" if none survive
        if metrics_html:
            parts.append(metrics_html)

    for section in (spec.get("sections") or []):  # `or []` — explicit null is not iterable
        parts.append(render_section(section))

    for section in (spec.get("additional_sections") or []):
        parts.append(render_section(section))

    if spec.get("bibliography"):
        bib_section = {
            "title": "Referencias",
            "blocks": [{
                "type": "bibliography",
                "references": spec["bibliography"],
            }],
        }
        parts.append(render_section(bib_section))

    return "\n\n".join(parts)
