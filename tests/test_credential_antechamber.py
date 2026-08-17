"""Hermetic tests for staged credential closure before prompt release."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import credential_antechamber as chamber  # noqa: E402


class HermeticAntechamber(unittest.TestCase):
    def test_normal_lifecycle_closes_path_before_prompt_and_child(self):
        result = chamber.run_hermetic_antechamber()
        self.assertTrue(result["passed"])
        self.assertTrue(result["prompt_released_after_closure"])
        self.assertFalse(result["cli_rereadable_after_gate"])
        self.assertFalse(result["tool_rereadable_after_gate"])
        self.assertTrue(result["separate_tool_process"])
        self.assertFalse(result["credential_value_returned"])
        self.assertFalse(result["llm_invoked"])
        self.assertFalse(result["real_auth_read"])
        self.assertEqual(result["runtime_mode"], "0o700")
        self.assertEqual(result["credential_mode"], "0o600")
        self.assertLess(
            result["transitions"].index("credential_path_closed"),
            result["transitions"].index("prompt_released"),
        )
        self.assertNotIn("EDGE_SYNTHETIC_AUTH_", json.dumps(result))

    def test_adversarial_readiness_never_returns_success(self):
        cases = {
            "ready-before-read": "readiness is unproven",
            "malformed-ready": "malformed frame",
            "crash-before-ready": "closed before terminal frame",
            "delay-ready": "timed out",
        }
        for behavior, message in cases.items():
            with self.subTest(behavior=behavior), self.assertRaisesRegex(
                    chamber.AntechamberError, message):
                chamber.run_hermetic_antechamber(
                    behavior=behavior,
                    timeout_seconds=0.1 if behavior == "delay-ready" else 0.5,
                )

    def test_signature_rejects_external_authority_inputs(self):
        with self.assertRaises(TypeError):
            chamber.run_hermetic_antechamber(auth_path="/home/operator/.codex/auth.json")
        with self.assertRaises(TypeError):
            chamber.run_hermetic_antechamber(token="real")
        with self.assertRaises(ValueError):
            chamber.run_hermetic_antechamber(behavior="codex")

    def test_parent_exception_terminates_and_cleans_temporary_runtime(self):
        real_frame = chamber._frame

        def fail_after_ready(line, expected):
            value = real_frame(line, expected)
            if expected == "ready":
                raise chamber.AntechamberError("injected parent failure")
            return value

        before = set(Path(tempfile.gettempdir()).glob("edge-auth-antechamber-*"))
        with mock.patch.object(chamber, "_frame", side_effect=fail_after_ready), \
                self.assertRaisesRegex(chamber.AntechamberError, "injected parent failure"):
            chamber.run_hermetic_antechamber()
        after = set(Path(tempfile.gettempdir()).glob("edge-auth-antechamber-*"))
        self.assertEqual(after, before)

    def test_sources_have_no_real_auth_network_or_llm_surface(self):
        sources = "\n".join((REPO / path).read_text() for path in (
            "tools/credential_antechamber.py",
            "tests/fixtures/fake_credential_cli.py",
            "tests/fixtures/fake_credential_tool.py",
        ))
        for forbidden in (
                "/home/operator/.codex", "/mnt/c/", "auth.json", "OPENAI_API_KEY",
                "import socket", "urllib", "requests", "httpx", "codex exec",
                "edge-heartbeat", "systemctl"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, sources)


if __name__ == "__main__":
    unittest.main()
