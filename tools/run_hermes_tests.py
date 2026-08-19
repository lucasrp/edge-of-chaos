#!/usr/bin/env python3
"""Run the focused Hermes integration gate without pytest or package discovery."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_hermes_sessions.py",
    "tests/test_hermes_pipeline.py",
    "tests/test_hermes_provision.py",
    "tests/test_mentor_preflight.py",
)
_SESSION_ENV = (
    "CLAUDE_CODE_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "GROK_SESSION_ID",
    "HERMES_SESSION_ID",
    "EDGE_EXCLUDE_SESSION_IDS",
)


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    for key in _SESSION_ENV:
        env.pop(key, None)
    failures = []
    for relative in TESTS:
        print(f"==> {relative}", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / relative)],
            cwd=ROOT,
            env=env,
            check=False,
        )
        if result.returncode:
            failures.append((relative, result.returncode))
    if failures:
        for relative, code in failures:
            print(f"FAIL {relative} (exit {code})", file=sys.stderr)
        return 1
    print(f"Hermes gate passed: {len(TESTS)} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
