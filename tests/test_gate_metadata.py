"""Ticket B — gates persistem metadado + curadoria de sources + o ATO artefato→source.

B.1: o verdict do gate deixa de ser descartado — `run_close` carimba a rubrica versionada
(`revisor@1` = sha256 do contrato do revisor, ADR-0025) no proof;
`publisher.publish` projeta o proof em `gate=` (payload flat, llm_judged/lead — CX-1: NUNCA
entra num rollup computed) e o persiste no MESMO batch atômico do `artefato.published`.

B.2: o gate persistido vira o reward que faltava — `fold_grounding_yield` JOINa o resultado
do gate por `dispatch_id` numa COLUNA própria (gate_n/gate_pass_rate), nunca dentro do
`score` de cosine (o gate é llm_judged; o score é computed).

B.3: o ATO artefato→source — `eventlog.integrate_artefato_source` (HITL: reviewer nomeado,
nunca automático) + o fold `integrated_sources_at`; `publisher.promote_artefato_to_source`
grava o evento (o log é a verdade) e marca o nó best-effort.

B.4 (veto de passabilidade) foi removido pelo ADR-0025: o revisor único só aponta furos,
nunca veta. O gate persistido agora é o contrato do revisor + os furos.
"""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import eventlog  # noqa: E402
import grounding_yield  # noqa: E402
import publisher  # noqa: E402


_ART = {
    "slug": "rubric-stamp",
    "content": {"sections": [{"title": "Body", "blocks": [
        {"type": "paragraph", "text": "bound content."}]}]},
    "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True, "snippet": "s"}],
    "proposes": [{"body": "b", "kind": "constraint"}],
    "intent": "open: x; bet: y",
}


class GateRubricIsVersionedAndStamped(unittest.TestCase):
    """B.1 — o contrato do revisor é versionado por CONTEÚDO (GLO-13): editar o contrato = sha
    novo; verdicts velhos ficam pinados ao seu. O proof que run_close minta carrega ambos."""

    def test_version_label_and_sha_shape(self):
        self.assertEqual(close.REVIEW_CONTRACT_VERSION, "revisor@1")
        self.assertRegex(close.REVIEW_CONTRACT_SHA, r"^[0-9a-f]{64}$")

    def test_sha_is_the_sha_of_the_reviewer_contract(self):
        import revisor
        self.assertEqual(close.REVIEW_CONTRACT_SHA,
                         hashlib.sha256(revisor.REVIEWER_CONTRACT.encode("utf-8")).hexdigest())

    def test_minted_proof_carries_rubric_version_and_sha(self):
        proof = close.run_close(dict(_ART), lambda: _ART,
                                complete_fn=lambda *a, **k: '{"furos": []}')
        self.assertTrue(proof["pass"])
        self.assertEqual(proof["gate_rubric"], close.REVIEW_CONTRACT_VERSION)
        self.assertEqual(proof["gate_rubric_sha"], close.REVIEW_CONTRACT_SHA)

    def test_furos_never_veto_at_the_close_seam(self):
        # ADR-0025: o que antes era veto (clareza baixa, strike) agora é furo — publica.
        published = []
        proof = close.run_close(
            dict(_ART), lambda: _ART,
            complete_fn=lambda *a, **k: '{"furos": ["referente sem nome"]}',
            publish_fn=lambda a, p: published.append(a))
        self.assertTrue(proof["pass"])
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["content"]["reviewer_notes"], ["referente sem nome"])


class GatePersistsOnThePublishedEvent(unittest.TestCase):
    """B.1 — o publisher deixa de descartar o verdict: `_gate_payload` projeta o proof num
    payload flat (llm_judged/lead/inferred_default — CX-1: nunca agrega num rollup computed) e
    `publish_artefato_atomic` o persiste no MESMO batch do `artefato.published` (replayável,
    sem novo tipo de evento). Forward-only: evento legado sem `gate` folda tolerante."""

    def _proof(self, furos=()):
        return {
            "pass": True, "digest": "x", "token": object(),
            "gate_rubric": close.REVIEW_CONTRACT_VERSION,
            "gate_rubric_sha": close.REVIEW_CONTRACT_SHA,
            "verdicts": [{"reviewer": close.REVIEWER_ID, "furos": list(furos)}],
            "reviewer_notes": list(furos),
        }

    def test_gate_payload_shape(self):
        gate = publisher._gate_payload(self._proof())
        self.assertEqual(gate["rubric"], close.REVIEW_CONTRACT_VERSION)
        self.assertEqual(gate["rubric_sha"], close.REVIEW_CONTRACT_SHA)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["strikes_n"], 0)
        self.assertEqual(gate["furos"], [])
        # provenance (CX-1): verdict de revisão é llm_judged, rigor teto lead.
        self.assertEqual(gate["provenance_class"], "llm_judged")
        self.assertEqual(gate["rigor"], "lead")
        self.assertEqual(gate["validity"], "inferred_default")

    def test_gate_payload_rubric_is_the_modules_not_the_proofs(self):
        # codex adversarial #2: a rubrica não é digest-bound — um proof mutado não pode
        # carimbar rubrica falsa no evento. O payload usa a régua do MÓDULO no publish
        # (mint e publish rodam no mesmo load; o campo do proof é auditoria, não fonte).
        tampered = self._proof()
        tampered["gate_rubric"] = "gate_rubric@99"
        tampered["gate_rubric_sha"] = "f" * 64
        gate = publisher._gate_payload(tampered)
        self.assertEqual(gate["rubric"], close.REVIEW_CONTRACT_VERSION)
        self.assertEqual(gate["rubric_sha"], close.REVIEW_CONTRACT_SHA)

    def test_gate_payload_never_enters_a_computed_rollup(self):
        # CX-1 (o verificar grita): um verdict-de-gate é llm_judged — reivindicar cravado/
        # computed num rollup levanta LOUD, nunca agrega.
        import cortex_provenance
        gate = publisher._gate_payload(self._proof())
        with self.assertRaises(ValueError):
            cortex_provenance.assert_rollup_computed([gate])

    def test_gate_payload_with_furos_is_not_clean(self):
        # `pass` aqui = "nenhum furo" (sinal pro yield), nunca o bilhete de publicação.
        gate = publisher._gate_payload(self._proof(furos=["referente sem nome"]))
        self.assertFalse(gate["pass"])
        self.assertEqual(gate["strikes_n"], 1)
        self.assertEqual(gate["notes_n"], 1)

    def test_gate_payload_degrades_to_none_never_raises(self):
        self.assertIsNone(publisher._gate_payload(None))
        self.assertIsNone(publisher._gate_payload({"verdicts": "x"}))
        self.assertIsNone(publisher._gate_payload({"verdicts": []}))

    def test_atomic_publish_persists_gate_on_the_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            gate = {"rubric": "gate_rubric@1", "pass": True, "strikes_n": 0}
            eventlog.publish_artefato_atomic(
                "g-slug", "intent", log=log,
                dispatch_id=eventlog.test_dispatch_id(), gate=gate)
            evs = eventlog.read(types=["artefato.published"], log=log)
            self.assertEqual(evs[0]["payload"]["gate"], gate)

    def test_atomic_publish_without_gate_records_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic(
                "g2-slug", "intent", log=log, dispatch_id=eventlog.test_dispatch_id())
            evs = eventlog.read(types=["artefato.published"], log=log)
            self.assertIsNone(evs[0]["payload"].get("gate"))

    def test_gate_props_are_flat_and_sanitized(self):
        # a projeção no nó (:Artefato) — flat props (badge de verdict, MIR-2/3), Cypher-navegável.
        gate = publisher._gate_payload(self._proof())
        props = publisher._gate_props(gate)
        self.assertEqual(props["gate_rubric"], close.REVIEW_CONTRACT_VERSION)
        self.assertTrue(props["gate_pass"])
        self.assertEqual(props["gate_strikes_n"], 0)
        self.assertEqual(props["gate_provenance_class"], "llm_judged")
        self.assertEqual(props["gate_rigor"], "lead")
        self.assertEqual(props["gate_validity"], "inferred_default")
        self.assertEqual(json.loads(props["gate_furos"]), [])
        self.assertEqual(publisher._gate_props(None), {})

    def test_corpus_fold_carries_gate_for_reproject(self):
        # reproject (forward-only): o item do corpus carrega o gate do payload — um replay
        # restaura as flat props; evento legado sem gate folda None, nunca quebra.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            gate = {"rubric": "gate_rubric@1", "pass": True, "strikes_n": 0}
            eventlog.publish_artefato_atomic(
                "g3-slug", "intent", log=log,
                dispatch_id=eventlog.test_dispatch_id(), gate=gate)
            items = eventlog.fold_corpus(eventlog.read(log=log))
            self.assertEqual(items[0]["gate"], gate)


HSMAP = {"api.exa.ai": "exa", "api.twitter.com": "x"}


def _open(log, did, intent="research"):
    eventlog.append("dispatch.open", "dispatch",
                    {"dispatch_id": did, "intent": intent, "geometry": "themed"}, log=log)


def _mani(log, source, interface, did, seq_tag):
    eventlog.append("grounding.manifest", "grounding",
                    {"raw_ref": [seq_tag, 1, "t", 0], "source": source, "interface": interface,
                     "lens": "mundo", "geometry": "gather", "attribution": "mapped",
                     "hits": 3, "dispatch_id": did, "intent": None, "recognizer_rev": 1},
                    log=log)


def _pub(log, slug, did, gate):
    eventlog.append("artefato.published", f"artefato:{slug}",
                    {"slug": slug, "dispatch_id": did, "skill": "research", "gate": gate},
                    log=log)


class YieldJoinsTheGateByDispatchId(unittest.TestCase):
    """B.2 — a curadoria de sources aprende do RESULTADO do gate, não só de cosine: o gate
    persistido no `artefato.published` JOINa por dispatch_id nas scoring-cells do dispatch.
    Coluna PRÓPRIA (gate_n/gate_pass_rate) — o gate é llm_judged e NUNCA entra no `score`
    de cosine (computed; CX-1). Legado sem gate: colunas ficam vazias, fold nunca quebra."""

    def _fold(self, log):
        return grounding_yield.grounding_yield_at(log=log, hsmap=HSMAP)

    def test_gate_result_credits_the_dispatchs_scoring_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1")
            _mani(log, "exa", "search-deep", "d1", "s1")
            _pub(log, "artA", "d1", {"rubric": "gate_rubric@1", "pass": True, "strikes_n": 0})
            _open(log, "d2")
            _mani(log, "exa", "search-deep", "d2", "s2")
            _pub(log, "artB", "d2", {"rubric": "gate_rubric@1", "pass": False, "strikes_n": 2})
            y = self._fold(log)
            cell = y["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(cell["gate_n"], 2)
            self.assertEqual(cell["gate_pass_n"], 1)
            self.assertEqual(cell["gate_pass_rate"], 0.5)

    def test_gate_never_leaks_into_the_cosine_score(self):
        # CX-1: o score (computed, cosine) é idêntico com ou sem gate no evento.
        def _score(gate):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                _open(log, "d1")
                for i in range(6):   # acima de min_attempts pra cristalizar um score
                    _mani(log, "exa", "search-deep", "d1", f"s{i}")
                _pub(log, "artA", "d1", gate)
                y = self._fold(log)
                return y["cells"][("research", "exa", "search-deep", "mundo", "gather")]["score"]
        self.assertEqual(_score(None),
                         _score({"rubric": "gate_rubric@1", "pass": True, "strikes_n": 0}))

    def test_legacy_publish_without_gate_folds_tolerantly(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1")
            _mani(log, "exa", "search-deep", "d1", "s1")
            _pub(log, "artA", "d1", None)
            y = self._fold(log)
            cell = y["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(cell["gate_n"], 0)
            self.assertIsNone(cell["gate_pass_rate"])

    def test_marginals_aggregate_the_gate_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1")
            _mani(log, "exa", "search-deep", "d1", "s1")
            _mani(log, "x", "v2-recent", "d1", "s2")
            _pub(log, "artA", "d1", {"rubric": "gate_rubric@1", "pass": True, "strikes_n": 0})
            y = self._fold(log)
            self.assertEqual(y["marginals"]["exa"]["gate_n"], 1)
            self.assertEqual(y["marginals"]["exa"]["gate_pass_rate"], 1.0)
            self.assertEqual(y["marginals"]["x"]["gate_n"], 1)


class ArtefatoBecomesSourceByHitlAct(unittest.TestCase):
    """B.3 — o ATO: um artefato INTEGRADO vira source (o edge se aterra na própria obra).
    Writes são ACTS: o evento `artefato.integrated` é HITL/autoridade (review_approved,
    authority=reviewer, reviewer≠asserter) — nunca o edge se auto-promovendo em silêncio.
    Zero tipo novo: o fold só marca o slug como integrado; o pool lê dali."""

    def _published(self, tmp, slug="obra"):
        log = Path(tmp) / "log.jsonl"
        eventlog.publish_artefato_atomic(slug, "intent", log=log,
                                         dispatch_id=eventlog.test_dispatch_id())
        return log

    def test_integration_appends_the_hitl_act(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._published(tmp)
            ev = eventlog.integrate_artefato_source("obra", "operador", log=log)
            self.assertEqual(ev["type"], "artefato.integrated")
            p = ev["payload"]
            self.assertEqual(p["slug"], "obra")
            self.assertIs(p["review_approved"], True)
            self.assertEqual(p["authority"], "reviewer")
            self.assertEqual(p["reviewer"], "operador")

    def test_integration_requires_a_named_reviewer(self):
        # HITL: nunca automático — sem autoridade nomeada, o ato não existe.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._published(tmp)
            with self.assertRaises(ValueError):
                eventlog.integrate_artefato_source("obra", "", log=log)
            with self.assertRaises(ValueError):
                eventlog.integrate_artefato_source("obra", None, log=log)

    def test_integration_refuses_an_unpublished_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._published(tmp)
            with self.assertRaises(ValueError):
                eventlog.integrate_artefato_source("nunca-publicado", "operador", log=log)

    def test_integrated_sources_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._published(tmp)
            self.assertEqual(eventlog.integrated_sources_at(log=log), {})
            eventlog.integrate_artefato_source("obra", "operador", log=log)
            pool = eventlog.integrated_sources_at(log=log)
            self.assertIn("obra", pool)
            self.assertEqual(pool["obra"]["reviewer"], "operador")

    def test_promote_writes_the_event_first_and_degrades_on_graph(self):
        # o log é a verdade: o evento landa mesmo com o grafo inalcançável (a marca no nó é
        # projeção best-effort, e um log não-canônico NUNCA escreve no grafo do install).
        with tempfile.TemporaryDirectory() as tmp:
            log = self._published(tmp)
            ev = publisher.promote_artefato_to_source("obra", "operador", log=log)
            self.assertEqual(ev["type"], "artefato.integrated")
            self.assertIn("obra", eventlog.integrated_sources_at(log=log))


class GroundingFloorDefaultIsObserve(unittest.TestCase):
    """B.4 — EDGE_GROUNDING_FLOOR sobe de 0=off para 1=observe (contar a violação, sem gatear):
    o primeiro degrau honesto — o instrumento liga, o veto continua opt-in (knob 2)."""

    def test_env_unset_defaults_to_observe(self):
        import os
        import harvest
        old = os.environ.pop("EDGE_GROUNDING_FLOOR", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                eventlog.append("dispatch.open", "dispatch",
                                {"session_id": "sD", "dispatch_id": "d1",
                                 "geometry": "themed"}, log=log)
                out = harvest.close_floor(log=log, store_root=Path(tmp) / "projects",
                                          session_id="sD", child_session="")
                # observe: NUNCA bloqueia…
                self.assertEqual(out, [])
                # …mas o instrumento está LIGADO: a leitura escura/violação é CONTADA no log
                counted = eventlog.read(types=["grounding.floor", "grounding.floor_dark"],
                                        log=log)
                self.assertTrue(counted, "default 1=observe: o floor deve contar, não silenciar")
        finally:
            if old is not None:
                os.environ["EDGE_GROUNDING_FLOOR"] = old


if __name__ == "__main__":
    unittest.main()
