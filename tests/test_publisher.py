"""The publisher — the close pipeline's atomic publish seam (ADR-0012/0013).

`publish` is `consolidate-state` minus session-digestion, de-YAML'd: it renders the
Artefato body via render.spec_to_html, wraps it in a self-contained neutral HTML page
that inlines tools/assets/base.css, writes it to blog/entries/<slug>.html, and ATOMICALLY
records state via the eventlog — the published event + its intent kernel in one act, so
`artefatos_without_kernel(log) == []` right after. C3 (no Artefato closes without a kernel)
is enforced at this seam: publishing without an intent raises.

These tests pin that seam offline (injected embed_fn, tempfile log + blog_dir).
"""
import os
import sys
import tempfile
import unittest
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import eventlog  # noqa: E402
import publisher  # noqa: E402
import render  # noqa: E402
import visual_grounding  # noqa: E402

_REAL_PROJECT = publisher.project_artefato
_REAL_PUBLISH = publisher.publish
FIXTURES = REPO / "tests/fixtures/genus_rite"


def _hash(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _stage(stage_id, file_name, inputs, summary):
    path = FIXTURES / file_name
    stage = {
        "id": stage_id,
        "path": str(path.relative_to(REPO)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input_stage_ids": list(inputs),
        "allowed_inputs": ["dossier", *inputs],
        "input_hashes": {"dossier": _hash(f"{stage_id}:dossier"),
                         **{i: _hash(f"{stage_id}:{i}") for i in inputs}},
        "summary": summary,
    }
    if inputs:
        stage["parent_stage_id"] = inputs[-1]
    return stage


def _stage_trace():
    return [
        _stage("old_edge_draft", "old_edge_draft.md", [],
               "old Edge subrite material before the gate"),
        _stage("gap_gate", "gap_gate.md", ["old_edge_draft"],
               "gate names actionable lacunas"),
        _stage("post_gate_grounding", "post_gate_grounding.md", ["old_edge_draft", "gap_gate"],
               "grounding answers the named lacuna"),
        _stage("final_rewrite", "final_rewrite.md", ["old_edge_draft", "post_gate_grounding"],
               "final rewrite shows the grounding delta"),
        _stage("fact_audit", "fact_audit.md", ["final_rewrite"],
               "fact audit narrows overclaim before close"),
    ]


def _neo4j_reachable():
    """True iff the install's Neo4j is reachable — gates the live lineage-edge test (which writes
    real :Artefato nodes + lineage edges). Offline/CI degrades to skip, never fails."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
        drv.verify_connectivity()
        drv.close()
        return True
    except Exception:  # noqa: BLE001 — no graph → skip the live test
        return False


_NEO4J = _neo4j_reachable()


def setUpModule():
    """Keep the whole module OFFLINE: the default project_fn now connects to the LIVE graph, so a
    publish in a test with a temp log would project a test Artefato into the install graph (Codex
    P2 / pollution). Neutralize the default projection to a no-op for every test that does not
    inject its own project_fn; the dedicated projection tests inject a fake or restore the real one.

    ADR-0016: every publish now requires a fresh wake stamp (no wake, no publish). These tests
    exercise the publisher's OTHER seams, so the harness stamps the wake on each call's log —
    the no-wake gate itself is covered in tests/test_predispatch.py."""
    publisher.project_artefato = lambda *a, **k: None

    def stamped_publish(*a, **kw):
        eventlog.dispatch_open(log=kw.get("log", eventlog.LOG))
        return _REAL_PUBLISH(*a, **kw)
    publisher.publish = stamped_publish


def tearDownModule():
    publisher.project_artefato = _REAL_PROJECT
    publisher.publish = _REAL_PUBLISH


class NoWakeGateIsRealAtTheSeam(unittest.TestCase):
    """Opus review — the suite's stamped_publish harness masks the wake gate everywhere else,
    so the gate gets coverage CO-LOCATED with the seam it guards: the REAL publish refuses
    without a stamp, independent of tests/test_predispatch.py."""

    def test_real_publish_without_stamp_raises_no_wake(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(RuntimeError) as ctx:
                _REAL_PUBLISH("any-slug", "<h1>x</h1>", "intent", skill="report",
                              verdict={"not": "a proof"}, log=log, blog_dir=tmp)
            self.assertIn("no-wake", str(ctx.exception))


def _fake_embed(text):
    """An offline embedder: a tiny deterministic 2-vector, never an OpenAI call."""
    return [float(len(text)), 1.0]


def _passing_proof(slug, spec, intent, *, cites=None, proposes=None,
                   distills=None, skill="report", lineage=None, genus_rite_trace=None,
                   accepted_risks=None):
    """A BOUND passing proof for the exact payload — minted via close's PRIVATE `_mint_proof`
    the same way `run_close` mints it (run_close-only token + sha256 digest of
    slug+spec+intent+cites+proposes+distills+skill+lineage+accepted_risks + both passing reviewer verdicts
    carrying the CANONICAL reviewer identities). This is the explicit TEST-ONLY seam standing
    in for run_close; it stamps the two canonical identities verify_proof requires. The
    publisher refuses anything not bound to the payload (and identities) it is publishing."""
    verdicts = [
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.FEYNMAN_REVIEWER_ID},
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.REGULAR_REVIEWER_ID},
    ]
    return close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                             cites=cites or [], proposes=proposes or [],
                             distills=distills, skill=skill, lineage=lineage,
                             genus_rite_trace=genus_rite_trace,
                             accepted_risks=accepted_risks)


def _spec():
    return {
        "executive_summary": ["the seam holds"],
        "sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "atomic publish plus kernel in one act."},
        ]}],
    }


def _floored_spec():
    # valid for EVERY roster skill's presentation floor at once. S6/S7 (R1/R2): ascii-diagram is dropped,
    # so include two renderable visual blocks; in an env without vl-convert they honestly degrade, and in
    # an env with vl-convert they satisfy the map visual floor. The plan `framed_steps` and discovery
    # `contextual_framing` floors are non-visual and still satisfied. No executive_summary: 1 paragraph +
    # 1 callout = prose count 2 (< the rich-rite threshold of 3), so the prose-synthesis moves aren't owed.
    return {"sections": [{"title": "Body", "blocks": [
        {"type": "paragraph", "text": "atomic publish plus kernel in one act."},
        {"type": "next-steps-grid", "items": ["step one", "step two"]},
        {"type": "callout", "text": "framing context"},
        visual_grounding.sign(
            {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 1}]}),
        visual_grounding.sign(
            {"type": "diagram", "layout": "dag",
             "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
             "edges": [{"source": "a", "target": "b", "label": "causes"}]}),
    ]}]}


def _developed_rite_spec():
    return {"sections": [{"title": "Executable rite", "blocks": [
        {"type": "paragraph", "text": "Because the approved arm came from a sequence, the sequence is the tested unit."},
        {"type": "paragraph", "text": "The reader needs the mechanism, not another report that merely resembles the old one."},
        {"type": "paragraph", "text": "The decision is to bind the rite before trusting another blind publish."},
        {"type": "derivation", "text": "If a final report can be imitated, the process trace must be proof-bound."},
        {"type": "gap-table", "gaps": [
            {"description": "Whether post-gate grounding happened", "need": "proof-bound trace", "status": "open"}]},
    ]}], "bibliography": [{"text": "genus rite doc", "url": "https://example.com"}]}


def _rite_trace():
    return {
        "version": "old-edge-grounded@1",
        "old_edge_draft": {
            "derived_thesis": "the sequence, not the final page, is the reproduced unit",
            "live_question": "whether the deploy reproduced the rite or only the final look",
            "reader_context": "the operator is comparing blind reports against the approved arm",
            "lineage_seed": "approved-old-edge-grounded-arm -> rejected lookalike -> publish seam",
            "worked_example": "approved exp072 arm starts from product question and mechanism",
            "lacunas": "trace proof, page shell, distributed Mundo, and next validation",
            "outside_frame_candidates": "reproducibility, artifact review, trace propagation",
            "mentor_arc": "name the mismatch, ground it, rewrite with a decision",
            "unknowns": "deployment drift",
            "actionable_landing": "gate this draft and ground the named gaps before rewriting",
        },
        "dossier": {
            "reader_model": "operator familiar with approved and rejected reports",
            "lineage": "approved old-edge arm and later smoke failures",
            "object_identity": "publishable developed synthesis owing the old-edge-grounded rite",
            "anchors": "stage fixture files and genus rite doc",
            "mechanism_evidence": "stage trace files plus proof-bound payload",
            "mundo_candidates": "reproducibility, traceability, artifact evaluation",
            "unknowns": "blind autonomous report still has to validate transfer",
        },
        "stage_trace": _stage_trace(),
        "reader_model": {
            "reader": "operator",
            "leveling": "can recognize the approved arm",
            "interests": "make the rite reproducible",
            "decision_context": "decide if the deploy can be trusted",
            "growth_target": "better judgment, not a local rubric optimum",
            "utility_target": "show what changed and the next verification",
        },
        "narrative_arc": {
            "throughline": "from mismatch to executable rite",
            "opening_stakes": "a report can look right and still be wrong",
            "turning_point": "the process becomes payload",
            "landing_decision": "refuse missing traces",
        },
        "gap_gate": [{"id": "g1", "gap": "process invisible",
                      "grounding_task": "bind trace into proof",
                      "disposition": "resolved"}],
        "post_gate_grounding": [{
            "gap_id": "g1",
            "source_ref": "docs/genus-rite-v6-canonical-form.md",
            "finding": "the movement includes post-gate grounding",
            "changed": "publish now validates that movement",
        }],
        "rewrite_delta": [{
            "gap_id": "g1",
            "before": "prompt-only rite",
            "after": "proof-bound rite",
            "effect": "reproducible",
            "final_anchor": "bind the rite",
        }],
        "canonical_journey": [
            {"move": "thesis", "where": "Executable rite"},
            {"move": "live_question", "where": "reader needs the mechanism"},
            {"move": "setup", "where": "approved arm came from a sequence"},
            {"move": "lineage", "where": "approved arm"},
            {"move": "result", "where": "tested unit"},
            {"move": "mechanism", "where": "process trace must be proof-bound"},
            {"move": "interpretation", "where": "final report can be imitated"},
            {"move": "mundo", "where": "genus rite doc"},
            {"move": "grounding_effect", "where": "bind the rite"},
            {"move": "limits", "where": "whether post-gate grounding happened"},
            {"move": "decision", "where": "decision is to bind the rite"},
            {"move": "references", "where": "genus rite doc"},
        ],
        "mundo_effects": [{
            "source_ref": "docs/genus-rite-v6-canonical-form.md",
            "fit": "reproducibility frames method reruns instead of output copying",
            "mismatch": "the external frame does not prove this deploy worked",
            "changes": "the final text must say the process trace is proof-bound",
            "final_anchor": "process trace must be proof-bound",
        }],
        "reader_visible_agency": {
            "decision_now": "bind the rite",
            "do_not_overclaim": "do not claim success without a blind report",
            "risk_status": "blind transfer remains open",
            "next_validation": "run an autonomous report after publish",
            "final_anchor": "decision is to bind the rite",
        },
        "fact_audit": {
            "external_claims_checked": "source positions the rite only",
            "overclaim_guard": "no source proves deploy success",
        },
    }


class PublishIsAtomicAndKerneled(unittest.TestCase):
    """publish writes a self-contained neutral HTML page (inlined base.css, the meta line,
    `<article class="report">`) AND records the published event + its kernel atomically, so
    the C3 invariant holds right after; publishing with no intent raises."""

    def test_writes_self_contained_page_and_records_kernel_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "the-seam-holds"
            cites = [{"ref": "arXiv:2507.02778", "kind": "mundo",
                      "relevant": True, "snippet": "the blind-spot is measured"}]

            intent = "next bet: pour the gate into the slot"
            path = publisher.publish(
                slug, _spec(), intent=intent,
                skill="report", cites=cites, date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed,
                verdict=_passing_proof(slug, _spec(), intent, cites=cites),
            )

            # the page exists and is self-contained + neutral, matching the entry shape
            page = Path(path)
            self.assertTrue(page.exists())
            self.assertEqual(page, Path(tmp) / f"{slug}.html")
            text = page.read_text()
            self.assertIn(".derivation", text)        # inlined base.css token
            self.assertIn("#7C3AED", text)            # functional derivation-purple, kept
            self.assertIn('<article class="report">', text)
            self.assertIn('<p class="meta">2026-06-08 · report</p>', text)
            self.assertIn("atomic publish plus kernel in one act", text)

            # the wrapper declares the entries' language and inlines the
            # page-frame enhancements (assets/page.js) — still self-contained
            self.assertIn('<html lang="pt-BR">', text)
            self.assertIn("<script>", text)
            self.assertIn("report-lightbox", text)    # inlined page.js token

            # state recorded ATOMICALLY: the C3 invariant holds right after
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], [slug])
            self.assertEqual(corpus[0]["intent"], "next bet: pour the gate into the slot")

            # the cite's source signal landed (offline, via embed_fn)
            yields = eventlog.source_yield_at(log=log)
            self.assertIn("arXiv:2507.02778", yields)
            self.assertEqual(yields["arXiv:2507.02778"]["count"], 1)

    def test_publish_without_intent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for missing in (None, "", "   "):
                with self.assertRaises(ValueError):
                    publisher.publish(
                        "no-kernel", _spec(), intent=missing, skill="report",
                        date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                        verdict=_passing_proof("no-kernel", _spec(), missing),
                    )
            # nothing published — C3 refused the close before any state landed
            self.assertEqual(eventlog.corpus_at(log=log), [])


class PublishRefusesWithoutAPassingReviewProof(unittest.TestCase):
    """#2 — the enforced close path. `publisher.publish` is no longer a callable producers
    reach for directly: it REFUSES unless handed the proof of a passing review that only
    `run_close` mints (both blind reviewers passed). A direct publish with no/failing
    verdict raises and writes nothing; the enforced path publishes only after the gate
    passes."""

    def test_direct_publish_without_verdict_raises_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                publisher.publish(
                    "ungated", _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / "ungated.html").exists())

    def test_direct_publish_with_a_failing_verdict_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            failing = {"pass": False, "verdicts": [
                {"pass": True, "strikes": []}, {"pass": False, "strikes": ["x"]}]}
            with self.assertRaises(ValueError):
                publisher.publish(
                    "ungated", _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=failing,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])

    def test_run_close_is_the_enforced_path_publishing_only_after_both_gates_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "enforced"
            art = {
                "slug": slug,
                "content": _spec(),
                "cites": [],
                "proposes": [],
                "intent": "open: x; bet: y",
                "skill": "report",
            }
            published = []

            def publish_fn(artefato, verdict):
                published.append(
                    publisher.publish(
                        artefato["slug"], artefato["content"], intent=artefato["intent"],
                        skill=artefato["skill"], date="2026-06-08", log=log, blog_dir=tmp,
                        embed_fn=_fake_embed, verdict=verdict,
                    )
                )

            # the enforced path uses the REAL canonical reviewers, so the proof carries the
            # two canonical identities verify_proof requires.
            result = close.run_close(
                art, produce_fn=lambda: art,
                reviewers=(close.feynman_review, close.regular_review),
                complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
                publish_fn=publish_fn,
            )
            self.assertTrue(result["pass"])
            self.assertEqual(len(published), 1)              # published exactly once
            self.assertTrue((Path(tmp) / f"{slug}.html").exists())
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

    def test_run_close_to_publish_lineage_only_richrite_no_split(self):
        # Codex: a developed-prose artefato whose rich-rite:lineage move is satisfied ONLY by authored
        # (target-only) lineage passes run_close, mints a proof, and PUBLISHES — the publish-seam genus
        # recheck now includes the normalized lineage, so close and publish never SPLIT (before the fix the
        # recheck saw no lineage and would have raised). The persisted event carries the normalized edge.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "lineage-only"
            content = {"sections": [{"title": "Executable rite", "blocks": [
                {"type": "paragraph",
                 "text": "Because the approved arm came from a sequence, the sequence is the tested unit."},
                {"type": "paragraph",
                 "text": "The reader needs the mechanism. What i do not know: whether post-gate grounding happened under concurrent load at scale."},
                {"type": "paragraph",
                 "text": "The decision is to bind the rite before trusting the publish; a final report can be imitated, so the process trace must be proof-bound."},
            ]}], "bibliography": [{"text": "genus rite doc", "url": "https://example.com"}]}
            cites = [{"ref": "docs/genus-rite-v6-canonical-form.md", "kind": "mundo",
                      "relevant": True, "snippet": "external frame snippet"}]
            lineage = [{"type": "supersedes", "target": "thread-7"}]  # target-only: the deciding lineage move
            art = {"slug": slug, "content": content, "cites": cites, "proposes": [],
                   "intent": "open: x; bet: y", "skill": "report", "lineage": lineage,
                   "genus_rite": _rite_trace()}
            published = []

            def publish_fn(artefato, verdict):
                published.append(publisher.publish(
                    artefato["slug"], artefato["content"], intent=artefato["intent"],
                    skill=artefato["skill"], cites=artefato["cites"], lineage=artefato["lineage"],
                    genus_rite_trace=artefato.get("genus_rite"),
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed, verdict=verdict))

            result = close.run_close(
                art, produce_fn=lambda: art,
                reviewers=(close.feynman_review, close.regular_review),
                complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
                publish_fn=publish_fn)
            self.assertTrue(result["pass"])
            self.assertEqual(len(published), 1)              # no close/publish split — published once
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["lineage"], lineage)  # normalized target-only edge persisted

    def test_hand_built_proof_at_the_seam_raises_and_writes_nothing(self):
        # Codex re-review #2: a forged dict with pass:True + passing verdicts but NO
        # run_close token (and no bound digest) must raise at the seam — the publisher is
        # not fooled by a shape-only proof.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            forged = {"pass": True, "verdicts": [
                {"pass": True}, {"pass": True}], "digest": "x", "token": "guessed"}
            with self.assertRaises(ValueError):
                publisher.publish(
                    "forged", _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=forged,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / "forged.html").exists())

    def test_proof_for_artefato_A_cannot_publish_artefato_B_at_the_seam(self):
        # the proof is BOUND to A's payload; handing it to publish B (digest mismatch)
        # raises before any state/HTML lands.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            spec_a = {"sections": [{"title": "A", "blocks": [
                {"type": "paragraph", "text": "artefato A content"}]}]}
            spec_b = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "DIFFERENT artefato B content"}]}]}
            proof_a = _passing_proof("artefato-a", spec_a, "open: a; bet: a")
            with self.assertRaises(ValueError):
                publisher.publish(
                    "artefato-b", spec_b, intent="open: b; bet: b", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=proof_a,  # A's proof, B's payload → digest mismatch
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / "artefato-b.html").exists())

    def test_single_reviewer_proof_at_the_seam_raises(self):
        # a proof minted from only one reviewer must not publish — both configured
        # reviewers must have passed.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            one = close._mint_proof(
                [{"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
                  "reviewer": close.FEYNMAN_REVIEWER_ID}],
                slug="single", spec=_spec(), intent="open: x; bet: y",
                cites=[], proposes=[], distills=None, skill="report")
            with self.assertRaises(ValueError):
                publisher.publish(
                    "single", _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=one,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])

    def test_altered_distills_at_the_seam_raises_and_writes_nothing(self):
        # Codex re-review #3: the proof binds `distills`. A proof-holder who alters distills
        # at publish time (poisoning provenance) is rejected — the digest no longer matches.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "bound-distills"
            reviewed_distills = [{"page": "memory", "body": "what was reviewed"}]
            proof = _passing_proof(slug, _spec(), "open: x; bet: y",
                                   distills=reviewed_distills)
            with self.assertRaises(ValueError):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    distills=[{"page": "memory", "body": "POISONED at publish"}],
                    verdict=proof,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / f"{slug}.html").exists())

    def test_altered_skill_at_the_seam_raises_and_writes_nothing(self):
        # the proof binds `skill`; publishing under a different skill is rejected.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "bound-skill"
            proof = _passing_proof(slug, _spec(), "open: x; bet: y", skill="report")
            with self.assertRaises(ValueError):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill="plan",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=proof,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / f"{slug}.html").exists())

    def test_bound_distills_publishes_when_unchanged(self):
        # the matching distills/skill publishes cleanly (the bind does not over-reject).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "matching-distills"
            reviewed_distills = [{"page": "memory", "body": "what was reviewed"}]
            proof = _passing_proof(slug, _spec(), "open: x; bet: y",
                                   distills=reviewed_distills)
            path = publisher.publish(
                slug, _spec(), intent="open: x; bet: y", skill="report",
                date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                distills=reviewed_distills, verdict=proof,
            )
            self.assertTrue(Path(path).exists())

    def test_altered_lineage_at_the_seam_raises_and_writes_nothing(self):
        # Cortex-v1 (brick-1): the proof binds `lineage` end-to-end. A proof-holder who alters the
        # authored typed lineage at publish time (poisoning provenance) is rejected at the REAL
        # publish seam — the digest no longer matches. Mirrors test_altered_distills_at_the_seam.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "bound-lineage-seam"
            reviewed_lineage = [{"type": "supersedes", "target": "thread-7"}]
            proof = _passing_proof(slug, _spec(), "open: x; bet: y",
                                   lineage=reviewed_lineage)
            with self.assertRaises(ValueError):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill="report",
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    lineage=[{"type": "contradicts", "target": "POISONED at publish"}],
                    verdict=proof,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / f"{slug}.html").exists())

    def test_developed_synthesis_without_genus_rite_trace_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "missing-rite-trace"
            spec = _developed_rite_spec()
            intent = "open: reproduce rite; bet: bind the process"
            cites = [{"ref": "docs/genus-rite-v6-canonical-form.md", "kind": "mundo",
                      "relevant": True, "snippet": "old-edge draft -> actionable gap gate"}]
            lineage = [{"type": "builds_on", "target": "approved-arm"}]
            with self.assertRaises(ValueError) as ctx:
                publisher.publish(
                    slug, spec, intent=intent, skill="report", cites=cites, lineage=lineage,
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=_passing_proof(slug, spec, intent, cites=cites, lineage=lineage),
                )
            self.assertIn("genus-rite:missing-trace", str(ctx.exception))
            self.assertEqual(eventlog.corpus_at(log=log), [])

    def test_genus_rite_trace_binds_digest_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "bound-rite-trace"
            spec = _developed_rite_spec()
            intent = "open: reproduce rite; bet: bind the process"
            cites = [{"ref": "docs/genus-rite-v6-canonical-form.md", "kind": "mundo",
                      "relevant": True, "snippet": "old-edge draft -> actionable gap gate"}]
            lineage = [{"type": "builds_on", "target": "approved-arm"}]
            trace = _rite_trace()
            proof = _passing_proof(slug, spec, intent, cites=cites, lineage=lineage,
                                   genus_rite_trace=trace)
            poisoned = {**trace, "rewrite_delta": [
                {"gap_id": "g1", "before": "proof-bound rite", "after": "poisoned",
                 "effect": "wrong", "final_anchor": "bind the rite"}]}
            with self.assertRaises(ValueError):
                publisher.publish(
                    slug, spec, intent=intent, skill="report", cites=cites, lineage=lineage,
                    genus_rite_trace=poisoned, date="2026-06-08", log=log, blog_dir=tmp,
                    embed_fn=_fake_embed, verdict=proof,
                )

            path = publisher.publish(
                slug, spec, intent=intent, skill="report", cites=cites, lineage=lineage,
                genus_rite_trace=trace, date="2026-06-08", log=log, blog_dir=tmp,
                embed_fn=_fake_embed, verdict=proof,
            )
            self.assertTrue(Path(path).exists())
            html = Path(path).read_text()
            self.assertIn('<main class="old-edge-grounded">', html)
            self.assertNotIn('<body><article class="report">', html)
            self.assertNotIn('<p class="meta">2026-06-08 · report</p>', html)
            ev = eventlog.read(types=["artefato.published"], log=log)[0]
            self.assertEqual(ev["payload"]["genus_rite"]["rewrite_delta"][0]["after"],
                             "proof-bound rite")
            self.assertEqual(ev["payload"]["genus_rite"]["stage_trace"][0]["id"],
                             "old_edge_draft")
            self.assertEqual(ev["payload"]["genus_rite"]["stage_trace"][0]["input_stage_ids"],
                             [])
            self.assertEqual(eventlog.corpus_at(log=log)[0]["genus_rite"]["version"],
                             "old-edge-grounded@1")

    def test_bound_lineage_publishes_when_unchanged(self):
        # The matching lineage publishes cleanly through the real seam (the bind does not
        # over-reject) — closing the integration gap so a non-empty lineage artefato is
        # publishable end-to-end, not just verifiable at the close layer.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "matching-lineage"
            reviewed_lineage = [{"type": "builds_on", "target": "thread-3"}]
            proof = _passing_proof(slug, _spec(), "open: x; bet: y",
                                   lineage=reviewed_lineage)
            path = publisher.publish(
                slug, _spec(), intent="open: x; bet: y", skill="report",
                date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                lineage=reviewed_lineage, verdict=proof,
            )
            self.assertTrue(Path(path).exists())

    def test_authored_lineage_rides_the_real_publish_seam_into_event_and_corpus(self):
        # Cortex-v1 (brick-1, slice lineage-event-roundtrip): the FULL publisher seam — not just the
        # low-level eventlog primitive — must carry the proof-bound authored lineage into the durable
        # `artefato.published` event AND the corpus fold. verify_proof binds lineage, but publish must
        # then HAND it to publish_artefato_atomic, or it disappears between proof and persistence
        # (Codex SUBSTANTIVE: lineage dropped at the seam). Asserts the raw event payload AND the
        # corpus item both carry the exact list.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "seam-roundtrip-lineage"
            lineage = [{"type": "supersedes", "target": "thread-7"},
                       {"type": "builds_on", "target": "thread-3"}]
            proof = _passing_proof(slug, _spec(), "open: x; bet: y", lineage=lineage)
            publisher.publish(
                slug, _spec(), intent="open: x; bet: y", skill="report",
                date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                lineage=lineage, verdict=proof,
            )
            published = [e for e in eventlog.read(types=["artefato.published"], log=log)
                         if e["payload"]["slug"] == slug]
            self.assertEqual(published[0]["payload"]["lineage"], lineage)
            corpus = [c for c in eventlog.corpus_at(log=log) if c["slug"] == slug]
            self.assertEqual(corpus[0]["lineage"], lineage)

    def test_lineage_binds_in_the_proof_digest(self):
        # Cortex-v1 (brick-1): the proof binds the AUTHORED typed `lineage` exactly as it binds
        # distills/skill — without it the field is forgeable at publish time. Mirrors
        # test_altered_distills_at_the_seam: the proof verifies against the SAME lineage, but an
        # ALTERED lineage (poisoned authored provenance) is rejected — the digest no longer matches.
        slug = "bound-lineage"
        lineage = [{"type": "supersedes", "target": "thread-7"},
                   {"type": "builds_on", "target": "thread-3"}]
        proof = _passing_proof(slug, _spec(), "open: x; bet: y", lineage=lineage)
        # verifies against the SAME lineage it was minted over...
        close.verify_proof(
            proof, slug=slug, spec=_spec(), intent="open: x; bet: y",
            cites=[], proposes=[], skill="report", lineage=lineage, reviewer_count=2,
        )
        # ...but an ALTERED lineage (forged authored provenance) is rejected.
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=slug, spec=_spec(), intent="open: x; bet: y",
                cites=[], proposes=[], skill="report",
                lineage=[{"type": "contradicts", "target": "POISONED at publish"}],
                reviewer_count=2,
            )

    def test_empty_lineage_is_back_compat(self):
        # A proof minted with NO lineage (the param unset) verifies against [] AND against an
        # unset lineage — so every prior offline mint/verify (which never passes lineage) keeps
        # binding identically. lineage `None`/`[]`/unset are one and the same in the digest.
        slug = "no-lineage"
        proof = _passing_proof(slug, _spec(), "open: x; bet: y")
        for lineage in (None, []):
            close.verify_proof(
                proof, slug=slug, spec=_spec(), intent="open: x; bet: y",
                cites=[], proposes=[], skill="report", lineage=lineage,
                reviewer_count=2,
            )

    def test_run_close_failing_gate_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            art = {"slug": "blocked", "content": _spec(), "cites": [], "proposes": [],
                   "intent": "open: x; bet: y"}
            published = []

            def publish_fn(artefato, verdict):
                published.append(artefato)

            def always_strike(artefato, complete_fn=None):
                return {"pass": False, "scores": {}, "strikes": ["x"], "overall": 2.0}

            result = close.run_close(
                art, produce_fn=lambda: art, reviewers=(always_strike, always_strike),
                complete_fn=lambda *a, **k: "", publish_fn=publish_fn,
            )
            self.assertFalse(result["pass"])
            self.assertEqual(published, [])                  # the gate never let it publish
            self.assertEqual(eventlog.corpus_at(log=log), [])


class ProjectAfterPublishIsAGuaranteedSideEffect(unittest.TestCase):
    """#30 move 1 — project-after-publish lives IN the publisher (was prose in memory.md the
    producer skipped). After the atomic commit, `publish` projects the Artefato into the graph
    as a GUARANTEED, best-effort side-effect: it calls `project_fn` with the EXACT published
    payload (slug + intent + skill + distills + proposes + cites). A failed projection is
    REPORTED, never fatal (ADR-0011/0006: the log is truth; reproject next beat). `project_fn`
    is injectable so the seam runs offline; the default `project_artefato` degrades safely when
    neo4j/openai are absent (it never raises into the publish)."""

    def test_project_fn_called_after_publish_with_the_published_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "projected"
            intent = "open: x; bet: y"
            cites = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True, "snippet": "snip"}]
            proposes = [{"body": "name it", "kind": "constraint"}]
            distills = ["cluster:recall"]
            lineage = [{"type": "supersedes", "target": "thread-7"}]
            seen = {}

            def project_fn(s, i, *, skill, distills, proposes, cites, spec=None,
                           lineage=None, log=None, gate=None, origin=None,
                           **kw):  # ticket A: +bears_on/para
                seen.update(slug=s, intent=i, skill=skill, distills=distills,
                            proposes=proposes, cites=cites, spec=spec,
                            lineage=lineage, log=log, gate=gate)

            publisher.publish(
                slug, _spec(), intent=intent, skill="report", cites=cites,
                proposes=proposes, distills=distills, lineage=lineage, date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=project_fn,
                verdict=_passing_proof(slug, _spec(), intent, cites=cites,
                                       proposes=proposes, distills=distills, lineage=lineage),
            )
            self.assertEqual(seen["slug"], slug)
            self.assertEqual(seen["intent"], intent)
            self.assertEqual(seen["skill"], "report")
            self.assertEqual(seen["distills"], distills)
            self.assertEqual(seen["proposes"], proposes)
            self.assertEqual(seen["cites"], cites)
            self.assertEqual(seen["spec"], _spec())   # the spec is passed for the content embed
            self.assertEqual(seen["lineage"], lineage)  # projection gets the NORMALIZED lineage — the SAME
            #   sanitized list the proof binds and the event persists (Codex: no proof/event-invisible junk
            #   may reach projection), equal-by-value to this already-clean input.
            self.assertEqual(seen["log"], log)         # the projection reads the SAME log (Codex P2)
            # B.1 (ticket B): a projeção recebe o MESMO gate que o evento persistiu — lido do
            # proof (nunca de um arg do caller), então o nó e o log nunca divergem.
            self.assertEqual(seen["gate"],
                             publisher._gate_payload(_passing_proof(
                                 slug, _spec(), intent, cites=cites, proposes=proposes,
                                 distills=distills, lineage=lineage)))

    def test_clean_plus_junk_lineage_projects_only_normalized(self):
        # Codex: a proof minted for CLEAN lineage, published with clean+junk — the junk normalizes away so
        # verify still passes — must hand the projection ONLY the normalized edges (no proof/event-invisible
        # item like a blank-slug builds_on can drive project_artefato and strand projection_complete=false).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "clean-proj"
            intent = "open: x; bet: y"
            cites = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True, "snippet": "snip"}]
            proposes = [{"body": "name it", "kind": "constraint"}]
            distills = ["cluster:recall"]
            clean = [{"type": "supersedes", "target": "thread-7"}]
            published = clean + [{"type": "builds_on", "slug": "   "}, "junk"]
            seen = {}

            def project_fn(s, i, *, skill, distills, proposes, cites, spec=None,
                           lineage=None, log=None, gate=None, origin=None,
                           **kw):  # ticket A: +bears_on/para
                seen["lineage"] = lineage

            publisher.publish(
                slug, _spec(), intent=intent, skill="report", cites=cites,
                proposes=proposes, distills=distills, lineage=published, date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=project_fn,
                verdict=_passing_proof(slug, _spec(), intent, cites=cites,
                                       proposes=proposes, distills=distills, lineage=clean),
            )
            self.assertEqual(seen["lineage"], clean)

    def test_failed_projection_does_not_break_the_publish(self):
        # ADR-0011: a projection write that fails is REPORTED, never fatal — the page + the
        # atomic commit still land; the next beat reprojects.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "degrade-safe"
            intent = "open: x; bet: y"

            def boom_project(*a, **k):
                raise RuntimeError("neo4j unreachable")

            path = publisher.publish(
                slug, _spec(), intent=intent, skill="report", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=boom_project,
                verdict=_passing_proof(slug, _spec(), intent),
            )
            # publish succeeded despite the projection blowing up
            self.assertTrue(Path(path).exists())
            self.assertEqual([c["slug"] for c in eventlog.corpus_at(log=log)], [slug])
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

    def test_non_canonical_log_skips_the_destructive_backbone_rebuild(self):
        # Codex P2: project_artefato with a CUSTOM (non-canonical) log must NOT run the destructive
        # ANCHORS DELETE/rebuild against the install graph — an empty/offline log would wipe live
        # Directions. The backbone sync is canonical-log only; a custom log projects ADD-only edges.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("eventlog.LOG", src,
                      "project_artefato must gate the backbone rebuild to the canonical log")
        # the DELETE (the destructive rebuild) must be guarded, not unconditional
        delete_idx = src.find("DELETE r")
        canonical_guard = src.rfind("eventlog.LOG", 0, delete_idx)
        self.assertNotEqual(canonical_guard, -1,
                            "the ANCHORS DELETE must be guarded by a canonical-log check")

    def test_reproject_graph_replays_committed_artefatos_to_the_graph(self):
        # Codex P2: a transient graph outage at publish time must be recoverable — reproject_graph
        # replays every committed Artefato through project_artefato (idempotent) so the "reproject
        # next beat" path actually exists. Verify it calls the projection per committed corpus item.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # commit two artefatos to the log (no graph projection — project_fn=None)
            for slug in ("recov-a", "recov-b"):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                    log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                    verdict=_passing_proof(slug, _spec(), "open: x; bet: y"))
            projected = []

            def fake_project(slug, intent, **k):
                projected.append(slug)

            publisher.reproject_graph(log=log, project_fn=fake_project,
                                      present_slugs=lambda: {},  # hermetic: none present
                                      backbone_fn=None)
            self.assertEqual(sorted(projected), ["recov-a", "recov-b"])

    def test_reproject_graph_replays_the_authored_lineage(self):
        # Cortex-v1 (brick-1, L3): the REPLAY path must mirror the forward path — reproject_graph
        # must pass the committed `lineage` to project_fn, or a transient-outage recovery silently
        # drops the authored typed lineage and the directed edges never re-derive (Codex SUBSTANTIVE).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "recov-lineage"
            lineage = [{"type": "supersedes", "target": "thread-7"}]
            publisher.publish(
                slug, _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None, lineage=lineage,
                verdict=_passing_proof(slug, _spec(), "open: x; bet: y", lineage=lineage))
            seen = {}

            def fake_project(s, intent, *, skill=None, distills=None, proposes=None,
                             cites=None, spec=None, lineage=None, log=None, gate=None, origin=None,
                             **kw):  # ticket A: +bears_on/para ride the replay
                seen["lineage"] = lineage

            publisher.reproject_graph(log=log, project_fn=fake_project,
                                      present_slugs=lambda: {},  # hermetic: none present
                                      backbone_fn=None)
            self.assertEqual(seen["lineage"], lineage)  # the logged lineage rides the replay

    def test_reproject_graph_replays_standalone_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_asset(
                "demo-proto-abc123def456",
                path="blog/entries/demo.proto.abc123def456.html",
                kind="html",
                sha256="a" * 64,
                skill="prototype",
                parent_slug="demo",
                media_type="text/html",
                role="prototype",
                log=log)
            projected = []

            def asset_project_fn(asset_slug, **kw):
                projected.append((asset_slug, kw))

            publisher.reproject_graph(
                log=log,
                project_fn=lambda *a, **k: None,
                present_slugs=lambda: {},
                backbone_fn=None,
                asset_project_fn=asset_project_fn)
            self.assertEqual(projected[0][0], "demo-proto-abc123def456")
            self.assertEqual(projected[0][1]["parent_slug"], "demo")
            self.assertEqual(projected[0][1]["kind"], "html")

    def test_backfill_entry_assets_records_legacy_files_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = Path(tmp) / "entries"
            entries.mkdir()
            log = Path(tmp) / "log.jsonl"
            (entries / "legacy-report.html").write_text("<html><body>legacy</body></html>")
            (entries / "legacy-report.app.js").write_text("console.log('legacy');")
            emitted = publisher.backfill_entry_assets(
                blog_dir=entries,
                log=log,
                project_fn=None,
            )
            self.assertEqual(len(emitted), 2)
            assets = eventlog.artefato_assets_at(log=log)
            self.assertEqual({a["kind"] for a in assets.values()}, {"html", "js"})
            self.assertTrue(all(a["role"] == "entry-backfill" for a in assets.values()))

            again = publisher.backfill_entry_assets(blog_dir=entries, log=log, project_fn=None)
            self.assertEqual(again, [])
            self.assertEqual(len(eventlog.artefato_assets_at(log=log)), 2)

    def test_backfill_entry_assets_skips_normal_published_slug_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = Path(tmp) / "entries"
            entries.mkdir()
            log = Path(tmp) / "log.jsonl"
            (entries / "published.html").write_text("<html><body>normal close page</body></html>")
            (entries / "published.app.js").write_text("console.log('asset');")
            eventlog.append_batch([
                ("artefato.published", "artefato:published",
                 {"slug": "published", "spec": {"type": "doc"}, "skill": "report"}),
                ("intent.kernel", "artefato:published", {"slug": "published", "intent": "why"}),
            ], log=log)

            publisher.backfill_entry_assets(blog_dir=entries, log=log, project_fn=None)
            assets = eventlog.artefato_assets_at(log=log)
            self.assertEqual(len(assets), 1)
            asset = next(iter(assets.values()))
            self.assertEqual(asset["kind"], "js")
            self.assertEqual(asset["parent_slug"], "published")

    def test_reproject_graph_runs_entry_asset_backfill_on_the_canonical_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            original_log = publisher.eventlog.LOG
            original_backfill = publisher.backfill_entry_assets
            called = []
            try:
                publisher.eventlog.LOG = log
                publisher.backfill_entry_assets = lambda **kw: called.append(kw) or []
                publisher.reproject_graph(
                    log=log,
                    project_fn=lambda *a, **k: None,
                    present_slugs=lambda: {},
                    backbone_fn=None,
                    asset_project_fn=lambda *a, **k: None,
                    session_topic_project_fn=lambda **kw: None,
                )
            finally:
                publisher.eventlog.LOG = original_log
                publisher.backfill_entry_assets = original_backfill
            self.assertEqual(called[0]["log"], log)
            self.assertIsNone(called[0]["project_fn"])

    def test_project_session_topic_index_emits_session_topic_fragment_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.record_session_topic(
                "s1",
                "session-memory-navigation",
                title="Memoria de sessoes navegavel",
                surface="claude",
                path="/tmp/s1.jsonl",
                score=3,
                keywords=["recall", "topics"],
                fragments=[{"turn": 1, "snippet": "indexar sessoes por topics"}],
                log=log,
            )
            eventlog.propose(
                "topic-7d:session-memory-navigation",
                "Construir memoria navegavel por Voz -> Topic -> Thread.",
                kind="thread",
                log=log,
            )
            seen = []

            class FakeSession:
                def run(self, query, **params):
                    seen.append((query, params))
                    return []

            publisher._project_session_topic_index(
                FakeSession(), "g1", eventlog.session_topics_at(log=log), log=log)

            joined = "\n".join(q for q, _ in seen)
            self.assertIn("MERGE (se:Episodic", joined)
            self.assertIn("MERGE (t:Topic", joined)
            self.assertIn("MERGE (vf:VozFragment", joined)
            self.assertIn("HAS_TOPIC", joined)
            self.assertIn("HAS_FRAGMENT", joined)
            self.assertIn("ABOUT", joined)
            self.assertIn("PROPOSES", joined)

    def test_reproject_graph_replays_session_topic_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.record_session_topic(
                "s1", "topic-thread-direction", title="Topics -> Threads -> Direction",
                surface="claude", fragments=[{"turn": 1, "snippet": "costurar topics"}],
                log=log)
            called = []

            publisher.reproject_graph(
                log=log,
                project_fn=lambda *a, **k: None,
                present_slugs=lambda: {},
                backbone_fn=None,
                asset_project_fn=lambda *a, **k: None,
                session_topic_project_fn=lambda **kw: called.append(kw["log"]))

            self.assertEqual(called, [log])

    def test_reproject_graph_replays_only_missing_slugs(self):
        # Codex P2: steady-state must NOT re-embed the whole corpus each sweep — reproject_graph
        # replays only the slugs MISSING (or STALE) in the graph. `present_slugs` maps each present
        # slug to its projected_at; a slug present AND FRESH (projected_at >= log ts) is skipped.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for slug in ("have-it", "missing-it"):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                    log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                    verdict=_passing_proof(slug, _spec(), "open: x; bet: y"))
            projected = []
            publisher.reproject_graph(
                log=log,
                project_fn=lambda slug, *a, **k: projected.append(slug),
                present_slugs=lambda: {"have-it": "9999-01-01T00:00:00+00:00"},  # present + FRESH
                backbone_fn=None)
            self.assertEqual(projected, ["missing-it"])  # only the missing one replays

    def test_reproject_graph_replays_a_stale_present_slug(self):
        # Codex P2: a republished slug whose graph node is STALE (projected_at older than the log's
        # latest published ts) must be RE-projected, even though it is 'present' — the graph cannot
        # keep an old kernel/edges forever after a republish whose projection never reached Neo4j.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            publisher.publish(
                "republished", _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                verdict=_passing_proof("republished", _spec(), "open: x; bet: y"))
            projected = []
            publisher.reproject_graph(
                log=log,
                project_fn=lambda slug, *a, **k: projected.append(slug),
                present_slugs=lambda: {"republished": "2000-01-01T00:00:00+00:00"},  # present but STALE
                backbone_fn=None)
            self.assertEqual(projected, ["republished"])  # stale node re-projected

    def test_project_artefato_sets_completion_marker_last(self):
        # Codex P2: completeness is `projection_complete` set as the LAST step (after all edges +
        # embed), so a half-projected node (embed set, SERVES/edges not) is NOT treated as present.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("projection_complete", src,
                      "project_artefato must set a completion marker after all writes")
        # the marker must be set AFTER the edge writes (CITES is the last edge loop). The final SET
        # uses the `$done` param (gated on resolved distills), not a literal — match the param form.
        self.assertGreater(src.find("projection_complete=$done"), src.rfind("[:CITES]->"),
                           "the completion marker must be the LAST write, after the edge loops")
        # and _graph_present_slugs reads the completion marker, not bare node/embedding presence
        self.assertIn("projection_complete", inspect.getsource(publisher._graph_present_slugs))

    def test_republish_clears_completion_marker_before_re_updating(self):
        # Codex P2: a republish with a corrected payload must clear projection_complete FIRST, so a
        # partial-failure mid-update leaves it incomplete (re-projected next sweep) and the graph
        # cannot keep a stale kernel/edges forever. The clear (set false) is in the first MERGE; the
        # set-true is the LAST step — so a failure between them leaves the marker false.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        clear_idx = src.find("projection_complete=false")  # cleared in the first MERGE
        set_idx = src.find("projection_complete=$done")     # final SET (gated on resolved distills)
        self.assertNotEqual(clear_idx, -1, "republish must CLEAR projection_complete before updating")
        self.assertLess(clear_idx, src.rfind("[:CITES]->"),
                        "the clear must precede the edge writes")
        self.assertGreater(set_idx, src.rfind("[:CITES]->"),
                           "the final marker SET must follow the edge writes (last)")
        self.assertLess(clear_idx, set_idx, "clear-false precedes the final SET")

    def test_projection_loads_the_openai_key_before_embedding(self):
        # Codex P1: the embed key lives in the install/dev secrets and is not necessarily exported —
        # project_artefato must load it (via _load_openai_key) before constructing OpenAI(), or every
        # publish would fail the embed, never complete, and be filtered from recall forever.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("_load_openai_key()", src,
                      "project_artefato must load the OpenAI key before the embed (Codex P1)")
        # the loader reads the install secret + the ~/.edge-sandbox-kit dev fallback
        loader = inspect.getsource(publisher._load_openai_key)
        self.assertIn("openai.env", loader)
        self.assertIn("edge-sandbox-kit", loader)

    def test_failed_embed_leaves_projection_incomplete(self):
        # Codex P2: a FAILED embed (key/service down) must NOT mark the projection complete — the
        # completion marker is gated on `embed_current`, so recovery retries the embed once creds
        # recover instead of skipping the slug forever.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("embed_current", src, "project_artefato must track embed success")
        # the completion marker is gated on embed_current AND no unresolved distills
        self.assertIn("embed_current and not unresolved_distills", src,
                      "the completion marker must require a current embedding")

    def test_unresolved_distill_leaves_projection_incomplete(self):
        # Codex P2: a distill ref whose cluster is not in the graph yet must leave the projection
        # INCOMPLETE (so recovery revisits once the grill attaches the cluster), not mark it done.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("unresolved_distills", src,
                      "project_artefato must track unresolved distills")
        # the completion marker is conditional on no unresolved distills
        self.assertIn("not unresolved_distills", src,
                      "the completion marker must be gated on resolved distills")

    def test_distill_resolution_uses_active_clusters_only(self):
        # Codex P2: archived/merged entities are hidden by graph_clusters, so the projection must
        # resolve distills against ACTIVE clusters only (never link/push a retired cluster).
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("coalesce(e.archived,false)=false", src)
        self.assertIn("e.merged_into IS NULL", src)

    def test_lineage_edges_are_a_fixed_allowlist_directed_this_to_prior(self):
        # Cortex-v1 (brick-1, L4): project_artefato materializes the AUTHORED typed lineage as
        # DIRECTED graph edges this -> prior, mapping item type through a FIXED Python allowlist
        # (never interpolating caller data into Cypher), and rebuilds them destructively like the
        # other authored edges so a corrected republish strands no stale edge.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        # the fixed allowlist maps the three authored relation types to their labels — keyed on the
        # producer-supplied type, never interpolating caller data (the LABEL is a fixed dict value)
        self.assertEqual(publisher.LINEAGE_LABELS,
                         {"builds_on": "BUILDS_ON", "supersedes": "SUPERSEDES",
                          "contradicts": "CONTRADICTS"},
                         "the lineage allowlist must map the three authored types to fixed labels")
        # the projection maps the producer type through THAT allowlist (no caller string in Cypher)
        self.assertIn("LINEAGE_LABELS", src,
                      "project_artefato must map item type through the fixed LINEAGE_LABELS allowlist")
        # the three labels JOIN the destructive edge-rebuild DELETE set (so a corrected republish
        # does not strand a stale lineage edge — mirrors the DISTILLS/PROPOSES/CITES rebuild)
        delete_idx = src.find("DELETE r")
        self.assertNotEqual(delete_idx, -1)
        delete_clause = src[src.rfind("MATCH", 0, delete_idx):delete_idx]
        for label in ("BUILDS_ON", "SUPERSEDES", "CONTRADICTS"):
            self.assertIn(label, delete_clause,
                          f"{label} must be in the destructive edge-rebuild DELETE set")
        # the edge is DIRECTED this -> prior. Assert the LINEAGE-SPECIFIC Cypher shape, not the
        # generic "MERGE (a)-[:" (Codex: that is also emitted by SERVES/DISTILLS/PROPOSES/CITES, so a
        # deleted/inverted lineage block would not trip it). The lineage MERGE is the ONLY one that
        # (a) interpolates its label from the fixed allowlist via `%s` and (b) targets the prior
        # Artefato `(p)` — every other authored edge targets (o)/(e)/(d)/(src). Both pin the block.
        self.assertIn("MERGE (a)-[:%s]->(p)", src,
                      "the lineage edge must interpolate the allowlist label via %s and be directed "
                      "this(a) -> prior(p) — distinct from the (o)/(e)/(d)/(src) authored edges")
        # the label that fills %s comes from the allowlist lookup, never raw caller data
        self.assertIn("LINEAGE_LABELS.get(item.get(\"type\"))", src,
                      "the %s label must be the fixed-allowlist value, not interpolated caller data")
        # and it is directed this -> prior, NOT prior -> this (a reversed MERGE must not appear)
        self.assertNotIn("MERGE (p)-[:", src,
                         "the lineage edge must be this -> prior, never prior -> this")

    def test_unresolved_lineage_prior_leaves_projection_incomplete(self):
        # Cortex-v1 (brick-1, L4): a lineage ref whose prior :Artefato is not in the graph yet
        # (out-of-order publish) must leave the projection INCOMPLETE so recovery revisits once the
        # prior lands — mirroring the unresolved-distills self-heal, not silently dropping the edge.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("unresolved_lineage", src,
                      "project_artefato must track an unresolved lineage prior")
        # the completion marker is gated on the resolved lineage too
        self.assertIn("not unresolved_lineage", src,
                      "the completion marker must be gated on the resolved lineage prior")

    def test_embedding_refreshed_on_content_change_skipped_when_unchanged(self):
        # Codex P2: re-embed only when the embed input CHANGED — a republish with changed intent/spec
        # refreshes the stale embedding; a pure edge-link revisit (same content) skips the re-embed.
        # Keyed on a sha256 hash of (slug+intent+spec_text), not bare `IS NOT NULL`.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        self.assertIn("embedding_input_hash", src,
                      "project_artefato must store an embed-input hash to detect content change")
        self.assertIn("emb_hash", src)
        # the re-embed condition compares the stored hash, not only embedding presence
        self.assertIn('row["h"] == emb_hash', src,
                      "re-embed must be gated on the embed-input hash, not just IS NOT NULL")

    def test_backbone_ensures_every_artefato_serves_the_objective(self):
        # Codex P2: an Artefato published BEFORE the Objective existed had SERVES no-op; the backbone
        # (every canonical sweep) guarantees the hub link so it is reachable from space-0.
        import inspect
        src = inspect.getsource(publisher._project_backbone)
        self.assertIn("[:SERVES]->", src,
                      "the backbone must ensure every Artefato SERVES the objective (reachability)")

    def test_reproject_graph_rebuilds_the_backbone_even_when_all_slugs_present(self):
        # Codex P2: the spine backbone (ANCHORS rebuild) must run on EVERY canonical sweep so newly
        # folded Directions get anchored — even when every artefato is already present (the steady
        # state after publish-time projection). The per-slug embed work is skipped; the backbone is not.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            publisher.publish(
                "present-one", _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                verdict=_passing_proof("present-one", _spec(), "open: x; bet: y"))
            projected, backbones = [], []
            publisher.reproject_graph(
                log=log,
                project_fn=lambda slug, *a, **k: projected.append(slug),
                present_slugs=lambda: {"present-one": "9999-01-01T00:00:00+00:00"},  # present + fresh
                backbone_fn=lambda log=None: backbones.append(True))
            self.assertEqual(projected, [])                  # no per-slug re-embed (all present)
            self.assertEqual(backbones, [True])              # but the backbone STILL rebuilt

    def test_reproject_graph_default_skips_a_non_canonical_log(self):
        # Codex P2: reproject_graph(log=temp_log) with the DEFAULT projector must NOT write into the
        # live graph — it mirrors publish()'s hermeticity guard. The real projector is restored and a
        # dead bolt URI would print a connection error IF it ran; default-skip means silence.
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            publisher.publish(
                "recov-c", _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                verdict=_passing_proof("recov-c", _spec(), "open: x; bet: y"))
            prev_uri = os.environ.get("EDGE_NEO4J_URI")
            os.environ["EDGE_NEO4J_URI"] = "bolt://127.0.0.1:1"
            prev_proj = publisher.project_artefato
            publisher.project_artefato = _REAL_PROJECT   # bypass the module no-op
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    publisher.reproject_graph(log=log)   # NO project_fn → default, non-canonical log
            finally:
                publisher.project_artefato = prev_proj
                if prev_uri is None:
                    os.environ.pop("EDGE_NEO4J_URI", None)
                else:
                    os.environ["EDGE_NEO4J_URI"] = prev_uri
            self.assertNotIn("Couldn't connect", buf.getvalue())  # the projector never ran

    def test_spec_text_flattens_content_for_the_embedding(self):
        # Codex P2: the content embedding must include the body, not just the kernel — a concept in
        # the body but not the kernel must still be in the embed input.
        spec = {
            "executive_summary": ["a summary sentence with CONCEPT_A"],
            "sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "the body mentions CONCEPT_B in prose"},
                {"type": "table", "headers": ["k"], "rows": [["CONCEPT_C"]]},
            ]}],
        }
        text = publisher._spec_text(spec)
        self.assertIn("CONCEPT_A", text)
        self.assertIn("CONCEPT_B", text)
        self.assertIn("CONCEPT_C", text)

    def test_spec_text_is_empty_for_a_none_spec(self):
        self.assertEqual(publisher._spec_text(None), "")

    def test_spec_text_includes_top_level_metrics(self):
        # Codex P2: render renders top-level `metrics`, so the embed must include their labels/values.
        spec = {"metrics": [{"value": "0.81", "label": "RECALL_AT_FIVE"}], "sections": []}
        text = publisher._spec_text(spec)
        self.assertIn("RECALL_AT_FIVE", text)
        self.assertIn("0.81", text)

    def test_reproject_graph_restores_the_persisted_skill(self):
        # Codex P2: the published event carries `skill`, so a recovery replay restores the REAL
        # producer identity (even when the node does not exist yet — the publish-time-outage case
        # this path is for). reproject_graph replays item['skill']; project_artefato coalesces it
        # (a legacy None never clobbers an existing value).
        import inspect
        rg = inspect.getsource(publisher.reproject_graph)
        self.assertIn('item.get("skill")', rg,
                      "reproject_graph must replay the persisted skill from the log")
        self.assertIn("coalesce", inspect.getsource(_REAL_PROJECT).lower(),
                      "project_artefato must coalesce skill (a None never clobbers existing)")

    def test_custom_log_default_skips_projection(self):
        # Codex P2: a publish to a NON-canonical (temp) log with the DEFAULT project_fn must NOT
        # project into the live graph — dry-runs/tests are hermetic by default. Restore the real
        # project_artefato (the module no-op is bypassed) and confirm it is never reached: a dead
        # bolt URI would print a connection error if it tried; default-skip means silence.
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "custom-log-noproject"
            prev_uri = os.environ.get("EDGE_NEO4J_URI")
            os.environ["EDGE_NEO4J_URI"] = "bolt://127.0.0.1:1"   # would error IF projection ran
            prev_proj = publisher.project_artefato
            publisher.project_artefato = _REAL_PROJECT            # bypass the module no-op
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    publisher.publish(
                        slug, _spec(), intent="open: x; bet: y", skill="report", date="2026-06-08",
                        log=log, blog_dir=tmp, embed_fn=_fake_embed,  # NO project_fn → default
                        verdict=_passing_proof(slug, _spec(), "open: x; bet: y"))
            finally:
                publisher.project_artefato = prev_proj
                if prev_uri is None:
                    os.environ.pop("EDGE_NEO4J_URI", None)
                else:
                    os.environ["EDGE_NEO4J_URI"] = prev_uri
            # the projection never ran (no connection attempt → no error printed)
            self.assertNotIn("Couldn't connect", buf.getvalue())
            self.assertNotIn("project", buf.getvalue().lower())

    def test_reproject_missing_pages_uses_the_persisted_skill(self):
        # Codex P2: a recovered page uses the REAL producer skill from the log, not 'report'.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            slug = "skill-page"
            # commit a `map` publish but force the page write to fail (recoverable)
            orig_replace = os.replace
            os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
            try:
                with self.assertRaises(OSError):
                    publisher.publish(
                        slug, _floored_spec(), intent="open: x; bet: y", skill="map", date="2026-06-08",
                        log=log, blog_dir=blog, embed_fn=_fake_embed, project_fn=None,
                        verdict=_passing_proof(slug, _floored_spec(), "open: x; bet: y", skill="map"))
            finally:
                os.replace = orig_replace
            publisher.reproject_missing_pages(log=log, blog_dir=blog, date="2026-06-08")
            text = (blog / f"{slug}.html").read_text()
            self.assertIn('<p class="meta">2026-06-08 · map</p>', text)  # the REAL skill, not report

    def test_published_event_carries_skill_for_graph_recovery(self):
        # the skill rides the atomic published event (the only recovery source), so a reproject
        # after a publish-time outage restores the producer identity on a node that did not exist.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "skill-persisted"
            publisher.publish(
                slug, _floored_spec(), intent="open: x; bet: y", skill="map", date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, project_fn=None,
                verdict=_passing_proof(slug, _floored_spec(), "open: x; bet: y", skill="map"))
            self.assertEqual(eventlog.corpus_at(log=log)[0]["skill"], "map")

    def test_project_artefato_clears_stale_edges_before_re_adding(self):
        # Codex P2: a republish/replay with corrected distills/proposes/cites must not leave the
        # slug's OLD edges behind — the projection rebuilds the slug's DISTILLS/PROPOSES/CITES.
        import inspect
        src = inspect.getsource(_REAL_PROJECT)
        for rel in ("DISTILLS", "PROPOSES", "CITES"):
            # each relationship is DELETEd for this slug before the MERGE re-adds the current set
            self.assertTrue(f"[r:{rel}]" in src or f":{rel}]->() DELETE" in src
                            or (f"{rel}" in src and "DELETE" in src),
                            f"project_artefato must clear the slug's stale {rel} edges before re-adding")

    def test_default_project_artefato_degrades_when_graph_unreachable(self):
        # the default projection must NEVER raise into the publish even when the graph is
        # unreachable — it is best-effort; it prints and returns. Point at a dead bolt port so
        # this is the GENUINE unreachable-graph degrade path, deterministic and offline, and
        # writes NOTHING to any live graph (no test pollution).
        prev = os.environ.get("EDGE_NEO4J_URI")
        os.environ["EDGE_NEO4J_URI"] = "bolt://127.0.0.1:1"
        try:
            # exercise the REAL projection (the module no-op patch is bypassed here), against a
            # dead bolt port — the genuine unreachable-graph degrade path, offline, no pollution.
            _REAL_PROJECT(
                "deg", "open: x; bet: y", skill="report",
                distills=["cluster:recall"], proposes=[], cites=[])
        except Exception as e:  # noqa: BLE001
            self.fail(f"project_artefato must degrade safely, raised {e!r}")
        finally:
            if prev is None:
                os.environ.pop("EDGE_NEO4J_URI", None)
            else:
                os.environ["EDGE_NEO4J_URI"] = prev


class WrapperMetadataIsEscapedAndSkillIsRostered(unittest.TestCase):
    """Codex round-4 [high]: the page wrapper interpolates caller/spec values (date, skill,
    title/slug) into raw HTML. Reviewers only see slug/content/cites; `skill` is proof-bound
    but NOT sanitized — so a producer could supply markup in `skill` (the proof binds to it,
    verify passes) and the public page would execute it. `date` is also unescaped. The fix:
    reject an out-of-roster skill BEFORE anything is written, and `html.escape(quote=True)`
    every wrapper value so no caller/spec value can inject markup."""

    def test_out_of_roster_skill_is_rejected_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "xss-via-skill"
            evil = "report</p><script>alert(1)</script>"
            # the proof binds to the (malicious) skill, so verify_proof would PASS — the
            # roster check is the gate that must stop it.
            proof = _passing_proof(slug, _spec(), "open: x; bet: y", skill=evil)
            with self.assertRaises(ValueError):
                publisher.publish(
                    slug, _spec(), intent="open: x; bet: y", skill=evil,
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=proof,
                )
            self.assertEqual(eventlog.corpus_at(log=log), [])
            self.assertFalse((Path(tmp) / f"{slug}.html").exists())

    def test_every_in_roster_skill_publishes_a_clean_meta_line(self):
        for skill in publisher.PRODUCER_ROSTER:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                slug = f"clean-{skill}"
                path = publisher.publish(
                    slug, _floored_spec(), intent="open: x; bet: y", skill=skill,
                    date="2026-06-08", log=log, blog_dir=tmp, embed_fn=_fake_embed,
                    verdict=_passing_proof(slug, _floored_spec(), "open: x; bet: y", skill=skill),
                )
                text = Path(path).read_text()
                self.assertIn(f'<p class="meta">2026-06-08 · {skill}</p>', text)
                # exactly ONE script element reaches the page: the repo-controlled
                # inlined assets/page.js — nothing injected via the meta line.
                self.assertEqual(text.count("<script>"), 1)
                self.assertNotIn("alert(", text)

    def test_malicious_date_is_escaped_no_raw_markup_reaches_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug = "xss-via-date"
            evil_date = "2026<script>alert(1)</script>"
            path = publisher.publish(
                slug, _spec(), intent="open: x; bet: y", skill="report",
                date=evil_date, log=log, blog_dir=tmp, embed_fn=_fake_embed,
                verdict=_passing_proof(slug, _spec(), "open: x; bet: y"),
            )
            text = Path(path).read_text()
            self.assertNotIn("<script>alert(1)</script>", text)
            self.assertIn("&lt;script&gt;", text)   # escaped, inert

    def test_title_from_slug_is_escaped_in_wrapper(self):
        # the title is derived from the slug; though the slug regex is strict, the wrapper
        # must still escape it so no value reaches the page as raw markup.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            page = publisher._page("a-b", "<p>body</p>", skill="report",
                                   date="2026-06-08", css="")
            self.assertIn("<title>a b</title>", page)
            self.assertIn("<h1>a b</h1>", page)

    def test_inlined_js_cannot_close_its_own_script_element(self):
        # page.js is repo-controlled, but defense in depth: a closing script tag
        # inside it must not terminate the wrapper's script element early.
        with tempfile.TemporaryDirectory():
            page = publisher._page("a-b", "<p>body</p>", skill="report",
                                   date="2026-06-08", css="",
                                   js='var a = "</script>";')
            self.assertEqual(page.count("</script>"), 1)  # the wrapper's own close tag

    def test_empty_js_emits_no_script_element(self):
        page = publisher._page("a-b", "<p>body</p>", skill="report",
                               date="2026-06-08", css="")
        self.assertNotIn("<script>", page)


class SlugIsContainedUnderBlogDir(unittest.TestCase):
    """#4 — the slug names a file under blog_dir, nothing more. A `../`/`/`/empty/funny slug
    is REJECTED (it must match `^[a-z0-9][a-z0-9-]*$`); a normal slug writes a file that
    resolves UNDER blog_dir, via a temp file + atomic rename (no half-written page, no escape)."""

    def test_traversal_and_malformed_slugs_are_rejected_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            for bad in ("../escape", "../../etc/passwd", "a/b", "", "   ",
                        "Caps", "under_score", "-leading",
                        "with space", "dot.slug"):
                with self.assertRaises(ValueError, msg=f"slug {bad!r} should be rejected"):
                    publisher.publish(
                        bad, _spec(), intent="open: x; bet: y", skill="report",
                        date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                        verdict=_passing_proof(bad, _spec(), "open: x; bet: y"),
                    )
            # nothing escaped, nothing landed
            self.assertFalse(Path(tmp, "escape.html").exists())
            self.assertFalse(Path(tmp, "passwd").exists())
            self.assertEqual(eventlog.corpus_at(log=log), [])

    def test_normal_slug_writes_under_blog_dir_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            out = publisher.publish(
                "recall-report-2", _spec(), intent="open: x; bet: y", skill="report",
                date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                verdict=_passing_proof("recall-report-2", _spec(), "open: x; bet: y"),
            )
            out = Path(out).resolve()
            self.assertEqual(out.parent, blog.resolve())          # contained under blog_dir
            self.assertTrue(out.exists())
            # atomic write left no temp-file litter
            self.assertEqual(list(blog.glob("*.tmp")), [])

    def test_a_failed_render_leaves_no_orphan_page_or_state(self):
        """#3 ordering: the page is rendered, then state is recorded, then the HTML is written
        (temp+rename). A render that raises mid-publish leaves NO orphan page (and no temp
        litter), so the log's truth and the on-disk projection never disagree."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            # a spec render that raises mid-publish must not leave a half-written page
            import render
            orig = render.spec_to_html
            render.spec_to_html = lambda spec: (_ for _ in ()).throw(RuntimeError("boom"))
            try:
                with self.assertRaises(RuntimeError):
                    publisher.publish(
                        "boom-slug", _spec(), intent="open: x; bet: y", skill="report",
                        date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                        verdict=_passing_proof("boom-slug", _spec(), "open: x; bet: y"),
                    )
            finally:
                render.spec_to_html = orig
            self.assertFalse((blog / "boom-slug.html").exists())
            self.assertEqual(list(blog.glob("*.tmp")) if blog.exists() else [], [])


class PublishIsRecoverableAfterTheCommit(unittest.TestCase):
    """Codex round-10 [high]: the commit point is the atomic `artefato.published` (WITH the
    spec) + `intent.kernel` append (ADR-0006: the log is truth). EVERYTHING after it — the page
    write, the source signals — is a recoverable PROJECTION re-derivable from the logged spec +
    cites. A failure after the commit (os.replace/write_text/_signal_cites raising) no longer
    strands an UNRECOVERABLE state: `reproject_missing_pages` re-renders the missing page from
    the logged spec (byte-identical to a normal publish) and re-emits any missing source signals."""

    def test_page_write_failure_after_commit_is_recoverable_from_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            slug = "recoverable"
            intent = "open: x; bet: y"
            cites = [{"ref": "arXiv:1", "kind": "mundo", "snippet": "snip"}]
            # force os.replace to raise AFTER the atomic commit (page never lands)
            orig_replace = os.replace
            os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
            try:
                with self.assertRaises(OSError):
                    publisher.publish(
                        slug, _spec(), intent=intent, skill="report", cites=cites,
                        date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                        verdict=_passing_proof(slug, _spec(), intent, cites=cites),
                    )
            finally:
                os.replace = orig_replace

            # NOT unrecoverable: the commit landed (log is truth) and it carries the spec
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], [slug])
            published = eventlog.read(types=["artefato.published"], log=log)
            self.assertEqual(published[0]["payload"]["spec"], _spec())
            # but the page is missing (the projection failed)
            self.assertFalse((blog / f"{slug}.html").exists())

            # recovery: reproject the missing page from the logged spec
            redone = publisher.reproject_missing_pages(
                log=log, blog_dir=blog, date="2026-06-08")
            self.assertEqual([Path(p).name for p in redone], [f"{slug}.html"])
            self.assertTrue((blog / f"{slug}.html").exists())

    def test_reprojected_page_byte_matches_a_normal_publish(self):
        spec = _spec()
        intent = "open: x; bet: y"
        cites = [{"ref": "arXiv:1", "kind": "mundo", "snippet": "snip"}]
        # (1) a normal, clean publish → the reference page bytes
        with tempfile.TemporaryDirectory() as tmp_ok:
            log_ok = Path(tmp_ok) / "log.jsonl"
            blog_ok = Path(tmp_ok) / "entries"
            slug = "byte-match"
            publisher.publish(
                slug, spec, intent=intent, skill="report", cites=cites,
                date="2026-06-08", log=log_ok, blog_dir=blog_ok, embed_fn=_fake_embed,
                verdict=_passing_proof(slug, spec, intent, cites=cites))
            reference = (blog_ok / f"{slug}.html").read_bytes()

        # (2) a publish whose page write fails after the commit, then reproject
        with tempfile.TemporaryDirectory() as tmp_bad:
            log_bad = Path(tmp_bad) / "log.jsonl"
            blog_bad = Path(tmp_bad) / "entries"
            slug = "byte-match"
            orig_replace = os.replace
            os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
            try:
                with self.assertRaises(OSError):
                    publisher.publish(
                        slug, spec, intent=intent, skill="report", cites=cites,
                        date="2026-06-08", log=log_bad, blog_dir=blog_bad,
                        embed_fn=_fake_embed,
                        verdict=_passing_proof(slug, spec, intent, cites=cites))
            finally:
                os.replace = orig_replace
            publisher.reproject_missing_pages(
                log=log_bad, blog_dir=blog_bad, date="2026-06-08")
            regenerated = (blog_bad / f"{slug}.html").read_bytes()

        self.assertEqual(regenerated, reference)  # byte-identical projection

    def test_signal_failure_after_commit_does_not_corrupt_the_page_and_is_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            slug = "signal-fails"
            intent = "open: x; bet: y"
            cites = [{"ref": "arXiv:1", "kind": "mundo", "snippet": "snip"}]
            # force the source-signal emission to raise AFTER the commit + page write
            orig_signal = eventlog.source_signal
            eventlog.source_signal = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("signal store down"))
            try:
                path = publisher.publish(
                    slug, _spec(), intent=intent, skill="report", cites=cites,
                    date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                    verdict=_passing_proof(slug, _spec(), intent, cites=cites))
            finally:
                eventlog.source_signal = orig_signal

            # the page is published cleanly (a signal failure is non-fatal to the page)
            self.assertTrue(Path(path).exists())
            # the signal did not land (it failed) — but it is recoverable from the logged cites
            self.assertEqual(eventlog.source_yield_at(log=log), {})
            publisher.reproject_missing_pages(
                log=log, blog_dir=blog, date="2026-06-08", embed_fn=_fake_embed)
            yields = eventlog.source_yield_at(log=log)
            self.assertIn("arXiv:1", yields)
            self.assertEqual(yields["arXiv:1"]["count"], 1)

    def test_reproject_is_a_noop_when_pages_and_signals_already_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            slug = "already-there"
            intent = "open: x; bet: y"
            cites = [{"ref": "arXiv:1", "kind": "mundo", "snippet": "snip"}]
            publisher.publish(
                slug, _spec(), intent=intent, skill="report", cites=cites,
                date="2026-06-08", log=log, blog_dir=blog, embed_fn=_fake_embed,
                verdict=_passing_proof(slug, _spec(), intent, cites=cites))
            before = (blog / f"{slug}.html").read_bytes()
            redone = publisher.reproject_missing_pages(
                log=log, blog_dir=blog, date="2026-06-08", embed_fn=_fake_embed)
            self.assertEqual(redone, [])  # nothing missing → nothing reprojected
            self.assertEqual((blog / f"{slug}.html").read_bytes(), before)
            # the signal count did not double (already-landed signals are not re-emitted)
            self.assertEqual(eventlog.source_yield_at(log=log)["arXiv:1"]["count"], 1)


@unittest.skipUnless(_NEO4J, "neo4j not reachable (live lineage-edge projection test)")
class LineageEdgesAreDirectedInTheLiveGraph(unittest.TestCase):
    """Cortex-v1 (brick-1, L4) — LIVE: project_artefato materializes the authored typed lineage
    as DIRECTED graph edges this -> prior. Gated on a reachable Neo4j (~/edge-experiments/.venv);
    uses dedicated `cv1l-*` test slugs and DETACH-DELETEs them on teardown so it leaves the
    install graph clean. Asserts: (1) supersedes lands the directed edge this -> prior; (2) the
    REVERSE edge does NOT exist; (3) a corrected republish REMOVES the stale edge."""

    THIS = "cv1l-this"
    PRIOR = "cv1l-prior"
    OTHER = "cv1l-other"

    def _session(self):
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        self._g = _identity.require_group()
        self._drv = GraphDatabase.driver(uri, auth=(user, pw))
        return self._drv.session()

    def _cleanup(self, s):
        s.run("MATCH (a:Artefato {group_id:$g}) WHERE a.slug IN $slugs DETACH DELETE a",
              g=self._g, slugs=[self.THIS, self.PRIOR, self.OTHER])

    def setUp(self):
        self.s = self._session()
        self._cleanup(self.s)
        # pre-create the prior :Artefato nodes the lineage points at (the "prior already landed"
        # path) — bare MERGE, no objective/embed dependency, so the edge MERGE can match.
        for slug in (self.PRIOR, self.OTHER):
            self.s.run("MERGE (a:Artefato {group_id:$g, slug:$slug})", g=self._g, slug=slug)

    def tearDown(self):
        try:
            self._cleanup(self.s)
        finally:
            self.s.close()
            self._drv.close()

    def _edge(self, frm, label, to):
        return self.s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$frm})-[r:%s]->"
            "(b:Artefato {group_id:$g, slug:$to}) RETURN count(r) AS n" % label,
            g=self._g, frm=frm, to=to).single()["n"]

    def test_supersedes_lands_directed_and_corrected_republish_removes_stale(self):
        # (1) project with supersedes -> prior: the directed edge this -> prior exists...
        _REAL_PROJECT(self.THIS, "open: x; bet: y", skill="report",
                      lineage=[{"type": "supersedes", "target": self.PRIOR}],
                      log="/tmp/cv1l-noncanonical.jsonl")  # non-canonical: ADD-only, no backbone
        self.assertEqual(self._edge(self.THIS, "SUPERSEDES", self.PRIOR), 1,
                         "supersedes must land the directed edge this -> prior")
        # (2) ...and the REVERSE edge does NOT exist (direction is unrecoverable, must be exact)
        self.assertEqual(self._edge(self.PRIOR, "SUPERSEDES", self.THIS), 0,
                         "the reverse lineage edge must NOT exist (direction is load-bearing)")
        # (3) a corrected republish (now supersedes OTHER, not PRIOR) removes the stale edge.
        _REAL_PROJECT(self.THIS, "open: x; bet: y", skill="report",
                      lineage=[{"type": "supersedes", "target": self.OTHER}],
                      log="/tmp/cv1l-noncanonical.jsonl")
        self.assertEqual(self._edge(self.THIS, "SUPERSEDES", self.PRIOR), 0,
                         "the corrected republish must remove the stale supersedes edge")
        self.assertEqual(self._edge(self.THIS, "SUPERSEDES", self.OTHER), 1,
                         "the corrected republish must land the new supersedes edge")


class AdoptionTelemetryEventAtPublish(unittest.TestCase):
    """R6 (S10): publish emits a durable `artefato.adoption` event (producer / owed / satisfied /
    degraded / shortfall / capability_state), so adoption is read off the EVENT STREAM at publish-time,
    never reconstructed from a retrospective corpus scan."""

    def _publish_and_read(self, slug, spec, *, skill="report", cites=None, visual_flags=None):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            intent = "next bet: measure adoption"
            publisher.publish(
                slug, spec, intent=intent, skill=skill, cites=cites or [], date="2026-06-18",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, visual_flags=visual_flags,
                verdict=_passing_proof(slug, spec, intent, cites=cites or [], skill=skill))
            events = eventlog.read(types=["artefato.adoption"], log=log)
            self.assertTrue(events, "publish emitted no artefato.adoption event")
            return events[-1]["payload"]

    def test_prose_only_report_owes_no_visual(self):
        p = self._publish_and_read("adopt-prose", _spec())
        self.assertEqual(p["producer"], "report")
        self.assertFalse(p["owed"])
        self.assertFalse(p["satisfied"])

    def test_quant_artefato_with_visual_is_owed_and_satisfied(self):
        spec = {"sections": [{"title": "Data", "blocks": [
            {"type": "paragraph", "text": "Win rate hit 42%, a 3x speedup, and 88 points — explained here."},
            {"type": "metrics-grid", "items": [{"value": "42%", "label": "win"},
                                               {"value": "3x", "label": "speedup"}]}]}]}
        p = self._publish_and_read("adopt-quant", spec)
        self.assertTrue(p["owed"])
        self.assertTrue(p["satisfied"])

    def test_producer_supplied_dict_flags_are_recorded(self):
        p = self._publish_and_read("adopt-flags", _spec(),
                                   visual_flags={"degraded": True, "shortfall": True})
        self.assertTrue(p["degraded"])
        self.assertTrue(p["shortfall"])

    def test_add_visuals_list_flags_are_recorded(self):
        # Codex S10: the REAL shape — visuals.add_visuals returns list[str], not a dict. The publisher must
        # derive shortfall/degraded from it (else a real publish reports false-healthy adoption).
        flags = ["shortfall: 2 spot(s) selected, 1 grounded",
                 "dropped spot 1 (chart): chart datum not attributable to the evidence"]
        p = self._publish_and_read("adopt-listflags", _spec(), visual_flags=flags)
        self.assertTrue(p["shortfall"])
        # a degradation marker in the list is reflected too
        p2 = self._publish_and_read("adopt-degr", _spec(),
                                    visual_flags=["degraded: ascii fallback (vl-convert absent)"])
        self.assertTrue(p2["degraded"])

    def test_capability_state_matches_render_backend(self):
        p = self._publish_and_read("adopt-cap", _spec())
        self.assertEqual(p["capability_state"], render.diagram_available())

    def test_numeric_dense_executive_summary_is_owed(self):
        # Codex S10: a numeric-dense executive_summary with no visual still OWES — render renders the
        # summary as prose, so adoption must not be under-counted at the source.
        spec = {"executive_summary": ["AUC 85.0, exact_match 0.167, and a 4% delta this run."],
                "sections": [{"title": "B", "blocks": [
                    {"type": "paragraph", "text": "Plain prose body with no numbers."}]}]}
        p = self._publish_and_read("adopt-summary", spec)
        self.assertTrue(p["owed"])
        self.assertFalse(p["satisfied"])     # numbers owed a visual, none rendered → adoption shortfall

    def test_metrics_only_artefato_is_owed_and_satisfied(self):
        # Codex S10: a top-level metrics grid is BOTH the owed quantitative material AND the satisfying
        # visual — owed and satisfied must agree (never satisfied-but-not-owed, which corrupts the ratio).
        spec = {"metrics": [{"value": "42%", "label": "win rate"}, {"value": "3x", "label": "speedup"}],
                "sections": [{"title": "B", "blocks": [
                    {"type": "paragraph",
                     "text": "Prose explaining the dashboard above: win rate hit 42% at a 3x speedup."}]}]}
        p = self._publish_and_read("adopt-metrics-only", spec)
        self.assertTrue(p["owed"])
        self.assertTrue(p["satisfied"])

    def test_section_metrics_grid_only_is_owed_and_satisfied(self):
        # Codex S10: a SECTION-level metrics-grid block (no numeric prose, no descriptor-form) is a
        # substantive visual → satisfied; it must therefore also be owed (satisfied ⟹ owed).
        spec = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "Prose explaining the grid below: win rate 42% and a 3x speedup."},
            {"type": "metrics-grid", "items": [{"value": "42%", "label": "win"},
                                               {"value": "3x", "label": "speedup"}]}]}]}
        p = self._publish_and_read("adopt-section-metrics", spec)
        self.assertTrue(p["owed"])
        self.assertTrue(p["satisfied"])

    def test_telemetry_failure_still_emits_an_adoption_event(self):
        # Codex S10: if the adoption computation fails (schema drift / capability-probe error), publish
        # must STILL commit an adoption event (with an `error` marker) — never silently drop it, never
        # block the page. Force render.diagram_available to raise during the publish.
        orig = render.diagram_available
        render.diagram_available = lambda: (_ for _ in ()).throw(RuntimeError("probe boom"))
        try:
            p = self._publish_and_read("adopt-boom", _spec())
        finally:
            render.diagram_available = orig
        self.assertEqual(p["producer"], "report")
        self.assertIsNotNone(p.get("error"))          # the failure is recorded, not swallowed
        self.assertIn("probe boom", p["error"])
        # Codex S10: an errored record exposes NULL on EVERY countable field — never a partially-computed
        # or default-False boolean a dashboard would count.
        for f in ("owed", "satisfied", "degraded", "shortfall", "capability_state"):
            self.assertIsNone(p[f], f"{f} leaked a countable value on an errored telemetry record")

    def test_eventlog_publish_boundary_always_emits_adoption(self):
        # Codex S10: the eventlog publish boundary itself synthesizes an adoption event when none is
        # supplied — no caller (legacy publish_artefato, a direct call) can commit a published artefato
        # with zero adoption telemetry.
        import eventlog as _el
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _el.dispatch_open(log=log)
            _el.publish_artefato("boundary-slug", "open: x; bet: y", log=log)
            events = _el.read(types=["artefato.adoption"], log=log)
            self.assertTrue(events, "the eventlog publish boundary committed no adoption event")
            self.assertEqual(events[-1]["payload"]["error"], "no-adoption-supplied")

    def test_eventlog_boundary_normalizes_a_malformed_adoption_payload(self):
        # Codex S10: a partial/malformed adoption dict must NOT pass through as usable telemetry — the
        # boundary replaces it with an error-marked record whose countable fields are all null.
        import eventlog as _el
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _el.dispatch_open(log=log)
            _el.publish_artefato_atomic("malformed-slug", "open: x; bet: y", skill="report",
                                        log=log, adoption={"owed": True})  # partial dict
            p = _el.read(types=["artefato.adoption"], log=log)[-1]["payload"]
            self.assertEqual(p["error"], "malformed-adoption")
            for f in ("owed", "satisfied", "degraded", "shortfall", "capability_state"):
                self.assertIsNone(p[f], f"{f} leaked from a malformed payload")

    def test_eventlog_boundary_nulls_an_errored_countable_payload(self):
        # Codex S10: a full-shaped payload that ALSO carries an `error` (or non-bool countable fields) must
        # NOT be counted — the boundary nulls all countable fields while preserving the error message.
        import eventlog as _el
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _el.dispatch_open(log=log)
            bad = {"owed": False, "satisfied": False, "degraded": False, "shortfall": False,
                   "capability_state": True, "error": "probe boom"}
            _el.publish_artefato_atomic("errored-slug", "open: x; bet: y", skill="report",
                                        log=log, adoption=bad)
            p = _el.read(types=["artefato.adoption"], log=log)[-1]["payload"]
            self.assertEqual(p["error"], "probe boom")        # message preserved
            for f in ("owed", "satisfied", "degraded", "shortfall", "capability_state"):
                self.assertIsNone(p[f], f"{f} stayed countable on an errored record")

    def test_non_bool_dict_flags_are_not_coerced_to_countable(self):
        # Codex S10: bool("false") is True — a non-bool dict flag must NOT become countable telemetry; it
        # is recorded as an all-null error instead.
        p = self._publish_and_read("adopt-strflags", _spec(),
                                   visual_flags={"degraded": "false", "shortfall": "false"})
        self.assertIsNotNone(p.get("error"))
        for f in ("owed", "satisfied", "degraded", "shortfall", "capability_state"):
            self.assertIsNone(p[f], f"{f} was coerced from a non-bool flag")

    def test_countable_record_requires_a_real_producer(self):
        # Codex S10: a full-bool payload with NO valid producer (skill) must not be countable — it becomes
        # an all-null malformed record (per-producer telemetry needs a real producer).
        import eventlog as _el
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _el.dispatch_open(log=log)
            payload = {"owed": True, "satisfied": True, "degraded": False, "shortfall": False,
                       "capability_state": True, "error": None}
            _el.publish_artefato_atomic("noskill-slug", "open: x; bet: y", skill=None,
                                        log=log, adoption=payload)
            p = _el.read(types=["artefato.adoption"], log=log)[-1]["payload"]
            self.assertEqual(p["error"], "malformed-adoption")
            for f in ("owed", "satisfied", "degraded", "shortfall", "capability_state"):
                self.assertIsNone(p[f])

    def test_tuple_visual_flags_are_an_errored_record(self):
        # Codex S10: the contract is dict/list/None — a tuple is not a list; it must yield an all-null
        # errored record, not coerced countable flags.
        p = self._publish_and_read("adopt-tupleflags", _spec(),
                                   visual_flags=("shortfall: x", "dropped spot 1"))
        self.assertIsNotNone(p.get("error"))
        for f in ("degraded", "shortfall"):
            self.assertIsNone(p[f])

    def test_eventlog_boundary_overwrites_caller_producer(self):
        # Codex S10: a caller cannot misattribute the producer — the boundary overwrites it from skill.
        import eventlog as _el
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _el.dispatch_open(log=log)
            payload = {"slug": "x", "producer": "map", "owed": True, "satisfied": True,
                       "degraded": False, "shortfall": False, "capability_state": True, "error": None}
            _el.publish_artefato_atomic("attrib-slug", "open: x; bet: y", skill="report",
                                        log=log, adoption=payload)
            p = _el.read(types=["artefato.adoption"], log=log)[-1]["payload"]
            self.assertEqual(p["producer"], "report")   # not the caller's "map"

    def test_form_owed_for_a_visual_descriptor_skill(self):
        # a `map` owes a visual by its DESCRIPTOR form even without quantitative content; _floored_spec
        # carries the ascii-diagrams + a callout (so R0 prose owe is met) → owed True.
        p = self._publish_and_read("adopt-map", _floored_spec(), skill="map")
        self.assertTrue(p["owed"])


class PublishCarriesResidualsFromTheProof(unittest.TestCase):
    """S6 (design-close §5): a publish-with-residuals proof carries `unaddressed`, and
    `publisher.publish` reads it OFF the proof (never a caller arg) → a first-class `residuals`
    field on the `artefato.published` event. A normal publish records residuals=None."""

    def test_residual_publish_records_unaddressed_on_the_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["EDGE_PUBLISH_WITH_RESIDUALS"] = "1"
            try:
                log = Path(tmp) / "log.jsonl"
                slug, spec, intent = "residual-page", _spec(), "open: x; bet: y"
                unaddressed = [{"reviewer": close.FEYNMAN_REVIEWER_ID,
                                "strikes": ["overstates the claim"],
                                "rationales": {"rigor": "why"}, "overall": 3.0}]
                verdicts = [
                    {"pass": False, "scores": {"rigor": 3}, "strikes": ["overstates the claim"],
                     "overall": 3.0, "reviewer": close.FEYNMAN_REVIEWER_ID},
                    {"pass": False, "scores": {"rigor": 3}, "strikes": ["overstates the claim"],
                     "overall": 3.0, "reviewer": close.REGULAR_REVIEWER_ID},
                ]
                proof = close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                                          cites=[], proposes=[], skill="report",
                                          residual_publish=True, unaddressed=unaddressed)
                publisher.publish(slug, spec, intent=intent, skill="report", date="2026-06-08",
                                  log=log, blog_dir=tmp, embed_fn=_fake_embed, verdict=proof)
                ev = eventlog.read(types=["artefato.published"], log=log)[-1]
                self.assertEqual(ev["payload"]["residuals"], unaddressed)
            finally:
                os.environ.pop("EDGE_PUBLISH_WITH_RESIDUALS", None)

    def test_normal_publish_records_residuals_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug, intent = "no-residual-page", "open: x; bet: y"
            publisher.publish(slug, _spec(), intent=intent, skill="report", date="2026-06-08",
                              log=log, blog_dir=tmp, embed_fn=_fake_embed,
                              verdict=_passing_proof(slug, _spec(), intent))
            ev = eventlog.read(types=["artefato.published"], log=log)[-1]
            self.assertIsNone(ev["payload"]["residuals"])
            self.assertIsNone(ev["payload"]["accepted_risks"])

    def test_risk_tags_are_read_from_the_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug, spec, intent = "risk-tag-page", _spec(), "open: x; bet: y"
            accepted_risks = [{
                "tag": "potential_overclaim",
                "claim": "the old Edge returned",
                "rationale": "strong mentor interpretation, not a closed fact",
            }]
            proof = _passing_proof(slug, spec, intent, accepted_risks=accepted_risks)
            publisher.publish(slug, spec, intent=intent, skill="report", date="2026-06-08",
                              log=log, blog_dir=tmp, embed_fn=_fake_embed, verdict=proof)
            ev = eventlog.read(types=["artefato.published"], log=log)[-1]
            self.assertEqual(ev["payload"]["accepted_risks"], accepted_risks)


if __name__ == "__main__":
    unittest.main()
