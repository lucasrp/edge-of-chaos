"""The Artefato genus conformance contract (Close architecture, S6, ADR-0012/0013).

The genus is the OUTPUT contract every producer's Artefato must satisfy — enforced,
not advisory. `check_genus` reads a finished artefato and returns the list of genus
violations ([] iff conformant). It pins the field shapes against the real
`eventlog.publish_artefato` + `kernel` signatures (cites / proposes / distills / intent)
and checks **visual-coverage**: quantitative/multi-value content with no visual element.

SECTIONS ARE FREE — `check_genus` never checks for a named or ordered section. Visual-
coverage is CONTENT-RELATIVE: an artefato with no quantitative material needs no visual
and must not be flagged. The shapes mirror tools/eventlog.py; the visual palette mirrors
tools/render.py.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _wellformed():
    """A fully conformant artefato: snippeted cite, bodied proposes, intent set,
    no quantitative material (so no visual is owed)."""
    return {
        "slug": "recall-report",
        "content": {
            "sections": [
                {"title": "What I found", "blocks": [
                    {"type": "paragraph", "text": "the read budget is unnamed"},
                ]},
            ],
        },
        "cites": [
            {"ref": "github:abc123", "kind": "atividade", "relevant": True,
             "snippet": "switched the cursor to a per-session watermark"},
        ],
        "proposes": [
            {"body": "name the full-read budget", "kind": "constraint"},
        ],
        "distills": ["cluster:recall"],
        "intent": "open: budget unnamed; bet: name it next beat",
    }


class GenusContractEnforced(unittest.TestCase):
    """The genus is enforced on the output: missing cite snippet, bodyless proposes,
    empty intent, and quantitative-content-without-a-visual each surface a violation;
    content with no quantitative material owes no visual; a well-formed artefato is clean."""

    def test_cite_without_snippet_is_a_violation_naming_the_cite(self):
        art = _wellformed()
        art["cites"] = [{"ref": "github:abc123", "kind": "atividade", "relevant": True}]
        violations = close.check_genus(art)
        self.assertTrue(any("github:abc123" in v for v in violations),
                        f"expected a violation naming the cite, got {violations}")

    def test_proposes_item_without_body_is_a_violation(self):
        art = _wellformed()
        art["proposes"] = [{"kind": "constraint"}]
        violations = close.check_genus(art)
        self.assertTrue(any("proposes" in v.lower() or "body" in v.lower() for v in violations),
                        f"expected a proposes/body violation, got {violations}")

    def test_empty_intent_is_a_violation(self):
        art = _wellformed()
        art["intent"] = ""
        violations = close.check_genus(art)
        self.assertTrue(any("intent" in v.lower() for v in violations),
                        f"expected an intent violation, got {violations}")

    def test_table_of_three_rows_with_no_visual_flags_visual_coverage(self):
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "table", "headers": ["metric", "value"],
             "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]}
        )
        violations = close.check_genus(art)
        self.assertIn("visual-coverage", violations)

    def test_no_quantitative_material_owes_no_visual(self):
        art = _wellformed()  # prose only, no table/metrics
        violations = close.check_genus(art)
        self.assertNotIn("visual-coverage", violations)

    def test_table_of_three_rows_with_a_visual_present_is_clean(self):
        """Content-relative: the same quantitative material is fine once a visual is present."""
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].extend([
            {"type": "table", "headers": ["metric", "value"],
             "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]},
            {"type": "metrics-grid", "items": [{"value": "0.8", "label": "recall"}]},
        ])
        violations = close.check_genus(art)
        self.assertNotIn("visual-coverage", violations)

    def test_wellformed_artefato_returns_empty(self):
        self.assertEqual(close.check_genus(_wellformed()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
