"""A25 — falha de instrumento condiciona somente a leva correspondente."""

import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402


class InstrumentFailureA25(unittest.TestCase):
    def _fixture(self, log):
        activity_event = eventlog.open_atividade(
            operacao="edge", finalidade="medir duas levas",
            tier="asserted", author="operador", log=log,
        )
        activity = f"edge/{activity_event['payload']['num']}"
        runs = {}
        facts = {}
        for batch in ("leva-suspeita", "leva-controle"):
            run_event = eventlog.open_run(
                atividades=[activity], config={"leva": batch},
                eval={"metric": "accuracy", "predicao": "sobe"},
                leva=batch, tier="asserted", log=log,
            )
            run_ref = f"edge/{run_event['payload']['num']}"
            fact_event = eventlog.observe_fato(
                atividade=activity, run=run_ref, leva=batch,
                body=f"resultado de {batch}",
                medida={"valor": 1, "como": "fixture"},
                tier="asserted", log=log,
            )
            runs[batch] = run_ref
            facts[batch] = f"edge/{fact_event['payload']['num']}"
        return activity, runs, facts

    def test_same_batch_runs_and_facts_become_suspect_without_contaminating_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _activity, runs, facts = self._fixture(log)

            failure = eventlog.instrument_failure(
                instrumento="playwright", leva="leva-suspeita",
                detalhe="browser encerrou antes da coleta", log=log,
            )

            self.assertEqual(failure["type"], "instrumento.falhou")
            self.assertEqual(failure["subject"], "leva:leva-suspeita")
            self.assertEqual(failure["payload"], {
                "instrumento": "playwright",
                "leva": "leva-suspeita",
                "detalhe": "browser encerrou antes da coleta",
            })
            folded_runs = eventlog.runs_at(log=log)
            folded_facts = eventlog.fatos_at(log=log)
            self.assertEqual(
                folded_runs[runs["leva-suspeita"]]["admissibilidade"], "suspeita"
            )
            self.assertEqual(
                folded_facts[facts["leva-suspeita"]]["admissibilidade"], "suspeita"
            )
            self.assertIsNone(folded_runs[runs["leva-controle"]]["admissibilidade"])
            self.assertIsNone(folded_facts[facts["leva-controle"]]["admissibilidade"])

            before_failure = failure["seq"] - 1
            self.assertIsNone(
                eventlog.runs_at(seq=before_failure, log=log)
                [runs["leva-suspeita"]]["admissibilidade"]
            )
            self.assertIsNone(
                eventlog.fatos_at(seq=before_failure, log=log)
                [facts["leva-suspeita"]]["admissibilidade"]
            )

    def test_pen_rejects_every_blank_field_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for field in ("instrumento", "leva", "detalhe"):
                with self.subTest(field=field):
                    values = {
                        "instrumento": "playwright",
                        "leva": "leva-1",
                        "detalhe": "sem saída",
                    }
                    values[field] = " "
                    before = log.read_bytes() if log.exists() else b""

                    with self.assertRaisesRegex(ValueError, field):
                        eventlog.instrument_failure(log=log, **values)

                    after = log.read_bytes() if log.exists() else b""
                    self.assertEqual(after, before)

    def test_corrupt_failure_event_is_fail_dark_and_does_not_mark_the_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _activity, runs, facts = self._fixture(log)
            eventlog.append(
                "instrumento.falhou", "leva:leva-suspeita",
                {"instrumento": "playwright", "leva": ["tipo-inválido"],
                 "detalhe": "quebrado"},
                log=log,
            )

            self.assertIsNone(
                eventlog.runs_at(log=log)[runs["leva-suspeita"]]["admissibilidade"]
            )
            self.assertIsNone(
                eventlog.fatos_at(log=log)[facts["leva-suspeita"]]["admissibilidade"]
            )

    def test_corrupt_batch_types_on_evidence_are_skipped_fail_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _activity, runs, facts = self._fixture(log)
            events = eventlog.read(log=log)
            corrupt_run = dict(next(
                event["payload"] for event in events if event["type"] == "run.opened"
            ))
            corrupt_run.update({
                "ulid": "corrupt-run", "num": "run-999", "leva": ["inválida"]
            })
            corrupt_fact = dict(next(
                event["payload"] for event in events if event["type"] == "fato.observed"
            ))
            corrupt_fact.update({
                "ulid": "corrupt-fact", "num": "fat-999", "leva": {"inválida": True}
            })
            eventlog.append("run.opened", "run:corrupt-run", corrupt_run, log=log)
            eventlog.append("fato.observed", "fato:corrupt-fact", corrupt_fact, log=log)

            folded_runs = eventlog.runs_at(log=log)
            folded_facts = eventlog.fatos_at(log=log)

            self.assertNotIn("edge/run-999", folded_runs)
            self.assertNotIn("edge/fat-999", folded_facts)
            self.assertIn(runs["leva-suspeita"], folded_runs)
            self.assertIn(facts["leva-suspeita"], folded_facts)


if __name__ == "__main__":
    unittest.main()
