"""Red-green tests for the structural Artifact Rite validator (candidate #2a).

validate_rite is a pure function: a loaded YAML spec in, a list of violation
codes out (empty == conforms). It is the deterministic form gate; merit stays
with the LLM review gate.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools._shared.artifact_rite import validate_rite  # noqa: E402


def valid_spec():
    return {
        "executive_summary": ["summary point"],
        "metrics": [{"value": "1", "label": "thing"}],
        "bibliography": [{"title": "a source"}],
        "sections": [
            {"role": "lineage", "title": "Linhagem", "blocks": [{"type": "paragraph", "text": "x"}]},
            {"title": "Body", "blocks": [{"type": "bar-chart", "title": "c", "items": []}]},
            {"role": "gaps", "title": "O que Não Sei", "blocks": [{"type": "paragraph", "text": "x"}]},
            {"role": "glossary", "title": "Glossário", "blocks": [{"type": "glossary", "terms": []}]},
        ],
    }


class ValidateRite(unittest.TestCase):
    def test_valid_spec_passes(self):
        self.assertEqual(validate_rite(valid_spec()), [])

    def test_missing_executive_summary(self):
        s = valid_spec(); del s["executive_summary"]
        self.assertIn("missing_executive_summary", validate_rite(s))

    def test_missing_metrics(self):
        s = valid_spec(); del s["metrics"]
        self.assertIn("missing_metrics", validate_rite(s))

    def test_missing_bibliography(self):
        s = valid_spec(); s["bibliography"] = []
        self.assertIn("missing_bibliography", validate_rite(s))

    def test_missing_lineage(self):
        s = valid_spec(); s["sections"][0].pop("role")
        codes = validate_rite(s)
        self.assertIn("missing_lineage", codes)

    def test_lineage_not_first(self):
        s = valid_spec()
        s["sections"][0], s["sections"][1] = s["sections"][1], s["sections"][0]
        self.assertIn("lineage_not_first", validate_rite(s))

    def test_missing_gaps(self):
        s = valid_spec(); s["sections"][2].pop("role")
        self.assertIn("missing_gaps", validate_rite(s))

    def test_gaps_not_penultimate(self):
        s = valid_spec()
        # move gaps to first-ish position (index 1) so it's no longer penultimate
        gaps = s["sections"].pop(2)
        s["sections"].insert(1, gaps)
        self.assertIn("gaps_not_penultimate", validate_rite(s))

    def test_missing_glossary(self):
        s = valid_spec(); s["sections"][3].pop("role")
        self.assertIn("missing_glossary", validate_rite(s))

    def test_glossary_not_last(self):
        s = valid_spec()
        extra = {"title": "After", "blocks": [{"type": "paragraph", "text": "x"}]}
        s["sections"].append(extra)  # glossary no longer last
        self.assertIn("glossary_not_last", validate_rite(s))

    def test_no_svg(self):
        s = valid_spec()
        s["sections"][1]["blocks"] = [{"type": "paragraph", "text": "x"}]
        self.assertIn("no_svg", validate_rite(s))

    def test_svg_via_raw_html_counts(self):
        s = valid_spec()
        s["sections"][1]["blocks"] = [{"type": "raw-html", "html": "<svg viewBox='0 0 1 1'></svg>"}]
        self.assertNotIn("no_svg", validate_rite(s))

    def test_line_chart_counts_as_svg(self):
        s = valid_spec()
        s["sections"][1]["blocks"] = [{"type": "line-chart", "points": []}]
        self.assertNotIn("no_svg", validate_rite(s))


if __name__ == "__main__":
    unittest.main()
