"""Boot-race + co-habitação do provision_neo4j (caso edgesandbox 2026-07-25).

(1) Depois do `docker run`, o neo4j leva ~1min aplicando a senha inicial; cheques que chegam
antes disparam falhas de auth em série → AuthenticationRateLimit envenena os primeiros
minutos do install. provision_neo4j espera a prontidão (RETURN 1 autenticado via docker
exec) antes de devolver. (2) Container existente + secret ausente no home = instalação
co-habitando um neo4j de outro install — devolver o caminho de um arquivo que não existe
era mentira silenciosa; agora é fail-loud com instrução.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _provision  # noqa: E402


class _Seq:
    """run stand-in com roteiro por comando: (predicado, rc, stdout)."""
    def __init__(self):
        self.calls = []
        self.auth_attempts = 0
        self.ready_after = 0

    def __call__(self, cmd, *a, **kw):
        cmd = list(cmd)
        self.calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
        if cmd[:2] == ["docker", "info"]:
            return R()
        if cmd[:2] == ["docker", "ps"]:
            R.stdout = ""          # container não existe ainda
            return R()
        if "cypher-shell" in cmd:
            self.auth_attempts += 1
            R.returncode = 0 if self.auth_attempts > self.ready_after else 1
            return R()
        return R()


class WaitUntilReady(unittest.TestCase):
    def _with_docker(self, fn):
        import shutil as _sh
        orig = _sh.which
        _sh.which = lambda name: "/usr/bin/docker"
        try:
            return fn()
        finally:
            _sh.which = orig

    def test_returns_only_after_authenticated_ping_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            seq = _Seq()
            seq.ready_after = 3     # 3 pings falham antes do neo4j ficar pronto
            self._with_docker(lambda: _provision.provision_neo4j(
                tmp, Path(tmp) / "secrets", run=seq, _sleep=lambda s: None))
            self.assertGreaterEqual(seq.auth_attempts, 4)

    def test_never_ready_is_fail_loud_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            seq = _Seq()
            seq.ready_after = 10**9
            with self.assertRaisesRegex(RuntimeError, "não ficou pronto"):
                self._with_docker(lambda: _provision.provision_neo4j(
                    tmp, Path(tmp) / "secrets", run=seq, _sleep=lambda s: None))

    def test_existing_container_with_missing_secret_is_loud(self):
        import shutil as _sh
        orig = _sh.which
        _sh.which = lambda name: "/usr/bin/docker"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                class _Has:
                    def __call__(self, cmd, *a, **kw):
                        class R:
                            returncode = 0
                            stdout = "abc123\n" if cmd[:2] == ["docker", "ps"] else ""
                        return R()
                with self.assertRaisesRegex(RuntimeError, "co-habita"):
                    _provision.provision_neo4j(tmp, Path(tmp) / "secrets", run=_Has())
        finally:
            _sh.which = orig

    def test_existing_container_with_present_secret_stays_idempotent(self):
        import shutil as _sh
        orig = _sh.which
        _sh.which = lambda name: "/usr/bin/docker"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = Path(tmp) / "secrets"
                env.mkdir()
                (env / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=x\n")

                class _Has:
                    def __call__(self, cmd, *a, **kw):
                        class R:
                            returncode = 0
                            stdout = "abc123\n" if cmd[:2] == ["docker", "ps"] else ""
                        return R()
                out = _provision.provision_neo4j(tmp, env, run=_Has())
                self.assertEqual(out, env / "neo4j.env")
        finally:
            _sh.which = orig


if __name__ == "__main__":
    unittest.main()
