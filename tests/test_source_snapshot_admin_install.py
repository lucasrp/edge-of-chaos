"""Hermetic failure-oriented tests for the one-shot admin installer."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import source_snapshot_admin_install as installer


class SourceSnapshotAdminInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.libexec = self.root / "libexec"
        self.sbin = self.root / "sbin"
        self.state = self.root / "state"
        self.snapshots = self.state / "snapshots"
        for path, mode in ((self.source, 0o700), (self.libexec, 0o755),
                           (self.sbin, 0o755), (self.state, 0o711),
                           (self.snapshots, 0o700)):
            path.mkdir(mode=mode)
        repo_tools = Path(__file__).resolve().parents[1] / "tools"
        for name in installer.SOURCE_FILES:
            (self.source / name).write_bytes((repo_tools / name).read_bytes())
        self.uid, self.gid = os.getuid(), os.getgid()
        self.layout = installer.InstallLayout(
            source_dir=self.source, libexec_parent=self.libexec,
            sbin_parent=self.sbin, state_base=self.state, snapshots=self.snapshots,
            expected_uid=self.uid, expected_gid=self.gid,
        )
        self.snapshot_canary = self.snapshots / "preexisting-canary"
        self.snapshot_canary.write_bytes(b"SNAPSHOT_MUST_NOT_CHANGE")

    def tearDown(self):
        for current, _dirs, files in os.walk(self.root):
            try:
                os.chmod(current, 0o700)
            except FileNotFoundError:
                pass
            for name in files:
                try:
                    os.chmod(Path(current) / name, 0o600)
                except FileNotFoundError:
                    pass
        self.tmp.cleanup()

    def snapshot_fingerprint(self):
        return [(str(p.relative_to(self.snapshots)), p.read_bytes(),
                 p.stat().st_mode & 0o777)
                for p in sorted(self.snapshots.rglob("*")) if p.is_file()]

    def install(self, **kwargs):
        return installer.install(self.layout, token=lambda: "testtoken00000001", **kwargs)

    def rollback(self, **kwargs):
        return installer.rollback(self.layout, token=lambda: "testtoken00000002", **kwargs)

    def assert_absent(self):
        self.assertFalse(self.layout.package.exists())
        self.assertFalse(self.layout.launcher.exists())
        self.assertFalse(self.layout.receipts.exists())
        self.assertFalse(self.layout.marker.exists())

    def test_success_is_exact_launcher_last_and_snapshot_preserving(self):
        before = self.snapshot_fingerprint()
        points = []
        result = self.install(fault=points.append)
        self.assertTrue(result["installed"])
        self.assertEqual(points[-1], "after_launcher_publish")
        self.assertEqual(self.snapshot_fingerprint(), before)
        self.assertFalse(self.layout.marker.exists())
        manifest = json.loads((self.layout.package / "INSTALL-MANIFEST.json").read_text())
        self.assertEqual(manifest["schema"], installer.INSTALL_SCHEMA)
        self.assertEqual(self.layout.launcher.read_bytes(), installer.LAUNCHER)
        self.assertIn(b"/usr/bin/python3 -B ", installer.LAUNCHER)
        self.assertEqual(self.layout.launcher.stat().st_mode & 0o777, 0o750)
        self.assertEqual({p.name for p in self.layout.receipts.iterdir()},
                         {"pending", "completed", ".journal.lock", ".rotation.lock"})

    def test_every_publish_fault_cleans_exactly_and_preserves_snapshots(self):
        for point in ("before_package_publish", "after_package_publish",
                      "after_receipts_publish", "after_launcher_publish"):
            with self.subTest(point=point):
                before = self.snapshot_fingerprint()
                def fail(here):
                    if here == point:
                        raise RuntimeError(point)
                with self.assertRaisesRegex(RuntimeError, point):
                    self.install(fault=fail)
                self.assert_absent()
                self.assertEqual(self.snapshot_fingerprint(), before)

    def test_collision_refuses_without_transaction_or_snapshot_write(self):
        self.layout.launcher.write_text("collision")
        before = self.snapshot_fingerprint()
        with self.assertRaisesRegex(installer.SnapshotAdminInstallError, "already exists"):
            self.install()
        self.assertFalse(self.layout.marker.exists())
        self.assertEqual(self.layout.launcher.read_text(), "collision")
        self.assertEqual(self.snapshot_fingerprint(), before)

    def test_bad_parent_mode_refuses_before_transaction(self):
        self.state.chmod(0o700)
        with self.assertRaisesRegex(installer.SnapshotAdminInstallError, "owner or mode"):
            self.install()
        self.assertFalse(self.layout.marker.exists())

    def test_exact_unused_install_rolls_back_without_snapshot_change(self):
        self.install()
        before = self.snapshot_fingerprint()
        result = self.rollback()
        self.assertFalse(result["installed"])
        self.assertFalse(result["operational_receipts_deleted"])
        self.assertTrue(result["empty_receipt_infrastructure_removed"])
        self.assert_absent()
        self.assertEqual(self.snapshot_fingerprint(), before)

    def test_tamper_migration_or_receipt_refuses_rollback_without_move(self):
        scenarios = ("tamper", "receipt", "index", "generations", "pending")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.install()
                if scenario == "tamper":
                    target = self.layout.package / "tools/source_rotation.py"
                    target.chmod(0o600); target.write_text("tampered"); target.chmod(0o640)
                elif scenario == "receipt":
                    (self.layout.receipts / "completed/receipt.json").write_text("{}")
                elif scenario == "index":
                    (self.snapshots / "index.json").write_text("{}")
                elif scenario == "generations":
                    (self.snapshots / "generations").mkdir()
                else:
                    (self.snapshots / "rotation.pending").write_text("x")
                with self.assertRaises(installer.SnapshotAdminInstallError):
                    self.rollback()
                self.assertTrue(self.layout.launcher.exists())
                self.assertTrue(self.layout.package.exists())
                self.assertTrue(self.layout.receipts.exists())
                self.assertFalse(self.layout.marker.exists())
                self.tearDown(); self.setUp()

    def test_precommit_rollback_fault_restores_exact_install(self):
        for point in ("after_launcher_quarantine", "after_package_quarantine"):
            with self.subTest(point=point):
                self.install()
                before = self.snapshot_fingerprint()
                def fail(here):
                    if here == point:
                        raise RuntimeError(point)
                with self.assertRaisesRegex(RuntimeError, point):
                    self.rollback(fault=fail)
                installer._validate_installed(self.layout)
                self.assertFalse(self.layout.marker.exists())
                self.assertEqual(self.snapshot_fingerprint(), before)
                self.tearDown(); self.setUp()

    def test_postcommit_fault_is_explicit_and_never_touches_snapshots(self):
        self.install()
        before = self.snapshot_fingerprint()
        def fail(here):
            if here == "after_rollback_commit":
                raise RuntimeError(here)
        with self.assertRaises(installer.SnapshotAdminRollbackCommitted):
            self.rollback(fault=fail)
        self.assertFalse(self.layout.launcher.exists())
        self.assertFalse(self.layout.package.exists())
        self.assertFalse(self.layout.receipts.exists())
        self.assertTrue(self.layout.marker.exists())
        self.assertEqual(self.snapshot_fingerprint(), before)
        self.assertEqual(len(list(self.sbin.glob(".edge-source-snapshot-admin-rollback-*"))), 1)
        self.assertEqual(len(list(self.libexec.glob(".edge-source-snapshot-admin-rollback-*"))), 1)
        self.assertEqual(len(list(self.state.glob(".admin-receipts-rollback-*"))), 1)

    def test_manifest_hash_and_inventory_tampering_fail_closed(self):
        self.install()
        path = self.layout.package / "INSTALL-MANIFEST.json"
        path.chmod(0o600)
        data = json.loads(path.read_text())
        data["artifacts"] = data["artifacts"][:-1]
        path.write_text(json.dumps(data))
        path.chmod(0o400)
        with self.assertRaisesRegex(installer.SnapshotAdminInstallError, "inventory"):
            self.rollback()
        self.assertTrue(self.layout.launcher.exists())

    def test_public_cli_has_only_install_and_rollback_without_overrides(self):
        parser = installer._parser()
        self.assertEqual(parser.parse_args(["install"]).operation, "install")
        self.assertEqual(parser.parse_args(["rollback"]).operation, "rollback")
        for argv in (("delete",), ("install", "--force"),
                     ("install", "--path", str(self.root)), ("install", "--timer")):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                parser.parse_args(list(argv))

    def test_main_refuses_non_root_before_parsing_or_state_access(self):
        with mock.patch.object(installer.os, "geteuid", return_value=1000), \
             mock.patch.object(installer, "install") as install_call, \
             mock.patch.object(installer, "rollback") as rollback_call:
            self.assertEqual(installer.main(["not-even-a-command"]), 2)
        install_call.assert_not_called()
        rollback_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
