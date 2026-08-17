#!/usr/bin/env python3
"""One-shot synthetic cross-identity denial probe; no persistent state."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile


def main():
    canary = "EDGE_SYNTHETIC_EXTERNAL_" + secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix="edge-external-identity-") as tmp:
        root = Path(tmp)
        os.chmod(root, 0o700)
        auth = root / "auth.json"
        auth.write_text(canary, encoding="ascii")
        os.chmod(auth, 0o600)
        result = subprocess.run(
            ["sudo", "-n", "-u", "nobody", "/usr/bin/test", "-r", str(auth)],
            capture_output=True, text=True, timeout=5,
        )
        if canary in result.stdout or canary in result.stderr:
            raise RuntimeError("synthetic canary escaped cross-identity probe")
        sudo_available = not (
            result.returncode != 0 and (
                "password" in result.stderr.lower()
                or "not allowed" in result.stderr.lower()
                or "sudoers" in result.stderr.lower()
            )
        )
        receipt = {
            "schema": "edge.external-identity-denial-probe/v1",
            "sudo_noninteractive_available": sudo_available,
            "external_identity": "nobody",
            "read_denied": sudo_available and result.returncode == 1,
            "unexpected_readable": sudo_available and result.returncode == 0,
            "content_returned": False,
            "real_auth_read": False,
            "persistent_state_created": False,
        }
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["read_denied"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
