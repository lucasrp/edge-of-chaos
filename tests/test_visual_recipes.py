"""The visual recipe set — the edge's closed Vega vocabulary (docs/specs/visual-recipe-set.md).

Pins the recipe builders end-to-end: every chart recipe expands to valid Vega-Lite that vl-convert
renders to `<svg`; every diagram recipe expands to valid Vega → `<svg`; the `dag` layout is
rank-correct on a multi-parent DAG and reduces crossings; malformed payloads FAIL CLOSED (a clear
error, never a crash and never a blank chart); a `v=1` payload still renders a faithful chart
(semantic-stability, not byte-identity); and the sanitizer strips hostile content from the rendered
SVG (the trust boundary).
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import visual_recipes as vr  # noqa: E402
import render  # noqa: E402

HAS_VL = render.diagram_available()


def _render_chart(payload):
    spec, err = vr.build_chart(payload)
    assert err is None, err
    import vl_convert
    return vl_convert.vegalite_to_svg(json.dumps(spec)), spec


def _render_diagram(payload):
    spec, err = vr.build_diagram(payload)
    assert err is None, err
    import vl_convert
    return vl_convert.vega_to_svg(json.dumps(spec)), spec


# ===========================================================================
# Chart recipes — each builds valid Vega-Lite that vl-convert renders to <svg
# ===========================================================================

@unittest.skipUnless(HAS_VL, "vl-convert not installed")
class ChartRecipesRender(unittest.TestCase):
    def test_line(self):
        svg, spec = _render_chart({"chart": "line", "title": "Trend",
                                   "data": [{"x": 1, "y": 2}, {"x": 2, "y": 5}, {"x": 3, "y": 3}]})
        self.assertTrue(svg.lstrip().startswith("<svg"))
        self.assertEqual(spec["mark"]["type"], "line")          # the right mark for the content shape

    def test_line_multi_series(self):
        svg, spec = _render_chart({"chart": "line", "data": [
            {"x": 1, "y": 2, "series": "a"}, {"x": 2, "y": 4, "series": "a"},
            {"x": 1, "y": 1, "series": "b"}, {"x": 2, "y": 3, "series": "b"}]})
        self.assertIn("<svg", svg)
        self.assertIn("color", spec["encoding"])                # series → a color split

    def test_sparkline(self):
        svg, spec = _render_chart({"chart": "sparkline", "data": [1, 3, 2, 5, 4]})
        self.assertIn("<svg", svg)
        self.assertEqual(spec["mark"]["type"], "line")

    def test_bar(self):
        svg, spec = _render_chart({"chart": "bar",
                                   "data": [{"label": "a", "value": 3}, {"label": "b", "value": 7}]})
        self.assertIn("<svg", svg)
        self.assertEqual(spec["mark"], "bar")

    def test_bar_horizontal(self):
        svg, spec = _render_chart({"chart": "bar", "horizontal": True,
                                   "data": [{"label": "a", "value": 3}, {"label": "b", "value": 7}]})
        self.assertIn("<svg", svg)
        self.assertEqual(spec["encoding"]["y"]["field"], "label")  # category on y when horizontal

    def test_scatter(self):
        svg, spec = _render_chart({"chart": "scatter", "x_label": "X", "y_label": "Y",
                                   "data": [{"x": 1, "y": 2}, {"x": 3, "y": 1}, {"x": 2, "y": 4}]})
        self.assertIn("<svg", svg)
        self.assertEqual(spec["mark"], "point")

    def test_slopegraph(self):
        svg, spec = _render_chart({"chart": "slopegraph", "data": [
            {"item": "x", "before": 1, "after": 4}, {"item": "y", "before": 3, "after": 2}]})
        self.assertIn("<svg", svg)
        self.assertEqual(spec["transform"][0]["fold"], ["before", "after"])  # Tufte fold

    def test_facet_modifier_small_multiples(self):
        spec, err = vr.build_chart({"chart": "bar", "facet": "group", "data": [
            {"label": "a", "value": 1, "group": "g1"}, {"label": "b", "value": 2, "group": "g1"},
            {"label": "a", "value": 3, "group": "g2"}, {"label": "b", "value": 4, "group": "g2"}]})
        self.assertIsNone(err)
        self.assertIn("facet", spec)             # composed into Tufte small multiples
        import vl_convert
        self.assertIn("<svg", vl_convert.vegalite_to_svg(json.dumps(spec)))


# ===========================================================================
# Diagram recipes — each builds valid Vega that vl-convert renders to <svg
# ===========================================================================

_NODES = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"},
          {"id": "c", "label": "C"}, {"id": "d", "label": "D"}]
_EDGES = [{"source": "a", "target": "b", "label": "step"}, {"source": "a", "target": "c"},
          {"source": "b", "target": "d"}, {"source": "c", "target": "d"}]


@unittest.skipUnless(HAS_VL, "vl-convert not installed")
class DiagramRecipesRender(unittest.TestCase):
    def test_dag(self):
        svg, spec = _render_diagram({"layout": "dag", "nodes": _NODES, "edges": _EDGES,
                                     "title": "Flow"})
        self.assertTrue(svg.lstrip().startswith("<svg"))
        self.assertEqual(spec["$schema"], "https://vega.github.io/schema/vega/v5.json")

    def test_dag_edge_label_renders(self):
        svg, _ = _render_diagram({"layout": "dag", "nodes": _NODES, "edges": _EDGES})
        self.assertIn("step", svg)                  # the edge label is drawn

    def test_force(self):
        svg, _ = _render_diagram({"layout": "force", "nodes": _NODES,
                                  "edges": _EDGES + [{"source": "d", "target": "a"}]})  # a cycle
        self.assertIn("<svg", svg)

    def test_dag_uses_no_vega_layout_transform(self):
        # the dag recipe computes its layout in pure Python; the spec must carry NO Vega transform.
        _, spec = _render_diagram({"layout": "dag", "nodes": _NODES, "edges": _EDGES})
        for d in spec["data"]:
            self.assertNotIn("transform", d)
        for m in spec["marks"]:
            self.assertNotIn("transform", m)


# ===========================================================================
# DAG layout correctness — rank, multi-parent, crossing count (regression fixtures)
# ===========================================================================

class DagLayout(unittest.TestCase):
    def test_longest_path_rank(self):
        # a -> b -> d AND a -> c -> d: d's rank is max(pred)+1 = 2 (longest path), not 1.
        lay = vr.dag_layout(_NODES, _EDGES)
        self.assertEqual(lay["rank"]["a"], 0)        # root
        self.assertEqual(lay["rank"]["b"], 1)
        self.assertEqual(lay["rank"]["c"], 1)
        self.assertEqual(lay["rank"]["d"], 2)        # longest path, not first-edge

    def test_multi_parent_node_ranks_below_all_parents(self):
        # the pass-1 gap: a step can depend on SEVERAL predecessors. f depends on b(1), c(1), e(2).
        nodes = [{"id": x} for x in "abcdef"]
        edges = [{"source": "a", "target": "b"}, {"source": "a", "target": "c"},
                 {"source": "c", "target": "e"}, {"source": "b", "target": "f"},
                 {"source": "c", "target": "f"}, {"source": "e", "target": "f"}]
        lay = vr.dag_layout(nodes, edges)
        self.assertEqual(lay["rank"]["e"], 2)
        self.assertEqual(lay["rank"]["f"], 3)        # below ALL parents (b=1, c=1, e=2 → 3)

    def test_cycle_does_not_hang_and_ranks(self):
        # a cycle a<->b: a back-edge is dropped so ranking terminates (never a hang).
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"},
                 {"source": "c", "target": "a"}]  # back-edge
        lay = vr.dag_layout(nodes, edges)
        self.assertEqual(lay["rank"]["a"], 0)
        self.assertLessEqual(len(lay["edges"]), len(edges))  # at least one back-edge dropped

    def test_barycenter_reduces_or_holds_crossings(self):
        # the barycenter ordering pass must never INCREASE crossings vs first-appearance order.
        nodes = [{"id": x} for x in "abcdefgh"]
        edges = [{"source": "a", "target": "e"}, {"source": "a", "target": "f"},
                 {"source": "b", "target": "e"}, {"source": "b", "target": "g"},
                 {"source": "c", "target": "f"}, {"source": "c", "target": "h"},
                 {"source": "d", "target": "g"}, {"source": "d", "target": "h"}]
        with_bary = vr.count_crossings(nodes, edges, barycenter=True)
        without = vr.count_crossings(nodes, edges, barycenter=False)
        self.assertLessEqual(with_bary, without)

    def test_crossing_count_diamond_is_planar(self):
        # the 4-node diamond is planar — the layout achieves 0 crossings.
        self.assertEqual(vr.count_crossings(_NODES, _EDGES), 0)

    def test_width_height_from_layout(self):
        lay = vr.dag_layout(_NODES, _EDGES)
        self.assertGreater(lay["width"], 0)
        self.assertGreater(lay["height"], 0)


# ===========================================================================
# Fail-closed — malformed payloads return a clear error, never a crash, never a blank chart
# ===========================================================================

class FailClosed(unittest.TestCase):
    def test_charts_fail_closed(self):
        cases = [
            {"chart": "line", "data": []},                       # empty data
            {"chart": "line", "data": "nope"},                   # non-list
            {"chart": "line", "data": [{"x": 1}]},               # missing y
            {"chart": "line", "data": [{"x": 1, "y": "two"}]},   # non-numeric y
            {"chart": "sparkline", "data": [1, "two", 3]},       # non-numeric
            {"chart": "bar", "data": [{"label": "a"}]},          # missing value
            {"chart": "bar", "data": [{"label": "a", "value": "x"}]},  # non-numeric value
            {"chart": "scatter", "data": [{"x": 1}]},            # missing y
            {"chart": "slopegraph", "data": [{"item": "x", "before": 1}]},  # missing after
            {"chart": "unknown-recipe", "data": [1]},            # not in the closed set
        ]
        for p in cases:
            spec, err = vr.build_chart(p)
            self.assertIsNone(spec, p)
            self.assertTrue(err, p)               # a clear human reason, never a crash

    def test_diagrams_fail_closed(self):
        cases = [
            {"layout": "dag", "nodes": []},                      # empty topology
            {"layout": "dag", "nodes": "nope"},                  # non-list nodes
            {"layout": "dag", "nodes": [{"label": "x"}]},        # node missing id
            {"layout": "dag", "nodes": [{"id": "a"}, {"id": "a"}]},  # duplicate id
            {"layout": "dag", "nodes": [{"id": "a"}], "edges": [{"source": "a"}]},  # edge missing target
            {"layout": "dag", "nodes": [{"id": "a"}], "edges": "nope"},  # non-list edges
            {"layout": "unknown-layout", "nodes": [{"id": "a"}]},  # not in the closed set
        ]
        for p in cases:
            spec, err = vr.build_diagram(p)
            self.assertIsNone(spec, p)
            self.assertTrue(err, p)

    def test_facet_missing_field_fails_closed(self):
        spec, err = vr.build_chart({"chart": "bar", "facet": "group",
                                    "data": [{"label": "a", "value": 1}]})  # no `group` on the row
        self.assertIsNone(spec)
        self.assertTrue(err)


# ===========================================================================
# Versioning — a v=1 payload still renders a faithful chart (semantic, not byte, stability)
# ===========================================================================

@unittest.skipUnless(HAS_VL, "vl-convert not installed")
class VersionStability(unittest.TestCase):
    def test_v1_payload_renders_faithfully(self):
        # a corpus authored at v=1 must still render to a valid, faithful chart (right marks, right
        # data) — semantic stability. `v` is metadata; it never blocks rendering of its own version.
        corpus = [
            {"type": "chart", "chart": "bar", "v": 1,
             "data": [{"label": "a", "value": 10}, {"label": "b", "value": 20}]},
            {"type": "chart", "chart": "line", "v": 1,
             "data": [{"x": 1, "y": 5}, {"x": 2, "y": 8}]},
            {"type": "diagram", "layout": "dag", "v": 1,
             "nodes": _NODES, "edges": _EDGES},
        ]
        for block in corpus:
            out = render.render_block(block)
            self.assertIn("<svg", out)                       # renders under its own v
            self.assertNotIn("<!--", out)                    # not a fail-closed comment
        # the recipe module declares the version it ships, and a provenance stamp is available.
        self.assertEqual(vr.RECIPE_VERSION, 1)
        self.assertIn("recipes", vr.PROVENANCE)

    def test_missing_v_defaults_to_renderable(self):
        # a block with no `v` is treated as v=1 (the default) — it still renders.
        out = render.render_block({"type": "chart", "chart": "bar",
                                   "data": [{"label": "a", "value": 1}]})
        self.assertIn("<svg", out)


# ===========================================================================
# Sanitizer trust boundary — hostile content stripped from the RENDERED SVG
# ===========================================================================

@unittest.skipUnless(HAS_VL, "vl-convert not installed")
class SanitizerOnRenderedSvg(unittest.TestCase):
    def test_hostile_label_text_does_not_inject_script(self):
        # a writer-controlled node label carrying markup must not produce a live script/event in the
        # inlined SVG — vl-convert escapes text, and the sanitizer is the final trust boundary.
        hostile = '<script>alert(1)</script>'
        out = render.render_block({"type": "diagram", "layout": "dag",
                                   "nodes": [{"id": "a", "label": hostile}, {"id": "b"}],
                                   "edges": [{"source": "a", "target": "b"}]})
        self.assertIn("<svg", out)
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("onerror", out.lower())

    def test_chart_title_with_markup_is_inert(self):
        out = render.render_block({"type": "chart", "chart": "bar",
                                   "title": '<img src=x onerror=alert(1)>',
                                   "data": [{"label": "a", "value": 1}]})
        self.assertIn("<svg", out)
        self.assertNotIn("onerror", out.lower())
        self.assertNotIn("<image", out.lower())


class FailClosedAndSynonyms(unittest.TestCase):
    def test_non_hashable_edge_endpoint_fails_closed(self):
        # a list/dict source/target must be a validation error, not a TypeError crash downstream.
        for bad_ep in ([("a",)], {"x": 1}, ["a"]):
            blk = {"type": "diagram", "layout": "dag",
                   "nodes": [{"id": "a"}, {"id": "b"}],
                   "edges": [{"source": bad_ep, "target": "b"}]}
            _spec, err = vr.build_diagram(blk)
            self.assertIsNotNone(err, bad_ep)
            self.assertTrue(render.render_block(blk).strip().startswith("<!--"))  # comment, not crash

    def test_chart_field_synonyms_build_and_render(self):
        # `recipe`/`rows` are documented chart synonyms — builder + gates must honor them.
        blk = {"type": "chart", "recipe": "bar", "rows": [{"label": "x", "value": 1}]}
        _spec, err = vr.build_chart(blk)
        self.assertIsNone(err)
        if HAS_VL:
            self.assertTrue(render.chart_renderable(blk))

    def test_diagram_field_synonyms_build(self):
        # `recipe`/`links` are documented diagram synonyms.
        blk = {"type": "diagram", "recipe": "dag", "nodes": [{"id": "a"}, {"id": "b"}],
               "links": [{"source": "a", "target": "b"}]}
        _spec, err = vr.build_diagram(blk)
        self.assertIsNone(err)

    def test_edge_to_undeclared_node_fails_closed(self):
        # a typo'd endpoint must be a validation error, not a silently-dropped edge.
        blk = {"type": "diagram", "layout": "dag", "nodes": [{"id": "a"}, {"id": "b"}],
               "edges": [{"source": "a", "target": "TYPO"}]}
        _spec, err = vr.build_diagram(blk)
        self.assertIsNotNone(err)
        self.assertIn("not a declared node", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
