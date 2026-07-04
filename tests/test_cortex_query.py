"""cortex — Modulo 2 front door: the query surface reclaimed from eventlog (C4, Costura B).

ADR-0010 names the read architecture — navigate the Cortex, replay the log — but eventlog was
double-duty: the append-log (Plataforma) AND the Cortex-query surface. ADR-0019 resolves the
straddle: one owner + a narrow interface. These tests pin the front door: the five query names
are OWNED by cortex — other modules call THIS — and they answer over a log passed in, exactly
as the substrate does (so #68 can swap the substrate behind the door without moving a caller).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cortex  # noqa: E402
import eventlog  # noqa: E402


class TestFrontDoor(unittest.TestCase):
    def test_surface_is_public_and_complete(self):
        """The cursor-query family with external callers, all public — supersede_rank loses the
        underscore at the door (harvest reached into eventlog._supersede_rank; a private reach-in
        is not an interface)."""
        for name in ("cosine", "direction_at", "objective_at", "report_at", "corpus_at",
                     "grounding_at", "source_yield_at", "source_feedback_at",
                     "artefatos_without_kernel", "supersede_rank"):
            self.assertTrue(callable(getattr(cortex, name)), name)

    def test_cosine_math_and_degrade(self):
        self.assertAlmostEqual(cortex.cosine([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cortex.cosine([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertEqual(cortex.cosine([0, 0], [1, 1]), 0.0)  # degrade, never divide-by-zero

    def test_direction_at_reads_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("d1", "steer body", log=log)
            d = cortex.direction_at(log=log)
            self.assertIn("d1", [i["id"] for i in d["proposed"]])

    def test_objective_at_reads_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the seam", log=log)
            self.assertEqual(cortex.objective_at(log=log)["body"], "ship the seam")

    def test_corpus_at_reads_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("a1", "why: pin the seam", log=log)
            self.assertEqual([c["slug"] for c in cortex.corpus_at(log=log)], ["a1"])

    def test_supersede_rank_orders_by_rev_then_seq(self):
        """The E2b contract at the public name: higher recognizer_rev wins over a later seq of a
        lower rev; corrupt rev ranks below any real one."""
        better = cortex.supersede_rank({"recognizer_rev": 2}, {"seq": 1})
        later_worse = cortex.supersede_rank({"recognizer_rev": 1}, {"seq": 9})
        corrupt = cortex.supersede_rank({"recognizer_rev": "bad"}, {"seq": 99})
        self.assertGreater(better, later_worse)
        self.assertGreater(later_worse, corrupt)


if __name__ == "__main__":
    unittest.main()
