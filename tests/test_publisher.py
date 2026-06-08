"""The publisher — the close pipeline's atomic publish seam (ADR-0012/0013).

`publish` is `consolidate-state` minus session-digestion, de-YAML'd: it renders the
Artefato body via render.spec_to_html, wraps it in a self-contained neutral HTML page
that inlines tools/assets/base.css, writes it to blog/entries/<slug>.html, and ATOMICALLY
records state via the eventlog — the published event + its intent kernel in one act, so
`artefatos_without_kernel(log) == []` right after. C3 (no Artefato closes without a kernel)
is enforced at this seam: publishing without an intent raises.

These tests pin that seam offline (injected embed_fn, tempfile log + blog_dir).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import eventlog  # noqa: E402
import publisher  # noqa: E402


def _fake_embed(text):
    """An offline embedder: a tiny deterministic 2-vector, never an OpenAI call."""
    return [float(len(text)), 1.0]


def _passing_proof(slug, spec, intent, *, cites=None, proposes=None,
                   distills=None, skill="report"):
    """A BOUND passing proof for the exact payload — minted via close's PRIVATE `_mint_proof`
    the same way `run_close` mints it (run_close-only token + sha256 digest of
    slug+spec+intent+cites+proposes+distills+skill + both passing reviewer verdicts carrying
    the CANONICAL reviewer identities). This is the explicit TEST-ONLY seam standing in for
    run_close; it stamps the two canonical identities verify_proof requires. The publisher
    refuses anything not bound to the payload (and identities) it is actually publishing."""
    verdicts = [
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.FEYNMAN_REVIEWER_ID},
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
         "reviewer": close.REGULAR_REVIEWER_ID},
    ]
    return close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                             cites=cites or [], proposes=proposes or [],
                             distills=distills, skill=skill)


def _spec():
    return {
        "executive_summary": ["the seam holds"],
        "sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "atomic publish plus kernel in one act."},
        ]}],
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


if __name__ == "__main__":
    unittest.main()
