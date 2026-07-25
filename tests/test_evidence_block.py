"""Phase 0 — evidence-safety + authenticity (docs/plans/multi-writer-rich-ui.md).

The palette regained a verbatim-quote home (`evidence` block), and — beyond mere
preservation — every evidence block must be PROVABLY copied from its cited source:
it carries a `source_ref` and an `anchor` (sha256 of the verbatim span), and the
discharge check verifies the quote equals the referenced source span. Preservation
is not enough; authenticity must be provable. A paraphrase, a fabricated quote, a
wrong source_ref, or an altered span must all FAIL discharge; only a verbatim quote
with a correct anchor against the cited source passes.
"""
import hashlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import render  # noqa: E402

# A stand-in source corpus: source_ref -> full source text (e.g. a client message).
SOURCES = {
    "msg-42": "I keep hitting the same bug every single deploy and it is driving me up the wall.",
    "msg-7": "Honestly the dashboard is the only thing I actually open each morning.",
}


def _anchor(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence(quote, source_ref, anchor=None, attribution="client"):
    span = quote
    return {
        "type": "evidence",
        "quote_text": span,
        "source_ref": source_ref,
        "anchor": anchor if anchor is not None else _anchor(span),
        "attribution": attribution,
    }


class EvidenceBlockRenders(unittest.TestCase):
    def test_evidence_renders_verbatim_with_attribution(self):
        quote = "I keep hitting the same bug every single deploy and it is driving me up the wall."
        html = render.render_block(_evidence(quote, "msg-42", attribution="client, 2026-06-14"))
        self.assertIn(quote, html)               # verbatim, not paraphrased
        self.assertIn("client, 2026-06-14", html)  # attribution shown
        self.assertNotIn("<script", html.lower())  # escaped/safe

    def test_unknown_block_still_degrades_to_comment(self):
        # Regression guard: adding the renderer must not break the unknown-type fallback.
        self.assertIn("<!--", render.render_block({"type": "no-such-block-xyz"}))

    def test_quote_is_escaped_not_markdown_transformed(self):
        # A verbatim span with markdown-like syntax must render LITERALLY — never rewritten to
        # <strong>/<code>/<a>/em-dash, or the displayed evidence diverges from the anchored text.
        marky = "the **bug** in `deploy` -- see [docs](http://x) -- every time"
        html = render.render_block(_evidence(marky, "msg-42"))
        self.assertIn("**bug**", html)        # literal asterisks, not <strong>
        self.assertIn("`deploy`", html)       # literal backticks, not <code>
        self.assertIn("[docs](http://x)", html)  # literal link syntax, not <a>
        self.assertNotIn("<strong>", html)
        self.assertNotIn("<code>", html)
        self.assertNotIn("<a ", html)

    def test_multiline_quote_preserves_whitespace(self):
        # A multi-line / multi-space verbatim span must display byte-faithfully — the renderer
        # must opt out of HTML whitespace collapsing.
        q = "line one\n  indented two\n\nfour"
        html = render.render_block(_evidence(q, "msg-42"))
        self.assertIn("pre-wrap", html)   # whitespace-preserving display
        self.assertIn(q, html)            # newlines/spaces kept in the source

    def test_synonym_authored_block_renders_verbatim(self):
        # A block authored with the advertised `quote`/`source` synonyms must render the quote.
        q = SOURCES["msg-7"]
        blk = {"type": "evidence", "quote": q, "source": "msg-7", "anchor": _anchor(q)}
        self.assertIn(q, render.render_block(blk))


class EvidenceAuthenticity(unittest.TestCase):
    def test_verbatim_with_correct_anchor_passes(self):
        quote = SOURCES["msg-42"]
        ok, reason = render.verify_evidence(_evidence(quote, "msg-42"), SOURCES)
        self.assertTrue(ok, reason)

    def test_anchor_tamper_rejected(self):
        quote = SOURCES["msg-42"]
        blk = _evidence(quote, "msg-42", anchor=_anchor("something else"))
        ok, reason = render.verify_evidence(blk, SOURCES)
        self.assertFalse(ok)
        self.assertIn("anchor", reason.lower())

    def test_fabricated_quote_rejected(self):
        # Exact-looking quote that appears in NO cited source span.
        fake = "I think this system is absolutely perfect and needs no changes."
        ok, reason = render.verify_evidence(_evidence(fake, "msg-42"), SOURCES)
        self.assertFalse(ok)

    def test_wrong_source_ref_rejected(self):
        quote = SOURCES["msg-42"]
        ok, reason = render.verify_evidence(_evidence(quote, "msg-DOES-NOT-EXIST"), SOURCES)
        self.assertFalse(ok)

    def test_blank_source_ref_rejected_even_without_corpus(self):
        # preservation-only mode must still require a non-blank source attribution.
        for ref in ("", "   ", None):
            ok, reason = render.verify_evidence(_evidence(SOURCES["msg-42"], ref))
            self.assertFalse(ok, ref)
            self.assertIn("source_ref", reason)

    def test_altered_span_rejected(self):
        altered = SOURCES["msg-42"].replace("same bug", "same crash")
        ok, reason = render.verify_evidence(_evidence(altered, "msg-42"), SOURCES)
        self.assertFalse(ok)

    def test_synonym_authored_block_verifies(self):
        # `quote`/`source` synonyms must be honored by verification, not only by rendering.
        q = SOURCES["msg-7"]
        blk = {"type": "evidence", "quote": q, "source": "msg-7", "anchor": _anchor(q)}
        ok, reason = render.verify_evidence(blk, SOURCES)
        self.assertTrue(ok, reason)


class EvidenceDischargeSplit(unittest.TestCase):
    """A claim discharges by paraphrase; an EVIDENCE item discharges only by a verified
    verbatim quote. is_evidence_discharged is what the close/producer gate calls."""

    def test_paraphrase_is_not_evidence_discharge(self):
        paraphrase = "The client is frustrated by a recurring deploy bug."
        blk = _evidence(paraphrase, "msg-42")  # anchored to itself, but NOT in the source span
        self.assertFalse(render.is_evidence_discharged(blk, SOURCES))

    def test_verbatim_is_evidence_discharge(self):
        blk = _evidence(SOURCES["msg-7"], "msg-7")
        self.assertTrue(render.is_evidence_discharged(blk, SOURCES))

    def test_discharge_requires_a_corpus(self):
        # A well-anchored quote must NOT discharge without a source corpus — anchor-only is not
        # proof of authenticity (a fabricated quote can carry a self-consistent hash).
        blk = _evidence(SOURCES["msg-7"], "msg-7")
        self.assertFalse(render.is_evidence_discharged(blk, None))
        self.assertFalse(render.is_evidence_discharged(blk))  # default sources=None


if __name__ == "__main__":
    unittest.main(verbosity=2)
