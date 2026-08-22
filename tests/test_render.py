"""The one canonical element-vocabulary renderer (Close architecture, S2).

`render.py` is the single source of the block palette ported from the legacy
`yaml_to_html.py` — de-YAML'd, file/config/log deps stripped. It takes a Python
structured-spec dict and returns an HTML string. These pin that the whole palette
is one registry, the Feynman blocks are ordinary (reachable, never mandatory)
elements, the class hooks match the neutralized base.css, and an unknown block
type degrades to an HTML comment rather than raising.
"""
import copy
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


class RenderingDoesNotMutateInput(unittest.TestCase):
    """Codex round-5 [high]: the publisher verifies the close proof over `spec`, THEN
    renders. If rendering mutates that proof-bound object (rewriting alias block types
    `type:"text"` -> paragraph, popping synonym fields in-place), a post-render retry or
    audit recomputes a digest that no longer matches the accepted proof. Rendering MUST be
    pure with respect to its input — the spec, its sections, and every block dict must be
    byte-for-byte unchanged after `spec_to_html`."""

    def test_alias_and_synonym_spec_is_not_mutated(self):
        spec = {
            "sections": [
                {
                    "title": "Sec",
                    "blocks": [
                        # alias block type: text -> paragraph; synonym field: content -> text
                        {"type": "text", "content": "x"},
                        # alias + structural-transform + synonym (comparison left/right)
                        {"type": "compare",
                         "left_title": "L", "left_items": ["a"],
                         "right_title": "R", "right_items": ["b"]},
                        # next-steps now/next/later grouping mutates item dicts in place
                        {"type": "next-steps-grid",
                         "now": [{"title": "do it"}]},
                    ],
                }
            ]
        }
        snapshot = copy.deepcopy(spec)

        render.spec_to_html(spec)

        self.assertEqual(spec, snapshot,
                         "rendering mutated the proof-bound input spec")

    def test_additional_sections_and_executive_summary_not_mutated(self):
        spec = {
            "executive_summary": ["point one", "point two"],
            "metrics": [{"value": "9", "label": "score"}],
            "additional_sections": [
                {
                    "title": "Extra",
                    "blocks": [
                        {"type": "p", "body": "aliased paragraph with synonym body"},
                        {"type": "code", "code": "print(1)", "title": "snippet"},
                    ],
                }
            ],
            "bibliography": [{"text": "ref", "url": "https://example.com"}],
        }
        snapshot = copy.deepcopy(spec)

        render.spec_to_html(spec)

        self.assertEqual(spec, snapshot,
                         "rendering mutated additional_sections / executive_summary spec")


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


class InlineTagSafelistRendersNotEscapes(unittest.TestCase):
    """A producer spec may emit raw inline formatting tags (<b>, <code>, …); render_text
    must render those, escape everything else, and never pass an unsafe tag through."""

    def test_safelisted_tags_render(self):
        for tag in ("b", "i", "strong", "em", "code", "u", "sub", "sup", "mark", "small"):
            out = render.render_text(f"x <{tag}>y</{tag}> z")
            self.assertIn(f"<{tag}>y</{tag}>", out, tag)
        self.assertIn("a<br>b", render.render_text("a<br>b"))

    def test_non_safelisted_angle_brackets_stay_escaped(self):
        # the exact bug: <slug> placeholders and the like must NOT be eaten as tags
        out = render.render_text("the <slug>.html file and a <div> block")
        self.assertIn("&lt;slug&gt;", out)
        self.assertIn("&lt;div&gt;", out)
        self.assertNotIn("<slug>", out)

    def test_unsafe_tags_never_pass(self):
        # only attribute-free safelist tags pass; anything with attributes stays escaped,
        # so no ACTIVE (unescaped) tag carrying a handler/script can reach the page.
        for bad in ("<script>alert(1)</script>", "<img src=x onerror=1>", "<b onclick=1>x</b>"):
            low = render.render_text(bad).lower()
            self.assertNotIn("<script", low)
            self.assertNotIn("<img", low)
            self.assertNotIn("<b onclick", low)

    def test_markdown_still_works_alongside(self):
        out = render.render_text("**bold** and `code` and <i>raw</i>")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn("<i>raw</i>", out)


class MarkdownMermaidKatexTest(unittest.TestCase):
    SAMPLE = (
        "# Titulo\n"
        "\n"
        "Paragrafo com \\(W_q\\) inline.\n"
        "\n"
        "```mermaid\n"
        "graph TD\n"
        "  A --> B\n"
        "```\n"
        "\n"
        "\\[\n"
        "S(a,b)=\\theta f(A\\cap B)\n"
        "\\]\n"
        "\n"
        "depois.\n"
    )

    def _page(self):
        return render.render_markdown_page(self.SAMPLE, "Titulo")

    def test_mermaid_fence_is_one_pre_not_split_paragraphs(self):
        page = self._page()
        self.assertEqual(page.count("<pre class=\"mermaid\">"), 1)
        self.assertIn("graph TD", page)
        self.assertIn("A --&gt; B", page)
        self.assertNotIn("<p>" + "```" + "mermaid</p>", page)
        self.assertNotIn("<p>graph TD</p>", page)
        start = page.index("<pre class=\"mermaid\">")
        end = page.index("</pre>", start)
        block = page[start:end]
        self.assertIn("graph TD", block)
        self.assertIn("A --&gt; B", block)

    def test_display_math_is_one_block(self):
        page = self._page()
        self.assertEqual(page.count("<div class=\"math-display\">"), 1)
        self.assertNotIn("<p>" + chr(92) + "[</p>", page)
        self.assertNotIn("<p>" + chr(92) + "]</p>", page)
        start = page.index("<div class=\"math-display\">")
        end = page.index("</div>", start)
        block = page[start:end]
        self.assertIn(chr(92) + "[", block)
        self.assertIn("S(a,b)=" + chr(92) + "theta f(A" + chr(92) + "cap B)", block)
        self.assertIn(chr(92) + "]", block)

    def test_inline_math_stays_in_paragraph(self):
        page = self._page()
        self.assertIn("<p>Paragrafo com " + chr(92) + "(W_q" + chr(92) + ") inline.</p>", page)

    def test_head_loads_mermaid_katex_and_auto_render(self):
        head = self._page().split("</head>", 1)[0]
        self.assertIn("mermaid@", head)
        self.assertIn("katex@", head)
        self.assertIn("auto-render", head)
        self.assertIn("renderMathInElement", head)
        self.assertIn("mermaid.initialize", head)

    def test_single_line_display_math(self):
        md = "# T" + chr(10)*2 + chr(92) + "[S=1" + chr(92) + "]" + chr(10)
        page = render.render_markdown_page(md, "T")
        self.assertEqual(page.count("<div class=\"math-display\">"), 1)
        self.assertIn(chr(92) + "[S=1" + chr(92) + "]", page)
        self.assertNotIn("<p>" + chr(92) + "[S=1" + chr(92) + "]</p>", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
