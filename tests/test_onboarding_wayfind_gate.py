"""Direction is the direção; the wayfind is the MAPA — complementary, and BOTH are
updated by EVERY mentor (operator 2026-07-28). The gate's `wayfind` piece is standard:
a `map.state` event must exist and be at least as recent as the latest steer feeder
(same clock as leveling). By the close, not necessarily at the session's start.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_gate  # noqa: E402


def _land_all_four(log):
    eventlog.set_objective("obj", rationale="r", log=log)
    eventlog.append("direction.set", "direction", {"body": "rumo"}, log=log)
    eventlog.append("direction.report", "direcionamento", {"body": "passo"}, log=log)
    eventlog.append("grill.leveling", "leveling", {"kind": "diario", "content": "x"}, log=log)


def _map(log):
    eventlog.append("map.state", "map:t", {"titulo": "mapa", "estado": "aberto"}, log=log)


def _map_opened(log):
    # the portfolio bound surface (portfolio.turn().map()) lands `map.opened` — the gate
    # must accept the whole map family (field failure: mentor close blocked 2026-07-29)
    eventlog.append("map.opened", "map:t", {"titulo": "mapa", "num": "map-001"}, log=log)


class WayfindIsAStandardPiece(unittest.TestCase):
    def test_wayfind_is_in_pieces(self):
        self.assertIn("wayfind", grill_gate.PIECES)

    def test_all_four_landed_but_no_map_misses_wayfind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            self.assertEqual(grill_gate.grill_complete(log=log), ["wayfind"])

    def test_map_as_recent_as_steers_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            _map(log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

    def test_map_opened_from_portfolio_surface_also_satisfies(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            _map_opened(log)
            self.assertEqual(grill_gate.grill_complete(log=log), [])

    def test_map_older_than_latest_steer_is_stale(self):
        # direção moved after the last map update → the mapa must move too
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            _map(log)
            eventlog.append("direction.set", "direction", {"body": "novo rumo"}, log=log)
            eventlog.append("grill.leveling", "leveling",
                            {"kind": "diario", "content": "y"}, log=log)
            self.assertEqual(grill_gate.grill_complete(log=log), ["wayfind"])

    def test_assert_raises_naming_wayfind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _land_all_four(log)
            with self.assertRaises(ValueError) as ctx:
                grill_gate.assert_grill_complete(log=log)
            self.assertIn("wayfind", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
