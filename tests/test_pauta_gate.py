"""O gate ambiente do rito e da caneta de publish penduram na PROPOSTA viva (o dente — ADR-0024).

Supersede os pins da estrada morta (dispatch.theme / vf:* — o seletor-de-Voz da main morreu no
merge da Pauta): a autoridade do beat ambiente é a `pauta.proposta` que o funil julgou, nunca
âncora prévia de Voz (a Voz entra como baseline no piso delta_voz, não como pré-condição de
existência — fog nunca-abordada, curiosidade e coringa nascem sem Voz por construção).
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import pauta  # noqa: E402
import rito  # noqa: E402

CELL = {"objeto": "atividade", "abordagem": "operacional"}


def _passa_tudo(prompt):
    return '{"reprova": [], "veredito": "passa", "evidencia": "ok"}'


def _propose(log, dispatch_id="d-1", forma="report", tema="T", faceta="F"):
    cand = {"tema": tema, "forma": forma, "faceta": faceta, "lastro": "lido: x"}
    return pauta.propose(CELL, [cand], dispatch_id=dispatch_id,
                         completer=_passa_tudo, log=log)


class RitoPautaGate(unittest.TestCase):
    def test_user_requested_dispatch_needs_no_ambient_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "user_requested"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                self.assertEqual(rito._ambient_theme_review_contract("d-1", log), "")

    def test_rite_fails_before_work_when_no_live_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                with self.assertRaisesRegex(rito.StageFailure, "pauta.proposta viva"):
                    rito._ambient_theme_review_contract("d-1", log)

    def test_contract_carries_the_proposta_and_the_altitude_clause(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            _propose(log, tema="fila de fechamento", faceta="dono do fechamento")
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                contract = rito._ambient_theme_review_contract("d-1", log)
            self.assertIn("fila de fechamento", contract)
            self.assertIn("dono do fechamento", contract)
            self.assertIn("operacional x atividade", contract)
            # a cláusula de altitude do operador sobrevive intacta à troca de autoridade
            self.assertIn("Mere subject overlap is insufficient", contract)
            self.assertIn("delegated agent's implementation altitude", contract)
            self.assertIn("human's purpose, decision horizon, and vocabulary", contract)

    def test_contract_names_the_signed_gate_elements(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            _propose(log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                contract = rito._ambient_theme_review_contract("d-1", log)
            self.assertIn("pauta-tabela-normativa.md", contract)
            self.assertIn("never as named sections", contract)


class PublishPenDente(unittest.TestCase):
    def test_canonical_publish_gate_rejects_beat_without_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "no-proposta"):
                    eventlog.publish_artefato_atomic(
                        "artifact", "why", log=log, dispatch_id="d-1", require_wake=True)

    def test_canonical_publish_gate_accepts_live_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            _propose(log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                published, _kernel = eventlog.publish_artefato_atomic(
                    "artifact", "why", log=log, dispatch_id="d-1", require_wake=True)
            self.assertEqual(published["type"], "artefato.published")

    def test_user_requested_publish_needs_no_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "user_requested"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                published, _kernel = eventlog.publish_artefato_atomic(
                    "artifact", "why", log=log, dispatch_id="d-1", require_wake=True)
            self.assertEqual(published["type"], "artefato.published")

    def test_dead_road_functions_are_gone(self):
        for fn in ("dispatch_theme_for", "record_dispatch_theme", "dispatch_theme_is_grounded"):
            self.assertFalse(hasattr(eventlog, fn), fn)


if __name__ == "__main__":
    unittest.main()
