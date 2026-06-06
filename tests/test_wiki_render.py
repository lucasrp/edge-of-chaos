"""wiki_render's pure projection seams — the deterministic half of the render (ADR-0005).

The wiki is a re-rendered projection of the graph. These pin the parts that need no LLM and no
graph: fact de-duplication, honoring the grill's `merged_into`, the honest cluster tag, and the
English-idiom synthesis prompt. The injected `q` stands in for the Neo4j query function.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import wiki_render  # noqa: E402


class FactsAreDedupedPreservingOrder(unittest.TestCase):
    def test_duplicate_facts_collapse_to_first_occurrence(self):
        rows = [{"f": "A"}, {"f": "A"}, {"f": "B"}]
        q = lambda c, **k: rows
        self.assertEqual(wiki_render._facts(q, "x"), ["A", "B"])


class ClustersHonorTheGrillsMerge(unittest.TestCase):
    def test_merged_into_entity_is_dropped_from_its_cluster(self):
        ents = [
            {"d": "genotype change proposal", "n": "genotype change proposal", "m": None},
            {"d": "genotype-change-proposal", "n": "genotype-change-proposal",
             "m": "genotype change proposal"},
        ]
        q = lambda c, **k: ([{"l": "Genotype workflow"}] if "l" not in k else ents)
        (label, got), = wiki_render._clusters(q, "exp004")
        self.assertEqual([e["n"] for e in got], ["genotype change proposal"])


class ClusterTagReflectsGrilledState(unittest.TestCase):
    def test_all_grilled_is_curated(self):
        self.assertEqual(wiki_render.cluster_tag(5, 5), "curated")

    def test_none_grilled_is_draft(self):
        self.assertEqual(wiki_render.cluster_tag(0, 4), "draft")

    def test_partial_shows_progress(self):
        self.assertEqual(wiki_render.cluster_tag(3, 5), "3/5 grilled")


class SynthesisPromptPinsEnglishKeepingCoinedTerms(unittest.TestCase):
    def test_prompt_pins_english_but_preserves_the_coined_idiom(self):
        p = wiki_render.synthesis_prompt("Beat lifecycle", ["assemble blocks the beat"], "IDIOM-X", "VOCAB-Y")
        self.assertIn("English", p)               # output language pinned
        self.assertIn("not their language", p)    # idiom = terminology, not language
        self.assertIn("verbatim", p)              # coined terms kept untranslated
        self.assertIn("IDIOM-X", p)               # the idiom flows through
        self.assertIn("VOCAB-Y", p)               # the projects' vocabulary flows through
        self.assertIn("assemble blocks the beat", p)
        self.assertIn("Beat lifecycle", p)


if __name__ == "__main__":
    unittest.main()
