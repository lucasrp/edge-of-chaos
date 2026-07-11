"""Vertical acceptances for the bounded wake portfolio brief."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import portfolio  # noqa: E402


class PortfolioBrief(unittest.TestCase):
    def test_empty_brief_has_a_stable_shape_from_exactly_one_cursor_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.object(eventlog, "read", wraps=eventlog.read) as read:
                brief = portfolio.portfolio_at(
                    seq=7, log=log, top_k=2, agenda_k=1,
                )

            self.assertEqual(brief, {
                "mapas_ativos": [],
                "atividades": [],
                "atividades_perdidas": [],
                "tickets": [],
                "runs": [],
                "fatos": [],
                "presuncoes": [],
                "sem_mapa": [],
                "canon": [],
                "agenda": [],
                "contested": [],
                "admissibilidade": [],
            })
            read.assert_called_once_with(until_seq=7, until_ts=None, log=log)

    def test_active_maps_carry_computed_frontiers_while_paused_maps_stay_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            active = eventlog.open_map(
                operacao="edge", titulo="Mapa vivo", rationale="Trabalho atual",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{active['payload']['num']}"
            first = eventlog.open_ticket(
                map=map_ref, titulo="Primeiro", question="Q1?", rationale="R1",
                dispatch_id="d1", author="operador", tier="asserted", log=log,
            )
            first_ref = f"edge/{first['payload']['num']}"
            second = eventlog.open_ticket(
                map=map_ref, titulo="Segundo", question="Q2?", rationale="R2",
                blocked_by=[first_ref], dispatch_id="d1", author="operador",
                tier="asserted", log=log,
            )
            second_ref = f"edge/{second['payload']['num']}"
            paused = eventlog.open_map(
                operacao="edge", titulo="Mapa pausado", rationale="Fora de cena",
                dispatch_id="d1", author="operador", log=log,
            )
            paused_ref = f"edge/{paused['payload']['num']}"
            eventlog.set_map_state(
                ref=paused_ref, estado="pausado", rationale="Pausar",
                dispatch_id="d1", author="operador", log=log,
            )

            brief = portfolio.portfolio_at(log=log, top_k=10, agenda_k=5)

            self.assertEqual(brief["mapas_ativos"], [{
                "ref": map_ref,
                "titulo": "Mapa vivo",
                "frontier": [[first_ref], [second_ref]],
            }])

    def test_top_k_is_one_common_lane_ranked_by_latest_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            old = eventlog.open_atividade(
                operacao="edge", finalidade="Atividade antiga",
                tier="asserted", author="operador", log=log,
            )
            old_ref = f"edge/{old['payload']['num']}"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Organizar",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            ticket = eventlog.open_ticket(
                map=map_ref, titulo="Ticket recente", question="Q?", rationale="R",
                dispatch_id="d1", author="operador", tier="asserted", log=log,
            )
            ticket_ref = f"edge/{ticket['payload']['num']}"
            current = eventlog.open_atividade(
                operacao="edge", finalidade="Atividade atual",
                tier="asserted", author="operador", log=log,
            )
            current_ref = f"edge/{current['payload']['num']}"
            eventlog.touch_atividade(
                ref=current_ref, sessao="s1", novo="Mais recente",
                tier="asserted", log=log,
            )

            brief = portfolio.portfolio_at(log=log, top_k=2, agenda_k=1)

            self.assertEqual([item["ref"] for item in brief["atividades"]], [current_ref])
            self.assertEqual([item["ref"] for item in brief["tickets"]], [ticket_ref])
            self.assertNotIn(old_ref, [item["ref"] for item in brief["atividades"]])

    def test_a9_lost_activity_is_a_canonical_wake_signal_and_sem_mapa_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Retomar o trabalho esquecido",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            for session, operations in (
                ("s1", ["edge"]), ("other", ["juridico"]), ("s2", ["edge"]),
            ):
                eventlog.append(
                    "sessao.racionalizada", f"sessao:{session}",
                    {"sessao_id": session, "operacoes": operations}, log=log,
                )

            brief = portfolio.portfolio_at(log=log, top_k=1, agenda_k=1)

            self.assertEqual(brief["atividades_perdidas"], [{
                "ref": activity_ref,
                "finalidade": "Retomar o trabalho esquecido",
                "sessoes_sem_toque": 2,
            }])
            self.assertEqual(brief["sem_mapa"], [{
                "ref": activity_ref, "operacao": "edge", "motivo": "largada",
            }])

    def test_a25_admissibility_surfaces_only_runs_and_facts_from_the_failed_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Medir duas levas",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            refs = {}
            for batch in ("suspeita", "controle"):
                run = eventlog.open_run(
                    atividades=[activity_ref], config={"leva": batch},
                    eval={"metric": "accuracy", "predicao": "sobe"},
                    leva=batch, tier="asserted", log=log,
                )
                run_ref = f"edge/{run['payload']['num']}"
                fact = eventlog.observe_fato(
                    atividade=activity_ref, run=run_ref, leva=batch,
                    body=f"resultado {batch}", medida={"valor": 1, "como": "fixture"},
                    tier="asserted", log=log,
                )
                refs[batch] = (run_ref, f"edge/{fact['payload']['num']}")
            eventlog.instrument_failure(
                instrumento="playwright", leva="suspeita", detalhe="browser caiu", log=log,
            )

            brief = portfolio.portfolio_at(log=log, top_k=10, agenda_k=1)

            self.assertEqual(brief["admissibilidade"], [
                {"tipo": "fato", "ref": refs["suspeita"][1], "leva": "suspeita",
                 "admissibilidade": "suspeita"},
                {"tipo": "run", "ref": refs["suspeita"][0], "leva": "suspeita",
                 "admissibilidade": "suspeita"},
            ])
            self.assertNotIn(
                refs["controle"][0], [item["ref"] for item in brief["admissibilidade"]],
            )

    def test_agenda_v1_combines_live_moves_and_bisect_questions_with_one_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            hypothesis = eventlog.declare_hypothesis(
                "A intervenção melhora o resultado",
                {"metric": "accuracy", "threshold": 0.8, "direction": "maior"},
                log=log,
            )
            hypothesis_ulid = hypothesis["payload"]["ulid"]
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Organizar",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            eventlog.open_ticket(
                map=map_ref, titulo="Cobrar hipótese", question="Funcionou?",
                rationale="Inscrever", inscricao=hypothesis_ulid,
                dispatch_id="d1", author="operador", tier="asserted", log=log,
            )
            evidence = eventlog.open_atividade(
                operacao="edge", finalidade="Evidência",
                tier="asserted", author="operador", log=log,
            )
            proposed = eventlog.propose_move(
                kind="map.archive", alvo=map_ref,
                effect={
                    "event_type": "map.state",
                    "subject": f"map:{opened_map['payload']['ulid']}",
                    "payload": {
                        "ref": opened_map["payload"]["ulid"], "estado": "arquivado",
                        "rationale": "Encerrar", "dispatch_id": "future",
                        "author": "operador",
                    },
                },
                expects={"estado": "ativado"}, evidencia=[evidence["payload"]["ulid"]],
                rationale="Propor arquivo", basis_seq=eventlog.read(log=log)[-1]["seq"],
                operacao="edge", log=log,
            )
            expected_question = portfolio.bisect("edge", log)[0]["ref"]

            brief = portfolio.portfolio_at(log=log, top_k=1, agenda_k=2)

            self.assertEqual([item["tipo"] for item in brief["agenda"]], [
                "move", "pergunta",
            ])
            self.assertEqual(brief["agenda"][0]["ref"], proposed["payload"]["ulid"])
            self.assertEqual(brief["agenda"][1]["ref"], expected_question)
            self.assertNotIn("recheck", brief["agenda"][0])
            bounded = portfolio.portfolio_at(log=log, top_k=1, agenda_k=1)
            self.assertEqual(len(bounded["agenda"]), 1)

    def test_epistemic_presumptions_compete_in_the_common_top_k_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {
                    "sessao_id": "s1", "operacoes": ["edge"],
                    "rationalization_id": "r1",
                    "epistemico": {"presuncoes": [{
                        "texto": "A entrega depende do teste",
                        "confirmaria": "teste passa", "refutaria": "teste falha",
                    }]},
                },
                log=log,
            )

            brief = portfolio.portfolio_at(log=log, top_k=1, agenda_k=0)

            self.assertEqual(len(brief["presuncoes"]), 1)
            self.assertEqual(brief["presuncoes"][0]["kind"], "presuncao")
            self.assertEqual(brief["presuncoes"][0]["texto"],
                             "A entrega depende do teste")

    def test_a37_generic_contested_and_canon_survive_top_k_until_adjudication(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "contest.raised", "qualquer:alvo-42",
                {"alvo": "alvo-42", "evidencia": "evidencia-1",
                 "detalhe": "contradição nova", "author": "operador"},
                log=log,
            )
            eventlog.append(
                "canon.elected", "canon:map:edge/map-999",
                {"kind": "map", "ref": "edge/map-999"}, log=log,
            )
            for purpose in ("Deslocada", "Mais recente"):
                eventlog.open_atividade(
                    operacao="edge", finalidade=purpose,
                    tier="asserted", author="operador", log=log,
                )

            brief = portfolio.portfolio_at(log=log, top_k=1, agenda_k=0)

            self.assertEqual(brief["contested"], [{
                "alvo": "alvo-42", "evidencia": "evidencia-1",
                "detalhe": "contradição nova", "author": "operador",
                "seq": 1,
            }])
            self.assertEqual(
                [(item["kind"], item["ref"]) for item in brief["canon"]],
                [("map", "edge/map-999")],
            )

            eventlog.append(
                "contest.adjudicated", "qualquer:alvo-42",
                {"alvo": "alvo-42", "veredito": "corrompido"}, log=log,
            )
            still_contested = portfolio.portfolio_at(log=log, top_k=1, agenda_k=0)
            self.assertEqual([item["alvo"] for item in still_contested["contested"]],
                             ["alvo-42"])

            eventlog.append(
                "contest.adjudicated", "qualquer:alvo-42",
                {"alvo": "alvo-42", "veredito": "mantido"}, log=log,
            )
            adjudicated = portfolio.portfolio_at(log=log, top_k=1, agenda_k=0)
            self.assertEqual(adjudicated["contested"], [])


if __name__ == "__main__":
    unittest.main()
