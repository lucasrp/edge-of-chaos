"""S-COHERENCE (conductor integration, Goal 3 slice 4) — the cross-node coherence gate (Q5), wired
INTO the circuit-breaker so a coherence/diversity failure forces ship:false and rides the attestation.

Pass = zero coherence strikes AND diversity in-band. The coherence reviewer is INJECTED (the skill's own
whole-doc subagent), so the dark path / offline default is unchanged (coherence_fn=None => no check).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))
import conductor  # noqa: E402
import assembly  # noqa: E402
from test_conductor_circuit_breaker import _SEED, _OBJECTIVE, _writer  # noqa: E402 — known-good harness


class CircuitBreakerFoldsCoherenceAndDiversity(unittest.TestCase):
    def test_coherence_flag_fails_closed(self):
        cb = conductor.circuit_breaker({"coherence_flags": ["cross-node contradiction"]})
        self.assertFalse(cb["ship"])
        self.assertIn("coherence:cross-node contradiction", cb["blocking"])

    def test_diversity_violation_is_advisory_not_a_hard_gate(self):
        # uncalibrated diversity over-fires on normal prose-only multi-node output, so it is REPORTED, never
        # a hard ship gate (codex review) — the coherence reviewer is the gate, not the self-bleu heuristic.
        cb = conductor.circuit_breaker({"diversity": {"violations": ["distinct-signatures 0.2 < 0.5"]}})
        self.assertTrue(cb["ship"])
        self.assertFalse(any(b.startswith("diversity:") for b in cb["blocking"]))

    def test_clean_ships(self):
        cb = conductor.circuit_breaker({"coherence_flags": [], "diversity": {"violations": []}})
        self.assertTrue(cb["ship"])


class RunConductorWiresCoherence(unittest.TestCase):
    def test_injected_coherence_flag_blocks_and_rides_the_attestation(self):
        # the coherence reviewer flags → result.coherence_flags → blocking → ship:false → the assembly
        # facts carry the failing verdict, so check_genus (S-ATTEST) blocks publish (A7).
        result = conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True,
                                         coherence_fn=lambda spec: ["duplicated framing"])
        self.assertEqual(result["coherence_flags"], ["duplicated framing"])
        self.assertFalse(result["ship"])
        self.assertTrue(any(b.startswith("coherence:") for b in result["blocking"]))
        facts = assembly.assembly_facts(result, _SEED)
        self.assertFalse(facts["conductor_ship"])
        self.assertTrue(facts["blocking"])

    def test_coherence_fn_receives_the_conciliated_deep_spec(self):
        seen = {}

        def coherence_fn(spec):
            seen["spec"] = spec
            return []
        result = conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True,
                                         coherence_fn=coherence_fn)
        self.assertIs(seen.get("spec"), result["deep_spec"])

    def test_coherence_fn_none_is_dark(self):
        result = conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True)
        self.assertEqual(result["coherence_flags"], [])

    def test_off_path_has_empty_coherence_flags(self):
        result = conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=False)
        self.assertEqual(result["coherence_flags"], [])
        self.assertTrue(result["ship"])   # nothing produced, nothing to block


if __name__ == "__main__":
    unittest.main()
