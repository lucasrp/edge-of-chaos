"""Modulo 1 (Aquisicao / Lastro) — the front door.

ADR-0019 (one owner + narrow interface): Aquisicao OWNS the acquisition gate; Julgamento (close)
CALLS it, never re-implements it. ADR-0021 (auditor gate). The seca declaration IS lastro.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog     # noqa: E402
import harvest      # noqa: E402
import aquisicao    # noqa: E402


class GroundingFloorIsTheOwnedGate(unittest.TestCase):
    def test_grounding_floor_is_the_owned_interface_over_harvest(self):
        # ADR-0019: the gate lives behind Aquisicao's interface; close calls THIS.
        self.assertIs(aquisicao.grounding_floor, harvest.close_floor)

    def test_knob_zero_blocks_nothing(self):
        # ADR-0021: auditor default off (knob 0) -> [] — the gate never blocks by default.
        self.assertEqual(aquisicao.grounding_floor(knob=0), [])


class DeclareDarkIsLastro(unittest.TestCase):
    def test_declares_a_seca_as_one_logged_event(self):
        # "consultei exa com as queries X/Y, zero relevantes" — the declaration sustains the
        # negative claim; it is lastro, so it is recorded, not swallowed.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            aquisicao.declare_dark("exa", "queries X e Y, zero relevantes", log=log)
            evs = eventlog.read(types=["grounding.dark"], log=log)
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["payload"]["source"], "exa")
            self.assertIn("zero relevantes", evs[0]["payload"]["reason"])

    def test_unexplained_or_unnamed_dark_is_rejected(self):
        # an unnamed source or an unexplained seca is not lastro — refuse it.
        with self.assertRaises(ValueError):
            aquisicao.declare_dark("", "reason")
        with self.assertRaises(ValueError):
            aquisicao.declare_dark("exa", "")


if __name__ == "__main__":
    unittest.main()
