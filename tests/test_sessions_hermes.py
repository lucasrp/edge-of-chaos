"""Hermes transcript adapter — public session export into the Edge sweep."""
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import sessions  # noqa: E402
import sweep  # noqa: E402

BODY = "a substantial decision about the Produto Isis architecture and its operational direction " * 4


def export_row(session_id="h1", *, source="whatsapp_cloud", parent=None):
    messages = []
    for i in range(3):
        messages.extend([
            {"id": i * 2 + 1, "role": "user", "content": f"{BODY} ({i})",
             "timestamp": 1000 + i * 2, "active": 1, "compacted": 0},
            {"id": i * 2 + 2, "role": "assistant", "content": f"reply {i}: {BODY}",
             "timestamp": 1001 + i * 2, "active": 1, "compacted": 0},
        ])
    messages.extend([
        {"id": 90, "role": "tool", "content": "sensitive tool output", "timestamp": 2000,
         "active": 1, "compacted": 0},
        {"id": 91, "role": "session_meta", "content": "runtime metadata", "timestamp": 2001,
         "active": 1, "compacted": 0},
        {"id": 92, "role": "user", "content": "rewound text", "timestamp": 2002,
         "active": 0, "compacted": 0},
    ])
    return {"id": session_id, "source": source, "parent_session_id": parent,
            "started_at": 1000.0, "ended_at": 2000.0, "messages": messages}


class MaterializeHermesExport(unittest.TestCase):
    def test_current_session_anchor_uses_hermes_runtime_id(self):
        self.assertEqual(
            sessions.current_session_anchor({"HERMES_SESSION_ID": "h-live"}),
            "hermes:h-live",
        )

    def test_writes_only_active_user_assistant_dialogue_and_preserves_surface(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export = root / "export.jsonl"
            export.write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
            found = sessions.materialize_hermes_export(export, root / "sessions")
            self.assertEqual(len(found), 1)
            self.assertEqual(stat.S_IMODE((root / "sessions").stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(found[0].path.stat().st_mode), 0o600)
            self.assertEqual(found[0].surface, "hermes")
            turns = sessions.read_turns(found[0].path, surface="hermes")
            self.assertEqual([t.role for t in turns], ["human", "edge"] * 3)
            text = "\n".join(t.text for t in turns)
            self.assertNotIn("sensitive tool output", text)
            self.assertNotIn("runtime metadata", text)
            self.assertNotIn("rewound text", text)

    def test_excludes_subagents_tool_sessions_cron_and_parent_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export = root / "export.jsonl"
            rows = [export_row("operator"), export_row("child", parent="operator"),
                    export_row("subagent", source="subagent"),
                    export_row("tool", source="tool"), export_row("cron", source="cron")]
            export.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            found = sessions.materialize_hermes_export(export, root / "sessions")
            self.assertEqual([s.id for s in found], ["operator"])

    def test_refresh_invokes_public_export_with_explicit_hermes_home(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            calls = []
            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                Path(command[-1]).write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            found = sessions.refresh_hermes_sessions(
                root / "sessions", hermes_home=root / "hermes-home", run=fake_run)
            self.assertEqual([s.id for s in found], ["h1"])
            self.assertEqual(calls[0][0][:3], ["hermes", "sessions", "export"])
            self.assertEqual(calls[0][1]["env"]["HERMES_HOME"], str(root / "hermes-home"))
            self.assertEqual(calls[0][1]["timeout"], 300)
            self.assertFalse((root / "sessions.export.tmp").exists())

    def test_refresh_serializes_concurrent_exports_for_one_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = {"active": 0, "max_active": 0}
            guard = threading.Lock()
            errors = []

            def fake_run(command, **kwargs):
                with guard:
                    state["active"] += 1
                    state["max_active"] = max(state["max_active"], state["active"])
                time.sleep(0.05)
                Path(command[-1]).write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
                with guard:
                    state["active"] -= 1
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            def refresh():
                try:
                    sessions.refresh_hermes_sessions(root / "sessions", run=fake_run)
                except Exception as exc:  # captured so both threads always join
                    errors.append(exc)

            threads = [threading.Thread(target=refresh) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual(errors, [])
            self.assertEqual(state["max_active"], 1)


class SweepPlansHermesWithoutClaudeStore(unittest.TestCase):
    def _store(self, root):
        export = root / "export.jsonl"
        export.write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
        store = root / "hermes"
        sessions.materialize_hermes_export(export, store)
        return store

    def test_explicit_hermes_store_does_not_require_a_claude_project_dir(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            plan = sweep.plan_sweep(False, {}, codex_dir=False, grok_dir=False, hermes_dir=store)
            self.assertEqual([item["id"] for item in plan], ["hermes:h1"])
            self.assertEqual(plan[0]["surface"], "hermes")
            self.assertFalse(plan[0]["skip"])

    def test_live_plan_refreshes_hermes_and_skips_missing_claude_store(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export = root / "export.jsonl"
            export.write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
            hermes_home = root / "hermes-home"
            hermes_home.mkdir()
            edge_home = root / "edge-home"

            def fake_refresh(output_dir, *, hermes_home=None, run=None):
                self.assertEqual(Path(hermes_home), root / "hermes-home")
                return sessions.materialize_hermes_export(export, output_dir)

            env = {"HERMES_HOME": str(hermes_home), "EDGE_HOME": str(edge_home)}
            with mock.patch.dict(os.environ, env, clear=False), \
                 mock.patch.object(sessions, "refresh_hermes_sessions", side_effect=fake_refresh), \
                 mock.patch.object(sweep, "_claude_enabled", return_value=False):
                plan = sweep.plan_sweep(None, {}, codex_dir=False, grok_dir=False)

            self.assertEqual([item["id"] for item in plan], ["hermes:h1"])

    def test_live_run_refreshes_once_and_never_resolves_claude(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export = root / "export.jsonl"
            export.write_text(json.dumps(export_row()) + "\n", encoding="utf-8")
            hermes_home = root / "hermes-home"
            hermes_home.mkdir()
            edge_home = root / "edge-home"
            calls = []

            def fake_refresh(output_dir, *, hermes_home=None, run=None):
                calls.append(Path(output_dir))
                return sessions.materialize_hermes_export(export, output_dir)

            env = {"HERMES_HOME": str(hermes_home), "EDGE_HOME": str(edge_home),
                   "EDGE_TOPIC_DIRECTION": "0"}
            with mock.patch.dict(os.environ, env, clear=False), \
                 mock.patch.object(sessions, "refresh_hermes_sessions", side_effect=fake_refresh), \
                 mock.patch.object(sweep, "_claude_enabled", return_value=False):
                n = sweep.run(None, ingest_fn=lambda items: None,
                              cursors_path=root / "cursors.json", reproject_fn=False,
                              log=root / "log.jsonl", graph_recover_fn=False,
                              group="limiar-test", codex_dir=False, grok_dir=False)

            self.assertEqual(n, 1)
            self.assertEqual(len(calls), 1)

    def test_run_threads_hermes_store_into_episode_and_cursor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            log, cursors = root / "log.jsonl", root / "cursors.json"
            seen = []
            n = sweep.run(False, ingest_fn=lambda items: seen.extend(i["id"] for i in items),
                          cursors_path=cursors, reproject_fn=False, log=log,
                          graph_recover_fn=False, group="limiar-test", codex_dir=False,
                          grok_dir=False, hermes_dir=store)
            self.assertEqual((n, seen), (1, ["hermes:h1"]))
            self.assertIn("hermes:h1", sweep.load_cursors(cursors))
            episodes = eventlog.read(types=["episode"], log=log)
            self.assertEqual(episodes[0]["payload"]["surface"], "hermes")


if __name__ == "__main__":
    unittest.main()
