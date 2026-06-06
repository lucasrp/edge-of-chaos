"""sweep — the pull-at-open digestion sweep (ADR-0008, issue #15).

These pin the PURE half: cursor-guarded delta selection, idempotency, and the log/cursor
side effects of `execute` — with an injected fake `ingest_fn`, so no Neo4j or OpenAI is touched.
The Graphiti ingest + re-projection are exercised live in the deploy/verify step, not here.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sweep      # noqa: E402
import eventlog   # noqa: E402

BODY = "a substantive design decision about the edge-next architecture and its direction " * 4


def write_session(d, sid, n_human=3, text=BODY):
    lines = []
    for i in range(n_human):
        lines.append(json.dumps({"type": "user", "message": {"content": f"{text} ({i})"}}))
        lines.append(json.dumps({"type": "assistant", "message": {"content": f"reply {i}: {text}"}}))
    p = Path(d) / f"{sid}.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return p


class PlanSweepSelectsDeltas(unittest.TestCase):
    """plan_sweep returns each session's new-since-cursor delta; a session already at its
    watermark plans nothing (idempotent); a thin delta is marked skip (left to grow)."""

    def test_new_session_then_idempotent_at_watermark(self):
        with tempfile.TemporaryDirectory() as proj:
            write_session(proj, "sessA")
            plan = sweep.plan_sweep(proj, {})
            self.assertEqual([p["id"] for p in plan], ["sessA"])
            self.assertFalse(plan[0]["skip"])
            self.assertEqual(sweep.plan_sweep(proj, {"sessA": plan[0]["watermark"]}), [])

    def test_thin_session_marked_skip(self):
        with tempfile.TemporaryDirectory() as proj:
            write_session(proj, "tiny", n_human=1, text="hi")
            plan = sweep.plan_sweep(proj, {})
            self.assertTrue(all(p["skip"] for p in plan))


class ExecuteIngestsLogsAdvances(unittest.TestCase):
    """execute ingests qualifying deltas (one episode event each), advances their cursors, and
    leaves thin deltas untouched (not ingested, cursor not advanced)."""

    def test_qualifying_ingested_and_cursor_advanced(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            log = Path(st) / "log.jsonl"
            seen = []
            cur, n = sweep.execute(sweep.plan_sweep(proj, {}),
                                   lambda items: seen.extend(i["id"] for i in items), {}, log=log)
            self.assertEqual((n, seen), (1, ["sessA"]))
            self.assertIn("sessA", cur)
            eps = eventlog.read(types=["episode"], log=log)
            self.assertEqual(len(eps), 1)
            self.assertEqual(eps[0]["payload"]["session"], "sessA")

    def test_thin_not_ingested_or_advanced(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "tiny", n_human=1, text="hi")
            log = Path(st) / "log.jsonl"
            seen = []
            cur, n = sweep.execute(sweep.plan_sweep(proj, {}),
                                   lambda items: seen.extend(i["id"] for i in items), {}, log=log)
            self.assertEqual((n, seen, cur), (0, [], {}))


class RunIsIdempotent(unittest.TestCase):
    """The whole-sweep guarantee: two back-to-back runs ingest the session once; the second is a
    no-op because the cursor advanced (re-running is safe under multiple triggers)."""

    def test_second_run_ingests_nothing(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"
            calls = []
            fake = lambda items: calls.append(len(items))
            n1 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log)
            n2 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log)
            self.assertEqual((n1, n2, calls), (1, 0, [1]))

    def test_growing_session_digests_only_new_delta(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"
            write_session(proj, "sessA")
            ingested = []
            fake = lambda items: ingested.append([i["id"] for i in items])
            sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log)
            # the session grows; a second sweep sees only the new tail
            write_session(proj, "sessA", n_human=6)  # rewrites longer (append-only in spirit)
            n2 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log)
            self.assertEqual(n2, 1)  # the new delta re-qualified
            self.assertEqual(ingested, [["sessA"], ["sessA"]])


class GraphIngestIsBestEffort(unittest.TestCase):
    """ADR-0006: the Tier-0 log is the source of truth. A graph ingest failure (no graphiti_core /
    Neo4j down on a fleet host like petertosh) is skipped, not fatal — episodes are still logged and
    cursors still advance, so digestion is current and the graph stays rebuildable from the log."""

    def test_ingest_failure_still_logs_and_advances(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"

            def boom(items):
                raise ModuleNotFoundError("No module named 'graphiti_core'")

            n = sweep.run(proj, ingest_fn=boom, cursors_path=cp, reproject_fn=False, log=log)
            self.assertEqual(n, 1)                                    # logged despite graph failure
            self.assertEqual(len(eventlog.read(types=["episode"], log=log)), 1)
            self.assertIn("sessA", sweep.load_cursors(cp))           # cursor advanced


if __name__ == "__main__":
    unittest.main(verbosity=2)
