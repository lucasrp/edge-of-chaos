"""The protocol's load-bearing invariant (pass-3 adversarial finding): a producer's presentation
descriptor ADDS obligations on top of the genus floor — it can NEVER buy a producer out of the rich
rite. A developed-prose artefato missing a cognitive move must still FAIL `check_genus`, even when its
declared presentation floor is fully satisfied.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from unittest import mock  # noqa: E402
import close  # noqa: E402
import render  # noqa: E402


def _art(skill, blocks):
    return {
        "skill": skill,
        "content": {"sections": [{"title": "s", "blocks": blocks}]},
        "intent": "open: x; bet: y",
        "cites": [{"ref": "r", "snippet": "s", "kind": "mundo", "relevant": True}],
        "proposes": [{"body": "b", "kind": "thread"}],
    }


def _para(t):
    return {"type": "paragraph", "text": t}


def _ascii():
    return {"type": "ascii-diagram", "content": "a -> b -> c"}


class DescriptorAddsNeverSubtracts(unittest.TestCase):
    def test_developed_prose_map_missing_moves_still_fails_genus(self):
        # 3 prose blocks → the content-relative rich rite is owed; NO move markers present; AND the
        # map's presentation floor (>=2 illustrations) is fully satisfied.
        v = close.check_genus(_art("map", [
            _para("plain prose with no cognitive markers at all here"),
            _para("more plain prose carrying none of the four moves"),
            _para("still more ordinary prose, nothing marked"),
            _ascii(), _ascii(),
        ]))
        self.assertTrue(any(x.startswith("rich-rite") for x in v), v)       # genus floor still bites
        self.assertFalse(any(x.startswith("presentation") for x in v), v)   # presentation IS satisfied

    def test_map_short_on_illustrations_flags_presentation(self):
        v = close.check_genus(_art("map", [_ascii()]))                      # only 1 illustration
        self.assertTrue(any(x.startswith("presentation:min_blocks_of") for x in v), v)


class GatesAgreeWithRendering(unittest.TestCase):
    """The Phase-2/3 review fixes: a gate must credit a block only when it actually renders/verifies."""

    def _table(self):
        return {"type": "table", "headers": ["a", "b"], "rows": [["1", "2"], ["3", "4"], ["5", "6"]]}

    def test_unrendered_diagram_does_not_satisfy_visual_coverage(self):
        blocks = [self._table(), {"type": "diagram", "layout": "dag",
                                  "nodes": [{"id": "a"}, {"id": "b"}],
                                  "edges": [{"source": "a", "target": "b"}]}]
        with mock.patch.object(render, "diagram_renderable", return_value=False):
            v = close.check_genus(_art("report", blocks))
        self.assertIn("visual-coverage", v)         # diagram rendered to a comment → no real visual
        with mock.patch.object(render, "diagram_renderable", return_value=True):
            v2 = close.check_genus(_art("report", blocks))
        self.assertNotIn("visual-coverage", v2)     # now it renders → covers

    def test_unrendered_chart_does_not_satisfy_visual_coverage(self):
        # the chart block is renderable-gated for visual-coverage the same way as diagram.
        blocks = [self._table(), {"type": "chart", "chart": "bar",
                                  "data": [{"label": "x", "value": 1}]}]
        with mock.patch.object(render, "chart_renderable", return_value=False):
            v = close.check_genus(_art("report", blocks))
        self.assertIn("visual-coverage", v)         # chart rendered to a comment → no real visual
        with mock.patch.object(render, "chart_renderable", return_value=True):
            v2 = close.check_genus(_art("report", blocks))
        self.assertNotIn("visual-coverage", v2)     # now it renders → covers

    def test_canonicalized_alias_counts_as_visual(self):
        # a `kpi-grid` (metrics-grid alias) must satisfy visual-coverage — types are canonicalized.
        blocks = [self._table(), {"type": "kpi-grid", "items": [{"label": "x", "value": "1"}]}]
        self.assertNotIn("visual-coverage", close.check_genus(_art("report", blocks)))

    def test_mismatched_evidence_anchor_fails_genus(self):
        bad = {"type": "evidence", "quote_text": "hello", "source_ref": "m", "anchor": "deadbeef"}
        v = close.check_genus(_art("report", [bad]))
        self.assertTrue(any(x.startswith("evidence-anchor") for x in v), v)

    def test_production_floor_rejects_unrenderable_diagram(self):
        # production path (no capabilities dict) uses the authoritative renderable check: a diagram
        # the recipe/vl-convert rejects must NOT satisfy a map's illustration floor, even when
        # vl-convert is installed.
        good = {"type": "diagram", "layout": "dag",
                "nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}]}
        bad1 = {"type": "diagram", "layout": "nope", "nodes": [{"id": "a"}]}
        bad2 = {"type": "diagram", "layout": "dag", "nodes": []}
        with mock.patch.object(render, "diagram_renderable", side_effect=lambda b: b is good):
            v_bad = close.check_genus(_art("map", [bad1, bad2]))
            v_ok = close.check_genus(_art("map", [good, good]))
        self.assertTrue(any(x.startswith("presentation:min_blocks_of") for x in v_bad), v_bad)
        self.assertFalse(any(x.startswith("presentation") for x in v_ok), v_ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
