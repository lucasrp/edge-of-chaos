"""TDD: onboarding first-run knobs (no agent.yaml). Slice 1+."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import onboarding  # noqa: E402


class SecretsInventory(unittest.TestCase):
    def test_secrets_dir_default_under_home(self):
        home = Path("/tmp/edge-home-x")
        self.assertEqual(onboarding.secrets_dir(home), home / "secrets")

    def test_inventory_lists_key_names_not_values(self):
        with tempfile.TemporaryDirectory() as td:
            sdir = Path(td) / "secrets"
            sdir.mkdir()
            (sdir / "openai.env").write_text("OPENAI_API_KEY=sk-secret-value\n")
            (sdir / "empty.env").write_text("\n# comment\n")
            inv = onboarding.inventory_secrets(sdir)
            self.assertIn("openai.env", inv["files"])
            self.assertIn("OPENAI_API_KEY", inv["vars"])
            blob = json.dumps(inv)
            self.assertNotIn("sk-secret-value", blob)

    def test_inventory_missing_dir_is_empty_not_raise(self):
        inv = onboarding.inventory_secrets(Path("/no/such/secrets-dir-xyz"))
        self.assertEqual(inv["files"], [])
        self.assertEqual(inv["vars"], [])


class RequireKnobs(unittest.TestCase):
    def test_require_name_from_arg(self):
        self.assertEqual(onboarding.require_name("ed"), "ed")

    def test_require_name_from_env(self):
        old = os.environ.get("EDGE_AGENT_NAME")
        try:
            os.environ["EDGE_AGENT_NAME"] = "roberto"
            self.assertEqual(onboarding.require_name(None), "roberto")
        finally:
            if old is None:
                os.environ.pop("EDGE_AGENT_NAME", None)
            else:
                os.environ["EDGE_AGENT_NAME"] = old

    def test_require_name_missing_fails_loud(self):
        old = os.environ.pop("EDGE_AGENT_NAME", None)
        try:
            with self.assertRaises(ValueError) as cm:
                onboarding.require_name(None)
            self.assertIn("name", str(cm.exception).lower())
        finally:
            if old is not None:
                os.environ["EDGE_AGENT_NAME"] = old

    def test_require_backfill_days_zero_ok(self):
        self.assertEqual(onboarding.require_backfill_days(0), 0)

    def test_require_backfill_days_from_env(self):
        old = os.environ.get("EDGE_ASSEMBLE_BACKFILL_DAYS")
        try:
            os.environ["EDGE_ASSEMBLE_BACKFILL_DAYS"] = "14"
            self.assertEqual(onboarding.require_backfill_days(None), 14)
        finally:
            if old is None:
                os.environ.pop("EDGE_ASSEMBLE_BACKFILL_DAYS", None)
            else:
                os.environ["EDGE_ASSEMBLE_BACKFILL_DAYS"] = old

    def test_require_backfill_days_missing_fails(self):
        old = os.environ.pop("EDGE_ASSEMBLE_BACKFILL_DAYS", None)
        try:
            with self.assertRaises(ValueError):
                onboarding.require_backfill_days(None)
        finally:
            if old is not None:
                os.environ["EDGE_ASSEMBLE_BACKFILL_DAYS"] = old

    def test_require_backfill_days_negative_fails(self):
        with self.assertRaises(ValueError):
            onboarding.require_backfill_days(-1)


class AdversarialCast(unittest.TestCase):
    def test_empty_cast_falls_back_to_self(self):
        cast = onboarding.resolve_adversarial_cast([], primary="claude")
        self.assertEqual(cast["mode"], "self")
        self.assertEqual(cast["members"], ["self"])
        self.assertEqual(cast["primary"], "claude")

    def test_declared_members_kept(self):
        cast = onboarding.resolve_adversarial_cast(["codex", "grok"], primary="claude")
        self.assertEqual(cast["mode"], "declared")
        self.assertEqual(cast["members"], ["codex", "grok"])


class EmbeddingOptional(unittest.TestCase):
    def test_absent_inventory_returns_none(self):
        inv = {"files": [], "vars": [], "by_file": {}}
        self.assertIsNone(onboarding.embedding_from_inventory(inv))

    def test_openai_key_present(self):
        inv = {
            "files": ["openai.env"],
            "vars": ["OPENAI_API_KEY"],
            "by_file": {"openai.env": ["OPENAI_API_KEY"]},
        }
        ref = onboarding.embedding_from_inventory(inv)
        self.assertIsNotNone(ref)
        self.assertEqual(ref["secret_ref"], "openai.env:OPENAI_API_KEY")
        self.assertEqual(ref["status"], "on")


class BootstrapPersist(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "state").mkdir()
            payload = {
                "name": "ed",
                "backfill_days": 14,
                "adversarials": {"mode": "self", "members": ["self"], "primary": "claude"},
                "embedding": None,
            }
            path = onboarding.persist_bootstrap(home, **payload)
            self.assertTrue(path.exists())
            loaded = onboarding.load_bootstrap(home)
            self.assertEqual(loaded["name"], "ed")
            self.assertEqual(loaded["backfill_days"], 14)
            self.assertEqual(loaded["adversarials"]["mode"], "self")
            self.assertIsNone(loaded["embedding"])


class BootstrapCfg(unittest.TestCase):
    def test_cfg_carries_lentes_and_name(self):
        inv = {"files": [], "vars": [], "by_file": {}}
        cast = onboarding.resolve_adversarial_cast([], primary="claude")
        cfg = onboarding.bootstrap_cfg(
            home=Path("/tmp/h"),
            name="ed",
            backfill_days=30,
            adversarials=cast,
            embedding=None,
            inventory=inv,
        )
        self.assertEqual(cfg["name"], "ed")
        self.assertEqual(cfg["codename"], "ed")
        self.assertEqual(cfg["lentes"]["backfill_days"], 30)
        self.assertIn("adversarials", cfg)
        self.assertNotIn("embedding", (cfg.get("routers") or {}))

    def test_cfg_wires_embedding_when_present(self):
        inv = {
            "files": ["openai.env"],
            "vars": ["OPENAI_API_KEY"],
            "by_file": {"openai.env": ["OPENAI_API_KEY"]},
        }
        emb = onboarding.embedding_from_inventory(inv)
        cast = onboarding.resolve_adversarial_cast(["codex"], primary="claude")
        cfg = onboarding.bootstrap_cfg(
            home=Path("~/edge"),
            name="ed",
            backfill_days=7,
            adversarials=cast,
            embedding=emb,
            inventory=inv,
        )
        self.assertEqual(
            cfg["routers"]["embedding"]["secret_ref"], "openai.env:OPENAI_API_KEY"
        )


class SecretsDeltaAndInsumo(unittest.TestCase):
    def test_delta_and_insumo_shape(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir(parents=True)
            (home / "secrets" / "openai.env").write_text("OPENAI_API_KEY=sk-x\n")
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=14, provision_skills=False
            )
            inv = onboarding.inventory_secrets(onboarding.secrets_dir(home))
            # second inventory after cursor stamp → unchanged
            d2 = onboarding.secrets_delta(home, inv)
            self.assertTrue(d2.get("unchanged") or d2["files_added"] == [])
            boot = onboarding.load_bootstrap(home)
            text = onboarding.compose_insumo(
                home=home,
                bootstrap=boot,
                inventory=inv,
                secrets_delta_=d2,
                assemble_text="A",
                quente_text="Q",
            )
            self.assertIn("## Quente", text)
            self.assertIn("lookback_days", text)
            self.assertIn("nasce no mentor", text)
            self.assertNotIn("sk-x", text)
            onboarding.write_insumo(home, text)
            onboarding.assert_mentor_has_insumo(home)

    def test_production_refused_until_complete(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir(parents=True)
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=7, provision_skills=False
            )
            with self.assertRaises(RuntimeError):
                onboarding.assert_production_allowed(home)

    def test_emit_phenotype_self_adversarial(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir(parents=True)
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=3, provision_skills=False
            )
            path = onboarding.emit_phenotype(home, mission="m", voice="v")
            import yaml

            cfg = yaml.safe_load(path.read_text())
            self.assertEqual(cfg["name"], "ed")
            self.assertEqual(cfg["lentes"]["backfill_days"], 3)
            self.assertIn("self", cfg.get("adversarials") or {})


class EdgeBootstrapCLI(unittest.TestCase):
    def test_cli_requires_home(self):
        import subprocess

        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "edge-bootstrap")],
            capture_output=True,
            text=True,
            env={**os.environ, "EDGE_HOME": ""},
        )
        # empty EDGE_HOME and no --home
        env = {k: v for k, v in os.environ.items() if k != "EDGE_HOME"}
        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "edge-bootstrap"), "--name", "x", "--backfill-days", "1"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_cli_bootstrap_ok(self):
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-bootstrap"),
                    "--home",
                    td,
                    "--name",
                    "ed",
                    "--backfill-days",
                    "14",
                    "--no-provision-skills",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue((Path(td) / "state" / "bootstrap.json").exists())
            self.assertIn("backfill_days=14", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
