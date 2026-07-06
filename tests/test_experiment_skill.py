"""The experiment skill is a technical protocol over Roberto's native Episteme contract."""
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent


class ExperimentSkillContract(unittest.TestCase):
    def test_experiment_skill_uses_the_native_roberto_contract(self):
        text = (REPO / "skills" / "experiment" / "SKILL.md").read_text()

        self.assertIn("name: experiment", text)
        self.assertIn("technical protocol", text)
        self.assertIn("mentor in experiment mode", text)
        self.assertIn("docs/agencia/implementacao/06-experiment-skill.md", text)
        self.assertIn("cortex/schema/ontologia.yaml", text)
        self.assertIn("cortex.experiment_at", text)
        self.assertIn("cortex.experiments_at", text)
        self.assertIn("experiment_declared", text)
        self.assertIn("run_started", text)
        self.assertIn("experiment_concluded", text)

    def test_experiment_skill_requires_report_to_close(self):
        text = (REPO / "skills" / "experiment" / "SKILL.md").read_text()

        self.assertIn("An experiment is not done until a report is published", text)
        self.assertIn("reports_on", text)
        self.assertIn("experiment_curation", text)
        self.assertIn("human-readable HTML report", text)
        self.assertIn("Do not call `publisher.publish` directly", text)

    def test_experiment_skill_handles_cold_start_with_a_compact_card(self):
        text = (REPO / "skills" / "experiment" / "SKILL.md").read_text()

        self.assertIn("Cold Start", text)
        self.assertIn("Do not fake history", text)
        self.assertIn("compact experiment card", text)
        self.assertIn("It is not a cold intake form", text)
        for term in ("Experiment:", "Arm:", "Run:", "Eval:", "Observation:", "Report:"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
