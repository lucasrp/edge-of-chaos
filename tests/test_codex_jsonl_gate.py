"""Hermetic PB-4 tests; no Codex, network, auth or LLM."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import codex_jsonl_gate as gate
from tools import heartbeat_sandbox as hs


class JsonlCompatibilityGate(unittest.TestCase):
    def _policy(self):
        meta_dir = {"owner": "edge-codex-heartbeat", "group": "edge-codex-heartbeat", "mode": "0700"}
        meta_file = {"owner": "edge-codex-heartbeat", "group": "edge-codex-heartbeat", "mode": "0600"}
        return hs.build_persistent_bridge_policy(
            {"sources": []}, edge_home="/home/operator/edge-install",
            runtime_output_root="/var/lib/edge-codex-heartbeat/runtime-output",
            codex_home="/var/lib/edge-codex-heartbeat/codex-home",
            service_identity="edge-codex-heartbeat", runtime_metadata=meta_dir,
            codex_home_metadata=meta_dir, auth_file_metadata=meta_file,
            operator_home=Path("/home/operator"), require_sources_exist=False,
        )

    def test_success_returns_only_sanitized_structure(self):
        receipt = gate.run_hermetic_fake()
        self.assertTrue(receipt["passed"])
        self.assertTrue(receipt["terminal"])
        self.assertTrue(receipt["process_group_terminal"])
        self.assertFalse(receipt["reasoning_persisted"])
        self.assertFalse(receipt["model_output_persisted"])
        self.assertFalse(receipt["llm_invoked"])
        encoded = json.dumps(receipt)
        self.assertNotIn("hidden", encoded)
        self.assertNotIn("EDGE_SYNTHETIC_JSONL_SECRET_CANARY", encoded)

    def test_every_adversarial_behavior_fails_closed(self):
        for behavior in (
            "tool", "unknown-event", "unknown-item", "malformed", "overflow",
            "stderr-overflow", "secret", "nonzero", "missing-terminal", "hang",
        ):
            with self.subTest(behavior=behavior), self.assertRaises(gate.JsonlGateError):
                gate.run_hermetic_fake(
                    behavior=behavior,
                    timeout_seconds=0.1 if behavior == "hang" else 1.0,
                )

    def test_order_duplicates_and_missing_message_fail(self):
        cases = [
            [b'{"type":"turn.started"}\n'],
            [b'{"type":"thread.started"}\n', b'{"type":"turn.started"}\n',
             b'{"type":"turn.completed"}\n'],
            [b'{"type":"thread.started"}\n', b'{"type":"thread.started"}\n'],
        ]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(gate.JsonlGateError):
                gate.inspect_jsonl(lines)

    def test_signature_cannot_select_real_executable_or_auth(self):
        with self.assertRaises(TypeError):
            gate.run_hermetic_fake(executable="codex")
        with self.assertRaises(TypeError):
            gate.run_hermetic_fake(auth_path="/home/operator/.codex/auth.json")
        with self.assertRaises(ValueError):
            gate.run_hermetic_fake(behavior="real-codex")

    def test_supervised_command_is_fixed_bounded_and_not_executed(self):
        command = gate.build_supervised_codex_command(
            self._policy(), codex_bin="/opt/openai/bin/codex",
            dispatch_id="persistent-fake-01",
        )
        self.assertEqual(command, [
            "/opt/openai/bin/codex", "exec", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--sandbox", "workspace-write", "--json", "--color",
            "never", "-C", "/home/operator/edge-install", "--add-dir",
            "/var/lib/edge-codex-heartbeat/runtime-output", "-",
        ])
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("auth.json", " ".join(command))
        with self.assertRaises(gate.JsonlGateError):
            gate.build_supervised_codex_command(
                self._policy(), codex_bin="codex", dispatch_id="x"
            )

    def test_sanitized_receipt_is_private_atomic_and_contains_no_content(self):
        receipt = gate.run_hermetic_fake()
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / "audit"
            audit.mkdir(mode=0o700)
            path = gate.write_terminal_receipt(
                receipt, audit_dir=audit, dispatch_id="fake-terminal-01"
            )
            body = path.read_text()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertIn('"dispatch_id":"fake-terminal-01"', body)
            self.assertNotIn("hidden", body)
            self.assertNotIn("EDGE_SYNTHETIC", body)
            self.assertEqual(list(audit.glob("*.tmp-*")), [])

    def test_receipt_writer_rejects_extra_raw_field(self):
        receipt = gate.run_hermetic_fake()
        receipt["raw_model_output"] = "must never land"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(gate.JsonlGateError):
            gate.write_terminal_receipt(
                receipt, audit_dir=Path(tmp), dispatch_id="fake-rejected-01"
            )

    def test_complete_fake_bridge_lands_only_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / "audit"
            audit.mkdir(mode=0o700)
            path = gate.run_hermetic_bridge(
                audit_dir=audit, dispatch_id="fake-bridge-complete-01"
            )
            self.assertEqual([p.name for p in audit.iterdir()], [path.name])
            body = path.read_text()
            self.assertNotIn("EDGE_SYNTHETIC_SUPERVISED_PROMPT", body)
            self.assertNotIn("hidden", body)

    def test_failed_fake_bridge_lands_no_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / "audit"
            audit.mkdir(mode=0o700)
            with self.assertRaises(gate.JsonlGateError):
                gate.run_hermetic_bridge(
                    audit_dir=audit, dispatch_id="fake-bridge-failed-01", behavior="tool"
                )
            self.assertEqual(list(audit.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
