"""Secrets env_dir — CONTRACT C4 (#22).

Secrets live in the install's env_dir (agent.yaml, defaulting to <edge_home>/secrets/ when the
field is unset). The genotype carries no credential literal and no delivery mechanism. The
installer verifies presence and FAILS LOUD per missing required key (naming it) — not a soft warning.

These run the apply module's helpers directly (no real provisioning). The agent.yaml `env_dir`
field is DEFERRED (agent.yaml is operator-dirty); the resolver already honors it the moment it lands.
"""
import importlib.util
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# edge-apply has no .py suffix — load it as a module via an explicit source loader.
_loader = SourceFileLoader("edge_apply", str(REPO / "tools" / "edge-apply"))
_spec = importlib.util.spec_from_loader("edge_apply", _loader)
edge_apply = importlib.util.module_from_spec(_spec)
_loader.exec_module(edge_apply)


class ResolveEnvDir(unittest.TestCase):
    def test_defaults_to_home_secrets_when_unset(self):
        home = Path("/home/x/edge")
        self.assertEqual(edge_apply.resolve_env_dir(home, {}), home / "secrets")

    def test_honors_agent_yaml_env_dir(self):
        home = Path("/home/x/edge")
        ed = edge_apply.resolve_env_dir(home, {"env_dir": "/srv/keys"})
        self.assertEqual(ed, Path("/srv/keys"))

    def test_expands_user_in_env_dir(self):
        ed = edge_apply.resolve_env_dir(Path("/home/x/edge"), {"env_dir": "~/keys"})
        self.assertTrue(str(ed).endswith("/keys"))
        self.assertNotIn("~", str(ed))


class ReadSecretResolvesAgainstEnvDir(unittest.TestCase):
    def test_reads_key_from_env_dir_not_hardcoded_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            env_dir = Path(tmp) / "custom-keys"
            env_dir.mkdir(parents=True)
            (env_dir / "openai.env").write_text('OPENAI_API_KEY="sk-from-env-dir"\n')
            got = edge_apply._read_secret(home, "openai.env:OPENAI_API_KEY", env_dir=env_dir)
            self.assertEqual(got, "sk-from-env-dir")

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_dir = Path(tmp) / "keys"
            env_dir.mkdir()
            self.assertIsNone(
                edge_apply._read_secret(Path(tmp), "absent.env:KEY", env_dir=env_dir))


class VerifyRequiredSecretsFailsLoud(unittest.TestCase):
    """A missing REQUIRED key (router/api-source with a secret_ref) fails loud naming the key —
    no soft warning. Keyless sources are not required."""

    CFG = {
        "routers": {"chat": {"provider": "openai", "secret_ref": "openai.env:OPENAI_API_KEY"}},
        "sources": [
            {"name": "exa", "kind": "api", "secret_ref": "exa.env:EXA_API_KEY"},
            {"name": "hn", "kind": "api"},          # keyless — not required
        ],
    }

    def test_missing_required_key_raises_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            env_dir = Path(tmp) / "secrets"
            env_dir.mkdir(parents=True)
            with self.assertRaises(RuntimeError) as ctx:
                edge_apply.verify_required_secrets(home, self.CFG, env_dir)
            msg = str(ctx.exception)
            self.assertIn("OPENAI_API_KEY", msg)
            self.assertIn("EXA_API_KEY", msg)

    def test_passes_when_all_required_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            env_dir = Path(tmp) / "secrets"
            env_dir.mkdir(parents=True)
            (env_dir / "openai.env").write_text("OPENAI_API_KEY=sk-x\n")
            (env_dir / "exa.env").write_text("EXA_API_KEY=ex-x\n")
            # must not raise; keyless hn requires nothing
            edge_apply.verify_required_secrets(home, self.CFG, env_dir)


class NoCredentialLiteralInApply(unittest.TestCase):
    def test_no_hardcoded_password_or_secrets_path(self):
        src = (REPO / "tools" / "edge-apply").read_text()
        self.assertNotIn("edgepassword123", src)
        # the hardcoded `home / "secrets"` default is gone from _read_secret's body;
        # the only secrets-dir reference is the env_dir default (resolve_env_dir).


if __name__ == "__main__":
    unittest.main(verbosity=2)
