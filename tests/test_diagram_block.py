"""The `diagram` block (and its `chart` sibling) — the visual recipe set's Vega backend
(docs/specs/visual-recipe-set.md). The writer emits the edge's own tiny schema (topology / data +
light config); `visual_recipes` expands it into a CLOSED Vega/Vega-Lite recipe, `vl-convert` renders
it browser-free (pure-pip wheel, no system binary, no root), and the produced SVG is allowlist-
sanitized before inlining.

Because the spec is writer-controlled, the block is a TRUST BOUNDARY: a closed recipe vocabulary
(no raw-Vega passthrough), per-recipe validation that FAILS CLOSED on malformed payloads, and an
allowlist-SANITIZED SVG. The sanitizer + the capability/degradation + the fail-closed paths are
pinned here; the render cases use the installed `vl-convert`.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import render  # noqa: E402

HAS_VL = render.diagram_available()
NODES = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}]
EDGES = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
DAG = {"type": "diagram", "layout": "dag", "nodes": NODES, "edges": EDGES}


class Sanitizer(unittest.TestCase):
    def test_strips_script_events_foreignobject_image_external_href(self):
        hostile = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<script>alert(1)</script>'
            '<a xlink:href="http://evil.example/x"><text onclick="steal()">n</text></a>'
            '<foreignObject><body>x</body></foreignObject>'
            '<image href="http://evil.example/x.png"/>'
            '<path d="M0 0 L1 1"/></svg>'
        )
        out = render._sanitize_svg(hostile)
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("onclick", out.lower())
        self.assertNotIn("foreignobject", out.lower())
        self.assertNotIn("<image", out.lower())
        self.assertNotIn("evil.example", out)   # external href + image src both gone
        self.assertIn("<path", out)             # legitimate drawing kept

    def test_keeps_same_document_fragment_href(self):
        out = render._sanitize_svg('<svg><a xlink:href="#node1"><text>n</text></a></svg>')
        self.assertIn("#node1", out)

    def test_strips_event_handlers_case_insensitively(self):
        out = render._sanitize_svg('<svg><text ONLOAD="x()" OnClick="y()">n</text></svg>')
        self.assertNotIn("ONLOAD", out)
        self.assertNotIn("OnClick", out)

    def test_strips_unquoted_dangerous_attributes(self):
        out = render._sanitize_svg('<svg><text onclick=alert(1)>n</text>'
                                   '<a href=javascript:alert(1)>x</a></svg>')
        self.assertNotIn("onclick", out.lower())
        self.assertNotIn("javascript", out.lower())

    @unittest.skipUnless(HAS_VL, "vl-convert not installed")
    def test_rendered_svg_is_inert(self):
        # The trust boundary: a rendered diagram/chart SVG carries no script/event/foreignObject.
        for block in (DAG, {"type": "chart", "chart": "bar",
                            "data": [{"label": "x", "value": 1}]}):
            out = render.render_block(block)
            self.assertIn("<svg", out)
            self.assertNotIn("<script", out.lower())
            self.assertNotIn("onload", out.lower())
            self.assertNotIn("foreignobject", out.lower())


class MalformedInputFailsClosed(unittest.TestCase):
    def test_non_mapping_payload_degrades_not_crashes(self):
        # a diagram/chart whose payload fields are the wrong shape degrades to a comment, never raises.
        for bad in (
            {"type": "diagram", "layout": "dag", "nodes": 123},
            {"type": "diagram", "layout": "dag", "nodes": []},
            {"type": "diagram", "layout": "nope", "nodes": NODES},
            {"type": "diagram", "layout": "dag", "nodes": NODES, "edges": [{"source": "a"}]},
            {"type": "chart", "chart": "bar", "data": "not a list"},
            {"type": "chart", "chart": "bar", "data": []},
            {"type": "chart", "chart": "nope", "data": [1]},
            {"type": "chart", "chart": "line", "data": [{"x": 1}]},  # missing y
        ):
            out = render.render_block(bad)
            self.assertIn("<!--", out)          # a comment, never an exception
            self.assertNotIn("<svg", out)

    def test_non_string_quote_fails_closed(self):
        bad = {"type": "evidence", "quote_text": {"nested": "x"}, "source_ref": "m", "anchor": "z"}
        ok, reason = render.verify_evidence(bad)
        self.assertFalse(ok)                    # genus violation, not a crash
        self.assertIn("<", render.render_block(bad))  # renders (degraded) without raising


class CapabilityAbsent(unittest.TestCase):
    def test_absent_vl_convert_degrades_to_comment_never_crashes(self):
        # capability gate keyed on vl-convert: absent → a comment, never a crash or raw passthrough.
        with mock.patch.object(render, "_vl_convert", return_value=None):
            out_d = render.render_block(DAG)
            out_c = render.render_block({"type": "chart", "chart": "bar",
                                         "data": [{"label": "x", "value": 1}]})
        for out in (out_d, out_c):
            self.assertIn("<!--", out)
            self.assertIn("unavailable", out.lower())
            self.assertIn("vl-convert", out.lower())

    def test_renderable_false_when_capability_absent(self):
        with mock.patch.object(render, "_vl_convert", return_value=None):
            self.assertFalse(render.diagram_renderable(DAG))
            self.assertFalse(render.chart_renderable(
                {"type": "chart", "chart": "bar", "data": [{"label": "x", "value": 1}]}))

    def test_dag_alias_canonicalizes_to_diagram(self):
        # a block authored as `dag` (alias) must route to the diagram renderer, not unknown-block.
        with mock.patch.object(render, "_vl_convert", return_value=None):
            out = render.render_block({"type": "dag", "layout": "dag", "nodes": NODES})
        self.assertIn("unavailable", out.lower())   # reached render_diagram


class DiagramRender(unittest.TestCase):
    @unittest.skipUnless(HAS_VL, "vl-convert not installed")
    def test_valid_dag_renders_inline_svg(self):
        out = render.render_block(DAG)
        self.assertIn("<svg", out)
        self.assertIn('class="diagram"', out)
        self.assertNotIn("<script", out.lower())

    @unittest.skipUnless(HAS_VL, "vl-convert not installed")
    def test_force_layout_renders(self):
        out = render.render_block({"type": "diagram", "layout": "force",
                                   "nodes": NODES, "edges": EDGES})
        self.assertIn("<svg", out)

    @unittest.skipUnless(HAS_VL, "vl-convert not installed")
    def test_renderable_true_for_valid_false_for_malformed(self):
        self.assertTrue(render.diagram_renderable(DAG))
        self.assertFalse(render.diagram_renderable(
            {"type": "diagram", "layout": "dag", "nodes": []}))
        self.assertFalse(render.diagram_renderable(
            {"type": "diagram", "layout": "nope", "nodes": NODES}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
