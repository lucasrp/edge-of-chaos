"""Phase 0 of the shared rich producer protocol (docs/plans/shared-rich-producer-protocol.md).

The seam: a per-producer DESCRIPTOR declares ADDITIONAL presentation obligations over a small, stable
PREDICATE VOCABULARY, evaluated by a GENERIC, capability-aware floor-evaluator — with no per-producer
branches. The descriptor never owns the rich rite (that stays the content-relative genus gate).

These pin the evaluator machinery: predicate satisfaction, capability degradation via any_of, the
writer-unsatisfiable (a real violation → bounce) vs environment-unsatisfiable (do NOT retry) split, the
fail-loud on an unregistered producer, and the no-regression guarantee (permissive descriptors today).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import producer_descriptor as pd  # noqa: E402


_DAG_NODES = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
_DAG_EDGES = [{"source": "a", "target": "b"}]


def _content(*types):
    """A spec whose blocks have the given canonical types (minimal valid-ish blocks)."""
    blocks = []
    for t in types:
        if t == "next-steps-grid":
            blocks.append({"type": t, "items": ["a", "b"]})
        elif t == "callout":
            blocks.append({"type": t, "text": "framing"})
        elif t in ("ascii-diagram", "code-block", "template-block", "raw-html"):
            blocks.append({"type": t, "content": "A -> B"})            # these read `content`, not `text`
        elif t in ("metrics-grid", "kpi-grid"):
            blocks.append({"type": t, "items": [{"label": "x", "value": "1"}]})  # grid reads `items`
        elif t == "diagram":
            blocks.append({"type": t, "layout": "dag", "nodes": _DAG_NODES, "edges": _DAG_EDGES})
        elif t == "chart":
            blocks.append({"type": t, "chart": "bar", "data": [{"label": "x", "value": 1}]})
        else:
            blocks.append({"type": t, "text": "x"})
    return {"sections": [{"title": "s", "blocks": blocks}]}


class MinBlocksOf(unittest.TestCase):
    def test_satisfied_when_count_met(self):
        req = [{"pred": "min_blocks_of", "types": ["ascii-diagram"], "n": 2}]
        v, env = pd.evaluate_floor(_content("ascii-diagram", "ascii-diagram"), req, capabilities={})
        self.assertEqual(v, [])
        self.assertEqual(env, [])

    def test_writer_unsatisfiable_when_too_few(self):
        req = [{"pred": "min_blocks_of", "types": ["ascii-diagram"], "n": 2}]
        v, env = pd.evaluate_floor(_content("ascii-diagram"), req, capabilities={})
        self.assertTrue(v)            # a real violation — the writer could have added another
        self.assertEqual(env, [])

    def test_empty_payload_block_does_not_count(self):
        # two ascii-diagrams with blank content are not real illustrations — must not satisfy the floor.
        req = [{"pred": "min_blocks_of", "types": ["ascii-diagram"], "n": 2}]
        empty = {"sections": [{"title": "s", "blocks": [
            {"type": "ascii-diagram", "content": "  "}, {"type": "ascii-diagram", "content": ""}]}]}
        self.assertTrue(pd.evaluate_floor(empty, req, capabilities={})[0])

    def test_alias_canonicalized_before_counting(self):
        # a `kpi-grid` block counts as `metrics-grid` (render alias) before the floor counts types.
        req = [{"pred": "min_blocks_of", "types": ["metrics-grid"], "n": 1}]
        v, env = pd.evaluate_floor(_content("kpi-grid"), req, capabilities={})
        self.assertEqual(v, [])


class CapabilityAwareness(unittest.TestCase):
    def test_any_of_falls_back_when_capability_absent(self):
        # diagram needs vl-convert; absent → the any_of branch on ascii-diagram (always available)
        # carries it.
        req = [{"pred": "any_of", "options": [
            {"pred": "min_blocks_of", "types": ["diagram"], "n": 1},
            {"pred": "min_blocks_of", "types": ["ascii-diagram"], "n": 1}]}]
        v, env = pd.evaluate_floor(_content("ascii-diagram"), req, capabilities={"vl-convert": False})
        self.assertEqual(v, [])

    def test_environment_unsatisfiable_is_not_a_violation_and_not_retried(self):
        # require a diagram, vl-convert absent, NO fallback → environment-unsatisfiable: env_skipped,
        # NOT a writer violation (so run_close never bounces/retries an impossible floor).
        req = [{"pred": "min_blocks_of", "types": ["diagram"], "n": 1}]
        v, env = pd.evaluate_floor(_content(), req, capabilities={"vl-convert": False})
        self.assertEqual(v, [])       # not a writer violation
        self.assertTrue(env)          # marked environment-unsatisfiable

    def test_writer_unsatisfiable_when_capability_present_but_unused(self):
        req = [{"pred": "min_blocks_of", "types": ["diagram"], "n": 1}]
        v, env = pd.evaluate_floor(_content(), req, capabilities={"vl-convert": True})
        self.assertTrue(v)            # vl-convert is available — the writer simply emitted no diagram
        self.assertEqual(env, [])

    def test_diagram_counts_only_when_renderable(self):
        # even with vl-convert available, an empty or malformed-topology diagram cannot render → it
        # must not count (the mocked path uses the recipe VALIDATOR for validity).
        req = [{"pred": "min_blocks_of", "types": ["diagram"], "n": 1}]

        def c(block):
            return {"sections": [{"title": "s", "blocks": [block]}]}
        good = {"type": "diagram", "layout": "dag", "nodes": _DAG_NODES, "edges": _DAG_EDGES}
        self.assertEqual(pd.evaluate_floor(c(good), req, capabilities={"vl-convert": True})[0], [])
        self.assertTrue(pd.evaluate_floor(  # empty topology — no payload
            c({"type": "diagram", "layout": "dag", "nodes": []}), req,
            capabilities={"vl-convert": True})[0])
        self.assertTrue(pd.evaluate_floor(  # unknown layout — validator rejects
            c({"type": "diagram", "layout": "nope", "nodes": _DAG_NODES}), req,
            capabilities={"vl-convert": True})[0])

    def test_chart_counts_only_when_renderable(self):
        # the chart block is a renderable-gated visual the same way as diagram.
        req = [{"pred": "min_blocks_of", "types": ["chart"], "n": 1}]

        def c(block):
            return {"sections": [{"title": "s", "blocks": [block]}]}
        good = {"type": "chart", "chart": "bar", "data": [{"label": "x", "value": 1}]}
        self.assertEqual(pd.evaluate_floor(c(good), req, capabilities={"vl-convert": True})[0], [])
        self.assertTrue(pd.evaluate_floor(  # empty data — validator rejects
            c({"type": "chart", "chart": "bar", "data": []}), req,
            capabilities={"vl-convert": True})[0])
        # vl-convert absent with no fallback → environment-unsatisfiable, never silently satisfied.
        v2, env2 = pd.evaluate_floor(c(good), req, capabilities={"vl-convert": False})
        self.assertEqual(v2, [])
        self.assertTrue(env2)

    def test_unrenderable_block_does_not_count(self):
        # a `diagram` block present while vl-convert is absent must NOT satisfy a diagram floor (it
        # cannot render) — any_of must bounce to the available fallback, not pass an unrenderable block.
        req = [{"pred": "any_of", "options": [
            {"pred": "min_blocks_of", "types": ["diagram"], "n": 1},
            {"pred": "min_blocks_of", "types": ["ascii-diagram"], "n": 1}]}]
        v, env = pd.evaluate_floor(_content("diagram"), req, capabilities={"vl-convert": False})
        self.assertTrue(v)            # writer-unsat: should have used the ascii-diagram fallback
        # and a bare diagram floor with no fallback is environment-unsat, never silently satisfied
        v2, env2 = pd.evaluate_floor(_content("diagram"),
                                     [{"pred": "min_blocks_of", "types": ["diagram"], "n": 1}],
                                     capabilities={"vl-convert": False})
        self.assertEqual(v2, [])
        self.assertTrue(env2)


class Structure(unittest.TestCase):
    def test_framed_steps_detected(self):
        req = [{"pred": "has_structure", "id": "framed_steps"}]
        self.assertEqual(pd.evaluate_floor(_content("next-steps-grid"), req, capabilities={})[0], [])
        self.assertTrue(pd.evaluate_floor(_content("paragraph"), req, capabilities={})[0])

    def test_framed_steps_via_grouped_now_next_later(self):
        # next-steps-grid supports grouped fields (now/next/later) — they carry real payload too.
        req = [{"pred": "has_structure", "id": "framed_steps"}]
        grouped = {"sections": [{"blocks": [
            {"type": "next-steps-grid", "now": ["a"], "next": ["b"], "later": ["c"]}]}]}
        self.assertEqual(pd.evaluate_floor(grouped, req, capabilities={})[0], [])

    def test_empty_structural_block_does_not_satisfy(self):
        # an empty steps grid / empty callout must NOT satisfy the structure/framing floors.
        empty_grid = {"sections": [{"blocks": [{"type": "next-steps-grid", "items": []}]}]}
        self.assertTrue(pd.evaluate_floor(empty_grid, [{"pred": "has_structure", "id": "framed_steps"}], capabilities={})[0])
        empty_callout = {"sections": [{"blocks": [{"type": "callout", "text": ""}]}]}
        self.assertTrue(pd.evaluate_floor(empty_callout, [{"pred": "contextual_framing"}], capabilities={})[0])

    def test_contextual_framing_detected(self):
        req = [{"pred": "contextual_framing"}]
        self.assertEqual(pd.evaluate_floor(_content("callout"), req, capabilities={})[0], [])
        self.assertTrue(pd.evaluate_floor(_content("paragraph"), req, capabilities={})[0])

    def test_links_synonym_diagram_counts(self):
        # a diagram authored with the `links` synonym (→ edges) must count (the recipe reads it).
        req = [{"pred": "min_blocks_of", "types": ["diagram"], "n": 1}]
        c = {"sections": [{"blocks": [{"type": "diagram", "layout": "dag",
                                       "nodes": _DAG_NODES, "edges": _DAG_EDGES}]}]}
        self.assertEqual(pd.evaluate_floor(c, req, capabilities={"vl-convert": True})[0], [])


class RegistryAndFailLoud(unittest.TestCase):
    def test_all_five_producers_registered(self):
        for skill in ("report", "research", "map", "plan", "discovery"):
            self.assertIsNotNone(pd.descriptor_for(skill), skill)

    def test_unregistered_producer_fails_loud(self):
        with self.assertRaises(KeyError):
            pd.require_descriptor("no-such-producer")

    def test_prose_producers_have_no_presentation_floor(self):
        # report/research depth IS the genus rich rite — they declare no presentation floor.
        for skill in ("report", "research"):
            art = {"skill": skill, "content": _content("paragraph")}
            self.assertEqual(pd.presentation_violations(art), [], skill)

    def test_visual_producers_owe_their_form_floor(self):
        # map owes >=2 illustrations; one is not enough.
        self.assertTrue(pd.presentation_violations({"skill": "map", "content": _content("ascii-diagram")}))
        self.assertEqual(
            pd.presentation_violations({"skill": "map", "content": _content("ascii-diagram", "ascii-diagram")}), [])
        # plan owes framed steps + an illustration; discovery owes contextual framing.
        self.assertTrue(pd.presentation_violations({"skill": "plan", "content": _content("paragraph")}))
        self.assertEqual(
            pd.presentation_violations({"skill": "plan", "content": _content("next-steps-grid", "ascii-diagram")}), [])
        self.assertTrue(pd.presentation_violations({"skill": "discovery", "content": _content("paragraph")}))
        self.assertEqual(
            pd.presentation_violations({"skill": "discovery", "content": _content("callout")}), [])

    def test_no_skill_or_unknown_is_noop(self):
        self.assertEqual(pd.presentation_violations({"content": _content("paragraph")}), [])
        self.assertEqual(pd.presentation_violations({"skill": "adr", "content": _content("paragraph")}), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
