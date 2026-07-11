"""A21 — o ledger, os folds e sua projeção não atravessam provider/modelo."""

import builtins
import importlib
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

_PROVIDER_ROOTS = frozenset({"openai", "graphiti_core"})


@contextmanager
def _providers_absent_from_module_cache():
    saved = {
        name: module
        for name, module in tuple(sys.modules.items())
        if name.split(".", 1)[0] in _PROVIDER_ROOTS
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name.split(".", 1)[0] in _PROVIDER_ROOTS:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class LensesZeroLlmA21(unittest.TestCase):
    def test_s1_through_s5_a25_and_graph_projection_are_mechanical(self):
        provider_imports = []
        completer_calls = []
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            root = name.split(".", 1)[0]
            if root in _PROVIDER_ROOTS:
                provider_imports.append(name)
                raise AssertionError(f"provider import forbidden on lenses path: {name}")
            return original_import(name, *args, **kwargs)

        def forbidden_completer(*args, **kwargs):
            completer_calls.append((args, kwargs))
            raise AssertionError("LLM completer called on mechanical lenses path")

        with _providers_absent_from_module_cache(), mock.patch(
            "builtins.__import__", side_effect=guarded_import
        ):
            eventlog = importlib.import_module("eventlog")
            graph_store = importlib.import_module("graph_store")
            portfolio = importlib.import_module("portfolio")
            publisher = importlib.import_module("publisher")
            llm = importlib.import_module("_llm")
            llm_routes = importlib.import_module("llm_routes")

            with mock.patch.object(llm, "complete", side_effect=forbidden_completer), \
                    mock.patch.object(
                        llm_routes, "completer_for", side_effect=forbidden_completer
                    ), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                dispatch = eventlog.test_dispatch_id()

                # S1/S2 — atividade e grãos reais, incluindo o join de admissibilidade A25.
                arc = eventlog.open_arco(
                    operacao="edge", nome="A21", tier="asserted",
                    author="operador", log=log,
                )
                arc_ref = f"edge/{arc['payload']['num']}"
                activity = eventlog.open_atividade(
                    operacao="edge", finalidade="provar caminho mecânico", arco=arc_ref,
                    tier="asserted", author="operador", log=log,
                )
                activity_ref = f"edge/{activity['payload']['num']}"
                eventlog.touch_atividade(
                    ref=activity_ref, sessao="session-a21", novo="evidência",
                    files=["tools/eventlog.py"], tier="llm_judged", log=log,
                )
                run = eventlog.open_run(
                    atividades=[activity_ref], config={"fixture": "a21"},
                    eval={"metric": "accuracy", "predicao": "sobe"},
                    leva="leva-a21", tier="asserted", log=log,
                )
                run_ref = f"edge/{run['payload']['num']}"
                fact = eventlog.observe_fato(
                    atividade=activity_ref, run=run_ref, leva="leva-a21",
                    body="accuracy=1", medida={"valor": 1, "como": "fixture"},
                    tier="asserted", log=log,
                )
                fact_ref = f"edge/{fact['payload']['num']}"
                eventlog.close_run(
                    ref=run_ref, resultado="accuracy=1", tier="asserted", log=log,
                )
                eventlog.close_arco(
                    ref=arc_ref, valencia="supports", julgamento="coerente",
                    tier="asserted", log=log,
                )
                eventlog.set_marco(
                    operacao="edge", ref=run_ref, rationale="estável",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                eventlog.instrument_failure(
                    instrumento="fixture", leva="leva-a21",
                    detalhe="checksum divergente", log=log,
                )

                # S3 — claims, promoção e contestação/adjudicação por evidência real.
                declared = eventlog.declare_hypothesis(
                    "A projeção é mecânica",
                    {"metric": "provider_calls", "threshold": 0, "direction": "menor"},
                    author="operador", log=log,
                )
                hypothesized = eventlog.hypothesize_claim(
                    statement="Nenhum provider participa", origem_sessao="session-a21",
                    derivation_key="a21-claim",
                    falsifier={"metric": "provider_calls", "threshold": 0,
                               "direction": "maior"},
                    log=log,
                )
                eventlog.promote_claim(
                    hypothesized=hypothesized["payload"]["ulid"],
                    declared=declared["payload"]["ulid"], log=log,
                )
                eventlog.bears_on(
                    ref=activity_ref, alvo=declared["payload"]["ulid"],
                    valencia="supports", tier="asserted", log=log,
                )
                eventlog.raise_contest(
                    alvo=declared["payload"]["ulid"], evidencia=fact_ref,
                    detalhe="exercitar o fold", author="grill", log=log,
                )
                eventlog.adjudicate_contest(
                    alvo=declared["payload"]["ulid"], veredito="mantido",
                    rationale="fixture suficiente", dispatch_id=dispatch,
                    author="operador", log=log,
                )
                eventlog.close_atividade(
                    ref=activity_ref, estado="cumprida", julgamento="provado",
                    tier="asserted", author="operador", rationale="fixture concluída",
                    dispatch_id=dispatch, log=log,
                )
                eventlog.reopen_atividade(
                    ref=activity_ref, motivo="exercitar replay", tier="asserted",
                    author="operador", rationale="teste A21", dispatch_id=dispatch,
                    log=log,
                )
                reconcile_candidate = eventlog.open_atividade(
                    operacao="edge", finalidade="disparar reconciliação mecânica",
                    tier="asserted", author="operador", log=log,
                )
                reconcile_candidate_ref = (
                    f"edge/{reconcile_candidate['payload']['num']}"
                )
                eventlog.close_atividade(
                    ref=reconcile_candidate_ref, estado="cumprida",
                    julgamento="fecho antes do novo sinal", tier="asserted",
                    author="operador", rationale="fixture S7",
                    dispatch_id=dispatch, log=log,
                )
                eventlog.touch_atividade(
                    ref=reconcile_candidate_ref, sessao="session-a21-late",
                    novo="evidência posterior ao fecho", tier="llm_judged", log=log,
                )

                # S4 — mapa, dependências, frontier e mudança de estado.
                way_map = eventlog.open_map(
                    operacao="edge", titulo="Mapa A21", rationale="prova dinâmica",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                map_ref = f"edge/{way_map['payload']['num']}"
                first_ticket = eventlog.open_ticket(
                    map=map_ref, titulo="Primeiro", question="Q1?", rationale="r1",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                first_ticket_ref = f"edge/{first_ticket['payload']['num']}"
                second_ticket = eventlog.open_ticket(
                    map=map_ref, titulo="Segundo", question="Q2?", rationale="r2",
                    blocked_by=[first_ticket_ref], dispatch_id=dispatch,
                    author="operador", log=log,
                )
                second_ticket_ref = f"edge/{second_ticket['payload']['num']}"
                eventlog.change_ticket_deps(
                    ref=second_ticket_ref, blocked_by=[], rationale="desbloqueado",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                eventlog.set_map_state(
                    ref=map_ref, estado="pausado", rationale="exercitar estado",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                eventlog.set_map_state(
                    ref=map_ref, estado="ativado", rationale="retomar",
                    dispatch_id=dispatch, author="operador", log=log,
                )

                # S5 — dois moves reais: um ratificado/materializado e outro declinado.
                archive_effect = {
                    "event_type": "map.state",
                    "subject": f"map:{way_map['payload']['ulid']}",
                    "payload": {
                        "ref": way_map["payload"]["ulid"], "estado": "arquivado",
                        "rationale": "fim da fixture", "dispatch_id": dispatch,
                        "author": "operador",
                    },
                }
                proposed = eventlog.propose_move(
                    kind="map.archive", alvo=map_ref, effect=archive_effect,
                    expects={"estado": "ativado"}, evidencia=[fact_ref],
                    rationale="arquivar", basis_seq=len(eventlog.read(log=log)), log=log,
                )
                eventlog.ratify_move(
                    ref=proposed["payload"]["ulid"], rationale="ratificado",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                declined_map = eventlog.open_map(
                    operacao="edge", titulo="Mapa declinado", rationale="segundo move",
                    dispatch_id=dispatch, author="operador", log=log,
                )
                declined_map_ref = f"edge/{declined_map['payload']['num']}"
                eventlog.open_ticket(
                    map=declined_map_ref, titulo="Permanece aberto", question="Q3?",
                    rationale="mantém frontier", dispatch_id=dispatch,
                    author="operador", log=log,
                )
                declined_effect = {
                    "event_type": "map.state",
                    "subject": f"map:{declined_map['payload']['ulid']}",
                    "payload": {
                        "ref": declined_map["payload"]["ulid"], "estado": "arquivado",
                        "rationale": "não executar", "dispatch_id": dispatch,
                        "author": "operador",
                    },
                }
                declined = eventlog.propose_move(
                    kind="map.archive", alvo=declined_map_ref, effect=declined_effect,
                    expects={"estado": "ativado"}, evidencia=[fact_ref],
                    rationale="proposta recusável",
                    basis_seq=len(eventlog.read(log=log)), log=log,
                )
                eventlog.decline_move(
                    ref=declined["payload"]["ulid"], reason="não agora",
                    dispatch_id=dispatch, author="operador", pin=True, log=log,
                )

                activities = eventlog.atividades_at(log=log)
                runs = eventlog.runs_at(log=log)
                facts = eventlog.fatos_at(log=log)
                arcs = eventlog.arcos_at(log=log)
                claims = eventlog.claims_at(log=log)
                presumptions = eventlog.presumptions_at(log=log)
                wayfinds = eventlog.wayfinds_at(log=log)
                frontier = eventlog.frontier_of(declined_map_ref, log=log)
                landmark = eventlog.marco_of("edge", log=log)
                self.assertIn(activity_ref, activities)
                self.assertEqual(runs[run_ref]["admissibilidade"], "suspeita")
                self.assertEqual(facts[fact_ref]["admissibilidade"], "suspeita")
                self.assertIn(arc_ref, arcs)
                self.assertIn(declared["payload"]["ulid"], claims["declared"])
                self.assertTrue(presumptions["nodes"])
                self.assertTrue(wayfinds["moves"]["ratificados"])
                self.assertTrue(wayfinds["moves"]["declinados"])
                self.assertTrue(frontier)
                self.assertEqual(landmark["ref"], run_ref)
                self.assertTrue(portfolio.direction_gate(dispatch, log))

                reconciliation = portfolio.reconcile(log)
                self.assertTrue(reconciliation["emitted"])
                self.assertEqual(
                    reconciliation["emitted"][0]["payload"]["kind"], "contest"
                )

                projection = publisher.project_lentes(log, graph_store.FakeGraph())
                self.assertTrue(projection.complete)

            self.assertEqual(provider_imports, [])
            self.assertEqual(completer_calls, [])
            self.assertFalse(any(
                name.split(".", 1)[0] in _PROVIDER_ROOTS for name in sys.modules
            ))


if __name__ == "__main__":
    unittest.main()
