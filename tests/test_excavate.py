"""The synthetic-excavation stage (EDGE_EXCAVATE, dark by default).

excavate mines loop1's gathered evidence for the direction-relevant findings the
producer's thin summary DROPPED, before synthesis — the collapsed single-pass form of
the synthetic grill (four probes as a checklist: relevance, contradiction, surprise,
lineage). Gated by EDGE_EXCAVATE: OFF => passthrough (today's behavior, ZERO model
spend); ON => one injected `complete_fn` call -> an accountable seed.

The model call is INJECTED so the logic tests offline, exactly like close.py's reviewers.
The load-bearing guarantees under test:
  - OFF is a true no-op AND never spends a token (complete_fn untouched).
  - the prompt actually AIMS: it carries the direction and every probe.
  - the parser is tolerant of fenced/dirty model output and drops malformed findings.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import excavate  # noqa: E402


def _spy_complete(returns):
    """A complete_fn stub that records its calls and returns a canned string."""
    calls = {"count": 0, "prompts": []}

    def complete_fn(prompt):
        calls["count"] += 1
        calls["prompts"].append(prompt)
        return returns

    complete_fn.calls = calls
    return complete_fn


_GOOD_SEED = json.dumps({
    "findings": [
        {"claim": "store cost rises with size", "citation": "p.4 fig.2",
         "bears_on": "read:write bet", "probe": "surprise"},
        {"claim": "nothing forgets by default", "citation": "sec.3",
         "bears_on": "eviction rail", "probe": "contradiction"},
    ],
    "residuals": ["is the lag live at 50 entities?"],
})


class EnabledFlag(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(excavate.enabled(env={}))

    def test_truthy_variants_on(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            self.assertTrue(excavate.enabled(env={"EDGE_EXCAVATE": v}), v)

    def test_falsy_variants_off(self):
        for v in ("", "0", "false", "no", "off"):
            self.assertFalse(excavate.enabled(env={"EDGE_EXCAVATE": v}), v)


class DarkByDefault(unittest.TestCase):
    def test_off_is_passthrough_and_spends_nothing(self):
        spy = _spy_complete(_GOOD_SEED)
        seed = excavate.excavate("evidence", "thin summary", "the direction",
                                 spy, is_enabled=False)
        self.assertFalse(seed["enabled"])
        self.assertTrue(seed["passthrough"])
        self.assertEqual(seed["findings"], [])
        self.assertEqual(spy.calls["count"], 0, "OFF must never call the model")


class OnExtracts(unittest.TestCase):
    def test_on_calls_model_and_parses_findings(self):
        spy = _spy_complete(_GOOD_SEED)
        seed = excavate.excavate("evidence", "thin summary", "the direction",
                                 spy, is_enabled=True)
        self.assertTrue(seed["enabled"])
        self.assertEqual(spy.calls["count"], 1)
        self.assertEqual(len(seed["findings"]), 2)
        self.assertEqual(seed["residuals"], ["is the lag live at 50 entities?"])

    def test_prompt_aims_carries_direction_and_all_probes(self):
        spy = _spy_complete(_GOOD_SEED)
        excavate.excavate("EVID", "SUMM", "THE-DASHBOARD-BET", spy, is_enabled=True)
        prompt = spy.calls["prompts"][0]
        self.assertIn("THE-DASHBOARD-BET", prompt)
        for probe in excavate.PROBES:
            self.assertIn(probe, prompt.lower())


class TolerantParser(unittest.TestCase):
    def test_strips_code_fence(self):
        fenced = "```json\n" + _GOOD_SEED + "\n```"
        seed = excavate._parse_seed(fenced)
        self.assertEqual(len(seed["findings"]), 2)

    def test_drops_malformed_findings_keeps_valid(self):
        dirty = json.dumps({
            "findings": [
                {"claim": "ok", "citation": "c", "bears_on": "b", "probe": "relevance"},
                {"claim": "no citation"},          # malformed -> dropped
                "not even a dict",                  # malformed -> dropped
            ],
            "residuals": [],
        })
        seed = excavate._parse_seed(dirty)
        self.assertEqual(len(seed["findings"]), 1)
        self.assertEqual(seed["findings"][0]["claim"], "ok")

    def test_garbage_yields_empty_seed_not_crash(self):
        seed = excavate._parse_seed("the model refused and wrote prose")
        self.assertEqual(seed["findings"], [])
        self.assertEqual(seed["residuals"], [])


if __name__ == "__main__":
    unittest.main()
