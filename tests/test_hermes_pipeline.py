import sys
import unittest
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
            for i in range(6, 12):
                conn.execute("INSERT INTO messages VALUES (?, 'a', 'user', ?, ?, 1)",
                             (i, "substantial operator prompt " * 20, f"2026-01-{i:02d}"))
        selected, _ = quente.select_window(
            store_dir=self.home, k=2, max_age_days=None,
            codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual([m["id"] for m in selected], ["hermes:a"])

        planned = sweep.plan_sweep(
            project_dir=self.home, cursors={}, recent=None,
            codex_dir=False, grok_dir=False, hermes_dir=self.db)
        self.assertEqual([p["surface"] for p in planned], ["hermes", "hermes"])
        self.assertEqual([p["profile_name"] for p in planned], ["work", "default"])
        self.assertEqual([p["edge_group"] for p in planned], ["hive", "hive"])
        self.assertEqual(planned[0]["turns"][:2], [
            sessions.Turn("human", "question"), sessions.Turn("edge", "answer")])


if __name__ == "__main__":
    unittest.main()
