# Issue #65 — the review gate cannot converge on rich content:
#   A. `pass` was left to the model's judgment; gpt-5.4 essentially never emits `pass:True`,
#      so even a STRIKELESS verdict (`{pass:false, strikes:[]}`) vetoed the mint. Derive `pass`
#      from strikes — the strikes are the documented blocking channel, `pass` is advisory.
#   B. a receding-target reviewer rewords a COSMETIC demand every round (hedge / label-as-inference
#      / gloss jargon / tone). Whether a strike is cosmetic or SUBSTANTIVE is a JUDGMENT, not a
#      keyword pattern — a SEMANTIC meta-gate (the codex/gpt-5.5 review completer, "codex gating
#      codex") decides it. Cosmetic-only → publish-with-criticism (S6); a substantive strike still
#      hard-fails.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import close      # noqa: E402
import _llm        # noqa: E402

# reuse the residuals-floor fixtures (canonical reviewers, knob env, conformant artefato)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_residuals_floor import (   # noqa: E402
    _conformant_artefato, _striking_reviewer, _KnobEnv)


def _judge(all_cosmetic):
    """A completer standing in for the semantic cosmetic judge (codex/gpt-5.5)."""
    payload = '{"all_cosmetic": %s, "rationale": "test"}' % ("true" if all_cosmetic else "false")
    return lambda prompt, *a, **k: payload


# =========================================================================================
# A. DERIVE `pass` FROM STRIKES — a strikeless pass:false no longer vetoes (proposal #1)
# =========================================================================================

class PassIsDerivedFromStrikes(unittest.TestCase):
    def test_strikeless_pass_false_parses_clean(self):
        # gpt-5.4's conservative veto: pass:false with NOTHING struck. The strikes are the
        # blocking channel; an unnamed veto is not actionable and must not block the mint.
        v = close._parse_verdict('{"pass": false, "scores": {"rigor": 4}, '
                                 '"strikes": [], "overall": 4.31}')
        self.assertTrue(v["pass"])
        self.assertTrue(close._verdict_clean(v))

    def test_a_named_strike_still_blocks_regardless_of_pass(self):
        v = close._parse_verdict('{"pass": true, "scores": {"rigor": 4}, '
                                 '"strikes": ["fabricated a source"], "overall": 4.0}')
        self.assertFalse(v["pass"])
        self.assertFalse(close._verdict_clean(v))

    def test_a_malformed_pass_string_fails_closed(self):
        # a `pass` that is present but NOT a boolean (the string "true") is schema drift, not an
        # advisory value — it strikes and fails closed even with no other strike.
        v = close._parse_verdict('{"pass": "true", "scores": {"rigor": 4}, '
                                 '"strikes": [], "overall": 4.0}')
        self.assertFalse(v["pass"])
        self.assertFalse(close._verdict_clean(v))

    def test_strikeless_false_reviewers_now_mint(self):
        # Both canonical reviewers return strikeless pass:false every round (the reported case).
        # Post-fix this is a clean close — a real proof mints, no residual/criticism attached.
        def strikeless_false(identity):
            def r(artefato, complete_fn=None):
                return {"pass": False, "scores": {"rigor": 4}, "strikes": [], "overall": 4.31}
            r.identity = identity
            return r
        result = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewers=(strikeless_false(close.FEYNMAN_REVIEWER_ID),
                       strikeless_false(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "")
        self.assertTrue(result.get("pass"))
        self.assertNotIn("residual_publish", result)


# =========================================================================================
# B1. THE SEMANTIC COSMETIC META-GATE — an LLM agent decides, fail-closed to substantive
# =========================================================================================

class SemanticCosmeticGate(unittest.TestCase):
    VERDICTS = [
        {"reviewer": close.FEYNMAN_REVIEWER_ID, "scores": {"rigor": 4},
         "strikes": ["isso soa mais forte do que a evidência; atenue"]},
        {"reviewer": close.REGULAR_REVIEWER_ID, "scores": {"clarity": 4},
         "strikes": ["glose o jargão"]},
    ]

    def test_true_only_when_agent_says_all_cosmetic(self):
        self.assertTrue(close._strikes_are_cosmetic(self.VERDICTS, _judge(True)))
        self.assertFalse(close._strikes_are_cosmetic(self.VERDICTS, _judge(False)))

    def test_the_agent_sees_every_strike_verbatim_in_its_prompt(self):
        seen = {}
        def spy(prompt, *a, **k):
            seen["prompt"] = prompt
            return '{"all_cosmetic": true}'
        close._strikes_are_cosmetic(self.VERDICTS, spy)
        self.assertIn("soa mais forte", seen["prompt"])
        self.assertIn("glose o jargão", seen["prompt"])

    def test_malformed_judge_response_fails_closed_to_substantive(self):
        self.assertFalse(close._strikes_are_cosmetic(self.VERDICTS, lambda *a, **k: "maybe?"))
        self.assertFalse(close._strikes_are_cosmetic(self.VERDICTS, lambda *a, **k: ""))
        # a well-formed JSON that is not exactly all_cosmetic:true is NOT a pass
        self.assertFalse(close._strikes_are_cosmetic(
            self.VERDICTS, lambda *a, **k: '{"all_cosmetic": "yes"}'))

    def test_no_completer_or_no_strikes_is_false(self):
        self.assertFalse(close._strikes_are_cosmetic(self.VERDICTS, None))
        self.assertFalse(close._strikes_are_cosmetic(
            [{"reviewer": close.FEYNMAN_REVIEWER_ID, "scores": {"x": 4}, "strikes": []}],
            _judge(True)))

    def test_transport_error_propagates_never_swallowed(self):
        def dead(*a, **k):
            raise _llm.LLMTransportError("quota dead", status=429)
        with self.assertRaises(_llm.LLMTransportError):
            close._strikes_are_cosmetic(self.VERDICTS, dead)


# =========================================================================================
# B2. INTEGRATION — cosmetic-only converges to graded publish; substance hard-fails
# =========================================================================================

class SubstanceAwareResidualPublish(unittest.TestCase):
    def test_cosmetic_only_publishes_with_criticism(self):
        # knob ON, bounce exhausted, both reviewers strike a demand the AGENT judges cosmetic →
        # publish-with-residuals (the criticism rides the section verbatim).
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            captured = {}
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=(_striking_reviewer(close.FEYNMAN_REVIEWER_ID,
                                              "isso soa mais forte do que a evidência; atenue"),
                           _striking_reviewer(close.REGULAR_REVIEWER_ID,
                                              "glose o jargão para o leitor")),
                complete_fn=_judge(True),
                publish_fn=lambda a, p: captured.update(art=a, proof=p))
            self.assertTrue(result.get("residual_publish"))
            self.assertIn("soa mais forte", str(captured["art"]["content"]))

    def test_agent_judged_substantive_disqualifies_and_hard_fails(self):
        # knob ON but the AGENT judges the criticism substantive → NEVER publish-with-residuals;
        # substance still hard-gates (the strengthening the issue asks for).
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            published = []
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=(_striking_reviewer(close.FEYNMAN_REVIEWER_ID,
                                              "a factual claim has no cite"),
                           _striking_reviewer(close.REGULAR_REVIEWER_ID,
                                              "the number is unsupported")),
                complete_fn=_judge(False),
                publish_fn=lambda a, p: published.append(a))
            self.assertFalse(result["pass"])
            self.assertNotIn("residual_publish", result)
            self.assertEqual(published, [])


if __name__ == "__main__":
    unittest.main()
