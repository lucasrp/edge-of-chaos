"""Vertical acceptances for the explicitly bound grill Turn."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import portfolio  # noqa: E402


class PortfolioTurn(unittest.TestCase):
    def test_mentor_writeback_uses_executable_bound_map_surface(self):
        skill = (REPO / "skills" / "mentor" / "SKILL.md").read_text()
        for token in (
            "tools/edge-python <<'PY'",
            'sys.path.insert(0, "tools")',
            "import eventlog",
            "import portfolio",
            'DISPATCH_ID = "',
            'portfolio.turn(DISPATCH_ID, "edge", eventlog.LOG).map(',
            'thread="<label>"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, skill)
        self.assertIn("Nunca derive o dispatch", skill)
        self.assertIn("Nunca chame `eventlog.open_map`", skill)
        subprocess.run(
            [str(REPO / "tools" / "edge-python"), "-c",
             "import sys; sys.path.insert(0, 'tools'); import eventlog, portfolio"],
            cwd=REPO, check=True, capture_output=True, text=True,
        )

    def test_construction_requires_explicit_nonblank_dispatch_and_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(TypeError):
                portfolio.turn(log=log)
            for dispatch_id, operation in (("", "edge"), ("d1", " ")):
                with self.subTest(dispatch_id=dispatch_id, operation=operation):
                    with self.assertRaises(ValueError):
                        portfolio.turn(dispatch_id, operation, log)

            bound = portfolio.turn("d1", "edge", log)
            self.assertEqual(bound.dispatch_id, "d1")
            self.assertEqual(bound.operacao, "edge")

    def test_open_echoes_the_bind_and_sets_focus_for_the_next_touch(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            bound = portfolio.turn("dispatch-open", "edge", log)

            opened = bound.open(
                finalidade="Atividade focada", eval={"regua": "resultado"},
            )
            eventlog.open_atividade(
                operacao="edge", finalidade="Concorrente sem foco",
                tier="asserted", author="operador", log=log,
            )
            touched = bound.touch(sessao="s1", novo="Avanço no foco")

            self.assertIsNone(opened["before"])
            self.assertEqual(opened["event"]["payload"]["dispatch_id"], "dispatch-open")
            self.assertEqual(opened["event"]["payload"]["operacao"], "edge")
            self.assertEqual(opened["after"]["finalidade"], "Atividade focada")
            self.assertEqual(touched["target"], opened["target"])

    def test_map_uses_injected_thread_resolver_and_echoes_bound_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            calls = []

            def resolve(label):
                calls.append(label)
                return [{"uuid": "thread-uuid", "display": "Thread canônica"}]

            echo = portfolio.turn("dispatch-map", "edge", log).map(
                titulo="Mapa A34", rationale="Decisão curatorial", thread="V10",
                resolve_thread_fn=resolve,
            )

            self.assertEqual(calls, ["V10"])
            self.assertEqual(echo["target"], "edge/map-001")
            self.assertIsNone(echo["before"])
            self.assertEqual(echo["event"]["payload"]["dispatch_id"], "dispatch-map")
            self.assertEqual(echo["event"]["payload"]["operacao"], "edge")
            self.assertEqual(
                echo["after"]["thread"],
                {"uuid": "thread-uuid", "display": "Thread canônica"},
            )

    def test_map_uses_install_resolver_by_default_for_a_thread_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch(
                "thread_resolver.resolve_for_install",
                return_value=[{"uuid": "production-uuid", "display": "Produção"}],
            ) as resolve:
                echo = portfolio.turn("dispatch-map", "edge", log).map(
                    titulo="Mapa real", rationale="Wiring production", thread="V10",
                )

            resolve.assert_called_once_with("V10")
            self.assertEqual(echo["after"]["thread"]["uuid"], "production-uuid")

    def test_map_without_thread_never_opens_the_install_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch(
                "thread_resolver.resolve_for_install",
                side_effect=AssertionError("thread=None must not open Neo4j"),
            ) as resolve:
                echo = portfolio.turn("dispatch-map", "edge", log).map(
                    titulo="Mapa local", rationale="Sem thread Graphiti",
                )

            resolve.assert_not_called()
            self.assertIsNone(echo["after"]["thread"])

    def test_map_rejects_raw_thread_snapshot_without_resolving_or_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch("thread_resolver.resolve_for_install") as resolve:
                with self.assertRaisesRegex(ValueError, "label"):
                    portfolio.turn("dispatch-map", "edge", log).map(
                        titulo="Mapa forjado", rationale="Não confiar no caller",
                        thread={"uuid": "forged", "display": "Forjado"},
                    )

            resolve.assert_not_called()
            self.assertFalse(log.exists(), "raw snapshot refusal must write zero bytes")

    def test_map_resolution_refusal_writes_zero_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "exactly one"):
                portfolio.turn("dispatch-map", "edge", log).map(
                    titulo="Mapa sem entidade", rationale="Falhar antes da caneta",
                    thread="inexistente", resolve_thread_fn=lambda _label: [],
                )
            self.assertFalse(log.exists(), "resolution refusal must write zero bytes")

    def test_touch_uses_the_only_open_activity_and_echoes_before_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Alvo único",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            bound = portfolio.turn("dispatch-touch", "edge", log)

            echo = bound.touch(
                sessao="s1", novo="Evidência nova", tier="asserted",
            )

            self.assertEqual(echo["target"], activity_ref)
            self.assertEqual(echo["before"]["toques"], [])
            self.assertEqual(echo["after"]["novo"], ["Evidência nova"])
            payload = echo["event"]["payload"]
            self.assertEqual(payload["ref"], opened["payload"]["ulid"])
            self.assertEqual(payload["dispatch_id"], "dispatch-touch")
            self.assertEqual(payload["operacao"], "edge")

    def test_touch_without_target_rejects_two_open_activities(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for purpose in ("A", "B"):
                eventlog.open_atividade(
                    operacao="edge", finalidade=purpose,
                    tier="asserted", author="operador", log=log,
                )
            bound = portfolio.turn("dispatch-touch", "edge", log)

            with self.assertRaises(portfolio.AmbiguousFocus):
                bound.touch(sessao="s1", novo="Sem alvo único")

            self.assertEqual(eventlog.read(types=["atividade.touched"], log=log), [])

    def test_close_requires_an_explicit_activity_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_atividade(
                operacao="edge", finalidade="Não usar foco para fechar",
                tier="asserted", author="operador", log=log,
            )
            bound = portfolio.turn("dispatch-close", "edge", log)

            with self.assertRaisesRegex(ValueError, "explicit.*activity|activity.*explicit"):
                bound.close(
                    estado="cumprida", julgamento="Terminou", rationale="Confirmado",
                )

            self.assertEqual(eventlog.read(types=["atividade.closed"], log=log), [])

    def test_explicit_close_echoes_and_persists_the_resolved_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Fechar explicitamente",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            bound = portfolio.turn("dispatch-close", "edge", log)

            echo = bound.close(
                activity="atv-001", estado="cumprida", julgamento="Terminou",
                rationale="Confirmado pelo grill",
            )

            self.assertEqual(echo["target"], activity_ref)
            self.assertEqual(echo["before"]["estado"], "aberta")
            self.assertEqual(echo["after"]["estado"], "cumprida")
            payload = echo["event"]["payload"]
            self.assertEqual(payload["ref"], opened["payload"]["ulid"])
            self.assertEqual(payload["dispatch_id"], "dispatch-close")
            self.assertEqual(payload["operacao"], "edge")

    def test_stale_implicit_focus_is_rejected_by_the_pen_under_lock_a35(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Foco que ficará stale",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            bound = portfolio.turn("dispatch-turn", "edge", log)
            bound.touch(
                activity=activity_ref, sessao="s1", novo="Foco estabelecido",
                tier="asserted",
            )
            eventlog.close_atividade(
                ref=activity_ref, estado="cumprida", julgamento="Fechado concorrentemente",
                tier="asserted", author="operador", log=log,
            )

            with self.assertRaisesRegex(ValueError, "stale|mismatch|actual"):
                bound.touch(sessao="s2", novo="Não deve landar", tier="asserted")

            touches = eventlog.read(types=["atividade.touched"], log=log)
            self.assertEqual(len(touches), 1)

    def test_reopen_requires_explicit_target_and_echoes_the_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Reabrir explicitamente",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            eventlog.close_atividade(
                ref=activity_ref, estado="cumprida", julgamento="Fechado",
                tier="asserted", author="operador", log=log,
            )
            bound = portfolio.turn("dispatch-reopen", "edge", log)
            with self.assertRaisesRegex(ValueError, "explicit"):
                bound.reopen(motivo="Sem alvo", rationale="Não pode")

            echo = bound.reopen(
                activity=activity_ref, motivo="Evidência nova",
                rationale="Reabrir conscientemente",
            )

            self.assertEqual(echo["before"]["estado"], "cumprida")
            self.assertEqual(echo["after"]["estado"], "reaberta")
            self.assertEqual(echo["event"]["payload"]["dispatch_id"], "dispatch-reopen")
            self.assertEqual(echo["event"]["payload"]["operacao"], "edge")

    def test_ratify_requires_an_explicit_move_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            bound = portfolio.turn("dispatch-ratify", "edge", log)

            with self.assertRaisesRegex(ValueError, "explicit"):
                bound.ratify(rationale="Sem move não vale")

    def test_ratify_echoes_and_persists_the_bound_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Arquivar", rationale="Mapa",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
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
                        "rationale": "Encerrar mapa", "dispatch_id": "future",
                        "author": "operador",
                    },
                },
                expects={"estado": "ativado"},
                evidencia=[evidence["payload"]["ulid"]], rationale="Propor arquivo",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            move_ulid = proposed["payload"]["ulid"]
            bound = portfolio.turn("dispatch-ratify", "edge", log)

            echo = bound.ratify(move=move_ulid, rationale="Ratificar conscientemente")

            self.assertEqual(echo["before"]["estado"], "proposto")
            self.assertEqual(echo["after"]["estado"], "ratificado")
            ratified = echo["event"][0]
            self.assertEqual(ratified["payload"]["ref"], move_ulid)
            self.assertEqual(ratified["payload"]["dispatch_id"], "dispatch-ratify")
            self.assertEqual(ratified["payload"]["operacao"], "edge")

    def test_decline_requires_explicit_move_and_echoes_the_bound_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Não arquivar", rationale="Mapa",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
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
                        "rationale": "Encerrar mapa", "dispatch_id": "future",
                        "author": "operador",
                    },
                },
                expects={"estado": "ativado"},
                evidencia=[evidence["payload"]["ulid"]], rationale="Propor arquivo",
                basis_seq=eventlog.read(log=log)[-1]["seq"], log=log,
            )
            move_ulid = proposed["payload"]["ulid"]
            bound = portfolio.turn("dispatch-decline", "edge", log)
            with self.assertRaisesRegex(ValueError, "explicit"):
                bound.decline(reason="Sem move")

            echo = bound.decline(
                move=move_ulid, reason="Manter mapa", rationale="Decisão do grill", pin=True,
            )

            self.assertEqual(echo["before"]["estado"], "proposto")
            self.assertEqual(echo["after"]["estado"], "declinado")
            payload = echo["event"]["payload"]
            self.assertEqual(payload["dispatch_id"], "dispatch-decline")
            self.assertEqual(payload["operacao"], "edge")
            self.assertEqual(payload["alvo"], opened_map["payload"]["ulid"])

    def test_refute_requires_explicit_source_and_target_and_echoes_resolved_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            activity = eventlog.open_atividade(
                operacao="edge", finalidade="Testar hipótese",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{activity['payload']['num']}"
            hypothesis = eventlog.declare_hypothesis(
                "A estratégia funciona",
                {"metric": "accuracy", "threshold": 0.8, "direction": "maior"},
                log=log,
            )
            hypothesis_ulid = hypothesis["payload"]["ulid"]
            bound = portfolio.turn("dispatch-refute", "edge", log)
            with self.assertRaisesRegex(ValueError, "explicit"):
                bound.refute(activity=activity_ref)

            echo = bound.refute(activity="atv-001", alvo=hypothesis_ulid,
                                evidencia="holdout-1")

            self.assertEqual(echo["before"]["bears_on"], [])
            self.assertEqual(echo["after"]["bears_on"][0]["valencia"], "refutes")
            payload = echo["event"]["payload"]
            self.assertEqual(payload["ref"], activity["payload"]["ulid"])
            self.assertEqual(payload["alvo"], hypothesis_ulid)
            self.assertEqual(payload["dispatch_id"], "dispatch-refute")
            self.assertEqual(payload["operacao"], "edge")


if __name__ == "__main__":
    unittest.main()
