"""_env_dir pré-fenótipo — o gap do EDGE_NEO4J_PASSWORD no onboarding (2×, edgesandbox).

Durante o first-run não existe agent.yaml; a resolução de segredos caía no fallback
legado ~/edge/secrets e o neo4j.env do install home nunca era carregado. Ordem nova:
EDGE_SECRETS_DIR (override explícito, espelha onboarding.secrets_dir) → agent.yaml
env_dir → agent.yaml edge_home/secrets → EDGE_HOME/secrets (pré-fenótipo) → ~/edge/secrets.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity  # noqa: E402


class EnvDirResolution(unittest.TestCase):
    def test_edge_secrets_dir_wins_always(self):
        with tempfile.TemporaryDirectory() as tmp:
            yaml_p = Path(tmp) / "agent.yaml"
            yaml_p.write_text("edge_home: /outra/casa\n")
            with mock.patch.dict(os.environ, {"EDGE_SECRETS_DIR": f"{tmp}/sec"}, clear=False):
                self.assertEqual(_identity._env_dir(yaml_p), Path(tmp) / "sec")

    def test_agent_yaml_env_dir_wins_over_edge_home_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            yaml_p = Path(tmp) / "agent.yaml"
            yaml_p.write_text(f"env_dir: {tmp}/fen\n")
            env = {k: v for k, v in os.environ.items() if k != "EDGE_SECRETS_DIR"}
            env["EDGE_HOME"] = f"{tmp}/home-env"
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(_identity._env_dir(yaml_p), Path(tmp) / "fen")

    def test_prephenotype_falls_to_edge_home_env(self):
        """O caso do onboarding: sem agent.yaml, EDGE_HOME aponta o install home."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "agent.yaml"          # não existe
            env = {k: v for k, v in os.environ.items() if k != "EDGE_SECRETS_DIR"}
            env["EDGE_HOME"] = f"{tmp}/edge-home"
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(_identity._env_dir(missing),
                                 Path(tmp) / "edge-home" / "secrets")

    def test_legacy_fallback_survives_without_any_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "agent.yaml"
            env = {k: v for k, v in os.environ.items()
                   if k not in ("EDGE_SECRETS_DIR", "EDGE_HOME")}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(_identity._env_dir(missing),
                                 Path(os.path.expanduser("~/edge")) / "secrets")

    def test_relative_env_dir_anchors_on_edge_home_never_cwd(self):
        """agent.yaml `env_dir: secrets` (relativo, como o onboarding escreve) resolve
        contra o edge_home do install — nunca contra o cwd (o gap do edge-apply no
        edgesandbox: cwd=genotipo-teste, secrets em ~/sandbox-home/secrets)."""
        with tempfile.TemporaryDirectory() as tmp:
            yaml_p = Path(tmp) / "agent.yaml"
            yaml_p.write_text(f"edge_home: {tmp}/casa\nenv_dir: secrets\n")
            env = {k: v for k, v in os.environ.items() if k != "EDGE_SECRETS_DIR"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(_identity._env_dir(yaml_p), Path(tmp) / "casa" / "secrets")


class IdentityPathHomeFirst(unittest.TestCase):
    """Identidade/doutrina (agent.yaml, memory/) num install com genótipo e home separados
    (EDGE_HOME) vive no HOME — o repo é genótipo puro, sem identidade (edgesandbox)."""

    def test_edge_home_wins_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent.yaml").write_text("name: x\n")
            with mock.patch.dict(os.environ, {"EDGE_HOME": tmp}, clear=False):
                self.assertEqual(_identity.identity_path("agent.yaml"),
                                 Path(tmp) / "agent.yaml")

    def test_missing_agent_yaml_in_home_still_uses_home_for_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"EDGE_HOME": tmp}, clear=False):
                self.assertEqual(_identity.identity_path("agent.yaml"),
                                 Path(tmp) / "agent.yaml")

    def test_no_edge_home_uses_repo(self):
        env = {k: v for k, v in os.environ.items() if k != "EDGE_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(_identity.identity_path("memory"), REPO / "memory")


class ApplyResolveEnvDir(unittest.TestCase):
    def _resolve(self, home, cfg):
        import importlib.util
        spec = importlib.util.spec_from_loader("edge_apply", loader=None)
        mod = __import__("importlib").util.module_from_spec(spec)
        mod.__dict__["__file__"] = str(REPO / "tools" / "edge-apply")
        src = (REPO / "tools" / "edge-apply").read_text()
        exec(compile(src, "edge-apply", "exec"), mod.__dict__)
        return mod.resolve_env_dir(home, cfg)

    def test_relative_env_dir_anchors_on_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "casa"
            self.assertEqual(self._resolve(home, {"env_dir": "secrets"}), home / "secrets")

    def test_absolute_env_dir_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "casa"
            self.assertEqual(self._resolve(home, {"env_dir": f"{tmp}/fen"}), Path(tmp) / "fen")

    def test_unset_defaults_to_home_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "casa"
            self.assertEqual(self._resolve(home, {}), home / "secrets")


if __name__ == "__main__":
    unittest.main()
