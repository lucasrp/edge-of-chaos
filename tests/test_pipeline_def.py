"""Story S11 — THE single shared pipeline definition (skills/_shared/pipeline.md).

The one file every producer funnels through (ADR-0012). It is prose; the testable surfaces
it names live in tools/. This test pins the load-bearing claims:

  * the three phases — pre-dispatch (assemble + delta) -> producer-loop (the scaffold) ->
    close (reviewers + publisher);
  * it names the testable modules: tools/close.py (genus + the two blind reviewers +
    run_close bounce/brake) and tools/publisher.py (atomic publish + C3 kernel);
  * the close lives at the SKILL'S EXIT — a standalone /ed-report observes the same close
    (honors ADR-0008);
  * the close-roles (reviewers, publisher) are NOT round-robinable (only producer-skills are).

Grep-based, case-insensitive: the doc is prose, so the test reads it and asserts the
load-bearing tokens are present.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINE = REPO / "skills" / "_shared" / "pipeline.md"


class PipelineHasThreePhasesAndCloseAtExit(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PIPELINE.exists(), f"missing {PIPELINE}")
        self.lower = PIPELINE.read_text(encoding="utf-8").lower()

    def test_names_the_three_phases(self):
        # pre-dispatch = assemble + delta
        self.assertIn("pre-dispatch", self.lower)
        self.assertIn("assemble", self.lower)
        self.assertIn("delta", self.lower)
        # producer-loop = the scaffold
        self.assertIn("producer-loop", self.lower)
        self.assertIn("scaffold", self.lower)
        # close = reviewers + publisher
        self.assertIn("close", self.lower)

    def test_references_the_scaffold_doc(self):
        self.assertIn("skills/_shared/scaffold.md", self.lower)

    def test_names_the_testable_modules(self):
        self.assertIn("tools/close.py", self.lower)
        self.assertIn("tools/publisher.py", self.lower)
        # close.py surfaces: genus, the two blind reviewers, run_close (bounce/brake)
        for token in ("genus", "reviewer", "run_close"):
            self.assertIn(token, self.lower, f"pipeline missing close.py surface: {token!r}")
        # publisher.py surfaces: atomic publish + the C3 kernel
        for token in ("atomic", "kernel", "c3"):
            self.assertIn(token, self.lower,
                          f"pipeline missing publisher.py surface: {token!r}")

    def test_close_lives_at_the_skill_exit(self):
        self.assertIn("exit", self.lower)
        self.assertIn("0008", self.lower)
        self.assertIn("/ed-report", self.lower)
        self.assertIn("standalone", self.lower)

    def test_close_roles_are_not_round_robinable(self):
        self.assertIn("round-robin", self.lower)
        # the close-roles (reviewers, publisher) are NOT round-robinable; only producers are.
        self.assertIn("not round-robinable", self.lower)

    def test_is_the_deyamld_publish_only_rewrite(self):
        self.assertIn("consolidate-state", self.lower)
        for token in ("de-yaml", "publish-only", "_shared/"):
            self.assertIn(token, self.lower, f"pipeline missing rewrite token: {token!r}")

    def test_uses_evidence_not_insumos(self):
        self.assertNotIn("insumos", self.lower)


if __name__ == "__main__":
    unittest.main(verbosity=2)
