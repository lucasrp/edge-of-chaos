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

SLUG = "exp-teste-rito"
INTENT = "provar que o rito inteiro roda, do dossier a publicacao"

APPROVED_GENERATOR = Path(
    "/home/vboxuser/edge/drafts/exp072-report-quality/post-gate-grounding-arm/"
    "generate_post_gate_grounding_arm.py")

# Canned cognitive outputs — scan-clean (no draft/grounding/prompt/harness vocabulary), so the
# deterministic treatment gates pass and treatment_cleanup takes the deterministic-copy branch.
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


def _green_run(tmp, canned=None, order=None, publish_fn=rito.DEFAULT_PUBLISH):
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
    eventlog.publish_artefato_atomic(
        SLUG, INTENT, spec=spec, skill="report", log=log, dispatch_id=did)
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
        self.assertEqual(render.RENDERER_ID, "exp072-neutral-markdown/v1")

    @unittest.skipUnless(APPROVED_GENERATOR.is_file(), "approved generator not on this host")
    def test_promoted_renderer_is_byte_identical_to_the_approved_one(self):
        spec = importlib.util.spec_from_file_location("approved_gen", APPROVED_GENERATOR)
        approved = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(approved)
        self.assertEqual(render.render_markdown_page(self.SAMPLE, "Titulo"),
                         approved.render_markdown(self.SAMPLE, "Titulo"))

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
            expected = render.markdown_page_bytes(sealed_md)
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


if __name__ == "__main__":
    unittest.main()
