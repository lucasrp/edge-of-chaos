"""Hermetic durable-journal tests for snapshot administration."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import admin_receipt_mediator as mediator
from tools import source_rotation as rotation
from tools import source_snapshot_admin as admin


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class AdminReceiptMediator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = self.root / "snapshots"
        self.snapshots.mkdir()
        self.uid, self.gid = os.getuid(), os.getgid()
        self.payload = b"SYNTHETIC_DURABLE_RECEIPT_CANARY"
        self._generation(self.snapshots, "current", self.payload)
        self.admin_config = admin.AdminConfig(
            snapshots_root=self.snapshots, lock_path=self.root / "rotation.lock",
            expected_uid=self.uid, expected_gid=self.gid,
            generation_id="synthetic-initial", max_candidate_bytes=1024 * 1024,
            safety_margin_bytes=1024 * 1024,
        )
        receipt_root = self.root / "receipts"
        (receipt_root / "pending").mkdir(parents=True, mode=0o700)
        receipt_root.chmod(0o700)
        (receipt_root / "completed").mkdir(mode=0o700)
        self.journal = mediator.JournalConfig(
            root=receipt_root, lock_path=self.root / "journal.lock",
            expected_uid=self.uid, expected_gid=self.gid,
        )
        self.journal.lock_path.touch(mode=0o600)
        self.clock = lambda: datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
        self.txid = lambda: "tx_synthetic_0001"

    def tearDown(self):
        for current, _dirs, files in os.walk(self.root):
            os.chmod(current, 0o700)
            for name in files:
                os.chmod(Path(current) / name, 0o600)
        self.tmp.cleanup()

    def _generation(self, parent, name, payload):
        root = parent / name
        source = root / "sources/synthetic"
        source.mkdir(parents=True)
        (source / "note.md").write_bytes(payload)
        row = {"source": "synthetic", "relative_path": "note.md", "size": len(payload),
               "sha256": hashlib.sha256(payload).hexdigest()}
        manifest = {
            "schema": rotation.MANIFEST_SCHEMA, "snapshot_id": name,
            "plan_sha256": "0" * 64, "files": [row], "excluded": [],
            "summary": {"included_files": 1, "included_bytes": len(payload),
                        "excluded_entries": 0},
            "credential_present": False, "llm_invoked": False, "network_used": False,
        }
        manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
        (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")
        rotation.seal_generation(root, uid=self.uid, gid=self.gid)

    def execute(self, argv, **kwargs):
        return mediator.execute_durable(
            argv, config=self.admin_config, journal=self.journal, now=self.clock,
            transaction_id=self.txid, **kwargs,
        )

    def preview_hash(self):
        return self.execute(["preview"])["result"]["preview_sha256"]

    def pending(self):
        return list((self.journal.root / "pending").glob("*.json"))

    def completed(self):
        return list((self.journal.root / "completed").glob("*.json"))

    def test_status_and_preview_are_zero_write_and_report_empty_journal(self):
        status = self.execute(["status"])
        preview = self.execute(["preview"])
        self.assertEqual(status["journal"]["pending_count"], 0)
        self.assertEqual(preview["journal"]["pending_count"], 0)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.completed(), [])

    def test_successful_apply_persists_completion_before_clearing_intent(self):
        preview_hash = self.preview_hash()
        receipt = self.execute(["apply", "--preview-sha256", preview_hash])
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.completed()), 1)
        completion_path = self.completed()[0]
        self.assertEqual(completion_path.stat().st_mode & 0o777, 0o400)
        completion = json.loads(completion_path.read_text())
        self.assertEqual(completion["outcome"], "completed")
        self.assertEqual(receipt["journal"]["transaction_id"], "tx_synthetic_0001")
        self.assertNotIn(self.payload.decode(), json.dumps([receipt, completion]))

    def test_wrong_reviewed_hash_is_rejected_before_intent(self):
        with self.assertRaisesRegex(rotation.SourceRotationError, "does not match"):
            self.execute(["apply", "--preview-sha256", "0" * 64])
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.completed(), [])
        self.assertFalse((self.snapshots / "index.json").exists())

    def test_proven_precommit_rejection_is_durable_and_clears_intent(self):
        reviewed = self.preview_hash()
        with mock.patch(
            "tools.admin_receipt_mediator.rotation.apply_legacy_migration",
            side_effect=rotation.SourceRotationError("synthetic precommit rejection"),
        ):
            with self.assertRaisesRegex(rotation.SourceRotationError, "precommit"):
                self.execute(["apply", "--preview-sha256", reviewed])
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.completed()), 1)
        self.assertEqual(json.loads(self.completed()[0].read_text())["outcome"],
                         "rejected-before-commit")

    def test_crash_after_admin_leaves_intent_and_hash_bound_recover_reconciles(self):
        reviewed = self.preview_hash()
        def fault(point):
            if point == "after_admin":
                raise RuntimeError("synthetic crash after state change")
        with self.assertRaisesRegex(RuntimeError, "after state change"):
            self.execute(["apply", "--preview-sha256", reviewed], fault=fault)
        self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.completed(), [])
        status = self.execute(["status"])
        self.assertEqual(status["journal"]["pending_count"], 1)
        index_hash = status["result"]["index_sha256"]
        with self.assertRaisesRegex(rotation.SourceRotationError, "does not match"):
            self.execute(["recover", "--index-sha256", "0" * 64])
        recovered = self.execute(["recover", "--index-sha256", index_hash])
        self.assertTrue(recovered["result"]["journal_reconciled"])
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.completed()), 1)

    def test_crash_after_completion_keeps_both_and_recover_only_clears_intent(self):
        reviewed = self.preview_hash()
        def fault(point):
            if point == "after_completion":
                raise RuntimeError("synthetic crash after durable completion")
        with self.assertRaisesRegex(RuntimeError, "durable completion"):
            self.execute(["apply", "--preview-sha256", reviewed], fault=fault)
        self.assertEqual((len(self.pending()), len(self.completed())), (1, 1))
        status = self.execute(["status"])
        index_hash = status["result"]["index_sha256"]
        recovered = self.execute(["recover", "--index-sha256", index_hash])
        self.assertTrue(recovered["result"]["journal_reconciled"])
        self.assertFalse(recovered["result"]["snapshot_recovery_invoked"])
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.completed()), 1)

    def test_snapshot_pending_recover_is_itself_journaled(self):
        reviewed = self.preview_hash()
        self.execute(["apply", "--preview-sha256", reviewed])
        (self.journal.root / "completed/tx_synthetic_0001.json").unlink()
        os.chmod(self.snapshots / "generations", 0o700)
        rotation._begin_transaction(self.snapshots)
        status = rotation.inspect_pending_transaction(
            self.snapshots, expected_uid=self.uid, expected_gid=self.gid,
        )
        self.txid = lambda: "tx_synthetic_0002"
        receipt = self.execute(["recover", "--index-sha256", status["index_sha256"]])
        self.assertEqual(receipt["command"], "recover")
        self.assertFalse((self.snapshots / "rotation.pending").exists())
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.completed()), 1)

    def test_unexpected_journal_entry_and_open_permissions_fail_closed(self):
        unexpected = self.journal.root / "pending/not-allowed.txt"
        unexpected.write_text("x")
        with self.assertRaisesRegex(rotation.SourceRotationError, "unexpected"):
            self.execute(["status"])
        unexpected.unlink()
        os.chmod(self.journal.root / "pending", 0o755)
        with self.assertRaisesRegex(rotation.SourceRotationError, "owner or mode"):
            self.execute(["status"])

    def test_missing_or_open_journal_lock_fails_before_receipt_access(self):
        self.journal.lock_path.unlink()
        with self.assertRaisesRegex(rotation.SourceRotationError, "lock is missing"):
            self.execute(["status"])
        self.journal.lock_path.touch(mode=0o600)
        os.chmod(self.journal.lock_path, 0o666)
        with self.assertRaisesRegex(rotation.SourceRotationError, "lock owner, mode"):
            self.execute(["status"])

    def test_tampered_intent_and_completion_are_rejected_even_by_status(self):
        reviewed = self.preview_hash()
        def fault(point):
            if point == "after_intent":
                raise RuntimeError("synthetic stop")
        with self.assertRaises(RuntimeError):
            self.execute(["apply", "--preview-sha256", reviewed], fault=fault)
        intent_path = self.pending()[0]
        os.chmod(intent_path, 0o600)
        intent = json.loads(intent_path.read_text()); intent["command"] = "forged"
        intent_path.write_text(json.dumps(intent)); os.chmod(intent_path, 0o400)
        with self.assertRaises(rotation.SourceRotationError):
            self.execute(["status"])

        self.tearDown(); self.setUp()
        reviewed = self.preview_hash()
        self.execute(["apply", "--preview-sha256", reviewed])
        completed_path = self.completed()[0]
        os.chmod(completed_path, 0o600)
        completed = json.loads(completed_path.read_text()); completed["outcome"] = "forged"
        completed_path.write_text(json.dumps(completed)); os.chmod(completed_path, 0o400)
        with self.assertRaises(rotation.SourceRotationError):
            self.execute(["status"])


if __name__ == "__main__":
    unittest.main()
