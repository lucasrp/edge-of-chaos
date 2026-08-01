"""S6 — racionalizador a-posteriori, bounded e idempotente pela entrada."""

import ast
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import racionalizador  # noqa: E402


def _nothing_changed():
    return {
        "operacoes": ["edge"],
        "stitch": {
            "goal": "implementar as lentes",
            "acao": "revisou o contrato",
            "entidades": [],
            "attribution": {
                "human_purpose": "implementar as lentes",
                "human_turn_indexes": [0],
                "edge_execution": "revisou o contrato",
                "shared_outcome": "revisou o contrato",
                "activity_relevant": True,
            },
        },
        "epistemico": {"presuncoes": []},
        "organizacional": {"enderecos": []},
        "derived_events": [],
    }


class NothingChangedTracerBullet(unittest.TestCase):
    def test_emits_only_audit_batch_and_identical_rerun_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            calls = []

            def complete_fn(prompt):
                calls.append(prompt)
                return json.dumps(_nothing_changed())

            turns = [
                {"role": "human", "text": "A spec está pronta."},
                {"role": "edge", "text": "Revisei; nada muda no que fazemos."},
            ]
            first = racionalizador.rationalize(
                "session-1",
                turns,
                complete_fn,
                log=log,
                surface="codex",
                watermark=2,
                racionalizador_version="model-x/prompt-v1",
            )
            second = racionalizador.rationalize(
                "session-1",
                turns,
                complete_fn,
                log=log,
                surface="codex",
                watermark=2,
                racionalizador_version="model-x/prompt-v1",
            )

            written = eventlog.read(log=log)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first["emitted"], written)
            self.assertEqual(second, {"emitted": [], "skipped_reason": "already_rationalized"})
            # Empty derived + non-blank stitch.goal floors one atividade.opened (+ touch).
            self.assertEqual(
                [event["type"] for event in written],
                ["sessao.racionalizada", "atividade.opened", "atividade.touched"],
            )
            payload = written[0]["payload"]
            self.assertEqual(payload["sessao_id"], "session-1")
            self.assertEqual(payload["surface"], "codex")
            self.assertEqual(payload["watermark"], 2)
            self.assertEqual(payload["racionalizador_version"], "model-x/prompt-v1")
            self.assertEqual(len(payload["source_hash"]), 64)
            self.assertEqual(len(payload["rationalization_id"]), 64)
            self.assertNotIn("supersedes", payload)
            # employment-gate: single-shot path persists empty cenas (no version bump)
            self.assertEqual(payload["cenas"], [])
            open_payload = written[1]["payload"]
            self.assertEqual(open_payload["finalidade"], "implementar as lentes")
            self.assertEqual(open_payload["tier"], "llm_judged")
            self.assertEqual(open_payload["author"], "racionalizador")
            self.assertEqual(open_payload["origem_sessao"], "session-1")
            self.assertEqual(written[2]["payload"]["novo"], "revisou o contrato")


class HumanPurposeOwnsTheActivity(unittest.TestCase):
    def test_edge_execution_cannot_replace_the_human_purpose(self):
        """The dialogue is shared, but the portfolio records the human's employment horizon."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"] = {
                "goal": "implementar POST /billing/recurrence com idempotency_key",
                "acao": "adicionou rota, migration e testes",
                "entidades": [],
                "attribution": {
                    "human_purpose": "controlar cobranças recorrentes a partir da conversa",
                    "human_turn_indexes": [0],
                    "edge_execution": "adicionou rota, migration e testes",
                    "shared_outcome": "a cobrança recorrente passou a ter um fluxo controlado",
                    "activity_relevant": True,
                },
            }
            turns = [
                {"role": "human", "text": (
                    "quero gerar uma cobrança ou cadastrar recorrência da conversa; "
                    "a IA deve ficar controlada nesse fluxo"
                )},
                {"role": "edge", "text": (
                    "Implementei POST /billing/recurrence com idempotency_key, migration e testes."
                )},
            ]

            result = racionalizador.rationalize(
                "session-role-attribution", turns,
                lambda _prompt: json.dumps(output), log=log,
            )

            opened = next(e for e in result["emitted"] if e["type"] == "atividade.opened")
            touched = next(e for e in result["emitted"] if e["type"] == "atividade.touched")
            self.assertEqual(
                opened["payload"]["finalidade"],
                "controlar cobranças recorrentes a partir da conversa",
            )
            self.assertEqual(
                touched["payload"]["novo"],
                "a cobrança recorrente passou a ter um fluxo controlado",
            )
            self.assertEqual(
                result["emitted"][0]["payload"]["stitch"]["attribution"]["edge_execution"],
                "adicionou rota, migration e testes",
            )

    def test_attribution_must_cite_a_human_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["attribution"]["human_turn_indexes"] = [1]

            result = racionalizador.rationalize(
                "session-wrong-speaker",
                [
                    {"role": "human", "text": "quero decidir o risco aceitável"},
                    {"role": "edge", "text": "implementei o lock"},
                ],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            self.assertEqual(result["skipped_reason"], "invalid_output")
            self.assertIn("must cite human turns: 1", result["error"])
            self.assertEqual(eventlog.read(log=log), [])

    def test_a_human_technical_tradeoff_remains_a_valid_purpose(self):
        output = _nothing_changed()
        output["stitch"]["attribution"].update({
            "human_purpose": "decidir entre lock pessimista e transação serializável",
            "human_turn_indexes": [0],
            "edge_execution": "comparou as duas estratégias com um teste de concorrência",
            "shared_outcome": "o trade-off ficou explícito para a decisão",
        })

        validated = racionalizador._validated_output(
            json.dumps(output),
            turns=racionalizador._normalized_turns([
                {"role": "human", "text": (
                    "quero discutir lock pessimista versus transação serializável"
                )},
            ]),
        )

        self.assertEqual(
            validated["derived_events"][0]["payload"]["finalidade"],
            "decidir entre lock pessimista e transação serializável",
        )


class AllOrNothingValidation(unittest.TestCase):
    def test_one_malformed_item_in_four_writes_zero_and_names_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["epistemico"]["presuncoes"] = [
                {"texto": "p1", "confirmaria": "c1", "refutaria": "r1"},
                {"texto": "p2", "confirmaria": "c2", "refutaria": "r2"},
                {"texto": "p3", "confirmaria": "c3"},
                {"texto": "p4", "confirmaria": "c4", "refutaria": "r4"},
            ]

            result = racionalizador.rationalize(
                "session-invalid",
                [{"role": "human", "text": "quatro presunções"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            self.assertEqual(result["emitted"], [])
            self.assertEqual(result["skipped_reason"], "invalid_output")
            self.assertIn("presuncoes[2].refutaria", result["error"])
            self.assertEqual(eventlog.read(log=log), [])

    def test_one_malformed_derived_event_in_four_is_rejected_before_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["derived_events"] = [
                {"type": "claim.hypothesized", "subject": "claim:a",
                 "payload": {"statement": "claim válido 1"}},
                {"type": "claim.hypothesized", "subject": "claim:b",
                 "payload": {"statement": "claim válido 2"}},
                {"type": "claim.hypothesized", "subject": "claim:c",
                 "payload": {"statement": "claim inválido", "falsifier": "prosa"}},
                {"type": "claim.hypothesized", "subject": "claim:d",
                 "payload": {"statement": "claim válido 4"}},
            ]

            result = racionalizador.rationalize(
                "session-invalid-derived",
                [{"role": "human", "text": "batch parcial"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            self.assertEqual(result["skipped_reason"], "invalid_output")
            self.assertIn("falsifier", result["error"])
            self.assertEqual(eventlog.read(log=log), [])

    def test_activity_close_from_rationalizer_is_a_typed_move_not_direct_event_a20(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge", finalidade="Fechar por proposta",
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            activity_ulid = opened["payload"]["ulid"]
            output = _nothing_changed()
            output["derived_events"] = [{
                "type": "move.proposed", "subject": "move:derived",
                "payload": {
                    "kind": "atividade.close", "alvo": activity_ref,
                    "effect": {
                        "event_type": "atividade.closed",
                        "subject": f"atividade:{activity_ulid}",
                        "payload": {
                            "ref": activity_ulid, "estado": "cumprida",
                            "julgamento": "Finalidade cumprida", "superada_por": None,
                            "tier": "asserted", "author": "grill",
                            "rationale": "Candidato para ratificação",
                            "dispatch_id": "dispatch-future",
                        },
                    },
                    "expects": {"estado": "aberta"}, "evidencia": [activity_ref],
                    "rationale": "A sessão indica fecho",
                    "basis_seq": eventlog.read(log=log)[-1]["seq"],
                },
            }]
            result = racionalizador.rationalize(
                "session-move-close", [{"role": "human", "text": "terminamos"}],
                lambda _prompt: json.dumps(output), log=log,
            )
            # move.proposed is not an activity open/touch; real goal still floors open+touch.
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                [
                    "sessao.racionalizada",
                    "move.proposed",
                    "atividade.opened",
                    "atividade.touched",
                ],
            )
            self.assertEqual(eventlog.read(types=["atividade.closed"], log=log), [])
            self.assertEqual(result["emitted"][1]["payload"]["kind"], "atividade.close")

    def test_activity_close_is_never_a_direct_rationalizer_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["derived_events"] = [{
                "type": "atividade.closed",
                "subject": "atividade:a",
                "payload": {"estado": "cumprida"},
            }]

            result = racionalizador.rationalize(
                "session-close",
                [{"role": "human", "text": "acabamos"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            self.assertEqual(result["skipped_reason"], "invalid_output")
            self.assertIn("move.proposed", result["error"])
            self.assertEqual(eventlog.read(log=log), [])

    def test_valid_derived_output_materializes_atomically_with_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["derived_events"] = [{
                "type": "claim.hypothesized",
                "subject": "claim:c",
                "payload": {"statement": "hipótese"},
            }]

            result = racionalizador.rationalize(
                "session-derived",
                [{"role": "human", "text": "extraímos uma hipótese"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            # Claim materializes with the audit; real-work goal also floors open+touch.
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                [
                    "sessao.racionalizada",
                    "claim.hypothesized",
                    "atividade.opened",
                    "atividade.touched",
                ],
            )
            claim = result["emitted"][1]["payload"]
            self.assertEqual(claim["statement"], "hipótese")
            self.assertEqual(claim["origem_sessao"], "session-derived")
            self.assertEqual(claim["tier"], "llm_judged")

    def test_operations_stitch_and_addresses_are_semantically_validated_before_append(self):
        invalid_outputs = []

        bad_operation = _nothing_changed()
        bad_operation["operacoes"] = ["Edge Project"]
        invalid_outputs.append((bad_operation, "operacoes[0]"))

        # Malformed stitch.entidades are dropped (not invalid_output) — see
        # test_malformed_stitch_entidades_are_dropped_not_invalid_output.

        missing_activity = _nothing_changed()
        missing_activity["organizacional"]["enderecos"] = [
            {"path": "tools/eventlog.py", "papel": "editado"}
        ]
        invalid_outputs.append((missing_activity, "enderecos[0].atividade"))

        bad_sha = _nothing_changed()
        bad_sha["organizacional"]["enderecos"] = [{
            "atividade": "edge/atv-001",
            "path": "tools/eventlog.py",
            "papel": "editado",
            "sha256": "not-a-sha",
        }]
        invalid_outputs.append((bad_sha, "enderecos[0].sha256"))

        bad_stat = _nothing_changed()
        bad_stat["organizacional"]["enderecos"] = [{
            "atividade": "edge/atv-001",
            "path": "tools/eventlog.py",
            "papel": "editado",
            "stat": {},
        }]
        invalid_outputs.append((bad_stat, "enderecos[0].stat"))

        for index, (output, error_field) in enumerate(invalid_outputs):
            with self.subTest(error_field=error_field), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                result = racionalizador.rationalize(
                    f"session-semantic-{index}",
                    [{"role": "human", "text": "validar tudo"}],
                    lambda _prompt, output=output: json.dumps(output),
                    log=log,
                )
                self.assertEqual(result["skipped_reason"], "invalid_output")
                self.assertIn(error_field, result["error"])
                self.assertEqual(eventlog.read(log=log), [])

    def test_full_stitch_refs_and_verifiable_addresses_survive_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["entidades"] = [
                "edge/atv-001", {"operacao": "edge", "num": "tkt-002"}
            ]
            output["organizacional"]["enderecos"] = [
                {
                    "atividade": "edge/atv-001",
                    "path": "tools/eventlog.py",
                    "papel": "editado",
                    "sha256": "A" * 64,
                },
                {
                    "atividade": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    "path": "tests/test_eventlog.py",
                    "papel": "consultado",
                    "stat": {"size": 123, "mtime_ns": 456},
                },
            ]

            result = racionalizador.rationalize(
                "session-valid-semantics",
                [{"role": "human", "text": "refs completas"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )

            payload = result["emitted"][0]["payload"]
            self.assertEqual(payload["stitch"]["entidades"], output["stitch"]["entidades"])
            self.assertEqual(
                payload["organizacional"]["enderecos"][0]["sha256"], "a" * 64
            )
            self.assertEqual(
                payload["organizacional"]["enderecos"][1]["stat"]["size"], 123
            )


class InputIdentityAndOverlay(unittest.TestCase):
    def test_new_attribution_supersedes_unpinned_activity_from_old_rationalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            old = _nothing_changed()
            old["stitch"]["attribution"].update({
                "human_purpose": "implementar lock e migration no endpoint",
                "shared_outcome": "lock e migration implementados",
            })
            new = _nothing_changed()
            new["stitch"]["attribution"].update({
                "human_purpose": "tornar a cobrança recorrente segura para uso real",
                "shared_outcome": "o risco de cobrança duplicada foi reduzido",
            })
            turns = [{"role": "human", "text": "quero cobrança recorrente segura"}]

            racionalizador.rationalize(
                "session-reframed", turns, lambda _prompt: json.dumps(old),
                log=log, racionalizador_version="prompt-v1",
            )
            racionalizador.rationalize(
                "session-reframed", turns, lambda _prompt: json.dumps(new),
                log=log, racionalizador_version="prompt-v2",
            )

            folded = eventlog.atividades_at(log=log)
            self.assertEqual(len(folded), 1)
            self.assertEqual(
                next(iter(folded.values()))["finalidade"],
                "tornar a cobrança recorrente segura para uso real",
            )

    def test_grown_session_changes_identity_and_audit_supersedes_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            complete_fn = lambda _prompt: json.dumps(_nothing_changed())
            initial = [{"role": "human", "text": "primeiro turno"}]
            grown = initial + [{"role": "edge", "text": "a sessão cresceu"}]

            first = racionalizador.rationalize(
                "session-growing", initial, complete_fn, log=log, watermark=1
            )
            second = racionalizador.rationalize(
                "session-growing", grown, complete_fn, log=log, watermark=2
            )

            first_payload = first["emitted"][0]["payload"]
            second_payload = second["emitted"][0]["payload"]
            self.assertNotEqual(second_payload["source_hash"], first_payload["source_hash"])
            self.assertNotEqual(
                second_payload["rationalization_id"], first_payload["rationalization_id"]
            )
            self.assertEqual(
                second_payload["supersedes"], first_payload["rationalization_id"]
            )
            # Each unpinned derivation is immutable in the raw log; the fold keeps
            # only the newer contribution named by supersedes.
            self.assertEqual(len(eventlog.read(log=log)), 6)

    def test_version_changes_rationalization_identity_not_evidence_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            complete_fn = lambda _prompt: json.dumps(_nothing_changed())
            turns = [{"role": "human", "text": "mesma evidência"}]

            first = racionalizador.rationalize(
                "session-versioned", turns, complete_fn, log=log,
                racionalizador_version="prompt-v1",
            )["emitted"][0]["payload"]
            second = racionalizador.rationalize(
                "session-versioned", turns, complete_fn, log=log,
                racionalizador_version="prompt-v2",
            )["emitted"][0]["payload"]

            self.assertEqual(second["source_hash"], first["source_hash"])
            self.assertNotEqual(second["rationalization_id"], first["rationalization_id"])
            self.assertEqual(second["supersedes"], first["rationalization_id"])

    def test_concurrent_identical_inputs_land_once_under_append_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            rendezvous = threading.Barrier(2)
            results = []

            def complete_fn(_prompt):
                rendezvous.wait(timeout=2)
                return json.dumps(_nothing_changed())

            def worker():
                results.append(racionalizador.rationalize(
                    "session-race",
                    [{"role": "human", "text": "mesma entrada concorrente"}],
                    complete_fn,
                    log=log,
                ))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            # floor emits audit + open + touch
            self.assertEqual(len(eventlog.read(log=log)), 3)
            self.assertEqual(sorted(len(result["emitted"]) for result in results), [0, 3])

    def test_corrupt_rationalization_payload_is_ignored_fail_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada", "sessao:corrupt", "not-an-object", log=log
            )

            result = racionalizador.rationalize(
                "session-after-corrupt",
                [{"role": "human", "text": "o log segue navegável"}],
                lambda _prompt: json.dumps(_nothing_changed()),
                log=log,
            )

            self.assertEqual(len(result["emitted"]), 3)
            self.assertEqual(len(eventlog.read(log=log)), 4)

    def test_a29_different_rebackfill_output_replaces_unpinned_grain(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first_output = _nothing_changed()
            first_output["derived_events"] = [{
                "type": "atividade.opened", "subject": "atividade:first",
                "payload": {"operacao": "edge", "finalidade": "Primeira segmentação"},
            }]
            second_output = _nothing_changed()
            second_output["derived_events"] = [{
                "type": "atividade.opened", "subject": "atividade:second",
                "payload": {"operacao": "edge", "finalidade": "Output completamente diferente",
                            "novo": "backfill maior releu a sessão"},
            }]
            first = racionalizador.rationalize(
                "session-rebackfill", [{"role": "human", "text": "parte 1"}],
                lambda _prompt: json.dumps(first_output), log=log, watermark=1,
            )
            second = racionalizador.rationalize(
                "session-rebackfill",
                [{"role": "human", "text": "parte 1"},
                 {"role": "human", "text": "parte descoberta no backfill"}],
                lambda _prompt: json.dumps(second_output), log=log, watermark=2,
            )
            self.assertEqual(len(eventlog.atividades_at(log=log)), 1)
            self.assertEqual(len(eventlog.read(types=["atividade.opened"], log=log)), 2)
            self.assertNotEqual(first["emitted"][0]["payload"]["rationalization_id"],
                                second["emitted"][0]["payload"]["rationalization_id"])
            self.assertEqual([event["type"] for event in second["emitted"]],
                             ["sessao.racionalizada", "atividade.opened",
                              "atividade.touched"])


class MarathonMechanicalCoreAndLocalBudget(unittest.TestCase):
    def test_uniform_scene_cut_covers_start_middle_end_before_consolidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            turns = [
                {"role": "human", "text": f"turn-{index}"}
                for index in range(20)
            ]
            turns[10]["text"] = "turn-10 MIDDLE_OBJECTIVE_CHANGE"
            requests = []

            def complete_fn(prompt):
                request = json.loads(prompt)
                requests.append(request)
                if request["stage"] == "scene":
                    return json.dumps({
                        "summary": " | ".join(turn["text"] for turn in request["turns"])
                    })
                output = _nothing_changed()
                output["stitch"]["attribution"].update({
                    "human_purpose": "MIDDLE_OBJECTIVE_CHANGE",
                    "shared_outcome": "MIDDLE_OBJECTIVE_CHANGE",
                })
                return json.dumps(output)

            result = racionalizador.rationalize(
                "session-marathon",
                turns,
                complete_fn,
                log=log,
                scene_turn_limit=2,
                max_scenes=3,
                sweep_token_budget=10_000,
            )

            scene_requests = [request for request in requests if request["stage"] == "scene"]
            self.assertEqual(len(scene_requests), 3)
            scene_text = " ".join(
                turn["text"] for request in scene_requests for turn in request["turns"]
            )
            self.assertIn("turn-0", scene_text)
            self.assertIn("MIDDLE_OBJECTIVE_CHANGE", scene_text)
            self.assertIn("turn-19", scene_text)
            self.assertEqual(requests[-1]["stage"], "consolidate")
            self.assertTrue(all(
                isinstance(scene["human_turn_indexes"], list)
                and scene["human_turn_indexes"]
                for scene in requests[-1]["scene_summaries"]
            ))
            self.assertEqual(result["usage"]["calls"], 4)
            self.assertLessEqual(result["usage"]["estimated_tokens"], 10_000)
            self.assertEqual(
                result["emitted"][0]["payload"]["stitch"]["goal"],
                "MIDDLE_OBJECTIVE_CHANGE",
            )
            cenas = result["emitted"][0]["payload"]["cenas"]
            self.assertEqual(len(cenas), 3)
            for cena in cenas:
                self.assertIsInstance(cena.get("summary"), str)
                self.assertTrue(cena["summary"].strip())
                self.assertIsInstance(cena.get("human_turn_indexes"), list)
                self.assertTrue(cena["human_turn_indexes"])

    def test_budget_exhaustion_leaves_no_checkpoint_and_next_call_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            turns = [{"role": "human", "text": f"turn-{index}"} for index in range(6)]
            calls = []

            def complete_fn(prompt):
                request = json.loads(prompt)
                calls.append(request)
                if request["stage"] == "scene":
                    return json.dumps({"summary": request["turns"][0]["text"]})
                return json.dumps(_nothing_changed())

            exhausted = racionalizador.rationalize(
                "session-pending",
                turns,
                complete_fn,
                log=log,
                scene_turn_limit=2,
                sweep_token_budget=1,
            )
            resumed = racionalizador.rationalize(
                "session-pending",
                turns,
                complete_fn,
                log=log,
                scene_turn_limit=2,
                sweep_token_budget=10_000,
            )

            self.assertEqual(exhausted["skipped_reason"], "budget_exhausted")
            self.assertEqual(exhausted["usage"]["calls"], 0)
            self.assertEqual(len(resumed["emitted"]), 3)
            self.assertEqual(len(eventlog.read(log=log)), 3)

    def test_completer_output_is_charged_and_oversize_response_cannot_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["unexpected_padding"] = "x" * 1_000_000

            # Budget must clear the session prompt incl. JSON instruction,
            # then fail when the padded output is charged.
            result = racionalizador.rationalize(
                "session-oversize-output",
                [{"role": "human", "text": "resposta enorme"}],
                lambda _prompt: json.dumps(output),
                log=log,
                sweep_token_budget=800,
            )

            self.assertEqual(result["skipped_reason"], "budget_exhausted")
            self.assertGreater(result["usage"]["output_tokens"], 100)
            self.assertEqual(
                result["usage"]["estimated_tokens"],
                result["usage"]["input_tokens"] + result["usage"]["output_tokens"],
            )
            self.assertEqual(eventlog.read(log=log), [])


class LooseJsonParsing(unittest.TestCase):
    def test_accepts_unescaped_control_character_from_model(self):
        self.assertEqual(racionalizador._loads_json_loose('{"text":"a\nb"}'), {"text": "a\nb"})


class ProviderFreeModule(unittest.TestCase):
    def test_only_the_injected_completer_can_reach_a_model(self):
        tree = ast.parse(Path(racionalizador.__file__).read_text())
        imported_roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }

        self.assertTrue({"openai", "graphiti_core"}.isdisjoint(imported_roots))


class PendingS6Integrations(unittest.TestCase):
    """S6 local integrations; only the external sweep coordinator remains pending."""

    def test_a28_grown_session_has_one_current_derived_contribution_and_pins_asserted_grains(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            initial_output = _nothing_changed()
            initial_output["derived_events"] = [{
                "type": "atividade.opened", "subject": "atividade:new",
                "payload": {"operacao": "edge", "finalidade": "Atividade original",
                            "novo": "abriu no começo"},
            }]
            first = racionalizador.rationalize(
                "session-overlay", [{"role": "human", "text": "começo"}],
                lambda _prompt: json.dumps(initial_output), log=log, watermark=1,
            )
            activity = next(iter(eventlog.atividades_at(log=log).values()))
            eventlog.touch_atividade(
                ref=activity["ref"], sessao="grill-pin", novo="confirmado pelo grill",
                tier="asserted", log=log,
            )
            grown_output = _nothing_changed()
            grown_output["derived_events"] = [{
                "type": "atividade.opened", "subject": "atividade:changed",
                "payload": {"operacao": "edge", "finalidade": "Segmentação diferente",
                            "novo": "sessão cresceu"},
            }]
            second = racionalizador.rationalize(
                "session-overlay",
                [{"role": "human", "text": "começo"},
                 {"role": "human", "text": "cresceu"}],
                lambda _prompt: json.dumps(grown_output), log=log, watermark=2,
            )
            folded = eventlog.atividades_at(log=log)
            self.assertEqual(len(folded), 1)
            current = next(iter(folded.values()))
            self.assertTrue(any(touch["tier"] == "asserted" for touch in current["toques"]))
            self.assertEqual([event["type"] for event in first["emitted"]],
                             ["sessao.racionalizada", "atividade.opened", "atividade.touched"])
            self.assertEqual([event["type"] for event in second["emitted"]],
                             ["sessao.racionalizada", "atividade.touched"])
            latest_id = second["emitted"][0]["payload"]["rationalization_id"]
            current_contributions = [touch for touch in current["toques"]
                                     if touch.get("rationalization_id") == latest_id]
            self.assertEqual(len(current_contributions), 1)
            self.assertEqual(second["emitted"][0]["payload"]["supersedes"],
                             first["emitted"][0]["payload"]["rationalization_id"])

    def test_a30_middle_objective_change_materializes_the_middle_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            turns = [{"role": "human", "text": f"turn-{index}"} for index in range(20)]
            turns[10]["text"] = "MIDDLE_OBJECTIVE_CHANGE"

            def complete_fn(prompt):
                request = json.loads(prompt)
                if request["stage"] == "scene":
                    return json.dumps({
                        "summary": " | ".join(turn["text"] for turn in request["turns"])
                    })
                output = _nothing_changed()
                output["stitch"]["attribution"].update({
                    "human_purpose": "MIDDLE_OBJECTIVE_CHANGE",
                    "shared_outcome": "objetivo mudou no meio",
                })
                output["derived_events"] = [{
                    "type": "atividade.opened", "subject": "atividade:middle",
                    "payload": {"operacao": "edge",
                                "finalidade": "MIDDLE_OBJECTIVE_CHANGE",
                                "novo": "objetivo mudou no meio"},
                }]
                return json.dumps(output)

            result = racionalizador.rationalize(
                "session-middle", turns, complete_fn, log=log,
                scene_turn_limit=2, max_scenes=3, sweep_token_budget=10_000,
            )
            self.assertIn("atividade.opened", [event["type"] for event in result["emitted"]])
            activities = eventlog.atividades_at(log=log)
            self.assertEqual(len(activities), 1)
            self.assertEqual(next(iter(activities.values()))["finalidade"],
                             "MIDDLE_OBJECTIVE_CHANGE")

    def test_fence_wrapped_json_accepted_for_scene_and_session_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            turns = [{"role": "human", "text": f"turn-{index}"} for index in range(4)]

            def complete_fn(prompt):
                request = json.loads(prompt)
                if request["stage"] == "scene":
                    body = json.dumps({"summary": "cena fenceada"})
                    return f"```json\n{body}\n```"
                body = json.dumps(_nothing_changed())
                return f"Here is the result:\n```json\n{body}\n```\n"

            result = racionalizador.rationalize(
                "session-fence",
                turns,
                complete_fn,
                log=log,
                scene_turn_limit=2,
                max_scenes=3,
                sweep_token_budget=10_000,
            )
            self.assertNotIn("skipped_reason", result)
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                ["sessao.racionalizada", "atividade.opened", "atividade.touched"],
            )

    def test_scene_prose_fallback_uses_raw_text_as_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            turns = [{"role": "human", "text": f"turn-{index}"} for index in range(4)]

            def complete_fn(prompt):
                request = json.loads(prompt)
                if request["stage"] == "scene":
                    self.assertIn("instruction", request)
                    return "**Continua.** A cena segue a atividade de deploy."
                return json.dumps(_nothing_changed())

            result = racionalizador.rationalize(
                "session-prose-scene",
                turns,
                complete_fn,
                log=log,
                scene_turn_limit=2,
                max_scenes=3,
                sweep_token_budget=10_000,
            )
            self.assertNotIn("skipped_reason", result)
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                ["sessao.racionalizada", "atividade.opened", "atividade.touched"],
            )

    def test_empty_derived_with_goal_floors_atividade_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            self.assertEqual(output["derived_events"], [])
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(len(validated["derived_events"]), 1)
            floor = validated["derived_events"][0]
            self.assertEqual(floor["type"], "atividade.opened")
            self.assertEqual(floor["subject"], "atividade:auto")
            self.assertEqual(floor["payload"]["operacao"], "edge")
            self.assertEqual(floor["payload"]["finalidade"], output["stitch"]["goal"])
            self.assertEqual(floor["payload"]["novo"], output["stitch"]["acao"])

            result = racionalizador.rationalize(
                "session-floor",
                [{"role": "human", "text": "trabalho real"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            types = [event["type"] for event in result["emitted"]]
            self.assertEqual(
                types, ["sessao.racionalizada", "atividade.opened", "atividade.touched"]
            )
            open_payload = next(
                event["payload"] for event in result["emitted"]
                if event["type"] == "atividade.opened"
            )
            self.assertEqual(open_payload["finalidade"], "implementar as lentes")
            self.assertEqual(open_payload["origem_sessao"], "session-floor")
            self.assertEqual(len(eventlog.atividades_at(log=log)), 1)

    def test_meta_noise_empty_derived_does_not_floor_atividade_opened(self):
        """G1: sem relevância de atividade, a atribuição não inventa emprego."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["goal"] = "status check do portfolio"
            output["stitch"]["acao"] = "Revisei; nada muda no que fazemos."
            output["stitch"]["attribution"].update({
                "human_purpose": "status check do portfolio",
                "edge_execution": "Revisei; nada muda no que fazemos.",
                "shared_outcome": "nada mudou no que fazemos",
                "activity_relevant": False,
            })
            output["derived_events"] = []
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(validated["derived_events"], [])

            result = racionalizador.rationalize(
                "session-meta-noise",
                [
                    {"role": "human", "text": "A spec está pronta."},
                    {"role": "edge", "text": "Revisei; nada muda no que fazemos."},
                ],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            types = [event["type"] for event in result["emitted"]]
            self.assertEqual(types, ["sessao.racionalizada"])
            self.assertEqual(eventlog.read(types=["atividade.opened"], log=log), [])
            self.assertEqual(eventlog.atividades_at(log=log), {})

    def test_agent_meta_work_does_not_floor_or_backfill_atividade(self):
        """Execução delegada pode ser semanticamente irrelevante ao emprego do humano."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["goal"] = (
                "Run a Codex adversarial review via the plugin runtime on request"
            )
            output["stitch"]["acao"] = (
                "Declined to launch the review after confirming the working directory "
                "is not a git repository"
            )
            output["stitch"]["attribution"].update({
                "human_purpose": output["stitch"]["goal"],
                "edge_execution": output["stitch"]["acao"],
                "shared_outcome": "a revisão não foi iniciada",
                "activity_relevant": False,
            })
            output["derived_events"] = []
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(validated["derived_events"], [])

            result = racionalizador.rationalize(
                "session-agent-meta",
                [
                    {"role": "human", "text": "roda o codex adversarial"},
                    {"role": "edge", "text": "não é repo git, recusei."},
                ],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                ["sessao.racionalizada"],
            )
            self.assertEqual(
                racionalizador.backfill_atividades_from_rationalizations(log=log),
                [],
            )
            self.assertEqual(eventlog.atividades_at(log=log), {})

    def test_generic_agent_task_does_not_floor_atividade(self):
        """Atribuição sem relevância fecha, independentemente do vocabulário da tarefa."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["goal"] = "Review the pull request"
            output["stitch"]["acao"] = "Summarized findings"
            output["stitch"]["attribution"].update({
                "human_purpose": output["stitch"]["goal"],
                "edge_execution": output["stitch"]["acao"],
                "shared_outcome": output["stitch"]["acao"],
                "activity_relevant": False,
            })
            output["derived_events"] = []
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(validated["derived_events"], [])

            result = racionalizador.rationalize(
                "session-agent-task",
                [
                    {"role": "human", "text": "review the PR and report back"},
                    {"role": "edge", "text": "Summarized findings."},
                ],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                ["sessao.racionalizada"],
            )
            self.assertEqual(eventlog.atividades_at(log=log), {})

    def test_unknown_prose_without_positive_evidence_does_not_floor(self):
        """O juízo semântico de irrelevância não depende de palavra positiva."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["goal"] = "Arrange the Tuesday calendar"
            output["stitch"]["acao"] = "Moved three blocks around"
            output["stitch"]["attribution"].update({
                "human_purpose": output["stitch"]["goal"],
                "edge_execution": output["stitch"]["acao"],
                "shared_outcome": output["stitch"]["acao"],
                "activity_relevant": False,
            })
            output["derived_events"] = []
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(validated["derived_events"], [])
            result = racionalizador.rationalize(
                "session-unknown-prose",
                [{"role": "human", "text": "fix my calendar"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            self.assertEqual(
                [event["type"] for event in result["emitted"]],
                ["sessao.racionalizada"],
            )
            self.assertEqual(eventlog.atividades_at(log=log), {})

    def test_edge_execution_open_is_reframed_by_human_purpose(self):
        """A finalidade humana enquadra a execução emitida pelo completer."""
        output = _nothing_changed()
        output["stitch"]["goal"] = "ship the mentee product feature"
        output["stitch"]["acao"] = "opened a PR for the feature"
        output["stitch"]["attribution"].update({
            "human_purpose": "ship the mentee product feature",
            "edge_execution": "Wire predispatch and edge-apply on the host",
            "shared_outcome": "opened a PR for the feature",
        })
        output["derived_events"] = [{
            "type": "atividade.opened",
            "subject": "atividade:agent",
            "payload": {
                "operacao": "edge",
                "finalidade": "Wire predispatch and edge-apply on the host",
                "novo": "touched systemd unit",
            },
        }]
        validated = racionalizador._validated_output(json.dumps(output))
        # The execution is retained as evidence, while its activity is framed by
        # the purpose cited from the human side of the dialogue.
        opens = [item for item in validated["derived_events"]
                 if item["type"] == "atividade.opened"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]["payload"]["finalidade"], "ship the mentee product feature")

    def test_claim_only_derived_with_real_goal_floors_atividade_opened(self):
        """G1: claim-only derived undercounts — still floor one open for real work."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["derived_events"] = [{
                "type": "claim.hypothesized",
                "subject": "claim:c",
                "payload": {"statement": "hipótese de trabalho real"},
            }]
            validated = racionalizador._validated_output(json.dumps(output))
            types = [item["type"] for item in validated["derived_events"]]
            self.assertIn("claim.hypothesized", types)
            self.assertIn("atividade.opened", types)
            floor = next(item for item in validated["derived_events"]
                         if item["type"] == "atividade.opened")
            self.assertEqual(floor["payload"]["finalidade"], output["stitch"]["goal"])
            self.assertEqual(floor["payload"]["novo"], output["stitch"]["acao"])

            result = racionalizador.rationalize(
                "session-claim-floor",
                [{"role": "human", "text": "extraímos uma hipótese e trabalhamos"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            emitted_types = [event["type"] for event in result["emitted"]]
            self.assertEqual(
                emitted_types,
                [
                    "sessao.racionalizada",
                    "claim.hypothesized",
                    "atividade.opened",
                    "atividade.touched",
                ],
            )

    def test_floor_does_not_duplicate_if_derived_already_has_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["attribution"].update({
                "human_purpose": "Finalidade explícita do completer",
                "shared_outcome": "toque explícito",
            })
            output["derived_events"] = [{
                "type": "atividade.opened",
                "subject": "atividade:explicit",
                "payload": {
                    "operacao": "edge",
                    "finalidade": "Finalidade explícita do completer",
                    "novo": "toque explícito",
                },
            }]
            validated = racionalizador._validated_output(json.dumps(output))
            self.assertEqual(len(validated["derived_events"]), 1)
            self.assertEqual(
                validated["derived_events"][0]["payload"]["finalidade"],
                "Finalidade explícita do completer",
            )

            result = racionalizador.rationalize(
                "session-no-dup-floor",
                [{"role": "human", "text": "já tem open"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            opens = [event for event in result["emitted"]
                     if event["type"] == "atividade.opened"]
            self.assertEqual(len(opens), 1)
            self.assertEqual(
                opens[0]["payload"]["finalidade"], "Finalidade explícita do completer"
            )

    def test_backfill_atividades_from_rationalizations_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # Checkpoint without derived siblings (pre-floor film).
            eventlog.append(
                "sessao.racionalizada",
                "sessao:old-1",
                {
                    "sessao_id": "old-1",
                    "surface": "claude",
                    "watermark": 1,
                    "operacoes": ["edge"],
                    "source_hash": "a" * 64,
                    "rationalization_id": "b" * 64,
                    "racionalizador_version": "v1",
                    "stitch": {
                        "goal": "Backfill lentes portfolio employment",
                        "acao": "Backfill acao da feature",
                        "entidades": [],
                        "attribution": {
                            "human_purpose": "Backfill lentes portfolio employment",
                            "human_turn_indexes": [0],
                            "edge_execution": "Backfill acao da feature",
                            "shared_outcome": "Backfill acao da feature",
                            "activity_relevant": True,
                        },
                    },
                    "epistemico": {"presuncoes": []},
                    "organizacional": {"enderecos": []},
                },
                log=log,
            )
            first = racionalizador.backfill_atividades_from_rationalizations(log=log)
            self.assertEqual(
                [event["type"] for event in first],
                ["atividade.opened", "atividade.touched"],
            )
            self.assertEqual(
                first[0]["payload"]["finalidade"],
                "Backfill lentes portfolio employment",
            )
            self.assertEqual(first[0]["payload"]["origem_sessao"], "old-1")
            self.assertEqual(first[0]["payload"]["author"], "racionalizador")
            self.assertEqual(first[0]["payload"]["tier"], "llm_judged")
            self.assertEqual(first[1]["payload"]["novo"], "Backfill acao da feature")
            second = racionalizador.backfill_atividades_from_rationalizations(log=log)
            self.assertEqual(second, [])
            self.assertEqual(len(eventlog.read(types=["atividade.opened"], log=log)), 1)
            self.assertEqual(len(eventlog.atividades_at(log=log)), 1)

    def test_backfill_repairs_open_without_touch_and_is_idempotent(self):
        """G3: crash window left open sans touch — rerun appends touch only."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada",
                "sessao:orphan-open",
                {
                    "sessao_id": "orphan-open",
                    "surface": "claude",
                    "watermark": 1,
                    "operacoes": ["edge"],
                    "source_hash": "c" * 64,
                    "rationalization_id": "d" * 64,
                    "racionalizador_version": "v1",
                    "stitch": {
                        "goal": "Repair incomplete lentes backfill",
                        "acao": "open landed; touch did not",
                        "entidades": [],
                        "attribution": {
                            "human_purpose": "Repair incomplete lentes backfill",
                            "human_turn_indexes": [0],
                            "edge_execution": "open landed; touch did not",
                            "shared_outcome": "open landed; touch did not",
                            "activity_relevant": True,
                        },
                    },
                    "epistemico": {"presuncoes": []},
                    "organizacional": {"enderecos": []},
                },
                log=log,
            )
            opened = eventlog.open_atividade(
                operacao="edge",
                finalidade="Repair incomplete lentes backfill",
                tier="llm_judged",
                author="racionalizador",
                origem_sessao="orphan-open",
                derivation_key="d" * 64 + ":backfill:0",
                log=log,
            )
            self.assertEqual(eventlog.read(types=["atividade.touched"], log=log), [])

            first = racionalizador.backfill_atividades_from_rationalizations(log=log)
            self.assertEqual([event["type"] for event in first], ["atividade.touched"])
            self.assertEqual(first[0]["payload"]["ref"], opened["payload"]["ulid"])
            self.assertEqual(first[0]["payload"]["sessao"], "orphan-open")
            self.assertEqual(first[0]["payload"]["novo"], "open landed; touch did not")
            self.assertEqual(len(eventlog.read(types=["atividade.opened"], log=log)), 1)
            self.assertEqual(len(eventlog.read(types=["atividade.touched"], log=log)), 1)

            second = racionalizador.backfill_atividades_from_rationalizations(log=log)
            self.assertEqual(second, [])
            self.assertEqual(len(eventlog.read(types=["atividade.opened"], log=log)), 1)
            self.assertEqual(len(eventlog.read(types=["atividade.touched"], log=log)), 1)

    def test_loads_json_loose_extracts_balanced_object(self):
        payload = {"summary": "ok"}
        raw = "preamble\n" + json.dumps(payload) + "\ntrailing noise"
        self.assertEqual(racionalizador._loads_json_loose(raw), payload)
        self.assertEqual(racionalizador._loads_json_loose(payload), payload)
        with self.assertRaises(ValueError):
            racionalizador._loads_json_loose("not json at all")

    def test_malformed_stitch_entidades_are_dropped_not_invalid_output(self):
        """Completer free-text entidades must not kill the whole film (7d drain)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            output = _nothing_changed()
            output["stitch"]["entidades"] = [
                "not-a-ref",
                {"operacao": "edge", "num": "atv-001"},
            ]
            validated = racionalizador._validated_output(json.dumps(output))
            # free-text dropped; valid dict ref kept if operacao in operacoes
            self.assertEqual(
                validated["stitch"]["entidades"],
                [{"operacao": "edge", "num": "atv-001"}],
            )
            result = racionalizador.rationalize(
                "session-bad-ent",
                [{"role": "human", "text": "implementar as lentes no mapa"}],
                lambda _prompt: json.dumps(output),
                log=log,
            )
            self.assertNotIn("skipped_reason", result)
            self.assertEqual(result["emitted"][0]["type"], "sessao.racionalizada")

    @unittest.skip("owned by sweep wiring: max_sessions, oldest-first, aggregate token budget")
    def test_a30_sweep_coordinator_bounds_and_resumes_multiple_sessions_oldest_first(self):
        self.fail("rationalize exposes per-session cost; sweep must coordinate the aggregate")


if __name__ == "__main__":
    unittest.main()
