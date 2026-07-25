"""Pauta R1 — pauta_at(): fold puro de pauta.* (spec §6; ADR-0006 — o log é a verdade).

Distribuição realizada por célula vs uniforme (falsificador de ato1-multi-setup-vs-centro);
3+ silêncios CONSECUTIVOS da mesma célula = candidata a poda (por evidência, nunca a priori).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import pauta  # noqa: E402


def _passa_tudo(prompt):
    # Fake permissivo (o fold não testa juízo): satisfaz o check batch E o critério.
    return '{"reprova": [], "veredito": "passa", "evidencia": "ok"}'


CAND = {"tema": "t", "forma": "report", "lastro": "lido: x"}
FOG_SI = {"objeto": "si", "abordagem": "fog"}
CUR_MUNDO = {"objeto": "mundo", "abordagem": "curiosidade"}


class FoldIsTheOnlyState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "log.jsonl"
        self.addCleanup(self._tmp.cleanup)

    def _pen(self, cell, candidates, did):
        return pauta.propose(cell, candidates, dispatch_id=did,
                             completer=_passa_tudo, log=self.log)

    def test_distribution_counts_per_cell(self):
        self._pen(FOG_SI, [CAND], "d1")
        self._pen(FOG_SI, [CAND], "d2")
        self._pen(CUR_MUNDO, [], "d3")
        state = pauta.pauta_at(log=self.log)
        self.assertEqual(state["cells"]["fog-si"]["proposta"], 2)
        self.assertEqual(state["cells"]["curiosidade-mundo"]["silencio"], 1)

    def test_three_consecutive_silences_mark_poda_candidate(self):
        for did in ("d1", "d2", "d3"):
            self._pen(CUR_MUNDO, [], did)
        state = pauta.pauta_at(log=self.log)
        self.assertEqual(state["silence_streaks"]["curiosidade-mundo"], 3)
        self.assertIn("curiosidade-mundo", state["poda_candidates"])

    def test_proposta_resets_the_streak(self):
        self._pen(CUR_MUNDO, [], "d1")
        self._pen(CUR_MUNDO, [], "d2")
        self._pen(CUR_MUNDO, [CAND], "d3")
        state = pauta.pauta_at(log=self.log)
        self.assertNotIn("curiosidade-mundo", state["silence_streaks"])
        self.assertEqual(state["poda_candidates"], [])

    def test_cursor_replays_the_past(self):
        first = self._pen(FOG_SI, [CAND], "d1")
        self._pen(FOG_SI, [CAND], "d2")
        past = pauta.pauta_at(seq=first["seq"], log=self.log)
        self.assertEqual(past["cells"]["fog-si"]["proposta"], 1)

    def test_vetoes_are_counted(self):
        self._pen(FOG_SI, [CAND], "d1")
        pauta.veto("d1", "não agora", log=self.log)
        self.assertEqual(pauta.pauta_at(log=self.log)["vetoes"], 1)

    def test_empty_log_folds_to_empty_state(self):
        state = pauta.pauta_at(log=self.log)
        self.assertEqual(state["cells"], {})
        self.assertEqual(state["vetoes"], 0)
        self.assertEqual(state["recall_unavailable"], 0)
        self.assertEqual(state["voz_authority"], 0)

    def test_recall_unavailable_rate_is_the_alarm(self):
        # dig r2 #7: um piso que nunca roda vira ALARME no fold, não JSON não-lido —
        # as propostas acima rodaram SEM voz_recall_fn → recall declarado indisponível.
        self._pen(FOG_SI, [CAND], "d1")
        state = pauta.pauta_at(log=self.log)
        self.assertEqual(state["recall_unavailable"], 1)

    def test_authority_path_proposals_are_counted(self):
        # r3: autoridade deriva do log — o fixture pena o dispatch.open comandado
        eventlog.dispatch_open({"dispatch_id": "d9", "origin": "user_requested"},
                               log=self.log)
        pauta.propose(FOG_SI, [], dispatch_id="d9",
                      constraints={"origem": "voz", "tema": "X", "forma": "report"},
                      log=self.log)
        state = pauta.pauta_at(log=self.log)
        self.assertEqual(state["voz_authority"], 1)
        self.assertEqual(state["recall_unavailable"], 0)  # waive por ordem ≠ organ down


if __name__ == "__main__":
    unittest.main()
