"""The two blind review gates (Close architecture, S7, ADR-0013).

ADR-0013: verification is BLIND by evidence-and-session, PROPERTY-NOT-SECTION. Two
reviewers judge the FINAL Artefato text — `feynman_review` (rigor + honesty) and
`regular_review` (clarity + craft). Each sees ONLY the artefato content + cites; it is
denied evidence, session, and briefing (the context-denial ladder's last rung). The dim
rubric is the legacy 9-dim DIMENSIONS minus the two report-welded dims
(structural_completeness, storytelling), rebalanced; each dim def is reworded from
"section X present" to "property X present anywhere, genuine + specific".

The LLM call is injectable (`complete_fn`) so these tests run offline; real runs pass a
make_client-backed completer on the review router (Grok) — model-blindness atop context-
blindness. A verdict is {pass, scores:{dim:0-5}, strikes:[...], overall:float}.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _artefato_with_hidden_context():
    """An artefato carrying SECRET non-published fields (evidence/session/briefing) that a
    blind reviewer must never see, alongside its published content + cites."""
    return {
        "slug": "recall-report",
        "content": {
            "sections": [
                {"title": "What I found", "blocks": [
                    {"type": "paragraph",
                     "text": "Recall improved once the cursor became a per-session watermark."},
                ]},
            ],
        },
        "cites": [
            {"ref": "github:abc123", "kind": "atividade", "relevant": True,
             "snippet": "switched the cursor to a per-session watermark"},
        ],
        "proposes": [{"body": "name the full-read budget", "kind": "constraint"}],
        "distills": ["cluster:recall"],
        "intent": "open: budget unnamed; bet: name it next beat",
        # ── non-published fields a blind reviewer is DENIED ──
        "evidence": "SECRET_EVIDENCE_TOKEN raw exa dump the author read",
        "session": "SECRET_SESSION_TOKEN the mentee's transcript",
        "briefing": "SECRET_BRIEFING_TOKEN the wake context",
    }


def _capturing_completer(verdict_json):
    """A fake complete_fn: records the messages/prompt it was handed, returns canned JSON."""
    captured = {}

    def complete_fn(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return verdict_json

    complete_fn.captured = captured
    return complete_fn


def _seen_text(captured):
    """Flatten everything the completer was handed (positional + kw) into one string."""
    parts = []
    for a in captured.get("args", ()):
        parts.append(repr(a))
    for v in captured.get("kwargs", {}).values():
        parts.append(repr(v))
    return " ".join(parts)


# A minimal valid verdict the fake completer can echo back.
_PASS_VERDICT = (
    '{"pass": true, "scores": {"content_depth": 4, "feynman_method": 4, '
    '"intellectual_honesty": 4, "didactic_clarity": 4, "internal_consistency": 4, '
    '"visualization": 4, "writing_quality": 4}, "strikes": [], "overall": 4.0}'
)
_STRIKE_VERDICT = (
    '{"pass": false, "scores": {"content_depth": 3, "feynman_method": 2, '
    '"intellectual_honesty": 2, "didactic_clarity": 3, "internal_consistency": 3, '
    '"visualization": 3, "writing_quality": 3}, '
    '"strikes": ["claim not re-sourceable from its cite"], "overall": 2.7}'
)

_KEPT = {"content_depth", "feynman_method", "intellectual_honesty", "didactic_clarity",
         "internal_consistency", "visualization", "writing_quality"}


class SevenDimsBlindAndPropertyNotSection(unittest.TestCase):
    """The S7 contract: exactly the 7 kept dims (dropped structural_completeness +
    storytelling); weights are a {dim:weight} dict summing to 1.0; the reviewers run blind
    (cites' content reaches the LLM, the secret evidence/session/briefing never does); the
    honesty/feynman dim text is property-not-section (says 'anywhere', not 'O que Não Sei');
    a claim not re-sourceable from its cite yields a strike."""

    def test_dimensions_are_exactly_the_seven_kept(self):
        self.assertEqual(set(close.DIMENSIONS), _KEPT)
        self.assertNotIn("structural_completeness", close.DIMENSIONS)
        self.assertNotIn("storytelling", close.DIMENSIONS)

    def test_weights_are_a_dict_over_the_seven_dims_summing_to_one(self):
        self.assertIsInstance(close.DIMENSION_WEIGHTS, dict)
        self.assertEqual(set(close.DIMENSION_WEIGHTS), _KEPT)
        self.assertAlmostEqual(sum(close.DIMENSION_WEIGHTS.values()), 1.0, places=6)

    def test_reviewer_sees_cites_content_but_never_evidence_session_or_briefing(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(_PASS_VERDICT)
        close.feynman_review(art, complete_fn=fn)
        seen = _seen_text(fn.captured)
        # the cite's content reaches the reviewer (blind = denied EVIDENCE, not denied cites)
        self.assertIn("switched the cursor to a per-session watermark", seen)
        self.assertIn("github:abc123", seen)
        # the non-published context is withheld
        self.assertNotIn("SECRET_EVIDENCE_TOKEN", seen)
        self.assertNotIn("SECRET_SESSION_TOKEN", seen)
        self.assertNotIn("SECRET_BRIEFING_TOKEN", seen)

    def test_regular_reviewer_is_also_blind(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(_PASS_VERDICT)
        close.regular_review(art, complete_fn=fn)
        seen = _seen_text(fn.captured)
        self.assertNotIn("SECRET_EVIDENCE_TOKEN", seen)
        self.assertNotIn("SECRET_SESSION_TOKEN", seen)
        self.assertNotIn("SECRET_BRIEFING_TOKEN", seen)

    def test_honesty_and_feynman_dims_are_property_not_section(self):
        honesty = close.DIMENSIONS["intellectual_honesty"].lower()
        feynman = close.DIMENSIONS["feynman_method"].lower()
        # property language: the boundary is checked ANYWHERE, location-agnostic
        self.assertIn("anywhere", honesty + feynman)
        # the legacy section-weld is gone
        self.assertNotIn("o que não sei", honesty)
        self.assertNotIn("o que nao sei", honesty)
        self.assertNotIn("o que não sei", feynman)
        self.assertNotIn("o que nao sei", feynman)

    def test_didactic_clarity_is_comprehension_not_a_glossary_section(self):
        clarity = close.DIMENSIONS["didactic_clarity"].lower()
        self.assertIn("somewhere", clarity)
        self.assertNotIn("glossary section", clarity)

    def test_a_claim_not_resourceable_from_its_cite_yields_a_strike(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(_STRIKE_VERDICT)
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])
        self.assertTrue(verdict["strikes"], "expected a strike on an unsourceable claim")
        self.assertTrue(any("re-sourceable" in s or "cite" in s for s in verdict["strikes"]))

    def test_verdict_shape_scores_keyed_by_dim(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(_PASS_VERDICT)
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertTrue(verdict["pass"])
        self.assertEqual(set(verdict["scores"]), _KEPT)
        self.assertIsInstance(verdict["overall"], float)


if __name__ == "__main__":
    unittest.main(verbosity=2)
