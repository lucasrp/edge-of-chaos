"""Ticket 05 — the 3-act flow (tronco → PROPOSTA → N artefato-agents) and its schema legs.

The spec (docs/agencia/implementacao/05-fluxo-3atos-multiartefato.md) kills the monolith
(1 grounding → close único). What is mechanically testable here:

  * ORIGIN — the artefato carries where it came from (`origin: user_requested | beat`, DO
    dispatch): predispatch stamps it on `dispatch.open`, `eventlog.dispatch_origin` folds it
    by dispatch_id (default `beat` — a beat artefato is indistinguishable from noise; the
    user's request is the gradient), and the publisher persists it on `artefato.published`.
  * SINGLE FILE is the ONE hard rule left — JS/image liberated in ANY genus: the standalone
    single-file seam (`publisher.publish_prototype_page`) is generalized roster-wide (the
    04-C exception becomes the rule); out-of-roster still refused.
  * LAZER — the pure-leisure skill returns (distinct from discovery): registered by
    declaration (roster + descriptor + SKILL.md), theme from agent.yaml seeds or, na
    omissão, pura criatividade; exemplar = the edge-of-chaos netlify blog.
  * The 3-act prose — beat SKILL carries the tronco (grounding inicial → PROPOSTA gated),
    the branches (um agente por artefato, rounds próprios, termina POR FORA), and the
    pipeline carries the consolidação-do-grafo phase + saiba-mais + the origin hierarchy;
    the scaffold tells the writer "seja Feynman nesse sentido".
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import eventlog  # noqa: E402
import predispatch  # noqa: E402
import producer_descriptor as pd  # noqa: E402
import publisher  # noqa: E402
from _blog_env import guard_blog_env


# --- origin: user_requested | beat -----------------------------------------------------------

class DispatchStampCarriesTheOrigin(unittest.TestCase):
    """predispatch stamps `origin` on dispatch.open — user_requested ≫ beat (the hierarchy of
    ORIGEM): a user-requested artefato is first-order signal; a beat one is exploration."""

    def _run(self, tmp, **kw):
        log = Path(tmp) / "log.jsonl"
        predispatch.run(ready_fn=lambda: None, drain_fn=lambda: None, 
            sweep_fn=lambda: 0, briefing_fn=lambda: "briefing",
            recall_fn=lambda: "recall", harvest_fn=lambda: 0,
            probe_fn=lambda spec: None, log=log, dispatch_id="d-1", **kw)
        evs = eventlog.read(types=["dispatch.open"], log=log)
        return evs[-1]["payload"]

    def test_default_origin_is_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(tmp)["origin"], "beat")

    def test_user_requested_origin_is_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._run(tmp, origin="user_requested")
            self.assertEqual(payload["origin"], "user_requested")

    def test_cli_exposes_the_origin_flag(self):
        import argparse
        # --origin is declared with the two legal values only (a typo fails loud at the CLI)
        with self.assertRaises(SystemExit):
            predispatch.main(["--origin", "typo", "--theme", "t"])  # invalid choice


class DispatchOriginFoldsFromTheLog(unittest.TestCase):
    """`eventlog.dispatch_origin(dispatch_id)` — the fold the publisher reads. Default `beat`:
    a legacy stamp (no origin key), an unknown id, or a hollow id all fold to `beat` (never a
    fabricated user_requested)."""

    def test_user_requested_folds_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-9", "origin": "user_requested"}, log=log)
            self.assertEqual(eventlog.dispatch_origin("d-9", log=log), "user_requested")

    def test_legacy_stamp_without_origin_folds_to_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-9"}, log=log)
            self.assertEqual(eventlog.dispatch_origin("d-9", log=log), "beat")

    def test_unknown_or_hollow_id_folds_to_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self.assertEqual(eventlog.dispatch_origin("never-minted", log=log), "beat")
            self.assertEqual(eventlog.dispatch_origin(None, log=log), "beat")

    def test_garbage_origin_value_folds_to_beat(self):
        # only the two legal values ride; junk in a payload never propagates
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-9", "origin": "hacked"}, log=log)
            self.assertEqual(eventlog.dispatch_origin("d-9", log=log), "beat")


def _passing_proof(slug, spec, intent, *, cites=None, dispatch_id=None, skill="report"):
    verdicts = [
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.FEYNMAN_REVIEWER_ID},
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.REGULAR_REVIEWER_ID},
    ]
    return close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                             cites=cites or [], proposes=[], skill=skill,
                             dispatch_id=dispatch_id)


def _spec():
    return {"sections": [{"title": "Body", "blocks": [
        {"type": "paragraph", "text": "origin rides the published event."}]}]}


class PublishPersistsTheOrigin(unittest.TestCase):
    """The artefato CARRIES its origin (do dispatch): publish resolves it from the minting
    dispatch.open and persists it on the `artefato.published` payload — so everything that
    learns from artefatos can weigh user_requested above beat."""

    def _publish(self, tmp, open_payload):
        log = Path(tmp) / "log.jsonl"
        eventlog.dispatch_open(open_payload, log=log)
        slug, intent = "origin-rides", "open: x; bet: y"
        did = open_payload.get("dispatch_id")
        # legacy-publish vehicle: `report` moved to the rite and is refused by publisher.publish;
        # origin persistence is skill-agnostic, so drive a still-legacy producer here.
        publisher.publish(
            slug, _spec(), intent, skill="prototype", date="2026-07-05",
            log=log, blog_dir=tmp, embed_fn=lambda t: [1.0, 0.0], project_fn=None,
            dispatch_id=did,
            verdict=_passing_proof(slug, _spec(), intent, dispatch_id=did, skill="prototype"))
        evs = eventlog.read(types=["artefato.published"], log=log)
        return evs[-1]["payload"]

    def test_user_requested_dispatch_publishes_a_user_requested_artefato(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._publish(
                tmp, {"dispatch_id": "test-or1", "origin": "user_requested"})
            self.assertEqual(payload["origin"], "user_requested")
            # the fold carries it too (codex adversarial #4, SINAL): read models — corpus,
            # graph projection — can weigh user_requested ≫ beat only if the fold exposes it.
            log = Path(tmp) / "log.jsonl"
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["origin"], "user_requested")

    def test_beat_dispatch_publishes_a_beat_artefato(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._publish(tmp, {"dispatch_id": "test-or2"})
            self.assertEqual(payload["origin"], "beat")

    def test_legacy_idless_publish_defaults_to_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._publish(tmp, {})
            self.assertEqual(payload["origin"], "beat")

    def test_origin_cannot_be_fabricated_at_the_atomic_seam(self):
        # codex meta-gate #5 (SINAL): the atomic seam DERIVES origin from the minting
        # dispatch.open — there is no caller channel to claim user_requested on a beat wake.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "test-fab"}, log=log)  # a BEAT wake
            with self.assertRaises(TypeError):  # no origin kwarg exists to fabricate through
                eventlog.publish_artefato_atomic(
                    "fab", "why", log=log, dispatch_id="test-fab", origin="user_requested")
            evs = eventlog.publish_artefato_atomic(
                "fab", "why", log=log, dispatch_id="test-fab")
            self.assertEqual(evs[0]["payload"]["origin"], "beat")  # derived, not claimed


class ProtoPagesAreServedUnderARestrictiveCSP(unittest.TestCase):
    """codex meta-gate #3 (SINAL parcial): roster-wide authored JS is operator-ordered; the real
    gap is serving `.proto.` pages same-origin with the blog's write APIs. The serve route caps
    them with a per-file CSP — inline script/style/data-img legal (the genus), all NETWORK denied
    (connect/form), so the page cannot reach /e/<slug>/comment|vote nor exfiltrate."""

    def test_proto_page_gets_the_csp_and_normal_entries_do_not(self):
        import importlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = root / "entries"
            entries.mkdir()
            (entries / "demo.proto.abc123def456.html").write_text(PAGE)
            (entries / "normal-entry.html").write_text("<html><body>ok</body></html>")
            import os
            guard_blog_env(self)
            os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
            os.environ["EDGE_BLOG_STATIC"] = str(root)
            os.environ["EDGE_BLOG_LOG"] = str(root / "log.jsonl")
            sys.path.insert(0, str(REPO / "blog"))
            import server
            importlib.reload(server)
            client = server.app.test_client()
            proto = client.get("/e/demo.proto.abc123def456.html")
            self.assertEqual(proto.status_code, 200)
            csp = proto.headers.get("Content-Security-Policy", "")
            self.assertIn("connect-src 'none'", csp)
            self.assertIn("form-action 'none'", csp)
            self.assertIn("script-src 'unsafe-inline'", csp)   # the genus stays alive
            normal = client.get("/e/normal-entry.html")
            self.assertEqual(normal.status_code, 200)
            self.assertNotIn("connect-src 'none'",
                             normal.headers.get("Content-Security-Policy", ""))


# --- single-file is the ONE hard rule — the seam goes roster-wide ----------------------------

PAGE = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>t</title></head>"
    "<body><img src='data:image/gif;base64,R0lGOD'>"
    "<script>document.title='alive';</script></body></html>"
)


class SingleFileSeamIsRosterWide(unittest.TestCase):
    """Operador: JS e imagem LIBERADOS em qualquer artefato — o 04-C vira a regra geral. The
    standalone single-file seam accepts EVERY roster genus; the single hard rule that stays is
    SINGLE FILE (full document, zero external resource loads). Out-of-roster still refused."""

    def test_every_roster_genus_can_publish_an_intact_single_file_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            for skill in publisher.PRODUCER_ROSTER:
                out = publisher.publish_prototype_page(
                    f"page-{skill}", PAGE, skill=skill, blog_dir=tmp)
                self.assertEqual(out.read_text(), PAGE)  # script + data-URI image intact

    def test_out_of_roster_is_still_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for skill in ("", "unknown", None):
                with self.assertRaises(ValueError):
                    publisher.publish_prototype_page("x", PAGE, skill=skill, blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])


# --- lazer: the pure-leisure skill returns ---------------------------------------------------

class LazerIsAFirstClassGenus(unittest.TestCase):
    """LAZER = skill NOVA (operador) — distinct from discovery (serendipidade dirigida): pure
    leisure, free exploration. Theme from agent.yaml seeds (fenótipo) or, na omissão, pura
    criatividade do agente. Exemplar da forma: the edge-of-chaos netlify blog."""

    @classmethod
    def setUpClass(cls):
        cls.skill = REPO / "skills" / "lazer" / "SKILL.md"

    def test_lazer_is_in_the_producer_roster(self):
        self.assertIn("lazer", publisher.PRODUCER_ROSTER)

    def test_lazer_declares_a_descriptor(self):
        self.assertEqual(pd.require_descriptor("lazer"), {"require": []})

    def test_skill_doc_carries_the_contract(self):
        self.assertTrue(self.skill.exists(), f"missing {self.skill}")
        low = self.skill.read_text(encoding="utf-8").lower()
        for token in ("lazer", "agent.yaml", "seeds", "criatividade",
                      "edge-of-chaos.netlify.app", "discovery"):
            self.assertIn(token, low, f"lazer SKILL missing token: {token!r}")
        # it exits through the same shared close as every producer (ADR-0008)
        self.assertIn("skills/_shared/pipeline.md", low)

    def test_lazer_holds_the_cortex_door_like_every_producer(self):
        # codex adversarial #8 (SINAL): a producer outside GRANTED_SUBJECTS is second-class at
        # runtime (the allowlist strips its recall/consolidação door by construction).
        import cortex_config
        import cortex_mcp
        self.assertIn("lazer", cortex_config.GRANTED_SUBJECTS)
        self.assertIn("lazer", cortex_mcp.GRANTED_SUBJECTS)


# --- the 3-act prose: tronco + galhos + consolidação + saiba-mais + Feynman ------------------

class BeatSkillCarriesTheThreeActTronco(unittest.TestCase):
    """Ato-1 (escolher): grounding INICIAL → PROPOSTA explícita (QUAIS artefatos 1..N, por quê
    — os gates de plano B.4 —, cada um com seu ângulo). Galhos: um agente por artefato, rounds
    PRÓPRIOS de grounding, loop localizado que termina POR FORA."""

    @classmethod
    def setUpClass(cls):
        cls.low = (REPO / "skills" / "beat" / "SKILL.md").read_text(encoding="utf-8").lower()

    def test_tronco_grounding_inicial_and_proposta(self):
        for token in ("grounding inicial", "proposta"):
            self.assertIn(token, self.low)

    def test_branches_one_agent_per_artefato_with_own_rounds(self):
        for token in ("um agente por artefato", "rounds", "por fora"):
            self.assertIn(token, self.low)

    def test_origin_hierarchy_is_named(self):
        self.assertIn("user_requested", self.low)


class PipelineCarriesConsolidationAndSaibaMais(unittest.TestCase):
    """The consolidação-do-grafo phase (operador: possivelmente a função MAIS IMPORTANTE do
    artefato) + links liberados / saiba-mais + single-file as the one hard rule."""

    @classmethod
    def setUpClass(cls):
        cls.low = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8").lower()

    def test_consolidation_phase_is_first_class(self):
        for token in ("consolida", "asserted", "cites"):
            self.assertIn(token, self.low)

    def test_saiba_mais_and_liberated_links(self):
        self.assertIn("saiba mais", self.low)

    def test_single_file_is_the_one_hard_rule(self):
        self.assertIn("single file", self.low.replace("single-file", "single file"))

    def test_origin_hierarchy(self):
        self.assertIn("user_requested", self.low)


class ScaffoldTellsTheWriterToBeFeynman(unittest.TestCase):
    """Operador: "seja Feynman nesse sentido" no escritor — the NAME-as-pointer (P1: the
    trained attractor beats pages of rule), fine-scoped; production gates stay impersonal."""

    def test_seja_feynman_nesse_sentido(self):
        low = (REPO / "skills" / "_shared" / "scaffold.md").read_text(encoding="utf-8").lower()
        self.assertIn("seja feynman nesse sentido", low)


if __name__ == "__main__":
    unittest.main(verbosity=2)
