"""grill_gate — the post-grill stage-(ii) enforcement (Codex gate finding [high],
docs/briefing-lifecycle-audit.md).

A completed grill MUST NOT leave the stage-(ii) briefing sections empty. The audit's
acceptance for stage (ii) FAILS if Objective, Direction, or Direcionamento is still empty
after a grill: the feeders (`set_objective` / `report_direction` / direction set-or-propose)
must have run. The grill skill says set the objective 'only when sharpened' and propose
Direction additively — with NO gate, a grill could complete leaving them empty. This pins
the gate that refuses that.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "tools" / "grill_gate.py"
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_gate  # noqa: E402


def _wayfind(log):
    """The mapa landed as state — wayfind piece (complementary to Direction, 2026-07-28)."""
    eventlog.append("map.state", "map:t", {"titulo": "mapa", "estado": "aberto"}, log=log)


class GrillCompleteNamesMissingPieces(unittest.TestCase):
    """grill_complete(log) returns the list of missing stage-(ii) pieces (empty list = complete)."""

    def test_empty_log_is_missing_all_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            missing = grill_gate.grill_complete(log=log)
            self.assertEqual(
                set(missing),
                {"objective", "direction", "direcionamento", "leveling", "wayfind"})

    def test_only_set_objective_ran_misses_direction_direcionamento_leveling(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", rationale="say-A-do-B", log=log)
            missing = grill_gate.grill_complete(log=log)
            self.assertNotIn("objective", missing)
            self.assertEqual(
                set(missing), {"direction", "direcionamento", "leveling", "wayfind"})
    def test_all_three_landed_without_leveling_misses_leveling(self):
        """Plan 2026-07-13: steers alone are not mentor-done (persona/leveling floor)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            self.assertEqual(
                set(grill_gate.grill_complete(log=log)), {"leveling", "wayfind"})

    def test_three_steers_plus_leveling_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling(
                "diario", "sem update de persona; residual = product", root=root, log=log)
            _wayfind(log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

    def test_leveling_before_latest_steer_still_missing(self):
        """Leveling must be at least as recent as the latest steer feeder (close order)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            import grill_writeback
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            grill_writeback.leveling("diario", "early", root=root, log=log)
            eventlog.report_direction("the steer after leveling", log=log)
            self.assertIn("leveling", grill_gate.grill_complete(log=log))

    def test_sweep_proposed_after_leveling_does_not_reopen_gate(self):
        """direction.proposed é fila de ratificação (wake/topic-thread infere sozinho, id
        topic-7d:*), não steer: um install completo NÃO pode se trancar porque o próprio
        beat inferiu propostas depois do grill (auto-lock turing/sandbox 2026-07-25)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.set_direction("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling("diario", "close", root=root, log=log)
            _wayfind(log)
            eventlog.propose("topic-7d:report-rite", "inferida pelo sweep", log=log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

    def test_direction_set_also_satisfies_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.set_direction("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling("diario", "close", root=root, log=log)
            _wayfind(log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

class EmptyBodiedFeedersDoNotCountAsLanded(unittest.TestCase):
    """Codex gate finding [high]: a whitespace/empty feeder body does NOT count as landed. Even if a
    grill appends empty objective/direction/report events directly to the log (bypassing the validating
    write helpers), the gate must still name the gap — an empty body is no stage-(ii) content. The
    events are appended raw (eventlog.append) precisely to model that attack the gate must catch."""

    def _append_empty_objective(self, log):
        eventlog.append("objective.set", "objective", {"body": "   ", "rationale": None}, log=log)

    def _append_empty_direction(self, log):
        eventlog.append("direction.proposed", "direction",
                        {"id": "d1", "body": "  \n ", "kind": "thread"}, log=log)

    def _append_empty_report(self, log):
        eventlog.append("direction.report", "direction",
                        {"body": "\t", "distills": [], "cites": []}, log=log)

    def test_empty_objective_body_is_named_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self._append_empty_objective(log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            self.assertIn("objective", grill_gate.grill_complete(log=log))

    def test_empty_direction_body_is_named_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            self._append_empty_direction(log)
            eventlog.report_direction("the steer", log=log)
            self.assertIn("direction", grill_gate.grill_complete(log=log))

    def test_empty_report_body_is_named_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            self._append_empty_report(log)
            self.assertIn("direcionamento", grill_gate.grill_complete(log=log))

    def test_close_cli_exits_nonzero_when_a_feeder_body_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            self._append_empty_report(log)  # report event present but its body is whitespace
            res = subprocess.run(
                [sys.executable, str(GATE), "close", "--log", str(log)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(res.returncode, 0, res.stdout)
            self.assertIn("direcionamento", res.stdout + res.stderr)

    def test_non_empty_bodies_still_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling("diario", "close", root=root, log=log)
            _wayfind(log)
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
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling("diario", "close", root=root, log=log)
            _wayfind(log)
            self.assertIsNone(grill_gate.assert_grill_complete(log=log))

    def test_raises_when_leveling_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            with self.assertRaises(ValueError) as ctx:
                grill_gate.assert_grill_complete(log=log)
            self.assertIn("leveling", str(ctx.exception))

class CloseCLIIsFailClosed(unittest.TestCase):
    """The runnable close: `grill_gate.py close --log <log>` exits NONZERO naming the gaps when
    a feeder is missing, exit 0 when the three landed — so the close is deterministic at runtime,
    not merely agent prose-compliance. Invoked via subprocess like tests/test_beat_launch.py."""

    def _close(self, log):
        return subprocess.run(
            [sys.executable, str(GATE), "close", "--log", str(log)],
            capture_output=True, text=True,
        )

    def test_incomplete_log_exits_nonzero_naming_the_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)  # only objective landed
            res = self._close(log)
            self.assertNotEqual(res.returncode, 0, res.stdout)
            out = res.stdout + res.stderr
            self.assertIn("direction", out)
            self.assertIn("direcionamento", out)
            # the named-gaps list (before the trailing explanation) must not include objective
            named = out.split("left empty:")[1].split("(")[0]
            self.assertNotIn("objective", named)

    def test_complete_log_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            root = Path(tmp) / "lv"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            import grill_writeback
            grill_writeback.leveling("diario", "close", root=root, log=log)
            _wayfind(log)
            res = self._close(log)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_steers_without_leveling_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.report_direction("the steer", log=log)
            res = self._close(log)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("leveling", res.stdout + res.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
