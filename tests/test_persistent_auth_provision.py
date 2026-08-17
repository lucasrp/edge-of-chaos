"""Hermetic synthetic-canary tests for atomic persistent auth provisioning."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import persistent_auth_provision as provision


class PersistentAuthProvision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / "synthetic-source"
        self.home = root / "codex-home"
        self.home.mkdir(mode=0o700)
        os.chmod(self.home, 0o700)
        self.canary = b"EDGE_SYNTHETIC_PERSISTENT_AUTH_" + os.urandom(24).hex().encode()
        self.source.write_bytes(self.canary)
        os.chmod(self.source, 0o600)
        self.uid = os.getuid()
        self.gid = os.getgid()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kwargs):
        return provision.provision_auth_bundle(
            self.source, self.home,
            expected_uid=self.uid, expected_gid=self.gid, **kwargs,
        )

    def test_atomic_install_is_private_and_receipt_is_content_free(self):
        receipt = self._run()
        installed = self.home / "auth.json"
        self.assertEqual(installed.read_bytes(), self.canary)
        self.assertEqual(installed.stat().st_mode & 0o777, 0o600)
        self.assertEqual(installed.stat().st_nlink, 1)
        encoded = json.dumps(receipt, sort_keys=True).encode()
        self.assertNotIn(self.canary, encoded)
        self.assertNotIn(str(self.source).encode(), encoded)
        self.assertNotIn(str(self.home).encode(), encoded)
        self.assertTrue(receipt["atomic_replace"])
        self.assertFalse(receipt["content_reported"])

    def test_injected_crash_preserves_previous_complete_bundle(self):
        previous = b"EDGE_SYNTHETIC_PREVIOUS_AUTH"
        installed = self.home / "auth.json"
        installed.write_bytes(previous)
        os.chmod(installed, 0o600)

        def crash():
            raise RuntimeError("synthetic crash before replace")

        with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
            self._run(before_replace=crash)
        self.assertEqual(installed.read_bytes(), previous)
        self.assertEqual(list(self.home.glob(".auth.json.tmp-*")), [])

    def test_rejects_source_symlink_hardlink_wrong_mode_and_empty(self):
        root = Path(self.tmp.name)
        cases = []
        link = root / "source-link"
        link.symlink_to(self.source)
        cases.append(link)
        hard = root / "source-hard"
        os.link(self.source, hard)
        cases.append(self.source)
        for path in cases:
            with self.subTest(path=path), self.assertRaises(provision.AuthProvisionError):
                provision.provision_auth_bundle(
                    path, self.home, expected_uid=self.uid, expected_gid=self.gid
                )
        hard.unlink()
        os.chmod(self.source, 0o644)
        with self.assertRaisesRegex(provision.AuthProvisionError, "mode"):
            self._run()
        os.chmod(self.source, 0o600)
        self.source.write_bytes(b"")
        with self.assertRaisesRegex(provision.AuthProvisionError, "size"):
            self._run()

    def test_rejects_symlink_in_source_or_home_parent_chain(self):
        root = Path(self.tmp.name)
        real_source_parent = root / "real-source-parent"
        real_source_parent.mkdir()
        nested_source = real_source_parent / "source"
        nested_source.write_bytes(self.canary)
        os.chmod(nested_source, 0o600)
        source_link = root / "source-parent-link"
        source_link.symlink_to(real_source_parent, target_is_directory=True)
        with self.assertRaises(provision.AuthProvisionError):
            provision.provision_auth_bundle(
                source_link / "source", self.home,
                expected_uid=self.uid, expected_gid=self.gid,
            )

        real_home = root / "real-home"
        real_home.mkdir(mode=0o700)
        os.chmod(real_home, 0o700)
        home_link = root / "home-link"
        home_link.symlink_to(real_home, target_is_directory=True)
        with self.assertRaises(provision.AuthProvisionError):
            provision.provision_auth_bundle(
                self.source, home_link,
                expected_uid=self.uid, expected_gid=self.gid,
            )

    def test_rejects_unsafe_home_and_existing_destination(self):
        os.chmod(self.home, 0o755)
        with self.assertRaisesRegex(provision.AuthProvisionError, "0700"):
            self._run()
        os.chmod(self.home, 0o700)
        installed = self.home / "auth.json"
        installed.symlink_to(self.source)
        with self.assertRaisesRegex(provision.AuthProvisionError, "regular"):
            self._run()
        installed.unlink()
        installed.write_bytes(b"old")
        os.chmod(installed, 0o600)
        second = Path(self.tmp.name) / "second-link"
        os.link(installed, second)
        with self.assertRaisesRegex(provision.AuthProvisionError, "hard link"):
            self._run()


if __name__ == "__main__":
    unittest.main()
