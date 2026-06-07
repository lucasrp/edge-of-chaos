"""venv + pinned deps; edge-python fail-loud (#20, per ADR-0011).

The graph tier is mandatory on every host: extraction (graphiti_core + neo4j + openai) runs
locally, so every host needs the runtime venv. Two guarantees, tested pure (no real venv build,
no network):

  1. requirements.txt pins the runtime deps to exact versions.
  2. tools/edge-python FAILS LOUD when the venv is missing — prints a clear error pointing at
     edge-apply and exits non-zero. No silent fallback to system python3 (that masks a broken
     install under ADR-0011).
  3. _provision.build_venv constructs the venv-create + pip-install commands from requirements.txt
     and is idempotent (skips the create when a valid venv already exists). Subprocess is mocked —
     nothing is built against this host.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDGE_PYTHON = REPO / "tools" / "edge-python"
sys.path.insert(0, str(REPO / "tools"))
import _provision  # noqa: E402


class RequirementsPinned(unittest.TestCase):
    def test_requirements_file_pins_runtime_deps(self):
        req = (REPO / "requirements.txt")
        self.assertTrue(req.exists(), "requirements.txt must exist (#20)")
        text = req.read_text().lower()
        for dep in ("graphiti", "neo4j", "openai", "flask", "yaml"):
            self.assertIn(dep, text, f"requirements.txt must pin {dep}")
        # every non-comment, non-blank line is an exact pin (== version)
        for line in req.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            self.assertIn("==", line, f"dep must be pinned to an exact version: {line!r}")


class EdgePythonFailsLoudWithoutVenv(unittest.TestCase):
    """Under ADR-0011 a missing venv is a BROKEN INSTALL, not a soft degrade — edge-python must
    exit non-zero with a clear error, never silently exec system python3."""

    def _run(self, env_home):
        env = dict(os.environ)
        env["EDGE_HOME"] = env_home
        # Strip any ambient venv so the test is deterministic across hosts.
        return subprocess.run(
            [str(EDGE_PYTHON), "-c", "print('SHOULD-NOT-RUN')"],
            capture_output=True, text=True, env=env,
        )

    def test_no_venv_exits_nonzero_with_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp)                      # EDGE_HOME has no .venv
            self.assertNotEqual(res.returncode, 0, "missing venv must fail loud")
            self.assertNotIn("SHOULD-NOT-RUN", res.stdout,
                             "must NOT fall back to system python3 and run the code")
            msg = (res.stderr + res.stdout).lower()
            self.assertIn("venv", msg)
            self.assertIn("edge-apply", msg, "the error must point at edge-apply")

    def test_existing_venv_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Forge a fake venv python that just echoes a marker, to prove edge-python execs it.
            venv_bin = Path(tmp) / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            py = venv_bin / "python"
            py.write_text("#!/usr/bin/env bash\necho VENV-PYTHON-RAN\n")
            py.chmod(0o755)
            env = dict(os.environ)
            env["EDGE_HOME"] = tmp
            res = subprocess.run([str(EDGE_PYTHON), "-c", "x"],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("VENV-PYTHON-RAN", res.stdout)


class _Recorder:
    """A subprocess.run stand-in: records calls, returns rc 0 (or a queued rc)."""
    def __init__(self, rcs=None):
        self.calls = []
        self.rcs = list(rcs or [])

    def __call__(self, cmd, *a, **kw):
        self.calls.append(list(cmd))
        rc = self.rcs.pop(0) if self.rcs else 0

        class R:
            returncode = rc
        return R()


class BuildVenvCommands(unittest.TestCase):
    def test_creates_venv_then_pip_installs_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rec = _Recorder()
            _provision.build_venv(home, REPO / "requirements.txt", run=rec)
            # 1st call: create the venv with the venv module
            self.assertIn("venv", rec.calls[0])
            self.assertIn(str(home / ".venv"), rec.calls[0])
            # a later call pip-installs from requirements.txt into the venv pip
            pip_calls = [c for c in rec.calls if any("pip" in part for part in c)]
            self.assertTrue(pip_calls, "must invoke the venv pip")
            install = [c for c in pip_calls if "install" in c]
            self.assertTrue(install, "must pip install")
            self.assertIn("-r", install[-1])
            self.assertIn(str(REPO / "requirements.txt"), install[-1])
            # uses the venv's OWN python/pip, not the system one
            self.assertTrue(any(str(home / ".venv" / "bin") in part
                                for c in pip_calls for part in c))

    def test_idempotent_skips_create_when_valid_venv_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # pretend a valid venv already exists
            (home / ".venv" / "bin").mkdir(parents=True)
            (home / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
            (home / ".venv" / "bin" / "python").chmod(0o755)
            rec = _Recorder()
            _provision.build_venv(home, REPO / "requirements.txt", run=rec)
            # no `python -m venv` create call when the venv is already there
            create = [c for c in rec.calls if "venv" in c and "-m" in c]
            self.assertEqual(create, [], "must not recreate an existing venv (idempotent)")

    def test_fails_loud_when_pip_install_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rec = _Recorder(rcs=[0, 1])               # venv create ok, pip install fails
            with self.assertRaises(RuntimeError):
                _provision.build_venv(home, REPO / "requirements.txt", run=rec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
