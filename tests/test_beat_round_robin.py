"""Story S12 — the beat is a PURE round-robin scheduler (ADR-0012).

Judgment is evacuated to the skill (amends ADR-0004): the beat carries ONLY rotation state.
`tools/_beat.next_producer(roster, state_path)` advances a persisted cursor strictly — no
queue-jump, no judgment. Given the roster ["report","map","plan"] and a fresh cursor, successive
calls return report -> map -> plan -> report (wrap). The cursor file path is injectable for tests.

The SKILL.md companion test pins the prose: theme-judgment ("choose one Worthwhile theme") is
evacuated from the beat, and the close is delegated to the shared pipeline at the skill's exit.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "beat" / "SKILL.md"
sys.path.insert(0, str(REPO / "tools"))
import _beat  # noqa: E402

ROSTER = ["report", "map", "plan"]


class RotationIsStrictAndStateful(unittest.TestCase):
    """The producer roster is round-robined strictly: a fresh cursor yields report, then map
    (stateful — the second call advances), then plan, then wraps to report. No queue-jump, no
    judgment — the moment never picks; the cursor just advances. State path is injectable."""

    def test_successive_calls_advance_strictly_and_wrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cursor = Path(tmp) / "beat" / "cursor.json"
            self.assertEqual(_beat.next_producer(ROSTER, cursor), "report")
            self.assertEqual(_beat.next_producer(ROSTER, cursor), "map")
            self.assertEqual(_beat.next_producer(ROSTER, cursor), "plan")
            self.assertEqual(_beat.next_producer(ROSTER, cursor), "report")  # wraps


class BeatSkillCarriesOnlyRotationNotJudgment(unittest.TestCase):
    """ADR-0012: theme-judgment is evacuated from the beat to the skill, and the close is
    delegated to the shared pipeline at the skill's exit. Grep the SKILL prose for both."""

    def setUp(self):
        self.assertTrue(SKILL.exists(), f"missing {SKILL}")
        self.text = SKILL.read_text(encoding="utf-8")
        self.lower = self.text.lower()

    def test_theme_judgment_is_evacuated(self):
        self.assertNotIn("choose one Worthwhile theme", self.text)

    def test_references_the_shared_pipeline_and_close_at_exit(self):
        self.assertIn("skills/_shared/pipeline.md", self.lower)
        self.assertIn("exit", self.lower)


if __name__ == "__main__":
    unittest.main(verbosity=2)
