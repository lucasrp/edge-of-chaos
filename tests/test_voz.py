"""Voz inbox — fold do log em pendência + disposição (Story 1, canal nativo).

Seams sob teste (acordados): fold_voz (puro), dispose (único escritor), voz_at (leitor).
Roda direto: python3 tests/test_voz.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import voz  # noqa: E402


def _ev(seq, type_, subject, payload):
    return {"seq": seq, "ts": f"2026-07-01T00:00:{seq:02d}+00:00",
            "type": type_, "subject": subject, "payload": payload}


class TestFoldPending(unittest.TestCase):
    def test_vote_and_comment_become_pending_signals_and_non_voz_ignored(self):
        events = [
            _ev(1, "artefato.published", "artefato", {"slug": "x"}),
            _ev(2, "voz.vote", "voz:my-slug", {"slug": "my-slug", "value": 1}),
            _ev(3, "voz.comment", "voz:my-slug",
                {"slug": "my-slug", "text": "foca no schema, não no recall"}),
            _ev(4, "episode", "session:abc", {"chars": 10}),
        ]
        state = voz.fold_voz(events)
        pending = state["pending"]
        self.assertEqual([s["seq"] for s in pending], [2, 3])

        vote = pending[0]
        self.assertEqual(vote["channel"], "native")
        self.assertEqual(vote["act"], "vote")
        self.assertEqual(vote["target"], "my-slug")
        self.assertEqual(vote["value"], 1)
        self.assertEqual(vote["required"], "receipt")

        comment = pending[1]
        self.assertEqual(comment["act"], "comment")
        self.assertEqual(comment["text"], "foca no schema, não no recall")
        self.assertEqual(comment["required"], "semantic")


class TestDispositionCloses(unittest.TestCase):
    def _base(self):
        return [
            _ev(2, "voz.vote", "voz:my-slug", {"slug": "my-slug", "value": 1}),
            _ev(3, "voz.comment", "voz:my-slug", {"slug": "my-slug", "text": "steer"}),
        ]

    def test_receipt_closes_vote_but_not_comment(self):
        events = self._base() + [
            _ev(5, "voz.disposition", "voz:2", {"of": 2, "state": "receipt_sent"}),
            _ev(6, "voz.disposition", "voz:3", {"of": 3, "state": "receipt_sent"}),
        ]
        pending = voz.fold_voz(events)["pending"]
        # o voto fechou com recibo; o comentário SEGUE pendente — recibo não fecha semântica
        self.assertEqual([s["seq"] for s in pending], [3])

    def test_semantic_answer_and_dead_letter_close_comment(self):
        answered = self._base() + [
            _ev(5, "voz.disposition", "voz:3",
                {"of": 3, "state": "semantic_answered", "ref": "some-artefato"}),
        ]
        self.assertEqual([s["seq"] for s in voz.fold_voz(answered)["pending"]], [2])

        parked = self._base() + [
            _ev(5, "voz.disposition", "voz:3",
                {"of": 3, "state": "dead_lettered", "reason": "obsoleto: alvo despublicado"}),
        ]
        self.assertEqual([s["seq"] for s in voz.fold_voz(parked)["pending"]], [2])


class TestDispose(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_dispose_appends_disposition_event_read_back_by_voz_at(self):
        import eventlog
        eventlog.append("voz.comment", "voz:my-slug",
                        {"slug": "my-slug", "text": "steer"}, log=self.log)
        state = voz.voz_at(log=self.log)
        self.assertEqual(len(state["pending"]), 1)
        seq = state["pending"][0]["seq"]

        voz.dispose(seq, "semantic_answered", ref="reply-artefato", log=self.log)
        after = voz.voz_at(log=self.log)
        self.assertEqual(after["pending"], [])
        self.assertEqual(after["dispositions"][seq][0]["state"], "semantic_answered")
        self.assertEqual(after["dispositions"][seq][0]["ref"], "reply-artefato")

    def test_dispose_fails_loud_on_bad_state_and_reasonless_dead_letter(self):
        with self.assertRaises(ValueError):
            voz.dispose(1, "answered", log=self.log)  # estado fora da máquina
        with self.assertRaises(ValueError):
            voz.dispose(1, "dead_lettered", log=self.log)  # dead-letter exige motivo


class TestReplayAndChat(unittest.TestCase):
    def test_fold_is_deterministic_replay_and_chat_comment_targets_chat(self):
        events = [
            _ev(2, "voz.comment", "voz:chat", {"text": "pergunta solta no chat"}),
            _ev(3, "voz.disposition", "voz:2", {"of": 2, "state": "receipt_sent"}),
        ]
        first, second = voz.fold_voz(events), voz.fold_voz(events)
        self.assertEqual(first, second)  # mesmo log → mesmo estado (drain idempotente)
        self.assertEqual(first["pending"][0]["target"], "chat")
        self.assertEqual(first["pending"][0]["required"], "semantic")


class TestBrief(unittest.TestCase):
    def test_empty_pending_yields_empty_brief(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(voz.brief(log=Path(d) / "log.jsonl"), "")

    def test_brief_is_bounded_counts_plus_oneliners(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.jsonl"
            import eventlog
            eventlog.append("voz.vote", "voz:my-slug",
                            {"slug": "my-slug", "value": 1}, log=log)
            eventlog.append("voz.comment", "voz:my-slug",
                            {"slug": "my-slug", "text": "x" * 500}, log=log)
            text = voz.brief(log=log, top=5)
            self.assertIn("2 pendente", text)       # contagem
            self.assertIn("1 voto", text)
            self.assertIn("1 comentário", text)
            self.assertIn("my-slug", text)          # one-liner com alvo
            self.assertLess(len(text), 600)         # bounded: nunca despeja o texto inteiro


class TestCloseCycle(unittest.TestCase):
    def setUp(self):
        import tempfile
        import eventlog
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.jsonl"
        eventlog.append("voz.vote", "voz:a", {"slug": "a", "value": 1}, log=self.log)
        self.vote_seq = 1
        eventlog.append("voz.comment", "voz:a", {"slug": "a", "text": "responde isso"},
                        log=self.log)
        self.comment_seq = 2
        eventlog.append("voz.comment", "voz:b", {"slug": "b", "text": "e isso"},
                        log=self.log)
        self.other_seq = 3

    def tearDown(self):
        self.tmp.cleanup()

    def test_close_cycle_disposes_everything_pending(self):
        voz.close_cycle(answered={self.comment_seq: "reply-artefato"}, log=self.log)
        state = voz.voz_at(log=self.log)
        # voto fechou; comentário respondido fechou com ref; o outro segue pendente com recibo
        self.assertEqual([s["seq"] for s in state["pending"]], [self.other_seq])
        self.assertEqual(state["dispositions"][self.comment_seq][0]["state"],
                         "semantic_answered")
        self.assertEqual(state["dispositions"][self.comment_seq][0]["ref"], "reply-artefato")
        self.assertEqual(state["dispositions"][self.other_seq][0]["state"], "receipt_sent")

    def test_close_cycle_is_idempotent_no_receipt_spam(self):
        first = voz.close_cycle(log=self.log)
        second = voz.close_cycle(log=self.log)
        self.assertTrue(first)          # primeiro ciclo grava recibos
        self.assertEqual(second, [])    # re-run não duplica nada
        state = voz.voz_at(log=self.log)
        self.assertEqual(len(state["dispositions"][self.comment_seq]), 1)


class TestGate(unittest.TestCase):
    def test_gate_raises_on_receiptless_voz_and_passes_after_close_cycle(self):
        import tempfile
        import eventlog
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.jsonl"
            eventlog.append("voz.comment", "voz:a", {"slug": "a", "text": "oi"}, log=log)
            with self.assertRaises(voz.VozUnreceived) as ctx:
                voz.assert_all_received(log=log)
            self.assertIn("seq 1", str(ctx.exception))
            voz.close_cycle(log=log)
            voz.assert_all_received(log=log)  # não levanta: tudo tem ao menos recibo


class TestAdr17Reconciliation(unittest.TestCase):
    def test_grill_resolved_comment_is_not_pending(self):
        # ADR-0017: o grill fecha um chat com voz.resolved {comment_id, outcome} —
        # o fold TEM que honrar esse terminal, senão o brief nagaria pra sempre.
        events = [
            _ev(2, "voz.comment", "voz:a",
                {"slug": "a", "text": "steer", "comment_id": "c-123"}),
            _ev(5, "voz.resolved", "voz:a",
                {"comment_id": "c-123", "outcome": "replied"}),
        ]
        self.assertEqual(voz.fold_voz(events)["pending"], [])


class TestPredispatchWiring(unittest.TestCase):
    def test_briefing_carries_voz_section_when_pending_and_stays_clean_when_not(self):
        import tempfile
        import eventlog
        import predispatch
        fns = dict(sweep_fn=lambda: 0, briefing_fn=lambda: "BRIEFING",
                   recall_fn=lambda: "RECALL")
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.jsonl"
            briefing, _ = predispatch.run(log=log, **fns)
            self.assertEqual(briefing, "BRIEFING")  # sem pendência, briefing intacto
            eventlog.append("voz.comment", "voz:a", {"slug": "a", "text": "oi"}, log=log)
            briefing, _ = predispatch.run(log=log, **fns)
            self.assertIn("BRIEFING", briefing)
            self.assertIn("Voz pendente", briefing)


if __name__ == "__main__":
    unittest.main()
