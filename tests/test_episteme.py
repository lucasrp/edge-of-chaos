"""Ticket A — episteme NATIVO no cortex (03-A + ontologia-cortex-v2 §1-§3/§6).

A.1 — a caneta da hipótese: `eventlog.declare_hypothesis` valida o falsifier ESTRUTURADO
{metric, threshold, direction} (HIP-1: só-prosa = raise LOUD); ULID primário (O-2),
content_hash secundário (O-3); `supersede_hypothesis` versiona (O-4 — nó imutável, novo ULID
+ aresta SUPERSEDES, nunca edição).

A.2 — bears_on: a correspondência thread=hipótese=artefato são 3 NÓS (2-hop), nunca identidade;
o artefato declara `bears_on: [{hypothesis, valence, rationale}]` no payload do publish —
digest-bound como lineage (mesma ameaça: arg-de-publish que afeta estado fora do digest é
forjável) — e o publisher projeta arestas valenciadas SUPPORTS|REFUTES|QUALIFIES|INCONCLUSIVE
com rigor=lead (teto duro), validity=inferred_default, provenance_class=asserted (CX-1: nunca
entra em rollup computed). Verdict NUNCA é armazenado.

A.3 — §6 parceiro: PROMOÇÃO, não mintagem — a :Entity extraída ganha a marca `parceiro`
(asserted, HITL: autoridade nomeada); a projeção só MATCHa, jamais cria o nó. `para` no publish
→ aresta artefato-PARA->parceiro (o documento FEITO pra pessoa).

A.4 — o schema declarativo `cortex/schema/ontologia.yaml` ganha nós/arestas/enums travados +
alias-map episteme (o instrumento que MEDE o diff do H-001); Experiment é nativo só por
`experiment.curated`, e Observation não nasce vazia.
"""
import json
import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import close  # noqa: E402
import cortex_provenance  # noqa: E402
import eventlog  # noqa: E402
import lineage  # noqa: E402
import publisher  # noqa: E402
import recall  # noqa: E402


FALSIFIER = {"metric": "ontology_diff_types", "threshold": 0, "direction": "menor"}


def _log(tmp):
    return Path(tmp) / "log.jsonl"


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def data(self):
        return self.rows

    def single(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    """Records every (query, params) run; serves canned rows keyed by a substring match."""

    def __init__(self, rows_by_marker=None):
        self.calls = []
        self.rows_by_marker = rows_by_marker or {}

    def run(self, query, **params):
        self.calls.append((query, params))
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return FakeResult(rows)
        return FakeResult()


class DeclareHypothesisPen(unittest.TestCase):
    """HIP-1 — hipótese nasce da caneta com falsifier ESTRUTURADO machine-comparable;
    ausente/só-prosa ⇒ LOUD. ULID primário (O-2), content_hash(statement+falsifier) secundário."""

    def test_declares_with_structured_falsifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = eventlog.declare_hypothesis(
                "o cortex re-instancia o episteme com diff ~0",
                FALSIFIER, slug="h-001", author="ed", log=_log(tmp))
            self.assertEqual(ev["type"], "hypothesis.declared")
            p = ev["payload"]
            # ULID primário: 26 chars Crockford base32
            self.assertRegex(p["ulid"], r"^[0-9A-HJKMNP-TV-Z]{26}$")
            self.assertEqual(ev["subject"], f"hypothesis:{p['ulid']}")
            self.assertEqual(p["slug"], "h-001")
            self.assertEqual(p["falsifier"], FALSIFIER)
            self.assertEqual(p["author"], "ed")
            # content_hash secundário: canonical json de statement+falsifier
            blob = json.dumps({"statement": p["statement"], "falsifier": p["falsifier"]},
                              sort_keys=True, ensure_ascii=False).encode("utf-8")
            self.assertEqual(p["content_hash"], hashlib.sha256(blob).hexdigest())

    def test_prose_only_falsifier_raises_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                eventlog.declare_hypothesis("h", "se o diff for grande, falha", log=_log(tmp))

    def test_missing_or_malformed_falsifier_fields_raise(self):
        bad = [
            {"threshold": 0, "direction": "menor"},                       # sem metric
            {"metric": " ", "threshold": 0, "direction": "menor"},        # metric blank
            {"metric": "m", "direction": "menor"},                        # sem threshold
            {"metric": "m", "threshold": "zero", "direction": "menor"},   # threshold não-numérico
            {"metric": "m", "threshold": True, "direction": "menor"},     # bool não é número
            {"metric": "m", "threshold": float("nan"), "direction": "menor"},  # não-finito
            {"metric": "m", "threshold": 0},                              # sem direction
            {"metric": "m", "threshold": 0, "direction": "up"},           # direction fora do enum
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for f in bad:
                with self.assertRaises(ValueError, msg=f):
                    eventlog.declare_hypothesis("h", f, log=_log(tmp))

    def test_blank_statement_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                eventlog.declare_hypothesis("  ", FALSIFIER, log=_log(tmp))

    def test_junk_falsifier_keys_never_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = eventlog.declare_hypothesis(
                "h", {**FALSIFIER, "verdict": "supported"}, log=_log(tmp))
            # o falsifier persistido é SÓ {metric, threshold, direction} — nenhum verdict
            # armazenado, nunca (ontologia §2b: "Verdict is NEVER stored").
            self.assertEqual(set(ev["payload"]["falsifier"]), {"metric", "threshold", "direction"})

    def test_ulids_are_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = eventlog.declare_hypothesis("h1", FALSIFIER, log=_log(tmp))
            b = eventlog.declare_hypothesis("h2", FALSIFIER, log=_log(tmp))
            self.assertNotEqual(a["payload"]["ulid"], b["payload"]["ulid"])


class SupersedeHypothesisIsVersioning(unittest.TestCase):
    """O-4 — nó imutável: mudar = declarar NOVA hipótese (novo ULID) + evento superseded
    ligando velha→nova; a caneta recusa ulids que nunca declararam neste log."""

    def _two(self, log):
        old = eventlog.declare_hypothesis("v1", FALSIFIER, log=log)["payload"]["ulid"]
        new = eventlog.declare_hypothesis("v2", FALSIFIER, log=log)["payload"]["ulid"]
        return old, new

    def test_supersede_links_old_to_new_in_the_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            old, new = self._two(log)
            eventlog.supersede_hypothesis(old, new, log=log)
            hyps = eventlog.hypotheses_at(log=log)
            self.assertEqual(hyps[old]["superseded_by"], new)
            self.assertIsNone(hyps[new]["superseded_by"])
            self.assertEqual(hyps[new]["statement"], "v2")

    def test_supersede_unknown_ulid_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            old, new = self._two(log)
            with self.assertRaises(ValueError):
                eventlog.supersede_hypothesis("01UNKNOWNULIDUNKNOWNULID00", new, log=log)
            with self.assertRaises(ValueError):
                eventlog.supersede_hypothesis(old, "01UNKNOWNULIDUNKNOWNULID00", log=log)

    def test_supersede_self_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            old, _ = self._two(log)
            with self.assertRaises(ValueError):
                eventlog.supersede_hypothesis(old, old, log=log)


class NormalizeBearsOnIsTheSingleSanitizer(unittest.TestCase):
    """Espelho de normalize_lineage (mesma camada neutra): só itens bem-formados sobrevivem
    ao digest e ao evento — valência fora do enum, hypothesis blank, junk: DROPPED, nunca
    coagido. A multivalência é nativa (1 artefato → N entries, O-6)."""

    def test_keeps_only_well_formed_items(self):
        raw = [
            {"hypothesis": "01ABC", "valence": "supports", "rationale": "porque sim"},
            {"hypothesis": "01ABC", "valence": "refutes"},
            "prosa",                                             # não-dict
            {"hypothesis": " ", "valence": "supports"},           # alvo blank
            {"hypothesis": "01DEF", "valence": "verdadeiro"},     # valência fora do enum
            {"hypothesis": "01ABC", "valence": "supports", "rationale": "dup"},  # dupe
            {"hypothesis": "01GHI", "valence": "qualifies", "rationale": 42},    # rationale não-str
        ]
        out = lineage.normalize_bears_on(raw)
        self.assertEqual(out, [
            {"hypothesis": "01ABC", "valence": "supports", "rationale": "porque sim"},
            {"hypothesis": "01ABC", "valence": "refutes"},
            {"hypothesis": "01GHI", "valence": "qualifies"},
        ])

    def test_non_list_folds_to_empty(self):
        self.assertEqual(lineage.normalize_bears_on(None), [])
        self.assertEqual(lineage.normalize_bears_on({"hypothesis": "x"}), [])

    def test_para_normalizer_keeps_nonblank_names_deduped(self):
        self.assertEqual(lineage.normalize_para(["Julio", " ", 7, "Julio", "Ana "]),
                         ["Julio", "Ana"])
        self.assertEqual(lineage.normalize_para("Julio"), [])


class BearsOnAndParaRideThePublishPayload(unittest.TestCase):
    """O payload do `artefato.published` ganha bears_on + para (normalizados); o fold do corpus
    os carrega para o replay (reproject restaura as arestas); evento legado folda []."""

    def test_atomic_publish_persists_normalized_bears_on_and_para(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            ulid = eventlog.declare_hypothesis("h", FALSIFIER, log=log)["payload"]["ulid"]
            ev, _ = eventlog.publish_artefato_atomic(
                "a-slug", "intent", log=log,
                bears_on=[{"hypothesis": ulid, "valence": "supports", "rationale": "r"},
                          "junk"],
                para=["Julio", " "])
            self.assertEqual(ev["payload"]["bears_on"],
                             [{"hypothesis": ulid, "valence": "supports", "rationale": "r"}])
            self.assertEqual(ev["payload"]["para"], ["Julio"])
            item = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item["bears_on"][0]["hypothesis"], ulid)
            self.assertEqual(item["para"], ["Julio"])

    def test_legacy_event_folds_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.publish_artefato_atomic("legacy", "intent", log=log)
            item = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item["bears_on"], [])
            self.assertEqual(item["para"], [])


class ProofDigestBindsBearsOnAndPara(unittest.TestCase):
    """E1b, o mesmo padrão do lineage: um arg de publish que afeta estado FORA do digest é
    forjável na hora do publish. bears_on/para entram no digest; verify_proof recusa alteração."""

    def test_digest_differs_when_bears_on_or_para_change(self):
        base = dict(slug="s", spec={"sections": []}, intent="i", cites=[], proposes=[])
        d0 = close.proof_digest(**base)
        d1 = close.proof_digest(**base, bears_on=[{"hypothesis": "01A", "valence": "supports"}])
        d2 = close.proof_digest(**base, para=["Julio"])
        self.assertNotEqual(d0, d1)
        self.assertNotEqual(d0, d2)
        self.assertNotEqual(d1, d2)

    def test_malformed_bears_on_digests_like_absent(self):
        base = dict(slug="s", spec={"sections": []}, intent="i", cites=[], proposes=[])
        self.assertEqual(close.proof_digest(**base),
                         close.proof_digest(**base, bears_on=["junk"], para=[42]))

    def test_verify_proof_refuses_altered_bears_on(self):
        art = {
            "slug": "bound", "intent": "open: x; bet: y",
            "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "bound content."}]}]},
            "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                       "snippet": "s"}],
            "proposes": [{"body": "b", "kind": "constraint"}],
            "bears_on": [{"hypothesis": "01A", "valence": "supports"}],
            "para": ["Julio"],
        }
        good = json.dumps({"pass": True, "scores": {d: 4 for d in close.DIMENSIONS},
                           "strikes": [], "rationales": {}, "overall": 4.0})
        proof = close.run_close(art, lambda: art, complete_fn=lambda *a, **k: good)
        self.assertTrue(proof["pass"])
        kw = dict(slug="bound", spec=art["content"], intent=art["intent"],
                  cites=art["cites"], proposes=art["proposes"])
        # binds: verify com o MESMO bears_on/para passa…
        close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=art["para"])
        # …e qualquer alteração é digest mismatch
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw,
                               bears_on=[{"hypothesis": "01A", "valence": "refutes"}],
                               para=art["para"])
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=["Outro"])


class PublishForwardsBearsOnToEventAndProjection(unittest.TestCase):
    """publisher.publish → publish_artefato_atomic → project_fn: bears_on/para atravessam a
    costura inteira (evento durável + projeção), digest-bound de ponta a ponta."""

    def test_publish_forwards_bears_on_and_para(self):
        spec = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "atomic publish plus kernel in one act."}]}]}
        intent = "open: x; bet: y"
        cites = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True, "snippet": "s"}]
        bears = [{"hypothesis": "01A", "valence": "supports"}]
        verdicts = [
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.FEYNMAN_REVIEWER_ID},
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.REGULAR_REVIEWER_ID},
        ]
        proof = close._mint_proof(verdicts, slug="fwd", spec=spec, intent=intent,
                                  cites=cites, proposes=[], skill="report",
                                  bears_on=bears, para=["Julio"])
        seen = {}
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.dispatch_open(log=log)
            publisher.publish(
                "fwd", spec, intent, skill="report", cites=cites, verdict=proof,
                bears_on=bears, para=["Julio"], log=log, blog_dir=tmp,
                embed_fn=lambda t: [1.0, 0.0],
                project_fn=lambda *a, **k: seen.update(k))
            ev = eventlog.read(types=["artefato.published"], log=log)[-1]
            self.assertEqual(ev["payload"]["bears_on"], bears)
            self.assertEqual(ev["payload"]["para"], ["Julio"])
            self.assertEqual(seen.get("bears_on"), bears)
            self.assertEqual(seen.get("para"), ["Julio"])


class ValencedEdgesProjectWithTheLeadCeiling(unittest.TestCase):
    """§2b — a projeção da aresta valenciada: label do enum FIXO (nunca interpolação de dado do
    caller), props {provenance_class:asserted, rigor:lead, validity:inferred_default, scope:cortex};
    alvo não-resolvido → unresolved (projection_complete=false, self-heal no próximo sweep)."""

    def test_supports_edge_merges_with_the_declared_props(self):
        s = FakeSession(rows_by_marker={":Hypothesis": [{"n": 1}]})
        unresolved = publisher._project_bears_on(
            s, "g1", "slug-a", [{"hypothesis": "01A", "valence": "supports",
                                 "rationale": "por isso"}])
        self.assertFalse(unresolved)
        q, params = next((q, p) for q, p in s.calls if "SUPPORTS" in q)
        self.assertIn("MERGE (a)-[r:SUPPORTS]->(h)", q)
        self.assertIn("'asserted'", q)
        self.assertIn("'lead'", q)
        self.assertIn("'inferred_default'", q)
        self.assertIn("'cortex'", q)
        self.assertEqual(params["ref"], "01A")
        self.assertEqual(params["rat"], "por isso")

    def test_valence_maps_through_the_fixed_label_allowlist(self):
        s = FakeSession(rows_by_marker={":Hypothesis": [{"n": 1}]})
        publisher._project_bears_on(
            s, "g1", "slug-a",
            [{"hypothesis": "01A", "valence": "refutes"},
             {"hypothesis": "01B", "valence": "qualifies"},
             {"hypothesis": "01C", "valence": "inconclusive"}])
        text = " ".join(q for q, _ in s.calls)
        for label in ("REFUTES", "QUALIFIES", "INCONCLUSIVE"):
            self.assertIn(f"MERGE (a)-[r:{label}]->(h)", text)

    def test_unresolved_hypothesis_marks_incomplete(self):
        s = FakeSession(rows_by_marker={":Hypothesis": [{"n": 0}]})
        unresolved = publisher._project_bears_on(
            s, "g1", "slug-a", [{"hypothesis": "01NOPE", "valence": "supports"}])
        self.assertTrue(unresolved)

    def test_para_edge_matches_only_promoted_parceiros_never_creates(self):
        s = FakeSession(rows_by_marker={"parceiro": [{"n": 1}]})
        unresolved = publisher._project_para(s, "g1", "slug-a", ["Julio"])
        self.assertFalse(unresolved)
        q = next(q for q, _ in s.calls if "PARA" in q)
        self.assertIn("MERGE (a)-[r:PARA]->(e)", q)
        self.assertIn("parceiro", q)
        # promoção, não mintagem (§6): a projeção jamais cria a Entity
        self.assertNotIn("MERGE (e:Entity", q)

    def test_unresolved_para_marks_incomplete(self):
        s = FakeSession(rows_by_marker={"parceiro": [{"n": 0}]})
        self.assertTrue(publisher._project_para(s, "g1", "slug-a", ["Ninguem"]))

    def test_valenced_and_para_labels_join_the_destructive_rebuild(self):
        # a republish com bears_on corrigido não pode deixar aresta velha encalhada —
        # os labels entram no MESMO delete-then-readd por slug do project_artefato.
        import inspect
        src = re.sub(r'["\s]', "", inspect.getsource(publisher.project_artefato))
        m = re.search(r"-\[r:([A-Z_|]+)\]->\(\)", src)
        self.assertIsNotNone(m)
        rebuilt = set(m.group(1).split("|"))
        self.assertLessEqual(
            {"SUPPORTS", "REFUTES", "QUALIFIES", "INCONCLUSIVE", "PARA"}, rebuilt)


class BackboneProjectsHypothesesAndParceiros(unittest.TestCase):
    """Os nós :Hypothesis (fold de hypothesis.declared) e a marca parceiro (fold de
    parceiro.promoted) projetam no backbone — idempotente, replayado a cada sweep canônico."""

    def test_hypothesis_nodes_project_from_the_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            ulid = eventlog.declare_hypothesis(
                "h viva", FALSIFIER, slug="h-001", log=log)["payload"]["ulid"]
            s = FakeSession()
            publisher._project_hypotheses(s, "g1", log)
            q, params = next((q, p) for q, p in s.calls if "MERGE (h:Hypothesis" in q)
            self.assertEqual(params["ulid"], ulid)
            self.assertEqual(params["statement"], "h viva")
            self.assertEqual(params["fm"], "ontology_diff_types")
            self.assertEqual(params["ft"], 0)
            self.assertEqual(params["fd"], "menor")
            self.assertEqual(params["slug"], "h-001")

    def test_superseded_pair_projects_a_supersedes_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            old = eventlog.declare_hypothesis("v1", FALSIFIER, log=log)["payload"]["ulid"]
            new = eventlog.declare_hypothesis("v2", FALSIFIER, log=log)["payload"]["ulid"]
            eventlog.supersede_hypothesis(old, new, log=log)
            s = FakeSession()
            publisher._project_hypotheses(s, "g1", log)
            q, params = next((q, p) for q, p in s.calls
                             if "SUPERSEDES" in q and "MERGE" in q)
            self.assertEqual(params["new"], new)
            self.assertEqual(params["old"], old)

    def test_reproject_after_re_supersede_leaves_no_stale_edge(self):
        # codex adversarial #4: o fold é last-wins (old→new2 corrige old→new1); a projeção
        # MERGE-only deixaria new1-[:SUPERSEDES]->old encalhada. O rebuild é destrutivo por
        # alvo (o padrão ANCHORS): DELETE as SUPERSEDES que apontam pro old, depois MERGE a atual.
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            old = eventlog.declare_hypothesis("v1", FALSIFIER, log=log)["payload"]["ulid"]
            n1 = eventlog.declare_hypothesis("v2", FALSIFIER, log=log)["payload"]["ulid"]
            n2 = eventlog.declare_hypothesis("v2-corrigida", FALSIFIER, log=log)["payload"]["ulid"]
            eventlog.supersede_hypothesis(old, n1, log=log)
            eventlog.supersede_hypothesis(old, n2, log=log)   # correção: last-wins no fold
            s = FakeSession()
            publisher._project_hypotheses(s, "g1", log)
            sup_calls = [(q, p) for q, p in s.calls if "SUPERSEDES" in q]
            deletes = [(q, p) for q, p in sup_calls if "DELETE" in q]
            merges = [(q, p) for q, p in sup_calls if "MERGE" in q]
            self.assertTrue(deletes, "a projeção deve DELETAR as SUPERSEDES velhas do alvo")
            self.assertEqual(len(merges), 1)
            self.assertEqual(merges[0][1]["new"], n2, "só a superseded_by ATUAL projeta")

    def test_parceiro_promotion_marks_the_existing_entity_never_mints(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.promote_parceiro("Julio", "pesquisador", by="operator", log=log)
            s = FakeSession()
            publisher._project_parceiros(s, "g1", log)
            q, params = next((q, p) for q, p in s.calls if "parceiro" in q)
            self.assertIn("MATCH (e:Entity", q)
            self.assertNotIn("MERGE (e:Entity", q)   # promoção, não mintagem (§6)
            self.assertEqual(params["name"], "Julio")
            self.assertEqual(params["kind"], "pesquisador")


class PromoteParceiroPen(unittest.TestCase):
    """§6 — a caneta da promoção: HITL (autoridade nomeada), kind do enum, asserted.
    O fold `parceiros_at` é o que a projeção replaya."""

    def test_promotes_with_named_authority_and_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            ev = eventlog.promote_parceiro("Julio", "pesquisador", by="operator",
                                           domain="juridico", log=log)
            self.assertEqual(ev["type"], "parceiro.promoted")
            self.assertEqual(ev["payload"]["provenance_class"], "asserted")
            got = eventlog.parceiros_at(log=log)["Julio"]
            self.assertEqual(got["kind"], "pesquisador")
            self.assertEqual(got["by"], "operator")
            self.assertEqual(got["domain"], "juridico")

    def test_refuses_missing_authority_blank_name_or_unknown_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            with self.assertRaises(ValueError):
                eventlog.promote_parceiro("Julio", "pesquisador", by=" ", log=log)
            with self.assertRaises(ValueError):
                eventlog.promote_parceiro(" ", "pesquisador", by="op", log=log)
            with self.assertRaises(ValueError):
                eventlog.promote_parceiro("Julio", "amigo", by="op", log=log)


class ValencedEdgesLiveOnTheAssertedPlane(unittest.TestCase):
    """CX-1 — a aresta valenciada declarada pelo autor é `asserted` (nunca computed): o
    scoreboard só consome computed, então um SUPPORTS num rollup grita LOUD."""

    def test_valences_and_para_derive_asserted(self):
        for t in ("supports", "refutes", "qualifies", "inconclusive", "para"):
            self.assertEqual(cortex_provenance.provenance_class_for(t), "asserted", t)

    def test_cx1_rejects_a_supports_edge_in_a_rollup(self):
        with self.assertRaises(ValueError):
            cortex_provenance.assert_rollup_computed(
                [{"edge_type": "supports", "id": "a->h"}])


class SurfAllowlistGainsTheValencedPair(unittest.TestCase):
    """§2c — SURF allowlist += SUPPORTS|REFUTES (sinal associativo); QUALIFIES/INCONCLUSIVE
    ficam FORA (peso de anotação, não associação)."""

    def test_supports_and_refutes_surf_qualifies_does_not(self):
        m = re.search(r"\[:([A-Z_|]+)\*1\.\.2\]", recall.SURF_QUERY)
        rels = set(m.group(1).split("|"))
        self.assertEqual(rels, {"BUILDS_ON", "SUPERSEDES", "CONTRADICTS", "RELATES_TO",
                                "CITES", "SUPPORTS", "REFUTES"})


class ProducerSnippetsForwardBearsOnAndPara(unittest.TestCase):
    """Codex adversarial #2 (meta-gate: SINAL) — o mint agora lê artefato.get('bears_on'/'para');
    um producer que adote a chave com a lambda velha mintaria um proof que o publisher rejeita
    (digest mismatch). As lambdas de publish dos SKILL.md encaminham ambos — pin mecânico,
    espelho do pin de dispatch_id."""

    PRODUCERS = ["report", "research", "discovery", "map", "plan", "prototype", "grill"]

    def test_every_publish_fn_forwards_bears_on_and_para(self):
        for p in self.PRODUCERS:
            doc = (REPO / "skills" / p / "SKILL.md").read_text()
            i = doc.find("publish_fn=lambda art, proof")
            self.assertNotEqual(i, -1, f"{p}: publish_fn lambda not found")
            region = doc[i:i + 600]
            for arg in ("bears_on=art.get('bears_on')", "para=art.get('para')"):
                self.assertIn(arg, region,
                              f"{p}: publish_fn must forward {arg} (mint binds it — an "
                              "adopted key with the old lambda is a digest mismatch)")


class OntologiaSchemaIsTheMeasurementInstrument(unittest.TestCase):
    """O schema declarativo que MEDE o diff do H-001: enums travados, alias-map episteme,
    e Experiment nativo quando existe caneta/curadoria real."""

    @classmethod
    def setUpClass(cls):
        import yaml
        cls.schema = yaml.safe_load(
            (REPO / "cortex" / "schema" / "ontologia.yaml").read_text())

    def test_provenance_class_enum_is_locked(self):
        self.assertEqual(self.schema["provenance_class"]["enum"],
                         ["computed", "asserted", "llm_judged", "extracted"])
        self.assertEqual(self.schema["provenance_class"]["rollup_eligible"], ["computed"])

    def test_rigor_ceiling_and_validity_enums(self):
        self.assertEqual(self.schema["enums"]["rigor"], ["lead", "cravado"])
        self.assertEqual(self.schema["enums"]["validity"],
                         ["valid", "inferred_default", "quarantine_invalid"])
        self.assertEqual(self.schema["enums"]["valencia"],
                         ["supports", "refutes", "qualifies", "inconclusive"])

    def test_alias_map_declares_the_episteme_correspondence(self):
        aliases = self.schema["edges"]["aliases"]
        self.assertEqual(aliases["SUPPORTS"], "apoia")
        self.assertEqual(aliases["REFUTES"], "refuta")
        self.assertEqual(aliases["SUPERSEDES"], "supersede")
        self.assertIn("deriva_de", aliases["BUILDS_ON"])

    def test_experiment_is_a_native_curated_node_not_reserved(self):
        self.assertNotIn("reserved_nodes", self.schema)
        self.assertEqual(self.schema["nodes"]["experiment"]["truth"], "experiment.curated")
        self.assertEqual(self.schema["nodes"]["experiment"]["read_order"],
                         ["canonical", "canonical_artifacts"])
        self.assertIn("modelagem", self.schema["nodes"])
        self.assertIn("observation", self.schema["nodes"])

    def test_hypothesis_and_parceiro_are_declared_nodes(self):
        self.assertIn("hypothesis", self.schema["nodes"])
        self.assertIn("parceiro", self.schema["nodes"])

    def test_rule_templates_register_the_gate_score_ruler(self):
        self.assertIn("gate_score_delta@1", self.schema["rule_templates"])


if __name__ == "__main__":
    unittest.main()
