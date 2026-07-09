"""Genus rite v6 is roster-wide, not report-specific.

The shared Artefato genus carries lineage, reader model, mechanism trace, Mundo
fit/mismatch, old-edge equivalent draft, post-gate grounding, visible rewrite delta,
fact-audit, and canonical form grammar.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


class GenusRiteV6ReviewRubric(unittest.TestCase):
    def test_new_dimensions_are_in_the_shared_rubric(self):
        for dim in ("lineage_and_reader_model", "mechanism_trace", "grounding_audit",
                    "old_edge_grounded_rite", "canonical_form_grammar"):
            self.assertIn(dim, close.DIMENSIONS)
            self.assertIn(dim, close.DIMENSION_WEIGHTS)

    def test_lineage_dimension_is_visible_not_hidden_metadata(self):
        dim = close.DIMENSIONS["lineage_and_reader_model"].lower()
        self.assertIn("visible", dim)
        self.assertIn("inherits", dim)
        self.assertIn("reject", dim)
        self.assertIn("numbered", dim)
        self.assertIn("leveling", dim)
        self.assertIn("interests", dim)
        self.assertIn("growth", dim)
        self.assertIn("hidden publish metadata is not lineage", dim)

    def test_mechanism_dimension_requires_a_concrete_trace(self):
        dim = close.DIMENSIONS["mechanism_trace"].lower()
        self.assertIn("worked example", dim)
        self.assertIn("how the result happened", dim)
        self.assertIn("decorative", dim)

    def test_grounding_audit_dimension_blocks_external_overclaim(self):
        dim = close.DIMENSIONS["grounding_audit"].lower()
        self.assertIn("fit/mismatch", dim)
        self.assertIn("do not validate", dim)
        self.assertIn("studies", dim)
        self.assertIn("best practices", dim)
        self.assertIn("where the topic deserves", dim)
        self.assertIn("magnitude", dim)
        self.assertIn("overextended external grounding is a strike", dim)

    def test_old_edge_grounded_rite_is_the_promoted_default(self):
        dim = close.DIMENSIONS["old_edge_grounded_rite"].lower()
        self.assertIn("old-edge equivalent", dim)
        self.assertIn("actionable grounding tasks", dim)
        self.assertIn("directed post-gate", dim)
        self.assertIn("grounding effect is visible", dim)
        self.assertIn("what changed", dim)

    def test_canonical_form_grammar_is_part_of_the_genus(self):
        dim = close.DIMENSIONS["canonical_form_grammar"].lower()
        self.assertIn("canonical house form", dim)
        self.assertIn("live question", dim)
        self.assertIn("lineage ledger", dim)
        self.assertIn("concrete mechanism trace", dim)
        self.assertIn("comparison-table", dim)
        self.assertIn("gap-table", dim)
        self.assertIn("next-steps-grid", dim)

    def test_prompt_carries_the_genus_rite_to_blind_reviewers(self):
        prompt = close._build_prompt(close._REGULAR_FOCUS,
                                     {"slug": "x", "content": {}, "cites": []})
        self.assertIn("GENUS RITE V6", prompt)
        self.assertIn("concrete mechanism trace", prompt)
        self.assertIn("fit/mismatch", prompt)
        self.assertIn("numbered lineage", prompt)
        self.assertIn("maximize utility and growth", prompt)
        self.assertIn("old-edge-with-grounding movement", prompt)
        self.assertIn("visible rewrite delta", prompt)
        self.assertIn("canonical-form miss", prompt)
        self.assertIn("canonical house journey", prompt)
        self.assertIn("next-steps-grid", prompt)

    def test_rubric_version_is_v6(self):
        self.assertEqual(close.GATE_RUBRIC_VERSION, "gate_rubric@6")


class SharedDocsCarryTheRite(unittest.TestCase):
    def test_scaffold_declares_the_rite_as_genus_not_report(self):
        text = (REPO / "skills/_shared/scaffold.md").read_text(encoding="utf-8")
        self.assertIn("Genus default rite v6", text)
        self.assertIn("not `report`", text)
        self.assertIn("docs/genus-rite-v6-canonical-form.md", text)
        for phrase in ("Lineage ledger", "Reader growth model",
                       "Post-gate grounder", "Mundo deepening",
                       "Old-edge equivalent first draft", "Actionable gap gate",
                       "Rewrite with visible grounding effect",
                       "canonical form grammar", "canonical block palette",
                       "numbered", "leveling", "interests"):
            self.assertIn(phrase, text)

    def test_canonical_rite_doc_preserves_the_experiment_content(self):
        text = (REPO / "docs/genus-rite-v6-canonical-form.md").read_text(encoding="utf-8")
        for phrase in (
            "old-edge draft -> actionable gap gate -> directed grounder",
            "The Canonical Form Grammar",
            "The Canonical Block Palette",
            "Skill Translation Rule",
            "External sources can position a local result",
            "They do not validate local",
        ):
            self.assertIn(phrase, text)

    def test_pipeline_routes_substantive_gaps_back_to_author(self):
        text = (REPO / "skills/_shared/pipeline.md").read_text(encoding="utf-8")
        self.assertIn("genus rite v6", text)
        self.assertIn("skill-independent", text)
        self.assertIn("old-edge-with-grounding rite", text)
        self.assertIn("grounding delta is visible", text)
        self.assertIn("canonical form", text)
        self.assertIn("canonical journey", text)
        self.assertIn("before the final gating review", text)
        self.assertIn("fact-audit", text)


if __name__ == "__main__":
    unittest.main()
