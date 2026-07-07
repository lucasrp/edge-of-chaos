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
alias-map episteme (o instrumento que MEDE o diff do H-001); Experiment é nó próprio e report
publicado liga Artefato->Experiment via REPORTS_ON, `experiment.curated` é leitura canônica
explícita, e Observation não nasce vazia.
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

    def test_reports_on_normalizer_keeps_experiment_ids_deduped(self):
        self.assertEqual(lineage.normalize_reports_on([" exp40 ", "", 7, "exp40", "exp41"]),
                         ["exp40", "exp41"])
        self.assertEqual(lineage.normalize_reports_on("exp40"), [])
        self.assertEqual(lineage.normalize_reports_on(["session-memory", "2026-exp", "exp071"]),
                         ["exp071"])

    def test_experiment_curation_normalizer_adds_the_report_artifact(self):
        curation = lineage.normalize_experiment_curation(
            [" exp40 "],
            {"prose": "GN wins this retrieval race.",
             "typed": {
                 "claim": "GN wins.",
                 "scope": "process 76610395.",
                 "status": "lead",
                 "caveat": "n=1.",
                 "supports": ["GN"],
                 "excludes": [],
                 "next": "Run C5.",
             },
             "canonical_artifacts": [{"ref": "results/summary.json", "role": "summary"}]},
            report_slug="relatorio-exp40",
            by="report")
        self.assertEqual(curation[0]["experiment_id"], "exp40")
        self.assertEqual(curation[0]["canonical_artifacts"][0],
                         {"ref": "artefato:relatorio-exp40", "role": "report",
                          "note": "finalization report"})

    def test_experiment_curation_requires_a_report_artifact(self):
        with self.assertRaisesRegex(ValueError, "finalization report artifact"):
            lineage.normalize_experiment_curation(
                ["exp40"],
                {"prose": "GN wins this retrieval race.",
                 "typed": {
                     "claim": "GN wins.",
                     "scope": "process 76610395.",
                     "status": "lead",
                     "caveat": "n=1.",
                     "supports": ["GN"],
                     "excludes": [],
                     "next": "Run C5.",
                 },
                 "canonical_artifacts": [{"ref": "results/summary.json", "role": "summary"}]},
                by="report")

    def test_experiment_curation_requires_a_canonical_experiment_id(self):
        with self.assertRaisesRegex(ValueError, "requires reports_on"):
            lineage.normalize_experiment_curation(
                ["session-memory-navigator"],
                {"prose": "The run is useful.",
                 "typed": {
                     "claim": "The run is useful.",
                     "scope": "one local session.",
                     "status": "lead",
                     "caveat": "single run.",
                     "supports": ["navigator"],
                     "excludes": [],
                     "next": "Repeat.",
                 }},
                report_slug="relatorio-exp")


class ExperimentDeclarationAndNumbering(unittest.TestCase):
    """Issue #107 — experiments have stable canonical ids before their report closes them."""

    def test_next_experiment_id_allocates_zero_padded_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            self.assertEqual(eventlog.next_experiment_id(log=log), "exp001")
            a = eventlog.declare_experiment("Compare two report structures", log=log)
            b = eventlog.declare_experiment("Compare source gates", log=log)
            self.assertEqual(a["payload"]["experiment_id"], "exp001")
            self.assertEqual(b["payload"]["experiment_id"], "exp002")
            self.assertEqual(eventlog.next_experiment_id(log=log), "exp003")

    def test_historical_ids_participate_in_the_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.curate_experiment(
                "exp40",
                prose="exp40 is a legal retrieval experiment.",
                typed={"claim": "GN wins.", "scope": "one process.", "status": "lead",
                       "caveat": "n=1.", "supports": ["GN"], "excludes": [],
                       "next": "Run C5."},
                canonical_artifacts=[{"ref": "artefato:relatorio-exp40", "role": "report"}],
                by="grill",
                log=log)
            self.assertEqual(eventlog.next_experiment_id(log=log), "exp041")

    def test_declared_experiment_is_readable_before_curation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.declare_experiment(
                "Find the best report dispatch",
                experiment_id="exp071",
                hypothesis="a pre-draft gate improves the final report",
                scope="Roberto research reports",
                owner="mentor",
                decision_rule="ship the arm with the best final judge plus human read",
                arms=[{"id": "baseline"}, {"id": "pre-draft"}],
                by="mentor",
                log=log)
            got = eventlog.experiment_at("exp071", log=log)
            self.assertEqual(got["title"], "Find the best report dispatch")
            self.assertEqual(got["status"], "declared")
            self.assertEqual(got["canonical"], {})
            self.assertEqual(got["canonical_artifacts"], [])

    def test_duplicate_or_noncanonical_experiment_id_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.declare_experiment("one", experiment_id="exp071", log=log)
            with self.assertRaises(ValueError):
                eventlog.declare_experiment("two", experiment_id="exp071", log=log)
            with self.assertRaises(ValueError):
                eventlog.declare_experiment("bad", experiment_id="weekend-report-test", log=log)


class BearsOnAndParaRideThePublishPayload(unittest.TestCase):
    """O payload do `artefato.published` ganha bears_on + para + reports_on (normalizados); o
    fold do corpus os carrega para o replay (reproject restaura as arestas); evento legado folda []."""

    def test_atomic_publish_persists_normalized_bears_on_para_and_reports_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            ulid = eventlog.declare_hypothesis("h", FALSIFIER, log=log)["payload"]["ulid"]
            ev, _ = eventlog.publish_artefato_atomic(
                "a-slug", "intent", log=log,
                bears_on=[{"hypothesis": ulid, "valence": "supports", "rationale": "r"},
                          "junk"],
                para=["Julio", " "], reports_on=[" exp40 ", "exp40", None])
            self.assertEqual(ev["payload"]["bears_on"],
                             [{"hypothesis": ulid, "valence": "supports", "rationale": "r"}])
            self.assertEqual(ev["payload"]["para"], ["Julio"])
            self.assertEqual(ev["payload"]["reports_on"], ["exp40"])
            item = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item["bears_on"][0]["hypothesis"], ulid)
            self.assertEqual(item["para"], ["Julio"])
            self.assertEqual(item["reports_on"], ["exp40"])

    def test_legacy_event_folds_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.publish_artefato_atomic("legacy", "intent", log=log)
            item = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item["bears_on"], [])
            self.assertEqual(item["para"], [])
            self.assertEqual(item["reports_on"], [])


class ProofDigestBindsBearsOnParaReportsOnAndExperimentCuration(unittest.TestCase):
    """E1b, o mesmo padrão do lineage: um arg de publish que afeta estado FORA do digest é
    forjável na hora do publish. bears_on/para/reports_on/experiment_curation entram no digest;
    verify_proof recusa alteração."""

    def test_digest_differs_when_bears_on_para_reports_on_or_experiment_curation_change(self):
        base = dict(slug="s", spec={"sections": []}, intent="i", cites=[], proposes=[])
        curation = {
            "prose": "GN wins.",
            "typed": {"claim": "GN wins.", "scope": "process 76610395.", "status": "lead",
                      "caveat": "n=1.", "supports": ["GN"], "excludes": [],
                      "next": "Run C5."},
        }
        d0 = close.proof_digest(**base)
        d1 = close.proof_digest(**base, bears_on=[{"hypothesis": "01A", "valence": "supports"}])
        d2 = close.proof_digest(**base, para=["Julio"])
        d3 = close.proof_digest(**base, reports_on=["exp40"])
        d4 = close.proof_digest(**base, reports_on=["exp40"], skill="report",
                                experiment_curation=curation)
        self.assertNotEqual(d0, d1)
        self.assertNotEqual(d0, d2)
        self.assertNotEqual(d0, d3)
        self.assertNotEqual(d0, d4)
        self.assertNotEqual(d1, d2)

    def test_malformed_bears_on_reports_on_digests_like_absent(self):
        base = dict(slug="s", spec={"sections": []}, intent="i", cites=[], proposes=[])
        self.assertEqual(close.proof_digest(**base),
                         close.proof_digest(**base, bears_on=["junk"], para=[42],
                                            reports_on=[42, " "]))

    def test_verify_proof_refuses_altered_bears_on(self):
        art = {
            "slug": "bound", "intent": "open: x; bet: y",
            "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "bound content."}]}]},
            "skill": "report",
            "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                       "snippet": "s"}],
            "proposes": [{"body": "b", "kind": "constraint"}],
            "bears_on": [{"hypothesis": "01A", "valence": "supports"}],
            "para": ["Julio"],
            "reports_on": ["exp40"],
            "experiment_curation": {
                "prose": "GN wins.",
                "typed": {"claim": "GN wins.", "scope": "process 76610395.", "status": "lead",
                          "caveat": "n=1.", "supports": ["GN"], "excludes": [],
                          "next": "Run C5."},
            },
        }
        good = json.dumps({"pass": True, "scores": {d: 4 for d in close.DIMENSIONS},
                           "strikes": [], "rationales": {}, "overall": 4.0})
        proof = close.run_close(art, lambda: art, complete_fn=lambda *a, **k: good)
        self.assertTrue(proof["pass"])
        kw = dict(slug="bound", spec=art["content"], intent=art["intent"],
                  cites=art["cites"], proposes=art["proposes"], skill=art["skill"])
        # binds: verify com o MESMO bears_on/para passa…
        close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=art["para"],
                           reports_on=art["reports_on"],
                           experiment_curation=art["experiment_curation"])
        # …e qualquer alteração é digest mismatch
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw,
                               bears_on=[{"hypothesis": "01A", "valence": "refutes"}],
                               para=art["para"], reports_on=art["reports_on"],
                               experiment_curation=art["experiment_curation"])
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=["Outro"],
                               reports_on=art["reports_on"],
                               experiment_curation=art["experiment_curation"])
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=art["para"],
                               reports_on=["exp41"], experiment_curation=art["experiment_curation"])
        altered = {**art["experiment_curation"], "prose": "GN wins after audit."}
        with self.assertRaises(ValueError):
            close.verify_proof(proof, **kw, bears_on=art["bears_on"], para=art["para"],
                               reports_on=art["reports_on"], experiment_curation=altered)


class PublishForwardsBearsOnToEventAndProjection(unittest.TestCase):
    """publisher.publish → publish_artefato_atomic → project_fn: bears_on/para/reports_on
    atravessam a costura inteira (evento durável + projeção), digest-bound de ponta a ponta."""

    def test_publish_forwards_bears_on_para_reports_on_and_finalizes_experiment(self):
        spec = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "atomic publish plus kernel in one act."}]}]}
        intent = "open: x; bet: y"
        cites = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True, "snippet": "s"}]
        bears = [{"hypothesis": "01A", "valence": "supports"}]
        experiment_curation = {
            "prose": "GN wins this retrieval race.",
            "typed": {"claim": "GN wins.", "scope": "process 76610395.", "status": "lead",
                      "caveat": "n=1.", "supports": ["GN"], "excludes": [],
                      "next": "Run C5."},
        }
        verdicts = [
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.FEYNMAN_REVIEWER_ID},
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.REGULAR_REVIEWER_ID},
        ]
        proof = close._mint_proof(verdicts, slug="fwd", spec=spec, intent=intent,
                                  cites=cites, proposes=[], skill="report",
                                  bears_on=bears, para=["Julio"], reports_on=["exp40"],
                                  experiment_curation=experiment_curation)
        seen = {}
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.dispatch_open(log=log)
            publisher.publish(
                "fwd", spec, intent, skill="report", cites=cites, verdict=proof,
                bears_on=bears, para=["Julio"], reports_on=[" exp40 "],
                experiment_curation=experiment_curation, log=log, blog_dir=tmp,
                embed_fn=lambda t: [1.0, 0.0],
                project_fn=lambda *a, **k: seen.update(k))
            ev = eventlog.read(types=["artefato.published"], log=log)[-1]
            self.assertEqual(ev["payload"]["bears_on"], bears)
            self.assertEqual(ev["payload"]["para"], ["Julio"])
            self.assertEqual(ev["payload"]["reports_on"], ["exp40"])
            exp = eventlog.experiment_at("exp40", log=log)
            self.assertEqual(exp["canonical"]["prose"], experiment_curation["prose"])
            self.assertEqual(exp["canonical_artifacts"][0]["ref"], "artefato:fwd")
            self.assertEqual(seen.get("bears_on"), bears)
            self.assertEqual(seen.get("para"), ["Julio"])
            self.assertEqual(seen.get("reports_on"), ["exp40"])


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

    def test_report_artifact_projects_a_reports_on_edge_to_experiment(self):
        s = FakeSession()
        unresolved = publisher._project_reports_on(s, "g1", "report-exp40", [" exp40 "])
        self.assertFalse(unresolved)
        q, params = next((q, p) for q, p in s.calls if "REPORTS_ON" in q)
        self.assertIn("MERGE (x:Experiment {group_id:$g, id:$experiment_id})", q)
        self.assertIn("MERGE (a)-[r:REPORTS_ON]->(x)", q)
        self.assertIn("'asserted'", q)
        self.assertEqual(params["experiment_id"], "exp40")

    def test_standalone_asset_projects_as_navigable_artefato(self):
        s = FakeSession()
        publisher._project_artefato_asset(s, "g1", {
            "asset_slug": "demo-proto-abc123def456",
            "path": "blog/entries/demo.proto.abc123def456.html",
            "kind": "html",
            "sha256": "a" * 64,
            "skill": "prototype",
            "parent_slug": "demo",
            "media_type": "text/html",
            "role": "prototype",
        })
        text = " ".join(q for q, _ in s.calls)
        self.assertIn("MERGE (a:Artefato {group_id:$g, slug:$slug})", text)
        self.assertIn("a.kind='asset'", text)
        self.assertIn("HAS_ASSET", text)
        q, params = next((q, p) for q, p in s.calls if "HAS_ASSET" in q)
        self.assertEqual(params["parent"], "demo")
        self.assertEqual(params["slug"], "demo-proto-abc123def456")

    def test_valenced_para_and_reports_on_labels_join_the_destructive_rebuild(self):
        # a republish com bears_on corrigido não pode deixar aresta velha encalhada —
        # os labels entram no MESMO delete-then-readd por slug do project_artefato.
        import inspect
        src = re.sub(r'["\s]', "", inspect.getsource(publisher.project_artefato))
        m = re.search(r"-\[r:([A-Z_|]+)\]->\(\)", src)
        self.assertIsNotNone(m)
        rebuilt = set(m.group(1).split("|"))
        self.assertLessEqual(
            {"SUPPORTS", "REFUTES", "QUALIFIES", "INCONCLUSIVE", "PARA", "REPORTS_ON"},
            rebuilt)


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
        for t in ("supports", "refutes", "qualifies", "inconclusive", "para", "reports_on"):
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
                                "CITES", "SUPPORTS", "REFUTES", "REPORTS_ON"})


class ProducerSnippetsForwardBearsOnParaAndReportsOn(unittest.TestCase):
    """Codex adversarial #2 (meta-gate: SINAL) — o mint agora lê
    artefato.get('bears_on'/'para'/'reports_on');
    um producer que adote a chave com a lambda velha mintaria um proof que o publisher rejeita
    (digest mismatch). As lambdas de publish dos SKILL.md encaminham ambos — pin mecânico,
    espelho do pin de dispatch_id."""

    PRODUCERS = ["report", "research", "discovery", "map", "plan", "prototype", "mentor"]

    def test_every_publish_fn_forwards_bears_on_para_and_reports_on(self):
        for p in self.PRODUCERS:
            doc = (REPO / "skills" / p / "SKILL.md").read_text()
            i = doc.find("publish_fn=lambda art, proof")
            self.assertNotEqual(i, -1, f"{p}: publish_fn lambda not found")
            region = doc[i:i + 600]
            for arg in ("bears_on=art.get('bears_on')",
                        "para=art.get('para')",
                        "reports_on=art.get('reports_on')"):
                self.assertIn(arg, region,
                              f"{p}: publish_fn must forward {arg} (mint binds it — an "
                              "adopted key with the old lambda is a digest mismatch)")

    def test_report_publish_fn_forwards_experiment_curation(self):
        doc = (REPO / "skills" / "report" / "SKILL.md").read_text()
        i = doc.find("publish_fn=lambda art, proof")
        self.assertNotEqual(i, -1, "report: publish_fn lambda not found")
        region = doc[i:i + 800]
        self.assertIn("experiment_curation=art.get('experiment_curation')", region)


class OntologiaSchemaIsTheMeasurementInstrument(unittest.TestCase):
    """O schema declarativo que MEDE o diff do H-001: enums travados, alias-map episteme,
    os nós do Episteme do Roberto, e a leitura canônica explícita de Experiment."""

    @classmethod
    def setUpClass(cls):
        import yaml
        cls.schema = yaml.safe_load(
            (REPO / "cortex" / "schema" / "ontologia.yaml").read_text())

    def test_provenance_class_enum_is_locked(self):
        self.assertEqual(self.schema["schema_version"], 1)
        self.assertIn("content_hash", self.schema)
        self.assertEqual(self.schema["provenance_class"]["enum"],
                         ["computed", "asserted", "llm_judged", "extracted"])
        self.assertEqual(self.schema["provenance_class"]["rollup_eligible"], ["computed"])

    def test_schema_content_hash_matches_canonical_payload(self):
        data = dict(self.schema)
        got = data.pop("content_hash")
        blob = json.dumps(data, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        self.assertEqual(got, hashlib.sha256(blob).hexdigest())

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
        self.assertIn("REPORTS_ON", self.schema["edges"]["structural"])

    def test_roberto_episteme_nodes_are_unified_not_reserved(self):
        self.assertNotIn("reserved_nodes", self.schema)
        nodes = self.schema["nodes"]
        for node in ("pergunta", "hipotese", "modelagem", "experimento", "observation"):
            self.assertIn(node, nodes)
        self.assertEqual(nodes["hipotese"]["runtime"], "hypothesis")
        self.assertEqual(nodes["modelagem"]["runtime"], "arm")
        self.assertEqual(nodes["experimento"]["runtime"], "experiment")
        for node, episteme_name in {
            "observation": "observation",
            "experiment": "experimento",
            "arm": "modelagem",
        }.items():
            self.assertIn(node, nodes)
            self.assertEqual(nodes[node]["episteme"], episteme_name)
            self.assertEqual(nodes[node]["key"], "ulid")
        curated = nodes["experiment"]["curated_read"]
        self.assertEqual(curated["truth"], "experiment.curated")
        self.assertEqual(curated["read_order"],
                         ["canonical", "canonical_artifacts"])

    def test_hypothesis_and_parceiro_are_declared_nodes(self):
        self.assertIn("hypothesis", self.schema["nodes"])
        self.assertIn("parceiro", self.schema["nodes"])

    def test_rule_templates_register_the_episteme_and_gate_rulers(self):
        self.assertIn("delta_ci@1", self.schema["rule_templates"])
        self.assertIn("gate_score_delta@1", self.schema["rule_templates"])

    def test_episteme_payload_alias_bans_survive_the_merge(self):
        banned = self.schema["payload_aliases_banidos"]
        self.assertEqual(banned["hypothesis"], ["hipotese", "hyp"])
        self.assertIn("trial_id", banned["run"])

    def test_episteme_controlled_paths_survive_the_merge(self):
        paths = self.schema["controlled_paths"]["episteme"]
        self.assertEqual(paths["run_started"][0],
                         {"path": "payload.arm", "term": "arm"})
        self.assertEqual(paths["experiment_declared"][0],
                         {"path": "payload.arms[]", "term": "arm"})
        self.assertEqual(paths["experiment_concluded"][0],
                         {"path": "payload.bearings[].valence", "term": "valencia"})
        self.assertEqual(paths["review_approved"][0],
                         {"path": "payload.authority", "term": "authority"})


if __name__ == "__main__":
    unittest.main()
