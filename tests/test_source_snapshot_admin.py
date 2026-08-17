"""Hermetic operator-interface tests; no installed snapshot or root service is used."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tools import source_rotation as rotation
from tools import source_snapshot_admin as admin


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class SourceSnapshotAdmin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = self.root / "snapshots"
        self.snapshots.mkdir()
        self.uid, self.gid = os.getuid(), os.getgid()
        self.payload = b"SYNTHETIC_ADMIN_CONTENT_CANARY"
        self._generation(self.snapshots, "current", self.payload)
        self.config = admin.AdminConfig(
            snapshots_root=self.snapshots,
            lock_path=self.root / "rotation.lock",
            expected_uid=self.uid,
            expected_gid=self.gid,
            generation_id="synthetic-initial",
            max_candidate_bytes=1024 * 1024,
            safety_margin_bytes=1024 * 1024,
        )
        self.clock = lambda: datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

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
        row = {
            "source": "synthetic", "relative_path": "note.md", "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
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

    def execute(self, argv):
        return admin.execute(argv, config=self.config, now=self.clock)

    def test_status_and_preview_are_read_only_content_free_receipts(self):
        before = [(p.relative_to(self.snapshots).as_posix(), p.lstat().st_ino,
                   p.lstat().st_mode, p.lstat().st_mtime_ns)
                  for p in sorted([self.snapshots, *self.snapshots.rglob("*")])]
        status = self.execute(["status"])
        preview = self.execute(["preview"])
        after = [(p.relative_to(self.snapshots).as_posix(), p.lstat().st_ino,
                  p.lstat().st_mode, p.lstat().st_mtime_ns)
                 for p in sorted([self.snapshots, *self.snapshots.rglob("*")])]
        self.assertEqual(before, after)
        self.assertEqual(status["result"]["status"], "legacy_valid")
        self.assertFalse(status["state_changed"])
        self.assertFalse(preview["state_changed"])
        encoded = json.dumps([status, preview])
        self.assertNotIn(self.payload.decode(), encoded)
        self.assertFalse(preview["credential_present"])
        self.assertFalse(preview["heartbeat_touched"])

    def test_apply_requires_exact_live_preview_hash_and_retains_legacy(self):
        preview = self.execute(["preview"])["result"]
        with self.assertRaisesRegex(rotation.SourceRotationError, "does not match"):
            self.execute(["apply", "--preview-sha256", "0" * 64])
        self.assertFalse((self.snapshots / "index.json").exists())
        receipt = self.execute(["apply", "--preview-sha256", preview["preview_sha256"]])
        self.assertTrue(receipt["state_changed"])
        self.assertEqual(receipt["result"]["reviewed_preview_sha256"],
                         preview["preview_sha256"])
        self.assertTrue((self.snapshots / "current").is_dir())
        self.assertTrue((self.snapshots / "generations/synthetic-initial").is_dir())
        status = self.execute(["status"])
        self.assertEqual(status["result"]["status"], "indexed_valid")

    def test_apply_rejects_drift_after_review(self):
        preview_hash = self.execute(["preview"])["result"]["preview_sha256"]
        target = self.snapshots / "current/sources/synthetic/note.md"
        os.chmod(target, 0o600)
        target.write_bytes(b"DRIFTED_SYNTHETIC_CONTENT")
        os.chmod(target, 0o400)
        with self.assertRaises(rotation.SourceRotationError):
            self.execute(["apply", "--preview-sha256", preview_hash])
        self.assertFalse((self.snapshots / "index.json").exists())

    def test_recover_requires_clean_state_and_exact_reviewed_index_hash(self):
        preview = self.execute(["preview"])["result"]
        self.execute(["apply", "--preview-sha256", preview["preview_sha256"]])
        os.chmod(self.snapshots / "generations", 0o700)
        rotation._begin_transaction(self.snapshots)
        status = self.execute(["status"])
        self.assertEqual(status["result"]["status"], "recoverable_clean")
        with self.assertRaisesRegex(rotation.SourceRotationError, "does not match"):
            self.execute(["recover", "--index-sha256", "0" * 64])
        self.assertTrue((self.snapshots / "rotation.pending").exists())
        receipt = self.execute([
            "recover", "--index-sha256", status["result"]["index_sha256"],
        ])
        self.assertTrue(receipt["state_changed"])
        self.assertFalse((self.snapshots / "rotation.pending").exists())

    def test_interface_exposes_no_path_force_delete_timer_or_retention_flags(self):
        forbidden = (
            ["preview", "--path", str(self.snapshots)],
            ["apply", "--preview-sha256", "0" * 64, "--force"],
            ["delete"], ["preview", "--timer"], ["status", "--retention", "9"],
        )
        for argv in forbidden:
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                with mock.patch("sys.stderr"):
                    self.execute(argv)

    def test_main_refuses_non_root_before_parsing_or_touching_state(self):
        with mock.patch("tools.source_snapshot_admin.os.geteuid", return_value=1000), \
                mock.patch("sys.stderr"):
            self.assertEqual(admin.main(["status"]), 2)
        self.assertFalse((self.snapshots / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
