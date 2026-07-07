import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import sessions  # noqa: E402


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _claude(path, prompt, *, sidechain=False):
    rows = []
    if sidechain:
        rows.append({"type": "user", "isSidechain": True, "message": {
            "role": "user", "content": prompt}})
    else:
        rows.append({"type": "user", "message": {"role": "user", "content": prompt}})
    return _write(path, rows)


def _codex(path, *, thread_source="user", parent=None, prompt="vamos trabalhar"):
    payload = {"id": "codex-1", "thread_source": thread_source}
    if parent:
        payload["parent_thread_id"] = parent
    rows = [
        {"type": "session_meta", "payload": payload},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": prompt}]}},
    ]
    return _write(path, rows)


class UserSessionFilter(unittest.TestCase):
    def test_claude_direct_operator_session_is_kept(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(Path(td) / "s.jsonl", "que dia esse virtualbox foi criado?")
            s = sessions.Session(id="s", path=p, surface="claude")
            self.assertIsNone(sessions.user_session_exclusion_reason(s))

    def test_claude_sidechain_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(Path(td) / "subagents" / "agent-a.jsonl", "faça o ticket", sidechain=True)
            s = sessions.Session(id="s", path=p, surface="claude")
            self.assertEqual(sessions.user_session_exclusion_reason(s), "claude-sidechain")

    def test_worker_prompt_in_root_session_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(
                Path(td) / "s.jsonl",
                "You are the prototype producer for this run. Your ONLY behavioral instructions are...",
            )
            s = sessions.Session(id="s", path=p, surface="claude")
            self.assertEqual(sessions.user_session_exclusion_reason(s), "agent-launch-prompt")

    def test_adversarial_gate_prompt_in_root_session_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(
                Path(td) / "s.jsonl",
                prompt="Você é o ADVERSARIAL de um build. ATAQUE o trabalho.",
            )
            s = sessions.Session(id="codex-1", path=p, surface="codex")
            self.assertEqual(sessions.user_session_exclusion_reason(s), "agent-launch-prompt")

    def test_codex_user_thread_is_kept(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(Path(td) / "s.jsonl")
            s = sessions.Session(id="codex-1", path=p, surface="codex")
            self.assertIsNone(sessions.user_session_exclusion_reason(s))

    def test_codex_scaffolding_user_messages_are_not_turns(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(
                Path(td) / "s.jsonl",
                prompt="<skill>\n<name>ed-wake</name>\n</skill>",
            )
            rows = p.read_text().splitlines()
            rows.append(json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "<subagent_notification>\n{}\n</subagent_notification>",
                    }],
                },
            }))
            rows.append(json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "texto real do usuario"}],
                },
            }))
            p.write_text("\n".join(rows) + "\n")
            turns = sessions.read_turns(p, surface="codex")
            self.assertEqual([t.text for t in turns], ["texto real do usuario"])

    def test_worker_and_task_scaffolding_messages_are_not_turns(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(Path(td) / "s.jsonl", "texto real do usuario")
            rows = p.read_text().splitlines()
            rows.insert(0, json.dumps({"type": "user", "message": {"role": "user", "content":
                "<task-notification>\n<task-id>x</task-id>\n</task-notification>"}}))
            rows.insert(1, json.dumps({"type": "user", "message": {"role": "user", "content":
                "This session is being continued from a previous conversation. Summary: ..."}}))
            rows.insert(2, json.dumps({"type": "user", "message": {"role": "user", "content":
                "ADVERSARIAL REVIEW — tente refutar este trabalho."}}))
            rows.insert(3, json.dumps({"type": "user", "message": {"role": "user", "content":
                "META-GATE (signal vs noise judge). Julgue cada achado."}}))
            rows.insert(4, json.dumps({"type": "user", "message": {"role": "user", "content":
                "<command-message>grill-me</command-message>"}}))
            rows.insert(5, json.dumps({"type": "user", "message": {"role": "user", "content":
                "Base directory for this skill: /home/vboxuser/.claude/skills/grill-me"}}))
            p.write_text("\n".join(rows) + "\n")
            turns = sessions.read_turns(p, surface="claude")
            self.assertEqual([t.text for t in turns], ["texto real do usuario"])

    def test_codex_subagent_thread_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(Path(td) / "s.jsonl", thread_source="subagent", parent="parent")
            s = sessions.Session(id="codex-1", path=p, surface="codex")
            self.assertEqual(
                sessions.user_session_exclusion_reason(s),
                "codex-thread-source:subagent",
            )


if __name__ == "__main__":
    unittest.main()
