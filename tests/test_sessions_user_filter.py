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


def _codex(path, *, thread_source="user", parent=None, prompt="vamos trabalhar",
           source="cli", originator="codex-tui"):
    payload = {"id": "codex-1", "thread_source": thread_source,
               "source": source, "originator": originator}
    if parent:
        payload["parent_thread_id"] = parent
    rows = [
        {"type": "session_meta", "payload": payload},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": prompt}]}},
    ]
    return _write(path, rows)




def _grok(path, prompt, *, session_kind=None, session_id="g1"):
    """Real-shaped Grok store: chat_history.jsonl + sibling summary.json."""
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    chat = root / "chat_history.jsonl"
    body = f"<user_query>\n{prompt}\n</user_query>"
    chat.write_text(json.dumps({
        "type": "user",
        "content": [{"type": "text", "text": body}],
    }) + "\n")
    summary = {
        "info": {"id": session_id, "cwd": "/tmp"},
        "session_summary": prompt[:80],
    }
    if session_kind is not None:
        summary["session_kind"] = session_kind
    (root / "summary.json").write_text(json.dumps(summary))
    return chat

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

    def test_implementation_vocabulary_in_direct_session_is_not_a_filter(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(
                Path(td) / "s.jsonl",
                "Implement ticket 42 e faça um adversarial review da solução.",
            )
            s = sessions.Session(id="s", path=p, surface="claude")
            self.assertIsNone(sessions.user_session_exclusion_reason(s))

    def test_codex_exec_is_excluded_even_when_thread_source_says_user(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(
                Path(td) / "s.jsonl",
                prompt="uma tarefa delegada com conteúdo arbitrário",
                source="exec",
                originator="codex_exec",
            )
            s = sessions.Session(id="codex-1", path=p, surface="codex")
            self.assertEqual(sessions.user_session_exclusion_reason(s), "codex-source:exec")

    def test_heartbeat_protocol_envelope_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _claude(
                Path(td) / "s.jsonl",
                "AUTHORITATIVE DISPATCH PLAN (mechanical; do not override):\nrun beat",
            )
            s = sessions.Session(id="s", path=p, surface="claude")
            self.assertEqual(
                sessions.user_session_exclusion_reason(s),
                "automated-session-envelope",
            )

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
            self.assertEqual([t.text for t in turns], [
                "ADVERSARIAL REVIEW — tente refutar este trabalho.",
                "META-GATE (signal vs noise judge). Julgue cada achado.",
                "texto real do usuario",
            ])

    def test_codex_subagent_thread_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = _codex(Path(td) / "s.jsonl", thread_source="subagent", parent="parent")
            s = sessions.Session(id="codex-1", path=p, surface="codex")
            self.assertEqual(
                sessions.user_session_exclusion_reason(s),
                "codex-thread-source:subagent",
            )

    def test_grok_operator_session_is_kept(self):
        """Operator Grok sessions have no session_kind (or absent field) — keep as Voz."""
        with tempfile.TemporaryDirectory() as td:
            p = _grok(Path(td) / "019f-op", "que dia esse virtualbox foi criado?",
                      session_id="019f-op")
            s = sessions.Session(id="019f-op", path=p, surface="grok")
            self.assertIsNone(sessions.user_session_exclusion_reason(s))

    def test_grok_subagent_session_kind_is_excluded(self):
        """Real Grok stores workers as session_kind=subagent (not under a subagents/ path)."""
        with tempfile.TemporaryDirectory() as td:
            p = _grok(Path(td) / "019f-worker", "Wire Grok into topic_threads like Codex",
                      session_kind="subagent", session_id="019f-worker")
            s = sessions.Session(id="019f-worker", path=p, surface="grok")
            self.assertEqual(
                sessions.user_session_exclusion_reason(s),
                "grok-session-kind:subagent",
            )
            self.assertFalse(sessions.is_user_session(s))

    def test_grok_subagents_path_still_excluded(self):
        """Belt-and-suspenders: a subagents/ path component still excludes."""
        with tempfile.TemporaryDirectory() as td:
            p = _grok(Path(td) / "subagents" / "019f-path", "faça o ticket",
                      session_id="019f-path")
            s = sessions.Session(id="019f-path", path=p, surface="grok")
            self.assertEqual(sessions.user_session_exclusion_reason(s), "grok-subagent")



if __name__ == "__main__":
    unittest.main()
