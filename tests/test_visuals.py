"""Slice 4 — the grounded 2-spot visual post-pass. Deterministic/offline: a fake role-tagged
dispatch_fn returns canned selector/builder JSON, so no live model + no subagent dispatch is needed.
Proves: the no-op contract, two-visual splice, attribution rejection (incl. the laundering guard),
anti-hairball caps, chart/graph quality false-positives, splice purity, the invariant guard, and the
real shipping path (the spliced content reaches close.run_close's genus check)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visuals    # noqa: E402
import render     # noqa: E402

# Evidence the visuals must be grounded against (the corpus attribution resolves to).
_EVIDENCE = {
    "text": ("Across slices the confirmed-bug count rose: slice one closed 3 defects, slice three "
             "closed 7 defects. The form gate feeds reconcile, and reconcile feeds the close gate."),
    "findings": [{"claim": "slice three closed 7 defects", "bears_on": "richness", "citation": "audit"}],
}


def _content(n_sections=3):
    return {"title": "t", "sections": [
        {"title": f"Section {i}", "blocks": [{"type": "paragraph", "text": f"prose {i}"}]}
        for i in range(n_sections)]}


def _fence(d):
    return "```json\n" + json.dumps(d) + "\n```"


def _chart_builder_payload():
    return {"block": {"type": "chart", "chart": "bar", "title": "Defects closed",
                      "data": [{"label": "slice one", "value": 3}, {"label": "slice three", "value": 7}]},
            "provenance": [
                {"datum": {"label": "slice one", "value": 3}, "source": "slice one closed 3 defects"},
                {"datum": {"label": "slice three", "value": 7}, "source": "slice three closed 7 defects"}]}


def _graph_builder_payload():
    return {"block": {"type": "diagram", "layout": "dag",
                      "nodes": [{"id": "fg", "label": "form gate"}, {"id": "rc", "label": "reconcile"},
                                {"id": "cg", "label": "close gate"}],
                      "edges": [{"source": "fg", "target": "rc"}, {"source": "rc", "target": "cg"}]},
            "provenance": [
                {"edge": {"source": "fg", "target": "rc"}, "source": "the form gate feeds reconcile"},
                {"edge": {"source": "rc", "target": "cg"}, "source": "and reconcile feeds the close gate"}]}


def _dispatch(spots, builder_by_kind):
    """A fake role-tagged dispatch_fn: selector returns `spots`; builder returns the canned payload for
    the kind named in its prompt."""
    def dispatch_fn(role, prompt):
        if role == "selector":
            return _fence({"spots": spots})
        kind = "chart" if '"chart"' in prompt or "ONE chart" in prompt else "graph"
        return _fence(builder_by_kind[kind])
    return dispatch_fn


class NoOp(unittest.TestCase):
    def test_dispatch_none_is_noop(self):
        c = _content()
        out, flags = visuals.add_visuals(c, evidence=_EVIDENCE, dispatch_fn=None)
        self.assertIs(out, c)
        self.assertEqual(flags, [])


class CapEnforced(unittest.TestCase):
    def test_zero_cap_dispatches_nothing_and_splices_nothing(self):
        # codex P3: max_visuals=0 must add nothing AND never dispatch (selector or builder).
        calls = []
        def d(role, prompt):
            calls.append(role)
            return _fence({"spots": [{"section_index": 0, "visual_kind": "chart", "intent": "x"}]})
        out, flags = visuals.add_visuals(_content(), evidence=_EVIDENCE, dispatch_fn=d, max_visuals=0)
        types = [render.canonical_block(b)[0] for s in out["sections"] for b in s["blocks"]]
        self.assertNotIn("chart", types)
        self.assertEqual(calls, [], "a zero cap must not dispatch any subagent")

    def test_one_worthwhile_spot_is_not_a_shortfall(self):
        # codex P3: selector intentionally returns 1 spot that grounds → no false 'wanted 2' shortfall.
        spots = [{"section_index": 0, "visual_kind": "chart", "intent": "defects per slice"}]
        d = _dispatch(spots, {"chart": _chart_builder_payload(), "graph": _graph_builder_payload()})
        out, flags = visuals.add_visuals(_content(), evidence=_EVIDENCE, dispatch_fn=d, max_visuals=2)
        types = [render.canonical_block(b)[0] for s in out["sections"] for b in s["blocks"]]
        self.assertIn("chart", types)
        self.assertEqual(flags, [], f"one grounded spot is not a shortfall, got {flags}")


class SynonymPayloads(unittest.TestCase):
    def test_chart_values_synonym_accepted(self):
        ok, why = visuals.chart_block_ok({"type": "chart", "chart": "bar",
                                          "values": [{"label": "a", "value": 1}]})  # `values` synonym
        self.assertTrue(ok, why)

    def test_graph_links_synonym_accepted(self):
        ok, why = visuals.graph_block_ok({"type": "diagram", "layout": "dag",
                                          "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
                                          "links": [{"source": "a", "target": "b"}]})  # `links` synonym
        self.assertTrue(ok, why)


class TwoVisualSuccess(unittest.TestCase):
    def test_two_grounded_visuals_spliced(self):
        spots = [{"section_index": 0, "visual_kind": "chart", "intent": "defects per slice"},
                 {"section_index": 1, "visual_kind": "graph", "intent": "the gate chain"}]
        d = _dispatch(spots, {"chart": _chart_builder_payload(), "graph": _graph_builder_payload()})
        out, flags = visuals.add_visuals(_content(), evidence=_EVIDENCE, dispatch_fn=d)
        self.assertIsInstance(out, dict)
        types = [render.canonical_block(b)[0] for s in out["sections"] for b in s["blocks"]]
        self.assertIn("chart", types)
        self.assertIn("diagram", types)
        self.assertEqual(flags, [], f"two grounded visuals → no shortfall, got {flags}")


class AttributionRejection(unittest.TestCase):
    def test_fabricated_value_is_dropped(self):
        bad = _chart_builder_payload()
        bad["block"]["data"][1]["value"] = 999          # not in any evidence span
        bad["provenance"][1]["source"] = "slice three closed 999 defects"  # span not in evidence
        spots = [{"section_index": 0, "visual_kind": "chart", "intent": "x"}]
        d = _dispatch(spots, {"chart": bad, "graph": _graph_builder_payload()})
        out, flags = visuals.add_visuals(_content(), evidence=_EVIDENCE, dispatch_fn=d, max_visuals=1)
        types = [render.canonical_block(b)[0] for s in out["sections"] for b in s["blocks"]]
        self.assertNotIn("chart", types, "a fabricated chart must be dropped")
        self.assertTrue(any("ungrounded" in f for f in flags))
        self.assertTrue(any("shortfall" in f for f in flags))

    def test_laundering_guard_source_only_in_report_not_evidence(self):
        # datum cites a span that's in the REPORT prose but NOT the evidence → rejected.
        block = {"type": "chart", "chart": "bar", "data": [{"label": "prose 0", "value": 1}]}
        prov = [{"datum": {"label": "prose 0", "value": 1}, "source": "prose 0"}]  # only in report
        ok, why = visuals.attributable(block, prov, _EVIDENCE)
        self.assertFalse(ok, why)

    def test_non_bar_recipe_fields_are_grounded(self):
        # P1 regression: line/scatter use {x,y} not {label,value}; a fabricated trend point must NOT
        # slip through just because it lacks `label`/`value` fields.
        block = {"type": "chart", "chart": "line",
                 "data": [{"x": "slice one", "y": 3}, {"x": "fabricated", "y": 999}]}
        prov = [{"source": "slice one closed 3 defects"}, {"source": "fabricated 999 trend"}]
        ok, why = visuals.attributable(block, prov, _EVIDENCE)
        self.assertFalse(ok, "a fabricated {x,y} datum must be rejected")

    def test_non_bar_recipe_grounded_when_real(self):
        block = {"type": "chart", "chart": "line",
                 "data": [{"x": "slice one", "y": 3}, {"x": "slice three", "y": 7}]}
        prov = [{"source": "slice one closed 3 defects"},
                {"source": "slice three closed 7 defects"}]
        ok, why = visuals.attributable(block, prov, _EVIDENCE)
        self.assertTrue(ok, why)


class AntiHairball(unittest.TestCase):
    def test_oversized_graph_dropped(self):
        big = {"block": {"type": "diagram", "layout": "dag",
                         "nodes": [{"id": str(i), "label": f"n{i}"} for i in range(14)],
                         "edges": [{"source": "0", "target": "1"}]}, "provenance": []}
        spots = [{"section_index": 0, "visual_kind": "graph", "intent": "x"}]
        d = _dispatch(spots, {"chart": _chart_builder_payload(), "graph": big})
        _out, flags = visuals.add_visuals(_content(), evidence=_EVIDENCE, dispatch_fn=d, max_visuals=1)
        self.assertTrue(any("too large" in f or "ungrounded" in f for f in flags))

    def test_cyclic_dag_rejected(self):
        # codex P2: a dag with a cycle (A→B, B→A) would render with a back-edge silently dropped.
        cyclic = {"type": "diagram", "layout": "dag",
                  "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
                  "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}
        ok, why = visuals.graph_block_ok(cyclic)
        self.assertFalse(ok)
        self.assertIn("cycle", why)
        # the same edges under force (undirected) are fine
        ok2, _ = visuals.graph_block_ok({**cyclic, "layout": "force"})
        self.assertTrue(ok2)

    def test_dense_graph_rejected_by_block_ok(self):
        block = {"type": "diagram", "layout": "force",
                 "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}, {"id": "c", "label": "c"}],
                 "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"},
                           {"source": "a", "target": "c"}, {"source": "c", "target": "a"},
                           {"source": "b", "target": "a"}, {"source": "c", "target": "b"},
                           {"source": "a", "target": "a"}]}  # 7 edges / 3 nodes > 2*nodes
        ok, why = visuals.graph_block_ok(block)
        self.assertFalse(ok)
        self.assertIn("dense", why)


class QualityGates(unittest.TestCase):
    def test_chart_ok_and_empty_rejected(self):
        ok, _ = visuals.chart_block_ok({"type": "chart", "chart": "bar",
                                        "data": [{"label": "a", "value": 1}, {"label": "b", "value": 2}]})
        self.assertTrue(ok)
        ok, why = visuals.chart_block_ok({"type": "chart", "chart": "bar", "data": []})
        self.assertFalse(ok)
        self.assertIn("no data", why)

    def test_graph_ok_and_undersized_rejected(self):
        ok, _ = visuals.graph_block_ok({"type": "diagram", "layout": "dag",
                                        "nodes": [{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
                                        "edges": [{"source": "a", "target": "b"}]})
        self.assertTrue(ok)
        ok, why = visuals.graph_block_ok({"type": "diagram", "layout": "dag",
                                          "nodes": [{"id": "a", "label": "a"}], "edges": []})
        self.assertFalse(ok)


class SplicePurity(unittest.TestCase):
    def test_splice_is_pure_and_at_section_end(self):
        c = _content(2)
        block = {"type": "chart", "chart": "bar", "data": [{"label": "a", "value": 1}]}
        out = visuals.splice_visuals(c, [{"block": block, "section_index": 1}])
        self.assertEqual(len(c["sections"][1]["blocks"]), 1, "caller's content must be untouched")
        self.assertEqual(out["sections"][1]["blocks"][-1]["type"], "chart")

    def test_unresolved_anchor_appends_trailing_section(self):
        c = _content(2)
        block = {"type": "chart", "chart": "bar", "data": [{"label": "a", "value": 1}]}
        out = visuals.splice_visuals(c, [{"block": block, "section_index": None}])
        self.assertEqual(len(out["sections"]), 3)
        self.assertEqual(out["sections"][-1]["blocks"][0]["type"], "chart")


class InvariantGuard(unittest.TestCase):
    def test_assert_fires_when_content_has_a_chart(self):
        c = {"sections": [{"title": "", "blocks": [{"type": "chart", "chart": "bar", "data": [1]}]}]}
        with self.assertRaises(AssertionError):
            visuals._assert_no_drawn_visuals(c)

    def test_add_visuals_skips_and_flags_preexisting_visual(self):
        c = {"sections": [{"title": "", "blocks": [{"type": "chart", "chart": "bar", "data": [1]}]}]}
        d = _dispatch([], {})
        out, flags = visuals.add_visuals(c, evidence=_EVIDENCE, dispatch_fn=d)
        self.assertIs(out, c)
        self.assertTrue(any("already carries" in f for f in flags))

    def test_invariant_guard_scans_additional_sections(self):
        # P2 regression: a visual hiding in additional_sections must be detected too.
        c = {"sections": [], "additional_sections": [
            {"title": "", "blocks": [{"type": "diagram", "layout": "dag", "nodes": [], "edges": []}]}]}
        self.assertTrue(visuals._existing_drawn_visuals(c), "must scan additional_sections")


class GroundingCompleteness(unittest.TestCase):
    """ed-research (real-issues deep-dive): EVERY reader-visible surface of EVERY closed recipe must be
    grounded — datum fields, chart/diagram title + axis/stage labels, node labels (incl. ISOLATED),
    id-only node text, and edge labels. A fabrication in ANY surface must be rejected."""
    EV = {"text": "alpha 10 beta 20 gamma 30 cause leads to effect under load latency throughput"}
    PROV = [{"source": EV["text"]}]   # whole-evidence span; grounds anything that IS in EV

    def _rej(self, block):
        ok, why = visuals.attributable(block, self.PROV, self.EV)
        self.assertFalse(ok, f"expected rejection, got pass for {block}")

    def _acc(self, block):
        ok, why = visuals.attributable(block, self.PROV, self.EV)
        self.assertTrue(ok, f"expected pass, got: {why}")

    def test_negative_value_keeps_its_sign(self):
        # codex P2: a signed evidence value (-5) must ground value:-5 and REJECT value:5.
        ev = {"text": "delta -5 change"}
        prov = [{"source": "delta -5 change"}]
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "delta", "value": -5}]}, prov, ev)[0])
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "delta", "value": 5}]}, prov, ev)[0])

    def test_substring_label_rejected(self):
        # codex P2: 'a' must NOT match 'alpha' — labels ground as whole tokens, not substrings.
        ev = {"text": "alpha 10"}
        prov = [{"source": "alpha 10"}]
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "a", "value": 10}]}, prov, ev)[0])
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 10}]}, prov, ev)[0])

    def test_numeric_label_does_not_ground_value(self):
        # codex P2: 'one k cost 10' — a fabricated value:1 must NOT ride on the '1' embedded in a '1k'
        # label. (Using a token-friendly label so the label itself grounds.)
        ev = {"text": "1k cost 10"}
        prov = [{"source": "1k cost 10"}]
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "1k", "value": 1}]}, prov, ev)[0],
            "a value embedded only in the label must not ground")
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "1k", "value": 10}]}, prov, ev)[0],
            "the real measure 10 must ground")

    def test_bar_surfaces(self):
        self._rej({"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 999}]})
        self._rej({"type": "chart", "chart": "bar", "data": [{"label": "delta", "value": 10}]})
        self._rej({"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 10}],
                   "title": "revenue"})
        self._acc({"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 10}],
                   "title": "alpha load"})

    def test_line_surfaces(self):
        self._rej({"type": "chart", "chart": "line", "data": [{"x": "alpha", "y": 777}]})
        self._rej({"type": "chart", "chart": "line", "data": [{"x": "omega", "y": 10}]})
        self._rej({"type": "chart", "chart": "line", "data": [{"x": "alpha", "y": 10}],
                   "y_label": "revenue"})
        self._acc({"type": "chart", "chart": "line", "data": [{"x": "alpha", "y": 10}]})

    def test_scatter_surfaces(self):
        self._rej({"type": "chart", "chart": "scatter", "data": [{"x": 10, "y": 888}]})
        self._rej({"type": "chart", "chart": "scatter", "data": [{"x": 10, "y": 20, "label": "phantom"}]})
        self._rej({"type": "chart", "chart": "scatter", "data": [{"x": 10, "y": 20}], "x_label": "revenue"})

    def test_slopegraph_surfaces(self):
        self._rej({"type": "chart", "chart": "slopegraph",
                   "data": [{"item": "alpha", "before": 10, "after": 555}]})
        self._rej({"type": "chart", "chart": "slopegraph",
                   "data": [{"item": "ghost", "before": 10, "after": 20}]})
        self._rej({"type": "chart", "chart": "slopegraph",
                   "data": [{"item": "alpha", "before": 10, "after": 20}], "before_label": "fabricated"})

    def test_sparkline_scalar_data(self):
        self._rej({"type": "chart", "chart": "sparkline", "data": [10, 20, 444]})
        self._acc({"type": "chart", "chart": "sparkline", "data": [10, 20, 30]})

    def test_dag_surfaces(self):
        self._rej({"type": "diagram", "layout": "dag",
                   "nodes": [{"id": "n1", "label": "cause"}, {"id": "n2", "label": "phantom"}],
                   "edges": [{"source": "n1", "target": "n2"}]})
        self._rej({"type": "diagram", "layout": "dag",  # isolated node — never in an edge, still drawn
                   "nodes": [{"id": "n1", "label": "cause"}, {"id": "n2", "label": "effect"},
                             {"id": "iso", "label": "orphan"}],
                   "edges": [{"source": "n1", "target": "n2"}]})
        self._rej({"type": "diagram", "layout": "dag",  # no label → id is the visible text
                   "nodes": [{"id": "cause"}, {"id": "madeup"}],
                   "edges": [{"source": "cause", "target": "madeup"}]})
        self._rej({"type": "diagram", "layout": "dag",  # fabricated edge label
                   "nodes": [{"id": "n1", "label": "cause"}, {"id": "n2", "label": "effect"}],
                   "edges": [{"source": "n1", "target": "n2", "label": "fabricated-relation"}]})
        self._rej({"type": "diagram", "layout": "dag", "title": "phantom system",
                   "nodes": [{"id": "n1", "label": "cause"}, {"id": "n2", "label": "effect"}],
                   "edges": [{"source": "n1", "target": "n2"}]})
        self._acc({"type": "diagram", "layout": "dag",
                   "nodes": [{"id": "n1", "label": "cause"}, {"id": "n2", "label": "effect"}],
                   "edges": [{"source": "n1", "target": "n2", "label": "leads to"}]})

    def test_force_isolated_node(self):
        self._rej({"type": "diagram", "layout": "force",
                   "nodes": [{"id": "a", "label": "latency"}, {"id": "b", "label": "throughput"},
                             {"id": "c", "label": "phantom"}],
                   "edges": [{"source": "a", "target": "b"}]})

    def test_reversed_directed_edge_rejected(self):
        # codex P2: 'cause leads to effect' supports cause→effect, NOT the reversed effect→cause.
        ev = {"text": "cause leads to effect"}
        prov = [{"source": "cause leads to effect"}]
        rev = {"type": "diagram", "layout": "dag",
               "nodes": [{"id": "a", "label": "cause"}, {"id": "b", "label": "effect"}],
               "edges": [{"source": "b", "target": "a"}]}  # reversed
        self.assertFalse(visuals.attributable(rev, prov, ev)[0], "a reversed directed edge must fail")
        fwd = {"type": "diagram", "layout": "dag",
               "nodes": [{"id": "a", "label": "cause"}, {"id": "b", "label": "effect"}],
               "edges": [{"source": "a", "target": "b"}]}
        self.assertTrue(visuals.attributable(fwd, prov, ev)[0])

    def test_force_edge_ignores_direction(self):
        # an undirected force edge is grounded by co-occurrence regardless of order.
        ev = {"text": "cause leads to effect"}
        prov = [{"source": "cause leads to effect"}]
        und = {"type": "diagram", "layout": "force",
               "nodes": [{"id": "a", "label": "cause"}, {"id": "b", "label": "effect"}],
               "edges": [{"source": "b", "target": "a"}]}
        self.assertTrue(visuals.attributable(und, prov, ev)[0])

    def test_swapped_slopegraph_values_rejected(self):
        # codex P2: 'alpha before 10 after 20' supports before=10/after=20, NOT the swap.
        ev = {"text": "alpha before 10 after 20"}
        prov = [{"source": "alpha before 10 after 20"}]
        swapped = {"type": "chart", "chart": "slopegraph", "before_label": "before", "after_label": "after",
                   "data": [{"item": "alpha", "before": 20, "after": 10}]}
        self.assertFalse(visuals.attributable(swapped, prov, ev)[0], "swapped before/after must fail")
        correct = {"type": "chart", "chart": "slopegraph", "before_label": "before", "after_label": "after",
                   "data": [{"item": "alpha", "before": 10, "after": 20}]}
        self.assertTrue(visuals.attributable(correct, prov, ev)[0])

    def test_swapped_scatter_xy_rejected(self):
        ev = {"text": "point x 10 y 20"}
        prov = [{"source": "point x 10 y 20"}]
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "scatter", "data": [{"x": 20, "y": 10}]}, prov, ev)[0])
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "scatter", "data": [{"x": 10, "y": 20}]}, prov, ev)[0])

    def test_json_key_order_does_not_affect_grounding(self):
        # codex P2: semantic field order (x,y / before,after), not JSON key order — {"y":20,"x":10} is
        # correct data and must pass.
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "scatter", "data": [{"y": 20, "x": 10}]},
            [{"source": "point x 10 y 20"}], {"text": "point x 10 y 20"})[0])
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "slopegraph", "before_label": "before", "after_label": "after",
             "data": [{"after": 20, "item": "alpha", "before": 10}]},
            [{"source": "alpha before 10 after 20"}], {"text": "alpha before 10 after 20"})[0])

    def test_edge_label_must_ground_with_its_endpoints(self):
        # codex P2: an A→B edge can't borrow a relation word from an unrelated sentence — the label
        # must co-occur with both endpoints in ONE unit.
        ev = {"text": "cause leads to effect. latency blocks throughput"}
        prov = [{"source": "cause leads to effect"}]
        bad = {"type": "diagram", "layout": "dag",
               "nodes": [{"id": "a", "label": "cause"}, {"id": "b", "label": "effect"}],
               "edges": [{"source": "a", "target": "b", "label": "blocks"}]}  # 'blocks' is elsewhere
        self.assertFalse(visuals.attributable(bad, prov, ev)[0], "mislabeled edge must be rejected")
        good = {"type": "diagram", "layout": "dag",
                "nodes": [{"id": "a", "label": "cause"}, {"id": "b", "label": "effect"}],
                "edges": [{"source": "a", "target": "b", "label": "leads to"}]}
        self.assertTrue(visuals.attributable(good, prov, ev)[0])

    def test_cross_unit_association_rejected(self):
        # codex P1: 'alpha 10' and 'beta 20' are SEPARATE evidence units; a datum pairing alpha↔20
        # must fail (no single unit asserts that association) even though both tokens exist.
        ev = {"text": "alpha 10. beta 20."}
        prov = [{"source": "alpha 10"}]
        ok, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                      "data": [{"label": "alpha", "value": 20}]}, prov, ev)
        self.assertFalse(ok, "a cross-unit label↔value pairing must be rejected")
        ok2, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                       "data": [{"label": "alpha", "value": 10}]}, prov, ev)
        self.assertTrue(ok2, "the real same-unit pairing must pass")

    def test_exact_number_not_substring(self):
        # codex P2: '10' must NOT match an evidence '100' (digit-substring is wrong; exact only).
        ev = {"text": "alpha 100"}
        prov = [{"source": "alpha 100"}]
        ok, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                      "data": [{"label": "alpha", "value": 10}]}, prov, ev)
        self.assertFalse(ok, "10 must not ride on an evidence 100")
        ok2, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                       "data": [{"label": "alpha", "value": 100}]}, prov, ev)
        self.assertTrue(ok2)

    def test_whole_document_citation_does_not_defeat_binding(self):
        # a builder citing the WHOLE evidence as one span can't launder a cross-unit pairing — binding
        # resolves against the evidence's own sentence UNITS, not the builder's coarse span.
        ev = {"text": "alpha 10. beta 20."}
        prov = [{"source": "alpha 10. beta 20."}]   # the whole thing as one citation
        ok, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                      "data": [{"label": "alpha", "value": 20}]}, prov, ev)
        self.assertFalse(ok, "coarse citation must not defeat unit-level association binding")

    def test_within_sentence_comma_cross_pair_rejected(self):
        # codex P1: a single sentence joining two facts by comma must still split into clause units so
        # a cross-pair {slice one ↔ 7} fails (both tokens are in the sentence, but not the same clause).
        ev = {"text": "slice one closed 3 defects, slice three closed 7 defects"}
        prov = [{"source": "slice one closed 3 defects"}]
        ok, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                      "data": [{"label": "slice one", "value": 7}]}, prov, ev)
        self.assertFalse(ok, "a comma-joined within-sentence cross-pair must be rejected")
        ok2, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                       "data": [{"label": "slice one", "value": 3}]}, prov, ev)
        self.assertTrue(ok2, "the real same-clause pairing must pass")

    def test_undelimited_multifact_unit_rejects_mispairing(self):
        # codex P1: 'alpha 10 beta 20' is ONE unit (no delimiter). A mispaired {alpha,20} must NOT
        # ground — the unit holds a sibling label (beta), so it's too ambiguous to pair. The chart
        # drops (safe) rather than ships a wrong pairing.
        ev = {"text": "alpha 10 beta 20"}
        prov = [{"source": "alpha 10 beta 20"}]
        mispaired = {"type": "chart", "chart": "bar",
                     "data": [{"label": "alpha", "value": 20}, {"label": "beta", "value": 10}]}
        self.assertFalse(visuals.attributable(mispaired, prov, ev)[0], "mispaired undelimited must fail")
        # the SAME ambiguous unit can't validate the 'correct' pairing either (safe: drop, don't guess)
        correct_but_ambiguous = {"type": "chart", "chart": "bar",
                                 "data": [{"label": "alpha", "value": 10}, {"label": "beta", "value": 20}]}
        self.assertFalse(visuals.attributable(correct_but_ambiguous, prov, ev)[0])
        # but WITH a delimiter the facts are separate units and the correct pairing grounds
        ev2 = {"text": "alpha 10, beta 20"}
        prov2 = [{"source": "alpha 10"}]
        self.assertTrue(visuals.attributable(correct_but_ambiguous, prov2, ev2)[0])

    def test_and_joined_cross_pair_rejected(self):
        # codex P1: facts joined by "and" (no comma) must also split into clause units, so a swapped
        # pair fails BOTH ways (alpha↔20 and the symmetric beta↔10).
        ev = {"text": "alpha closed 10 and beta closed 20"}
        prov = [{"source": "alpha closed 10"}]
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 20}]}, prov, ev)[0])
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "beta", "value": 10}]}, prov, ev)[0])
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 10}]}, prov, ev)[0])

    def test_digit_grouping_comma_not_split(self):
        ev = {"text": "alpha 3,000 items"}
        prov = [{"source": "alpha 3,000 items"}]
        ok, _ = visuals.attributable({"type": "chart", "chart": "bar",
                                      "data": [{"label": "alpha", "value": 3000}]}, prov, ev)
        self.assertTrue(ok, "3,000 must survive as one number, not split on its comma")

    def test_pt_comma_decimal_grounded(self):
        # codex P2: Portuguese comma decimals (0,91) must ground value 0.91 and REJECT 91 — the reports
        # are PT, so this is core language-agnosticism, not an edge case.
        ev = {"text": "alpha 0,91 de recall"}
        prov = [{"source": "alpha 0,91 de recall"}]
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 0.91}]}, prov, ev)[0])
        self.assertFalse(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 91}]}, prov, ev)[0])

    def test_pt_grouped_thousands_period(self):
        # PT thousands use a period: 3.000 → 3000.
        ev = {"text": "alpha 3.000 itens"}
        prov = [{"source": "alpha 3.000 itens"}]
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 3000}]}, prov, ev)[0])

    def test_mixed_separator_decimal(self):
        # codex P2: 1,234.56 (EN) and 1.234,56 (PT) → 1234.56, not 123456.
        self.assertEqual(visuals._parse_number("1,234.56"), 1234.56)
        self.assertEqual(visuals._parse_number("1.234,56"), 1234.56)
        self.assertEqual(visuals._parse_number("0,91"), 0.91)
        self.assertEqual(visuals._parse_number("3,000"), 3000.0)
        ev = {"text": "alpha 1.234,56 reais"}
        self.assertTrue(visuals.attributable(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 1234.56}]},
            [{"source": "alpha 1.234,56 reais"}], ev)[0])

    def test_decimal_value_grounded(self):
        # codex P2: a decimal metric (0.91) must not be torn apart by the unit splitter's period.
        ev = {"text": "alpha 0.91 recall"}
        prov = [{"source": "alpha 0.91 recall"}]
        ok, why = visuals.attributable({"type": "chart", "chart": "bar",
                                        "data": [{"label": "alpha", "value": 0.91}]}, prov, ev)
        self.assertTrue(ok, why)

    def test_finding_only_evidence_shown_in_prompt(self):
        # codex P2: finding-only evidence (seed shape, no top-level text) must still appear in prompts,
        # else the post-pass silently no-ops on the verifier's own evidence shape.
        txt = visuals._evidence_text({"findings": [{"claim": "slice three closed 7 defects",
                                                    "citation": "audit"}]})
        self.assertIn("slice three closed 7 defects", txt)

    def test_finding_only_evidence_grounds_a_chart(self):
        ev = {"findings": [{"claim": "alpha closed 5 defects", "bears_on": "x", "citation": "audit"}]}
        prov = [{"source": "alpha closed 5 defects"}]
        ok, why = visuals.attributable({"type": "chart", "chart": "bar",
                                        "data": [{"label": "alpha", "value": 5}]}, prov, ev)
        self.assertTrue(ok, why)

    def test_slopegraph_requires_grounded_before_after_labels(self):
        # codex P2: omitting before_label/after_label ships a hardcoded English default — reject; the
        # builder must supply grounded in-language labels.
        ev = {"text": "antes 10 depois 20 alpha"}
        prov = [{"source": "antes 10 depois 20 alpha"}]
        ok, _ = visuals.attributable({"type": "chart", "chart": "slopegraph",
                                      "data": [{"item": "alpha", "before": 10, "after": 20}]}, prov, ev)
        self.assertFalse(ok, "a slopegraph with no before/after labels would ship an English default")
        ok2, _ = visuals.attributable({"type": "chart", "chart": "slopegraph",
                                       "data": [{"item": "alpha", "before": 10, "after": 20}],
                                       "before_label": "antes", "after_label": "depois"}, prov, ev)
        self.assertTrue(ok2, "grounded in-language before/after labels must pass")


class ChromeSanitized(unittest.TestCase):
    def test_ungrounded_title_stripped_not_rejected(self):
        # decoration: a chart with grounded data but an ungrounded TITLE ships WITHOUT the title (the
        # title is dropped so it can't mislead) — it does not kill the data-grounded visual.
        ev = {"text": "alpha 10"}
        b = {"type": "chart", "chart": "bar", "title": "fabricated revenue",
             "x_label": "alpha", "data": [{"label": "alpha", "value": 10}]}
        out = visuals.sanitize_chrome(b, ev)
        self.assertNotIn("title", out, "ungrounded title must be stripped")
        self.assertEqual(out.get("x_label"), "alpha", "grounded axis label is kept")
        ok, why = visuals.attributable(out, [{"source": "alpha 10"}], ev)
        self.assertTrue(ok, why)

    def test_grounded_title_kept(self):
        ev = {"text": "alpha 10 load"}
        b = {"type": "chart", "chart": "bar", "title": "alpha load",
             "data": [{"label": "alpha", "value": 10}]}
        self.assertEqual(visuals.sanitize_chrome(b, ev).get("title"), "alpha load")


class GroundingGuard(unittest.TestCase):
    """The anti-whack-a-mole structural guard: if a recipe/schema adds a new VISIBLE top-level field
    without it being added to the grounded-text tuples, these fail — forcing the grounding rule to be
    updated in lockstep instead of silently shipping fabrication."""
    def test_chart_text_fields_cover_schema_visible_optionals(self):
        structural = {"horizontal", "facet", "v"}
        visible = set(render.BLOCK_SCHEMAS["chart"]["optional"]) - structural
        self.assertLessEqual(visible, set(visuals._CHART_TEXT_FIELDS),
                             f"unguarded chart-level visible field(s): {visible - set(visuals._CHART_TEXT_FIELDS)}")

    def test_diagram_text_fields_cover_schema_visible_optionals(self):
        structural = {"edges", "orientation", "v"}
        visible = set(render.BLOCK_SCHEMAS["diagram"]["optional"]) - structural
        self.assertLessEqual(visible, set(visuals._DIAGRAM_TEXT_FIELDS),
                             f"unguarded diagram-level visible field(s): {visible - set(visuals._DIAGRAM_TEXT_FIELDS)}")


class CombinedSectionIndex(unittest.TestCase):
    def test_spot_resolves_and_splices_into_additional_sections(self):
        # P2: the selector enumerates sections + additional_sections; an index into the additional list
        # must resolve + splice there, not append a stray trailing section.
        content = {"sections": [{"title": "A", "blocks": []}],
                   "additional_sections": [{"title": "B", "blocks": []}]}
        idx = visuals._resolve_section(content, {"section_index": 1})  # combined index 1 == B
        self.assertEqual(idx, 1)
        block = {"type": "chart", "chart": "bar", "data": [{"label": "a", "value": 1}]}
        out = visuals.splice_visuals(content, [{"block": block, "section_index": 1}])
        self.assertEqual(out["additional_sections"][0]["blocks"][-1]["type"], "chart")
        self.assertEqual(len(out["sections"]), 1, "no stray trailing section")


class CloseIntegration(unittest.TestCase):
    def test_spliced_content_passes_genus(self):
        # the real shipping path: add_visuals output becomes artefato['content']; close.check_genus
        # (run inside run_close every iteration) must see the spliced spec and accept the visual.
        import close
        spots = [{"section_index": 0, "visual_kind": "chart", "intent": "defects per slice"}]
        d = _dispatch(spots, {"chart": _chart_builder_payload(), "graph": _graph_builder_payload()})
        # a content spec that already clears the rich-rite floor on its own (derivation + gap-table)
        base = {"title": "t", "sections": [
            {"title": "Findings", "blocks": [
                {"type": "paragraph", "text": "Across slices the confirmed-bug count rose materially."},
                {"type": "derivation", "bullets": ["slice one closed 3", "slice three closed 7"]}]},
            {"title": "", "blocks": [{"type": "gap-table", "gaps": [{"description": "the live lag"}]}]}]}
        spliced, flags = visuals.add_visuals(base, evidence=_EVIDENCE, dispatch_fn=d, max_visuals=1)
        types = [render.canonical_block(b)[0] for s in spliced["sections"] for b in s["blocks"]]
        self.assertIn("chart", types)
        artefato = {"content": spliced, "intent": "show the slice progress",
                    "cites": [{"ref": "audit", "kind": "mundo", "relevant": True,
                               "snippet": "slice three closed 7 defects"}],
                    "proposes": [{"body": "ship it", "kind": "thread"}],
                    "distills": ["cluster:richness"]}
        self.assertEqual(close.check_genus(artefato), [], "the spliced spec must pass genus")


if __name__ == "__main__":
    unittest.main()
