"""tkt-003 — assembly_pending as log events only (sole truth = log).

Per-item queue: pending without matching done/failed stays open.
assemble_ready.PENDING_DRAIN when open items remain.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import assemble_ready  # noqa: E402
import eventlog        # noqa: E402


class AssemblyPendingIsLogTruth(unittest.TestCase):
    def test_empty_log_has_no_open_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            self.assertEqual(eventlog.assembly_pending_open(log=log), {})

    def test_pending_without_done_stays_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-a", kind="artefato", ref="slug-a", log=log)
            open_ = eventlog.assembly_pending_open(log=log)
            self.assertIn("pkg-a", open_)
            self.assertEqual(open_["pkg-a"]["kind"], "artefato")

    def test_done_clears_pending_for_that_package_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-a", kind="artefato", log=log)
            eventlog.mark_assembly_pending("pkg-b", kind="dig", log=log)
            eventlog.mark_assembly_done("pkg-a", log=log)
            open_ = eventlog.assembly_pending_open(log=log)
            self.assertNotIn("pkg-a", open_)
            self.assertIn("pkg-b", open_)

    def test_failed_also_clears_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-x", kind="artefato", log=log)
            eventlog.mark_assembly_failed("pkg-x", reason="relacional incomplete", log=log)
            self.assertEqual(eventlog.assembly_pending_open(log=log), {})

    def test_ready_pending_drain_miss_when_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-a", kind="artefato", log=log)
            report = assemble_ready.ready(log=log)
        codes = {m.code for m in report.misses}
        self.assertIn(assemble_ready.CODE_PENDING_DRAIN, codes)
        self.assertFalse(report.ok)
        self.assertIsInstance(report.seq, int)

    def test_ready_ok_when_pending_queue_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")
            report = assemble_ready.ready(log=log)
        self.assertTrue(report.ok)
        self.assertEqual(report.misses, ())

    def test_ready_ok_after_all_packages_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.mark_assembly_pending("pkg-a", kind="artefato", log=log)
            eventlog.mark_assembly_done("pkg-a", log=log)
            report = assemble_ready.ready(log=log)
        self.assertTrue(report.ok)

    def test_package_id_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.mark_assembly_pending("", kind="artefato", log=log)
            with self.assertRaises(ValueError):
                eventlog.mark_assembly_pending("  ", kind="artefato", log=log)

    def test_publish_atomic_enqueues_assembly_pending(self):
        """SINAL tkt-003: publish lands assembly.pending in the same truth log (no vacuous drain)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(
                {"dispatch_id": eventlog.test_dispatch_id(), "origin": "beat"},
                log=log,
            )
            did = eventlog.read(types=["dispatch.open"], log=log)[-1]["payload"]["dispatch_id"]
            eventlog.publish_artefato_atomic(
                "slug-pending",
                intent="open: x; bet: y",
                skill="prototype",  # rito-excepted; tests the atomic pending enqueue
                dispatch_id=did,
                log=log,
                require_wake=True,
            )
            open_ = eventlog.assembly_pending_open(log=log)
            self.assertIn("artefato:slug-pending", open_)
            self.assertEqual(open_["artefato:slug-pending"]["kind"], "artefato")
            report = assemble_ready.ready(log=log)
            codes = {m.code for m in report.misses}
            self.assertIn(assemble_ready.CODE_PENDING_DRAIN, codes)


if __name__ == "__main__":
    unittest.main()
