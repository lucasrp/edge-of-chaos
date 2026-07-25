"""tkt-002 / S30.A1 — Assemble readiness bar (wake-blocking).

Module: assemble_ready — small interface, deep checklist later.
Seam: ready(log=…) -> ReadyReport; predispatch injects ready_fn.
F0: fail-closed with ASSEMBLE_BAR_NOT_IMPLEMENTED until sub-bars land.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import assemble_ready  # noqa: E402
import eventlog        # noqa: E402
import predispatch     # noqa: E402


class ReadyReportIsTheInterface(unittest.TestCase):
    def test_miss_and_report_are_immutable_and_carry_stable_codes(self):
        m = assemble_ready.Miss(
            code=assemble_ready.CODE_BAR_NOT_IMPLEMENTED,
            detail="bar not wired",
        )
        r = assemble_ready.ReadyReport(ok=False, misses=(m,), seq=None)
        self.assertFalse(r.ok)
        self.assertEqual(r.misses[0].code, "ASSEMBLE_BAR_NOT_IMPLEMENTED")
        with self.assertRaises(Exception):
            r.ok = True  # type: ignore[misc]

    def test_default_ready_ok_when_log_has_no_open_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            report = assemble_ready.ready(log=log)
        self.assertTrue(report.ok)
        self.assertEqual(report.misses, ())

    def test_ready_never_raises_on_empty_or_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.jsonl"
            report = assemble_ready.ready(log=missing)
        # empty / missing log = no open pending → ready (drain pass)
        self.assertTrue(report.ok)
        self.assertEqual(report.misses, ())

    def test_empty_checks_is_ok_true(self):
        """Ticket §2.3 stubs-green: all checks pass (empty or all-None) → ok."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            report = assemble_ready.ready(log=log, checks=[])
        self.assertTrue(report.ok)
        self.assertEqual(report.misses, ())

    def test_assert_ready_raises_with_code_and_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-block", kind="artefato", log=log)
            with self.assertRaises(assemble_ready.AssembleNotReady) as ctx:
                assemble_ready.assert_ready(log=log)
        msg = str(ctx.exception)
        self.assertIn(assemble_ready.CODE_PENDING_DRAIN, msg)
        self.assertIn("pkg-block", msg)


class PredispatchHonorsAssembleReadyGate(unittest.TestCase):
    """Assemble readiness is a first-class wake gate (not a grounding annotation).

    Quality > latency (operator): not ready → no stamp, no false woken dispatch.
    """

    def test_not_ready_aborts_before_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def not_ready():
                raise assemble_ready.AssembleNotReady(
                    assemble_ready.ReadyReport(
                        ok=False,
                        misses=(assemble_ready.Miss(
                            code=assemble_ready.CODE_RELATIONAL_ACT,
                            detail="test",
                        ),),
                        seq=None,
                    )
                )

            with self.assertRaises(assemble_ready.AssembleNotReady) as ctx:
                predispatch.run(
                    sweep_fn=lambda: 0,
                    briefing_fn=lambda: "B",
                    recall_fn=lambda: "R",
                    harvest_fn=lambda: 0,
                    ready_fn=not_ready,
                    log=log,
                )
            self.assertIn("RELATIONAL_ACT", str(ctx.exception))
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "not-ready assemble must not leave a woken stamp")

    def test_ready_allows_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            briefing, recall = predispatch.run(
                sweep_fn=lambda: 3,
                briefing_fn=lambda: "BRIEFING",
                recall_fn=lambda: "RECALL",
                harvest_fn=lambda: 0,
                ready_fn=lambda: None,
                drain_fn=lambda: None,
                log=log,
            )
            self.assertEqual((briefing, recall), ("BRIEFING", "RECALL"))
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_default_ready_fn_bricks_stamp_when_pending_open(self):
        """Default wire is assert_ready — open assembly.pending → no stamp.

        drain_fn no-op so we isolate the ready gate (open drain would clear via stub).
        """
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-wake", kind="artefato", log=log)
            with self.assertRaises(assemble_ready.AssembleNotReady):
                predispatch.run(
                    sweep_fn=lambda: 0,
                    briefing_fn=lambda: "B",
                    recall_fn=lambda: "R",
                    harvest_fn=lambda: 0,
                    drain_fn=lambda: None,
                    log=log,
                    # ready_fn intentionally omitted
                )
            self.assertFalse(eventlog.wake_fresh(log=log))

    def test_default_ready_fn_allows_stamp_when_queue_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            predispatch.run(
                sweep_fn=lambda: 0,
                briefing_fn=lambda: "B",
                recall_fn=lambda: "R",
                harvest_fn=lambda: 0,
                log=log,
            )
            self.assertTrue(eventlog.wake_fresh(log=log))

if __name__ == "__main__":
    unittest.main()
