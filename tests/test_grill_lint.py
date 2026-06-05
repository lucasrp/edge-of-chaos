"""Lint's pure core — the mechanical detection that seeds the grill agenda (CONTEXT: Lint).

Lint detects and escalates by harm potential; the rule or the mentee resolves. These pin the
detectors that need no graph: surface-variant folding (canonical-identity) and the retired-term
check (entity names the glossary moved to `_Avoid_` — a conflict with the Idiom).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import grill_lint  # noqa: E402


class NormalizeFoldsSurfaceVariants(unittest.TestCase):
    def test_separators_and_case_fold(self):
        self.assertEqual(grill_lint.normalize("genotype-change-proposal"),
                         grill_lint.normalize("genotype change proposal"))


class DuplicateGroupsAreCanonicalIdentityFailures(unittest.TestCase):
    def test_only_surface_variants_group(self):
        groups = grill_lint.duplicate_groups(
            ["genotype change proposal", "genotype-change-proposal", "Zep", "Zep/Graphiti"])
        # separator variants fold; token-different synonyms (Zep vs Zep/Graphiti) do not.
        self.assertEqual(sorted(len(g) for g in groups), [2])


class AvoidTermsAndRetired(unittest.TestCase):
    def test_avoid_parsed_and_retired_flagged(self):
        avoid = grill_lint.avoid_terms("**Mundo**:\nThe world.\n_Avoid_: coleta, source, busca")
        self.assertIn("coleta", avoid)
        self.assertEqual(set(grill_lint.retired(["Coleta", "Delta", "edge-next"], avoid)), {"Coleta"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
