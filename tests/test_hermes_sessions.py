import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import sessions
import surfaces_cfg


class HermesSessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.db = self.home / "state.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT,
                    parent_session_id TEXT, started_at TEXT, ended_at TEXT, profile_name TEXT);
                CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT,
                    role TEXT, content TEXT, timestamp TEXT, active INTEGER);
                INSERT INTO sessions VALUES ('a', 'cli', NULL, '1', NULL, 'work');
                INSERT INTO sessions VALUES ('b', 'cli', NULL, '1', NULL, NULL);
                INSERT INTO messages VALUES (3, 'a', 'assistant', 'answer', '2026-01-02', 1);
                INSERT INTO messages VALUES (1, 'a', 'user', 'question', '2026-01-01', 1);
                INSERT INTO messages VALUES (2, 'a', 'system', 'hidden', '2026-01-01', 1);
                INSERT INTO messages VALUES (4, 'a', 'user', 'inactive', '2026-01-03', 0);
                INSERT INTO messages VALUES (5, 'b', 'user', 'later', '2026-02-01', 1);
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rationalization_reads_virtual_hermes_dialogue(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO sessions VALUES ('c', 'cli', NULL, '1', NULL, 'work')")
            conn.executemany("INSERT INTO messages VALUES (?, 'c', ?, ?, ?, 1)", [
                (10, 'user', 'first substantial operator question about the project architecture', '2026-03-01'),
                (11, 'assistant', 'a substantial answer describing the architecture and next steps', '2026-03-01'),
                (12, 'user', 'second substantial operator question confirming the implementation', '2026-03-01'),
            ])
        session = next(s for s in sessions.list_hermes_sessions(self.db) if s.id == 'c')
        turns, watermark = sessions.mentee_dialogue_for_rationalize(session)
        self.assertEqual([turn.role for turn in turns], ['human', 'edge', 'human'])
        self.assertEqual(watermark, 12)

    def test_resolution_listing_turns_and_delta(self):
        self.assertEqual(surfaces_cfg.surface_home("hermes", env={"HERMES_HOME": str(self.home)}), self.home)
        found = sessions.list_hermes_sessions(env={"HERMES_HOME": str(self.home)})
        self.assertEqual([(s.id, s.updated_at) for s in found],
                         [('a', '2026-01-02'), ('b', '2026-02-01')])
        self.assertEqual([s.profile_name for s in found], ["work", "default"])
        self.assertEqual(sessions.read_turns(found[0].path, "hermes"),
                         [sessions.Turn("human", "question"), sessions.Turn("edge", "answer")])
        turns, watermark = sessions.delta(found[0].path, 1, "hermes")
        self.assertEqual(turns, [sessions.Turn("edge", "answer")])
        self.assertEqual(watermark, 3)

    def test_background_completion_notification_is_runtime_scaffolding(self):
        self.assertTrue(sessions._is_scaffolding_turn(
            "human", "[IMPORTANT: Background process proc_123 completed normally (exit code 0)."
        ))

    def test_current_session_anchors_include_hermes_env(self):
        env = {"EDGE_HOME": str(self.home), "HERMES_SESSION_ID": "desktop-live"}
        self.assertEqual(
            sessions.current_session_anchors(env),
            ("hermes:desktop-live",),
        )

    def test_current_session_anchors_include_live_hermes_markers(self):
        env = {"EDGE_HOME": str(self.home)}
        sessions.mark_hermes_session_active("desktop-live", env=env)
        self.assertEqual(
            sessions.current_session_anchors(env),
            ("hermes:desktop-live",),
        )
        sessions.mark_hermes_session_inactive("desktop-live", env=env)
        self.assertEqual(sessions.current_session_anchors(env), ())


if __name__ == "__main__":
    unittest.main()
