"""The session reader + delta — slice 1 of the measure-first spike (G5).

A Claude transcript is the raw layer (ADR-0004 decision A): one `.jsonl` = one session.
This reader discovers sessions, parses them into ordered human/edge turns (filtering the
transcript's noise lines), and computes the delta of a session since a stored watermark — the
deterministic, locator/offset-based kernel that feeds the agentic claim-extraction (slice 2).
It carries no semantics (ADR-0001: no per-source semantic primitive).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sessions  # noqa: E402


def _write_session(project_dir: Path, sid: str, lines: list) -> Path:
    """Write a synthetic transcript: one JSON object per line, like Claude Code."""
    p = project_dir / f"{sid}.jsonl"
    p.write_text("".join(json.dumps(o) + "\n" for o in lines))
    return p


def _msg(role: str, text: str) -> dict:
    """A real Claude transcript message line: content is a list of typed blocks."""
    return {"type": role, "message": {"role": role, "content": [{"type": "text", "text": text}]}}


def _codex_msg(role: str, text: str) -> dict:
    typ = "input_text" if role == "user" else "output_text"
    return {"type": "response_item",
            "payload": {"type": "message", "role": role,
                        "content": [{"type": typ, "text": text}]}}


def _grok_user(text: str, *, wrap_query: bool = True, synthetic_reason=None) -> dict:
    body = f"<user_query>\n{text}\n</user_query>" if wrap_query else text
    obj = {"type": "user", "content": [{"type": "text", "text": body}]}
    if synthetic_reason is not None:
        obj["synthetic_reason"] = synthetic_reason
    return obj


def _grok_assistant(text: str) -> dict:
    return {"type": "assistant", "content": [{"type": "text", "text": text}]}


class ListSessionsDiscoversTranscripts(unittest.TestCase):
    """One `.jsonl` in the project dir = one session, identified by its filename uuid."""

    def test_each_jsonl_is_one_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_session(d, "aaa", [{"type": "user"}])
            _write_session(d, "bbb", [{"type": "user"}])
            ids = {s.id for s in sessions.list_sessions(d)}
            self.assertEqual(ids, {"aaa", "bbb"})


class ReadTurnsExtractsOrderedDialogue(unittest.TestCase):
    """A transcript parses into ordered turns; `user`->human, `assistant`->edge, text only."""

    def test_human_then_edge_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "s", [_msg("user", "qual o tema?"),
                                                _msg("assistant", "o tema e X")])
            turns = sessions.read_turns(p)
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "qual o tema?"), ("edge", "o tema e X")])


class ReadTurnsDropsNoise(unittest.TestCase):
    """Bookkeeping lines and text-less tool-only messages are not dialogue turns."""

    def test_only_text_dialogue_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "s", [
                {"type": "queue-operation", "operation": "x"},
                {"type": "attachment"},
                _msg("user", "pergunta real"),
                {"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
                {"type": "user", "message": {"role": "user",
                    "content": [{"type": "tool_result", "content": "output"}]}},
                {"type": "last-prompt"},
                _msg("assistant", "resposta real"),
            ])
            turns = sessions.read_turns(p)
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "pergunta real"), ("edge", "resposta real")])


class CodexReadTurnsExtractsVisibleDialogue(unittest.TestCase):
    """Codex JSONL is a different envelope, but normalizes to the same human/edge turns."""

    def test_codex_response_items_parse_and_drop_scaffolding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "rollout", [
                {"type": "session_meta", "payload": {"id": "codex-session"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "duplicado"}},
                _codex_msg("developer", "instrucoes internas"),
                _codex_msg("user", "<environment_context>cwd</environment_context>"),
                _codex_msg("user", "quero juntar as CLIs"),
                {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command"}},
                _codex_msg("assistant", "vou implementar o parser"),
            ])
            turns = sessions.read_turns(p, surface="codex")
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "quero juntar as CLIs"),
                              ("edge", "vou implementar o parser")])

    def test_codex_session_id_comes_from_session_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions" / "2026" / "07" / "05"
            root.mkdir(parents=True)
            p = _write_session(root, "rollout-name", [
                {"type": "session_meta", "payload": {"id": "stable-id"}},
                _codex_msg("user", "oi"),
            ])
            found = sessions.list_codex_sessions(Path(tmp) / "sessions")
            self.assertEqual([(s.id, s.path) for s in found], [("stable-id", p)])


class ExtractClaimsParsesTheModelsAssertions(unittest.TestCase):
    """Claim extraction is agentic: it feeds the dialogue to an injected LLM and parses the
    discrete assertions it returns. The injected `complete_fn` is the testable seam."""

    def test_parses_claims_from_model_json(self):
        turns = [sessions.Turn("human", "o foco e legibilidade"),
                 sessions.Turn("edge", "hipotese: o gargalo e custo de contexto")]
        captured = {}

        def fake_complete(prompt: str) -> str:
            captured["prompt"] = prompt
            return json.dumps(["mentee prioriza legibilidade",
                               "gargalo suposto: custo de contexto"])

        claims = sessions.extract_claims(turns, fake_complete)
        self.assertEqual([c.text for c in claims],
                         ["mentee prioriza legibilidade", "gargalo suposto: custo de contexto"])
        # the dialogue actually reaches the model.
        self.assertIn("legibilidade", captured["prompt"])


class ClassifySessionLabelsClaimEvolution(unittest.TestCase):
    """Each new claim is labelled against the accumulated state in ONE batched call:
    replacement / duplicate / divergence / novel — the G5 distinction (time vs meaning)."""

    def test_parses_batched_labels(self):
        state = ["mentee prioriza legibilidade"]
        new = [sessions.Claim("mentee agora prioriza velocidade"),
               sessions.Claim("mentee usa TDD por padrao")]

        def fake_complete(prompt: str) -> str:
            return json.dumps([
                {"text": "mentee agora prioriza velocidade", "kind": "replacement"},
                {"text": "mentee usa TDD por padrao", "kind": "novel"},
            ])

        labelled = sessions.classify_session(state, new, fake_complete)
        self.assertEqual([(c.text, c.kind) for c in labelled],
                         [("mentee agora prioriza velocidade", "replacement"),
                          ("mentee usa TDD por padrao", "novel")])


class DeltaReadsOnlyWhatIsNew(unittest.TestCase):
    """The delta is the turns after a raw-line watermark; re-reading from it yields nothing."""

    def test_incremental_then_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "s", [_msg("user", "primeira")])
            turns, mark = sessions.delta(p, 0)
            self.assertEqual([t.text for t in turns], ["primeira"])

            # append a new exchange; the next delta starts at the prior watermark.
            with p.open("a") as fh:
                fh.write(json.dumps(_msg("assistant", "segunda")) + "\n")
            turns2, mark2 = sessions.delta(p, mark)
            self.assertEqual([t.text for t in turns2], ["segunda"])

            # nothing new since the latest watermark.
            turns3, mark3 = sessions.delta(p, mark2)
            self.assertEqual(turns3, [])
            self.assertEqual(mark3, mark2)

    def test_codex_delta_uses_the_codex_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "c", [_codex_msg("user", "primeira")])
            turns, mark = sessions.delta(p, 0, surface="codex")
            self.assertEqual([t.text for t in turns], ["primeira"])
            with p.open("a") as fh:
                fh.write(json.dumps(_codex_msg("assistant", "segunda")) + "\n")
            turns2, _ = sessions.delta(p, mark, surface="codex")
            self.assertEqual([(t.role, t.text) for t in turns2], [("edge", "segunda")])

    def test_grok_delta_uses_the_grok_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "g", [_grok_user("primeira")])
            turns, mark = sessions.delta(p, 0, surface="grok")
            self.assertEqual([t.text for t in turns], ["primeira"])
            with p.open("a") as fh:
                fh.write(json.dumps(_grok_assistant("segunda")) + "\n")
            turns2, _ = sessions.delta(p, mark, surface="grok")
            self.assertEqual([(t.role, t.text) for t in turns2], [("edge", "segunda")])


class GrokReadTurnsExtractsVisibleDialogue(unittest.TestCase):
    """Grok chat_history.jsonl is a third envelope; normalizes to the same human/edge turns."""

    def test_grok_user_query_and_assistant_parse_and_drop_synthetic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "chat_history", [
                {"type": "system", "content": "You are Grok"},
                _grok_user("oi", wrap_query=True),
                {"type": "user",
                 "content": [{"type": "text", "text": "<system-reminder>\nskills\n</system-reminder>"}],
                 "synthetic_reason": "system_reminder"},
                {"type": "reasoning", "content": "thinking"},
                {"type": "backend_tool_call", "name": "bash"},
                {"type": "tool_result", "content": "ok"},
                _grok_assistant("Ed here — what do you want to work on?"),
            ])
            turns = sessions.read_turns(p, surface="grok")
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "oi"),
                              ("edge", "Ed here — what do you want to work on?")])

    def test_list_grok_sessions_finds_chat_history_under_cwd_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions" / "%2Fhome%2Fop" / "019f-abc"
            root.mkdir(parents=True)
            p = root / "chat_history.jsonl"
            p.write_text(json.dumps(_grok_user("oi", wrap_query=True)) + "\n")
            (root / "events.jsonl").write_text("{}\n")
            found = sessions.list_grok_sessions(Path(tmp) / "sessions")
            self.assertEqual([(s.id, s.surface, s.path) for s in found],
                             [("019f-abc", "grok", p)])

    def test_grok_session_anchor_and_live_env(self):
        self.assertEqual(sessions.grok_session_anchor("019f-x"), "grok:019f-x")
        self.assertEqual(sessions.split_session_anchor("grok:019f-x"), ("grok", "019f-x"))
        self.assertEqual(
            sessions.current_session_anchor({"GROK_SESSION_ID": "019f-live"}),
            "grok:019f-live",
        )


class MeasureYieldsTheG5Verdict(unittest.TestCase):
    """The spike's number: counts per kind + whether the bottleneck is time (replacement/
    duplicate, Zep solves) or meaning (divergence, grill-me's domain)."""

    def _c(self, kind):
        return sessions.Classification(text="x", kind=kind)

    def test_meaning_dominates(self):
        cls = [self._c("divergence"), self._c("divergence"),
               self._c("replacement"), self._c("novel")]
        m = sessions.measure(cls)
        self.assertEqual(m["counts"], {"replacement": 1, "duplicate": 0,
                                       "divergence": 2, "novel": 1})
        self.assertEqual(m["verdict"], "meaning")

    def test_time_dominates(self):
        cls = [self._c("replacement"), self._c("duplicate"), self._c("divergence")]
        self.assertEqual(sessions.measure(cls)["verdict"], "time")


class RunSpikeAccumulatesStateAcrossSessions(unittest.TestCase):
    """The spike walks sessions oldest->newest, classifying each against the state grown so
    far, then folds that session's claims into the state for the next one."""

    def test_state_grows_in_order(self):
        sess_a = [sessions.Turn("human", "a")]
        sess_b = [sessions.Turn("human", "b")]
        seen_states = []

        def extract_fn(turns):
            return [sessions.Claim(turns[0].text)]

        def classify_fn(state, claims):
            seen_states.append(list(state))  # capture what state each session saw
            return [sessions.Classification(claims[0].text, "novel")]

        m = sessions.run_spike([sess_a, sess_b], extract_fn, classify_fn)
        # session A saw an empty state; session B saw A's claim already folded in.
        self.assertEqual(seen_states, [[], ["a"]])
        self.assertEqual(m["counts"]["novel"], 2)


class GrokLiveSessionAnchor(unittest.TestCase):
    """Live Grok identity is in active_sessions.json (CLI does not export GROK_SESSION_ID)."""

    def test_current_session_anchor_from_active_sessions_pid(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "active_sessions.json"
            active.write_text(json.dumps([{
                "session_id": "019f-live-pid",
                "pid": os.getpid(),
                "cwd": "/tmp",
                "opened_at": "2026-07-11T00:00:00Z",
            }]))
            env = {
                "EDGE_GROK_ACTIVE_SESSIONS": str(active),
                # no CLAUDE/CODEX/GROK session env keys
            }
            self.assertEqual(
                sessions.current_session_anchor(env),
                "grok:019f-live-pid",
            )

    def test_grok_session_id_env_wins_over_active_file(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "active_sessions.json"
            active.write_text(json.dumps([{
                "session_id": "019f-from-file",
                "pid": os.getpid(),
                "cwd": "/tmp",
                "opened_at": "2026-07-11T00:00:00Z",
            }]))
            env = {
                "GROK_SESSION_ID": "019f-from-env",
                "EDGE_GROK_ACTIVE_SESSIONS": str(active),
            }
            self.assertEqual(
                sessions.current_session_anchor(env),
                "grok:019f-from-env",
            )

    def test_single_active_entry_without_pid_match_is_none(self):
        """Finding E: sole-entry fallback fabricated stale session_id — fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "active_sessions.json"
            active.write_text(json.dumps([{
                "session_id": "019f-only",
                "pid": 1,  # not us
                "cwd": "/tmp",
                "opened_at": "2026-07-11T00:00:00Z",
            }]))
            env = {"EDGE_GROK_ACTIVE_SESSIONS": str(active)}
            self.assertIsNone(sessions.current_session_anchor(env))

    def test_multi_active_without_pid_match_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "active_sessions.json"
            active.write_text(json.dumps([
                {"session_id": "a", "pid": 1, "cwd": "/a", "opened_at": "2026-07-11T00:00:00Z"},
                {"session_id": "b", "pid": 2, "cwd": "/b", "opened_at": "2026-07-11T00:00:01Z"},
            ]))
            env = {"EDGE_GROK_ACTIVE_SESSIONS": str(active)}
            self.assertIsNone(sessions.current_session_anchor(env))

    def test_resolve_via_grok_home_active_sessions(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".grok"
            home.mkdir()
            (home / "active_sessions.json").write_text(json.dumps([{
                "session_id": "019f-home",
                "pid": os.getpid(),
                "cwd": "/tmp",
                "opened_at": "2026-07-11T00:00:00Z",
            }]))
            env = {"GROK_HOME": str(home)}
            self.assertEqual(
                sessions.current_session_anchor(env),
                "grok:019f-home",
            )


# --- M2.MIN.1: Mineração interface seam (dialogue_turns / mentee_dialogue) ---


class DialogueTurnsThreeSurfaces(unittest.TestCase):
    """``dialogue_turns(path, surface)`` → list[Turn(human|edge)], tools/terminals dropped.

    Spec: memory/spec-mineracao-deep-module.md — three chat surfaces share one Turn shape.
    """

    def test_claude_dialogue_only_no_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "s", [
                _msg("user", "qual o tema?"),
                {"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
                {"type": "user", "message": {"role": "user",
                    "content": [{"type": "tool_result", "content": "noise"}]}},
                _msg("assistant", "o tema e X"),
            ])
            turns = sessions.dialogue_turns(p, surface="claude")
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "qual o tema?"), ("edge", "o tema e X")])

    def test_codex_dialogue_only_no_function_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "c", [
                {"type": "session_meta", "payload": {"id": "c1"}},
                _codex_msg("user", "quero o portfolio"),
                {"type": "response_item",
                 "payload": {"type": "function_call", "name": "exec_command"}},
                _codex_msg("assistant", "vou montar o brief"),
            ])
            turns = sessions.dialogue_turns(p, surface="codex")
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "quero o portfolio"),
                              ("edge", "vou montar o brief")])

    def test_grok_dialogue_only_no_synthetic_or_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "g", [
                _grok_user("oi do operador"),
                {"type": "user",
                 "content": [{"type": "text", "text": "<system-reminder>x</system-reminder>"}],
                 "synthetic_reason": "system_reminder"},
                {"type": "backend_tool_call", "name": "bash"},
                {"type": "tool_result", "content": "ok"},
                _grok_assistant("pronto"),
            ])
            turns = sessions.dialogue_turns(p, surface="grok")
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "oi do operador"), ("edge", "pronto")])

    def test_bad_surface_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "s", [_msg("user", "x")])
            with self.assertRaises(ValueError) as ctx:
                sessions.dialogue_turns(p, surface="gemini")
            self.assertIn("surface", str(ctx.exception).lower())


class MenteeDialogueForRationalize(unittest.TestCase):
    """``mentee_dialogue_for_rationalize(session)`` → None | (turns, watermark).

    None when not operator-facing or no human dialogue; else pre-processed turns + CAS watermark.
    """

    def test_claude_operator_returns_turns_and_watermark(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "op", [
                _msg("user", "vamos fechar o MIN.1"),
                {"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
                _msg("assistant", "ok, testes no seam"),
            ])
            session = sessions.Session(id="op", path=p, surface="claude")
            packed = sessions.mentee_dialogue_for_rationalize(session)
            self.assertIsNotNone(packed)
            turns, watermark = packed
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "vamos fechar o MIN.1"),
                              ("edge", "ok, testes no seam")])
            self.assertEqual(watermark, 3)  # raw lines, including tool line

    def test_claude_sidechain_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "subagents"
            sub.mkdir()
            p = _write_session(sub, "w", [
                _msg("user", "You are the prototype producer for this run. Ticket X."),
                _msg("assistant", "working"),
            ])
            session = sessions.Session(id="w", path=p, surface="claude")
            self.assertIsNone(sessions.mentee_dialogue_for_rationalize(session))

    def test_codex_operator_returns_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "c", [
                {"type": "session_meta",
                 "payload": {"id": "c1", "thread_source": "user"}},
                _codex_msg("user", "emprego do mentee"),
                _codex_msg("assistant", "portfolio_at only"),
            ])
            session = sessions.Session(id="c1", path=p, surface="codex")
            packed = sessions.mentee_dialogue_for_rationalize(session)
            self.assertIsNotNone(packed)
            turns, watermark = packed
            self.assertEqual([t.role for t in turns], ["human", "edge"])
            self.assertEqual(watermark, 3)

    def test_codex_subagent_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "c", [
                {"type": "session_meta",
                 "payload": {"id": "c2", "thread_source": "subagent",
                             "parent_thread_id": "parent"}},
                _codex_msg("user", "faça o ticket longo " * 20),
                _codex_msg("assistant", "ok"),
            ])
            session = sessions.Session(id="c2", path=p, surface="codex")
            self.assertIsNone(sessions.mentee_dialogue_for_rationalize(session))

    def test_grok_operator_returns_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "g1"
            root.mkdir()
            p = root / "chat_history.jsonl"
            p.write_text("".join(json.dumps(o) + "\n" for o in [
                _grok_user("que dia o virtualbox foi criado?"),
                _grok_assistant("vou checar"),
            ]))
            (root / "summary.json").write_text(json.dumps({
                "info": {"id": "g1", "cwd": "/tmp"},
                "session_kind": "operator",
            }))
            session = sessions.Session(id="g1", path=p, surface="grok")
            packed = sessions.mentee_dialogue_for_rationalize(session)
            self.assertIsNotNone(packed)
            turns, watermark = packed
            self.assertEqual([(t.role, t.text) for t in turns],
                             [("human", "que dia o virtualbox foi criado?"),
                              ("edge", "vou checar")])
            self.assertEqual(watermark, 2)

    def test_grok_worker_session_kind_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "gw"
            root.mkdir()
            p = root / "chat_history.jsonl"
            p.write_text("".join(json.dumps(o) + "\n" for o in [
                _grok_user("Wire the adapter"),
                _grok_assistant("done"),
            ]))
            (root / "summary.json").write_text(json.dumps({
                "info": {"id": "gw"},
                "session_kind": "subagent",
            }))
            session = sessions.Session(id="gw", path=p, surface="grok")
            self.assertIsNone(sessions.mentee_dialogue_for_rationalize(session))

    def test_edge_only_transcript_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_session(Path(tmp), "edge-only", [
                _msg("assistant", "no human ever spoke"),
            ])
            session = sessions.Session(id="edge-only", path=p, surface="claude")
            self.assertIsNone(sessions.mentee_dialogue_for_rationalize(session))


if __name__ == "__main__":
    unittest.main(verbosity=2)
