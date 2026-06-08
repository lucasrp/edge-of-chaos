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


def _passing_proof():
    """The proof token a passing close produces — two passing reviewer verdicts. Only
    `run_close` mints this in the live pipeline; a test forges it explicitly to stand in
    for the gate it stands behind."""
    return {"pass": True, "verdicts": [
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0},
        {"pass": True, "scores": {}, "strikes": [], "overall": 4.0},
    ]}


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

            path = publisher.publish(
                slug, _spec(), intent="next bet: pour the gate into the slot",
                skill="report", cites=cites, date="2026-06-08",
                log=log, blog_dir=tmp, embed_fn=_fake_embed, verdict=_passing_proof(),
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
                        verdict=_passing_proof(),
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
            }
            published = []

            def publish_fn(artefato, verdict):
                published.append(
                    publisher.publish(
                        artefato["slug"], artefato["content"], intent=artefato["intent"],
                        skill="report", date="2026-06-08", log=log, blog_dir=tmp,
                        embed_fn=_fake_embed, verdict=verdict,
                    )
                )

            def always_pass(artefato, complete_fn=None):
                return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}

            result = close.run_close(
                art, produce_fn=lambda: art, reviewers=(always_pass, always_pass),
                complete_fn=lambda *a, **k: "", publish_fn=publish_fn,
            )
            self.assertTrue(result["pass"])
            self.assertEqual(len(published), 1)              # published exactly once
            self.assertTrue((Path(tmp) / f"{slug}.html").exists())
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

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
                        verdict=_passing_proof(),
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
                verdict=_passing_proof(),
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
                        verdict=_passing_proof(),
                    )
            finally:
                render.spec_to_html = orig
            self.assertFalse((blog / "boom-slug.html").exists())
            self.assertEqual(list(blog.glob("*.tmp")) if blog.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
