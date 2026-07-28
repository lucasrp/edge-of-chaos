import sys
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import quente
import sessions
import sweep
from tests.test_hermes_sessions import HermesSessionsTest


class HermesPipelineTest(HermesSessionsTest):
    def test_sweep_skips_profiles_without_edge_group(self):
        planned = sweep.plan_sweep(
            project_dir=self.home, cursors={}, recent=None,
            codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual(planned, [])

    def test_quente_and_sweep_consume_hermes(self):
        (self.home / "config.yaml").write_text("edge_group: hive\n")
        with __import__("sqlite3").connect(self.db) as conn:
            now = datetime.now(timezone.utc).isoformat()
            for i in range(6, 12):
                conn.execute("INSERT INTO messages VALUES (?, 'a', 'user', ?, ?, 1)",
                             (i, "substantial operator prompt " * 20, now))
        selected, _ = quente.select_window(
            store_dir=self.home, k=2, max_age_days=None,
            codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual([m["id"] for m in selected], ["hermes:a"])

        with __import__("sqlite3").connect(self.db) as conn:
            for i in range(12, 18):
                conn.execute("INSERT INTO messages VALUES (?, 'b', 'user', ?, ?, 1)",
                             (i, "substantial operator prompt " * 20, now))
        planned = sweep.plan_sweep(
            project_dir=self.home, cursors={}, recent=None,
            codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual([p["surface"] for p in planned], ["hermes", "hermes"])
        self.assertEqual([p["profile_name"] for p in planned], ["work", "default"])
        self.assertEqual([p["edge_group"] for p in planned], ["hive", "hive"])
        self.assertEqual(planned[0]["turns"][:2], [
            sessions.Turn("human", "question"), sessions.Turn("edge", "answer")])

    def test_sweep_does_not_date_cut_hermes_history(self):
        (self.home / "config.yaml").write_text("edge_group: hive\n")
        with mock.patch.object(sweep, "_film_window_start", return_value=10**20):
            planned = sweep.plan_sweep(
                project_dir=self.home, cursors={}, recent=None,
                codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual([p["profile_name"] for p in planned], ["work", "default"])


if __name__ == "__main__":
    unittest.main()
