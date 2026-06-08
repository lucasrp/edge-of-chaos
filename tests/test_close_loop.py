"""The bounce loop + the loop-2 brake (Close architecture, S8, ADR-0012/0013).

The close's gate is BOUNDED IN THE PROTOCOL, not in the producer's discretion — that
bound is what separates a gate from the retry-envelope ADR-0003 killed. Two module
constants pin it: `BOUNCE_MAX` (reviewer→producer re-produces) and `LOOP2_MAX_REOPENS`
(serendipity's advisory loop-1 reopens).

`run_close` runs BOTH blind reviewers on the artefato; on any strike/fail it BOUNCES
(re-produces via `produce_fn`) up to `BOUNCE_MAX` times, then HARD-FAILS — never an
unbounded loop. `run_loop2` is the producer-loop brake: the critic converges (emits a
`ship` boolean), serendipity is ADVISORY (may request a reopen, bounded by
`LOOP2_MAX_REOPENS`) and can NEVER hold the loop hostage.

`produce_fn`, `reviewers`, the reviewers' `complete_fn`, and the loop-2 roles are all
injectable so these tests run offline.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _reviewer_strikes_n_then_passes(n):
    """A reviewer stub that strikes its first `n` calls then passes. The `complete_fn`
    is accepted-and-ignored (kept in the signature so it stays injectable like the real
    reviewers)."""
    calls = {"count": 0}

    def reviewer(artefato, complete_fn=None):
        calls["count"] += 1
        if calls["count"] <= n:
            return {"pass": False, "scores": {}, "strikes": ["a strike"], "overall": 2.0}
        return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}

    reviewer.calls = calls
    return reviewer


def _reviewer_always_passes():
    def reviewer(artefato, complete_fn=None):
        return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}
    return reviewer


def _reviewer_always_strikes():
    def reviewer(artefato, complete_fn=None):
        return {"pass": False, "scores": {}, "strikes": ["a strike"], "overall": 2.0}
    return reviewer


def _counting_producer():
    """A produce_fn that counts its calls and returns a fresh artefato each time."""
    calls = {"count": 0}

    def produce_fn():
        calls["count"] += 1
        return {"slug": f"re-produced-{calls['count']}"}

    produce_fn.calls = calls
    return produce_fn


class BounceIsBoundedByProtocol(unittest.TestCase):
    """The bound lives in the protocol constants (BOUNCE_MAX / LOOP2_MAX_REOPENS), never
    in the producer's discretion. A single strike triggers exactly one re-produce then
    passes; an always-striking reviewer bounces exactly BOUNCE_MAX times then HARD-FAILS
    (no infinite loop). Loop-2: serendipity is advisory + bounded, and the critic's
    `ship` stops the loop immediately — serendipity can never hold it hostage."""

    def test_one_strike_triggers_exactly_one_reproduce_then_passes(self):
        produce_fn = _counting_producer()
        # one reviewer strikes once then passes; the other always passes.
        striker = _reviewer_strikes_n_then_passes(1)
        passer = _reviewer_always_passes()
        result = close.run_close(
            {"slug": "first-cut"}, produce_fn,
            reviewers=(striker, passer), complete_fn=lambda *a, **k: "",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(produce_fn.calls["count"], 1)  # exactly one re-produce

    def test_always_strikes_bounces_bounce_max_then_hard_fails(self):
        produce_fn = _counting_producer()
        always = _reviewer_always_strikes()
        result = close.run_close(
            {"slug": "first-cut"}, produce_fn,
            reviewers=(always, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
        )
        self.assertFalse(result["pass"])  # hard fail, no infinite loop
        self.assertEqual(produce_fn.calls["count"], close.BOUNCE_MAX)
        self.assertIn("verdicts", result)

    def test_serendipity_is_advisory_and_bounded_critic_converges(self):
        reopen_calls = {"count": 0}

        def reopen_fn():
            reopen_calls["count"] += 1
            return {"slug": "re-gathered"}

        # critic never wants to ship → only the reopen bound stops the loop.
        def critic_never_ships(artefato):
            return {"ship": False}

        # serendipity ALWAYS wants to diverge/reopen — it must NOT loop forever.
        def serendipity_always_reopens(artefato):
            return {"reopen": True}

        result = close.run_loop2(
            {"slug": "draft"}, critic_never_ships,
            serendipity_always_reopens, reopen_fn,
        )
        # serendipity is bounded by the protocol, never unbounded.
        self.assertEqual(reopen_calls["count"], close.LOOP2_MAX_REOPENS)
        self.assertFalse(result["ship"])

    def test_critic_ship_stops_loop_even_if_serendipity_wants_to_diverge(self):
        reopen_calls = {"count": 0}

        def reopen_fn():
            reopen_calls["count"] += 1
            return {"slug": "re-gathered"}

        def critic_ships(artefato):
            return {"ship": True}

        def serendipity_always_reopens(artefato):
            return {"reopen": True}  # still diverging, but cannot hold the loop hostage

        result = close.run_loop2(
            {"slug": "draft"}, critic_ships,
            serendipity_always_reopens, reopen_fn,
        )
        self.assertTrue(result["ship"])
        self.assertEqual(reopen_calls["count"], 0)  # ship wins; serendipity never gates


if __name__ == "__main__":
    unittest.main(verbosity=2)
