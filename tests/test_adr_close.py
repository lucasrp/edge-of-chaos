"""ADRs 0012 + 0013 — the Close-architecture decisions, captured as house-format ADRs.

The Close rewrite (Story S4) records two architectural decisions:

  * 0012 (lifecycle) — the beat is a pure round-robin scheduler; theme-choice and
    production move into the producer skill; the whole dispatch is ONE shared
    pipeline (pre-dispatch -> producer-loop -> close); this AMENDS ADR-0004 by
    evacuating judgment from the beat, and honors ADR-0008 (the close at the
    skill's exit observes the pull-at-open digestion contract).

  * 0013 (verification) — verification is BLIND by evidence-and-session; two blind
    gates on the final text; the gate checks a PROPERTY anywhere, not a named
    SECTION; the 9-dim legacy review is cut to 7 KEPT dims with two DROPPED
    (structural_completeness, storytelling).

These tests pin that both ADRs exist and state their load-bearing decisions, in the
house format (sibling cross-references, no new glossary terms). Content is matched
case-insensitively.
"""
import unittest
from pathlib import Path

ADR = Path(__file__).resolve().parent.parent / "docs" / "adr"
ADR_0012 = ADR / "0012-lifecycle-round-robin-beat-one-shared-pipeline.md"
ADR_0013 = ADR / "0013-verification-is-blind-property-not-section.md"

# The 7 dimensions KEPT by 0013 (genus / universal).
KEPT_DIMS = (
    "content_depth",
    "feynman_method",
    "intellectual_honesty",
    "didactic_clarity",
    "internal_consistency",
    "visualization",
    "writing_quality",
)
# The 2 dimensions DROPPED by 0013 (welded to report-form).
DROPPED_DIMS = ("structural_completeness", "storytelling")


class ADRsExistAndStateKeyDecisions(unittest.TestCase):
    def test_both_adrs_exist(self):
        self.assertTrue(ADR_0012.exists(), f"missing {ADR_0012}")
        self.assertTrue(ADR_0013.exists(), f"missing {ADR_0013}")

    def test_0012_states_lifecycle_decision(self):
        text = ADR_0012.read_text().lower()
        for token in ("round-robin", "pipeline", "amends", "0004", "0008"):
            self.assertIn(token, text, f"0012 missing key term: {token!r}")

    def test_0013_states_verification_decision(self):
        text = ADR_0013.read_text().lower()
        for token in ("property", "blind"):
            self.assertIn(token, text, f"0013 missing key term: {token!r}")
        for dim in KEPT_DIMS:
            self.assertIn(dim, text, f"0013 missing KEPT dim: {dim!r}")
        for dim in DROPPED_DIMS:
            self.assertIn(dim, text, f"0013 missing DROPPED dim: {dim!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
