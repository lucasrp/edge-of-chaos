"""Vertical acceptances for mechanical Activity↔Direction reconciliation."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import portfolio  # noqa: E402


class PortfolioReconcile(unittest.TestCase):
    def _closed_ticket_and_activity(self, log, operation):
        opened_map = eventlog.open_map(
            operacao=operation, titulo=f"Mapa {operation}", rationale="Orientar",
            dispatch_id=f"open-{operation}", author="operador", log=log,
        )
        map_ref = f"{operation}/{opened_map['payload']['num']}"
        opened_ticket = eventlog.open_ticket(
            map=map_ref, titulo="Decisão", question="Qual caminho?",
            rationale="Decidir", dispatch_id=f"open-{operation}",
            author="operador", log=log,
        )
        ticket_ref = f"{operation}/{opened_ticket['payload']['num']}"
        opened_activity = eventlog.open_atividade(
            operacao=operation, finalidade="Produzir evidência",
            tier="asserted", author="operador", log=log,
        )
        activity_ref = f"{operation}/{opened_activity['payload']['num']}"
        eventlog.close_ticket(
            ref=ticket_ref, resolucao="Decidido", valencia="supports",
            bears_on=[{"alvo": activity_ref, "valencia": "supports"}],
            rationale="Decisão tomada", dispatch_id=f"close-{operation}",
            author="operador", log=log,
        )
        return opened_ticket, ticket_ref, activity_ref

    def test_touch_after_activity_closure_proposes_contest_without_reopening_a8(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Fechar sem congelar evidência",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=activity_ref, estado="cumprida", julgamento="Entrega concluída",
                tier="asserted", author="operador", log=log,
            )
            eventlog.touch_atividade(
                ref=activity_ref, sessao="late-session", novo="Contradição nova",
                tier="llm_judged", log=log,
            )

            portfolio.reconcile(log)

            activity = eventlog.atividades_at(log=log)[activity_ref]
            proposals = eventlog.wayfinds_at(log=log)["moves"]["propostos"]
            self.assertEqual(activity["estado"], "cumprida")
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["kind"], "contest")
            self.assertEqual(proposals[0]["alvo"], opened["payload"]["ulid"])
            self.assertEqual(proposals[0]["effect"]["event_type"], "contest.raised")

    def test_touch_on_activity_bearing_on_closed_ticket_contests_the_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            opened_ticket = eventlog.open_ticket(
                map=map_ref, titulo="Decisão", question="Qual caminho?",
                rationale="Decidir", dispatch_id="d1", author="operador", log=log,
            )
            ticket_ref = f"edge/{opened_ticket['payload']['num']}"
            opened_activity = eventlog.open_atividade(
                operacao="edge", finalidade="Executar decisão",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened_activity['payload']['num']}"
            eventlog.close_ticket(
                ref=ticket_ref, resolucao="Decidido", valencia="supports",
                bears_on=[{"alvo": activity_ref, "valencia": "supports"}],
                rationale="Decisão tomada", dispatch_id="d2",
                author="operador", log=log,
            )
            eventlog.bears_on(
                ref=activity_ref, alvo=ticket_ref, valencia="supports",
                tier="asserted", log=log,
            )
            eventlog.touch_atividade(
                ref=activity_ref, sessao="rework", novo="Decisão precisa revisão",
                tier="llm_judged", log=log,
            )

            portfolio.reconcile(log)

            proposals = eventlog.wayfinds_at(log=log)["moves"]["propostos"]
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["kind"], "contest")
            self.assertEqual(proposals[0]["alvo"], opened_ticket["payload"]["ulid"])

    def test_stitch_matches_only_a_full_ticket_ref_across_operations_a31(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket_a, ticket_ref_a, activity_ref_a = self._closed_ticket_and_activity(
                log, "op-a"
            )
            self._closed_ticket_and_activity(log, "op-b")
            eventlog.touch_atividade(
                ref=activity_ref_a, sessao="s1", novo="Reabrir a decisão",
                tier="llm_judged", log=log,
            )
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {
                    "sessao_id": "s1", "operacoes": ["op-a"],
                    "stitch": {
                        "goal": "Revisar", "acao": "Testar",
                        "entidades": [ticket_ref_a, "tkt-001"],
                    },
                    "epistemico": {"presuncoes": []},
                },
                log=log,
            )

            result = portfolio.reconcile(log)

            proposals = eventlog.wayfinds_at(log=log)["moves"]["propostos"]
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["kind"], "contest")
            self.assertEqual(proposals[0]["alvo"], ticket_a["payload"]["ulid"])
            self.assertNotIn(activity_ref_a,
                             {item["ref"] for item in result["sem_mapa"]})

    def test_refuting_run_flags_ticket_subscribed_to_the_hypothesis_a18(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            hypothesis = eventlog.declare_hypothesis(
                "A abordagem melhora accuracy",
                {"metric": "accuracy", "threshold": 0.8, "direction": "maior"},
                log=log,
            )
            hypothesis_ulid = hypothesis["payload"]["ulid"]
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Testar hipótese",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            opened_ticket = eventlog.open_ticket(
                map=map_ref, titulo="Cobrar hipótese", question="Ela se sustenta?",
                rationale="Falsificador explícito", dispatch_id="d1",
                author="operador", inscricao=hypothesis_ulid, log=log,
            )
            opened_activity = eventlog.open_atividade(
                operacao="edge", finalidade="Executar holdout",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened_activity['payload']['num']}"
            opened_run = eventlog.open_run(
                atividades=[activity_ref], config={"split": "holdout"},
                eval={"metric": "accuracy", "predicao": "sobe"},
                tier="asserted", log=log,
            )
            run_ref = f"edge/{opened_run['payload']['num']}"
            eventlog.close_run(
                ref=run_ref, resultado="accuracy 0.62",
                bears_on=[{"alvo": hypothesis_ulid, "valencia": "refutes"}],
                tier="asserted", log=log,
            )

            portfolio.reconcile(log)

            proposals = eventlog.wayfinds_at(log=log)["moves"]["propostos"]
            self.assertEqual(len(proposals), 1)
            move = proposals[0]
            self.assertEqual(move["kind"], "falsificador_aconteceu")
            self.assertEqual(move["alvo"], opened_ticket["payload"]["ulid"])
            self.assertIn(hypothesis_ulid, move["effect"]["payload"]["detalhe"])
            self.assertIn(opened_run["payload"]["ulid"], move["evidencia"])

    def test_reconcile_is_idempotent_for_the_same_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Detectar retrabalho",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Concluída",
                tier="asserted", author="operador", log=log,
            )
            eventlog.touch_atividade(
                ref=ref, sessao="late", novo="Novo dado",
                tier="llm_judged", log=log,
            )

            first = portfolio.reconcile(log)
            second = portfolio.reconcile(log)

            self.assertEqual(len(first["emitted"]), 1)
            self.assertEqual(second["emitted"], [])
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)

    def test_pinned_decline_is_never_reproposed_a16(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Não insistir após pin",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Concluída",
                tier="asserted", author="operador", log=log,
            )
            eventlog.touch_atividade(
                ref=ref, sessao="late", novo="Novo dado",
                tier="llm_judged", log=log,
            )
            proposed = portfolio.reconcile(log)["emitted"][0]
            eventlog.decline_move(
                ref=proposed["payload"]["ulid"], reason="Não reabrir esta questão",
                dispatch_id="decline-pin", author="grill", pin=True, log=log,
            )

            result = portfolio.reconcile(log)

            self.assertEqual(result["emitted"], [])
            folded = eventlog.wayfinds_at(log=log)
            self.assertEqual(folded["moves"]["propostos"], [])
            self.assertEqual(len(folded["moves"]["declinados"]), 1)
            self.assertIn(proposed["payload"]["move_key"], folded["pins"])

    def test_concurrent_reconcilers_land_one_proposal_a26(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="CAS do reconciliador",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Concluída",
                tier="asserted", author="operador", log=log,
            )
            eventlog.touch_atividade(
                ref=ref, sessao="late", novo="Novo dado",
                tier="llm_judged", log=log,
            )
            rendezvous = threading.Barrier(2)
            results = []

            def worker():
                rendezvous.wait(timeout=2)
                results.append(portfolio.reconcile(log))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(sorted(len(result["emitted"]) for result in results), [0, 1])
            self.assertTrue(all(result["sem_mapa"] == [] for result in results))
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)

    def test_unmapped_work_below_threshold_is_only_a_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_map(
                operacao="edge", titulo="Mapa disponível", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Trabalho ainda não mapeado",
                eval={"regua": "resultado observável"},
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            eventlog.touch_atividade(
                ref=activity_ref, sessao="s1", novo="Primeiro avanço",
                tier="llm_judged", log=log,
            )

            result = portfolio.reconcile(log)

            self.assertEqual(result["emitted"], [])
            self.assertEqual(result["sem_mapa"], [{
                "ref": activity_ref, "operacao": "edge", "motivo": "largada",
            }])
            self.assertEqual(eventlog.read(types=["move.proposed"], log=log), [])

    def test_falsifiable_unmapped_work_after_two_sessions_proposes_ticket_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa único", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            opened_activity = eventlog.open_atividade(
                operacao="edge", finalidade="Trabalho cobrável sem ticket",
                eval={"regua": "resultado observável"},
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened_activity['payload']['num']}"
            for session in ("s1", "s2"):
                eventlog.touch_atividade(
                    ref=activity_ref, sessao=session, novo=f"avanço {session}",
                    tier="llm_judged", log=log,
                )

            result = portfolio.reconcile(log)

            self.assertEqual(result["sem_mapa"], [])
            self.assertEqual(len(result["emitted"]), 1)
            move = result["emitted"][0]["payload"]
            self.assertEqual(move["kind"], "ticket.open")
            self.assertEqual(move["alvo"], opened_map["payload"]["ulid"])
            self.assertEqual(move["effect"]["payload"]["map"],
                             opened_map["payload"]["ulid"])
            self.assertEqual(move["effect"]["payload"]["tier"], "llm_judged")
            self.assertEqual(eventlog.wayfinds_at(log=log)["tickets"], {})

    def test_ticket_open_reconciliation_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_map(
                operacao="edge", titulo="Mapa único", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Trabalho cobrável",
                eval={"regua": "resultado observável"},
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            for session in ("s1", "s2"):
                eventlog.touch_atividade(
                    ref=activity_ref, sessao=session, novo=session,
                    tier="llm_judged", log=log,
                )

            first = portfolio.reconcile(log)
            second = portfolio.reconcile(log)

            self.assertEqual(len(first["emitted"]), 1)
            self.assertEqual(second["emitted"], [])
            proposals = eventlog.read(types=["move.proposed"], log=log)
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["payload"]["effect"]["payload"]["num"],
                             "tkt-001")

    def test_concurrent_ticket_open_reconcilers_land_one_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_map(
                operacao="edge", titulo="Mapa único", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Trabalho cobrável concorrente",
                eval={"regua": "resultado observável"},
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            for session in ("s1", "s2"):
                eventlog.touch_atividade(
                    ref=activity_ref, sessao=session, novo=session,
                    tier="llm_judged", log=log,
                )
            rendezvous = threading.Barrier(2)
            results = []

            def worker():
                rendezvous.wait(timeout=2)
                results.append(portfolio.reconcile(log))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(sorted(len(result["emitted"]) for result in results), [0, 1])
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)

    def test_two_sessions_without_eval_remain_a_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_map(
                operacao="edge", titulo="Mapa único", rationale="Orientar",
                dispatch_id="d1", author="operador", log=log,
            )
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Saliência sem régua",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            for session in ("s1", "s2"):
                eventlog.touch_atividade(
                    ref=activity_ref, sessao=session, novo=session,
                    tier="llm_judged", log=log,
                )

            result = portfolio.reconcile(log)

            self.assertEqual(result["emitted"], [])
            self.assertEqual(result["sem_mapa"][0]["ref"], activity_ref)

    def test_unmapped_touches_without_new_state_are_signaled_as_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Atividade girando",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            for session in ("s1", "s2"):
                eventlog.touch_atividade(
                    ref=activity_ref, sessao=session, tier="llm_judged", log=log,
                )

            result = portfolio.reconcile(log)

            self.assertEqual(result["sem_mapa"], [{
                "ref": activity_ref, "operacao": "edge", "motivo": "loop",
            }])

    def test_bearing_and_stitch_for_same_rework_converge_to_one_contest(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, ticket_ref, activity_ref = self._closed_ticket_and_activity(log, "edge")
            eventlog.bears_on(
                ref=activity_ref, alvo=ticket_ref, valencia="supports",
                tier="asserted", log=log,
            )
            eventlog.touch_atividade(
                ref=activity_ref, sessao="s1", novo="Revisão",
                tier="llm_judged", log=log,
            )
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {
                    "sessao_id": "s1", "operacoes": ["edge"],
                    "stitch": {"goal": "Revisar", "acao": "Testar",
                               "entidades": [ticket_ref]},
                    "epistemico": {"presuncoes": []},
                },
                log=log,
            )

            portfolio.reconcile(log)

            proposals = eventlog.wayfinds_at(log=log)["moves"]["propostos"]
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["alvo"], ticket["payload"]["ulid"])


if __name__ == "__main__":
    unittest.main()
