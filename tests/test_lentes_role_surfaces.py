"""S12b — portfolio is an explicit role surface, never ambient wake context."""

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import briefing  # noqa: E402
import eventlog  # noqa: E402
import portfolio  # noqa: E402
import predispatch  # noqa: E402
import quente  # noqa: E402
import recall  # noqa: E402


SUBGRAPH = {
    "codename": "ed",
    "objective": "orientar sem cabresto",
    "bets": [],
    "artefatos": [],
    "clusters": [],
    "experiments": [],
    "assets": [],
}


class PortfolioRecallIsOptIn(unittest.TestCase):
    def test_opt_in_consumes_the_real_portfolio_fold_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="alpha", titulo="Mapa vivo", rationale="Orientar o trabalho",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"alpha/{opened_map['payload']['num']}"
            activity = eventlog.open_atividade(
                operacao="alpha", finalidade="Medir a integração",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"alpha/{activity['payload']['num']}"
            run = eventlog.open_run(
                atividades=[activity_ref], config={"browser": "chromium"},
                eval={"metric": "pass rate", "predicao": "sobe"},
                leva="batch-a25", tier="asserted", log=log,
            )
            run_ref = f"alpha/{run['payload']['num']}"
            eventlog.instrument_failure(
                instrumento="playwright", leva="batch-a25",
                detalhe="browser caiu", log=log,
            )

            text = recall.compose_portfolio_recall_brief(
                subgraph=SUBGRAPH,
                portfolio_fn=portfolio.portfolio_at,
                log=log,
            )

            self.assertIn(map_ref, text)
            self.assertIn(run_ref, text)
            self.assertIn("batch-a25", text)
            self.assertIn("suspeita", text)

    def test_active_map_is_visible_only_on_the_explicit_portfolio_surface(self):
        snapshot = {
            "mapas_ativos": [{
                "ref": "alpha/map-007",
                "titulo": "Escolher a arquitetura",
                "frontier": [["alpha/tkt-003"], ["alpha/tkt-004"]],
            }],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [],
            "admissibilidade": [],
        }

        ordinary = recall.compose_recall_brief(subgraph=SUBGRAPH)
        portfolio_view = recall.compose_portfolio_recall_brief(
            subgraph=SUBGRAPH,
            portfolio_fn=lambda **_kwargs: snapshot,
        )

        self.assertNotIn("alpha/map-007", ordinary)
        self.assertIn("alpha/map-007", portfolio_view)
        self.assertIn("alpha/tkt-003", portfolio_view)

    def test_activity_missed_by_later_sessions_is_named_for_the_wake(self):
        snapshot = {
            "mapas_ativos": [],
            "atividades_perdidas": [{
                "ref": "alpha/atv-009",
                "finalidade": "Fechar o contrato de cache",
                "sessoes_sem_toque": 3,
            }],
            "contested": [],
            "agenda": [],
            "admissibilidade": [],
        }

        text = recall.compose_portfolio_recall_brief(
            subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: snapshot,
        )

        self.assertIn("alpha/atv-009", text)
        self.assertIn("3 sessões sem toque", text)

    def test_real_contested_item_stays_visible_outside_the_ordinal_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "contest.raised", "atividade:atv-real-011",
                {
                    "alvo": "atv-real-011",
                    "evidencia": "alpha/atv-011",
                    "detalhe": "O fecho foi contradito por evidência nova",
                    "author": "mentor",
                },
                log=log,
            )

            text = recall.compose_portfolio_recall_brief(
                subgraph=SUBGRAPH,
                portfolio_fn=lambda **kwargs: portfolio.portfolio_at(
                    top_k=0, **kwargs,
                ),
                log=log,
            )

        self.assertIn("Contested — faixa reservada", text)
        self.assertIn("atv-real-011", text)
        self.assertIn("alpha/atv-011", text)
        self.assertIn("contradito por evidência nova", text)

    def test_bounded_pull_agenda_renders_moves_and_questions_without_an_inbox_count(self):
        snapshot = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [
                {"tipo": "move", "ref": "move-17", "rationale": "Adjudicar o novo fato"},
                {"tipo": "pergunta", "ref": "claim-4",
                 "texto": "Qual premissa poda mais ramos?"},
            ],
            "admissibilidade": [],
        }

        text = recall.compose_portfolio_recall_brief(
            subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: snapshot,
        )

        self.assertIn("Agenda pull bounded", text)
        self.assertIn("[move] move-17 — Adjudicar o novo fato", text)
        self.assertIn("[pergunta] claim-4 — Qual premissa poda mais ramos?", text)
        self.assertNotIn("pendentes", text.lower())

    def test_instrument_failure_marks_the_matching_batch_in_the_admissibility_brief(self):
        snapshot = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [],
            "admissibilidade": [{
                "tipo": "run",
                "ref": "alpha/run-004",
                "leva": "batch-browser-2",
                "admissibilidade": "suspeita",
            }],
        }

        text = recall.compose_portfolio_recall_brief(
            subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: snapshot,
        )

        self.assertIn("Admissibilidade suspeita", text)
        self.assertIn("alpha/run-004", text)
        self.assertIn("batch-browser-2", text)
        self.assertIn("suspeita", text)
        self.assertNotIn("instrumento None", text)

    def test_opt_in_fails_loud_when_the_portfolio_snapshot_is_incomplete(self):
        incomplete = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [],
        }

        with self.assertRaisesRegex(ValueError, "admissibilidade"):
            recall.compose_portfolio_recall_brief(
                subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: incomplete,
            )

    def test_opt_in_fails_loud_when_a_lane_contains_a_non_mapping_item(self):
        malformed = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": ["alpha/atv-011"],
            "agenda": [],
            "admissibilidade": [],
        }

        with self.assertRaisesRegex(ValueError, "contested.*dict"):
            recall.compose_portfolio_recall_brief(
                subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: malformed,
            )

    def test_opt_in_rejects_an_unknown_agenda_item_type(self):
        malformed = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [{"tipo": "inbox", "body": "não pode virar fila"}],
            "admissibilidade": [],
        }

        with self.assertRaisesRegex(ValueError, "agenda.*tipo"):
            recall.compose_portfolio_recall_brief(
                subgraph=SUBGRAPH, portfolio_fn=lambda **_kwargs: malformed,
            )

    def test_opt_in_passes_the_selected_ledger_snapshot_to_the_fold(self):
        calls = []
        snapshot = {
            "mapas_ativos": [],
            "atividades_perdidas": [],
            "contested": [],
            "agenda": [],
            "admissibilidade": [],
        }

        def portfolio_reader(**kwargs):
            calls.append(kwargs)
            return snapshot

        selected_log = Path("/tmp/selected-edge-ledger.jsonl")
        recall.compose_portfolio_recall_brief(
            subgraph=SUBGRAPH,
            group="cortex-group-b",
            portfolio_fn=portfolio_reader,
            log=selected_log,
            seq=37,
            ts="2026-07-11T12:00:00+00:00",
        )

        self.assertEqual(calls, [{
            "log": selected_log,
            "seq": 37,
            "ts": "2026-07-11T12:00:00+00:00",
        }])

    def test_opt_in_rejects_corrupt_items_before_rendering_orientation(self):
        valid = {
            "mapas_ativos": [{
                "ref": "alpha/map-001", "titulo": "Mapa",
                "frontier": [["alpha/tkt-001"]],
            }],
            "atividades_perdidas": [{
                "ref": "alpha/atv-001", "finalidade": "Investigar",
                "sessoes_sem_toque": 2,
            }],
            "contested": [{
                "alvo": "atv-001", "evidencia": "alpha/atv-001",
                "detalhe": "Evidência posterior", "seq": 9,
            }],
            "agenda": [
                {"tipo": "move", "ref": "move-1", "rationale": "Ratificar"},
                {"tipo": "pergunta", "ref": "claim-1", "texto": "Qual poda?"},
            ],
            "admissibilidade": [{
                "tipo": "run", "ref": "alpha/run-001", "leva": "batch-1",
                "instrumento": "playwright", "admissibilidade": "suspeita",
            }],
        }
        corruptions = {
            "mapas_ativos": {},
            "map_frontier": {"frontier": "alpha/tkt-001"},
            "atividades_perdidas": {"sessoes_sem_toque": "2"},
            "contested": {"alvo": None},
            "agenda_move": {"rationale": None},
            "agenda_pergunta": {"texto": None},
            "admissibilidade": {"leva": None},
            "instrumento": {"instrumento": 42},
        }

        for case, corruption in corruptions.items():
            malformed = {lane: [dict(item) for item in items]
                         for lane, items in valid.items()}
            if case == "mapas_ativos":
                malformed["mapas_ativos"][0] = corruption
            elif case == "map_frontier":
                malformed["mapas_ativos"][0].update(corruption)
            elif case == "atividades_perdidas":
                malformed["atividades_perdidas"][0].update(corruption)
            elif case == "contested":
                malformed["contested"][0].update(corruption)
            elif case == "agenda_move":
                malformed["agenda"][0].update(corruption)
            elif case == "agenda_pergunta":
                malformed["agenda"][1].update(corruption)
            else:
                malformed["admissibilidade"][0].update(corruption)
            with self.subTest(case=case), self.assertRaisesRegex(
                ValueError, case.split("_")[0],
            ):
                recall.compose_portfolio_recall_brief(
                    subgraph=SUBGRAPH,
                    portfolio_fn=lambda **_kwargs: malformed,
                )


class RoleContractsAreExplicit(unittest.TestCase):
    def test_assemble_is_not_an_authorized_portfolio_opt_in_caller(self):
        recall_skill = (REPO / "skills/recall/SKILL.md").read_text()
        authorization = recall_skill.split(
            "That command is the **shared, map-blind default**.", 1,
        )[1].split("surface instead:", 1)[0]

        self.assertNotIn("`assemble`", authorization)

    def test_only_portfolio_reading_role_contracts_name_the_opt_in_callable(self):
        allowed = (
            "skills/wake/SKILL.md",
            "skills/mentor/SKILL.md",
            "skills/recall/SKILL.md",
        )
        map_blind = (
            "skills/assemble/SKILL.md",
            "skills/delta/SKILL.md",
            "skills/lazer/SKILL.md",
            "skills/_shared/scaffold.md",  # owns the diverge role
        )

        for relative in allowed:
            with self.subTest(role=relative):
                self.assertIn(
                    "compose_portfolio_recall_brief",
                    (REPO / relative).read_text(),
                )
        for relative in map_blind:
            with self.subTest(role=relative):
                self.assertNotIn(
                    "compose_portfolio_recall_brief",
                    (REPO / relative).read_text(),
                )

    def test_wake_has_exactly_one_portfolio_output_owner(self):
        wake = (REPO / "skills/wake/SKILL.md").read_text()
        assemble = (REPO / "skills/assemble/SKILL.md").read_text()

        self.assertEqual(
            (wake + assemble).count("compose_portfolio_recall_brief"),
            1,
        )
        self.assertIn("recall subagent", wake)

class SharedWakeSurfacesStayMapBlind(unittest.TestCase):
    def test_briefing_quente_and_ordinary_recall_do_not_surface_a_real_map_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "log.jsonl"
            store = root / "sessions"
            store.mkdir()
            opened = eventlog.open_map(
                operacao="alpha",
                titulo="Este mapa só cabe nos papéis opt-in",
                rationale="A24 separa orientação de autorização",
                dispatch_id="dispatch-a24",
                author="operador",
                log=log,
            )
            map_ref = f"alpha/{opened['payload']['num']}"

            briefing_text = briefing.compose_briefing(
                log=log, clusters=[], roster=[],
            )
            quente_text, _window = quente.build_bundle(
                store_dir=store, repos=(), eventlog_path=log, codex_dir=False,
            )
            recall_text = recall.compose_recall_brief(subgraph=SUBGRAPH)

            self.assertNotIn(map_ref, briefing_text)
            self.assertNotIn(map_ref, quente_text)
            self.assertNotIn(map_ref, recall_text)

    def test_predispatch_default_recall_wiring_never_calls_the_portfolio_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.object(
                recall, "compose_portfolio_recall_brief",
                side_effect=AssertionError("map surface leaked into shared predispatch"),
            ), mock.patch.object(
                recall, "compose_recall_brief", return_value="ordinary recall",
            ) as ordinary:
                result = predispatch.run(
                    sweep_fn=lambda: 0,
                    briefing_fn=lambda: "ordinary briefing",
                    recall_fn=None,
                    harvest_fn=lambda: 0,
                    probe_fn=lambda _spec: None,
                    log=log,
                )

            self.assertEqual(result, ("ordinary briefing", "ordinary recall"))
            ordinary.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
