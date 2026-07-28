"""Regime nodes (Genesis/Objective/Direction) are keyed group×agent so N agents can share one
corpus group while each keeps its own spine. Pinned as module-level query constants (the
test_recall_brief idiom: guards live in constants, testable as interfaces). Legacy single-agent
nodes carry no `agent` — the CLAIM migrates them to the running install idempotently, and the
spine read coalesces so recall never goes dark between upgrade and first sweep.
"""
import inspect
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import publisher  # noqa: E402
import recall  # noqa: E402


class BackboneKeyedByAgent(unittest.TestCase):
    def test_regime_merges_carry_the_agent_key(self):
        for const in (publisher.BACKBONE_GENESIS, publisher.BACKBONE_OBJECTIVE,
                      publisher.BACKBONE_DIRECTION):
            self.assertIn("agent:$a", const, f"regime MERGE must key by agent: {const}")

    def test_claim_migrates_legacy_nodes(self):
        self.assertIn("n.agent IS NULL", publisher.BACKBONE_CLAIM)
        self.assertIn("SET n.agent=$a", publisher.BACKBONE_CLAIM)

    def test_anchors_rebuild_only_touches_own_regime(self):
        self.assertIn("agent:$a", publisher.BACKBONE_ANCHORS_CLEAR,
                      "the DESTRUCTIVE anchors clear must never delete another agent's steers")

    def test_serves_sweep_links_own_or_unclaimed_artefatos_only(self):
        self.assertIn("coalesce(a.agent,$a)=$a", publisher.BACKBONE_SERVES_SWEEP)

    def test_project_backbone_uses_the_constants(self):
        src = inspect.getsource(publisher._project_backbone)
        for name in ("BACKBONE_CLAIM", "BACKBONE_GENESIS", "BACKBONE_OBJECTIVE",
                     "BACKBONE_ANCHORS_CLEAR", "BACKBONE_DIRECTION"):
            self.assertIn(name, src, f"_project_backbone must run the pinned constant {name}")


class SpineReadFiltersByAgent(unittest.TestCase):
    def test_spine_query_coalesces_agent(self):
        # coalesce: a legacy node (agent null) still answers its sole install pre-claim
        self.assertIn("coalesce(gen.agent,$agent)=$agent", recall.SPINE_QUERY)
        self.assertIn("coalesce(o.agent,$agent)=$agent", recall.SPINE_QUERY)
        self.assertIn("coalesce(d.agent,$agent)=$agent", recall.SPINE_QUERY)


class ArtefatoProvenance(unittest.TestCase):
    def test_project_artefato_stamps_the_author_agent(self):
        src = inspect.getsource(publisher.project_artefato)
        self.assertIn("a.agent=coalesce(a.agent,$agent)", src,
                      "shared corpus: every Artefato written must carry who authored it")


if __name__ == "__main__":
    unittest.main()
