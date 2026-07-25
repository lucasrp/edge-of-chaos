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


if __name__ == "__main__":
    unittest.main()
