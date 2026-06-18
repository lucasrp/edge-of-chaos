"""S9 (R5): the conductor's CUT-with-reason + severity-classified circuit-breaker. A dropped finding the
SEMANTIC JUDGE accepted as a non-blocking decline ships as a logged residual (status 'final'); a BLOCKING
finding (correctness drop the judge did NOT accept, grounding shortfall, gate/genus/shape violation, render
failure) FAILS CLOSED even at the cap — it can never become a residual. Crucially, decline acceptance is
REVIEWER-BOUND (read from the judge's discharge records), never a caller/producer parameter."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import conductor  # noqa: E402

_CLEAN = {"genus": {"deep": [], "synthetic": []}, "synthetic_shape": [],
          "visual_flags": [], "outline": [], "form_flags": [], "opener_flags": []}


def _result(**over):
    r = {k: (list(v) if isinstance(v, list) else dict(v)) for k, v in _CLEAN.items()}
    r.update(over)
    return r


def _node_dropping(fid, *, decline=None):
    """An outline node whose judge discharge record dropped `fid` (delivered:false), optionally with a
    reviewer-accepted decline."""
    return {"id": "n0", "discharge": [{"finding_id": fid, "delivered": False, "decline": decline}]}


_ACCEPTED = {"accepted": True, "severity": "non_blocking", "reason": "out of scope for this bet"}


class CircuitBreaker(unittest.TestCase):
    def test_clean_run_ships_final(self):
        v = conductor.circuit_breaker(_result())
        self.assertTrue(v["ship"])
        self.assertEqual(v["status"], "final")
        self.assertEqual(v["blocking"], [])

    def test_judge_accepted_decline_ships_as_logged_residual(self):
        # R5 acceptance (a): a dropped finding the JUDGE accepted as a non-blocking decline → residual.
        v = conductor.circuit_breaker(_result(outline=[_node_dropping("f3", decline=_ACCEPTED)]))
        self.assertTrue(v["ship"])
        self.assertEqual(v["status"], "final")
        self.assertEqual(v["residuals"], [{"finding_id": "f3", "reason": "out of scope for this bet"}])
        self.assertEqual(v["blocking"], [])

    def test_silent_dropped_finding_fails_closed(self):
        v = conductor.circuit_breaker(_result(outline=[_node_dropping("f3")]))   # no decline
        self.assertFalse(v["ship"])
        self.assertEqual(v["status"], "blocked")
        self.assertIn("dropped-finding:f3", v["blocking"])

    def test_blocking_severity_decline_still_blocks(self):
        d = {"accepted": True, "severity": "blocking", "reason": "x"}
        v = conductor.circuit_breaker(_result(outline=[_node_dropping("f3", decline=d)]))
        self.assertFalse(v["ship"])
        self.assertIn("dropped-finding:f3", v["blocking"])

    def test_unaccepted_decline_still_blocks(self):
        d = {"accepted": False, "severity": "non_blocking", "reason": "x"}
        v = conductor.circuit_breaker(_result(outline=[_node_dropping("f3", decline=d)]))
        self.assertFalse(v["ship"])

    def test_blank_reason_decline_still_blocks(self):
        d = {"accepted": True, "severity": "non_blocking", "reason": "   "}
        v = conductor.circuit_breaker(_result(outline=[_node_dropping("f3", decline=d)]))
        self.assertFalse(v["ship"])
        self.assertIn("dropped-finding:f3", v["blocking"])

    def test_delivered_finding_is_not_blocking(self):
        node = {"id": "n0", "discharge": [{"finding_id": "f0", "delivered": True, "decline": None}]}
        v = conductor.circuit_breaker(_result(outline=[node]))
        self.assertTrue(v["ship"])

    def test_grounding_shortfall_fails_closed_even_with_a_decline(self):
        # R5 acceptance (b): ungrounded data (R2) is BLOCKING — not declinable.
        r = _result(visual_flags=["shortfall: 2 spot(s) selected, 1 grounded"],
                    outline=[_node_dropping("f3", decline=_ACCEPTED)])
        v = conductor.circuit_breaker(r)
        self.assertFalse(v["ship"])
        self.assertTrue(any(b.startswith("grounding:") for b in v["blocking"]))

    def test_genus_violation_fails_closed(self):
        v = conductor.circuit_breaker(_result(genus={"deep": ["visual-coverage"], "synthetic": []}))
        self.assertFalse(v["ship"])
        self.assertIn("genus:deep:visual-coverage", v["blocking"])

    def test_synthetic_shape_violation_fails_closed(self):
        v = conductor.circuit_breaker(_result(synthetic_shape=["too-thin"]))
        self.assertFalse(v["ship"])
        self.assertIn("synthetic-shape:too-thin", v["blocking"])

    def test_render_failure_fails_closed(self):
        v = conductor.circuit_breaker(_result(), render_ok=False)
        self.assertFalse(v["ship"])
        self.assertIn("render:failed", v["blocking"])

    def test_per_node_gate_failure_fails_closed_even_with_clean_discharge(self):
        # Codex S9: a deterministic per-node contract-gate failure is BLOCKING and never declinable — a
        # clean (delivered) semantic discharge cannot clear it.
        node = {"id": "n0", "gate": ["empty node"],
                "discharge": [{"finding_id": "f0", "delivered": True, "decline": None}]}
        v = conductor.circuit_breaker(_result(outline=[node]))
        self.assertFalse(v["ship"])
        self.assertIn("gate:n0:empty node", v["blocking"])

    def test_quality_flags_are_non_blocking_residuals(self):
        r = _result(form_flags=["node 'n1' owed a structured form"], opener_flags=["weak opener"])
        v = conductor.circuit_breaker(r)
        self.assertTrue(v["ship"])
        self.assertEqual(len(v["residuals"]), 2)

    def test_decline_is_not_caller_attestable(self):
        # Codex S9 (trust boundary): circuit_breaker takes NO caller `declined` param — acceptance is read
        # only from the judge's discharge records. A dropped finding with no judge-accepted decline blocks.
        with self.assertRaises(TypeError):
            conductor.circuit_breaker(_result(outline=[_node_dropping("f3")]),
                                      declined={"f3": {"accepted": True, "severity": "non_blocking",
                                                       "reason": "self-attested"}})

    def test_run_conductor_off_carries_neutral_breaker_verdict(self):
        out = conductor.run_conductor({}, "obj", lambda *a, **k: "", is_enabled=False)
        self.assertTrue(out["ship"])
        self.assertEqual(out["status"], "final")
        self.assertEqual(out["blocking"], [])


_SEED = {"findings": [
    {"claim": "store cost rises with corpus size", "citation": "p.4", "bears_on": "the bet", "probe": "surprise"},
    {"claim": "nothing forgets by default", "citation": "sec.3", "bears_on": "eviction", "probe": "contradiction"},
    {"claim": "the briefing re-derives core memory", "citation": "docs", "bears_on": "frame", "probe": "lineage"}],
    "residuals": ["is the lag live at 50 entities?"], "enabled": True, "passthrough": False}
_OBJECTIVE = "spec the dashboard read panels off the briefing registry"


def _writer(prompt):
    claims = [ln for ln in prompt.splitlines() if ln.strip()]
    return ("Because the evidence shows it, it follows that " + " ".join(claims) +
            " — what i don't know: scale; this builds on prior work.")


def _judge_drops_all(prompt):
    if "SEMANTIC discharge reviewer" in prompt:
        return ('{"verdicts": [{"finding_id": "f0", "delivered": false}, '
                '{"finding_id": "f1", "delivered": false}, {"finding_id": "f2", "delivered": false}]}')
    return _writer(prompt)


def _judge_drops_but_accepts(prompt):
    # the judge drops every finding BUT accepts each as a non-blocking decline with a reason.
    if "SEMANTIC discharge reviewer" in prompt:
        rec = ('{"finding_id": "%s", "delivered": false, '
               '"decline": {"accepted": true, "severity": "non_blocking", "reason": "out of scope"}}')
        return '{"verdicts": [' + ", ".join(rec % f for f in ("f0", "f1", "f2")) + "]}"
    return _writer(prompt)


class CircuitBreakerWiredIntoRunConductor(unittest.TestCase):
    """R5 end-to-end (Codex S9): run_conductor applies the breaker, and decline acceptance is bound to the
    semantic JUDGE's output."""

    def test_dropped_findings_block_the_run(self):
        out = conductor.run_conductor(_SEED, _OBJECTIVE, _judge_drops_all, is_enabled=True)
        self.assertEqual(out["status"], "blocked")
        self.assertFalse(out["ship"])
        self.assertTrue(any(b.startswith("dropped-finding:") for b in out["blocking"]))

    def test_judge_accepted_declines_clear_the_dropped_findings(self):
        out = conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True,
                                      discharge_fn=_judge_drops_but_accepts)
        # the dropped findings are no longer blocking — the JUDGE accepted them as non-blocking residuals.
        self.assertFalse(any(b.startswith("dropped-finding:") for b in out["blocking"]))
        self.assertTrue(any(r.get("finding_id") in ("f0", "f1", "f2") for r in out["residuals"]))


if __name__ == "__main__":
    unittest.main()
