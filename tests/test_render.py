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


if __name__ == "__main__":
    unittest.main(verbosity=2)
