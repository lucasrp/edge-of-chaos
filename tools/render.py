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
import html
import re
from html.parser import HTMLParser


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
    for row in b["rows"]:
        cells = row.get("cells", [])
        classes = row.get("classes", [])
        parts.append('<tr>')
        for j, cell in enumerate(cells):
            cls = classes[j] if j < len(classes) else ""
            td_cls = f' class="{attr_value(cls)}"' if cls else ""
            parts.append(f'<td{td_cls}>{render_text(str(cell))}</td>')
        parts.append('</tr>')
    if b.get("score_row"):
        sr = b["score_row"]
        cells = sr.get("cells", [])
        classes = sr.get("classes", [])
        parts.append('<tr class="score-row">')
        for j, cell in enumerate(cells):
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
    steps = list(b.get("steps", []) or b.get("items", []))
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
        # Normalize: string → dict
        if isinstance(step, str):
            step = {"title": step}
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
        line_type = line.get("type", "context")
        css_class = f"diff-{attr_value(line_type)}"
        prefix = {"insert": "+ ", "delete": "- ", "context": "  "}.get(line_type, "  ")
        parts.append(
            f'<div class="{css_class}">{prefix}{render_pre(line["text"])}</div>'
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
    """Block for 'what I derived from scratch' — purple-bordered card."""
    parts = ['<div class="derivation">']
    parts.append('<div class="derivation-header">')
    parts.append('<span class="derivation-icon">D</span>')
    title = b.get("title", "Derivacao")
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
    # Fallback: if spec uses headers/rows (table format), delegate to table renderer
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
    parts.append('<th>#</th><th>Gap</th><th>O que preciso saber</th><th>Status</th>')
    parts.append('</tr></thead><tbody>')
    for row in b.get("gaps", []):
        num = row.get("id", "")
        desc = row.get("description", "")
        need = row.get("need", "")
        status = row.get("status", "aberto")
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

BLOCK_SCHEMAS = {
    "paragraph": {
        "required": ["text"],
        "optional": ["style"],
        "synonyms": {"content": "text", "description": "text", "body": "text"},
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
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def render_block(block: dict) -> str:
    """Dispatch a single block to its renderer.

    Unknown block type → an HTML comment, never an exception. Field synonyms are
    normalized to the canonical field the renderer expects.

    PURE w.r.t. its input: alias-type rewrites and synonym normalization build a NEW
    block dict (a shallow copy is enough — only top-level keys are reassigned/popped),
    so the caller's proof-bound block is never mutated.
    """
    block_type = block.get("type", "paragraph")
    if block_type in _BLOCK_TYPE_ALIASES:
        block_type = _BLOCK_TYPE_ALIASES[block_type]
        block = {**block, "type": block_type}
    fn = RENDERERS.get(block_type)
    if fn is None:
        return f'<!-- unknown block type: {html.escape(block_type)} -->'

    # Apply field synonyms (e.g. content → text for paragraph)
    schema = BLOCK_SCHEMAS.get(block_type)
    if schema:
        synonyms = schema.get("synonyms", {})
        if any(syn in block and canonical not in block
               for syn, canonical in synonyms.items()):
            block = dict(block)
            for syn, canonical in synonyms.items():
                if syn in block and canonical not in block:
                    block[canonical] = block.pop(syn)

    return fn(block)


def render_section(section: dict) -> str:
    """Render a section with title and blocks."""
    parts = ['<div class="section">']
    if section.get("title"):
        parts.append(f'<h2 class="section-title">{render_text(section["title"])}</h2>')
    for block in section.get("blocks", []):
        parts.append(render_block(block))
    parts.append('</div>')
    return "\n".join(parts)


def render_executive_summary(items: list) -> str:
    """Render executive summary block."""
    parts = [
        '<div class="executive-summary">',
        '<h3>Resumo Executivo</h3>',
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
        parts.append(render_executive_summary(spec["executive_summary"]))

    if spec.get("metrics"):
        parts.append(_render_metrics_items(spec["metrics"]))

    for section in spec.get("sections", []):
        parts.append(render_section(section))

    for section in spec.get("additional_sections", []):
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
