"""The rito runtime contract — the experiment's rite promoted to the genotype's production path.

The operator's law: the rite is the WHOLE causal execution, grounding-1 through publication of
the rendered page. We never gate on the artifact's appearance; we prove EXECUTION — and the
approved renderer + its output hash are PINNED AS A STAGE of the rite (pinning the pipeline,
not scoring the artifact).

Under test:
- `rito.run_rito` — sequences stages 1–11 (10 cognitive stages + publication), seals a
  manifest of begin/finish/fail receipts with hashes, renders via the pinned renderer,
  terminates in publication. A run that didn't publish didn't finish the rite.
- `rito.verify_rito` — the DETECTOR: given a production run's outputs (run dir + event log +
  blog dir), answers "did this traverse the experiment's rite, with the experiment's form?".
  It must FAIL against the legacy publisher path.
- `render.render_markdown_page` / `render.markdown_page_bytes` — the approved renderer
  promoted from the exp072 post-gate-grounding arm, renderer id pinned.
- `publisher.publish_rito` — writes the EXACT reviewed bytes; recomputes the render and
  REFUSES a hash mismatch; commits the atomic event bound to the manifest.
"""
import hashlib
import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import publisher  # noqa: E402
import render  # noqa: E402
import rito  # noqa: E402
import yaml_rite  # noqa: E402

SLUG = "exp-teste-rito"
INTENT = "provar que o rito inteiro roda, do dossier a publicacao"

APPROVED_GENERATOR = Path(
    "/home/vboxuser/edge/drafts/exp072-report-quality/post-gate-grounding-arm/"
    "generate_post_gate_grounding_arm.py")


def _approved_generator_present():
    """The pinned generator lives in ONE operator's draft folder — it is not part of the genotype.
    Probing it must never decide the fate of this module: on a host where the path's parent is
    another user's home, `Path.is_file()` RAISES PermissionError (py<3.13) at import time and the
    WHOLE module fails to load, taking every other rito test — and tests.test_publisher, which
    drives `_green_run` from here — down with it. Any OSError means "not on this host" → skip."""
    try:
        return APPROVED_GENERATOR.is_file()
    except OSError:
        return False

YAML_AUTHORIAL_DRAFT = """intent: "open: o buscador sem indice; bet: o indice muda o placar"
cites:
  - ref: exp072
    kind: atividade
    snippet: "29 vitorias com o indice"
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: "O relato anterior nomeou o buraco do indice; este deriva o placar."
  - type: comparison
    before:
      title: raw
      bullets: ["8", "sem estrutura"]
    after:
      title: indice
      bullets: ["29", "a rodada 3 mostra o mecanismo"]
  - type: gap-marker
    text: "unknown: whether the next round repeats the lift"
"""
YAML_PROVISIONAL = """intent: "open: o buscador sem indice; bet: o indice muda o placar"
cites:
  - ref: exp072
    kind: atividade
    snippet: "29 vitorias com o indice"
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: "O relato anterior nomeou o buraco do indice; este deriva o placar."
  - type: comparison
    before:
      title: raw
      bullets: ["8", "sem estrutura"]
    after:
      title: indice
      bullets: ["29", "versao revisada: a rodada 3 mostra o mecanismo"]
  - type: gap-marker
    text: "unknown: whether the next round repeats the lift"
"""
YAML_AUTHOR_CORRECTION = """intent: "open: o buscador sem indice; bet: o indice muda o placar"
cites:
  - ref: exp072
    kind: atividade
    snippet: "29 vitorias com o indice"
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: "O relato anterior nomeou o buraco do indice; este deriva o placar."
  - type: comparison
    before:
      title: raw
      bullets: ["8", "sem estrutura"]
    after:
      title: indice
      bullets: ["29", "versao final auditada. A rodada 3 mostra o mecanismo."]
  - type: gap-marker
    text: "unknown: whether the next round repeats the lift"
"""
YAML_LEAKY_CORRECTION = """intent: "open: o buscador sem indice; bet: o indice muda o placar"
cites:
  - ref: exp072
    kind: atividade
    snippet: "29 vitorias com o indice"
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: "Neste rascunho eu explico o mecanismo da rodada 3."
  - type: comparison
    before:
      title: raw
      bullets: ["8", "sem estrutura"]
    after:
      title: indice
      bullets: ["29", "a rodada 3 mostra o mecanismo"]
  - type: gap-marker
    text: "unknown: whether the next round repeats the lift"
"""
YAML_CLEAN_CLEANUP = """intent: "open: o buscador sem indice; bet: o indice muda o placar"
cites:
  - ref: exp072
    kind: atividade
    snippet: "29 vitorias com o indice"
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: "Aqui eu explico o mecanismo da rodada 3."
  - type: comparison
    before:
      title: raw
      bullets: ["8", "sem estrutura"]
    after:
      title: indice
      bullets: ["29", "a rodada 3 mostra o mecanismo"]
  - type: gap-marker
    text: "unknown: whether the next round repeats the lift"
"""

# Canned cognitive outputs — scan-clean (no draft/grounding/prompt/harness vocabulary), so the
# deterministic treatment gates pass and treatment_cleanup takes the deterministic-copy branch.
# Default canned outputs are Markdown (3aeb049 producer). YAML_* fixtures
# remain for the leftover-YAML HTML-probe tests (#647 / #585).
CANNED = {
    "first_authorial_draft": (
        "# Relatorio exp-teste\n\nA pergunta viva: o buscador melhora com o indice?\n\n"
        "- fato: 29 vitorias\n- inferencia: o indice ajuda\n\n"
        "| arm | placar |\n|---|---|\n| raw | 8 |\n| indice | 29 |"),
    "gap_critique": "# Lacunas\n\nFaltou o caso concreto da rodada 3.",
    "grounding2_targeted": "# Memo dirigido\n\nEvidencia adicional sobre a rodada 3.",
    "provisional_rewrite": (
        "# Relatorio exp-teste\n\nVersao revisada: a rodada 3 mostra o mecanismo."),
    "fact_audit": "# Fact audit\n\n## Verdict\nPASS\n\n## Claim ledger\ntudo sustentado.",
    "author_correction": (
        "# Relatorio exp-teste\n\nVersao final auditada. A rodada 3 mostra o mecanismo.\n\n"
        "> o indice vence onde a estrutura importa."),
    "final_review": (
        "ACCEPTANCE: PASS\nUNSUPPORTED_CLAIMS: 0\nTREATMENT_LEAK: NO\n\n"
        "Revisao qualitativa: util por si so."),
}

YAML_CANNED = {
    "first_authorial_draft": YAML_AUTHORIAL_DRAFT,
    "gap_critique": "# Lacunas\n\nFaltou o caso concreto da rodada 3.",
    "grounding2_targeted": "# Memo dirigido\n\nEvidencia adicional sobre a rodada 3.",
    "provisional_rewrite": YAML_PROVISIONAL,
    "fact_audit": "# Fact audit\n\n## Verdict\nPASS\n\n## Claim ledger\ntudo sustentado.",
    "author_correction": YAML_AUTHOR_CORRECTION,
    "final_review": (
        "ACCEPTANCE: PASS\nUNSUPPORTED_CLAIMS: 0\nTREATMENT_LEAK: NO\n\n"
        "Revisao qualitativa: util por si so."),
}

LLM_ORDER = ["first_authorial_draft", "gap_critique", "grounding2_targeted",
             "provisional_rewrite", "fact_audit", "author_correction", "final_review"]


def _prompts():
    """The producer's cognitive inputs — prose-owned; the runtime never authors these."""
    def mk(stage):
        return lambda outputs: f"[{stage}] escreva a partir de: {sorted(outputs)}"
    stages = LLM_ORDER + ["treatment_cleanup"]
    return {stage: mk(stage) for stage in stages}


def _complete_fn(canned, order):
    """Fake transport: returns the canned output for each LLM stage in rite order."""
    queue = [canned[name] for name in order]

    def complete(route, prompt, max_tokens):
        if not queue:
            raise RuntimeError("transport exhausted: rite asked for more stages than canned")
        return queue.pop(0)
    return complete


def _stamp_wake(log):
    did = eventlog.test_dispatch_id()
    eventlog.dispatch_open({"dispatch_id": did}, log=log)
    return did


def _green_run(tmp, canned=None, order=None, publish_fn=rito.DEFAULT_PUBLISH,
               publish_meta=None):
    """Run the full rite offline into tmp; returns (manifest, run_dir, log, blog_dir)."""
    tmp = Path(tmp)
    log, blog, run_dir = tmp / "log.jsonl", tmp / "blog", tmp / "run"
    did = _stamp_wake(log)
    manifest = rito.run_rito(
        SLUG,
        run_dir=run_dir,
        grounding1_fn=lambda: "# Dossier factual\n\nFatos: 29-8-3 em 40 rodadas.",
        prompts=_prompts(),
        complete_fn=_complete_fn(canned or CANNED, order or LLM_ORDER),
        intent=INTENT,
        skill="report",
        dispatch_id=did,
        log=log,
        blog_dir=blog,
        publish_fn=publish_fn,
        publish_meta=publish_meta,
    )
    return manifest, run_dir, log, blog


def _legacy_outputs(tmp):
    """Reproduce what the CURRENT legacy path leaves behind: a structured-spec page through the
    legacy `_page` shell + base.css, and an `artefato.published` event with a legacy spec.
    No rite run dir, no manifest, no sealed stages."""
    tmp = Path(tmp)
    log, blog, run_dir = tmp / "log.jsonl", tmp / "blog", tmp / "legacy-run"
    run_dir.mkdir(parents=True)
    spec = {"sections": [{"title": "Resultado", "blocks": [
        {"type": "paragraph", "text": "O indice venceu por 29 a 8."}]}]}
    did = _stamp_wake(log)
    # fabricate the legacy-shaped event (report via the direct atomic commit) the detector must
    # still REJECT — the migrated-producer guard on the primitive is bypassed here with the
    # rite-authorized flag purely to RE-CREATE the pre-rite shape for the detector to catch.
    eventlog.publish_artefato_atomic(
        SLUG, INTENT, spec=spec, skill="report", _rite_authorized=True, log=log,
        dispatch_id=did)
    page = publisher._page(
        SLUG, "<p>O indice venceu por 29 a 8.</p>", skill="report",
        date="2026-07-10", css=publisher.BASE_CSS.read_text())
    blog.mkdir(parents=True)
    (blog / f"{SLUG}.html").write_text(page)
    return run_dir, log, blog


class StageTableTest(unittest.TestCase):
    def test_stage_table_is_the_experiments_causal_order_plus_publication(self):
        self.assertEqual(
            [name for _, name, _, _, _ in rito.STAGES],
            ["grounding1_dossier", "first_authorial_draft", "gap_critique",
             "grounding2_targeted", "provisional_rewrite", "fact_audit",
             "author_correction", "treatment_cleanup", "final_html", "final_review",
             "publication"])

    def test_author_and_reviewer_routes_are_the_experiments(self):
        routes = {name: route for _, name, _, route, _ in rito.STAGES}
        self.assertEqual(routes["first_authorial_draft"], "chat")
        self.assertEqual(routes["gap_critique"], "review")
        self.assertEqual(routes["grounding2_targeted"], "review")
        self.assertEqual(routes["provisional_rewrite"], "chat")
        self.assertEqual(routes["fact_audit"], "review")
        self.assertEqual(routes["author_correction"], "chat")
        self.assertEqual(routes["treatment_cleanup"], "chat")
        self.assertEqual(routes["final_review"], "review")
        self.assertIsNone(routes["final_html"])
        self.assertIsNone(routes["publication"])


class RendererPromotionTest(unittest.TestCase):
    SAMPLE = ("# Titulo\n\nParagrafo com `code`, **bold** e "
              "[link](https://example.com).\n\n- item um\n- item dois\n\n"
              "| a | b |\n|---|---|\n| 1 | 2 |\n\n> uma citacao\n\n## Secao\n\ntexto.")

    def test_renderer_id_is_pinned(self):
        self.assertEqual(render.RENDERER_ID, "exp072-neutral-markdown/v2")

    @unittest.skipUnless(_approved_generator_present(), "approved generator not on this host")
    def test_promoted_renderer_keeps_the_approved_sample_body(self):
        spec = importlib.util.spec_from_file_location("approved_gen", APPROVED_GENERATOR)
        approved = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(approved)
        ours = render.render_markdown_page(self.SAMPLE, "Titulo")
        theirs = approved.render_markdown(self.SAMPLE, "Titulo")

        def _main(page):
            return page.split("<main>", 1)[1].split("</main>", 1)[0]

        self.assertEqual(_main(ours), _main(theirs))

    def test_markdown_page_bytes_is_the_single_byte_seam(self):
        data = render.markdown_page_bytes(self.SAMPLE)
        self.assertIsInstance(data, bytes)
        self.assertTrue(data.endswith(b"\n"))
        # deterministic: same markdown, same bytes — the pin the detector hashes against
        self.assertEqual(data, render.markdown_page_bytes(self.SAMPLE))


class DetectorAgainstLegacyTest(unittest.TestCase):
    def test_detector_rejects_the_legacy_publish_path(self):
        """THE red-line test: the current legacy path (structured spec → _page shell →
        publish event) must NOT pass as the rite."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, log, blog = _legacy_outputs(tmp)
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("manifest-missing", verdict["failures"])


class FullRiteTest(unittest.TestCase):
    def test_full_rite_passes_the_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = _green_run(tmp)
            self.assertEqual(manifest["status"], "completed")
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertEqual(verdict["failures"], [])
            self.assertTrue(verdict["pass"])

    def test_published_page_is_the_pinned_render_of_the_sealed_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            sealed_md = (run_dir / "08_BLIND_SAFE_FINAL.md").read_text()
            expected = yaml_rite.page_bytes(sealed_md)
            self.assertEqual((blog / f"{SLUG}.html").read_bytes(), expected)
            self.assertEqual((run_dir / "09_FINAL.html").read_bytes(), expected)

    def test_publication_event_is_bound_to_manifest_and_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = _green_run(tmp)
            evs = [e for e in eventlog.read(log=log) if e["type"] == "artefato.published"]
            self.assertEqual(len(evs), 1)
            spec = evs[0]["payload"]["spec"]
            self.assertEqual(spec["format"], "edge-markdown/v1")
            self.assertEqual(spec["renderer_id"], render.RENDERER_ID)
            self.assertEqual(spec["rito_manifest_sha256"], rito.manifest_core_hash(manifest))
            page_sha = hashlib.sha256((blog / f"{SLUG}.html").read_bytes()).hexdigest()
            self.assertEqual(spec["page_sha256"], page_sha)

    def test_publish_meta_rides_the_published_event(self):
        """The product spine (proposes/cites/distills/lineage) passes through the rito
        publication untouched — the rite replaces the path, not the ontology."""
        meta = {"proposes": [{"body": "medir a rodada 4", "kind": "constraint"}],
                "cites": [{"ref": "exp072", "kind": "atividade", "relevant": True,
                           "snippet": "29-8-3"}]}
        with tempfile.TemporaryDirectory() as tmp:
            _, _, log, _ = _green_run(tmp, publish_meta=meta)
            ev = next(e for e in eventlog.read(log=log)
                      if e["type"] == "artefato.published")
            self.assertEqual(ev["payload"]["proposes"], meta["proposes"])
            self.assertEqual(ev["payload"]["cites"], meta["cites"])

    def test_first_authorial_draft_stays_addressable_for_blind_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = _green_run(tmp)
            draft = run_dir / "02_FIRST_AUTHORIAL_DRAFT.md"
            self.assertTrue(draft.is_file())
            sealed = next(s for s in manifest["stages"]
                          if s["name"] == "first_authorial_draft")["output"]["sha256"]
            self.assertEqual(hashlib.sha256(draft.read_bytes()).hexdigest(), sealed)
            draft.unlink()
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertTrue(any(f.startswith("receipt-mismatch:first_authorial_draft")
                                for f in verdict["failures"]))

    def test_treatment_cleanup_deterministic_copy_when_scan_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, _, _ = _green_run(tmp)
            stage = next(s for s in manifest["stages"] if s["name"] == "treatment_cleanup")
            self.assertEqual(stage["execution"]["mode"], "deterministic_copy")
            self.assertEqual((run_dir / "08_BLIND_SAFE_FINAL.md").read_bytes(),
                             (run_dir / "07_AUDITED_FINAL.md").read_bytes())

    def test_treatment_cleanup_same_author_when_correction_leaks(self):
        canned = dict(CANNED)
        canned["author_correction"] = ("# Relatorio exp-teste\n\nNeste rascunho eu explico o "
                                       "mecanismo da rodada 3.")
        canned["treatment_cleanup"] = ("# Relatorio exp-teste\n\nAqui eu explico o mecanismo "
                                       "da rodada 3.")
        order = LLM_ORDER[:6] + ["treatment_cleanup"] + LLM_ORDER[6:]
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = _green_run(tmp, canned=canned, order=order)
            stage = next(s for s in manifest["stages"] if s["name"] == "treatment_cleanup")
            self.assertEqual(stage["execution"]["mode"], "same_author")
            self.assertTrue(rito.verify_rito(run_dir, log=log, blog_dir=blog)["pass"])


class NegativePathsTest(unittest.TestCase):
    def test_partial_rite_fails_the_detector(self):
        """A run that stops before render/publish (transport dies at fact_audit) leaves a
        failed manifest the detector refuses."""
        canned_order = LLM_ORDER[:4]  # transport exhausted at fact_audit
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                _green_run(tmp, order=canned_order)
            run_dir, log, blog = Path(tmp) / "run", Path(tmp) / "log.jsonl", Path(tmp) / "blog"
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("stage-not-completed:fact_audit", verdict["failures"])
            self.assertIn("stage-not-completed:publication", verdict["failures"])

    def test_legacy_renderer_bytes_fail_the_detector(self):
        """The cycle-2 death: rite executed but the page shipped through the legacy frontend.
        The form is part of the config — legacy bytes must FAIL."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            legacy = publisher._page(SLUG, "<p>mesmo conteudo</p>", skill="report",
                                     date="2026-07-10", css=publisher.BASE_CSS.read_text())
            (blog / f"{SLUG}.html").write_text(legacy)
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("page-bytes-mismatch", verdict["failures"])

    def test_review_before_render_fails_the_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            manifest_path = run_dir / "00_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            html_stage = next(s for s in manifest["stages"] if s["name"] == "final_html")
            review_stage = next(s for s in manifest["stages"] if s["name"] == "final_review")
            # forge a history where the review happened before the render existed
            review_stage["started_at"] = "2000-01-01T00:00:00+00:00"
            review_stage["finished_at"] = "2000-01-01T00:01:00+00:00"
            manifest_path.write_text(json.dumps(manifest))
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("review-before-render", verdict["failures"])

    def test_missing_publication_event_fails_the_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            kept = [line for line in log.read_text().splitlines()
                    if json.loads(line)["type"] != "artefato.published"]
            log.write_text("\n".join(kept) + "\n")
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("publication-event-missing", verdict["failures"])

    def test_forged_event_does_not_satisfy_the_sealed_receipt(self):
        """Codex [high]: the detector must bind to the SEALED publication receipt, not to
        'any matching event for the slug' — a receipt pointing at a different event fails."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            receipt_path = run_dir / "11_PUBLICATION.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["event_seq"] = receipt["event_seq"] + 999
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
            # re-seal the manifest receipt for the tampered file so ONLY the binding fails
            manifest_path = run_dir / "00_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            pub = next(s for s in manifest["stages"] if s["name"] == "publication")
            pub["output"]["sha256"] = hashlib.sha256(
                receipt_path.read_bytes()).hexdigest()
            pub["output"]["bytes"] = len(receipt_path.read_bytes())
            manifest_path.write_text(json.dumps(manifest))
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("publication-receipt-unbound", verdict["failures"])

    def test_event_markdown_must_equal_the_sealed_markdown(self):
        """Codex [high]: the logged spec's markdown must BE the sealed 08 markdown — a
        swapped source that still page-hash-matches is refused."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            lines = log.read_text().splitlines()
            out = []
            for line in lines:
                ev = json.loads(line)
                if ev["type"] == "artefato.published":
                    ev["payload"]["spec"]["markdown"] = "# Outro texto\n\ntrocado.\n"
                out.append(json.dumps(ev))
            log.write_text("\n".join(out) + "\n")
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("publication-event-unbound", verdict["failures"])

    def test_publish_rito_is_idempotent_after_the_event_committed(self):
        """Codex [high]: a crash between the event commit and the page write must not
        double-publish on resume — publish_rito finds the bound event, rewrites the page,
        and returns the same receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            before = [e for e in eventlog.read(log=log)
                      if e["type"] == "artefato.published"]
            (blog / f"{SLUG}.html").unlink()  # simulate the crash window
            receipt = publisher.publish_rito(SLUG, run_dir, intent=INTENT,
                                             skill="report", log=log, blog_dir=blog)
            after = [e for e in eventlog.read(log=log)
                     if e["type"] == "artefato.published"]
            self.assertEqual(len(after), len(before))  # no duplicate event
            self.assertEqual(receipt["event_seq"], before[0]["seq"])
            self.assertTrue((blog / f"{SLUG}.html").is_file())
            self.assertTrue(rito.verify_rito(run_dir, log=log, blog_dir=blog)["pass"])

    def test_manifest_status_must_be_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            manifest_path = run_dir / "00_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "failed"
            manifest_path.write_text(json.dumps(manifest))
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("manifest-not-completed", verdict["failures"])

    def test_stage_contract_drift_fails_the_detector(self):
        """Codex [med]: a manifest that keeps the names but rewires a stage's route/output
        contract is not the experiment's rite."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            manifest_path = run_dir / "00_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            stage = next(s for s in manifest["stages"] if s["name"] == "fact_audit")
            stage["route"] = "chat"  # the audit must be the independent reviewer route
            manifest_path.write_text(json.dumps(manifest))
            verdict = rito.verify_rito(run_dir, log=log, blog_dir=blog)
            self.assertFalse(verdict["pass"])
            self.assertIn("stage-contract-drift:fact_audit", verdict["failures"])

    def test_acceptance_fail_closes_the_rite_before_publication(self):
        canned = dict(CANNED)
        canned["final_review"] = ("ACCEPTANCE: FAIL\nUNSUPPORTED_CLAIMS: 2\n"
                                  "TREATMENT_LEAK: NO\n\nduas alegacoes sem lastro.")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(rito.StageFailure):
                _green_run(tmp, canned=canned)
            blog = Path(tmp) / "blog"
            self.assertFalse((blog / f"{SLUG}.html").exists())
            log = Path(tmp) / "log.jsonl"
            evs = [e for e in eventlog.read(log=log) if e["type"] == "artefato.published"]
            self.assertEqual(evs, [])


class PublishRitoSeamTest(unittest.TestCase):
    def _run_without_publication(self, tmp):
        """Run the rite with a capturing publish_fn so the seam can be exercised directly."""
        captured = {}

        def fake_publish(markdown, manifest):
            captured["markdown"] = markdown
            return {"event_seq": -1, "page_sha256": "fake", "page_path": "fake",
                    "rito_manifest_sha256": rito.manifest_core_hash(manifest)}
        manifest, run_dir, log, blog = _green_run(tmp, publish_fn=fake_publish)
        return manifest, run_dir, log, blog

    def test_publish_rito_refuses_a_renderer_hash_mismatch(self):
        """Pinned form: if the sealed final_html hash does not match the recomputed pinned
        render, the publisher must refuse — nothing lands."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = self._run_without_publication(tmp)
            manifest_path = run_dir / "00_MANIFEST.json"
            data = json.loads(manifest_path.read_text())
            html_stage = next(s for s in data["stages"] if s["name"] == "final_html")
            html_stage["output"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(data))
            (run_dir / "09_FINAL.html").write_bytes(b"<!doctype html>legacy bytes\n")
            _stamp_wake(log)
            with self.assertRaises(ValueError):
                publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                       log=log, blog_dir=blog)
            self.assertFalse((blog / f"{SLUG}.html").exists())

    def test_publish_rito_refuses_tampered_sealed_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = self._run_without_publication(tmp)
            path = run_dir / "08_BLIND_SAFE_FINAL.md"
            path.write_text(path.read_text() + "\nfrase inserida depois do selo.\n")
            _stamp_wake(log)
            with self.assertRaises(ValueError):
                publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                       log=log, blog_dir=blog)
            self.assertFalse((blog / f"{SLUG}.html").exists())

    def test_reprojection_re_derives_identical_bytes(self):
        """ADR-0006: the log is truth — the publisher's `_render_page` must re-derive the
        EXACT page bytes from the logged edge-markdown spec."""
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            spec = next(e for e in eventlog.read(log=log)
                        if e["type"] == "artefato.published")["payload"]["spec"]
            _, page = publisher._render_page(SLUG, spec, skill="report", date="2026-07-10")
            self.assertEqual((page.rstrip() + "\n").encode("utf-8"),
                             (blog / f"{SLUG}.html").read_bytes())


class RitoFinalReviewReplacesDoubleBlind(unittest.TestCase):
    """Operator decision, 2026-07-10, verbatim "basta" (docs/rito-runtime.md): the rite's own
    `final_review` (stage 10) REPLACES `close.run_close`'s double-blind reviewer gate on the
    rito path. The blind-winning B was produced with only the rite's internal review — an extra
    stochastic gate is not the experiment. Anti-forgery is the rito's seal (per-stage receipts
    + hash-refuse), not reviewer proofs. Changing this is re-opening the operator's decision,
    not fixing a bug."""

    def test_publish_rito_takes_no_run_close_proof(self):
        params = inspect.signature(publisher.publish_rito).parameters
        self.assertNotIn("verdict", params)
        self.assertNotIn("proof", params)

    def test_full_rite_publishes_with_no_run_close_verdict_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            ev = next(e for e in eventlog.read(types=["artefato.published"], log=log))
            self.assertNotIn("verdict", ev["payload"])
            self.assertTrue(rito.verify_rito(run_dir, log=log, blog_dir=blog)["pass"])


class PublishRitoSideEffectsTest(unittest.TestCase):
    """A rito-published artefato must be a first-class citizen of the graph/corpus: the rito
    publish path must emit the SAME post-publish side-effects as the legacy `publish` path —
    source-signal emission (ADR-0009) and graph projection (#30) — for `edge-markdown/v1`.
    Failure semantics mirror the legacy path: both side-effects run AFTER the commit + page
    write and are BEST-EFFORT (never abort the publish)."""

    def _fake_embed(self, text):
        return [float(len(text)), 1.0]

    def _sealed_run(self, tmp):
        """A sealed run dir whose real publish_rito hasn't run yet (capturing publish_fn), so the
        seam is exercised directly with injected fakes — mirrors _run_without_publication."""
        def fake_publish(markdown, manifest):
            return {"event_seq": -1, "page_sha256": "fake", "page_path": "fake",
                    "rito_manifest_sha256": rito.manifest_core_hash(manifest)}
        manifest, run_dir, log, blog = _green_run(tmp, publish_fn=fake_publish)
        _stamp_wake(log)  # a fresh wake for the real publish_rito below
        return run_dir, log, blog

    def test_publish_rito_projects_edge_markdown_with_real_content(self):
        """(a) publish_rito triggers graph projection for edge-markdown/v1 with the artefato's
        REAL content reachable by the projection (not an empty node): the spec handed to the
        projection flattens to the markdown body, so the content embedding/mentions see it."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, log, blog = self._sealed_run(tmp)
            seen = {}

            def project_fn(s, i, *, skill, distills, proposes, cites, spec=None,
                           lineage=None, log=None, gate=None, origin=None, **kw):
                seen.update(slug=s, intent=i, skill=skill, spec=spec)

            publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                   log=log, blog_dir=blog, project_fn=project_fn)
            self.assertEqual(seen["slug"], SLUG)
            self.assertEqual(seen["intent"], INTENT)
            self.assertEqual(seen["skill"], "report")
            # the REAL content is reachable: _spec_text of the projected spec is non-empty and
            # carries the markdown body (the "empty node" the mission warns about would flatten
            # to '' because edge-markdown/v1 has no sections/executive_summary keys).
            flattened = publisher._spec_text(seen["spec"])
            self.assertIn("rodada 3", flattened)

    def test_publish_rito_emits_source_signals_for_its_cites(self):
        """(b) source-signal emission fires with the cites, exactly like the legacy path."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, log, blog = self._sealed_run(tmp)
            cites = [{"ref": "arXiv:2507.02778", "kind": "mundo",
                      "relevant": True, "snippet": "o indice vence"}]
            publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                   log=log, blog_dir=blog, cites=cites,
                                   embed_fn=self._fake_embed, project_fn=None)
            yields = eventlog.source_yield_at(log=log)
            self.assertIn("arXiv:2507.02778", yields)
            self.assertEqual(yields["arXiv:2507.02778"]["count"], 1)

    def test_side_effect_failure_is_best_effort_like_legacy(self):
        """(c) a side-effect failure (projection blows up) is REPORTED, never fatal — the page +
        atomic commit still land; identical contract to the legacy path's project_fn wrapper."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, log, blog = self._sealed_run(tmp)

            def boom_project(*a, **k):
                raise RuntimeError("neo4j unreachable")

            receipt = publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                             log=log, blog_dir=blog, project_fn=boom_project)
            self.assertTrue((blog / f"{SLUG}.html").is_file())
            self.assertEqual([c["slug"] for c in eventlog.corpus_at(log=log)], [SLUG])

    def test_resume_does_not_re_emit_side_effects(self):
        """Codex adversarial [SEV-HIGH]: the idempotent-resume branch reuses an already-committed
        event — re-running the side-effects would DOUBLE-COUNT source signals (source_signal is a
        bare append, no dedup) and re-project from the retry's args. Side-effects run ONLY on the
        FRESH commit; a resume is a pure page re-derivation. reproject_missing_pages heals a crash
        that dropped them."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, log, blog = self._sealed_run(tmp)
            cites = [{"ref": "arXiv:9", "kind": "mundo", "relevant": True, "snippet": "x"}]
            # first (fresh) publish emits exactly one signal per cite
            publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                   log=log, blog_dir=blog, cites=cites,
                                   embed_fn=self._fake_embed, project_fn=None)
            self.assertEqual(eventlog.source_yield_at(log=log)["arXiv:9"]["count"], 1)
            (blog / f"{SLUG}.html").unlink()  # simulate the crash window, force resume
            projected = []
            publisher.publish_rito(SLUG, run_dir, intent=INTENT, skill="report",
                                   log=log, blog_dir=blog, cites=cites,
                                   embed_fn=self._fake_embed,
                                   project_fn=lambda *a, **k: projected.append(1))
            # resume re-derived the page but did NOT re-emit the signal or re-project
            self.assertTrue((blog / f"{SLUG}.html").is_file())
            self.assertEqual(eventlog.source_yield_at(log=log)["arXiv:9"]["count"], 1)
            self.assertEqual(projected, [])


class DetectorCliTest(unittest.TestCase):
    def test_cli_verify_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, log, blog = _green_run(tmp)
            ok = rito.main(["verify", str(run_dir), "--log", str(log),
                            "--blog-dir", str(blog)])
            self.assertEqual(ok, 0)
            (blog / f"{SLUG}.html").write_text("legacy\n")
            bad = rito.main(["verify", str(run_dir), "--log", str(log),
                             "--blog-dir", str(blog)])
            self.assertEqual(bad, 1)


    def test_report_markdown_first_draft_completes(self):
        """3aeb049: a report-form first draft is Markdown. YAML is not required."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = _green_run(tmp)
            self.assertEqual(manifest["status"], "completed")
            sealed = (run_dir / "08_BLIND_SAFE_FINAL.md").read_text()
            self.assertFalse(yaml_rite.is_yaml_draft(sealed))
            self.assertTrue((blog / f"{SLUG}.html").is_file())


class ReaderFacingProbeReviewTest(unittest.TestCase):
    """#585 / #647: leftover YAML is reviewed as published HTML, not keys."""

    def test_final_review_prompt_is_rendered_html(self):
        def prompts():
            base = _prompts()
            base["final_review"] = (
                lambda o: "<strict review>\n\n"
                + (o.get("reader_facing") or o["treatment_cleanup"]))
            return base

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            log, blog, run_dir = tmp / "log.jsonl", tmp / "blog", tmp / "run"
            did = _stamp_wake(log)
            rito.run_rito(
                SLUG, run_dir=run_dir,
                grounding1_fn=lambda: "# Dossier factual\n\nFatos: 29-8-3 em 40 rodadas.",
                prompts=prompts(),
                complete_fn=_complete_fn(YAML_CANNED, LLM_ORDER),
                intent=INTENT, skill="report", dispatch_id=did,
                log=log, blog_dir=blog,
            )
            review_prompt = (run_dir / "prompts" / "10_final_review.md").read_text()
            sealed = (run_dir / "08_BLIND_SAFE_FINAL.md").read_text()
            self.assertTrue(yaml_rite.is_yaml_draft(sealed))
            self.assertIn("rodada 3", review_prompt)
            self.assertIn("comparison-grid", review_prompt)
            self.assertNotIn("type: lineage", review_prompt)
            self.assertNotIn("type: comparison", review_prompt)
            self.assertIn("type: lineage", sealed)

    def test_yaml_source_is_not_the_probe_body(self):
        """The probe facing text is HTML, never raw YAML keys."""
        facing = yaml_rite.reader_facing_text(YAML_AUTHOR_CORRECTION)
        self.assertIn("rodada 3", facing)
        self.assertNotIn("type: comparison", facing)
        self.assertTrue(facing.lstrip().startswith("<!doctype html>")
                        or "<main>" in facing)


if __name__ == "__main__":
    unittest.main()
