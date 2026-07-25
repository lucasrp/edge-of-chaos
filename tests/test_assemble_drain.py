"""tkt-004 drain worker — per package_id on the log; done only after relational step."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import assemble_drain  # noqa: E402
import assemble_ready  # noqa: E402
import eventlog        # noqa: E402


class AssembleDrainPerItem(unittest.TestCase):
    def test_empty_queue_is_noop_and_ready_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            result = assemble_drain.drain(log=log)
            self.assertEqual(result.done, ())
            self.assertEqual(result.failed, ())
            self.assertTrue(assemble_ready.ready(log=log).ok)

    def test_drain_calls_relational_before_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-a", kind="artefato", ref="s", log=log)
            order = []

            def rel(pkg):
                order.append(("rel", pkg["package_id"]))
                return assemble_drain.RelationalOutcome(ok=True)

            result = assemble_drain.drain(log=log, relational_fn=rel, budget=10)
            self.assertEqual(result.done, ("pkg-a",))
            types = [e["type"] for e in eventlog.read(log=log)]
            self.assertIn("assembly.done", types)
            # relational invoked before done pen
            self.assertEqual(order[0], ("rel", "pkg-a"))
            done_seq = next(e["seq"] for e in eventlog.read(log=log) if e["type"] == "assembly.done")
            # only one package
            self.assertTrue(assemble_ready.ready(log=log).ok)

    def test_relational_fail_writes_failed_not_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-x", kind="artefato", log=log)

            def rel(_pkg):
                return assemble_drain.RelationalOutcome(ok=False, reason="graph dark")

            result = assemble_drain.drain(log=log, relational_fn=rel)
            self.assertEqual(result.failed, ("pkg-x",))
            types = [e["type"] for e in eventlog.read(log=log)]
            self.assertIn("assembly.failed", types)
            self.assertNotIn("assembly.done", types)
            # failed clears open set (R2=A)
            self.assertEqual(eventlog.assembly_pending_open(log=log), {})
            self.assertTrue(assemble_ready.ready(log=log).ok)

    def test_budget_limits_packages_per_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-1", kind="artefato", log=log)
            eventlog.mark_assembly_pending("pkg-2", kind="artefato", log=log)
            result = assemble_drain.drain(
                log=log,
                relational_fn=lambda p: assemble_drain.RelationalOutcome(ok=True),
                budget=1,
            )
            self.assertEqual(len(result.done), 1)
            open_ = eventlog.assembly_pending_open(log=log)
            self.assertEqual(len(open_), 1)
            self.assertFalse(assemble_ready.ready(log=log).ok)

    def test_must_not_done_if_relational_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-e", kind="artefato", log=log)

            def rel(_pkg):
                raise RuntimeError("boom")

            result = assemble_drain.drain(log=log, relational_fn=rel)
            self.assertEqual(result.failed, ("pkg-e",))
            types = [e["type"] for e in eventlog.read(log=log)]
            self.assertIn("assembly.failed", types)
            self.assertNotIn("assembly.done", types)


class PredispatchDrainsBeforeReady(unittest.TestCase):
    def test_open_drain_clears_pending_so_wake_can_stamp(self):
        """R1=C: open path tries budgeted drain before ready gate."""
        import predispatch
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-w", kind="artefato", log=log)
            # without drain, default ready would fail
            self.assertFalse(assemble_ready.ready(log=log).ok)
            briefing, _ = predispatch.run(
                sweep_fn=lambda: 0,
                briefing_fn=lambda: "B",
                recall_fn=lambda: "R",
                harvest_fn=lambda: 0,
                drain_fn=lambda: assemble_drain.drain(
                    log=log,
                    relational_fn=lambda p: assemble_drain.RelationalOutcome(ok=True),
                    budget=10,
                ),
                log=log,
            )
            self.assertEqual(briefing, "B")
            self.assertTrue(eventlog.wake_fresh(log=log))
            self.assertEqual(eventlog.assembly_pending_open(log=log), {})


if __name__ == "__main__":
    unittest.main()
