"""Lentes de Atividade/Direction — aceitações verticais da spec v2."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


class AtividadePens(unittest.TestCase):
    def test_open_requires_non_blank_finalidade_without_writing_a5(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for invalid in (None, "", "   "):
                with self.subTest(finalidade=invalid):
                    with self.assertRaisesRegex(ValueError, "finalidade"):
                        eventlog.open_atividade(
                            operacao="edge", finalidade=invalid,
                            tier="asserted", author="operador", log=log,
                        )
            self.assertEqual(eventlog.read(log=log), [])

    def test_open_allocates_distinct_contiguous_nums_under_the_log_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            barrier = threading.Barrier(2)
            written = []

            def open_one(name):
                barrier.wait()
                written.append(eventlog.open_atividade(
                    operacao="edge", finalidade=name,
                    tier="asserted", author="operador", log=log,
                ))

            threads = [threading.Thread(target=open_one, args=(name,))
                       for name in ("Entregar S1", "Validar S1")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(sorted(e["payload"]["num"] for e in written),
                             ["atv-001", "atv-002"])
            self.assertEqual([e["seq"] for e in eventlog.read(log=log)], [1, 2])

    def test_superada_por_requires_a_valid_successor_and_other_states_reject_it_a6(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first = eventlog.open_atividade(
                operacao="edge", finalidade="Primeira", tier="asserted",
                author="operador", log=log,
            )
            second = eventlog.open_atividade(
                operacao="edge", finalidade="Segunda", tier="asserted",
                author="operador", log=log,
            )
            first_ref = f"edge/{first['payload']['num']}"
            second_ref = f"edge/{second['payload']['num']}"
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "superada_por"):
                eventlog.close_atividade(
                    ref=first_ref, estado="superada_por", julgamento="Substituída",
                    tier="asserted", author="operador", log=log,
                )
            with self.assertRaisesRegex(ValueError, "superada_por"):
                eventlog.close_atividade(
                    ref=first_ref, estado="cumprida", julgamento="Terminou",
                    superada_por=second_ref, tier="asserted", author="operador", log=log,
                )
            self.assertEqual(log.read_bytes(), before)


class RunPensAndFolds(unittest.TestCase):
    def _activity(self, log, finalidade="Medir"):
        event = eventlog.open_atividade(
            operacao="edge", finalidade=finalidade,
            tier="asserted", author="operador", log=log,
        )
        return f"edge/{event['payload']['num']}"

    def test_open_run_requires_preregistered_eval_and_computes_hash_a10(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity = self._activity(log)
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "eval"):
                eventlog.open_run(
                    atividades=[activity], config={"arm": "A"}, eval=None,
                    tier="asserted", log=log,
                )
            with self.assertRaisesRegex(ValueError, "atividades"):
                eventlog.open_run(
                    atividades=[], config={"arm": "A"},
                    eval={"metric": "errors", "predicao": "cai"},
                    tier="asserted", log=log,
                )
            with self.assertRaisesRegex(ValueError, "prediction_hash"):
                eventlog.open_run(
                    atividades=[activity], config={"arm": "A"},
                    eval={"metric": "errors", "predicao": "cai"},
                    prediction_hash="forged", tier="asserted", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            first = eventlog.open_run(
                atividades=[activity], config={"arm": "A"},
                eval={"metric": " errors ", "predicao": " cai "},
                tier="asserted", log=log,
            )
            second = eventlog.open_run(
                atividades=[activity], config={"arm": "B"},
                eval={"metric": "errors", "predicao": "cai!"},
                tier="asserted", log=log,
            )
            self.assertEqual(first["payload"]["num"], "run-001")
            self.assertEqual(second["payload"]["num"], "run-002")
            self.assertNotEqual(first["payload"]["prediction_hash"],
                                second["payload"]["prediction_hash"])
            canonical = json.dumps(
                {"metric": "errors", "predicao": "cai"},
                sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            )
            import hashlib
            self.assertEqual(first["payload"]["prediction_hash"],
                             hashlib.sha256(canonical.encode()).hexdigest())

    def test_one_run_joins_every_activity_without_duplication_a39(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first = self._activity(log, "Pergunta A")
            second = self._activity(log, "Pergunta B")
            opened = eventlog.open_run(
                atividades=[first, second], config={"corpus": "fixture"},
                eval={"metric": "accuracy", "predicao": "> 0.8"},
                tier="asserted", log=log,
            )
            run_ref = f"edge/{opened['payload']['num']}"

            activities = eventlog.atividades_at(log=log)
            self.assertEqual(activities[first]["runs"], [run_ref])
            self.assertEqual(activities[second]["runs"], [run_ref])
            run = eventlog.runs_at(log=log)[run_ref]
            self.assertEqual(run["atividades"], opened["payload"]["atividades"])
            self.assertEqual(run["primaria"], opened["payload"]["atividades"][0])

    def test_run_refuses_measured_bearing_for_nao_mede_but_accepts_no_bearing_a11(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            measured = self._activity(log, "Medida")
            excluded = self._activity(log, "Não medida")
            opened = eventlog.open_run(
                atividades=[measured], config={"arm": "A"},
                eval={"metric": "errors", "predicao": "cai"},
                nao_mede=[excluded], tier="asserted", log=log,
            )
            run_ref = f"edge/{opened['payload']['num']}"
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "nao_mede|não mede"):
                eventlog.close_run(
                    ref=run_ref, resultado="sem efeito",
                    bears_on=[{"alvo": excluded, "valencia": "refutes"}],
                    tier="asserted", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            closed = eventlog.close_run(
                ref=run_ref, resultado="instrumento não cobre a pergunta",
                bears_on=[{"alvo": excluded, "valencia": "no_bearing"}],
                tier="asserted", log=log,
            )
            excluded_ulid = eventlog.atividades_at(log=log)[excluded]["ulid"]
            self.assertEqual(closed["payload"]["bears_on"],
                             [{"alvo": excluded_ulid, "valencia": "no_bearing"}])
            self.assertEqual(eventlog.runs_at(log=log)[run_ref]["resultado"],
                             "instrumento não cobre a pergunta")

    def test_presumption_graph_links_fact_run_two_activities_and_arc_without_dup_run_a39(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            arc = eventlog.open_arco(
                operacao="edge", nome="Qualidade", tier="asserted",
                author="operador", log=log,
            )
            arc_ref = f"edge/{arc['payload']['num']}"
            activities = []
            activity_events = []
            for name in ("Pergunta A", "Pergunta B"):
                opened = eventlog.open_atividade(
                    operacao="edge", finalidade=name, arco=arc_ref,
                    eval={"regua": f"régua {name}"}, tier="asserted",
                    author="operador", log=log,
                )
                activity_events.append(opened)
                activities.append(f"edge/{opened['payload']['num']}")
            run = eventlog.open_run(
                atividades=activities, config={"corpus": "fixture"},
                eval={"metric": "accuracy", "predicao": "sobe"},
                tier="asserted", log=log,
            )
            run_ref = f"edge/{run['payload']['num']}"
            fact = eventlog.observe_fato(
                atividade=activities[0], run=run_ref, body="Accuracy 0.84",
                medida={"valor": 0.84, "como": "holdout"}, tier="asserted", log=log,
            )
            eventlog.close_run(
                ref=run_ref, resultado="0.84",
                bears_on=[{"alvo": activities[0], "valencia": "supports"}],
                tier="asserted", log=log,
            )
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                {"sessao_id": "s1", "operacoes": ["edge"],
                 "epistemico": {"presuncoes": [
                     {"texto": "O ganho generaliza", "confirmaria": "novo holdout",
                      "refutaria": "regressão", "depende_de": run_ref},
                 ]},
                 "organizacional": {"enderecos": [
                     {"atividade": activities[0], "path": "ORGANIZACIONAL-NAO-EPISTEMICO",
                      "papel": "config"},
                 ]}},
                log=log,
            )

            tree = eventlog.presumptions_at(log=log)
            fact_key = f"fato:{fact['payload']['ulid']}"
            run_key = f"run:{run['payload']['ulid']}"
            activity_keys = [f"atividade:{event['payload']['ulid']}"
                             for event in activity_events]
            arc_key = f"arco:{arc['payload']['ulid']}"
            self.assertEqual(sum(key == run_key for key in tree["nodes"]), 1)
            self.assertEqual(tree["nodes"][run_key]["depends_on"], [fact_key])
            for activity_key in activity_keys:
                self.assertIn(run_key, tree["nodes"][activity_key]["depends_on"])
            self.assertEqual(tree["nodes"][arc_key]["depends_on"], activity_keys)
            self.assertEqual(tree["nodes"][run_key]["resultado"], "0.84")
            self.assertNotIn("ORGANIZACIONAL-NAO-EPISTEMICO",
                             json.dumps(tree, ensure_ascii=False))


class FatoPensAndFolds(unittest.TestCase):
    def test_observed_fact_has_identity_and_joins_activity_run_and_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Contar erros",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            run_event = eventlog.open_run(
                atividades=[activity], config={"arm": "A"},
                eval={"metric": "errors", "predicao": "cai"},
                leva="batch-1", tier="asserted", log=log,
            )
            run = f"edge/{run_event['payload']['num']}"
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "body"):
                eventlog.observe_fato(
                    atividade=activity, run=run, body=" ", tier="asserted", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            observed = eventlog.observe_fato(
                atividade=activity, run=run, leva="batch-1", body="113 erros",
                endereco={"path": "results.json", "line": 7},
                medida={"valor": 113, "como": "contador do parser"},
                tier="asserted", log=log,
            )
            self.assertEqual(observed["payload"]["num"], "fat-001")
            self.assertEqual(observed["payload"]["atividade"],
                             activity_event["payload"]["ulid"])
            self.assertEqual(observed["payload"]["run"], run_event["payload"]["ulid"])
            self.assertEqual(observed["payload"]["leva"], "batch-1")
            fact_ref = f"edge/{observed['payload']['num']}"
            folded = eventlog.atividades_at(log=log)[activity]
            self.assertEqual(folded["fatos"], [fact_ref])


class ArcoPensAndFolds(unittest.TestCase):
    def test_arc_has_own_valence_and_move_changes_activity_membership_a12(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            old = eventlog.open_arco(
                operacao="edge", nome="Arco antigo",
                tier="asserted", author="operador", log=log,
            )
            new = eventlog.open_arco(
                operacao="edge", nome="Arco novo",
                tier="asserted", author="operador", log=log,
            )
            old_ref = f"edge/{old['payload']['num']}"
            new_ref = f"edge/{new['payload']['num']}"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Mudar de arco", arco=old_ref,
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            eventlog.close_arco(
                ref=old_ref, valencia="refutes", julgamento="Aposta fria",
                tier="asserted", log=log,
            )
            before_move = eventlog.atividades_at(log=log)[activity]
            self.assertEqual(before_move["arco"], old["payload"]["ulid"])
            self.assertNotIn("valencia", before_move)
            self.assertEqual(eventlog.arcos_at(log=log)[old_ref]["valencia"], "refutes")

            eventlog.move_arco(
                ref=activity, arco_novo=new_ref, tier="asserted", author="grill",
                rationale="A finalidade agora serve ao novo arco", log=log,
            )
            self.assertEqual(eventlog.atividades_at(log=log)[activity]["arco"],
                             new["payload"]["ulid"])


class MarcoPensAndFolds(unittest.TestCase):
    def test_marco_is_latest_curated_pointer_not_computed_frontier_a13(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            refs = []
            for index in range(1, 10):
                opened = eventlog.open_atividade(
                    operacao="edge", finalidade=f"Atividade {index}",
                    tier="asserted", author="operador", log=log,
                )
                refs.append(f"edge/{opened['payload']['num']}")
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "rationale"):
                eventlog.set_marco(
                    operacao="edge", ref=refs[3], rationale=" ",
                    dispatch_id="dispatch-1", author="operador", log=log,
                )
            with self.assertRaisesRegex(ValueError, "dispatch_id"):
                eventlog.set_marco(
                    operacao="edge", ref=refs[3], rationale="Primeiro estável",
                    dispatch_id=None, author="operador", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            eventlog.set_marco(
                operacao="edge", ref=refs[3], rationale="Primeiro estável",
                dispatch_id="dispatch-1", author="operador", log=log,
            )
            eventlog.set_marco(
                operacao="edge", ref=refs[4], nota="Índice confirmado",
                rationale="Novo marco validado", dispatch_id="dispatch-2",
                author="grill", log=log,
            )
            self.assertEqual(eventlog.marco_of("edge", log=log)["ref"], refs[4])
            computed_frontier = refs[-1]
            self.assertNotEqual(eventlog.marco_of("edge", log=log)["ref"],
                                computed_frontier)
            self.assertFalse(any(event["type"].startswith("frontier.")
                                 for event in eventlog.read(log=log)))


class GrainNumberAllocation(unittest.TestCase):
    def test_run_fact_and_arc_nums_are_independent_and_serialized_under_flock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Concorrência",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"

            def race(call):
                barrier = threading.Barrier(2)
                written, errors = [], []

                def worker(index):
                    try:
                        barrier.wait()
                        written.append(call(index))
                    except Exception as exc:  # test captures thread failures for the main assertion
                        errors.append(exc)

                threads = [threading.Thread(target=worker, args=(index,)) for index in (1, 2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                self.assertEqual(errors, [])
                return sorted(event["payload"]["num"] for event in written)

            self.assertEqual(race(lambda index: eventlog.open_run(
                atividades=[activity], config={"arm": index},
                eval={"metric": "m", "predicao": str(index)}, tier="asserted", log=log,
            )), ["run-001", "run-002"])
            self.assertEqual(race(lambda index: eventlog.observe_fato(
                atividade=activity, body=f"fato {index}", tier="asserted", log=log,
            )), ["fat-001", "fat-002"])
            self.assertEqual(race(lambda index: eventlog.open_arco(
                operacao="edge", nome=f"arco {index}", tier="asserted",
                author="operador", log=log,
            )), ["arc-001", "arc-002"])

    def test_semantically_invalid_s2_grains_fail_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Filtro semântico",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            good_run = eventlog.open_run(
                atividades=[activity], config={"arm": "good"},
                eval={"metric": "m", "predicao": "p"}, tier="asserted", log=log,
            )
            good_arc = eventlog.open_arco(
                operacao="edge", nome="válido", tier="asserted",
                author="operador", log=log,
            )
            eventlog.append(
                "run.opened", "run:BAD",
                {**good_run["payload"], "ulid": "BAD", "num": "run-999", "tier": "bogus"},
                log=log,
            )
            bad_arc = {**good_arc["payload"], "ulid": "BAD-ARC", "num": "arc-999"}
            bad_arc.pop("author")
            eventlog.append("arco.opened", "arco:BAD-ARC", bad_arc, log=log)
            eventlog.append(
                "fato.observed", "fato:BAD-FACT",
                {"ulid": "BAD-FACT", "num": "fat-999", "operacao": "edge",
                 "atividade": activity_event["payload"]["ulid"], "body": "",
                 "tier": "asserted"},
                log=log,
            )
            self.assertEqual(list(eventlog.runs_at(log=log)), ["edge/run-001"])
            self.assertEqual(list(eventlog.arcos_at(log=log)), ["edge/arc-001"])
            self.assertEqual(eventlog.atividades_at(log=log)[activity]["fatos"], [])


class ClaimPensAndFolds(unittest.TestCase):
    def test_portfolio_pure_folds_reuse_one_event_snapshot_without_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.hypothesize_claim(
                statement="Claim puro", origem_sessao="s1", derivation_key="claim-pure",
                falsifier={"metric": "m", "threshold": 1, "direction": "maior"},
                log=log,
            )
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa puro", rationale="Snapshot",
                dispatch_id="dispatch-map", author="grill", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            eventlog.open_ticket(
                map=map_ref, titulo="Ticket puro", question="Q?", rationale="Snapshot",
                dispatch_id="dispatch-ticket", author="grill", log=log,
            )
            events = eventlog.read(log=log)
            expected_claims = eventlog.claims_at(log=log)
            expected_presumptions = eventlog.presumptions_at(log=log)
            expected_frontier = eventlog.frontier_of(map_ref, log=log)
            corrupt_snapshot = [None, "noise", {"type": "claim.hypothesized",
                                                 "payload": ["corrupt"]}, *events]
            wayfinds = eventlog.fold_wayfinds(corrupt_snapshot)

            with mock.patch.object(
                    eventlog, "read", side_effect=AssertionError("pure folds cannot read")):
                self.assertEqual(eventlog.fold_claims(corrupt_snapshot), expected_claims)
                self.assertEqual(
                    eventlog.fold_presumptions(corrupt_snapshot), expected_presumptions)
                self.assertEqual(
                    eventlog.frontier_from_wayfinds(map_ref, wayfinds), expected_frontier)

    def test_claim_presumption_and_frontier_adapters_each_read_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="One read",
                dispatch_id="dispatch-map", author="grill", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            real_read = eventlog.read
            for call in (
                lambda: eventlog.claims_at(log=log),
                lambda: eventlog.presumptions_at(log=log),
                lambda: eventlog.frontier_of(map_ref, log=log),
            ):
                with mock.patch.object(eventlog, "read", wraps=real_read) as read_fn:
                    call()
                    self.assertEqual(read_fn.call_count, 1)

    def test_hypothesized_claim_reuses_hip1_and_only_eval_claim_is_presumption_a14(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "STRUCTURED|falsifier"):
                eventlog.hypothesize_claim(
                    statement="Forma inválida", falsifier="quando falhar",
                    origem_sessao="s1", derivation_key="d1", log=log,
                )
            self.assertEqual(eventlog.read(log=log), [])

            salient = eventlog.hypothesize_claim(
                statement="  Pode haver um gargalo  ", origem_sessao="s1",
                derivation_key="d1", log=log,
            )
            chargeable = eventlog.hypothesize_claim(
                statement="A latência excede o piso", origem_sessao="s1",
                derivation_key="d2",
                falsifier={"metric": " latency ", "threshold": 120, "direction": "menor"},
                log=log,
            )
            claims = eventlog.claims_at(log=log)
            self.assertEqual(claims["hypothesized"][salient["payload"]["ulid"]]["statement"],
                             "Pode haver um gargalo")
            self.assertEqual(chargeable["payload"]["falsifier"]["metric"], "latency")
            presumption_nodes = eventlog.presumptions_at(log=log)["nodes"]
            self.assertNotIn(f"claim:{salient['payload']['ulid']}", presumption_nodes)
            self.assertIn(f"claim:{chargeable['payload']['ulid']}", presumption_nodes)

    def test_promote_claim_links_existing_hypothesized_to_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            hypothesized = eventlog.hypothesize_claim(
                statement="A hipótese implícita", origem_sessao="s1",
                derivation_key="d1", log=log,
            )
            declared = eventlog.declare_hypothesis(
                "A hipótese ratificada",
                {"metric": "accuracy", "threshold": 0.8, "direction": "maior"},
                log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "hypothesized"):
                eventlog.promote_claim(
                    hypothesized="missing", declared=declared["payload"]["ulid"], log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            eventlog.promote_claim(
                hypothesized=hypothesized["payload"]["ulid"],
                declared=declared["payload"]["ulid"], log=log,
            )
            claims = eventlog.claims_at(log=log)
            self.assertEqual(
                claims["hypothesized"][hypothesized["payload"]["ulid"]]["promoted_to"],
                declared["payload"]["ulid"],
            )

    def test_claims_fold_surfaces_and_clears_contested_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Gerar evidência",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            fact = eventlog.observe_fato(
                atividade=activity, body="Evidência", tier="asserted", log=log,
            )
            claim = eventlog.declare_hypothesis(
                "Claim contestado",
                {"metric": "m", "threshold": 1, "direction": "maior"}, log=log,
            )
            claim_id = claim["payload"]["ulid"]
            eventlog.raise_contest(
                alvo=claim_id, evidencia=f"edge/{fact['payload']['num']}",
                detalhe="Contradição", author="racionalizador", log=log,
            )
            self.assertTrue(eventlog.claims_at(log=log)["declared"][claim_id]["contested"])
            self.assertEqual(eventlog.claims_at(log=log)["contested"], [claim_id])
            eventlog.adjudicate_contest(
                alvo=claim_id, veredito="mantido", rationale="Claim permanece",
                dispatch_id="dispatch-claim", author="grill", log=log,
            )
            self.assertFalse(eventlog.claims_at(log=log)["declared"][claim_id]["contested"])

    def test_presumption_nodes_keep_deterministic_operation_membership_without_cross_contamination(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            claim = eventlog.hypothesize_claim(
                statement="Claim da operação edge", origem_sessao="s-edge",
                derivation_key="claim-edge",
                falsifier={"metric": "m", "threshold": 1, "direction": "maior"},
                log=log,
            )
            declared = eventlog.declare_hypothesis(
                "Claim ainda sem vínculo operacional",
                {"metric": "x", "threshold": 0, "direction": "menor"}, log=log,
            )
            for session, operation, text in (
                ("s-edge", "edge", "Presunção edge sem depende_de"),
                ("s-legal", "legal", "Presunção legal"),
            ):
                eventlog.append(
                    "sessao.racionalizada", f"sessao:{session}",
                    {"sessao_id": session, "operacoes": [operation],
                     "epistemico": {"presuncoes": [
                         {"texto": text, "confirmaria": "sim", "refutaria": "não"},
                     ]}},
                    log=log,
                )
            nodes = eventlog.presumptions_at(log=log)["nodes"]
            claim_key = f"claim:{claim['payload']['ulid']}"
            declared_key = f"claim:{declared['payload']['ulid']}"
            self.assertEqual(nodes[claim_key]["operacoes"], ["edge"])
            self.assertEqual(nodes[declared_key]["operacoes"], [])
            edge_nodes = {key for key, node in nodes.items() if "edge" in node["operacoes"]}
            legal_nodes = {key for key, node in nodes.items() if "legal" in node["operacoes"]}
            self.assertTrue(any("s-edge" in key for key in edge_nodes))
            self.assertFalse(any("s-legal" in key for key in edge_nodes))
            self.assertTrue(any("s-legal" in key for key in legal_nodes))


class ContestPensAndFolds(unittest.TestCase):
    def test_new_evidence_marks_contested_without_changing_curated_state_a15(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Fechar com autoridade",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            eventlog.close_atividade(
                ref=activity, estado="cumprida", julgamento="Cumpriu",
                tier="asserted", author="operador", log=log,
            )
            fact = eventlog.observe_fato(
                atividade=activity, body="Contradição observada",
                tier="asserted", log=log,
            )
            fact_ref = f"edge/{fact['payload']['num']}"
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "evidencia|resolve"):
                eventlog.raise_contest(
                    alvo=activity, evidencia="edge/fat-999",
                    detalhe="não existe", author="racionalizador", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            for index in range(5):
                eventlog.raise_contest(
                    alvo=activity, evidencia=fact_ref,
                    detalhe=f"contradição {index}", author="racionalizador", log=log,
                )
            folded = eventlog.atividades_at(log=log)[activity]
            self.assertEqual(folded["estado"], "cumprida")
            self.assertTrue(folded["contested"])
            self.assertEqual(len(folded["contests"]), 5)

    def test_adjudication_mantido_clears_flag_and_preserves_contest_history_a42(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity_event = eventlog.open_atividade(
                operacao="edge", finalidade="Manter decisão",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{activity_event['payload']['num']}"
            eventlog.close_atividade(
                ref=activity, estado="cumprida", julgamento="Cumpriu",
                tier="asserted", author="operador", log=log,
            )
            fact = eventlog.observe_fato(
                atividade=activity, body="Sinal divergente", tier="asserted", log=log,
            )
            eventlog.raise_contest(
                alvo=activity, evidencia=f"edge/{fact['payload']['num']}",
                detalhe="Sinal não destrona sozinho", author="racionalizador", log=log,
            )
            eventlog.adjudicate_contest(
                alvo=activity, veredito="mantido", rationale="Evidência insuficiente",
                dispatch_id="dispatch-1", author="grill", log=log,
            )
            folded = eventlog.atividades_at(log=log)[activity]
            self.assertFalse(folded["contested"])
            self.assertEqual(len(folded["contests"]), 1)
            self.assertEqual(folded["estado"], "cumprida")

    def test_corrected_adjudication_requires_and_commits_successor_in_same_batch_a42(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Corrigir decisão",
                tier="asserted", author="operador", log=log,
            )
            activity = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=activity, estado="cumprida", julgamento="Leitura inicial",
                tier="asserted", author="operador", log=log,
            )
            fact = eventlog.observe_fato(
                atividade=activity, body="Contradição decisiva", tier="asserted", log=log,
            )
            eventlog.raise_contest(
                alvo=activity, evidencia=f"edge/{fact['payload']['num']}",
                detalhe="Muda o veredito", author="racionalizador", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "sucessor"):
                eventlog.adjudicate_contest(
                    alvo=activity, veredito="corrigido", rationale="Correção necessária",
                    dispatch_id="dispatch-2", author="grill", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            successor = {
                "type": "atividade.closed", "subject": f"atividade:{opened['payload']['ulid']}",
                "payload": {"ref": opened["payload"]["ulid"], "estado": "abandonada",
                            "julgamento": "Contradição confirmou abandono",
                            "superada_por": None, "tier": "asserted", "author": "grill",
                            "rationale": "Correção necessária", "dispatch_id": "dispatch-2"},
            }
            successor_event, adjudication = eventlog.adjudicate_contest(
                alvo=activity, veredito="corrigido", sucessor=successor,
                rationale="Correção necessária", dispatch_id="dispatch-2",
                author="grill", log=log,
            )
            self.assertEqual(adjudication["payload"]["sucessor"], successor_event["seq"])
            self.assertEqual(adjudication["seq"], successor_event["seq"] + 1)
            folded = eventlog.atividades_at(log=log)[activity]
            self.assertEqual(folded["estado"], "abandonada")
            self.assertFalse(folded["contested"])


class WayfinderPensAndFolds(unittest.TestCase):
    def _map(self, log, operation, title="Mapa"):
        event = eventlog.open_map(
            operacao=operation, titulo=title, rationale="Mapa necessário",
            dispatch_id=f"dispatch-{operation}", author="grill", log=log,
        )
        return f"{operation}/{event['payload']['num']}"

    def _ticket(self, log, map_ref, title, blocked_by=None):
        event = eventlog.open_ticket(
            map=map_ref, titulo=title, question=f"Como resolver {title}?",
            blocked_by=blocked_by or [], rationale="Decisão necessária",
            dispatch_id="dispatch-ticket", author="grill", log=log,
        )
        operation = map_ref.split("/", 1)[0]
        return f"{operation}/{event['payload']['num']}"

    def test_open_map_rejects_caller_supplied_thread_snapshot_without_writing_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "thread.*label"):
                eventlog.open_map(
                    operacao="edge", titulo="A34", rationale="Resolver na borda",
                    dispatch_id="dispatch-a34", author="grill",
                    thread={"uuid": "thread-forged", "display": "Snapshot confiado"},
                    log=log,
                )
            self.assertFalse(log.exists(), "refusal must append zero bytes")

    def test_open_map_resolves_thread_label_once_and_persists_canonical_snapshot_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            calls = []

            def resolve(label):
                calls.append(label)
                return [{"uuid": "thread-canonical", "display": "Nome canônico"}]

            opened = eventlog.open_map(
                operacao="edge", titulo="A34", rationale="Resolver na borda",
                dispatch_id="dispatch-a34", author="grill", thread="  V10  ",
                resolve_thread_fn=resolve, log=log,
            )

            self.assertEqual(calls, ["V10"])
            self.assertEqual(
                opened["payload"]["thread"],
                {"uuid": "thread-canonical", "display": "Nome canônico"},
            )
            self.assertEqual(
                eventlog.read(log=log)[0]["payload"]["thread"],
                {"uuid": "thread-canonical", "display": "Nome canônico"},
            )

    def test_open_map_refuses_missing_thread_candidate_with_zero_bytes_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "exactly one"):
                eventlog.open_map(
                    operacao="edge", titulo="A34", rationale="Resolver na borda",
                    dispatch_id="dispatch-a34", author="grill", thread="inexistente",
                    resolve_thread_fn=lambda _label: [], log=log,
                )
            self.assertFalse(log.exists(), "missing thread must append zero bytes")

    def test_open_map_refuses_ambiguous_thread_candidates_with_zero_bytes_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            candidates = [
                {"uuid": "thread-a", "display": "A"},
                {"uuid": "thread-b", "display": "B"},
            ]
            with self.assertRaisesRegex(ValueError, "exactly one"):
                eventlog.open_map(
                    operacao="edge", titulo="A34", rationale="Resolver na borda",
                    dispatch_id="dispatch-a34", author="grill", thread="ambígua",
                    resolve_thread_fn=lambda _label: candidates, log=log,
                )
            self.assertFalse(log.exists(), "ambiguous thread must append zero bytes")

    def test_open_map_refuses_malformed_thread_resolution_with_zero_bytes_a34(self):
        malformed_results = (
            None,
            {"uuid": "thread-a", "display": "Nome"},
            ({"uuid": "thread-a", "display": "Nome"},),
            [None],
            [{"uuid": "", "display": "Nome"}],
            [{"uuid": "thread-a", "display": None}],
        )
        for result in malformed_results:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                with self.assertRaises(ValueError):
                    eventlog.open_map(
                        operacao="edge", titulo="A34", rationale="Resolver na borda",
                        dispatch_id="dispatch-a34", author="grill", thread="malformada",
                        resolve_thread_fn=lambda _label, value=result: value, log=log,
                    )
                self.assertFalse(log.exists(), "malformed resolution must append zero bytes")

    def test_open_map_requires_thread_resolver_and_writes_zero_bytes_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "resolve_thread_fn"):
                eventlog.open_map(
                    operacao="edge", titulo="A34", rationale="Resolver na borda",
                    dispatch_id="dispatch-a34", author="grill", thread="V10", log=log,
                )
            self.assertFalse(log.exists(), "missing resolver must append zero bytes")

    def test_open_map_without_thread_does_not_call_resolver_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def resolver_must_not_run(_label):
                self.fail("thread=None must bypass the resolver")

            opened = eventlog.open_map(
                operacao="edge", titulo="Sem thread", rationale="Compatibilidade",
                dispatch_id="dispatch-a34-none", author="grill", thread=None,
                resolve_thread_fn=resolver_must_not_run, log=log,
            )
            self.assertIsNone(opened["payload"]["thread"])
            self.assertEqual(len(eventlog.read(log=log)), 1)

    def test_open_map_refuses_async_thread_resolver_with_zero_bytes_a34(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            async def async_resolver(_label):
                return [{"uuid": "thread-a", "display": "A"}]

            with self.assertRaisesRegex(ValueError, "synchronous"):
                eventlog.open_map(
                    operacao="edge", titulo="A34", rationale="Resolver síncrono",
                    dispatch_id="dispatch-a34", author="grill", thread="V10",
                    resolve_thread_fn=async_resolver, log=log,
                )
            self.assertFalse(log.exists(), "async resolver must append zero bytes")

    def test_real_ticket_short_ref_is_ambiguous_across_operations_a31(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_a = self._map(log, "op-a")
            map_b = self._map(log, "op-b")
            ticket_a = self._ticket(log, map_a, "Ticket A")
            ticket_b = self._ticket(log, map_b, "Ticket B")
            evidence_event = eventlog.open_atividade(
                operacao="op-a", finalidade="Resolver ticket A",
                tier="asserted", author="operador", log=log,
            )
            evidence = f"op-a/{evidence_event['payload']['num']}"
            self.assertEqual((map_a, map_b), ("op-a/map-001", "op-b/map-001"))
            self.assertEqual((ticket_a, ticket_b), ("op-a/tkt-001", "op-b/tkt-001"))

            before = log.read_bytes()
            with self.assertRaises(eventlog.AmbiguousRef):
                eventlog.close_ticket(
                    ref="tkt-001", resolucao="Resolvido",
                    valencia="supports", bears_on=[{"alvo": evidence,
                                                    "valencia": "supports"}],
                    rationale="Fecho", dispatch_id="dispatch-close",
                    author="grill", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            eventlog.close_ticket(
                ref=ticket_a, resolucao="Resolvido por A",
                valencia="supports", bears_on=[{"alvo": evidence,
                                                "valencia": "supports"}],
                rationale="Fecho", dispatch_id="dispatch-close",
                author="grill", log=log,
            )
            wayfinds = eventlog.wayfinds_at(log=log)
            self.assertEqual(wayfinds["tickets"][ticket_a]["estado"], "closed")
            self.assertEqual(wayfinds["tickets"][ticket_b]["estado"], "open")

    def test_frontier_is_derived_in_layers_and_moves_when_blocker_closes_a2(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_ref = self._map(log, "edge")
            a = self._ticket(log, map_ref, "A")
            b = self._ticket(log, map_ref, "B", blocked_by=[a])
            c = self._ticket(log, map_ref, "C", blocked_by=[b])
            evidence_event = eventlog.open_atividade(
                operacao="edge", finalidade="Resolver blockers",
                tier="asserted", author="operador", log=log,
            )
            evidence = f"edge/{evidence_event['payload']['num']}"

            def close(ref):
                eventlog.close_ticket(
                    ref=ref, resolucao=f"{ref} resolvido", valencia="supports",
                    bears_on=[{"alvo": evidence, "valencia": "supports"}],
                    rationale="Resolvido", dispatch_id="dispatch-close",
                    author="grill", log=log,
                )

            close(a)
            self.assertEqual(eventlog.frontier_of(map_ref, log=log), [[b], [c]])
            close(b)
            self.assertEqual(eventlog.frontier_of(map_ref, log=log), [[c]])
            self.assertFalse(any(event["type"].startswith("frontier.")
                                 for event in eventlog.read(log=log)))

    def test_declined_unblocks_and_paused_map_suppresses_frontier_a41(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_ref = self._map(log, "edge")
            a = self._ticket(log, map_ref, "A")
            b = self._ticket(log, map_ref, "B", blocked_by=[a])
            self.assertEqual(eventlog.frontier_of(map_ref, log=log), [[a], [b]])
            eventlog.decline_ticket(
                ref=a, reason="Não é necessário", dispatch_id="dispatch-decline",
                author="grill", log=log,
            )
            self.assertEqual(eventlog.frontier_of(map_ref, log=log), [[b]])
            eventlog.set_map_state(
                ref=map_ref, estado="pausado", rationale="Operação em pausa",
                dispatch_id="dispatch-pause", author="grill", log=log,
            )
            self.assertEqual(eventlog.frontier_of(map_ref, log=log), [])
            folded = eventlog.wayfinds_at(log=log)
            self.assertEqual(folded["tickets"][a]["estado"], "declined")
            self.assertEqual(folded["tickets"][b]["estado"], "open")

    def test_reopen_ticket_rejects_open_and_reopens_terminal_ticket_a41(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket = self._ticket(log, self._map(log, "edge"), "Reabrível")
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "open"):
                eventlog.reopen_ticket(
                    ref=ticket, motivo="Ainda aberto", dispatch_id="dispatch-reopen",
                    author="grill", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            eventlog.decline_ticket(
                ref=ticket, reason="Prematuro", dispatch_id="dispatch-decline",
                author="grill", log=log,
            )
            eventlog.reopen_ticket(
                ref=ticket, motivo="Nova evidência", evidencia="sessao:s2",
                dispatch_id="dispatch-reopen", author="grill", log=log,
            )
            self.assertEqual(eventlog.wayfinds_at(log=log)["tickets"][ticket]["estado"],
                             "open")

    def test_change_ticket_deps_rejects_a_real_api_constructed_cycle_a41(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_ref = self._map(log, "edge")
            a = self._ticket(log, map_ref, "A")
            b = self._ticket(log, map_ref, "B", blocked_by=[a])
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "cycle|ciclo"):
                eventlog.change_ticket_deps(
                    ref=a, blocked_by=[b], rationale="Dependência descoberta",
                    dispatch_id="dispatch-deps", author="grill", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            eventlog.change_ticket_deps(
                ref=b, blocked_by=[], rationale="Dependência removida",
                dispatch_id="dispatch-deps-2", author="grill", log=log,
            )
            self.assertEqual(eventlog.wayfinds_at(log=log)["tickets"][b]["blocked_by"], [])

    def test_map_is_a_canonical_object_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_ref = self._map(log, "edge", "Mapa canônico")
            self.assertIn("map", eventlog.CANON_KINDS)
            eventlog.append(
                "canon.elected", f"map:{map_ref}",
                {"kind": "map", "ref": map_ref, "thread": "portfolio"}, log=log,
            )
            self.assertEqual(eventlog.docs_at(log=log)["canon"], [
                {"kind": "map", "ref": map_ref, "thread": "portfolio",
                 "ts": eventlog.read(log=log)[-1]["ts"]},
            ])

    def test_map_and_ticket_numbers_are_serialized_under_flock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def race(call):
                barrier = threading.Barrier(2)
                written, errors = [], []

                def worker(index):
                    try:
                        barrier.wait()
                        written.append(call(index))
                    except Exception as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=worker, args=(index,)) for index in (1, 2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                self.assertEqual(errors, [])
                return sorted(event["payload"]["num"] for event in written)

            self.assertEqual(race(lambda index: eventlog.open_map(
                operacao="edge", titulo=f"Mapa {index}", rationale="Concorrência",
                dispatch_id=f"dispatch-map-{index}", author="grill", log=log,
            )), ["map-001", "map-002"])
            self.assertEqual(race(lambda index: eventlog.open_ticket(
                map="edge/map-001", titulo=f"Ticket {index}", question="Como?",
                rationale="Concorrência", dispatch_id=f"dispatch-ticket-{index}",
                author="grill", log=log,
            )), ["tkt-001", "tkt-002"])

    def test_wayfind_fold_exposes_moves_by_current_state_without_s5_pens(self):
        events = [
            {"seq": 1, "type": "move.proposed",
             "payload": {"ulid": "M1", "move_key": "K1", "kind": "ticket.close"}},
            {"seq": 2, "type": "move.proposed",
             "payload": {"ulid": "M2", "move_key": "K2", "kind": "ticket.close"}},
            {"seq": 3, "type": "move.ratified", "payload": {"ref": "M1"}},
            {"seq": 4, "type": "move.declined",
             "payload": {"ref": "M2", "pin": True, "reason": "não"}},
        ]
        folded = eventlog.fold_wayfinds(events)
        self.assertEqual(folded["moves"]["propostos"], [])
        self.assertEqual([move["ulid"] for move in folded["moves"]["ratificados"]], ["M1"])
        self.assertEqual([move["ulid"] for move in folded["moves"]["declinados"]], ["M2"])
        self.assertEqual(folded["pins"], {"K2"})


class MovePensAndFolds(unittest.TestCase):
    def _fixture(self, log):
        map_event = eventlog.open_map(
            operacao="edge", titulo="Mapa", rationale="Mover",
            dispatch_id="dispatch-map", author="grill", log=log,
        )
        map_ref = f"edge/{map_event['payload']['num']}"
        ticket_event = eventlog.open_ticket(
            map=map_ref, titulo="Ticket", question="Fechar?", rationale="Mover",
            dispatch_id="dispatch-ticket", author="grill", log=log,
        )
        ticket_ref = f"edge/{ticket_event['payload']['num']}"
        evidence_event = eventlog.open_atividade(
            operacao="edge", finalidade="Resolver",
            tier="asserted", author="operador", log=log,
        )
        evidence_ref = f"edge/{evidence_event['payload']['num']}"
        effect = {
            "event_type": "ticket.closed",
            "subject": f"ticket:{ticket_event['payload']['ulid']}",
            "payload": {
                "ref": ticket_event["payload"]["ulid"], "resolucao": "Resolvido",
                "valencia": "supports",
                "bears_on": [{"alvo": evidence_event["payload"]["ulid"],
                               "valencia": "supports"}],
                "rationale": "Evidência suficiente", "tier": "asserted",
                "author": "grill", "dispatch_id": "dispatch-ratify",
            },
        }
        return ticket_ref, evidence_ref, effect

    def test_propose_validates_effect_and_evidence_then_dedups_move_key_a16(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            basis = eventlog.read(log=log)[-1]["seq"]
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "evidencia"):
                eventlog.propose_move(
                    kind="ticket.close", alvo=ticket, effect=effect,
                    expects={"estado": "open"}, evidencia=[], rationale="Achado",
                    basis_seq=basis, log=log,
                )
            malformed = json.loads(json.dumps(effect))
            malformed["payload"].pop("resolucao")
            with self.assertRaisesRegex(ValueError, "resolucao"):
                eventlog.propose_move(
                    kind="ticket.close", alvo=ticket, effect=malformed,
                    expects={"estado": "open"}, evidencia=[evidence], rationale="Achado",
                    basis_seq=basis, log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            proposed = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Achado",
                basis_seq=basis, log=log,
            )
            duplicate = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Achado muda",
                basis_seq=basis, log=log,
            )
            self.assertIsNone(duplicate)
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)
            self.assertEqual(proposed["payload"]["author"], "edge")

    def test_ticket_open_proposal_allocates_identity_under_lock_and_ratifies_byte_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_event = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Investigar",
                dispatch_id="dispatch-map", author="grill", log=log,
            )
            evidence = eventlog.open_atividade(
                operacao="edge", finalidade="Sinal que pede ticket",
                tier="asserted", author="operador", log=log,
            )
            effect = {
                "event_type": "ticket.opened",
                "subject": None,
                "payload": {
                    "map": map_event["payload"]["ulid"],
                    "titulo": "Abrir pela lente",
                    "question": "O sinal exige mudar a direção?",
                    "rationale": "Sinal mecanicamente admissível",
                    "blocked_by": [],
                    "inscricao": None,
                    "tier": "llm_judged",
                    "author": "edge",
                    "dispatch_id": "dispatch-reconcile",
                    "legacy_ref": None,
                    "annotations": {"source": "reconcile"},
                },
            }
            before = log.read_bytes()
            malformed = json.loads(json.dumps(effect))
            malformed["payload"].pop("question")
            with self.assertRaisesRegex(ValueError, "question"):
                eventlog.propose_move(
                    kind="ticket.open", effect=malformed, expects={"estado": "ativado"},
                    evidencia=[evidence["payload"]["ulid"]], rationale="Inválido",
                    basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
                )
            supplied_identity = json.loads(json.dumps(effect))
            supplied_identity["payload"].update({"ulid": "caller", "num": "tkt-999"})
            with self.assertRaisesRegex(ValueError, "ulid/num"):
                eventlog.propose_move(
                    kind="ticket.open", effect=supplied_identity,
                    expects={"estado": "ativado"},
                    evidencia=[evidence["payload"]["ulid"]], rationale="Inválido",
                    basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            proposed = eventlog.propose_move(
                kind="ticket.open", effect=effect, expects={"estado": "ativado"},
                evidencia=[evidence["payload"]["ulid"]], rationale="Propor ticket",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            reserved = proposed["payload"]["effect"]
            self.assertEqual(reserved["payload"]["num"], "tkt-001")
            self.assertRegex(reserved["payload"]["ulid"], r"^[0-9A-HJKMNP-TV-Z]{26}$")
            self.assertEqual(reserved["subject"], f"ticket:{reserved['payload']['ulid']}")
            self.assertNotIn("ulid", effect["payload"], "caller input must remain untouched")
            self.assertNotIn("num", effect["payload"])

            ratified, opened = eventlog.ratify_move(
                ref=proposed["payload"]["ulid"], rationale="Ratificado",
                dispatch_id="dispatch-ratify", author="grill", log=log,
            )
            self.assertEqual(
                ratified["payload"]["effect"],
                {"event_type": opened["type"], "subject": opened["subject"],
                 "payload": opened["payload"]},
            )
            self.assertIn("edge/tkt-001", eventlog.wayfinds_at(log=log)["tickets"])

    def test_ticket_open_reservations_never_reassign_after_decline_or_concurrency(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            map_event = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Investigar",
                dispatch_id="dispatch-map", author="grill", log=log,
            )
            evidence = eventlog.open_atividade(
                operacao="edge", finalidade="Evidência",
                tier="asserted", author="operador", log=log,
            )
            map_ulid = map_event["payload"]["ulid"]
            evidence_ulid = evidence["payload"]["ulid"]

            def propose(title):
                return eventlog.propose_move(
                    kind="ticket.open",
                    effect={
                        "event_type": "ticket.opened", "subject": None,
                        "payload": {
                            "map": map_ulid, "titulo": title, "question": "Q?",
                            "rationale": "R", "blocked_by": [], "inscricao": None,
                            "tier": "llm_judged", "author": "edge",
                            "dispatch_id": "dispatch-reconcile", "legacy_ref": None,
                            "annotations": None,
                        },
                    },
                    expects={"estado": "ativado"}, evidencia=[evidence_ulid],
                    rationale="Propor", basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
                )

            declined = propose("Reserva declinada")
            self.assertEqual(declined["payload"]["effect"]["payload"]["num"], "tkt-001")
            eventlog.decline_move(
                ref=declined["payload"]["ulid"], reason="Não agora",
                dispatch_id="dispatch-decline", author="grill", log=log,
            )

            barrier = threading.Barrier(2)
            results, errors = [], []

            def worker():
                try:
                    barrier.wait()
                    results.append(propose("Proposta concorrente"))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            landed = [result for result in results if result is not None]
            self.assertEqual(len(landed), 1, "semantic intent dedups before identity allocation")
            self.assertEqual(landed[0]["payload"]["effect"]["payload"]["num"], "tkt-002")

            distinct = [propose("Proposta distinta A"), propose("Proposta distinta B")]
            self.assertEqual(
                [result["payload"]["effect"]["payload"]["num"] for result in distinct],
                ["tkt-003", "tkt-004"],
            )
            eventlog.ratify_move(
                ref=landed[0]["payload"]["ulid"], rationale="Ratificar uma",
                dispatch_id="dispatch-ratify", author="grill", log=log,
            )
            direct = eventlog.open_ticket(
                map="edge/map-001", titulo="Direto", question="Depois?",
                rationale="Não reutilizar reserva", dispatch_id="dispatch-direct",
                author="grill", log=log,
            )
            self.assertEqual(direct["payload"]["num"], "tkt-005")

    def test_concurrent_identical_proposals_land_exactly_once_a26(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            basis = eventlog.read(log=log)[-1]["seq"]
            barrier = threading.Barrier(2)
            results, errors = [], []

            def worker():
                try:
                    barrier.wait()
                    results.append(eventlog.propose_move(
                        kind="ticket.close", alvo=ticket, effect=effect,
                        expects={"estado": "open"}, evidencia=[evidence],
                        rationale="Mesmo gatilho", basis_seq=basis, log=log,
                    ))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(sum(result is not None for result in results), 1)
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)

    def test_ratify_embeds_and_materializes_byte_equal_effect_with_single_line_recovery_a17(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            proposed = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Fechar",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            ratified, materialized = eventlog.ratify_move(
                ref=proposed["payload"]["ulid"], rationale="Ratificado pelo mentee",
                dispatch_id="dispatch-ratify", author="grill", log=log,
            )
            embedded = ratified["payload"]["effect"]
            self.assertEqual(
                {"event_type": materialized["type"], "subject": materialized["subject"],
                 "payload": materialized["payload"]},
                embedded,
            )
            all_events = eventlog.read(log=log)
            recovery_only = [event for event in all_events
                             if event["seq"] != materialized["seq"]]
            self.assertEqual(
                eventlog.fold_wayfinds(recovery_only)["tickets"][ticket]["estado"],
                eventlog.fold_wayfinds(all_events)["tickets"][ticket]["estado"],
            )
            self.assertEqual(eventlog.fold_wayfinds(recovery_only)["tickets"][ticket]["estado"],
                             "closed")
            diff = eventlog.portfolio_diff("dispatch-ratify", log=log)
            self.assertEqual(diff["fechados"], [ticket])
            self.assertEqual(diff["moves_ratificados"], [proposed["payload"]["ulid"]])
            self.assertEqual(diff["frontier_antes"], {"edge/map-001": [[ticket]]})
            self.assertEqual(diff["frontier_depois"], {"edge/map-001": []})

    def test_ratify_and_decline_validate_operation_bind_and_persist_resolved_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            first = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Fechar",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "operacao|operation|other"):
                eventlog.ratify_move(
                    ref=first["payload"]["ulid"], rationale="Wrong bind",
                    dispatch_id="dispatch-wrong", author="grill",
                    operacao="other", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            ratified, _materialized = eventlog.ratify_move(
                ref=first["payload"]["ulid"], rationale="Bound",
                dispatch_id="dispatch-ratify", author="grill",
                operacao="edge", log=log,
            )
            self.assertEqual(ratified["payload"]["operacao"], "edge")
            self.assertEqual(ratified["payload"]["alvo"], first["payload"]["alvo"])
            self.assertEqual(ratified["payload"]["dispatch_id"], "dispatch-ratify")

            second_effect = json.loads(json.dumps(effect))
            second_effect["payload"]["resolucao"] = "Resolvido de outro modo"
            second = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=second_effect,
                expects={"estado": "closed"}, evidencia=[evidence], rationale="Reavaliar",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "operacao|operation|other"):
                eventlog.decline_move(
                    ref=second["payload"]["ulid"], reason="Wrong bind",
                    dispatch_id="dispatch-wrong", author="grill",
                    operacao="other", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            declined = eventlog.decline_move(
                ref=second["payload"]["ulid"], reason="Bound decline",
                dispatch_id="dispatch-decline", author="grill",
                operacao="edge", log=log,
            )
            self.assertEqual(declined["payload"]["operacao"], "edge")
            self.assertEqual(declined["payload"]["alvo"], second["payload"]["alvo"])
            self.assertEqual(declined["payload"]["dispatch_id"], "dispatch-decline")

    def test_declined_pin_is_move_key_and_identical_proposal_never_relands_a16(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            basis = eventlog.read(log=log)[-1]["seq"]
            proposed = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Fechar",
                basis_seq=basis, log=log,
            )
            eventlog.decline_move(
                ref=proposed["payload"]["ulid"], reason="Não fechar", pin=True,
                dispatch_id="dispatch-decline", author="grill", log=log,
            )
            folded = eventlog.wayfinds_at(log=log)
            self.assertEqual(folded["pins"], {proposed["payload"]["move_key"]})
            self.assertIsNone(eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Tentar de novo",
                basis_seq=basis, log=log,
            ))
            self.assertEqual(len(eventlog.read(types=["move.proposed"], log=log)), 1)

    def test_ratify_and_decline_are_mutually_exclusive_under_concurrency_a27(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            proposed = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Fechar",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            ref = proposed["payload"]["ulid"]
            barrier = threading.Barrier(2)
            successes, errors = [], []

            def ratify():
                try:
                    barrier.wait()
                    successes.append(("ratified", eventlog.ratify_move(
                        ref=ref, rationale="Sim", dispatch_id="dispatch-ratify",
                        author="grill", log=log,
                    )))
                except Exception as exc:
                    errors.append(exc)

            def decline():
                try:
                    barrier.wait()
                    successes.append(("declined", eventlog.decline_move(
                        ref=ref, reason="Não", dispatch_id="dispatch-decline",
                        author="grill", log=log,
                    )))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=ratify), threading.Thread(target=decline)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            folded = eventlog.wayfinds_at(log=log)["moves"]
            self.assertEqual(len(folded["ratificados"]) + len(folded["declinados"]), 1)

    def test_ratify_rejects_stale_expects_and_writes_nothing_a27(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ticket, evidence, effect = self._fixture(log)
            proposed = eventlog.propose_move(
                kind="ticket.close", alvo=ticket, effect=effect,
                expects={"estado": "open"}, evidencia=[evidence], rationale="Fechar",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            eventlog.close_ticket(
                ref=ticket, resolucao="Fechado à mão", valencia="supports",
                bears_on=[{"alvo": evidence, "valencia": "supports"}],
                rationale="Gesto direto", dispatch_id="dispatch-direct",
                author="grill", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "stale|closed|actual"):
                eventlog.ratify_move(
                    ref=proposed["payload"]["ulid"], rationale="Tarde demais",
                    dispatch_id="dispatch-ratify", author="grill", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

    def test_confirm_and_portfolio_diff_are_keyed_by_exact_dispatch_a19_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "rationale"):
                eventlog.confirm_portfolio(
                    rationale=" ", dispatch_id="dispatch-confirm", log=log,
                )
            map_event = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Abrir",
                dispatch_id="dispatch-open", author="grill", log=log,
            )
            map_ref = f"edge/{map_event['payload']['num']}"
            eventlog.set_map_state(
                ref=map_ref, estado="pausado", rationale="Pausar",
                dispatch_id="dispatch-a", author="grill", log=log,
            )
            eventlog.set_map_state(
                ref=map_ref, estado="ativado", rationale="Retomar",
                dispatch_id="dispatch-b", author="grill", log=log,
            )
            confirmed = eventlog.confirm_portfolio(
                rationale="Li os mapas; nada muda", dispatch_id="dispatch-confirm", log=log,
            )
            self.assertEqual(confirmed["type"], "portfolio.confirmed")
            diff_a = eventlog.portfolio_diff("dispatch-a", log=log)
            diff_b = eventlog.portfolio_diff("dispatch-b", log=log)
            self.assertEqual(diff_a["pausados"], [map_ref])
            self.assertEqual(diff_a["ativados"], [])
            self.assertEqual(diff_b["ativados"], [map_ref])
            self.assertEqual(diff_b["pausados"], [])
            self.assertTrue(diff_a["frontier_antes"] == diff_a["frontier_depois"] ==
                            {map_ref: []})


class AtividadeLifecyclePens(unittest.TestCase):
    def test_open_activity_accepts_optional_dispatch_and_rejects_blank_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "dispatch_id"):
                eventlog.open_atividade(
                    operacao="edge", finalidade="Inválida",
                    tier="asserted", author="operador", dispatch_id=" ", log=log,
                )
            self.assertFalse(log.exists() and log.read_bytes())
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Aberta pelo Turn",
                tier="asserted", author="operador",
                dispatch_id="dispatch-open", log=log,
            )
            self.assertEqual(opened["payload"]["dispatch_id"], "dispatch-open")
            self.assertEqual(opened["payload"]["operacao"], "edge")

    def test_bears_on_turn_fields_and_expected_source_state_are_checked_under_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            source = eventlog.open_atividade(
                operacao="edge", finalidade="Fonte",
                tier="asserted", author="operador", log=log,
            )
            target = eventlog.open_atividade(
                operacao="edge", finalidade="Alvo",
                tier="asserted", author="operador", log=log,
            )
            source_ref = f"edge/{source['payload']['num']}"
            target_ref = f"edge/{target['payload']['num']}"
            eventlog.close_atividade(
                ref=source_ref, estado="cumprida", julgamento="Fechou",
                tier="asserted", author="operador", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "stale|cumprida|estado"):
                eventlog.bears_on(
                    ref=source_ref, alvo=target_ref, valencia="refutes",
                    tier="asserted", dispatch_id="dispatch-refute",
                    expects={"estado": "aberta"}, operacao="edge", log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            linked = eventlog.bears_on(
                ref=source_ref, alvo=target_ref, valencia="refutes",
                tier="asserted", dispatch_id="dispatch-direct",
                operacao="edge", log=log,
            )
            self.assertEqual(linked["payload"]["dispatch_id"], "dispatch-direct")
            self.assertEqual(linked["payload"]["operacao"], "edge")
            self.assertEqual(linked["payload"]["ref"], source["payload"]["ulid"])
            self.assertEqual(linked["payload"]["alvo"], target["payload"]["ulid"])

    def test_turn_touch_persists_dispatch_and_operation_and_rejects_stale_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Foco do turno",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Fechou antes do Turn",
                tier="asserted", author="operador", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "stale|cumprida|estado"):
                eventlog.touch_atividade(
                    ref=ref, sessao="turn-stale", novo="não pode pousar",
                    tier="llm_judged", dispatch_id="dispatch-turn",
                    expects={"estado": "aberta"}, log=log,
                )
            self.assertEqual(log.read_bytes(), before)

            # Direct evidence capture remains backward compatible: a closed activity can still be
            # touched when the caller deliberately omits optimistic expectations.
            touch = eventlog.touch_atividade(
                ref=ref, sessao="direct-late", novo="evidência tardia",
                tier="llm_judged", dispatch_id="dispatch-direct", log=log,
            )
            self.assertEqual(touch["payload"]["dispatch_id"], "dispatch-direct")
            self.assertEqual(touch["payload"]["operacao"], "edge")
            self.assertEqual(touch["payload"]["ref"], opened["payload"]["ulid"])

    def test_concurrent_expected_open_closures_have_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Fecho CAS",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            barrier = threading.Barrier(2)
            wins, errors = [], []

            def worker(index):
                try:
                    barrier.wait()
                    wins.append(eventlog.close_atividade(
                        ref=ref, estado="cumprida", julgamento=f"winner-{index}",
                        tier="asserted", author="operador",
                        expects={"estado": "aberta"}, log=log,
                    ))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(wins), 1)
            self.assertEqual(len(errors), 1)
            self.assertRegex(str(errors[0]), "stale|cumprida|estado")
            self.assertEqual(wins[0]["payload"]["operacao"], "edge")
            self.assertEqual(len(eventlog.read(types=["atividade.closed"], log=log)), 1)

    def test_reopen_optional_expects_rejects_wrong_terminal_state_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Reabrir com CAS",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Feita",
                tier="asserted", author="operador", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "stale|cumprida|estado"):
                eventlog.reopen_atividade(
                    ref=ref, motivo="Outro motivo", tier="asserted", author="operador",
                    expects={"estado": "abandonada"}, log=log,
                )
            self.assertEqual(log.read_bytes(), before)

    def test_reopen_is_explicit_and_rejects_an_already_open_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Testar máquina de estados",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            with self.assertRaisesRegex(ValueError, "aberta|open"):
                eventlog.reopen_atividade(
                    ref=ref, motivo="Ainda viva", tier="asserted",
                    author="operador", log=log,
                )
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Fechada",
                tier="asserted", author="operador", log=log,
            )
            reopened = eventlog.reopen_atividade(
                ref=ref, motivo="Contradição nova", evidencia="session-2",
                tier="asserted", author="operador", log=log,
            )
            self.assertEqual(reopened["payload"]["operacao"], "edge")
            self.assertEqual(eventlog.atividades_at(log=log)[ref]["estado"], "reaberta")

    def test_bears_on_links_existing_grains_and_rejects_bad_valence_or_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            source = eventlog.open_atividade(
                operacao="edge", finalidade="Produzir evidência",
                tier="asserted", author="operador", log=log,
            )
            target = eventlog.open_atividade(
                operacao="edge", finalidade="Receber evidência",
                tier="asserted", author="operador", log=log,
            )
            source_ref = f"edge/{source['payload']['num']}"
            target_ref = f"edge/{target['payload']['num']}"
            eventlog.bears_on(
                ref=source_ref, alvo=target_ref, valencia="supports",
                evidencia="Teste passou", tier="asserted", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "valencia"):
                eventlog.bears_on(
                    ref=source_ref, alvo=target_ref, valencia="maybe",
                    tier="asserted", log=log,
                )
            with self.assertRaisesRegex(ValueError, "does not resolve"):
                eventlog.bears_on(
                    ref=source_ref, alvo="edge/atv-999", valencia="supports",
                    tier="asserted", log=log,
                )
            self.assertEqual(log.read_bytes(), before)
            self.assertEqual(
                eventlog.atividades_at(log=log)[source_ref]["bears_on"][0]["alvo"],
                target["payload"]["ulid"],
            )

    def test_short_refs_require_an_explicit_operation_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first = eventlog.open_atividade(
                operacao="op-a", finalidade="Ligar ticket",
                tier="asserted", author="operador", log=log,
            )
            eventlog.open_atividade(
                operacao="op-b", finalidade="Outra operação",
                tier="asserted", author="operador", log=log,
            )
            with self.assertRaises(eventlog.AmbiguousRef):
                eventlog.touch_atividade(
                    ref="atv-001", sessao="s1", tier="llm_judged", log=log,
                )
            linked = eventlog.touch_atividade(
                ref="atv-001", sessao="s1", tier="llm_judged",
                operacao="op-a", log=log,
            )
            self.assertEqual(linked["payload"]["ref"], first["payload"]["ulid"])

    def test_touch_pen_allows_only_one_touch_per_session_and_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Um toque por sessão",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.touch_atividade(
                ref=ref, sessao="same", novo="primeiro", tier="llm_judged", log=log,
            )
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "session.*activity|sessão.*atividade"):
                eventlog.touch_atividade(
                    ref=ref, sessao="same", novo="duplicado", tier="llm_judged", log=log,
                )
            self.assertEqual(log.read_bytes(), before)


class AtividadeFold(unittest.TestCase):
    def test_corrupt_activity_events_fail_dark_while_valid_history_folds(self):
        valid = {
            "seq": 2, "ts": "2026-07-11T00:00:00+00:00",
            "type": "atividade.opened", "subject": "atividade:VALID",
            "payload": {"ulid": "VALID", "num": "atv-001", "operacao": "edge",
                        "finalidade": "Sobreviver corrupção", "tier": "asserted",
                        "author": "operador"},
        }
        folded = eventlog.fold_atividades([
            None,
            {"seq": 1, "type": "atividade.opened", "payload": "corrupt"},
            valid,
            {"seq": 3, "type": "atividade.touched", "payload": ["corrupt"]},
        ])
        self.assertEqual(list(folded), ["edge/atv-001"])

    def test_semantically_invalid_openings_fail_dark(self):
        base = {"ulid": "VALID", "num": "atv-001", "operacao": "edge",
                "finalidade": "Válida", "tier": "asserted", "author": "operador"}
        events = [
            {"seq": 1, "type": "atividade.opened", "payload": dict(base)},
            {"seq": 2, "type": "atividade.opened",
             "payload": {**base, "ulid": "BAD-TIER", "num": "atv-002", "tier": "bogus"}},
            {"seq": 3, "type": "atividade.opened",
             "payload": {k: v for k, v in {**base, "ulid": "NO-AUTHOR",
                                             "num": "atv-003"}.items()
                         if k != "author"}},
        ]
        self.assertEqual(list(eventlog.fold_atividades(events)), ["edge/atv-001"])

    def test_week_window_uses_rationalization_utc_timestamp_a1(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            events = []

            def add(event_type, subject, payload, ts):
                events.append({"seq": len(events) + 1, "ts": ts, "type": event_type,
                               "subject": subject, "payload": payload})

            for index, name in enumerate(("A", "B", "C"), 1):
                add("atividade.opened", f"atividade:U{name}",
                    {"ulid": f"U{name}", "num": f"atv-{index:03d}",
                     "operacao": "edge", "finalidade": name, "tier": "asserted",
                     "author": "operador"},
                    "2026-07-01T00:00:00+00:00")
            sessions = (
                ("old", "UA", "antigo", "2026-07-02T00:00:00+00:00"),
                ("recent-a", "UA", "novo A", "2026-07-08T00:00:00+00:00"),
                ("recent-b1", "UB", "novo B1", "2026-07-09T00:00:00+00:00"),
                ("recent-b2", "UB", "novo B2", "2026-07-10T00:00:00+00:00"),
                ("future", "UC", "ainda não", "2026-07-12T00:00:00+00:00"),
            )
            for session, activity, novo, ts in sessions:
                add("atividade.touched", f"atividade:{activity}",
                    {"ref": activity, "sessao": session, "novo": novo,
                     "files": [], "spans": [], "tier": "llm_judged"}, ts)
                add("sessao.racionalizada", f"sessao:{session}",
                    {"sessao_id": session, "operacoes": ["edge"]}, ts)
            log.write_text("".join(json.dumps(event) + "\n" for event in events))

            folded = eventlog.atividades_at(ts="2026-07-11T00:00:00+00:00", log=log)
            start = "2026-07-04T00:00:00+00:00"
            end = "2026-07-11T00:00:00+00:00"
            touched_this_week = {
                ref: [touch["novo"] for touch in item["toques"]
                      if start <= touch["racionalizada_ts"] <= end]
                for ref, item in folded.items()
                if any(start <= touch["racionalizada_ts"] <= end for touch in item["toques"])
            }
            self.assertEqual(touched_this_week, {
                "edge/atv-001": ["novo A"],
                "edge/atv-002": ["novo B1", "novo B2"],
            })

    def test_touches_project_new_information_in_order_a4(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Implementar as lentes",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.touch_atividade(
                ref=ref, sessao="session-1", novo="Contrato lido",
                files=["docs/spec.md"], tier="llm_judged", log=log,
            )
            eventlog.touch_atividade(
                ref=ref, sessao="session-2", novo="Fold implementado",
                files=["tools/eventlog.py"], tier="llm_judged", log=log,
            )

            activity = eventlog.atividades_at(log=log)[ref]
            self.assertEqual(activity["novo"], ["Contrato lido", "Fold implementado"])
            self.assertEqual(activity["files"], ["docs/spec.md", "tools/eventlog.py"])
            self.assertEqual([touch["sessao"] for touch in activity["toques"]],
                             ["session-1", "session-2"])

    def test_asserted_closure_amends_and_outranks_later_llm_candidate_a7(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Comprovar precedência",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Primeira leitura",
                tier="asserted", author="operador", log=log,
            )
            amended = eventlog.close_atividade(
                ref=ref, estado="abandonada", julgamento="Emenda humana",
                tier="asserted", author="operador", log=log,
            )
            eventlog.append(
                "atividade.closed", f"atividade:{opened['payload']['ulid']}",
                {"ref": opened["payload"]["ulid"], "estado": "cumprida",
                 "julgamento": "Candidato posterior", "superada_por": None,
                 "tier": "llm_judged", "author": "racionalizador"},
                log=log,
            )

            activity = eventlog.atividades_at(log=log)[ref]
            self.assertEqual(len(activity["fechos"]), 3)
            self.assertEqual(activity["fecho"]["seq"], amended["seq"])
            self.assertEqual(activity["estado"], "abandonada")
            self.assertEqual(activity["fechos"][-1]["julgamento"], "Candidato posterior")

    def test_touching_a_closed_activity_records_evidence_without_reopening_a8(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Fechar sem perder evidência",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=ref, estado="cumprida", julgamento="Finalidade cumprida",
                tier="asserted", author="operador", log=log,
            )
            eventlog.touch_atividade(
                ref=ref, sessao="late-session", novo="Contradição nova",
                tier="llm_judged", log=log,
            )

            activity = eventlog.atividades_at(log=log)[ref]
            self.assertEqual(activity["estado"], "cumprida")
            self.assertEqual(activity["novo"], ["Contradição nova"])

    def test_sessions_without_touch_count_only_later_rationalizations_in_operation_a9(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Detectar esfriamento",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            for session, operations in (
                ("s1", ["edge"]), ("other", ["juridico"]), ("s2", ["edge"]),
            ):
                eventlog.append(
                    "sessao.racionalizada", f"sessao:{session}",
                    {"sessao_id": session, "operacoes": operations}, log=log,
                )
            self.assertEqual(eventlog.atividades_at(log=log)[ref]["sessoes_sem_toque"], 2)

    def test_organizational_addresses_join_files_and_changed_hash_marks_old_stale_a3(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Usar um arquivo",
                tier="asserted", author="operador", log=log,
            )
            ref = f"edge/{opened['payload']['num']}"
            for session, digest in (("s1", "old-hash"), ("s2", "new-hash")):
                eventlog.append(
                    "sessao.racionalizada", f"sessao:{session}",
                    {"sessao_id": session, "operacoes": ["edge"],
                     "organizacional": {"enderecos": [
                         {"atividade": ref, "path": "tools/eventlog.py",
                          "papel": "implementation", "sha256": digest},
                     ]}},
                    log=log,
                )
            activity = eventlog.atividades_at(log=log)[ref]
            self.assertEqual(activity["files"], ["tools/eventlog.py"])
            self.assertEqual([address["stale"] for address in activity["enderecos"]],
                             [True, False])


if __name__ == "__main__":
    unittest.main()
