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
import eventlog  # noqa: E402
import publisher  # noqa: E402


def _fake_embed(text):
    """An offline embedder: a tiny deterministic 2-vector, never an OpenAI call."""
    return [float(len(text)), 1.0]


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
                log=log, blog_dir=tmp, embed_fn=_fake_embed,
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
                    )
            # nothing published — C3 refused the close before any state landed
            self.assertEqual(eventlog.corpus_at(log=log), [])


if __name__ == "__main__":
    unittest.main()
