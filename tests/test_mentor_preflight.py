import os
import sqlite3
import tempfile
import unittest
from unittest import mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import mentor_preflight


class MentorPreflightTests(unittest.TestCase):
    def test_collect_composes_all_sources(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(mentor_preflight.recall, "compose_portfolio_recall_brief", return_value="portfolio") as portfolio, \
                mock.patch.object(mentor_preflight, "recent_hermes_work", return_value=[{"title": "recent"}]), \
                mock.patch.object(mentor_preflight.cortex, "communities", return_value=[{"name": "community"}]) as communities:
            result = mentor_preflight.collect()
        self.assertEqual(result["group"], "default")
        self.assertEqual(result["portfolio_recall"], "portfolio")
        self.assertIn("leveling", result)
        self.assertEqual(result["recent_hermes_work"], [{"title": "recent", "front_id": "F01", "user_goal": "", "outcome": ""}])
        self.assertEqual(result["communities"], [{"name": "community"}])
        portfolio.assert_called_once_with(group="default")
        communities.assert_called_once_with("default")

    def test_recent_work_deduplicates_numbered_session_titles(self):
        with tempfile.NamedTemporaryFile() as tmp:
            db = sqlite3.connect(tmp.name)
            db.execute("CREATE TABLE sessions (id TEXT, started_at REAL, title TEXT)")
            db.execute("CREATE TABLE messages (id INTEGER, session_id TEXT, role TEXT, content TEXT, tool_name TEXT)")
            db.executemany("INSERT INTO sessions VALUES (?, ?, ?)", [("new", 900, "Steve Wake Blocked #28"), ("old", 800, "Steve Wake Blocked #27"), ("other", 700, "OnlinEstetica — Meta Ads daily check")])
            db.commit()
            work = mentor_preflight.recent_hermes_work(tmp.name, now=1000)
        self.assertEqual([item["session_id"] for item in work], ["other"])


if __name__ == "__main__":
    unittest.main()
