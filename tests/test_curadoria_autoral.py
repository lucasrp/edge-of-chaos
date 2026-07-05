"""Curadoria autoral — a ADOÇÃO do ticket A: o produtor autora o juízo no publish.

Regra do operador (2026-07-05): `para` DEFAULT = SEMPRE o operador/mentee — todo artefato é
PARA alguém; na ausência de alvo explícito, o alvo é ele (nunca vazio). Um `para` explícito
(colega/cliente) sobrescreve.

Mecânica: o default resolve na COSTURA do evento (`eventlog.publish_artefato_atomic`, o padrão
`origin`: DERIVADO no seam, nunca arg de caller, FORA do digest — identidade do install, não
dado forjável de produtor). O evento fica honesto: `para` = só o autorado (digest-bound,
ticket A); `para_default` = o nome do mentee derivado quando o autorado é vazio. O nome vem de
`_identity.mentee()` (EDGE_MENTEE env → agent.yaml `mentee` → `repo_owner`) — nunca um literal.

Projeção: `_project_para_default` marca o :Artefato (prop `para_default`) e só cria a aresta
PARA quando a Entity do mentee JÁ está promovida (§6: promoção, nunca mintagem) — e NUNCA
retorna unresolved (fail-safe: o default não pode encalhar projection_complete=false em todo
artefato de um install cujo mentee ainda não foi promovido).

bears_on ausente = vazio honesto: nenhuma aresta valenciada, nunca fabricada.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO / "tools"))

import _identity  # noqa: E402
import close  # noqa: E402
import eventlog  # noqa: E402
import publisher  # noqa: E402


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


class MenteeIdentity(unittest.TestCase):
    """`_identity.mentee()` — o nome do operador/mentee do install, nunca um literal do
    genótipo: EDGE_MENTEE env → agent.yaml `mentee` → `repo_owner` → None (runtime degrade)."""

    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"EDGE_MENTEE": "opx"}):
            self.assertEqual(_identity.mentee(), "opx")

    def test_agent_yaml_mentee_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("mentee: fulano\nrepo_owner: outro\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EDGE_MENTEE", None)
                self.assertEqual(_identity.mentee(agent_yaml=ay), "fulano")

    def test_repo_owner_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("repo_owner: dono\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EDGE_MENTEE", None)
                self.assertEqual(_identity.mentee(agent_yaml=ay), "dono")

    def test_nothing_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "missing.yaml"
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EDGE_MENTEE", None)
                self.assertIsNone(_identity.mentee(agent_yaml=ay))

    def test_blank_and_nonstring_values_are_skipped(self):
        # codex adversarial #2 (SINAL): the mechanical default must be as normalized as the
        # authored para — a blank env / non-string yaml value never rides into event or graph.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("mentee: 123\nrepo_owner: '  dono  '\n")
            with mock.patch.dict(os.environ, {"EDGE_MENTEE": "  "}):
                self.assertEqual(_identity.mentee(agent_yaml=ay), "dono")
            ay.write_text("mentee: 123\nrepo_owner: 42\n")
            with mock.patch.dict(os.environ, {"EDGE_MENTEE": " "}):
                self.assertIsNone(_identity.mentee(agent_yaml=ay))


class ParaDefaultRidesTheEventSeam(unittest.TestCase):
    """O default resolve em publish_artefato_atomic (padrão origin: derivado, nunca caller
    arg). Evento honesto: para = autorado; para_default = mentee só quando o autorado é vazio."""

    def test_empty_para_gains_the_mentee_default(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            ev, _ = eventlog.publish_artefato_atomic("a", "intent", log=_log(tmp))
            self.assertEqual(ev["payload"]["para"], [])
            self.assertEqual(ev["payload"]["para_default"], "op")

    def test_blank_only_para_still_defaults(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            ev, _ = eventlog.publish_artefato_atomic("a", "intent", log=_log(tmp),
                                                     para=[" ", 42])
            self.assertEqual(ev["payload"]["para"], [])
            self.assertEqual(ev["payload"]["para_default"], "op")

    def test_explicit_para_is_preserved_no_default(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            ev, _ = eventlog.publish_artefato_atomic("a", "intent", log=_log(tmp),
                                                     para=["Julio"])
            self.assertEqual(ev["payload"]["para"], ["Julio"])
            self.assertIsNone(ev["payload"]["para_default"])

    def test_unresolvable_mentee_stays_honestly_none(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(_identity, "mentee", return_value=None):
            ev, _ = eventlog.publish_artefato_atomic("a", "intent", log=_log(tmp))
            self.assertIsNone(ev["payload"]["para_default"])

    def test_fold_carries_para_default_for_replay(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            log = _log(tmp)
            eventlog.publish_artefato_atomic("a", "intent", log=log)
            item = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item["para_default"], "op")

    def test_legacy_event_folds_none(self):
        # evento pré-adoção (sem o campo) folda None — forward-only, sem backfill.
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.append("artefato.published", "artefato:old",
                            {"slug": "old"}, log=log)
            eventlog.append("intent.kernel", "artefato:old",
                            {"slug": "old", "intent": "i"}, log=log)
            item = eventlog.corpus_at(log=log)[0]
            self.assertIsNone(item.get("para_default"))


class PublishForwardsParaDefaultToProjection(unittest.TestCase):
    """publisher.publish lê para_default DO EVENTO retornado (um único ponto de derivação; o
    log é a verdade) e o entrega à projeção. O default NUNCA entra no digest: o publish com
    para=None passa verify_proof intacto (o proof foi mintado sem o default)."""

    def test_publish_with_no_para_projects_the_default(self):
        spec = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "para-default rides the seam."}]}]}
        intent = "open: x; bet: y"
        verdicts = [
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.FEYNMAN_REVIEWER_ID},
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.REGULAR_REVIEWER_ID},
        ]
        proof = close._mint_proof(verdicts, slug="pd", spec=spec, intent=intent,
                                  cites=[], proposes=[], skill="report")
        seen = {}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            log = _log(tmp)
            eventlog.dispatch_open(log=log)
            publisher.publish("pd", spec, intent, skill="report", verdict=proof,
                              log=log, blog_dir=tmp, embed_fn=lambda t: [1.0],
                              project_fn=lambda *a, **k: seen.update(k))
            ev = eventlog.read(types=["artefato.published"], log=log)[-1]
            self.assertEqual(ev["payload"]["para_default"], "op")
            self.assertEqual(seen.get("para_default"), "op")
            self.assertEqual(seen.get("para"), [])

    def test_explicit_para_projects_no_default(self):
        spec = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "explicit para overrides."}]}]}
        intent = "open: x; bet: y"
        verdicts = [
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.FEYNMAN_REVIEWER_ID},
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.REGULAR_REVIEWER_ID},
        ]
        proof = close._mint_proof(verdicts, slug="pe", spec=spec, intent=intent,
                                  cites=[], proposes=[], skill="report", para=["Julio"])
        seen = {}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            log = _log(tmp)
            eventlog.dispatch_open(log=log)
            publisher.publish("pe", spec, intent, skill="report", verdict=proof,
                              para=["Julio"], log=log, blog_dir=tmp,
                              embed_fn=lambda t: [1.0],
                              project_fn=lambda *a, **k: seen.update(k))
            self.assertEqual(seen.get("para"), ["Julio"])
            self.assertIsNone(seen.get("para_default"))

    def test_reproject_replays_para_default(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EDGE_MENTEE": "op"}):
            log = _log(tmp)
            eventlog.dispatch_open(log=log)
            eventlog.publish_artefato_atomic("rp", "intent", log=log)
            seen = {}
            publisher.reproject_graph(log=log,
                                      project_fn=lambda *a, **k: seen.update(k),
                                      present_slugs=lambda: {}, backbone_fn=None)
            self.assertEqual(seen.get("para_default"), "op")


class ProjectionOfTheDefaultIsFailSafe(unittest.TestCase):
    """_project_para_default: prop no :Artefato SEMPRE; aresta PARA SÓ quando a Entity do
    mentee já está promovida (§6 — o endpoint é o parceiro PROMOVIDO; o default nunca minta
    nem promove). NUNCA unresolved: retorna None, jamais encalha projection_complete."""

    def test_marks_the_prop_and_guards_the_edge_by_promotion(self):
        s = FakeSession()
        self.assertIsNone(publisher._project_para_default(s, "g", "slug", "op"))
        prop_sets = [q for q, _ in s.calls if "para_default" in q and "SET" in q]
        self.assertTrue(prop_sets, "the :Artefato must be marked para-o-mentee (prop)")
        edges = [q for q, _ in s.calls if "PARA" in q]
        self.assertTrue(edges, "the PARA edge MERGE must be attempted")
        self.assertTrue(all("parceiro:true" in q for q in edges),
                        "the default edge targets ONLY an already-promoted Entity (§6)")
        self.assertTrue(all("MERGE (e" not in q for q in edges),
                        "the default never mints the parceiro node")

    def test_no_default_clears_a_stale_mark(self):
        # republish que agora AUTORA para → o default anterior não pode sobrar como marca.
        s = FakeSession()
        publisher._project_para_default(s, "g", "slug", None)
        self.assertTrue(any("REMOVE" in q and "para_default" in q for q, _ in s.calls))
        self.assertFalse(any("PARA" in q for q, _ in s.calls))


class PromotionBackfillsTheDefaultEdge(unittest.TestCase):
    """codex adversarial #1 (SINAL): publish-before-promotion must SELF-HEAL — the default is
    fail-safe (never blocks completion), so the backbone (`_project_parceiros`, run every
    canonical publish + sweep) backfills a.para_default -> PARA once the mentee's promotion
    lands, the same pattern as the SERVES backfill for pre-Objective artefatos."""

    def test_parceiro_projection_backfills_para_default_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = _log(tmp)
            eventlog.promote_parceiro("dono", "equipe", by="operador", log=log)
            s = FakeSession()
            publisher._project_parceiros(s, "g", log)
            backfills = [(q, p) for q, p in s.calls
                         if "para_default" in q and "PARA" in q and "MERGE (a)-[r:PARA]" in q]
            self.assertTrue(backfills, "promotion must backfill the pending default PARA edges")
            q, p = backfills[0]
            self.assertIn("parceiro:true", q)
            self.assertEqual(p.get("name"), "dono")


class AbsentBearsOnIsHonestlyEmpty(unittest.TestCase):
    """bears_on ausente = vazio honesto: nenhuma aresta valenciada projetada, nada unresolved."""

    def test_empty_bears_on_projects_nothing(self):
        s = FakeSession()
        self.assertFalse(publisher._project_bears_on(s, "g", "slug", []))
        self.assertEqual(s.calls, [])

    def test_none_bears_on_projects_nothing(self):
        s = FakeSession()
        self.assertFalse(publisher._project_bears_on(s, "g", "slug", None))
        self.assertEqual(s.calls, [])


class SkillsInstructTheAuthoring(unittest.TestCase):
    """A adoção nos SKILLs: cada produtor é instruído a AUTORAR bears_on/para no passo de
    consolidação (pin mecânico, espelho do pin de ticket A: chave sem instrução = costura
    turnkey sem adoção)."""

    PRODUCERS = ["report", "research", "discovery", "map", "plan", "prototype", "grill"]

    def test_every_producer_names_the_authored_judgement(self):
        for p in self.PRODUCERS:
            doc = (REPO / "skills" / p / "SKILL.md").read_text()
            for key in ("bears_on", "hypotheses_at"):
                self.assertIn(key, doc,
                              f"{p}: SKILL.md must instruct authoring {key} "
                              "(curadoria no contexto quente)")

    def test_pipeline_carries_the_goal_level_rule(self):
        doc = (REPO / "skills" / "_shared" / "pipeline.md").read_text()
        for key in ("bears_on", "hypotheses_at", "para"):
            self.assertIn(key, doc)


if __name__ == "__main__":
    unittest.main()
