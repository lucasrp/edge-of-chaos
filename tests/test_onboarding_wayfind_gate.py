"""The initial wayfind is CONCOMITANT with Direction (operator 2026-07-28): the first
mentor may not close without the map on the table AND landed as state. The gate grows an
opt-in `wayfind` piece — a `map.state` event must exist — and finish_onboarding is the
caller that requires it. Daily grill closes are untouched.
"""
import inspect
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_gate  # noqa: E402
import onboarding  # noqa: E402


def _land_all_four(log):
    eventlog.set_objective("obj", rationale="r", log=log)
    eventlog.append("direction.set", "direction", {"body": "rumo"}, log=log)
    eventlog.append("direction.report", "direcionamento", {"body": "passo"}, log=log)
    eventlog.append("grill.leveling", "leveling", {"kind": "diario", "content": "x"}, log=log)


class WayfindPiece(unittest.TestCase):
    def test_all_four_landed_but_no_map_misses_wayfind_when_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])
            missing = grill_gate.grill_complete(log=log, require_wayfind=True)
            self.assertEqual(missing, ["wayfind"])

    def test_map_state_event_satisfies_wayfind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            eventlog.append("map.state", "map:t", {"titulo": "mapa", "estado": "aberto"},
                            log=log)
            self.assertEqual(
                grill_gate.grill_complete(log=log, require_wayfind=True), [])

    def test_assert_raises_naming_wayfind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            with self.assertRaises(ValueError) as ctx:
                grill_gate.assert_grill_complete(log=log, require_wayfind=True)
            self.assertIn("wayfind", str(ctx.exception))


class FinishRequiresTheWayfind(unittest.TestCase):
    def test_finish_onboarding_passes_require_wayfind(self):
        src = inspect.getsource(onboarding.finish_onboarding)
        self.assertIn("require_wayfind=True", src)


if __name__ == "__main__":
    unittest.main()
