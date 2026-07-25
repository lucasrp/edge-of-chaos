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


class SourceYieldAgendaIsADeltaOverTheCuratedFrontier(unittest.TestCase):
    """Slice 3 (ADR-0011): the agenda is a DELTA, not one item per source every run. A source that
    already carries a curated opinion is omitted (the converged frontier) — UNLESS fresh signal
    CONTRADICTS the curated value, in which case it re-surfaces as a `contested`/confront item for the
    mentee to retire or reaffirm (the two-way Convergence). curated[] is fold_source_feedback's tier."""

    def test_curated_source_is_omitted_from_the_agenda(self):
        ybr = {"exa": {"ref": "exa", "kind": "mundo", "count": 3, "mean_similarity": 0.72}}
        curated = [{"source": "exa", "opinion": "valued: recent-paper recall", "kind": None}]
        agenda = grill_lint.source_yield_agenda(ybr, curated=curated)
        self.assertEqual(agenda, [])  # already curated, yield consistent → nothing to grill

    def test_uncurated_source_still_surfaces_as_source_yield(self):
        ybr = {"hn": {"ref": "hn", "kind": "mundo", "count": 1, "mean_similarity": 0.55}}
        agenda = grill_lint.source_yield_agenda(ybr, curated=[])
        self.assertEqual(len(agenda), 1)
        self.assertEqual(agenda[0][1], "source-yield")

    def test_contradicted_curated_source_resurfaces_as_contested(self):
        # curated=valued, but the accruing yield has gone cold (mean sim below the threshold) → contested
        ybr = {"exa": {"ref": "exa", "kind": "mundo", "count": 4, "mean_similarity": 0.12}}
        curated = [{"source": "exa", "opinion": "valued: recent-paper recall", "kind": None}]
        agenda = grill_lint.source_yield_agenda(ybr, curated=curated)
        self.assertEqual(len(agenda), 1)
        harm, kind, belief, ask = agenda[0]
        self.assertEqual(kind, "source-contested")
        self.assertEqual(harm, "HIGH")
        self.assertIn("exa", belief)
        self.assertIn("contradict", (belief + ask).lower())

    def test_curated_source_matches_ref_by_source_prefix(self):
        # curated keyed by source name; yield keyed by ref like "github:abc" — match on the prefix.
        ybr = {"github:abc": {"ref": "github:abc", "kind": "atividade",
                              "count": 2, "mean_similarity": 0.81}}
        curated = [{"source": "github", "opinion": "valued: the mentee's own commits", "kind": None}]
        agenda = grill_lint.source_yield_agenda(ybr, curated=curated)
        self.assertEqual(agenda, [])  # github is curated, yield healthy → omitted


if __name__ == "__main__":
    unittest.main(verbosity=2)
