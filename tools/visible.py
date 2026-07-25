"""Modulo 5 (Publicacao) — the visible-text adapter.

The reader-visible-text machinery of the Close protocol, factored out of tools/close.py
VERBATIM (the codex-hardened HTML/CSS/glyph hide-detection logic). It answers the two
questions the close/genus layer asks of rendered output: "what text does a reader
actually SEE?" (`visible_text`) and "does this prose paint any visible explanation?"
(`is_visible`). Both public functions NEVER raise — they return '' / False on any error.

The private symbols below (the HTMLParser, the CSS allowlist, the glyph predicate) are the
exact bodies moved out of close.py; do NOT rewrite the hardened CSS logic.
"""
import re
import unicodedata
from html.parser import HTMLParser as _HTMLParser

import render


def _attrs_mark_hidden(attrs) -> bool:
    """A start tag's subtree is DROPPED from the reader-visible claim corpus if ANY hide-or-untrusted
    mechanism is present (Codex S3 #5/#6/#7). Centralized so every mechanism lives in one place:
      • the boolean HTML `hidden` attribute (browser-default `display:none`) — any presence, any value;
      • `aria-hidden="true"`;
      • ANY non-empty inline `style`. We cannot prove an author-controlled style keeps text VISIBLE —
        `safe_style` permits `opacity:0` / `font-size:0` / `position:absolute;left:-9999px` /
        `display:none` / `visibility:hidden` / `color:#fff` and unbounded other tricks — so a styled
        element is treated as possibly-hidden and its text does NOT ground a claim (fail-closed). This
        kills the OPEN-ENDED CSS class instead of blocklisting individual declarations. Trusted renderers
        emit `style` only from an author-controlled field, so a grounding claim must live in UNSTYLED
        trusted prose (raw-html is already stripped from the corpus upstream)."""
    a = dict(attrs)
    return ("hidden" in a
            or a.get("aria-hidden") == "true"
            or bool(isinstance(a.get("style"), str) and a["style"].strip()))


def _attrs_render_hidden(attrs) -> bool:
    """Hidden-predicate for the R0-for-values corpus: a subtree is hidden by the boolean `hidden` attr,
    `aria-hidden="true"`, or a style that hides under `_style_hides_text` — the SAME allowlist detector the R0
    storytelling floor uses, so the corpus is provably NO WEAKER than the R0 prose floor (Codex re-gate #10).
    Unlike `_attrs_mark_hidden` (any style → hidden) it credits the renderer's benign text styling
    (font-size/margin/background/border/line-height in _R0_SAFE_PROSE_PROPS), but it STILL fail-closes on any
    non-benign property — so a producer-slipped overflow:hidden / position:absolute;left:-9999px /
    content-visibility:hidden / zoom:0 / novel trick is dropped, exactly as R0 would drop it."""
    a = dict(attrs)
    if "hidden" in a or a.get("aria-hidden") == "true":
        return True
    style = a.get("style")
    return bool(isinstance(style, str) and style.strip() and _style_hides_text(render.safe_style(style)))


# tags that create a VISUAL break — text on either side is NOT visually contiguous, so it must not fuse
# into one token (Codex S3 #7: `1000<br>0` reads as two numbers, not `10000`). `<br>` is the line-break in
# render_text's inline safelist; the rest are block-level. Inline formatting (strong/em/code/…) flows and
# is deliberately NOT here, so `8<strong>5</strong>` stays the contiguous `85` the reader sees.
_BREAK_TAGS = frozenset({
    "br", "p", "div", "li", "tr", "td", "th", "ul", "ol", "table", "thead", "tbody",
    "section", "blockquote", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
})


class _VisibleTextParser(_HTMLParser):
    """Collect only the DISPLAYED text of rendered HTML — text inside a subtree marked hidden
    (the boolean `hidden` attribute, style display:none / visibility:hidden, or aria-hidden=true) is
    dropped (Codex S3 #5). A visual-break tag (`<br>` / block-level) emits a space separator so visible
    text never fuses across a line/block boundary (Codex S3 #7). Tolerant of unbalanced tags.
    convert_charrefs unescapes entities into the collected text."""
    def __init__(self, hidden_fn=_attrs_mark_hidden):
        super().__init__(convert_charrefs=True)
        self._hidden_fn = hidden_fn   # which start tags hide their subtree (conservative vs render-truth)
        self._stack = []   # (tag, contributes_hidden)
        self._hidden = 0
        self._out = []

    def _maybe_break(self, tag):
        if self._hidden == 0 and tag.lower() in _BREAK_TAGS:
            self._out.append(" ")

    def handle_starttag(self, tag, attrs):
        is_hidden = self._hidden_fn(attrs)
        self._stack.append((tag, is_hidden))
        if is_hidden:
            self._hidden += 1
        self._maybe_break(tag)

    def handle_startendtag(self, tag, attrs):  # e.g. `<br/>` — void, no matching end tag
        if not self._hidden_fn(attrs):
            self._maybe_break(tag)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                self._hidden -= sum(1 for _, h in self._stack[i:] if h)
                del self._stack[i:]
                break
        self._maybe_break(tag)

    def handle_data(self, data):
        if self._hidden == 0:
            self._out.append(data)

    def text(self):
        return "".join(self._out)


def _render_visible(html_str, hidden_fn=_attrs_mark_hidden) -> str:
    """Visible text of one rendered HTML fragment. `hidden_fn` decides which subtrees are hidden: the default
    `_attrs_mark_hidden` is CONSERVATIVE (any inline `style` → dropped) for the untrusted-prose grounding
    corpus; pass `_attrs_render_hidden` for TRUSTED renderer output, which credits benign renderer styling and
    drops only EXPLICIT hiding (display:none / visibility:hidden / opacity:0 / offscreen / …). '' on error."""
    parser = _VisibleTextParser(hidden_fn)
    try:
        parser.feed(html_str)
        parser.close()
    except Exception:  # noqa: BLE001 — malformed HTML → fail closed
        return ""
    return parser.text()


# a CSS <number>[unit] value, parsed for its NUMERIC magnitude — handles sign, decimals AND exponent
# notation (0e0 / 1e3) uniformly (Codex S2 #3), so the zero/off-screen tests judge the real value rather
# than chasing literal forms. (render.safe_style strips `+`-signed declarations, but `[+-]?` is harmless.)
_NUM_UNIT = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-z%]*)", re.I)
_ZERO_ALPHA_HEX = re.compile(r"#[0-9a-f]{3}0|#[0-9a-f]{6}00", re.I)         # #RGBA / #RRGGBBAA, alpha 0


def _num_unit(val: str):
    """Parse a single CSS numeric value into (float magnitude, unit) or None — exponent/sign/decimal aware."""
    m = _NUM_UNIT.fullmatch(val.strip())
    if not m:
        return None
    try:
        return float(m.group(1)), m.group(2).lower()
    except ValueError:
        return None


def _is_css_zero(val: str) -> bool:
    """True iff `val` is a CSS numeric value equal to zero (any form: 0 / .0 / 0px / 0% / 0e0 / -0) — the
    magnitude is parsed as a float, so exponent and signed forms are covered; 0.5 / 1e3 are NOT zero."""
    nu = _num_unit(val)
    return nu is not None and nu[0] == 0.0


def _is_transparent_color(val: str) -> bool:
    v = val.strip().lower()
    return v == "transparent" or bool(_ZERO_ALPHA_HEX.fullmatch(v))


# approximate px-per-unit so a negative text-indent is judged by its REAL off-screen distance, not a raw
# integer (Codex S2 #3: -50em ≈ 800px hides, -20px is a legit hanging-indent nudge). Unknown unit → em-scale
# (conservative). Relative units (%/vw/…) are handled separately (a large negative % moves text off its box).
_LEN_PX = {"px": 1.0, "pt": 96 / 72, "pc": 16.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4,
           "em": 16.0, "rem": 16.0, "ex": 8.0, "ch": 8.0, "q": 96 / 25.4 / 4}
_OFFSCREEN_PX = 100.0


def _text_indent_hides(val: str) -> bool:
    """True iff a NEGATIVE text-indent moves the text far enough to be off-screen — the text-replacement
    hide idiom. A small negative px (hanging-indent nudge) stays visible; a large or relative-unit negative
    hides. Magnitude is parsed as a float (sign/decimal/exponent aware) and unit-scaled to real px."""
    nu = _num_unit(val)
    if nu is None or nu[0] >= 0:        # only a negative indent pushes text off-screen
        return False
    mag, unit = -nu[0], nu[1]
    if unit in ("%", "vw", "vh", "vmin", "vmax"):
        return mag >= 50            # a large negative relative indent pushes text off its box
    return mag * _LEN_PX.get(unit or "px", 16.0) >= _OFFSCREEN_PX


# R0 prose visibility is ALLOWLIST-based, the DECISIVE end to the single-declaration-hider arms race
# (Codex S2 #3, operator decision): prose counts as visible only if EVERY sanitized declaration uses a
# known-SAFE text-styling property with a non-hiding value. The hide-capable properties below carry value
# checks; every OTHER property must be in `_R0_SAFE_PROSE_PROPS` or the declaration is treated as
# possibly-hiding (fail-closed) — so an UNKNOWN or future property (content-visibility / zoom / …) can
# never produce a false PASS of the floor. (safe_style already strips paren-bearing declarations like
# transform:scale(0) / clip:rect(…), so those never reach here.) The narrative_depth blind reviewer remains
# the adequacy backstop. Fail-closed is the right direction for R0: a benign-but-exotic style that doesn't
# count just means the author states the explanation in plainer prose — hidden prose never passes.
_R0_SAFE_PROSE_PROPS = frozenset({
    # purely-benign visible text styling (no value can hide the text)
    "background", "background-color", "background-image", "background-position", "background-size",
    "background-repeat", "background-clip",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "border-color", "border-width", "border-style", "border-radius",
    "font-weight", "font-style", "font-family", "font-variant", "font-stretch", "font-feature-settings",
    "text-align", "text-transform", "text-decoration", "text-decoration-color", "text-decoration-line",
    "text-shadow", "line-height", "letter-spacing", "word-spacing", "word-break", "overflow-wrap",
    "white-space", "vertical-align", "direction", "writing-mode", "text-orientation", "tab-size",
    "list-style", "list-style-type", "cursor",
    # hide-CAPABLE but kept-visible-with-a-good-value (their hiding value is checked below)
    "color", "-webkit-text-fill-color", "display", "visibility", "opacity", "font-size", "font", "scale",
    "text-indent",
    # layout offsets that DON'T hide on their own (need position to go off-screen → reviewer backstop)
    "left", "top", "right", "bottom", "width", "min-width", "max-width", "height", "min-height", "max-height",
})
# `display` VALUES that paint their text content (positive allowlist — Codex S2 #3). Any other value
# (none, table-column, table-column-group, …) does not render the text and is treated as hiding.
_VISIBLE_DISPLAY = frozenset({
    "block", "inline", "inline-block", "flow-root", "list-item", "flex", "inline-flex",
    "grid", "inline-grid", "table", "inline-table", "table-cell", "table-caption", "table-row",
    "table-row-group", "table-header-group", "table-footer-group", "contents", "run-in",
})


# painting-CATEGORY characters that nonetheless render NOTHING on their own: default-ignorable letters
# (Hangul fillers + combining grapheme joiner) and the blank-rendering Braille Pattern Blank (a `So`
# symbol). (Variation selectors / zero-width / format chars are category M*/C* and already excluded by
# requiring a base L/N/P/S category; Unicode spaces are Z* and excluded too.)
_DEFAULT_IGNORABLE = frozenset({0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800})


def _has_visible_glyph(s: str) -> bool:
    """True iff `s` contains a glyph that PAINTS — a base letter/number/punctuation/symbol (L/N/P/S).
    Excludes whitespace (Unicode Z*), zero-width/format/control characters (C*) like ​ / ﻿, bare
    combining marks (M*) and default-ignorable variation selectors (Mn), and the default-ignorable
    Hangul-filler letters — so a paragraph made of only those renders no visible explanation (Codex S2 #3)."""
    return any(unicodedata.category(c)[0] in "LNPS" and ord(c) not in _DEFAULT_IGNORABLE for c in s)


def _style_explicitly_hides(safe: str) -> bool:
    """True iff the SANITIZED inline style contains a KNOWN hiding declaration (display:none / table-column;
    visibility:hidden|collapse; opacity/font-size signed-zero; scale zero-axis; `font:` shorthand zero size;
    transparent/zero-alpha color; large-negative text-indent; negative letter/word spacing). The
    value-checked half of `_style_hides_text` — kept separate so the value checks can be reasoned about on
    their own; the unknown-property fail-closed half (which catches overflow / position / content-visibility /
    zoom / any exotic prop) lives in `_style_hides_text`."""
    for decl in safe.split(";"):
        prop, sep, val = decl.partition(":")
        if not sep:
            continue
        prop, val = prop.strip().lower(), val.strip().lower()
        if not prop:
            continue
        if prop == "display" and val not in _VISIBLE_DISPLAY:
            return True   # none / table-column / any non-painting display value
        if prop == "visibility" and val in ("hidden", "collapse"):
            return True
        if prop in ("opacity", "font-size") and _is_css_zero(val):
            return True
        if prop == "scale" and any(_is_css_zero(t) for t in val.split()):
            return True
        if prop == "font":
            # `font` shorthand: drop the `/line-height` component, then a ZERO size token (bare `0` is a
            # valid length, or `0px`/`0%`) hides — family/keyword tokens are never css-zero (Codex S2 #3).
            size_region = re.sub(r"/\s*\S+", " ", val)
            if any(_is_css_zero(t) for t in size_region.split()):
                return True
        if prop in ("color", "-webkit-text-fill-color") and _is_transparent_color(val):
            return True
        if prop == "text-indent" and _text_indent_hides(val):
            return True
        if prop in ("letter-spacing", "word-spacing"):
            # NEGATIVE tracking collapses glyphs onto each other into an unreadable smear (Codex re-gate #9).
            # The renderers never emit these, and legitimate explanation never uses negative tracking, so any
            # negative value is treated as hiding (positive/normal spacing stays visible).
            nu = _num_unit(val)
            if nu is not None and nu[0] < 0:
                return True
    return False


def _style_hides_text(safe: str) -> bool:
    """True iff the SANITIZED inline style hides/collapses the text (ALLOWLIST model): a known hiding
    declaration (`_style_explicitly_hides`), OR a property NOT in `_R0_SAFE_PROSE_PROPS` (unknown/exotic →
    fail-closed — e.g. position offscreen / content-visibility:hidden / zoom:0 / overflow clipping). Returns
    False only when EVERY declaration is a known-safe, non-hiding one. Shared by the R0 storytelling floor and
    the R0-for-values corpus, so neither can be tricked by a style the other would catch."""
    if _style_explicitly_hides(safe):
        return True
    for decl in safe.split(";"):
        prop, sep, _ = decl.partition(":")
        prop = prop.strip().lower()
        if sep and prop and prop not in _R0_SAFE_PROSE_PROPS:
            return True   # unknown/exotic property kept by safe_style → fail-closed as possibly-hiding
    return False


def _r0_prose_visible(block) -> bool:
    """True iff a prose block (paragraph/callout) is reader-VISIBLE explanation: it carries real RENDERED
    body text AND is not hidden by its own inline style. Reads the canonical `text` field the renderer
    actually displays (Codex S2 #3) — NOT `_block_text`, which flattens metadata like `style`, so an empty
    styled block cannot pose as prose. The `style` field is the only hiding vector for a prose block
    (render_text escapes raw HTML, so no nested style/hidden enters via the text)."""
    _bt, cblock = render.canonical_block(block)        # normalize synonyms to the field render reads
    text = cblock.get("text") if isinstance(cblock, dict) else None
    if not (isinstance(text, str) and text.strip()):
        return False
    # the RENDERED body must show a VISIBLE GLYPH: markup-only formatting (text "<br>") or zero-width/
    # format characters (​/﻿) render no readable explanation (Codex S2 #3). render_text emits no
    # style attrs, so `_render_visible` here strips only inline tags / break-separators (block style below).
    if not _has_visible_glyph(_render_visible(render.render_text(text))):
        return False
    # Only a PARAGRAPH applies `style` as a CSS attribute (render_paragraph → safe_style); a callout uses
    # `style` as a VARIANT name (a class), never a hiding CSS attr. Run the hider check against the SAME
    # sanitized style render_paragraph emits, so the predicate exactly matches renderer output (Codex S2 #3).
    if _bt == "paragraph":
        style = block.get("style")
        if isinstance(style, str) and _style_hides_text(render.safe_style(style)):
            return False
    return True


def visible_text(block_or_str, *, trusted=True) -> str:
    """The reader-visible text of a rendered block dict or a prose string. NEVER raises — '' on any error.
    `trusted` selects the hidden-predicate: the renderer's own output credits benign styling
    (`_attrs_render_hidden`); untrusted prose drops any styled subtree (`_attrs_mark_hidden`)."""
    hidden_fn = _attrs_render_hidden if trusted else _attrs_mark_hidden
    try:
        if isinstance(block_or_str, dict):
            html = render.render_block(block_or_str)
        elif isinstance(block_or_str, str):
            html = render.render_text(block_or_str)
        else:
            return ""
        return _render_visible(html, hidden_fn)
    except Exception:  # noqa: BLE001 — malformed block/string or renderer error → fail closed
        return ""


def is_visible(block_or_str) -> bool:
    """True iff the prose block dict / string carries reader-visible painted explanation. NEVER raises —
    False on any error."""
    try:
        if isinstance(block_or_str, dict):
            return _r0_prose_visible(block_or_str)
        if isinstance(block_or_str, str):
            return _has_visible_glyph(_render_visible(render.render_text(block_or_str)))
        return False
    except Exception:  # noqa: BLE001 — malformed input or renderer error → fail closed
        return False
