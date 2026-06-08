"""The two blind review gates (Close architecture, S7, ADR-0013).

ADR-0013: verification is BLIND by evidence-and-session, PROPERTY-NOT-SECTION. Two
reviewers judge the FINAL Artefato text — `feynman_review` (rigor + honesty) and
`regular_review` (clarity + craft). Each sees ONLY the artefato content + cites; it is
denied evidence, session, and briefing (the context-denial ladder's last rung). The dim
rubric is the legacy 9-dim DIMENSIONS with the depth dims RESTORED — development_completeness
+ narrative_depth carry the depth/arc the rewrite had dropped — but reworded PROPERTY-NOT-SECTION:
"property X present anywhere, genuine + specific", never "section X present" (SECTIONS stay FREE).

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
    '{"pass": true, "scores": {"development_completeness": 4, "narrative_depth": 4, '
    '"content_depth": 4, "feynman_method": 4, '
    '"intellectual_honesty": 4, "didactic_clarity": 4, "internal_consistency": 4, '
    '"visualization": 4, "writing_quality": 4}, "strikes": [], "overall": 4.0}'
)
_STRIKE_VERDICT = (
    '{"pass": false, "scores": {"development_completeness": 2, "narrative_depth": 2, '
    '"content_depth": 3, "feynman_method": 2, '
    '"intellectual_honesty": 2, "didactic_clarity": 3, "internal_consistency": 3, '
    '"visualization": 3, "writing_quality": 3}, '
    '"strikes": ["factual claim not re-sourceable from its cite"], "overall": 2.4}'
)

_KEPT = {"development_completeness", "narrative_depth", "content_depth", "feynman_method",
         "intellectual_honesty", "didactic_clarity", "internal_consistency", "visualization",
         "writing_quality"}


class NineDimsBlindAndPropertyNotSection(unittest.TestCase):
    """The S7 contract: exactly the 9 dims (depth RESTORED — development_completeness +
    narrative_depth — without re-introducing the old section-order mandate); weights are a
    {dim:weight} dict summing to 1.0; the reviewers run blind (cites' content reaches the LLM,
    the secret evidence/session/briefing never does); the honesty/feynman dim text is
    property-not-section (says 'anywhere', not 'O que Não Sei'); a FACTUAL claim not
    re-sourceable from its cite yields a strike."""

    def test_dimensions_are_exactly_the_nine(self):
        self.assertEqual(set(close.DIMENSIONS), _KEPT)
        # the OLD section-mandate dims stay gone — depth is back as PROPERTY, not section order
        self.assertNotIn("structural_completeness", close.DIMENSIONS)
        self.assertNotIn("storytelling", close.DIMENSIONS)
        self.assertIn("development_completeness", close.DIMENSIONS)
        self.assertIn("narrative_depth", close.DIMENSIONS)

    def test_weights_are_a_dict_over_the_nine_dims_summing_to_one(self):
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


class VerdictParsingFailsClosed(unittest.TestCase):
    """Codex round-7 [high]: a degraded/schema-drifted reviewer response must NEVER mint a
    pass. `_parse_verdict` coerced `pass` with `bool(...)`, so `{"pass":"false"}` became
    True. The fix fails closed: a verdict passes ONLY iff `result["pass"] is True` (exact
    boolean identity); ANY non-bool (`"false"`, `"true"`, None, missing, a number) is a
    schema/parse violation treated as FAILING. Malformed scores fail closed too."""

    def test_string_false_pass_is_a_failing_verdict(self):
        # bool("false") is True — the old coercion would mint a PASS from a FAILED review.
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": "false", "scores": {}, "strikes": ["x"]}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_string_true_pass_is_a_failing_verdict_non_bool(self):
        # a STRING "true" is still a schema drift — non-bool fails closed.
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": "true", "scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_real_bool_true_pass_passes(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": true, "scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertTrue(verdict["pass"])

    def test_real_bool_false_pass_fails(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": false, "scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_missing_pass_field_fails_closed(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_null_pass_fails_closed(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": null, "scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_numeric_pass_fails_closed(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": 1, "scores": {}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])

    def test_nonnumeric_score_fails_closed_not_coerced(self):
        # a malformed score (a string) must not crash or be silently coerced; the verdict
        # fails closed — it cannot become a passing verdict on the strength of a garbled score.
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(
            '{"pass": true, "scores": {"content_depth": "high"}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])
        self.assertIsInstance(verdict["overall"], float)  # no crash; overall still numeric

    def test_score_object_fails_closed(self):
        # a non-numeric, non-string score (a nested object) also fails closed without crashing.
        art = _artefato_with_hidden_context()
        fn = _capturing_completer(
            '{"pass": true, "scores": {"content_depth": {"nested": 4}}, "strikes": []}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])


class StruckVerdictFailsEvenWhenPassIsTrue(unittest.TestCase):
    """Codex round-9 [high]: a struck reviewer verdict must NEVER mint a passing verdict.
    `_parse_verdict` checked only `result['pass'] is True` and IGNORED a non-empty `strikes`
    list, so a canonical reviewer response `{"pass":true,"strikes":["uncited claim"]}` yielded
    a PASS despite the close protocol that ANY reviewer strike must bounce/fail. The fix:
    `passed = (result['pass'] is True) and not strikes` — a non-empty strikes list makes the
    verdict FAIL while the strikes are preserved for the bounce. A clean strikes:[] still passes.
    """

    def test_pass_true_with_strikes_is_a_failing_verdict(self):
        verdict = close._parse_verdict(
            '{"pass": true, "scores": {}, "strikes": ["uncited claim"]}')
        self.assertFalse(verdict["pass"])
        self.assertIn("uncited claim", verdict["strikes"])

    def test_pass_true_with_empty_strikes_still_passes(self):
        verdict = close._parse_verdict('{"pass": true, "scores": {}, "strikes": []}')
        self.assertTrue(verdict["pass"])

    def test_struck_verdict_through_feynman_reviewer_fails(self):
        art = _artefato_with_hidden_context()
        fn = _capturing_completer('{"pass": true, "scores": {}, "strikes": ["uncited claim"]}')
        verdict = close.feynman_review(art, complete_fn=fn)
        self.assertFalse(verdict["pass"])


class DegradedVerdictShapeNeverRaises(unittest.TestCase):
    """Codex round-8 [medium]: kill the WHOLE degraded-reviewer-output class, not just
    `scores:null`. `_parse_verdict` assumed `result['scores']` was a dict and called
    `.items()`/`.get()` on whatever it got — a degraded reviewer returning valid JSON like
    `{"pass":true,"scores":null}`, `scores:[]` (a list), `strikes:null`, or a non-dict
    `result` (a bare JSON list or string) raised AttributeError BEFORE it could fail closed,
    turning schema drift into an unhandled crash instead of a bounded failing verdict.

    The contract: `_parse_verdict` defensively validates the ENTIRE verdict shape and FAILS
    CLOSED (returns pass:false with an explanatory strike) on ANY shape violation, and NEVER
    raises for ANY input shape — `result` not a dict, `pass` not exactly True, `scores` not a
    dict, any score not a real int/float (bool excluded), `strikes` not a list."""

    def _parse(self, raw):
        """_parse_verdict must never raise for any input shape — assert that, then return."""
        try:
            return close._parse_verdict(raw)
        except Exception as e:  # noqa: BLE001 — the whole point is it must never raise
            self.fail(f"_parse_verdict raised on degraded shape {raw!r}: {e!r}")

    def _assert_failing(self, verdict):
        self.assertIs(verdict["pass"], False)
        self.assertIsInstance(verdict["scores"], dict)
        self.assertIsInstance(verdict["strikes"], list)
        self.assertIsInstance(verdict["overall"], float)
        self.assertTrue(verdict["strikes"], "a shape violation must carry an explanatory strike")

    def test_scores_null_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('{"pass": true, "scores": null, "strikes": []}'))

    def test_scores_list_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('{"pass": true, "scores": [], "strikes": []}'))

    def test_scores_string_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('{"pass": true, "scores": "nope", "strikes": []}'))

    def test_strikes_null_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('{"pass": true, "scores": {}, "strikes": null}'))

    def test_strikes_string_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('{"pass": true, "scores": {}, "strikes": "oops"}'))

    def test_result_is_a_json_list_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('[1, 2, 3]'))

    def test_result_is_a_json_string_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('"just a string"'))

    def test_result_is_a_json_number_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('42'))

    def test_result_is_json_null_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('null'))

    def test_invalid_json_does_not_raise_and_fails_closed(self):
        self._assert_failing(self._parse('not json at all {'))

    def test_well_formed_verdict_still_passes(self):
        verdict = self._parse(_PASS_VERDICT)
        self.assertIs(verdict["pass"], True)
        self.assertEqual(set(verdict["scores"]), _KEPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
