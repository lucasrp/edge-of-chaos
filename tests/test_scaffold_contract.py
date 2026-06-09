"""Story S10 — the shared producer scaffold (skills/_shared/scaffold.md).

The scaffold is the producer-loop every producer-skill inherits (ADR-0012). It defines
three ROLE-defined slots — `gather-grounding` (loop1: explorers -> evidence),
`converge` (loop2 critic), `diverge` (loop2 serendipity) — plus the loop structure and
the context-denial ladder (ADR-0013). The load-bearing invariant this test pins:

  * the slots are ROLE-defined, NOT report-defined — the scaffold names the role, never
    the report-specifics. Report-welding (explorer=URL, cite=link, named-section mandates)
    lives in each producer skill's mapping, NEVER in the scaffold;
  * loop1/loop2 structure and the full 5-stage context-denial ladder are stated;
  * the rename is honored: "evidence", never "insumos".

Grep-based: the doc is prose, so the test reads it and asserts presence/absence of the
load-bearing tokens (case-insensitive for the prose; absence checks are case-insensitive
too so a capitalized welding still fails).
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAFFOLD = REPO / "skills" / "_shared" / "scaffold.md"

# The 3 ROLE slot-names the scaffold defines (role-defined, not report-defined).
SLOT_ROLES = ("gather-grounding", "converge", "diverge")

# The 5 stages of the context-denial ladder (ADR-0013), in rungs.
LADDER_STAGES = ("producer", "serendipity", "critic", "reviewers", "publisher")

# Report-welding that MUST be absent — the scaffold must stay non-procrusto: no report
# semantics hard-coded into a slot (explorer=URL, cite=link), and no named-section mandate.
FORBIDDEN_WELDING = ("explorer=url", "cite=link")
# Section-mandate wording the scaffold must NOT carry (sections are FREE; a producer's
# mapping owns any section choice, never the shared scaffold).
FORBIDDEN_SECTION_MANDATES = (
    "required section",
    "mandatory section",
    "section is required",
    "named section",
)


class ScaffoldSlotsAreRoleNotReportDefined(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCAFFOLD.exists(), f"missing {SCAFFOLD}")
        self.text = SCAFFOLD.read_text(encoding="utf-8")
        self.lower = self.text.lower()

    def test_defines_the_three_role_slots(self):
        for role in SLOT_ROLES:
            self.assertIn(role, self.lower, f"scaffold missing role slot: {role!r}")

    def test_states_role_defined_not_report_defined(self):
        self.assertIn("role-defined", self.lower)
        self.assertIn("report-defined", self.lower)

    def test_states_the_loop_structure(self):
        self.assertIn("loop1", self.lower)
        self.assertIn("loop2", self.lower)
        # loop1 = explorers -> evidence; loop2 = critic converges via a `ship` verdict;
        # serendipity advisory, may reopen loop1 bounded (references run_loop2).
        for token in ("explorer", "evidence", "critic", "serendipity",
                      "ship", "loop2_max_reopens", "run_loop2"):
            self.assertIn(token, self.lower, f"scaffold missing loop token: {token!r}")

    def test_states_the_full_context_denial_ladder(self):
        for stage in LADDER_STAGES:
            self.assertIn(stage, self.lower, f"ladder missing stage: {stage!r}")
        # Freshness is evidence-vs-reasoning, not cites-vs-no-cites (ADR-0013).
        self.assertIn("freshness", self.lower)

    def test_absent_report_welding(self):
        for welding in FORBIDDEN_WELDING:
            self.assertNotIn(welding, self.lower,
                             f"scaffold welds report semantics: {welding!r}")

    def test_absent_section_mandates(self):
        for mandate in FORBIDDEN_SECTION_MANDATES:
            self.assertNotIn(mandate, self.lower,
                             f"scaffold mandates a section: {mandate!r}")

    def test_uses_evidence_not_insumos(self):
        self.assertIn("evidence", self.lower)
        self.assertNotIn("insumos", self.lower)

    def test_states_the_introspective_memory_passes(self):
        # #28: the producer's THIRD relation — its own memory (the graph), reached by the
        # producer itself (rung 1), not by an explorer. The loop must wire BOTH passes and
        # point at the manual, so the capability cannot go dormant (the g.search() cautionary
        # tale). Grep the load-bearing tokens.
        for token in ("recall-before-act", "project-after-publish", "memory.md"):
            self.assertIn(token, self.lower, f"scaffold missing memory token: {token!r}")
        # recall is the producer's own memory — denied to the deeper rungs (rung-1 only).
        self.assertIn("recall", self.lower)

    def test_states_agentic_grounding_how_no_primitive(self):
        # The actionable HOW (corrects the "materialize a primitive" misframe a beat fell into):
        # explorers ground via the source specs + source-roadmap, agentically, keys loaded; there is
        # no per-source primitive (ADR-0001) and an explorer never waits for one.
        for token in ("source-roadmap", "agentically", "adr-0001", "primitive", "keys"):
            self.assertIn(token, self.lower, f"scaffold missing grounding-how token: {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
