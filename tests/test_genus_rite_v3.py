"""Genus rite v4 is roster-wide, not report-specific.

The 2026-07-08 report-quality experiment promoted the winning rite to the
shared Artefato genus: lineage, reader model, mechanism trace, Mundo fit/mismatch,
post-gate grounding, and fact-audit.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


class GenusRiteV4ReviewRubric(unittest.TestCase):
    def test_new_dimensions_are_in_the_shared_rubric(self):
        for dim in ("lineage_and_reader_model", "mechanism_trace", "grounding_audit"):
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

    def test_prompt_carries_the_genus_rite_to_blind_reviewers(self):
        prompt = close._build_prompt(close._REGULAR_FOCUS,
                                     {"slug": "x", "content": {}, "cites": []})
        self.assertIn("GENUS RITE V4", prompt)
        self.assertIn("concrete mechanism trace", prompt)
        self.assertIn("fit/mismatch", prompt)
        self.assertIn("numbered lineage", prompt)
        self.assertIn("maximize utility and growth", prompt)
        self.assertIn("post-gate grounder", prompt)

    def test_rubric_version_is_v4(self):
        self.assertEqual(close.GATE_RUBRIC_VERSION, "gate_rubric@4")


class SharedDocsCarryTheRite(unittest.TestCase):
    def test_scaffold_declares_the_rite_as_genus_not_report(self):
        text = (REPO / "skills/_shared/scaffold.md").read_text(encoding="utf-8")
        self.assertIn("Genus default rite v4", text)
        self.assertIn("not `report`", text)
        for phrase in ("Lineage ledger", "Reader growth model",
                       "Post-gate grounder", "Mundo deepening",
                       "numbered", "leveling", "interests"):
            self.assertIn(phrase, text)

    def test_pipeline_routes_substantive_gaps_back_to_author(self):
        text = (REPO / "skills/_shared/pipeline.md").read_text(encoding="utf-8")
        self.assertIn("genus rite v4", text)
        self.assertIn("skill-independent", text)
        self.assertIn("post-gate grounder", text)
        self.assertIn("before the final gating review", text)
        self.assertIn("fact-audit", text)


if __name__ == "__main__":
    unittest.main()
