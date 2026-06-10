"""ADR-0016 — no wake, no publish. The entry-driver (tools/predispatch.py) runs the mechanical
pre-dispatch floor (sweep → briefing → recall brief) and stamps `dispatch.open`; the publisher —
the one mechanical wall every real publish crosses (the close's publish stage) — refuses without
a stamp newer than the last `artefato.published`. One wake per publish. Delta stays agentic and
is never stamped nor gated (ADR-0001/0011)."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog    # noqa: E402
import publisher   # noqa: E402
import predispatch  # noqa: E402


class WakeFreshness(unittest.TestCase):
    """The fold: a dispatch.open newer than the last artefato.published = a fresh wake."""

    def test_no_stamp_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self.assertFalse(eventlog.wake_fresh(log=log))

    def test_stamp_on_empty_log_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_stamp_is_consumed_by_a_publish_one_wake_per_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            eventlog._append_orphan_published_for_test("a-slug", log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a stamp must not be reusable across publishes (ADR-0016)")
            eventlog.dispatch_open(log=log)
            self.assertTrue(eventlog.wake_fresh(log=log))


class NoWakeNoPublish(unittest.TestCase):
    """The publisher refuses without a fresh stamp — BEFORE proof verification, so the refusal
    names the real gap (`no-wake`), not a proof error."""

    def test_publish_without_stamp_raises_no_wake(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(RuntimeError) as ctx:
                publisher.publish("any-slug", "<h1>x</h1>", "intent", skill="report",
                                  verdict={"not": "a proof"}, log=log,
                                  blog_dir=Path(tmp) / "blog")
            self.assertIn("no-wake", str(ctx.exception))

    def test_fresh_stamp_releases_the_gate_to_the_proof_check(self):
        # with a stamp, the same call proceeds past the wake gate and fails on the fake proof
        # instead (ValueError from verify_proof) — proving gate order and release
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            with self.assertRaises(ValueError):
                publisher.publish("any-slug", "<h1>x</h1>", "intent", skill="report",
                                  verdict={"not": "a proof"}, log=log,
                                  blog_dir=Path(tmp) / "blog")


class EntryDriver(unittest.TestCase):
    """predispatch.run — the mechanical floor, injectable (house style) so it runs offline."""

    def test_runs_the_floor_and_stamps_with_the_sweep_yield(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            briefing_text, recall_text = predispatch.run(
                sweep_fn=lambda: 7,
                briefing_fn=lambda: "BRIEFING",
                recall_fn=lambda: "RECALL",
                log=log)
            self.assertEqual((briefing_text, recall_text), ("BRIEFING", "RECALL"))
            evs = eventlog.read(types=["dispatch.open"], log=log)
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["payload"].get("swept_sessions"), 7,
                             "the stamp carries the sweep yield (the read-side metric)")

    def test_stamp_lands_even_when_a_brief_degrades(self):
        # the gate proves the wake RAN, not that the world cooperated (ADR-0016): a degraded
        # brief (e.g. graph outage) still stamps — only a raising SWEEP (fail-loud store,
        # ADR-0015) aborts before the stamp
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def dark_recall():
                raise RuntimeError("graph down")

            briefing_text, recall_text = predispatch.run(
                sweep_fn=lambda: 0, briefing_fn=lambda: "B", recall_fn=dark_recall, log=log)
            self.assertIn("DARK", recall_text)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_a_failing_sweep_aborts_before_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def loud_sweep():
                raise RuntimeError("transcript store not found")

            with self.assertRaises(RuntimeError):
                predispatch.run(sweep_fn=loud_sweep, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a dispatch that could not wake must not look woken")


class TheDriverIsPinnedInProse(unittest.TestCase):
    """Every producer's SKILL.md carries the entry snippet; the pipeline names the stamp."""

    def test_producers_run_the_entry_driver(self):
        for producer in ("report", "research", "map", "plan", "discovery"):
            skill = (REPO / "skills" / producer / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("predispatch.py", skill,
                          f"skills/{producer} is missing the ADR-0016 entry-driver snippet")

    def test_pipeline_names_the_stamp_and_the_gate(self):
        pipeline = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8")
        self.assertIn("predispatch.py", pipeline)
        self.assertIn("dispatch.open", pipeline)
        flat = " ".join(pipeline.lower().split())   # collapse wrapping
        self.assertIn("no wake, no publish", flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
