"""The mentor rename: `mentor` is the canonical skill, `grill` is legacy compatibility."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_config  # noqa: E402
import cortex_mcp  # noqa: E402
import producer_descriptor  # noqa: E402
import publisher  # noqa: E402


class MentorIsTheCanonicalSkillName(unittest.TestCase):
    def test_mentor_skill_is_canonical_and_grill_is_an_alias(self):
        mentor = (REPO / "skills" / "mentor" / "SKILL.md").read_text()
        grill = (REPO / "skills" / "grill" / "SKILL.md").read_text()

        self.assertIn("name: mentor", mentor)
        self.assertIn("Invoked as /{prefix}-mentor", mentor)
        self.assertIn("`skill`='mentor'", mentor)
        self.assertIn("skills/mentor/SKILL.md", grill)
        self.assertIn("legacy alias", grill.lower())

    def test_mentor_requires_split_home_safe_cortex_recall(self):
        mentor = (REPO / "skills" / "mentor" / "SKILL.md").read_text()
        self.assertIn("$EDGE_HOME/tools/edge-python", mentor)
        self.assertIn("compose_portfolio_recall_brief", mentor)
        self.assertIn("**Hard gate:**", mentor)

    def test_mentor_owns_the_live_experiment_transition(self):
        mentor = (REPO / "skills" / "mentor" / "SKILL.md").read_text()

        self.assertIn("Experiment is a technical protocol the mentor may invoke", mentor)
        self.assertIn("not a second conversational agent", mentor)
        self.assertIn("mentor in experiment mode", mentor)
        self.assertIn("the experiment schema", mentor)
        for term in ("`Experiment`", "`Arm`", "`Run`", "`Eval`", "`Observation`", "`Report`"):
            self.assertIn(term, mentor)
        self.assertIn("Preserve contradictions", mentor)
        self.assertIn("curated interpretation", mentor)

    def test_runtime_allowlists_accept_mentor_and_legacy_grill(self):
        self.assertIn("mentor", publisher.PRODUCER_ROSTER)
        self.assertIn("grill", publisher.PRODUCER_ROSTER)
        self.assertIn("mentor", producer_descriptor.DESCRIPTORS)
        self.assertIn("grill", producer_descriptor.DESCRIPTORS)
        self.assertIn("mentor", cortex_config.GRANTED_SUBJECTS)
        self.assertIn("mentor", cortex_mcp.GRANTED_SUBJECTS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
