"""Vertical acceptances for the pure portfolio bisection selector."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import portfolio  # noqa: E402
import racionalizador  # noqa: E402


def _write_seven_node_tree(log, operation="alpha"):
    arc = eventlog.open_arco(
        operacao=operation, nome="Escolher abordagem",
        tier="asserted", author="operador", log=log,
    )
    arc_ref = f"{operation}/{arc['payload']['num']}"

    for index in range(2):
        activity = eventlog.open_atividade(
            operacao=operation, finalidade=f"Testar ramo {index}",
            eval={"regua": f"evidência do ramo {index}"}, arco=arc_ref,
            tier="asserted", author="operador", log=log,
        )
        activity_ref = f"{operation}/{activity['payload']['num']}"
        run = eventlog.open_run(
            atividades=[activity_ref], config={"ramo": index},
            eval={"metric": "accuracy", "predicao": "sobe"},
            tier="asserted", log=log,
        )
        run_ref = f"{operation}/{run['payload']['num']}"
        eventlog.observe_fato(
            atividade=activity_ref, run=run_ref,
            body=f"Resultado do ramo {index}",
            medida={"valor": index, "como": "fixture"},
            tier="asserted", log=log,
        )

    eventlog.close_arco(
        ref=arc_ref, valencia="supports", julgamento="Ramos comparados",
        tier="asserted", log=log,
    )
    return arc_ref


class PortfolioBisect(unittest.TestCase):
    def test_seven_node_tree_asks_the_root_question_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root_ref = _write_seven_node_tree(log)

            self.assertEqual(len(eventlog.presumptions_at(log=log)["nodes"]), 7)
            self.assertEqual(portfolio.bisect("alpha", log)[0]["ref"], root_ref)

    def test_questions_are_filtered_to_the_requested_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _write_seven_node_tree(log, "alpha")
            _write_seven_node_tree(log, "beta")

            questions = portfolio.bisect("alpha", log)

            self.assertEqual(len(questions), 7)
            self.assertTrue(all(question["ref"].startswith("alpha/")
                                for question in questions))

    def test_dependencyless_session_presumption_uses_explicit_operation_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {
                    "sessao_id": "s1", "operacoes": ["alpha"],
                    "epistemico": {"presuncoes": [{
                        "texto": "Presunção sem dependência",
                        "confirmaria": "evidência A", "refutaria": "evidência B",
                    }]},
                },
                log=log,
            )

            alpha = portfolio.bisect("alpha", log)
            beta = portfolio.bisect("beta", log)

            self.assertEqual([item.get("texto") for item in alpha],
                             ["Presunção sem dependência"])
            self.assertEqual(beta, [])

    def test_dependency_does_not_override_explicit_operation_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _write_seven_node_tree(log, "alpha")
            output = {
                "operacoes": ["beta"],
                "stitch": {"goal": "Comparar", "acao": "Medir", "entidades": []},
                "epistemico": {"presuncoes": [{
                    "texto": "Presunção beta ligada a evidência alpha",
                    "confirmaria": "evidência C", "refutaria": "evidência D",
                    "depende_de": "alpha/run-001",
                }]},
                "organizacional": {"enderecos": []},
            }
            result = racionalizador.rationalize(
                "s1", [{"role": "user", "text": "compare os resultados"}],
                lambda _prompt: output, log=log,
            )
            self.assertEqual(len(result["emitted"]), 1)

            alpha_texts = {item.get("texto") for item in portfolio.bisect("alpha", log)}
            beta_texts = {item.get("texto") for item in portfolio.bisect("beta", log)}

            self.assertNotIn("Presunção beta ligada a evidência alpha", alpha_texts)
            self.assertIn("Presunção beta ligada a evidência alpha", beta_texts)

    def test_organizational_metadata_never_becomes_a_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _write_seven_node_tree(log, "alpha")
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {
                    "sessao_id": "s1",
                    "operacoes": ["alpha"],
                    "epistemico": {"presuncoes": [{
                        "texto": "O resultado generaliza",
                        "confirmaria": "novo holdout",
                        "refutaria": "regressão",
                        "depende_de": "alpha/run-001",
                    }]},
                    "organizacional": {"enderecos": [{
                        "atividade": "alpha/atv-001",
                        "path": "ORGANIZACIONAL-NAO-EPISTEMICO",
                        "papel": "implementation",
                    }]},
                },
                log=log,
            )

            folded = eventlog.presumptions_at(log=log)
            questions = portfolio.bisect("alpha", log)

            self.assertIn("O resultado generaliza",
                          {node.get("texto") for node in folded["nodes"].values()})
            self.assertIn("O resultado generaliza",
                          {question.get("texto") for question in questions})
            self.assertNotIn("ORGANIZACIONAL-NAO-EPISTEMICO",
                             json.dumps(folded, ensure_ascii=False))
            self.assertNotIn("ORGANIZACIONAL-NAO-EPISTEMICO",
                             json.dumps(questions, ensure_ascii=False))

    def test_order_is_deterministic_and_selection_does_not_write_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _write_seven_node_tree(log, "alpha")
            events_before = eventlog.read(log=log)

            first = portfolio.bisect("alpha", log)
            second = portfolio.bisect("alpha", log)

            self.assertEqual(first, second)
            self.assertEqual([question["ref"] for question in first], [
                "alpha/arc-001",
                "alpha/atv-001", "alpha/atv-002",
                "alpha/run-001", "alpha/run-002",
                "alpha/fat-001", "alpha/fat-002",
            ])
            self.assertEqual(eventlog.read(log=log), events_before)


if __name__ == "__main__":
    unittest.main()
