"""The one canonical element-vocabulary renderer (Close architecture, S2).

`render.py` is the single source of the block palette ported from the legacy
`yaml_to_html.py` — de-YAML'd, file/config/log deps stripped. It takes a Python
structured-spec dict and returns an HTML string. These pin that the whole palette
is one registry, the Feynman blocks are ordinary (reachable, never mandatory)
elements, the class hooks match the neutralized base.css, and an unknown block
type degrades to an HTML comment rather than raising.
"""
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import render  # noqa: E402


class PaletteRendersEachBlockType(unittest.TestCase):
    """One spec exercising blocks across the palette — Feynman (derivation, gap-table
    with an open gap), structural (table), planning (next-steps-grid) and the escape
    hatch (raw-html) — renders with the base.css class hooks. An unknown block type
    degrades to an HTML comment, never an exception."""

    def test_palette_emits_class_hooks_and_degrades_unknown(self):
        spec = {
            "sections": [
                {
                    "title": "Palette",
                    "blocks": [
                        {"type": "derivation", "title": "From scratch",
                         "text": "derived this", "bullets": ["step one", "step two"]},
                        {"type": "gap-table", "gaps": [
                            {"id": 1, "description": "the unknown thing",
                             "need": "evidence", "status": "open"}]},
                        {"type": "table", "headers": ["A", "B"],
                         "rows": [["1", "2"]]},
                        {"type": "next-steps-grid", "steps": [
                            {"title": "do the thing", "description": "now"}]},
                        {"type": "raw-html", "content": "<aside>verbatim</aside>"},
                        {"type": "totally-made-up-block", "text": "x"},
                    ],
                }
            ]
        }

        html = render.spec_to_html(spec)

        # Feynman blocks are ordinary palette elements, reachable here
        self.assertIn('class="derivation"', html)
        self.assertIn("gap-status-open", html)
        # planning / structural palette
        self.assertIn("next-steps-grid", html)
        self.assertIn("<table>", html)
        # raw-html escape hatch passes through verbatim
        self.assertIn("<aside>verbatim</aside>", html)
        # unknown block type → HTML comment, never raised
        self.assertIn("<!-- unknown block", html)
        self.assertIn("totally-made-up-block", html)


class RawHtmlIsSanitizedButSvgSurvives(unittest.TestCase):
    """#5: the publisher serves rendered pages publicly, so a source-influenced raw-html
    block must not become executable. On render, strip <script>, on*= event-handler attrs,
    javascript:/script-bearing data: URLs, <foreignObject>, <iframe> — while KEEPING the
    operator's visual escape hatch: benign inline SVG (rects/paths/text) survives intact."""

    def test_script_and_handlers_stripped_svg_survives(self):
        spec = {
            "sections": [
                {
                    "title": "Hatch",
                    "blocks": [
                        {"type": "raw-html", "content":
                            '<div onclick="steal()">hi</div>'
                            '<script>evil()</script>'
                            '<svg viewBox="0 0 10 10">'
                            '<rect x="1" y="1" width="8" height="8"/>'
                            '<path d="M0 0 L10 10"/>'
                            '<text x="2" y="5">ok</text>'
                            '</svg>'},
                    ],
                }
            ]
        }

        html = render.spec_to_html(spec)

        # script element and its content are gone
        self.assertNotIn("<script", html)
        self.assertNotIn("evil()", html)
        # the inline event handler is stripped
        self.assertNotIn("onclick", html)
        self.assertNotIn("steal()", html)
        # benign SVG graphics survive intact
        self.assertIn("<svg", html)
        self.assertIn("<rect", html)
        self.assertIn('<path d="M0 0 L10 10"', html)
        self.assertIn("<text", html)
        self.assertIn(">ok</text>", html)


class GeneratedHrefsAreSchemeSanitized(unittest.TestCase):
    """Re-review #high: render_text rewrites [text](url) into <a href="url"> and the
    bibliography emits <a href="url"> from a source-influenced `url` — both bypassed the
    raw-html sanitizer's safe-scheme allowlist. A javascript:/data:/mixed-case/leading-
    control URL must NOT become an executable href in EITHER path; a normal https:// link
    survives as an anchor."""

    UNSAFE = [
        "javascript:alert(1)",
        "JavaScript:alert(1)",  # mixed case
        "data:text/html,<script>alert(1)</script>",
        "\tjavascript:alert(1)",  # leading control/whitespace
    ]

    def test_markdown_link_unsafe_urls_neutralized_https_survives(self):
        for bad in self.UNSAFE:
            spec = {"sections": [{"title": "P", "blocks": [
                {"type": "paragraph", "text": f"see [click]({bad}) now"}]}]}
            html = render.spec_to_html(spec)
            self.assertNotIn('href="javascript:', html.lower(),
                             f"unsafe href leaked for {bad!r}")
            self.assertNotIn("href=\"data:", html.lower(),
                             f"unsafe href leaked for {bad!r}")
            # The link text is still shown (plain text fallback)
            self.assertIn("click", html)

        # A normal https:// link survives as a real anchor
        ok = {"sections": [{"title": "P", "blocks": [
            {"type": "paragraph", "text": "see [click](https://example.com) now"}]}]}
        html = render.spec_to_html(ok)
        self.assertIn('<a href="https://example.com"', html)
        self.assertIn(">click</a>", html)

    def test_bibliography_url_unsafe_neutralized_https_survives(self):
        for bad in self.UNSAFE:
            spec = {"bibliography": [{"text": "ref", "url": bad}]}
            html = render.spec_to_html(spec)
            self.assertNotIn('href="javascript:', html.lower(),
                             f"unsafe href leaked for {bad!r}")
            self.assertNotIn("href=\"data:", html.lower(),
                             f"unsafe href leaked for {bad!r}")

        ok = {"bibliography": [{"text": "ref", "url": "https://example.com"}]}
        html = render.spec_to_html(ok)
        self.assertIn('<a href="https://example.com"', html)


class AttributeValuesCannotBreakOut(unittest.TestCase):
    """Codex round-3 [high]: renderers interpolate spec-controlled values into HTML
    attributes (style, class, badge_class, card_class, td class) WITHOUT escaping, so a
    quote-breaking payload like `color:red" onmouseover="alert(1)` injects an event-handler
    attribute — bypassing the raw-html sanitizer AND the centralized URL checks. Every
    attribute-producing block type must neutralize the quote-break: NO new attribute
    (onmouseover/onerror) escapes the quoted value."""

    # A payload that, interpolated raw, closes the attribute and opens an event handler.
    BREAKOUT = 'red" onmouseover="alert(1)'
    CLASS_BREAKOUT = 'x" onmouseover="alert(1)'

    @staticmethod
    def _real_attrs(markup):
        """The actual attributes a browser would parse — escaped `&quot;` inside a
        value stays part of that value, so a neutralized payload yields NO on*= attr."""
        names = []

        class _P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                names.extend(n.lower() for n, _ in attrs)

            handle_startendtag = handle_starttag

        p = _P()
        p.feed(markup)
        p.close()
        return names

    def _assert_no_handler(self, html, label):
        # A quote-break would make `onmouseover` a REAL parsed attribute; escaping
        # keeps it inert text inside the original attribute's value.
        attrs = self._real_attrs(html)
        leaked = [a for a in attrs if a.startswith("on")]
        self.assertEqual([], leaked, f"{label}: quote-break leaked handler(s) {leaked}")

    def test_paragraph_style_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "paragraph", "style": f"color:{self.BREAKOUT}", "text": "x"}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "paragraph style")

    def test_callout_variant_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "callout", "variant": self.CLASS_BREAKOUT, "text": "x"}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "callout variant")

    def test_card_badge_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "card", "badge": "B", "badge_class": self.CLASS_BREAKOUT}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "card badge_class")

    def test_numbered_card_card_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "numbered-card", "title": "T", "card_class": self.CLASS_BREAKOUT}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "numbered-card card_class")

    def test_numbered_card_badge_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "numbered-card", "title": "T", "badge": "B",
             "badge_class": self.CLASS_BREAKOUT}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "numbered-card badge_class")

    def test_comparison_badge_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "comparison",
             "before": {"title": "L", "badge": "B", "badge_class": self.CLASS_BREAKOUT},
             "after": {"title": "R"}}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "comparison badge_class")

    def test_comparison_table_cell_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "comparison-table", "headers": ["H"],
             "rows": [{"cells": ["c"], "classes": [self.CLASS_BREAKOUT]}]}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "comparison-table cell class")

    def test_comparison_table_score_row_cell_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "comparison-table", "headers": ["H"], "rows": [],
             "score_row": {"cells": ["c"], "classes": [self.CLASS_BREAKOUT]}}]}]}
        self._assert_no_handler(render.spec_to_html(spec),
                                "comparison-table score_row cell class")

    def test_code_block_badge_class_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "code-block", "content": "x", "badge": "B",
             "badge_class": self.CLASS_BREAKOUT}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "code-block badge_class")

    def test_list_style_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "list", "style": f"color:{self.BREAKOUT}", "items": ["a"]}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "list style")

    def test_diff_block_line_type_cannot_break_out(self):
        spec = {"sections": [{"title": "P", "blocks": [
            {"type": "diff-block", "lines": [
                {"type": self.CLASS_BREAKOUT, "text": "x"}]}]}]}
        self._assert_no_handler(render.spec_to_html(spec), "diff-block line type")

    def test_badge_html_variant_cannot_break_out(self):
        # The shared badge sink: variant goes into badge-{variant} class.
        self._assert_no_handler(render.badge_html("B", self.CLASS_BREAKOUT), "badge_html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
