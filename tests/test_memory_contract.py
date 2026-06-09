"""The introspective-memory discipline (skills/_shared/memory.md) — #28 + space-0/semantic ext.

memory.md is the prose manual the producer executes to use the edge's own graph as memory: no
deterministic CLI (recall is cognition, ADR-0001/0003). This grep-based contract pins the
load-bearing pieces so the capability cannot silently rot (the dormant g.search() cautionary tale):

  * recall-before-act AND project-after-publish are both stated;
  * space-0: method+personality are the :Genesis root the agent wakes at, the spine rooted to it;
  * semantic search of Artefatos by their own embedding (the #28 refinement, now live);
  * the log stays canonical (ADR-0006) — the graph is a best-effort projection;
  * the cluster slug trap is documented with wiki_render's canonical rule (no naive exact match).
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEMORY = REPO / "skills" / "_shared" / "memory.md"


class IntrospectiveMemoryContract(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MEMORY.exists(), f"missing {MEMORY}")
        self.lower = MEMORY.read_text(encoding="utf-8").lower()

    def test_states_both_passes(self):
        for token in ("recall-before-act", "project-after-publish"):
            self.assertIn(token, self.lower, f"memory.md missing pass: {token!r}")

    def test_space_zero_genesis_root(self):
        # method+personality are space 0 — the :Genesis node the agent wakes at; spine rooted to it.
        for token in ("space 0", ":genesis", "method", "personality"):
            self.assertIn(token, self.lower, f"memory.md missing space-0 token: {token!r}")
        self.assertTrue("grounds" in self.lower and "anchors" in self.lower,
                        "memory.md must root the spine to genesis (GROUNDS/ANCHORS)")
        # every Artefato SERVES the objective (the hub) so it is reachable from space-0 even before
        # the grill consolidates the steer it proposed.
        self.assertIn("serves", self.lower, "every Artefato must SERVE the objective (the hub)")
        self.assertIn("hub", self.lower)

    def test_backbone_rebuilds_active_anchors(self):
        # codex: the backbone sync must REBUILD the Objective's ANCHORS set each project (delete the
        # stale edges first), else a dropped/superseded Direction stays anchored and recall from
        # space-0 diverges from the canonical log.
        self.assertIn("delete r", self.lower, "memory.md must clear stale ANCHORS before re-adding")
        self.assertIn("rebuild", self.lower)

    def test_semantic_artefato_search(self):
        # semantic search of a report by its own content — the embedding on :Artefato.
        for token in ("embedding", "semantic", "text-embedding-3-small", "cosine" if "cosine" in self.lower else "cos"):
            self.assertIn(token, self.lower, f"memory.md missing semantic token: {token!r}")

    def test_log_stays_canonical(self):
        # ADR-0006: the log is truth, the graph is a best-effort projection.
        self.assertIn("adr-0006", self.lower)
        self.assertTrue("source of truth" in self.lower or "canonical" in self.lower)
        self.assertIn("best-effort", self.lower)

    def test_not_a_source(self):
        # recall is producer-side (rung 1), NOT a world source (ADR-0011).
        self.assertIn("not a source", self.lower)

    def test_cluster_slug_trap_documented(self):
        # the slug↔display mismatch + wiki_render's canonical rule (no naive exact/space-only match).
        self.assertIn("wiki_render", self.lower)
        self.assertIn("[^a-z]", self.lower)


if __name__ == "__main__":
    unittest.main(verbosity=2)
