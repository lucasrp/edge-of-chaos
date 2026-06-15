"""Slice 5a — the SHARED doc-rendering surface (`blog/docmd.py`): markdown → HTML through an
allowlist sanitizer / no-scripts boundary.

This module is the single rendering path BOTH Slice 5a (design docs) and Slice 5b (wiki / cluster
pages) go through. Its whole reason to exist is the security boundary: the docs it renders are
edge-authored AND source-derived, so the markdown can carry raw HTML, event handlers, or
`javascript:` URLs. Rendering one must NOT let anything execute same-origin in the authed dashboard
(an injected `<script>` / handler could read state and fire authenticated log-mutating POSTs,
defeating the Slice-1 write gate).

So these tests pin the boundary as a property: whatever the source markdown carries, the rendered
HTML is INERT — no `<script>`, no `on*=` handler, no `javascript:` URL — while the legitimate
markdown (headings, emphasis, code, lists, links) still renders.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "blog"))

import docmd  # noqa: E402


class TestRendersLegitimateMarkdown(unittest.TestCase):
    """The happy path: real design-doc markdown renders to readable HTML."""

    def test_heading_renders_as_h_tag(self):
        out = docmd.render_doc_html("# Glossary\n")
        self.assertIn("<h1>Glossary</h1>", out)

    def test_prose_renders_as_a_paragraph(self):
        out = docmd.render_doc_html("the edge knows the mentee.\n")
        self.assertIn("<p>the edge knows the mentee.</p>", out)

    def test_markdown_link_renders_as_anchor(self):
        out = docmd.render_doc_html("see [ADR-0017](docs/adr/0017-x.md) for the model.\n")
        self.assertIn('<a href="docs/adr/0017-x.md">ADR-0017</a>', out)

    def test_inline_emphasis_and_code_render(self):
        out = docmd.render_doc_html("a **bold** word and `code` span.\n")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<code>code</code>", out)

    def test_bullet_list_renders_as_ul(self):
        out = docmd.render_doc_html("- Mundo\n- Atividade\n- Voz\n")
        self.assertIn("<ul>", out)
        self.assertIn("<li>Mundo</li>", out)
        self.assertIn("<li>Voz</li>", out)
        self.assertIn("</ul>", out)

    def test_blockquote_renders(self):
        out = docmd.render_doc_html("> Language only. Invariants live in CONTRACT.md.\n")
        self.assertIn("<blockquote>", out)
        self.assertIn("Language only.", out)

    def test_fenced_code_block_renders_pre_code_and_is_inert(self):
        # ADRs carry fenced code. Inside a fence, markdown is NOT interpreted and any HTML is escaped
        # — a `<script>` in a code block is shown verbatim, never executed.
        out = docmd.render_doc_html("```\n<script>x()</script>\nplain code\n```\n")
        self.assertIn("<pre><code>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out.lower())


class TestRendersInert(unittest.TestCase):
    """The security boundary: whatever the source carries, the output cannot execute same-origin."""

    def test_raw_script_tag_renders_as_inert_text_not_a_live_tag(self):
        # An edge-authored / source-derived doc carries a raw <script>. It must NOT survive as a
        # live tag in the authed dashboard — escaped to literal text, never executed.
        out = docmd.render_doc_html("intro\n<script>alert(document.cookie)</script>\n")
        self.assertNotIn("<script>", out.lower())
        # ...and it is still PRESENT as escaped text — inert, not silently dropped.
        self.assertIn("&lt;script&gt;", out)

    def test_event_handler_in_raw_html_is_not_a_live_attribute(self):
        # A raw <img> with an onerror handler — the classic no-<script>-needed XSS. The handler must
        # not survive as a live attribute; the whole tag escapes to inert text.
        out = docmd.render_doc_html('<img src=x onerror="fetch(\'/e/x/vote\',{method:\'POST\'})">\n')
        # The tag is not live markup (escaped to &lt;img…), so the onerror cannot bind to an element.
        self.assertNotIn("<img", out.lower())
        # The handler text survives only inside an escaped run — never as a live `onerror="` with a
        # real double-quote opening an attribute value.
        self.assertNotIn('onerror="', out.lower())

    def test_javascript_url_link_is_not_a_live_anchor(self):
        # A markdown link whose href is a javascript: URL — a same-origin code-execution vector. The
        # visible text may remain, but there must be NO live anchor carrying the javascript: href.
        out = docmd.render_doc_html("click [here](javascript:alert(document.cookie)) now.\n")
        self.assertNotIn('href="javascript:', out.lower())
        self.assertNotIn("javascript:alert", out.lower())

    def test_javascript_url_with_obfuscated_scheme_is_not_a_live_anchor(self):
        # Whitespace / case obfuscation inside the scheme must not slip past the allowlist.
        out = docmd.render_doc_html("[x](JaVaScRiPt:alert(1)) and [y](\tjavascript:alert(2))\n")
        self.assertNotIn("javascript:", out.lower())
        self.assertNotIn("<a href=", out.lower())

    def test_entity_obfuscated_scheme_is_rejected(self):
        # An attacker hides the `javascript:` scheme behind HTML entities, betting the allowlist
        # checks only one decode level. The href decodes to a fixpoint before the scheme test, so a
        # numeric/named-entity `javascript:` / `data:` is caught and the link is not live.
        for src in ("[a](java&#115;cript:alert(1))",
                    "[b](javascript&colon;alert(1))",
                    "[c](data:text/html,xx)"):
            out = docmd.render_doc_html(src + "\n")
            self.assertNotIn("<a href=", out.lower(), src)

    def test_quote_in_href_cannot_break_the_attribute(self):
        # A `"` in the href must stay escaped (&quot;) so it cannot close the attribute and inject an
        # event handler — the whole run was html-escaped before the inline pass.
        out = docmd.render_doc_html('[a](http://x" onmouseover="alert(1))\n')
        self.assertNotIn('" onmouseover="', out)

    def test_safe_relative_and_http_links_still_render(self):
        # The allowlist must not over-block legitimate links the docs use.
        out = docmd.render_doc_html(
            "[adr](docs/adr/0017-x.md) [http](https://example.com) [frag](#term)\n")
        self.assertIn('<a href="docs/adr/0017-x.md">adr</a>', out)
        self.assertIn('<a href="https://example.com">http</a>', out)
        self.assertIn('<a href="#term">frag</a>', out)


if __name__ == "__main__":
    unittest.main()
