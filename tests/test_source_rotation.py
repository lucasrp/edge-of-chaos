"""Hermetic tests for manual immutable source-snapshot rotation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from tools import source_rotation as rotation


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class SourceRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = self.root / "snapshots"
        self.generations = self.snapshots / "generations"
        self.lock = self.root / "rotation.lock"
        self.snapshots.mkdir()
        self.generations.mkdir()
        self.uid = os.getuid()
        self.gid = os.getgid()

    def tearDown(self):
        for current, dirs, files in os.walk(self.root):
            os.chmod(current, 0o700)
            for name in files:
                os.chmod(Path(current) / name, 0o600)
        self.tmp.cleanup()

    def generation(self, parent, generation_id, payload=b"synthetic"):
        root = parent / generation_id
        source = root / "sources" / "synthetic"
        source.mkdir(parents=True)
        target = source / "note.md"
        target.write_bytes(payload)
        row = {
            "source": "synthetic", "relative_path": "note.md", "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        manifest = {
            "schema": rotation.MANIFEST_SCHEMA, "snapshot_id": generation_id,
            "plan_sha256": "0" * 64, "files": [row], "excluded": [],
            "summary": {"included_files": 1, "included_bytes": len(payload),
                        "excluded_entries": 0},
            "credential_present": False, "llm_invoked": False, "network_used": False,
        }
        manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
        (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")
        rotation.seal_generation(root, uid=self.uid, gid=self.gid)
        return root, manifest

    def initialize(self):
        self.generation(self.generations, "g1", b"one")
        return rotation.initialize_index_for_generation(
            self.snapshots, lock_path=self.lock, generation_id="g1", committed_at="t1",
            expected_uid=self.uid, expected_gid=self.gid,
        )

    def rotate(self, generation_id="g2", payload=b"two", fault=None):
        candidate, _ = self.generation(self.generations, f".candidate-{generation_id}", payload)
        return rotation.rotate_candidate(
            self.snapshots, lock_path=self.lock, candidate=candidate, generation_id=generation_id,
            committed_at=f"t-{generation_id}", expected_uid=self.uid,
            expected_gid=self.gid, fault=fault,
        )

    def legacy(self, payload=b"legacy"):
        self.generations.rmdir()
        return self.generation(self.snapshots, "current", payload)

    def test_initial_index_and_normal_rotation_keep_current_and_previous(self):
        first = self.initialize()
        self.assertEqual((first["current"], first["previous"]), ("g1", None))
        second = self.rotate()
        self.assertEqual((second["current"], second["previous"]), ("g2", "g1"))
        self.assertEqual({p.name for p in self.generations.iterdir()}, {"g1", "g2"})

    def test_second_rotation_deletes_only_unreferenced_old_previous(self):
        self.initialize()
        self.rotate()
        third = self.rotate("g3", b"three")
        self.assertEqual((third["current"], third["previous"]), ("g3", "g2"))
        self.assertEqual({p.name for p in self.generations.iterdir()}, {"g2", "g3"})

    def test_rollback_swaps_roles_without_changing_generation_bytes(self):
        self.initialize()
        current = self.rotate()
        before = {name: current["manifest_sha256"][name] for name in ("g1", "g2")}
        rolled = rotation.rollback_index(
            self.snapshots, lock_path=self.lock, committed_at="rollback", expected_uid=self.uid,
            expected_gid=self.gid,
        )
        self.assertEqual((rolled["current"], rolled["previous"]), ("g1", "g2"))
        self.assertEqual(rolled["manifest_sha256"], before)

    def test_tampered_manifest_file_and_unexpected_file_fail_closed(self):
        self.initialize()
        os.chmod(self.generations / "g1/sources/synthetic/note.md", 0o600)
        (self.generations / "g1/sources/synthetic/note.md").write_text("tampered")
        os.chmod(self.generations / "g1/sources/synthetic/note.md", 0o400)
        with self.assertRaisesRegex(rotation.SourceRotationError, "integrity"):
            self.rotate()

        self.tearDown(); self.setUp(); self.initialize()
        extra = self.generations / "g1/sources/synthetic/extra.md"
        os.chmod(extra.parent, 0o700); extra.write_text("extra"); os.chmod(extra, 0o400)
        os.chmod(extra.parent, 0o500)
        with self.assertRaisesRegex(rotation.SourceRotationError, "unexpected"):
            self.rotate()

    def test_bad_modes_symlink_and_hardlink_are_rejected(self):
        self.initialize()
        file = self.generations / "g1/sources/synthetic/note.md"
        os.chmod(file, 0o600)
        with self.assertRaisesRegex(rotation.SourceRotationError, "mode"):
            self.rotate()

        self.tearDown(); self.setUp(); self.initialize()
        candidate, _ = self.generation(self.generations, ".candidate-g2", b"two")
        os.chmod(candidate / "sources/synthetic", 0o700)
        link = candidate / "sources/synthetic/link.md"
        link.symlink_to("note.md")
        os.chmod(candidate / "sources/synthetic", 0o500)
        with self.assertRaisesRegex(rotation.SourceRotationError, "symlink"):
            rotation.rotate_candidate(
                self.snapshots, lock_path=self.lock, candidate=candidate,
                generation_id="g2", committed_at="t2",
                expected_uid=self.uid, expected_gid=self.gid,
            )

    def test_unknown_generation_blocks_rotation(self):
        self.initialize()
        (self.generations / "orphan").mkdir()
        with self.assertRaisesRegex(rotation.SourceRotationError, "unexplained"):
            self.rotate()

    def test_failures_before_commit_preserve_old_index_and_remove_candidate(self):
        for failure_point in ("before_publish", "after_publish", "before_index_commit"):
            with self.subTest(failure_point=failure_point):
                self.tearDown(); self.setUp(); self.initialize()
                before = (self.snapshots / "index.json").read_bytes()
                def fault(point):
                    if point == failure_point:
                        raise RuntimeError("synthetic crash")
                with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                    self.rotate(fault=fault)
                self.assertEqual((self.snapshots / "index.json").read_bytes(), before)
                self.assertEqual(json.loads(before)["current"], "g1")
                self.assertEqual({p.name for p in self.generations.iterdir()}, {"g1"})
                self.assertFalse((self.snapshots / "rotation.pending").exists())

    def test_failure_after_commit_is_reported_as_committed_cleanup_required(self):
        self.initialize(); self.rotate()
        def fault(point):
            if point == "before_retention_cleanup":
                raise RuntimeError("synthetic cleanup failure")
        with self.assertRaises(rotation.RotationCommittedCleanupRequired):
            self.rotate("g3", b"three", fault=fault)
        index = json.loads((self.snapshots / "index.json").read_text())
        self.assertEqual((index["current"], index["previous"]), ("g3", "g2"))
        self.assertTrue((self.generations / "g1").exists())
        candidate, _ = self.generation(self.generations, ".candidate-g4", b"four")
        with self.assertRaisesRegex(rotation.SourceRotationError, "unexplained"):
            rotation.rotate_candidate(
                self.snapshots, lock_path=self.lock, candidate=candidate,
                generation_id="g4", committed_at="t4",
                expected_uid=self.uid, expected_gid=self.gid,
            )

    def test_atomic_index_replace_failure_preserves_old_index_and_cleans_generation(self):
        self.initialize()
        before = (self.snapshots / "index.json").read_bytes()
        candidate, _ = self.generation(self.generations, ".candidate-g2", b"two")
        original = os.replace
        def fail_index_replace(source, destination, *args, **kwargs):
            if Path(destination).name == "index.json":
                raise OSError("synthetic index failure")
            return original(source, destination, *args, **kwargs)
        with mock.patch("tools.source_rotation.os.replace", side_effect=fail_index_replace):
            with self.assertRaisesRegex(OSError, "synthetic index failure"):
                rotation.rotate_candidate(
                    self.snapshots, lock_path=self.lock, candidate=candidate,
                    generation_id="g2", committed_at="t2", expected_uid=self.uid,
                    expected_gid=self.gid,
                )
        self.assertEqual((self.snapshots / "index.json").read_bytes(), before)
        self.assertEqual({p.name for p in self.generations.iterdir()}, {"g1"})
        self.assertEqual(list(self.snapshots.glob(".index-*.tmp")), [])
        self.assertFalse((self.snapshots / "rotation.pending").exists())

    def test_failure_immediately_after_commit_keeps_new_current_and_blocks_next_rotation(self):
        self.initialize()
        def fault(point):
            if point == "after_index_commit":
                raise RuntimeError("synthetic post-commit failure")
        with self.assertRaises(rotation.RotationCommittedCleanupRequired):
            self.rotate(fault=fault)
        index = json.loads((self.snapshots / "index.json").read_text())
        self.assertEqual((index["current"], index["previous"]), ("g2", "g1"))
        self.assertEqual({p.name for p in self.generations.iterdir()}, {"g1", "g2"})
        self.assertTrue((self.snapshots / "rotation.pending").exists())
        candidate, _ = self.generation(self.generations, ".candidate-g3", b"three")
        with self.assertRaisesRegex(rotation.SourceRotationError, "requires review"):
            rotation.rotate_candidate(
                self.snapshots, lock_path=self.lock, candidate=candidate,
                generation_id="g3", committed_at="t3", expected_uid=self.uid,
                expected_gid=self.gid,
            )

    def test_concurrent_lock_fails_closed(self):
        lock = self.root / "rotation.lock"
        held = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(rotation.SourceRotationError, "holds the lock"):
                with rotation.rotation_lock(lock):
                    self.fail("contended lock entered")
        finally:
            fcntl.flock(held, fcntl.LOCK_UN); os.close(held)

    def test_invalid_index_and_no_previous_rollback_are_rejected(self):
        self.initialize()
        with self.assertRaisesRegex(rotation.SourceRotationError, "previous"):
            rotation.rollback_index(
                self.snapshots, lock_path=self.lock, committed_at="rollback",
                expected_uid=self.uid,
                expected_gid=self.gid,
            )
        os.chmod(self.snapshots / "index.json", 0o600)
        payload = json.loads((self.snapshots / "index.json").read_text())
        payload["current"] = "forged"
        (self.snapshots / "index.json").write_text(json.dumps(payload))
        with self.assertRaisesRegex(rotation.SourceRotationError, "owner or mode"):
            self.rotate()

    def test_legacy_preview_is_content_bound_read_only_and_capacity_aware(self):
        legacy, manifest = self.legacy()
        before = {p.relative_to(self.snapshots).as_posix() for p in self.snapshots.rglob("*")}
        preview = rotation.preview_legacy_migration(
            self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
            expected_gid=self.gid, max_candidate_bytes=1024,
            safety_margin_bytes=2048,
        )
        after = {p.relative_to(self.snapshots).as_posix() for p in self.snapshots.rglob("*")}
        self.assertEqual(before, after)
        self.assertEqual(preview["legacy_manifest_sha256"], manifest["manifest_sha256"])
        self.assertEqual(preview["capacity"]["required_free_bytes"], 3072)
        self.assertRegex(preview["observation_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(preview["content_read"])
        self.assertFalse(preview["state_changed"])
        self.assertTrue(legacy.is_dir())

    def test_preview_bound_migration_copies_verifies_indexes_and_retains_legacy(self):
        legacy, manifest = self.legacy()
        preview = rotation.preview_legacy_migration(
            self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
            expected_gid=self.gid, max_candidate_bytes=1024,
            safety_margin_bytes=2048,
        )
        result = rotation.apply_legacy_migration(
            self.snapshots, lock_path=self.lock, preview=preview, committed_at="migration",
            expected_uid=self.uid, expected_gid=self.gid,
        )
        self.assertEqual((result["current"], result["previous"]), ("legacy-001", None))
        self.assertTrue(result["legacy_retained"])
        self.assertTrue(legacy.is_dir())
        copied = rotation.validate_generation(
            self.snapshots / "generations/legacy-001",
            expected_uid=self.uid, expected_gid=self.gid,
        )
        self.assertEqual(copied["manifest_sha256"], manifest["manifest_sha256"])
        self.assertEqual(stat.S_IMODE((self.snapshots / "generations").stat().st_mode), 0o500)
        self.assertFalse((self.snapshots / "rotation.pending").exists())

    def test_tampered_preview_and_legacy_drift_fail_before_migration(self):
        legacy, _ = self.legacy()
        preview = rotation.preview_legacy_migration(
            self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
            expected_gid=self.gid, max_candidate_bytes=1024,
            safety_margin_bytes=2048,
        )
        tampered = dict(preview); tampered["generation_id"] = "forged"
        with self.assertRaisesRegex(rotation.SourceRotationError, "preview integrity"):
            rotation.apply_legacy_migration(
                self.snapshots, lock_path=self.lock, preview=tampered,
                committed_at="migration", expected_uid=self.uid, expected_gid=self.gid,
            )
        forged_capacity = json.loads(json.dumps(preview))
        forged_capacity["capacity"]["required_free_bytes"] += 1
        forged_capacity["preview_sha256"] = hashlib.sha256(canonical(
            rotation._preview_binding_payload(forged_capacity)
        )).hexdigest()
        forged_capacity["observation_sha256"] = hashlib.sha256(canonical(
            rotation._preview_observation_payload(forged_capacity)
        )).hexdigest()
        with self.assertRaisesRegex(rotation.SourceRotationError, "capacity arithmetic"):
            rotation.apply_legacy_migration(
                self.snapshots, lock_path=self.lock, preview=forged_capacity,
                committed_at="migration", expected_uid=self.uid, expected_gid=self.gid,
            )
        target = legacy / "sources/synthetic/note.md"
        os.chmod(target, 0o600); target.write_bytes(b"changed"); os.chmod(target, 0o400)
        with self.assertRaisesRegex(rotation.SourceRotationError, "integrity"):
            rotation.apply_legacy_migration(
                self.snapshots, lock_path=self.lock, preview=preview,
                committed_at="migration", expected_uid=self.uid, expected_gid=self.gid,
            )
        self.assertFalse((self.snapshots / "index.json").exists())
        self.assertFalse((self.snapshots / "generations").exists())

    def test_preview_authority_is_stable_across_free_space_observations(self):
        self.legacy()
        first_space = shutil._ntuple_diskusage(total=20000, used=10000, free=10000)
        second_space = shutil._ntuple_diskusage(total=20000, used=11000, free=9000)
        with mock.patch("tools.source_rotation.shutil.disk_usage", side_effect=(
            first_space, second_space,
        )):
            first = rotation.preview_legacy_migration(
                self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
                expected_gid=self.gid, max_candidate_bytes=1024, safety_margin_bytes=2048,
            )
            second = rotation.preview_legacy_migration(
                self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
                expected_gid=self.gid, max_candidate_bytes=1024, safety_margin_bytes=2048,
            )
        self.assertEqual(first["preview_sha256"], second["preview_sha256"])
        self.assertNotEqual(first["observation_sha256"], second["observation_sha256"])

    def test_insufficient_capacity_refuses_without_creating_migration_state(self):
        self.legacy()
        enough = shutil._ntuple_diskusage(total=10000, used=0, free=10000)
        low = shutil._ntuple_diskusage(total=10000, used=9999, free=1)
        with mock.patch("tools.source_rotation.shutil.disk_usage", return_value=enough):
            preview = rotation.preview_legacy_migration(
                self.snapshots, generation_id="legacy-001", expected_uid=self.uid,
                expected_gid=self.gid, max_candidate_bytes=1024,
                safety_margin_bytes=2048,
            )
        with mock.patch("tools.source_rotation.shutil.disk_usage", return_value=low):
            with self.assertRaisesRegex(rotation.SourceRotationError, "insufficient"):
                rotation.apply_legacy_migration(
                    self.snapshots, lock_path=self.lock, preview=preview,
                    committed_at="migration", expected_uid=self.uid, expected_gid=self.gid,
                )
        self.assertFalse((self.snapshots / "index.json").exists())
        self.assertFalse((self.snapshots / "generations").exists())

    def test_clean_pending_transaction_requires_reviewed_hash_then_clears(self):
        self.initialize()
        def fault(point):
            if point == "after_index_commit":
                raise RuntimeError("synthetic post-commit failure")
        with self.assertRaises(rotation.RotationCommittedCleanupRequired):
            self.rotate(fault=fault)
        status = rotation.inspect_pending_transaction(
            self.snapshots, expected_uid=self.uid, expected_gid=self.gid,
        )
        self.assertEqual(status["status"], "recoverable_clean")
        with self.assertRaisesRegex(rotation.SourceRotationError, "changed after review"):
            rotation.clear_recovered_transaction(
                self.snapshots, lock_path=self.lock, expected_index_sha256="0" * 64,
                expected_uid=self.uid, expected_gid=self.gid,
            )
        result = rotation.clear_recovered_transaction(
            self.snapshots, lock_path=self.lock,
            expected_index_sha256=status["index_sha256"], expected_uid=self.uid,
            expected_gid=self.gid,
        )
        self.assertTrue(result["state_changed"])
        self.assertFalse((self.snapshots / "rotation.pending").exists())

    def test_pending_transaction_with_orphan_is_never_auto_cleared(self):
        self.initialize()
        rotation._begin_transaction(self.snapshots)
        orphan, _ = self.generation(self.generations, "orphan", b"orphan")
        status = rotation.inspect_pending_transaction(
            self.snapshots, expected_uid=self.uid, expected_gid=self.gid,
        )
        self.assertEqual(status["status"], "blocked_generation_mismatch")
        self.assertEqual(status["extra_generation_ids"], [orphan.name])
        with self.assertRaisesRegex(rotation.SourceRotationError, "not safe"):
            rotation.clear_recovered_transaction(
                self.snapshots, lock_path=self.lock,
                expected_index_sha256=status["index_sha256"], expected_uid=self.uid,
                expected_gid=self.gid,
            )


if __name__ == "__main__":
    unittest.main()
