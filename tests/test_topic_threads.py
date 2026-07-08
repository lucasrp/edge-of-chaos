import json
import sys
import tempfile
import unittest
from pathlib import Path

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


class TopicThreadsProjectDirection(unittest.TestCase):
    def test_recent_voice_topics_are_indexed_by_session_topic_and_fragment(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            _write_claude_session(Path(proj) / "s1.jsonl", [
                "quero indexar sessoes por topics e navegar pelos fragmentos",
                "recall deve achar fragments e topics preservando a sessao",
            ])

            out = topic_threads.sync_recent_topic_memory(
                project_dir=proj, codex_dir=False, all_stores=False, log=log,
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
                project_dir=proj, codex_dir=False, all_stores=False, log=log,
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
                project_dir=proj, codex_dir=False, all_stores=False, log=log,
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
                    project_dir=proj, codex_dir=False, all_stores=False, log=log,
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
                project_dir=proj, codex_dir=False, all_stores=False, log=log,
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
            )

            self.assertEqual(n, 0)
            self.assertEqual(reprojected, [True])
            self.assertEqual(
                eventlog.direction_at(log=log)["proposed"][0]["id"],
                "topic-7d:topic-thread-direction",
            )


if __name__ == "__main__":
    unittest.main()
