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
                     "artefatos_without_kernel", "experiments_at", "experiment_at",
                     "supersede_rank"):
            self.assertTrue(callable(getattr(cortex, name)), name)

    def test_door_forwards_late(self):
        """One forwarding proof (args/kwargs reach the substrate) + the late-binding contract:
        a monkeypatch on the eventlog attribute is seen through the door — the seam the test
        phenotype relies on (test_sweep._isolate), and the red that created these wrappers."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("d1", "steer body", log=log)
            d = cortex.direction_at(log=log)
            self.assertIn("d1", [i["id"] for i in d["proposed"]])
        original = eventlog.direction_at
        try:
            eventlog.direction_at = lambda *a, **k: {"set": [], "proposed": [{"id": "patched"}]}
            self.assertEqual(cortex.direction_at()["proposed"][0]["id"], "patched")
        finally:
            eventlog.direction_at = original

    def test_supersede_rank_delegates(self):
        """The one door-specific fact: the private eventlog._supersede_rank is public here."""
        args = ({"recognizer_rev": 2}, {"seq": 1})
        self.assertEqual(cortex.supersede_rank(*args), eventlog._supersede_rank(*args))

    def test_experiment_at_reads_native_experiment_curations(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.curate_experiment(
                "exp40",
                prose="exp40 is a legal retrieval experiment.",
                typed={
                    "claim": "GN wins on one process.",
                    "scope": "process 76610395.",
                    "status": "lead",
                    "caveat": "n=1.",
                    "supports": ["GN"],
                    "excludes": ["general claim"],
                    "next": "Run C5.",
                },
                canonical_artifacts=[{"ref": "results/summary.json", "role": "summary"}],
                by="grill",
                log=log,
            )
            self.assertEqual(cortex.experiment_at("exp40", log=log)["canonical"]["typed"]["status"],
                             "lead")


if __name__ == "__main__":
    unittest.main()
