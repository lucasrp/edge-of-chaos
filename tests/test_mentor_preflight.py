import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mentor_preflight


class MentorPreflightTest(unittest.TestCase):
    def test_collect_reuses_canonical_hot_window(self):
        selected = [
            {"id": "hermes:s1", "surface": "hermes", "path": "p1", "last": "2026-07-30T12:00:00Z"},
            {"id": "hermes:s2", "surface": "hermes", "path": "p2", "last": "2026-07-29T12:00:00Z"},
            {"id": "hermes:s3", "surface": "hermes", "path": "p3", "last": "2026-07-28T12:00:00Z"},
        ]
        turns = {
            "p1": [mock.Mock(role="human", text=mentor_preflight.quente.SCAFFOLDING[0] + " wrapper"),
                   mock.Mock(role="human", text="goal one"), mock.Mock(role="edge", text="outcome one")],
            "p2": [mock.Mock(role="human", text="goal two"), mock.Mock(role="edge", text="outcome two")],
            "p3": [mock.Mock(role="human", text="goal three"), mock.Mock(role="edge", text="outcome three")],
        }
        with mock.patch.object(mentor_preflight.quente, "select_window", return_value=(selected, "start")) as select, \
             mock.patch.object(mentor_preflight.sessions, "read_turns", side_effect=lambda path, surface: turns[path]), \
             mock.patch.object(mentor_preflight.recall, "compose_mentee_persona_brief", return_value="level"), \
             mock.patch.object(mentor_preflight.recall, "compose_portfolio_recall_brief", return_value="portfolio"), \
             mock.patch.object(mentor_preflight.cortex, "communities", return_value=[{"name": "community"}]):
            result = mentor_preflight.collect(group="default", db_path="state.db")

        select.assert_called_once_with(k=3, max_age_days=7, hermes_dir="state.db")
        self.assertEqual([w["session_id"] for w in result["recent_hermes_work"]], ["hermes:s1", "hermes:s2", "hermes:s3"])
        self.assertEqual(result["recent_hermes_work"][0]["user_goal"], "goal one")
        self.assertEqual(result["recent_hermes_work"][0]["outcome"], "outcome one")
        self.assertNotIn("front_id", result["recent_hermes_work"][0])
        self.assertEqual(result["leveling"], "level")
        self.assertEqual(result["portfolio_recall"], "portfolio")
        self.assertEqual(result["communities"], [{"name": "community"}])

    def test_work_from_window_preserves_distinct_sessions_without_title_dedup(self):
        selected = [
            {"id": "hermes:a", "surface": "hermes", "path": "a", "last": "1"},
            {"id": "hermes:b", "surface": "hermes", "path": "b", "last": "2"},
        ]
        same = [mock.Mock(role="human", text="same goal"), mock.Mock(role="edge", text="same outcome")]
        with mock.patch.object(mentor_preflight.sessions, "read_turns", return_value=same):
            work = mentor_preflight.work_from_window(selected)
        self.assertEqual([w["session_id"] for w in work], ["hermes:a", "hermes:b"])


if __name__ == "__main__":
    unittest.main()
