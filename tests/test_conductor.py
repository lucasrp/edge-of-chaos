"""The conductor — multi-agent artefato production, SLICE 1 (EDGE_CONDUCTOR, dark by default).

The conductor (issue #36) divides one over-large synthesis into a state-tracked outline of
nodes authored FROM the excavate seed, fills each node via the existing producer cognition
(the model call INJECTED as `complete_fn`, like close.py's reviewers), gates each node with a
deterministic mechanical contract (check_genus-style — never an LLM), and assembles the filled
nodes into one `content` block-spec that passes `close.check_genus`.

Slice 1 covers ONLY: outline-from-seed, per-node lifecycle state, injected fill, the mechanical
contract gate, and assembly. The scoped LLM review stack and the living split/merge outline are
slices 2-3 and are NOT exercised here.

The load-bearing guarantees under test (mirroring tests/test_excavate.py):
  - OFF (dark default) is a true no-op AND never spends a token (complete_fn untouched).
  - a seed of N findings authors a MULTI-node outline whose three-part arc (motivate → deliver
    → change-the-course) is covered, every finding assigned to exactly one node.
  - the per-node lifecycle transitions empty→draft→revised→final are pure and total.
  - the mechanical gate flags a node whose assigned finding was not discharged, and an empty node.
  - assembly of the filled nodes is a `content` spec that passes close.check_genus.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import conductor  # noqa: E402
import close  # noqa: E402


# A realistic excavate seed (the shape tools/excavate.py emits): findings + residuals.
_SEED = {
    "findings": [
        {"claim": "store cost rises with corpus size", "citation": "p.4 fig.2",
         "bears_on": "the read:write bet", "probe": "surprise"},
        {"claim": "nothing forgets by default", "citation": "sec.3",
         "bears_on": "the eviction rail", "probe": "contradiction"},
        {"claim": "the briefing re-derives core memory", "citation": "Letta docs",
         "bears_on": "the field frame", "probe": "lineage"},
    ],
    "residuals": ["is the lag live at 50 entities?"],
    "enabled": True,
    "passthrough": False,
}
_OBJECTIVE = "spec the dashboard read panels off the briefing registry"


def _spy_filler():
    """A stub complete_fn that records its calls and returns node prose that DISCHARGES
    whatever finding claims the writer prompt carries — so the mechanical gate passes. It
    echoes every `claim` substring it sees in the prompt, which is exactly what the gate
    scans for (the offline analogue of a writer that developed its assigned findings)."""
    calls = {"count": 0, "prompts": []}

    def complete_fn(prompt):
        calls["count"] += 1
        calls["prompts"].append(prompt)
        # Echo back the assigned claims so the node discharges them, plus a derivation/boundary/
        # lineage marker so the assembled whole clears the rich-rite floor.
        claims = [ln for ln in prompt.splitlines() if ln.strip()]
        body = ("Because the evidence shows it, it follows that " + " ".join(claims) +
                " — what i don't know: the open question of scale; this builds on prior work.")
        return body

    complete_fn.calls = calls
    return complete_fn


class EnabledFlag(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(conductor.enabled(env={}))

    def test_truthy_variants_on(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            self.assertTrue(conductor.enabled(env={"EDGE_CONDUCTOR": v}), v)

    def test_falsy_variants_off(self):
        for v in ("", "0", "false", "no", "off"):
            self.assertFalse(conductor.enabled(env={"EDGE_CONDUCTOR": v}), v)


class DarkByDefault(unittest.TestCase):
    def test_off_is_passthrough_and_spends_nothing(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=False)
        self.assertFalse(result["enabled"])
        self.assertTrue(result["passthrough"])
        self.assertIsNone(result["content"])
        self.assertEqual(spy.calls["count"], 0, "OFF must never call the model")


class OutlineFromSeed(unittest.TestCase):
    def test_n_findings_author_a_multinode_outline(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        # multi-node: more than the bare three-part arc when there are several findings
        self.assertGreater(len(nodes), 3, "N findings should fan into a multi-node outline")
        for n in nodes:
            self.assertEqual(n["status"], "empty")
            self.assertIn("contract", n)
            self.assertIn("intent", n["contract"])
            self.assertIn("finding_ids", n["contract"])

    def test_three_part_arc_is_covered(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        roles = {n["role"] for n in nodes}
        self.assertEqual(roles, set(conductor.ARC_ROLES),
                         "the outline must cover motivate, deliver, and change-the-course")

    def test_every_finding_assigned_exactly_once(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        assigned = [fid for n in nodes for fid in n["contract"]["finding_ids"]]
        all_ids = [conductor.finding_id(i) for i in range(len(_SEED["findings"]))]
        self.assertEqual(sorted(assigned), sorted(all_ids))
        self.assertEqual(len(assigned), len(set(assigned)), "no finding assigned twice")

    def test_empty_seed_still_authors_the_arc(self):
        nodes = conductor.author_outline({"findings": [], "residuals": []}, _OBJECTIVE)
        roles = {n["role"] for n in nodes}
        self.assertEqual(roles, set(conductor.ARC_ROLES))


class LifecycleState(unittest.TestCase):
    """empty → draft → revised → final — pure, total transitions."""

    def test_forward_transitions(self):
        self.assertEqual(conductor.advance("empty"), "draft")
        self.assertEqual(conductor.advance("draft"), "revised")
        self.assertEqual(conductor.advance("revised"), "final")

    def test_final_is_terminal(self):
        self.assertEqual(conductor.advance("final"), "final")

    def test_unknown_status_raises(self):
        with self.assertRaises(ValueError):
            conductor.advance("bogus")

    def test_fill_drives_empty_to_draft(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler()
        filled = conductor.fill_node(nodes[0], _SEED, _OBJECTIVE, spy)
        self.assertEqual(filled["status"], "draft")
        self.assertEqual(spy.calls["count"], 1)
        self.assertTrue(filled["blocks"], "a filled node carries content blocks")


class MechanicalGate(unittest.TestCase):
    """Deterministic per-node contract gate (check_genus-style) — never an LLM."""

    def test_discharged_node_has_no_violations(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler()
        # fill the deliver node that owns at least one finding
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        filled = conductor.fill_node(deliver, _SEED, _OBJECTIVE, spy)
        self.assertEqual(conductor.contract_gate(filled, _SEED), [])

    def test_undischarged_finding_is_flagged(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        # a node "filled" with prose that never develops the assigned finding
        starved = {**deliver, "status": "draft",
                   "blocks": [{"type": "paragraph", "text": "unrelated filler prose"}]}
        violations = conductor.contract_gate(starved, _SEED)
        self.assertTrue(violations, "an undischarged assigned finding must be flagged")
        first_claim = _SEED["findings"][deliver["contract"]["finding_ids"][0]
                                         if isinstance(deliver["contract"]["finding_ids"][0], int)
                                         else 0]
        # the violation names the undischarged finding
        self.assertTrue(any("finding" in v.lower() for v in violations), violations)

    def test_empty_node_is_flagged(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        empty = {**nodes[0], "status": "draft", "blocks": []}
        violations = conductor.contract_gate(empty, _SEED)
        self.assertTrue(any("empty" in v.lower() or "non-empty" in v.lower() for v in violations),
                        violations)


class Assembly(unittest.TestCase):
    """The filled nodes assemble into a `content` spec that passes close.check_genus."""

    def test_assembled_content_passes_check_genus(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["passthrough"])
        # one fill call per node
        self.assertEqual(spy.calls["count"], len(result["outline"]))
        content = result["content"]
        self.assertIn("sections", content)
        # wrap in the artefato fields the seed/producer supplies (cites with an outside frame,
        # intent, distills) — the conductor owns `content`; check_genus reads the whole.
        artefato = {
            "slug": "conductor-smoke",
            "content": content,
            "intent": _OBJECTIVE,
            "cites": [{"ref": "Letta docs", "kind": "mundo", "relevant": True,
                       "snippet": "core memory is always-in-context working memory"}],
            "proposes": [{"body": "spec the read panels off the registry", "kind": "thread"}],
            "distills": ["cluster:briefing"],
        }
        self.assertEqual(close.check_genus(artefato), [])

    def test_all_nodes_reach_final(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True)
        self.assertTrue(all(n["status"] == "final" for n in result["outline"]),
                        "every gated node should be driven to final")


class EnvPathDefault(unittest.TestCase):
    """The is_enabled=None path actually consults EDGE_CONDUCTOR (the production wiring)."""

    def setUp(self):
        self._saved = os.environ.get("EDGE_CONDUCTOR")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("EDGE_CONDUCTOR", None)
        else:
            os.environ["EDGE_CONDUCTOR"] = self._saved

    def test_env_off_is_passthrough_no_spend(self):
        spy = _spy_filler()
        os.environ["EDGE_CONDUCTOR"] = "off"
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy)  # env decides
        self.assertTrue(result["passthrough"])
        self.assertEqual(spy.calls["count"], 0)

    def test_env_on_runs(self):
        spy = _spy_filler()
        os.environ["EDGE_CONDUCTOR"] = "1"
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy)
        self.assertTrue(result["enabled"])
        self.assertGreater(spy.calls["count"], 0)


if __name__ == "__main__":
    unittest.main()
