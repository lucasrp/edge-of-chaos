import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import sessions  # noqa: E402
import sweep  # noqa: E402
import topic_threads  # noqa: E402


def _write_claude_session(path, prompts):
    rows = []
    for i, prompt in enumerate(prompts):
        rows.append({"type": "user", "message": {"role": "user", "content": prompt}})
        rows.append({"type": "assistant", "message": {"role": "assistant",
                                                       "content": f"reply {i}"}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _write_codex_session(store, sid, prompts):
    """Codex layout: flat/recursive *.jsonl with session_meta id."""
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "session_meta", "payload": {
        "id": sid, "thread_source": "user", "source": "cli",
        "originator": "codex-tui",
    }}]
    for prompt in prompts:
        rows.append({"type": "response_item",
                     "payload": {"type": "message", "role": "user",
                                 "content": [{"type": "input_text", "text": prompt}]}})
        rows.append({"type": "response_item",
                     "payload": {"type": "message", "role": "assistant",
                                 "content": [{"type": "output_text", "text": "ok"}]}})
    p = store / f"{sid}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _write_grok_session(store, sid, prompts):
    """Grok layout: sessions/<cwd>/<sid>/chat_history.jsonl."""
    root = Path(store) / "%2Ftmp" / sid
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for prompt in prompts:
        q = f"<user_query>\n{prompt}\n</user_query>"
        rows.append({"type": "user", "content": [{"type": "text", "text": q}]})
        rows.append({"type": "assistant", "content": [{"type": "text", "text": "ok"}]})
    p = root / "chat_history.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (root / "summary.json").write_text(json.dumps({"info": {"id": sid}}))
    return p


class TopicThreadsProjectDirection(unittest.TestCase):
    def test_recent_voice_topics_are_indexed_by_session_topic_and_fragment(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s1.jsonl", [
                "quero indexar sessoes por topics e navegar pelos fragmentos",
                "recall deve achar fragments e topics preservando a sessao",
            ])

            out = topic_threads.sync_recent_topic_memory(
                project_dir=proj, codex_dir=False, grok_dir=False, all_stores=False, log=log,
            )

            self.assertGreaterEqual(out["topics"], 1)
            idx = eventlog.session_topics_at(log=log)
            self.assertIn("s1", idx["sessions"])
            self.assertIn("session-voice", idx["topics"])
            self.assertIn("session-memory-navigation", idx["topics"])
            topic = idx["topics"]["session-memory-navigation"]
            self.assertEqual(topic["sessions"], ["s1"])
            self.assertEqual(len(topic["fragments"]), 2)
            first_fragment = idx["fragments"][topic["fragments"][0]]
            self.assertEqual(first_fragment["session_id"], "s1")
            self.assertIn("sess", first_fragment["snippet"].lower())

            again = topic_threads.sync_recent_topic_memory(
                project_dir=proj, codex_dir=False, grok_dir=False, all_stores=False, log=log,
            )
            self.assertEqual(again["topics"], 0, "same topic index must be idempotent")

    def test_recent_voice_topics_become_direction_proposed_with_evidence_refs(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s1.jsonl", [
                "direction proposed deve rodar na hora do wake junto com o assemble",
                "eh bom que o wake ja vai costurando os topics em threads, consolidando",
            ])

            written = topic_threads.propose_recent_topic_directions(
                project_dir=proj, codex_dir=False, grok_dir=False, all_stores=False, log=log,
            )

            self.assertEqual(written, 1)
            d = eventlog.direction_at(log=log)
            item = d["proposed"][0]
            self.assertEqual(item["id"], "topic-7d:topic-thread-direction")
            self.assertIn("wake", item["body"].lower())
            self.assertIn("grill", item["body"].lower())
            self.assertEqual(len(item["relates_to"]), 2)
            self.assertEqual(item["relates_to"][0]["kind"], "voz.fragment")
            self.assertEqual(
                topic_threads.propose_recent_topic_directions(
                    project_dir=proj, codex_dir=False, grok_dir=False, all_stores=False, log=log,
                ),
                0,
                "same current body must not append duplicate proposals",
            )

    def test_set_direction_is_not_reopened_by_automatic_topic_projection(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s1.jsonl", [
                "direction proposed deve rodar no wake e costurar topics",
                "assemble deve ler essa direction proposed antes do grill",
            ])
            eventlog.set_direction(
                "topic-7d:topic-thread-direction",
                "Ratified direction already owns this thread",
                log=log,
            )

            written = topic_threads.propose_recent_topic_directions(
                project_dir=proj, codex_dir=False, grok_dir=False, all_stores=False, log=log,
            )

            self.assertEqual(written, 0)
            d = eventlog.direction_at(log=log)
            self.assertEqual(len(d["set"]), 1)
            self.assertEqual(d["proposed"], [])

    def test_sweep_reprojects_when_only_topic_direction_changes(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            path = _write_claude_session(Path(proj) / "s1.jsonl", [
                "direction proposed deve rodar no wake junto com assemble",
                "costurar topics em threads facilita busca e consolidacao",
            ])
            _turns, watermark = sessions.delta(path, 0, surface="claude")
            cursors = Path(st) / "cursors.json"
            cursors.write_text(json.dumps({"s1": watermark}))
            log = Path(st) / "log.jsonl"
            reprojected = []

            n = sweep.run(
                proj,
                ingest_fn=lambda items: None,
                cursors_path=cursors,
                reproject_fn=lambda: reprojected.append(True),
                log=log,
                graph_recover_fn=False,
                group="test-group",
                codex_dir=False,
                grok_dir=False,
            )

            self.assertEqual(n, 0)
            self.assertEqual(reprojected, [True])
            self.assertEqual(
                eventlog.direction_at(log=log)["proposed"][0]["id"],
                "topic-7d:topic-thread-direction",
            )


class TopicThreadsSurfaceDiscovery(unittest.TestCase):
    """Codex + Grok optional stores join topic_threads the same way sweep/quente do."""

    def test_codex_dir_explicit_indexes_with_codex_anchor(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as codex, \
                tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s-claude.jsonl", ["claude only noise"])
            _write_codex_session(codex, "c-stable", [
                "quero indexar sessoes por topics e navegar pelos fragmentos",
                "recall deve achar fragments e topics preservando a sessao",
            ])

            out = topic_threads.sync_recent_topic_memory(
                project_dir=proj, codex_dir=codex, grok_dir=False, all_stores=False, log=log,
            )

            self.assertGreaterEqual(out["topics"], 1)
            idx = eventlog.session_topics_at(log=log)
            self.assertIn("codex:c-stable", idx["sessions"])
            topic = idx["topics"]["session-memory-navigation"]
            self.assertIn("codex:c-stable", topic["sessions"])
            frag = idx["fragments"][topic["fragments"][0]]
            self.assertEqual(frag["surface"], "codex")
            self.assertEqual(frag["session_id"], "codex:c-stable")

    def test_grok_dir_explicit_indexes_with_grok_anchor(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as grok, \
                tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s-claude.jsonl", ["claude only noise"])
            _write_grok_session(grok, "g-stable", [
                "quero indexar sessoes por topics e navegar pelos fragmentos",
                "recall deve achar fragments e topics preservando a sessao",
            ])

            out = topic_threads.sync_recent_topic_memory(
                project_dir=proj, codex_dir=False, grok_dir=grok, all_stores=False, log=log,
            )

            self.assertGreaterEqual(out["topics"], 1)
            idx = eventlog.session_topics_at(log=log)
            self.assertIn("grok:g-stable", idx["sessions"])
            topic = idx["topics"]["session-memory-navigation"]
            self.assertIn("grok:g-stable", topic["sessions"])
            frag = idx["fragments"][topic["fragments"][0]]
            self.assertEqual(frag["surface"], "grok")
            self.assertEqual(frag["session_id"], "grok:g-stable")

    def test_project_dir_set_without_optional_dirs_is_hermetic(self):
        """project_dir set + codex_dir/grok_dir None must not touch real ~/.codex or ~/.grok."""
        with tempfile.TemporaryDirectory() as proj:
            _write_claude_session(Path(proj) / "s1.jsonl", ["hello"])
            with mock.patch.object(sessions, "list_codex_sessions") as list_codex, \
                    mock.patch.object(sessions, "list_grok_sessions") as list_grok:
                frags = topic_threads.collect_voice_fragments(
                    project_dir=proj, codex_dir=None, grok_dir=None, all_stores=False,
                )
                list_codex.assert_not_called()
                list_grok.assert_not_called()
            self.assertTrue(all(f.surface == "claude" for f in frags))

    def test_all_stores_includes_grok_when_dir_defaulted(self):
        """Real-sweep mode (all_stores) discovers Grok like Codex when dirs are None."""
        with tempfile.TemporaryDirectory() as claude_root, tempfile.TemporaryDirectory() as grok:
            _write_claude_session(Path(claude_root) / "proj" / "s1.jsonl", ["claude noise"])
            _write_grok_session(grok, "g-all", [
                "quero indexar sessoes por topics e navegar pelos fragmentos",
            ])
            frags = topic_threads.collect_voice_fragments(
                project_dir=None, claude_root=claude_root, codex_dir=False, grok_dir=grok,
                all_stores=True,
            )
            surfaces = {f.surface for f in frags}
            self.assertIn("grok", surfaces)
            self.assertTrue(any(f.session_id == "grok:g-all" for f in frags))


if __name__ == "__main__":
    unittest.main()
