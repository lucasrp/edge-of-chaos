"""grill_gate — the post-grill stage-(ii) enforcement (Codex gate finding [high],
docs/briefing-lifecycle-audit.md).

A completed grill MUST NOT leave the stage-(ii) briefing sections empty. The audit's
acceptance for stage (ii) FAILS if Objective, Direction, or Direcionamento is still empty
after a grill: the feeders (`set_objective` / `report_direction` / direction set-or-propose)
must have run. The grill skill says set the objective 'only when sharpened' and propose
Direction additively — with NO gate, a grill could complete leaving them empty. This pins
the gate that refuses that.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_gate  # noqa: E402


class GrillCompleteNamesMissingPieces(unittest.TestCase):
    """grill_complete(log) returns the list of missing stage-(ii) pieces (empty list = complete)."""

    def test_empty_log_is_missing_all_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            missing = grill_gate.grill_complete(log=log)
            self.assertEqual(set(missing), {"objective", "direction", "direcionamento"})

    def test_only_set_objective_ran_misses_direction_and_direcionamento(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", rationale="say-A-do-B", log=log)
            missing = grill_gate.grill_complete(log=log)
            self.assertNotIn("objective", missing)
            self.assertEqual(set(missing), {"direction", "direcionamento"})

    def test_all_three_landed_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

    def test_direction_set_also_satisfies_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.set_direction("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])


class AssertGrillCompleteRaisesOnGaps(unittest.TestCase):
    """assert_grill_complete raises naming the gaps; passes silently when the three landed."""

    def test_raises_naming_the_missing_pieces(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            with self.assertRaises(ValueError) as ctx:
                grill_gate.assert_grill_complete(log=log)
            msg = str(ctx.exception)
            self.assertIn("direction", msg)
            self.assertIn("direcionamento", msg)
            # objective landed, so it is NOT among the named gaps
            self.assertNotIn("objective", grill_gate.grill_complete(log=log))

    def test_passes_silently_when_all_three_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            self.assertIsNone(grill_gate.assert_grill_complete(log=log))


if __name__ == "__main__":
    unittest.main(verbosity=2)
