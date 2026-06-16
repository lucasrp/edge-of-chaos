"""Slice 2: (D-D) item-level metrics filter — a MIXED grid must shed its filler cards, not just pass a
block-level boolean; (D-F) chart recipes must default to LANDSCAPE sizing, including faceted charts
where the wrapper drops top-level width/height."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import blocks  # noqa: E402
import render  # noqa: E402
import visual_recipes  # noqa: E402


class MetricsItemFilter(unittest.TestCase):
    def test_mixed_grid_sheds_filler(self):
        b = {"type": "metrics-grid", "items": [
            {"value": "42%", "label": "win rate"},
            {"value": "pré-CSS", "label": "posição"},   # filler — non-quantitative value
            {"value": "célula", "label": "unidade"},     # filler
            {"value": "3x", "label": "speedup"}]}
        out = blocks.normalize_block(b)
        self.assertIsNotNone(out)
        vals = [it["value"] for it in out["items"]]
        self.assertEqual(vals, ["42%", "3x"])  # only quantitative survive, order preserved

    def test_all_filler_grid_dropped(self):
        b = {"type": "metrics-grid", "items": [
            {"value": "pré-CSS", "label": "x"}, {"value": "célula", "label": "y"}]}
        self.assertIsNone(blocks.normalize_block(b))

    def test_top_level_metrics_also_shed_filler(self):
        # codex P2: top-level content.metrics is rendered directly (not via normalize_block); the SAME
        # item filter must apply at the render seam so filler cards never leak on that path either.
        spec = {"metrics": [{"value": "42%", "label": "win rate"},
                            {"value": "pré-CSS", "label": "posição"}],  # filler
                "sections": []}
        h = render.spec_to_html(spec)
        self.assertIn("42%", h)
        self.assertNotIn("pré-CSS", h)

    def test_top_level_all_filler_metrics_render_nothing(self):
        spec = {"metrics": [{"value": "pré-CSS", "label": "x"}], "sections": []}
        h = render.spec_to_html(spec)
        self.assertNotIn("metrics-grid", h)  # no empty grid div leaks

    def test_all_quantitative_kept(self):
        b = {"type": "metrics-grid", "items": [
            {"value": "42%", "label": "a"}, {"value": 0, "label": "errors"}, {"value": "30ms", "label": "p50"}]}
        out = blocks.normalize_block(b)
        self.assertEqual(len(out["items"]), 3)


class BarAxisLabels(unittest.TestCase):
    def test_bar_honors_in_language_axis_titles(self):
        # the vision-gate caught this: a bar chart must use the producer's x_label/y_label, not leak the
        # raw field names 'label'/'value' (English-ish chrome in a non-English report).
        spec, err = visual_recipes.build_chart({"type": "chart", "chart": "bar",
            "x_label": "fatia", "y_label": "defeitos",
            "data": [{"label": "fatia 1", "value": 3}, {"label": "fatia 3", "value": 7}]})
        self.assertIsNone(err, err)
        enc = spec.get("encoding") or spec.get("spec", {}).get("encoding")
        self.assertEqual(enc["x"]["axis"]["title"], "fatia")
        self.assertEqual(enc["y"]["axis"]["title"], "defeitos")

    def test_horizontal_bar_axis_titles_stay_with_their_axes(self):
        # codex P2: x_label must title the x axis and y_label the y axis even when horizontal swaps
        # the category/value encodings.
        spec, err = visual_recipes.build_chart({"type": "chart", "chart": "bar", "horizontal": True,
            "x_label": "quantidade", "y_label": "fatia",
            "data": [{"label": "fatia 1", "value": 3}, {"label": "fatia 3", "value": 7}]})
        self.assertIsNone(err, err)
        enc = spec.get("encoding") or spec.get("spec", {}).get("encoding")
        self.assertEqual(enc["x"]["axis"]["title"], "quantidade")  # x axis = value (horizontal)
        self.assertEqual(enc["x"]["field"], "value")
        self.assertEqual(enc["y"]["axis"]["title"], "fatia")       # y axis = category
        self.assertEqual(enc["y"]["field"], "label")


class ChartLandscapeSizing(unittest.TestCase):
    def _spec(self, payload):
        spec, err = visual_recipes.build_chart(payload)
        self.assertIsNone(err, f"build error: {err}")
        return spec

    def test_each_recipe_is_landscape(self):
        cases = [
            {"chart": "bar", "data": [{"label": "a", "value": 1}, {"label": "b", "value": 2}]},
            {"chart": "line", "data": [{"x": 1, "y": 2}, {"x": 2, "y": 3}, {"x": 3, "y": 1}]},
            {"chart": "scatter", "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]},
            {"chart": "slopegraph", "data": [{"item": "a", "before": 1, "after": 3},
                                             {"item": "b", "before": 2, "after": 1}]},
        ]
        for c in cases:
            with self.subTest(chart=c["chart"]):
                spec = self._spec({"type": "chart", **c})
                self.assertIn("width", spec)
                self.assertGreaterEqual(spec["width"], spec.get("height", 0),
                                        f"{c['chart']} is not landscape")

    def test_faceted_chart_inner_is_landscape(self):
        spec = self._spec({"type": "chart", "chart": "bar", "facet": "grp", "data": [
            {"label": "a", "value": 1, "grp": "g1"}, {"label": "b", "value": 2, "grp": "g2"}]})
        self.assertIn("spec", spec, "expected a faceted spec")
        inner = spec["spec"]
        self.assertIn("width", inner)
        self.assertGreaterEqual(inner["width"], inner.get("height", 0),
                                "faceted inner cell is not landscape")


if __name__ == "__main__":
    unittest.main()
