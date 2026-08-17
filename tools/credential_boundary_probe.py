"""Hermetic same-identity negative proof for the persistent-auth bridge."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

try:
    from tools import codex_jsonl_gate
except ImportError:  # direct execution with tools/ on sys.path
    import codex_jsonl_gate


_ROOT = Path(__file__).resolve().parent.parent
_READER = _ROOT / "tests" / "fixtures" / "fake_auth_reader.py"
_PREFIX = "EDGE_SYNTHETIC_BOUNDARY_"


class BoundaryProbeError(RuntimeError):
    """The synthetic boundary did not exhibit its required behavior."""


def run_same_identity_negative_proof() -> dict:
    """Prove the credential owner can read fake auth and the JSONL gate still rejects the tool."""
    canary = _PREFIX + secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix="edge-boundary-proof-") as tmp:
        root = Path(tmp)
        os.chmod(root, 0o700)
        auth = root / "auth.json"
        auth.write_text(canary, encoding="ascii")
        os.chmod(auth, 0o600)
        result = subprocess.run(
            [sys.executable, str(_READER), str(auth), canary],
            capture_output=True, text=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
            timeout=2,
        )
        if result.returncode != 0 or canary in result.stdout or canary in result.stderr:
            raise BoundaryProbeError("same-identity reader returned unsafe evidence")
        try:
            evidence = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BoundaryProbeError("same-identity reader returned malformed evidence") from exc
        if evidence != {
            "readable": True,
            "matched_expected_synthetic_value": True,
            "content_returned": False,
        }:
            raise BoundaryProbeError("same-identity readability was not proven")

        tool_stream = [
            b'{"type":"thread.started"}\n',
            b'{"type":"turn.started"}\n',
            b'{"type":"item.completed","item":{"type":"command_execution"}}\n',
            b'{"type":"turn.completed"}\n',
        ]
        gate_rejected = False
        try:
            codex_jsonl_gate.inspect_jsonl(tool_stream, secret_needles=[canary])
        except codex_jsonl_gate.JsonlGateError:
            gate_rejected = True
        if not gate_rejected:
            raise BoundaryProbeError("terminal gate accepted a synthetic tool event")

        receipt = {
            "schema": "edge.credential-boundary-negative-proof/v1",
            "same_identity_readable": True,
            "synthetic_value_match": True,
            "content_returned": False,
            "terminal_gate_rejected_tool": True,
            "preventive_isolation_from_same_identity": False,
            "real_auth_read": False,
            "llm_invoked": False,
            "network_used": False,
        }
        if canary in json.dumps(receipt, sort_keys=True):
            raise BoundaryProbeError("synthetic canary reached returned evidence")
        return receipt
