"""Ticket B — gates persistem metadado + curadoria de sources + o ATO artefato→source.

B.1: o verdict do gate deixa de ser descartado — `run_close` carimba a rubrica versionada
(`gate_rubric@1` = sha256 do canonical-JSON de DIMENSIONS+WEIGHTS+focus prompts) no proof;
`publisher.publish` projeta o proof em `gate=` (payload flat, llm_judged/lead — CX-1: NUNCA
entra num rollup computed) e o persiste no MESMO batch atômico do `artefato.published`.

B.2: o gate persistido vira o reward que faltava — `fold_grounding_yield` JOINa o resultado
do gate por `dispatch_id` numa COLUNA própria (gate_n/gate_pass_rate), nunca dentro do
`score` de cosine (o gate é llm_judged; o score é computed).

B.3: o ATO artefato→source — `eventlog.integrate_artefato_source` (HITL: reviewer nomeado,
nunca automático) + o fold `integrated_sources_at`; `publisher.promote_artefato_to_source`
grava o evento (o log é a verdade) e marca o nó best-effort.

B.4: fim = substância+passabilidade em AND com veto LIMITADO — a nota de clareza/
contextualização abaixo do piso volta a VETAR como strike NOMEADO (endereçável, bounded
pelo BOUNCE_MAX existente; o loop termina POR FORA — nunca o loop infinito do #65).
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


def _verdict_json(scores, strikes=(), rationales=None):
    return json.dumps({"pass": True, "scores": scores, "strikes": list(strikes),
                       "rationales": rationales or {}, "overall": 4.0})


_GOOD_SCORES = {d: 4 for d in close.DIMENSIONS}


class GateRubricIsVersionedAndStamped(unittest.TestCase):
    """B.1 — a rubrica é versionada por CONTEÚDO (GLO-13): editar dims/weights/focus = sha novo
    = versão nova; verdicts velhos ficam pinados à sua. O proof que run_close minta carrega ambos."""

    def test_version_label_and_sha_shape(self):
        self.assertEqual(close.GATE_RUBRIC_VERSION, "gate_rubric@1")
        self.assertRegex(close.GATE_RUBRIC_SHA, r"^[0-9a-f]{64}$")

    def test_sha_is_the_canonical_json_of_dims_weights_and_focus(self):
        blob = json.dumps(
            {"dimensions": close.DIMENSIONS, "weights": close.DIMENSION_WEIGHTS,
             "feynman_focus": close._FEYNMAN_FOCUS, "regular_focus": close._REGULAR_FOCUS},
            sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.assertEqual(close.GATE_RUBRIC_SHA, hashlib.sha256(blob).hexdigest())

    def test_minted_proof_carries_rubric_version_and_sha(self):
        art = {
            "slug": "rubric-stamp",
            "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "bound content."}]}]},
            "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                       "snippet": "s"}],
            "proposes": [{"body": "b", "kind": "constraint"}],
            "intent": "open: x; bet: y",
        }
        proof = close.run_close(
            art, lambda: art,
            complete_fn=lambda *a, **k: _verdict_json(_GOOD_SCORES))
        self.assertTrue(proof["pass"])
        self.assertEqual(proof["gate_rubric"], close.GATE_RUBRIC_VERSION)
        self.assertEqual(proof["gate_rubric_sha"], close.GATE_RUBRIC_SHA)


class PassabilityVetoIsBoundedAndNamed(unittest.TestCase):
    """B.4 — clareza/passabilidade volta a VETAR (a sobre-correção do #65 fez a nota virar
    conselho → shipou 'referente sem nome'), mas LIMITADO: só uma nota PRESENTE e numérica
    abaixo do piso veta, como strike NOMEADO (endereçável pelo improve loop) — o bound é o
    BOUNCE_MAX de sempre, o loop termina por fora."""

    def test_low_didactic_clarity_vetoes_with_a_named_strike(self):
        raw = _verdict_json({**_GOOD_SCORES, "didactic_clarity": 2},
                            rationales={"didactic_clarity": "referente sem nome"})
        v = close._parse_verdict(raw)
        self.assertFalse(v["pass"])
        veto = [s for s in v["strikes"] if s.startswith("passabilidade-veto: didactic_clarity")]
        self.assertEqual(len(veto), 1, v["strikes"])
        # endereçável: o strike carrega o rationale do reviewer (o QUE consertar)
        self.assertIn("referente sem nome", veto[0])

    def test_low_contextualization_vetoes(self):
        v = close._parse_verdict(_verdict_json({**_GOOD_SCORES, "contextualization": 1}))
        self.assertFalse(v["pass"])
        self.assertTrue(any(s.startswith("passabilidade-veto: contextualization")
                            for s in v["strikes"]))

    def test_score_at_the_floor_does_not_veto(self):
        v = close._parse_verdict(_verdict_json({**_GOOD_SCORES, "didactic_clarity": 3,
                                                "contextualization": 3}))
        self.assertTrue(v["pass"])
        self.assertEqual(v["strikes"], [])

    def test_nan_or_infinite_score_fails_closed_never_bypasses_the_veto(self):
        # codex adversarial #1: json.loads aceita NaN/Infinity; NaN < 3 é False — sem o
        # guard, uma nota NaN passaria pelo veto E contaminaria o overall. Não-finito =
        # malformado → strike, fail-closed.
        raw = ('{"pass": true, "scores": {' +
               ", ".join(f'"{d}": 4' for d in close.DIMENSIONS if d != "didactic_clarity") +
               ', "didactic_clarity": NaN}, "strikes": []}')
        v = close._parse_verdict(raw)
        self.assertFalse(v["pass"])
        self.assertTrue(any("malformed score" in s for s in v["strikes"]), v["strikes"])
        self.assertEqual(v["overall"], v["overall"], "overall nunca é NaN")

    def test_missing_passability_dims_never_veto(self):
        # o guard anti-#65: um reviewer que OMITE a dim nunca veta por omissão —
        # senão o gate voltaria inganhável (score ausente ≠ nota baixa).
        v = close._parse_verdict('{"pass": true, "scores": {}, "strikes": []}')
        self.assertTrue(v["pass"])
        self.assertEqual(v["strikes"], [])

    def test_veto_is_bounded_at_the_close_seam(self):
        # o loop termina POR FORA: um reviewer que SEMPRE dá clareza 2 bounca até o
        # BOUNCE_MAX e HARD-FAILS com o strike nomeado — nunca o loop infinito do #65.
        art = {
            "slug": "veto-bounded",
            "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "conteúdo."}]}]},
            "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                       "snippet": "s"}],
            "proposes": [{"body": "b", "kind": "constraint"}],
            "intent": "open: x; bet: y",
        }
        calls = {"n": 0}

        def produce_fn():
            calls["n"] += 1
            return dict(art, slug=f"veto-bounded-{calls['n']}")

        published = []
        out = close.run_close(
            art, produce_fn,
            complete_fn=lambda *a, **k: _verdict_json({**_GOOD_SCORES,
                                                       "didactic_clarity": 2}),
            publish_fn=lambda a, p: published.append(a))
        self.assertFalse(out["pass"])
        self.assertEqual(published, [])
        self.assertLessEqual(calls["n"], close.BOUNCE_MAX)
        self.assertTrue(any(s.startswith("passabilidade-veto:")
                            for v in out["verdicts"] for s in v["strikes"]))

    def test_veto_dims_and_floor_are_pinned(self):
        self.assertEqual(set(close.PASSABILITY_VETO_DIMS),
                         {"didactic_clarity", "contextualization"})
        self.assertEqual(close.PASSABILITY_VETO_FLOOR, 3)


class GatePersistsOnThePublishedEvent(unittest.TestCase):
    """B.1 — o publisher deixa de descartar o verdict: `_gate_payload` projeta o proof num
    payload flat (llm_judged/lead/inferred_default — CX-1: nunca agrega num rollup computed) e
    `publish_artefato_atomic` o persiste no MESMO batch do `artefato.published` (replayável,
    sem novo tipo de evento). Forward-only: evento legado sem `gate` folda tolerante."""

    def _proof(self, strikes=()):
        return {
            "pass": True, "digest": "x", "token": object(),
            "gate_rubric": close.GATE_RUBRIC_VERSION,
            "gate_rubric_sha": close.GATE_RUBRIC_SHA,
            "verdicts": [
                {"reviewer": close.FEYNMAN_REVIEWER_ID, "pass": True,
                 "scores": {"content_depth": 4, "feynman_method": 5, "bad": "high"},
                 "rationales": {"content_depth": "dados reais"},
                 "strikes": list(strikes), "overall": 4.2},
                {"reviewer": close.REGULAR_REVIEWER_ID, "pass": True,
                 "scores": {"didactic_clarity": 3},
                 "rationales": {"didactic_clarity": "termos definidos"},
                 "strikes": [], "overall": 3.9},
            ],
        }

    def test_gate_payload_shape(self):
        gate = publisher._gate_payload(self._proof())
        self.assertEqual(gate["rubric"], close.GATE_RUBRIC_VERSION)
        self.assertEqual(gate["rubric_sha"], close.GATE_RUBRIC_SHA)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["strikes_n"], 0)
        # scores por reviewer, só numéricos (props flat no nó — um score corrompido não vira prop)
        self.assertEqual(gate["feynman"]["scores"],
                         {"content_depth": 4, "feynman_method": 5})
        self.assertEqual(gate["regular"]["scores"], {"didactic_clarity": 3})
        self.assertEqual(gate["feynman"]["rationales"], {"content_depth": "dados reais"})
        # provenance (CX-1): verdict de gate é llm_judged, rigor teto lead — o verificar grita
        # se um verdict-de-gate reivindicar cravado.
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
        self.assertEqual(gate["rubric"], close.GATE_RUBRIC_VERSION)
        self.assertEqual(gate["rubric_sha"], close.GATE_RUBRIC_SHA)

    def test_gate_payload_scores_are_allowlisted_to_the_rubric_dims(self):
        # codex adversarial #3: um reviewer não pode cunhar prop arbitrária no nó — só
        # dims da rubrica viram gate_<rev>_<dim>.
        proof = self._proof()
        proof["verdicts"][0]["scores"]["invented_dim"] = 5
        gate = publisher._gate_payload(proof)
        self.assertNotIn("invented_dim", gate["feynman"]["scores"])
        props = publisher._gate_props(gate)
        self.assertNotIn("gate_feynman_invented_dim", props)

    def test_gate_payload_never_enters_a_computed_rollup(self):
        # CX-1 (o verificar grita): um verdict-de-gate é llm_judged — reivindicar cravado/
        # computed num rollup levanta LOUD, nunca agrega.
        import cortex_provenance
        gate = publisher._gate_payload(self._proof())
        with self.assertRaises(ValueError):
            cortex_provenance.assert_rollup_computed([gate])

    def test_gate_payload_with_strikes_is_not_a_pass(self):
        gate = publisher._gate_payload(self._proof(strikes=["referente sem nome"]))
        self.assertFalse(gate["pass"])
        self.assertEqual(gate["strikes_n"], 1)

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
        self.assertEqual(props["gate_rubric"], close.GATE_RUBRIC_VERSION)
        self.assertTrue(props["gate_pass"])
        self.assertEqual(props["gate_strikes_n"], 0)
        self.assertEqual(props["gate_feynman_content_depth"], 4)
        self.assertEqual(props["gate_regular_didactic_clarity"], 3)
        self.assertEqual(props["gate_provenance_class"], "llm_judged")
        self.assertEqual(props["gate_rigor"], "lead")
        self.assertEqual(props["gate_validity"], "inferred_default")
        rat = json.loads(props["gate_rationales"])
        self.assertEqual(rat["feynman"]["content_depth"], "dados reais")
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
