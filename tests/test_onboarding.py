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


class OnboardingCompletePath(unittest.TestCase):
    """Seam: is_onboarding_complete / assert_production_allowed.

    Spec: complete = phenotype thick + grill_gate empty-missing list.
    """

    def _fresh_home(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        home = Path(td.name)
        (home / "secrets").mkdir(parents=True)
        return home

    def test_phenotype_alone_is_not_complete(self):
        home = self._fresh_home()
        log = home / "log.jsonl"
        onboarding.run_bootstrap(home=home, name="ed", backfill_days=14, provision_skills=False)
        onboarding.emit_phenotype(home, mission="m", voice="v")
        self.assertFalse(onboarding.is_onboarding_complete(home, log=log))
        with self.assertRaises(RuntimeError):
            onboarding.assert_production_allowed(home, log=log)

    def test_grill_plus_phenotype_allows_production(self):
        import eventlog
        import grill_writeback

        home = self._fresh_home()
        log = home / "log.jsonl"
        onboarding.run_bootstrap(home=home, name="ed", backfill_days=14, provision_skills=False)
        onboarding.emit_phenotype(home, mission="learn", voice="direct")
        eventlog.set_objective("learn well", log=log)
        eventlog.propose("d1", "first direction", log=log)
        eventlog.report_direction("steer body", log=log)
        grill_writeback.leveling(
            "diario",
            "sem update de persona; residual = product",
            root=home / "lv",
            log=log,
        )
        self.assertTrue(onboarding.is_onboarding_complete(home, log=log))
        onboarding.assert_production_allowed(home, log=log)  # does not raise


class BriefingOnboardingRoster(unittest.TestCase):
    """Seam: briefing.source_roster — soft when bootstrap present, fail-closed otherwise."""

    def test_soft_roster_when_bootstrap_and_no_yaml(self):
        import briefing

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir()
            (home / "secrets" / "openai.env").write_text("OPENAI_API_KEY=sk-not-logged\n")
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=21, provision_skills=False
            )
            old = os.environ.get("EDGE_HOME")
            os.environ["EDGE_HOME"] = str(home)
            try:
                roster = briefing.source_roster(agent_yaml=home / "missing-agent.yaml")
            finally:
                if old is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old
            names = [r["name"] for r in roster]
            self.assertIn("claude-sessions", names)
            self.assertIn("secrets-inventory", names)
            blob = json.dumps(roster)
            self.assertNotIn("sk-not-logged", blob)

    def test_missing_yaml_without_bootstrap_still_fails_closed(self):
        import briefing

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            old = os.environ.get("EDGE_HOME")
            os.environ["EDGE_HOME"] = str(home)
            try:
                with self.assertRaises(briefing.BriefingIdentityError):
                    briefing.source_roster(agent_yaml=home / "missing-agent.yaml")
            finally:
                if old is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old


class SweepBackfillFromBootstrap(unittest.TestCase):
    """Seam: sweep._lentes_config uses bootstrap backfill_days when yaml absent."""

    def test_backfill_days_read_from_bootstrap_json(self):
        import sweep

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=21, provision_skills=False
            )
            old = os.environ.get("EDGE_HOME")
            os.environ["EDGE_HOME"] = str(home)
            try:
                cfg = sweep._lentes_config(path=home / "agent.yaml")  # no phenotype
            finally:
                if old is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old
            self.assertEqual(cfg["backfill_days"], 21)


class HeartbeatEnableFlag(unittest.TestCase):
    """Seam: install_heartbeat(enable=False) writes units but does not enable timer."""

    def test_bootstrap_does_not_enable_timer(self):
        import _provision

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            unit_dir = home / "units"
            calls = []

            def fake_run(cmd, **kw):
                calls.append(list(cmd))

                class R:
                    returncode = 0

                return R()

            _provision.install_heartbeat(
                {"heartbeat_interval": "3h", "codename": "ed", "name": "ed"},
                home,
                unit_dir=unit_dir,
                run=fake_run,
                enable=False,
            )
            self.assertTrue((unit_dir / "edge-heartbeat.timer").exists())
            joined = [" ".join(c) for c in calls]
            self.assertTrue(any("daemon-reload" in j for j in joined))
            self.assertFalse(any("enable" in j and "edge-heartbeat.timer" in j for j in joined))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class AutoStampInsumo(unittest.TestCase):
    """Seam: maybe_stamp_insumo after wake/predispatch when first-run."""

    def test_stamps_when_bootstrap_and_no_phenotype(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=7, provision_skills=False
            )
            path = onboarding.maybe_stamp_insumo(
                home,
                briefing_text="## Assemble\n\nbrief body",
                recall_text="# Recall\n\nmem",
                quente_text="hot threads",
                delta_text="world new",
            )
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())
            text = path.read_text()
            self.assertIn("## Quente", text)
            self.assertIn("lookback_days", text)
            self.assertIn("nasce no mentor", text)
            self.assertIn("brief body", text)
            self.assertIn("hot threads", text)

    def test_no_stamp_when_no_bootstrap(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path = onboarding.maybe_stamp_insumo(home, briefing_text="x")
            self.assertIsNone(path)

    def test_no_stamp_when_phenotype_already_present(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=7, provision_skills=False
            )
            onboarding.emit_phenotype(home, mission="m", voice="v")
            path = onboarding.maybe_stamp_insumo(home, briefing_text="should not write")
            self.assertIsNone(path)


class FinishOnboarding(unittest.TestCase):
    """Seam: finish_onboarding = grill_gate + emit_phenotype (+ optional heartbeat)."""

    def test_finish_emits_phenotype_after_grill(self):
        import eventlog
        import grill_writeback

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            log = home / "log.jsonl"
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=14, provision_skills=False
            )
            eventlog.set_objective("learn", log=log)
            eventlog.propose("d1", "direction body", log=log)
            eventlog.report_direction("steer", log=log)
            grill_writeback.leveling(
                "diario", "sem update de persona; residual = x",
                root=home / "lv", log=log,
            )
            path = onboarding.finish_onboarding(
                home, log=log, mission="learn", voice="direct", enable_heartbeat=False
            )
            self.assertTrue(path.is_file())
            self.assertTrue(onboarding.is_onboarding_complete(home, log=log))
            onboarding.assert_production_allowed(home, log=log)

    def test_finish_refuses_without_grill(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            log = home / "log.jsonl"
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=5, provision_skills=False
            )
            with self.assertRaises(ValueError):
                onboarding.finish_onboarding(home, log=log, mission="m", voice="v")


class PredispatchStampsInsumo(unittest.TestCase):
    """Seam: predispatch.run stamps insumo on first-run (injectable home)."""

    def test_run_stamps_insumo_via_stamp_fn(self):
        import predispatch

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            log = home / "log.jsonl"
            (home / "secrets").mkdir()
            onboarding.run_bootstrap(
                home=home, name="ed", backfill_days=10, provision_skills=False
            )
            stamped = {}

            def stamp(**kw):
                stamped["ok"] = True
                return onboarding.maybe_stamp_insumo(home=home, **{
                    k: kw[k] for k in (
                        "briefing_text", "recall_text", "quente_text", "delta_text"
                    ) if k in kw
                })

            predispatch.run(
                sweep_fn=lambda: 0,
                briefing_fn=lambda: "BRIEFING TEXT",
                recall_fn=lambda: "RECALL TEXT",
                harvest_fn=lambda: 0,
                probe_fn=lambda _s: None,
                ready_fn=lambda: None,
                drain_fn=lambda: None,
                log=log,
                origin="user_requested",
                stamp_insumo_fn=lambda **kw: stamp(
                    briefing_text=kw.get("briefing_text", ""),
                    recall_text=kw.get("recall_text", ""),
                ),
            )
            self.assertTrue(stamped.get("ok"))
