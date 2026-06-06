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


class SourceYieldAgendaSurfacesPerSourceYield(unittest.TestCase):
    """ADR-0009: the grill consults the source-feedback hypothesis tier via grill_lint — per-source
    yield → a hypothesis agenda item ("source X yielded N cites, mean sim 0.YZ — relevant?"). A pure
    helper over the yield dict (eventlog.source_yield_at's output), unit-testable WITHOUT a driver."""

    def test_yield_dict_becomes_agenda_items(self):
        ybr = {"github:abc": {"ref": "github:abc", "kind": "atividade",
                              "count": 2, "mean_similarity": 0.81}}
        agenda = grill_lint.source_yield_agenda(ybr)
        self.assertEqual(len(agenda), 1)
        harm, kind, belief, ask = agenda[0]
        self.assertEqual(kind, "source-yield")
        self.assertIn("github:abc", belief)
        self.assertIn("2", belief)       # count surfaced
        self.assertIn("0.81", belief)    # mean similarity surfaced
        self.assertIn("relevant", ask.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
