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


if __name__ == "__main__":
    unittest.main(verbosity=2)
