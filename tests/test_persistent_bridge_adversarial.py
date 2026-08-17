"""PB-5 hermetic adversarial matrix for the persistent bridge design."""
import os
from pathlib import Path
import tempfile
import unittest

from tools import credential_boundary_probe
from tools import heartbeat_sandbox as hs
from tools.heartbeat_child_env import build_hardened_child_env


class PersistentBridgeAdversarialMatrix(unittest.TestCase):
    def _policy(self):
        owner = "edge-codex-heartbeat"
        directory = {"owner": owner, "group": owner, "mode": "0700"}
        auth = {"owner": owner, "group": owner, "mode": "0600"}
        return hs.build_persistent_bridge_policy(
            {"sources": [{"name": "synthetic", "path": "/srv/evidence/source"}]},
            edge_home="/home/operator/edge-install",
            runtime_output_root="/var/lib/edge-codex-heartbeat/runtime-output",
            codex_home="/var/lib/edge-codex-heartbeat/codex-home",
            service_identity=owner, runtime_metadata=directory,
            codex_home_metadata=directory, auth_file_metadata=auth,
            operator_home=Path("/home/operator"), require_sources_exist=False,
        )

    def test_synthetic_source_denies_write_while_runtime_accepts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir(mode=0o555)
            runtime.mkdir(mode=0o700)
            os.chmod(source, 0o555)
            os.chmod(runtime, 0o700)
            try:
                with self.assertRaises(PermissionError):
                    (source / "forbidden").write_text("no", encoding="utf-8")
                (runtime / "allowed").write_text("yes", encoding="utf-8")
                self.assertEqual((runtime / "allowed").read_text(), "yes")
            finally:
                os.chmod(source, 0o700)

    def test_closed_environment_drops_ambient_authority(self):
        env = build_hardened_child_env({
            "PATH": "/usr/bin", "HOME": "/private/codex",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
            "SSH_AUTH_SOCK": "/run/ssh.sock", "OP_SERVICE_ACCOUNT_TOKEN": "canary",
            "OPENAI_API_KEY": "canary", "EDGE_RUNTIME_ROOT": "/private/runtime",
        })
        self.assertEqual(env["EDGE_RUNTIME_ROOT"], "/private/runtime")
        for denied in (
            "DOCKER_HOST", "SSH_AUTH_SOCK", "OP_SERVICE_ACCOUNT_TOKEN", "OPENAI_API_KEY"
        ):
            self.assertNotIn(denied, env)

    def test_unit_hides_sensitive_paths_and_grants_only_two_write_roots(self):
        unit = hs.render_persistent_bridge_candidate(self._policy())
        self.assertIn("InaccessiblePaths=-/run/docker.sock", unit)
        self.assertIn("InaccessiblePaths=-/home/operator/.ssh", unit)
        self.assertIn("InaccessiblePaths=-/home/operator/.config/1Password", unit)
        writes = [line for line in unit.splitlines() if line.startswith("ReadWritePaths=")]
        self.assertEqual(writes, [
            "ReadWritePaths=/var/lib/edge-codex-heartbeat/runtime-output",
            "ReadWritePaths=/var/lib/edge-codex-heartbeat/codex-home",
        ])

    def test_same_identity_residual_is_required_not_hidden(self):
        receipt = credential_boundary_probe.run_same_identity_negative_proof()
        self.assertTrue(receipt["same_identity_readable"])
        self.assertFalse(receipt["preventive_isolation_from_same_identity"])
        self.assertTrue(receipt["terminal_gate_rejected_tool"])


if __name__ == "__main__":
    unittest.main()
