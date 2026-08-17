"""Hermetic tests for the deterministic no-credential source stage."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import source_stage as stage


class SourceStage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.output = self.root / "output"
        self.source.mkdir()
        self.output.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, **kwargs):
        return stage.build_stage_plan(
            [{"name": "synthetic", "path": str(self.source)}],
            stage_root=self.output, **kwargs,
        )

    def test_plan_is_metadata_only_and_excludes_generated_and_secret_names(self):
        (self.source / "note.md").write_text("PUBLIC_CANARY")
        (self.source / ".env").write_text("SECRET_CANARY")
        generated = self.source / ".git"
        generated.mkdir()
        (generated / "config").write_text("GENERATED_CANARY")
        plan = self._plan()
        encoded = json.dumps(plan, sort_keys=True)
        self.assertFalse(plan["content_read"])
        self.assertNotIn("PUBLIC_CANARY", encoded)
        self.assertNotIn("SECRET_CANARY", encoded)
        self.assertEqual([row["relative_path"] for row in plan["included"]], ["note.md"])
        self.assertEqual({row["reason"] for row in plan["excluded"]},
                         {"generated-directory", "secret-like-name"})

    def test_obsidian_application_state_is_excluded_but_vault_notes_remain(self):
        (self.source / "note.md").write_text("VAULT_NOTE_CANARY")
        obsidian = self.source / ".obsidian"
        obsidian.mkdir()
        (obsidian / "graph.json").write_text("APPLICATION_STATE_CANARY")
        plan = self._plan()
        self.assertEqual(
            [row["relative_path"] for row in plan["included"]], ["note.md"]
        )
        self.assertEqual(plan["excluded"], [{
            "source": "synthetic", "relative_path": ".obsidian",
            "reason": "generated-directory",
        }])

    def test_drive_temporary_directory_is_excluded(self):
        temporary = self.source / ".tmp.driveupload"
        temporary.mkdir()
        (temporary / "fragment").write_text("SYNC_CANARY")
        plan = self._plan()
        self.assertEqual(plan["included"], [])
        self.assertEqual(plan["excluded"], [{
            "source": "synthetic", "relative_path": ".tmp.driveupload",
            "reason": "generated-directory",
        }])

    def test_operating_system_metadata_files_are_excluded(self):
        (self.source / "desktop.ini").write_text("WINDOWS_METADATA_CANARY")
        (self.source / ".DS_Store").write_text("MACOS_METADATA_CANARY")
        (self.source / "note.md").write_text("KNOWLEDGE_CANARY")
        plan = self._plan()
        self.assertEqual(
            [row["relative_path"] for row in plan["included"]], ["note.md"]
        )
        self.assertEqual(
            {row["reason"] for row in plan["excluded"]}, {"generated-file"}
        )

    def test_file_type_allowlist_excludes_unknown_and_limits_extensionless_names(self):
        for name in ("note.md", ".dockerignore", ".gitignore", "Dockerfile", "uv.lock"):
            (self.source / name).write_text("ALLOWED_TYPE_CANARY")
        for name in ("payload.exe", "unknown-extensionless"):
            (self.source / name).write_text("UNSUPPORTED_TYPE_CANARY")
        plan = self._plan()
        self.assertEqual(
            {row["relative_path"] for row in plan["included"]},
            {"note.md", ".dockerignore", ".gitignore", "Dockerfile", "uv.lock"},
        )
        self.assertEqual(
            {row["relative_path"] for row in plan["excluded"]},
            {"payload.exe", "unknown-extensionless"},
        )
        self.assertEqual(
            {row["reason"] for row in plan["excluded"]},
            {"unsupported-file-type"},
        )

    def test_materializes_complete_hashed_snapshot_without_excluded_canary(self):
        (self.source / "docs").mkdir()
        payload = b"SYNTHETIC_ALLOWED_PAYLOAD"
        (self.source / "docs" / "note.md").write_bytes(payload)
        (self.source / "auth.json").write_text("SYNTHETIC_SECRET_CANARY")
        plan = self._plan()
        manifest = stage.materialize_stage(
            plan, stage_root=self.output, snapshot_id="synthetic-001"
        )
        final = self.output / "synthetic-001"
        self.assertEqual((final / "sources/synthetic/docs/note.md").read_bytes(), payload)
        self.assertFalse((final / "sources/synthetic/auth.json").exists())
        persisted = (final / "manifest.json").read_text()
        self.assertNotIn("SYNTHETIC_SECRET_CANARY", persisted)
        self.assertEqual(json.loads(persisted), manifest)
        self.assertTrue(manifest["files"][0]["sha256"])
        self.assertFalse(manifest["credential_present"])

    def test_runtime_artifacts_are_excluded_but_dependency_lock_is_kept(self):
        runtime_names = (
            "observer.db", "observer.sqlite", "observer.sqlite3",
            "observer.db-wal", "observer.sqlite-shm", "observer.sqlite3-journal",
            "worker.pid", "runtime.log", "observer.lock", "watchdog.lock",
        )
        for name in runtime_names:
            (self.source / name).write_text("RUNTIME_CANARY")
        (self.source / "uv.lock").write_text("DEPENDENCY_LOCK_CANARY")
        plan = self._plan()
        self.assertEqual(
            [row["relative_path"] for row in plan["included"]], ["uv.lock"]
        )
        self.assertEqual(
            {row["relative_path"] for row in plan["excluded"]}, set(runtime_names)
        )
        self.assertEqual(
            {row["reason"] for row in plan["excluded"]}, {"runtime-artifact"}
        )

    def test_rejects_symlink_hardlink_special_file_and_overlaps(self):
        target = self.source / "target"
        target.write_text("x")
        link = self.source / "link"
        link.symlink_to(target)
        with self.assertRaisesRegex(stage.SourceStageError, "symlink"):
            self._plan()
        link.unlink()
        hard = self.source / "hard"
        os.link(target, hard)
        with self.assertRaisesRegex(stage.SourceStageError, "hard-linked"):
            self._plan()
        hard.unlink()
        fifo = self.source / "pipe"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(stage.SourceStageError, "non-regular"):
            self._plan()
        fifo.unlink()
        with self.assertRaisesRegex(stage.SourceStageError, "overlap"):
            stage.build_stage_plan(
                [{"name": "synthetic", "path": str(self.source)}],
                stage_root=self.source / "stage",
            )

    def test_rejects_symlink_in_source_parent_chain(self):
        real = self.root / "real"
        real.mkdir()
        (real / "note.md").write_text("synthetic")
        linked = self.root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(stage.SourceStageError, "symlink"):
            stage.build_stage_plan(
                [{"name": "synthetic", "path": str(linked)}], stage_root=self.output
            )

    def test_copy_traverses_execute_only_parent_without_listing_it(self):
        corridor = self.root / "corridor"
        corridor.mkdir()
        source = corridor / "source"
        source.mkdir()
        (source / "note.md").write_text("synthetic")
        os.chmod(corridor, 0o111)
        try:
            plan = stage.build_stage_plan(
                [{"name": "synthetic", "path": str(source)}], stage_root=self.output
            )
            stage.materialize_stage(
                plan, stage_root=self.output, snapshot_id="execute-only-parent"
            )
        finally:
            os.chmod(corridor, 0o700)
        self.assertEqual(
            (self.output / "execute-only-parent/sources/synthetic/note.md").read_text(),
            "synthetic",
        )

    def test_source_change_after_plan_fails_closed_and_leaves_no_snapshot(self):
        source_file = self.source / "note.md"
        source_file.write_text("before")
        plan = self._plan()

        def mutate():
            source_file.write_text("after-change")

        with self.assertRaisesRegex(stage.SourceStageError, "changed"):
            stage.materialize_stage(
                plan, stage_root=self.output, snapshot_id="race", before_copy=mutate
            )
        self.assertFalse((self.output / "race").exists())
        self.assertEqual(list(self.output.glob(".stage-*")), [])

    def test_copy_io_error_names_only_source_and_relative_path(self):
        (self.source / "note.md").write_text("synthetic")
        plan = self._plan()
        def fail_read(fd, size):
            raise OSError(5, "synthetic input/output error")
        with mock.patch("tools.source_stage.os.read", side_effect=fail_read):
            with self.assertRaisesRegex(
                stage.SourceStageError, r"synthetic:note\.md.*input/output"
            ):
                stage.materialize_stage(
                    plan, stage_root=self.output, snapshot_id="io-error"
                )
        self.assertFalse((self.output / "io-error").exists())
        self.assertEqual(list(self.output.glob(".stage-*")), [])

    def test_tampered_plan_existing_snapshot_and_bounds_fail_closed(self):
        (self.source / "note.md").write_text("bounded")
        plan = self._plan()
        plan["summary"]["included_files"] = 999
        with self.assertRaisesRegex(stage.SourceStageError, "integrity"):
            stage.materialize_stage(plan, stage_root=self.output, snapshot_id="tampered")
        with self.assertRaisesRegex(stage.SourceStageError, "bound"):
            self._plan(max_bytes=1)
        clean = self._plan()
        stage.materialize_stage(clean, stage_root=self.output, snapshot_id="once")
        with self.assertRaisesRegex(stage.SourceStageError, "already exists"):
            stage.materialize_stage(clean, stage_root=self.output, snapshot_id="once")


if __name__ == "__main__":
    unittest.main()
