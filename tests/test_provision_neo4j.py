"""Per-host Neo4j via Docker (#18, per ADR-0011) — mandatory, own-per-host, fail-loud.

Every host runs its OWN Neo4j (no central/shared graph). Provisioned via Docker: pinned neo4j:5.x
(required for the vector index), --restart unless-stopped, data volume under <home>/state/neo4j/,
and a GENERATED per-host password written to the secrets dir (no baked-in literal — CONTRACT C4).
Fail loud if Docker is absent. All tested pure — subprocess is mocked, nothing runs against this host.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _provision  # noqa: E402


class _Recorder:
    """subprocess.run stand-in: records calls; returns a result with returncode + stdout."""
    def __init__(self, rcs=None, stdouts=None):
        self.calls = []
        self.rcs = list(rcs or [])
        self.stdouts = list(stdouts or [])

    def __call__(self, cmd, *a, **kw):
        self.calls.append(list(cmd))
        rc = self.rcs.pop(0) if self.rcs else 0
        out = self.stdouts.pop(0) if self.stdouts else ""

        class R:
            returncode = rc
            stdout = out
        return R()


class PasswordIsGeneratedNotLiteral(unittest.TestCase):
    def test_generated_password_is_random_and_nonempty(self):
        a, b = _provision.generate_neo4j_password(), _provision.generate_neo4j_password()
        self.assertTrue(a and b)
        self.assertNotEqual(a, b, "each host gets a distinct password")
        self.assertNotIn("edgepassword123", a)
        self.assertGreaterEqual(len(a), 16)

    def test_secret_written_mode_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _provision.write_neo4j_secret(tmp, "s3cr3t-xyz")
            self.assertTrue(path.exists())
            self.assertIn("EDGE_NEO4J_PASSWORD=s3cr3t-xyz", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class Neo4jRunCommand(unittest.TestCase):
    def test_command_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd = _provision.neo4j_run_command(home, "PW")
            j = " ".join(cmd)
            self.assertIn("docker", cmd)
            self.assertIn("run", cmd)
            # pinned 5.x image (vector index)
            self.assertTrue(any(part.startswith("neo4j:5") for part in cmd),
                            f"must pin neo4j:5.x, got {cmd}")
            self.assertIn("--restart", cmd)
            self.assertIn("unless-stopped", cmd)
            # data on an ANONYMOUS docker volume, NEVER a bind mount under <home> — root-owned files
            # there block `rm -rf <home>` and break a clean reinstall (bug #5, found by a from-zero run)
            self.assertIn("/data", cmd)
            self.assertNotIn(str(home / "state" / "neo4j"), j)
            # the generated password, never a literal
            self.assertIn("NEO4J_AUTH=neo4j/PW", j)
            self.assertNotIn("edgepassword123", j)
            # bolt port published
            self.assertIn("7687:7687", j)


class ProvisionNeo4j(unittest.TestCase):
    def test_fails_loud_when_docker_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            # docker_present returns False → `docker info` rc 1 (but PATH check guards first);
            # force absence by a runner that errors, and patch shutil.which to None.
            import shutil as _sh
            orig = _sh.which
            _sh.which = lambda name: None
            try:
                rec = _Recorder()
                with self.assertRaises(RuntimeError) as ctx:
                    _provision.provision_neo4j(tmp, Path(tmp) / "secrets", run=rec)
                self.assertIn("docker", str(ctx.exception).lower())
            finally:
                _sh.which = orig

    def test_provisions_when_docker_present_and_no_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil as _sh
            orig = _sh.which
            _sh.which = lambda name: "/usr/bin/docker"
            try:
                # docker info rc 0; docker ps -aq → "" (no container yet); docker run rc 0
                rec = _Recorder(rcs=[0, 0, 0], stdouts=["", "", ""])
                secret = _provision.provision_neo4j(tmp, Path(tmp) / "secrets", run=rec)
                # the secret was written with a generated password
                self.assertTrue(secret.exists())
                self.assertIn("EDGE_NEO4J_PASSWORD=", secret.read_text())
                self.assertNotIn("edgepassword123", secret.read_text())
                # a `docker run ... neo4j:5.x` was issued
                run_calls = [c for c in rec.calls if "run" in c and "docker" in c]
                self.assertTrue(run_calls)
                self.assertTrue(any(p.startswith("neo4j:5") for p in run_calls[0]))
            finally:
                _sh.which = orig

    def test_idempotent_when_container_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil as _sh
            orig = _sh.which
            _sh.which = lambda name: "/usr/bin/docker"
            try:
                # docker info rc 0; docker ps -aq → "abc123" (container already there)
                # o secret DESTE install existe — sem ele, container-existente é o caso
                # co-habitação e falha alto (test_provision_neo4j_readiness.py)
                env = Path(tmp) / "secrets"
                env.mkdir()
                (env / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=x\n")
                rec = _Recorder(rcs=[0, 0], stdouts=["", "abc123\n"])
                _provision.provision_neo4j(tmp, env, run=rec)
                # NO docker run when the container already exists (idempotent)
                run_calls = [c for c in rec.calls if "run" in c and "docker" in c]
                self.assertEqual(run_calls, [], "must not re-run an existing Neo4j container")
            finally:
                _sh.which = orig

    def test_container_exists_requires_capture(self):
        """Regression: real subprocess.run fills .stdout only with capture_output=True. The probe MUST
        request it, or it never sees the container id and reports False on a host that HAS the
        container — then re-`docker run` → 'name already in use' crash (the bug a clean reinstall hit)."""
        seen = {}

        def realish_run(cmd, *a, **kw):
            seen["capture"] = kw.get("capture_output")
            out = "abc123\n" if kw.get("capture_output") else None   # mimic real subprocess.run
            return type("R", (), {"returncode": 0, "stdout": out})()

        self.assertTrue(_provision.container_exists("edge-neo4j", run=realish_run))
        self.assertTrue(seen["capture"], "container_exists must call docker ps with capture_output=True")


class SelectInstallMode(unittest.TestCase):
    """The seam is the WHOLE edge's install mode — 'docker' or 'local' — chosen ONCE and read by
    every containerizable step (today: Neo4j), not a per-component provider. Onboarding tests what's
    possible and executes: docker reachable → 'docker'; otherwise the edge installs 'local'
    (user-space, no docker permission needed) end to end, instead of the old docker-mandatory death."""

    def test_local_when_docker_absent(self):
        self.assertEqual(_provision.select_install_mode({"docker_present": False}), "local")


class ProvisionNeo4jLocal(unittest.TestCase):
    """The 'local' mode: user-space Neo4j (tarball + bundled JRE) under <home>/runtime — no docker,
    no root. Runs AS THE USER, so data under <home> is user-owned: `rm -rf <home>` stays clean (the
    inverse of bug #5, by construction). Heavy I/O (download, start, bolt readiness) is injected —
    this proves the orchestration; a real boot needs a no-docker+java host (calibration)."""

    def test_provisions_user_space_writes_secret_sets_password_and_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = home / "secrets"
            downloaded = []
            rec = _Recorder(rcs=[0, 0], stdouts=["", ""])
            secret = _provision.provision_neo4j_local(
                home, env, run=rec,
                _download=lambda url, dest: downloaded.append((url, Path(dest))),
                _ready=lambda pw: True, _sleep=lambda s: None, _password="pw123")
            # secret written with the generated password (never a literal)
            self.assertTrue(secret.exists())
            self.assertIn("EDGE_NEO4J_PASSWORD=pw123", secret.read_text())
            # JRE + neo4j fetched under <home>/runtime (user-space, under home — not root, not docker)
            self.assertTrue(downloaded, "must fetch the bundled JRE + neo4j tarball")
            self.assertTrue(all(str(home / "runtime") in str(d) for _, d in downloaded),
                            "runtime lives user-space under <home>")
            cmds = [" ".join(map(str, c)) for c in rec.calls]
            self.assertTrue(any("set-initial-password" in c for c in cmds), "must set initial password")
            self.assertTrue(any(c.rstrip().endswith(" start") for c in cmds), "must start neo4j")

    def test_existing_store_reuses_secret_without_resetting_initial_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = home / "secrets"
            env.mkdir()
            secret = env / "neo4j.env"
            secret.write_text("EDGE_NEO4J_PASSWORD=existing-pw\n")
            database = home / "runtime" / "neo4j" / "data" / "databases" / "neo4j"
            database.mkdir(parents=True)
            (database / "store-marker").write_text("existing")
            ready_passwords = []
            rec = _Recorder()

            out = _provision.provision_neo4j_local(
                home, env, run=rec, _download=lambda url, dest: None,
                _ready=lambda pw: ready_passwords.append(pw) or True, _sleep=lambda s: None)

            self.assertEqual(out, secret)
            self.assertEqual(secret.read_text(), "EDGE_NEO4J_PASSWORD=existing-pw\n")
            self.assertEqual(ready_passwords, ["existing-pw"])
            cmds = [" ".join(map(str, c)) for c in rec.calls]
            self.assertFalse(any("set-initial-password" in c for c in cmds))
            self.assertTrue(any(c.rstrip().endswith(" start") for c in cmds))

    def test_existing_store_without_secret_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            database = home / "runtime" / "neo4j" / "data" / "databases" / "neo4j"
            database.mkdir(parents=True)
            (database / "store-marker").write_text("existing")

            with self.assertRaisesRegex(RuntimeError, "já possui dados"):
                _provision.provision_neo4j_local(
                    home, home / "secrets", run=_Recorder(),
                    _download=lambda url, dest: None, _ready=lambda pw: True)


class EnsureNeo4jReadsMode(unittest.TestCase):
    """Neo4j does not decide the mode — it READS it. Docker absent → the install is 'local' → Neo4j
    is provisioned user-space, no raise. This seam proves Neo4j follows the edge-wide mode."""

    def test_docker_absent_provisions_local_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "secrets"
            called = {}

            def fake_local(home, env_dir, **kw):
                called["local"] = (Path(home), Path(env_dir))
                return Path(env_dir) / "neo4j.env"

            orig_docker = _provision.docker_present
            orig_local = getattr(_provision, "provision_neo4j_local", None)
            _provision.docker_present = lambda **k: False
            _provision.provision_neo4j_local = fake_local
            try:
                secret = _provision.ensure_neo4j(tmp, env)          # must NOT raise
                self.assertIn("local", called, "local mode must provision Neo4j user-space")
                self.assertEqual(secret, env / "neo4j.env")
            finally:
                _provision.docker_present = orig_docker
                if orig_local is not None:
                    _provision.provision_neo4j_local = orig_local


if __name__ == "__main__":
    unittest.main(verbosity=2)
