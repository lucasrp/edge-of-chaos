"""Fail-closed runtime policy for the Hermes-only derivative."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import onboarding  # noqa: E402
import runtime_policy  # noqa: E402
import surfaces_cfg  # noqa: E402
import _claude_provision  # noqa: E402
import _codex_provision  # noqa: E402
import _grok_provision  # noqa: E402
import _llm  # noqa: E402
import _identity  # noqa: E402
import sessions  # noqa: E402


class HarnessGate(unittest.TestCase):
    def test_forbidden_harness_is_rejected_before_side_effect(self):
        for harness in (
            "claude",
            "anthropic",
            "codex",
            "grok",
            "",
            None,
            "unknown",
            "Hermes",
            " hermes ",
        ):
            with self.subTest(harness=harness):
                calls: list[str] = []

                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.run_for_harness(
                        harness,
                        lambda: calls.append("called"),
                    )

                self.assertEqual(calls, [])

    def test_missing_dedicated_home_is_rejected(self):
        with self.assertRaises(runtime_policy.RuntimePolicyError):
            runtime_policy.require_dedicated_hermes_home(None)

    def test_default_global_home_is_rejected(self):
        with self.assertRaises(runtime_policy.RuntimePolicyError):
            runtime_policy.require_dedicated_hermes_home(
                Path("/profiles/default"),
                default_home=Path("/profiles/default"),
            )

    def test_explicit_forbidden_surface_is_rejected_even_when_disabled(self):
        cfg = {
            "surfaces": {
                "hermes": {"enabled": True},
                "claude": {"enabled": False},
            }
        }

        with self.assertRaises(runtime_policy.RuntimePolicyError):
            runtime_policy.require_hermes_only_surfaces(cfg)

    def test_explicit_config_cannot_reenable_forbidden_surface(self):
        for forbidden in ("claude", "codex", "grok"):
            cfg = {"surfaces": {forbidden: {"enabled": True}}}
            with self.subTest(harness=forbidden):
                self.assertFalse(surfaces_cfg.surface_enabled(forbidden, cfg=cfg))

    def test_runtime_config_rejects_external_activation_selectors(self):
        cases = (
            {"primary": "claude"},
            {"adversarials": {"members": ["codex"]}},
            {"heartbeat": {"cli_mix": {"hermes": 1, "grok": 1}}},
            {"execution_subagents": {"default": "grok"}},
            {"subagents": {"codex_assist": {"review": True}}},
        )
        for cfg in cases:
            with self.subTest(cfg=cfg):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.require_hermes_only_runtime_config(cfg)

    def test_runtime_config_rejects_malformed_mapping_sections(self):
        for section in ("surfaces", "routers", "heartbeat"):
            with self.subTest(section=section):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.require_hermes_only_runtime_config({section: []})

    def test_runtime_config_rejects_external_router_and_heartbeat(self):
        configs = (
            {"routers": {"chat": {"provider": "claude"}}},
            {"routers": {"review": {"provider": "codex"}}},
            {"heartbeat": {"cli": "grok"}},
        )
        for cfg in configs:
            with self.subTest(cfg=cfg):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.require_hermes_only_runtime_config(cfg)

    def test_make_client_rejects_external_cli_before_constructor(self):
        constructor = mock.Mock(side_effect=AssertionError("external client constructed"))
        with mock.patch.dict(_llm._SUBSCRIPTION_CLIENTS, {"claude": constructor}):
            with self.assertRaises(runtime_policy.RuntimePolicyError):
                _llm.make_client({"provider": "claude"}, api_key="")
        constructor.assert_not_called()

    def test_embedding_router_uses_closed_provider_and_model_policy(self):
        for provider in ("claude", "codex", "grok", "xai", "deepseek", "together"):
            with self.subTest(provider=provider):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.require_allowed_embedding_router(
                        {"provider": provider, "model": "embedding-model"}
                    )
        for model in ("claude-embedding", "grok-vector", "codex-embed"):
            with self.subTest(model=model):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    runtime_policy.require_allowed_embedding_router(
                        {"provider": "openai", "model": model}
                    )
        with self.assertRaises(runtime_policy.RuntimePolicyError):
            runtime_policy.require_allowed_embedding_router(
                {"provider": "azure", "model": "text-embedding-3-small"}
            )
        accepted = runtime_policy.require_allowed_embedding_router(
            {
                "provider": "azure",
                "base_url": "https://example.openai.azure.com/openai/v1",
                "model": "text-embedding-3-small",
            }
        )
        self.assertEqual(accepted["provider"], "azure")

    def test_make_client_rejects_external_api_completion_provider(self):
        for provider in ("xai", "openrouter", "openai"):
            with self.subTest(provider=provider):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    _llm.make_client({"provider": provider}, "synthetic-key")

    def test_public_session_ingestion_is_dark_before_path_access(self):
        calls = (
            lambda: sessions.list_sessions(Path("/must-not-read")),
            lambda: sessions.list_codex_sessions(Path("/must-not-read")),
            lambda: sessions.list_grok_sessions(Path("/must-not-read")),
            lambda: sessions.dialogue_turns(Path("/must-not-read"), surface="claude"),
            lambda: sessions.read_turns(Path("/must-not-read"), surface="claude"),
            lambda: sessions.current_session_anchor({"CLAUDE_CODE_SESSION_ID": "synthetic"}),
            _identity.project_dir,
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    call()

    def test_edge_dogfood_shadow_is_blocked_before_home_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "dogfood-home"
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "edge-dogfood-shadow"),
                 "--home", str(home), "seed"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("blocked", proc.stderr.lower())
            self.assertFalse(home.exists())

    def test_edge_heartbeat_is_blocked_before_home_access(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "install"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-heartbeat"),
                    "--home",
                    str(home),
                    "--cli",
                    "claude",
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("forbidden", result.stderr)
            self.assertFalse(home.exists())

    def test_direct_adversarial_resolver_rejects_forbidden_member(self):
        with self.assertRaises(runtime_policy.RuntimePolicyError):
            onboarding.resolve_adversarial_cast(["codex"], primary="hermes")

    def test_direct_bootstrap_cfg_rejects_forbidden_primary(self):
        with self.assertRaises(runtime_policy.RuntimePolicyError):
            onboarding.bootstrap_cfg(
                home=Path("/unused/install"),
                name="probe",
                backfill_days=0,
                adversarials={"mode": "self", "primary": "claude", "members": ["self"]},
                embedding=None,
                primary="claude",
            )

    def test_bootstrap_cfg_declares_hermes_without_host_detection(self):
        installed = {"claude": False, "codex": False, "grok": False, "hermes": False}
        with mock.patch.object(
            surfaces_cfg,
            "detect_installed_surfaces",
            return_value=installed,
        ):
            cfg = onboarding.bootstrap_cfg(
                home=Path("/unused/install"),
                name="probe",
                backfill_days=0,
                adversarials={"mode": "self", "primary": "hermes", "members": ["self"]},
                embedding=None,
                primary="hermes",
            )

        self.assertEqual(cfg["surfaces"], {"hermes": {"enabled": True}})

    def test_surface_path_resolvers_do_not_expose_forbidden_homes(self):
        for forbidden in ("claude", "codex", "grok"):
            with self.subTest(harness=forbidden):
                cfg = {
                    "surfaces": {
                        forbidden: {
                            "enabled": True,
                            "home": f"/synthetic/{forbidden}",
                            "sessions": f"/synthetic/{forbidden}/sessions",
                            "active_sessions": f"/synthetic/{forbidden}/active.json",
                        }
                    }
                }
                env = {
                    "CODEX_HOME": "/override/codex",
                    "GROK_HOME": "/override/grok",
                    "EDGE_CODEX_SESSIONS_DIR": "/override/codex/sessions",
                    "EDGE_GROK_SESSIONS_DIR": "/override/grok/sessions",
                }
                self.assertIsNone(surfaces_cfg.surface_home(forbidden, cfg=cfg, env=env))
                self.assertIsNone(surfaces_cfg.surface_sessions_dir(forbidden, cfg=cfg, env=env))
                self.assertIsNone(
                    surfaces_cfg.surface_active_sessions_path(forbidden, cfg=cfg, env=env)
                )

    def test_hermes_surface_path_requires_dedicated_home(self):
        self.assertIsNone(surfaces_cfg.surface_home("hermes", cfg={}, env={}))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = {"surfaces": {"hermes": {"enabled": True, "home": str(root / ".hermes")}}}
            with mock.patch.object(runtime_policy.Path, "home", return_value=root):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    surfaces_cfg.surface_home("hermes", cfg=cfg, env={})
            dedicated = root / ".hermes" / "profiles" / "edge"
            cfg["surfaces"]["hermes"]["home"] = str(dedicated)
            with mock.patch.object(runtime_policy.Path, "home", return_value=root):
                self.assertEqual(
                    surfaces_cfg.surface_home("hermes", cfg=cfg, env={}),
                    dedicated.resolve(),
                )

    def test_autodetection_authorizes_only_explicit_dedicated_hermes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for dirname in (".claude", ".codex", ".grok", ".hermes"):
                (home / dirname).mkdir()
            self.assertEqual(
                surfaces_cfg.surfaces_block_for_installed(env={}, home=home),
                {},
            )
            dedicated = home / ".hermes" / "profiles" / "edge"
            dedicated.mkdir(parents=True)
            with mock.patch.object(runtime_policy.Path, "home", return_value=home):
                block = surfaces_cfg.surfaces_block_for_installed(
                    env={"HERMES_HOME": str(dedicated)}, home=home
                )
            self.assertEqual(
                block,
                {"hermes": {"enabled": True, "home": str(dedicated.resolve())}},
            )

    def test_absent_surface_block_defaults_only_to_hermes(self):
        self.assertTrue(surfaces_cfg.surface_enabled("hermes", cfg={}))
        for forbidden in ("claude", "codex", "grok"):
            with self.subTest(harness=forbidden):
                self.assertFalse(surfaces_cfg.surface_enabled(forbidden, cfg={}))

    def test_provision_surface_rejects_forbidden_harness_before_detection(self):
        with mock.patch.object(
            surfaces_cfg,
            "detect_installed_surfaces",
            side_effect=AssertionError("host detection reached"),
        ):
            with self.assertRaises(runtime_policy.RuntimePolicyError):
                surfaces_cfg.provision_surface("claude", cfg={})

    def test_bootstrap_rejects_forbidden_primary_before_writing_home(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            install_home = Path(tmp) / "new-install"

            with self.assertRaises(runtime_policy.RuntimePolicyError):
                onboarding.run_bootstrap(
                    home=install_home,
                    name="probe",
                    backfill_days=0,
                    primary="claude",
                    provision_skills=False,
                )

            self.assertFalse(install_home.exists())

    def test_bootstrap_rejects_forbidden_adversarial_before_writing_home(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            install_home = Path(tmp) / "new-install"

            with self.assertRaises(runtime_policy.RuntimePolicyError):
                onboarding.run_bootstrap(
                    home=install_home,
                    name="probe",
                    backfill_days=0,
                    primary="hermes",
                    adversarials=["codex"],
                    provision_skills=False,
                )

            self.assertFalse(install_home.exists())

    def test_bootstrap_requires_dedicated_hermes_home_before_processing(self):
        with mock.patch.object(
            onboarding,
            "require_name",
            side_effect=AssertionError("bootstrap crossed the policy barrier"),
        ):
            with self.assertRaises(runtime_policy.RuntimePolicyError):
                onboarding.run_bootstrap(
                    home=Path("/unused/install"),
                    name="probe",
                    backfill_days=0,
                    primary="hermes",
                    hermes_home=None,
                    provision_skills=True,
                )

    def test_bootstrap_provisions_only_dedicated_hermes_home(self):
        import tempfile

        installed = {"claude": True, "codex": True, "grok": True, "hermes": True}
        forbidden = AssertionError("forbidden provisioner reached")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_home = root / "install"
            hermes_home = root / "profiles" / "edge"
            with (
                mock.patch.object(
                    surfaces_cfg,
                    "detect_installed_surfaces",
                    return_value=installed,
                ),
                mock.patch.object(
                    _claude_provision,
                    "provision_claude",
                    side_effect=forbidden,
                ),
                mock.patch.object(
                    _codex_provision,
                    "provision_codex",
                    side_effect=forbidden,
                ),
                mock.patch.object(
                    _grok_provision,
                    "provision_grok",
                    side_effect=forbidden,
                ),
            ):
                result = onboarding.run_bootstrap(
                    home=install_home,
                    name="probe",
                    backfill_days=0,
                    primary="hermes",
                    hermes_home=hermes_home,
                    provision_skills=True,
                )

            self.assertNotIn("provision_warning", result)
            self.assertTrue(result["provisioned_surfaces"])
            self.assertTrue(
                all(row.startswith("hermes: ") for row in result["provisioned_surfaces"])
            )
            self.assertTrue(
                (hermes_home / "skills" / "probe-wake" / "SKILL.md").is_file()
            )

    def test_cli_defaults_primary_to_hermes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            install_home = Path(tmp) / "install"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-bootstrap"),
                    "bootstrap",
                    "--home",
                    str(install_home),
                    "--name",
                    "probe",
                    "--backfill-days",
                    "0",
                    "--no-provision-skills",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"ok": true', result.stdout)

    def test_edge_apply_rejects_forbidden_surface_before_install(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phenotype = root / "agent.yaml"
            phenotype.write_text(
                "name: probe\n"
                "surfaces:\n"
                "  hermes:\n"
                "    enabled: true\n"
                "  claude:\n"
                "    enabled: false\n",
                encoding="utf-8",
            )
            install_home = root / "install"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-apply"),
                    "--yaml",
                    str(phenotype),
                    "--home",
                    str(install_home),
                    "--hermes-home",
                    str(root / "profiles" / "edge"),
                    "--validate",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("forbidden surfaces declared", result.stderr)
            self.assertFalse(install_home.exists())

    def test_edge_apply_writes_only_dedicated_hermes_home(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phenotype = root / "agent.yaml"
            phenotype.write_text(
                "name: probe\n"
                "codename: probe\n"
                "mission: test gate\n"
                "voice: direct\n"
                "skill_prefix: probe\n"
                "tool_prefix: probe\n"
                "blog_public_url: https://probe.invalid\n"
                "surfaces:\n"
                "  hermes:\n"
                "    enabled: true\n"
                "sources:\n"
                "  - name: hn\n"
                "    kind: api\n",
                encoding="utf-8",
            )
            install_home = root / "install"
            hermes_home = root / "profiles" / "edge"
            external_homes = {
                "claude": root / "profiles" / "claude",
                "codex": root / "profiles" / "codex",
                "grok": root / "profiles" / "grok",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-apply"),
                    "--yaml",
                    str(phenotype),
                    "--home",
                    str(install_home),
                    "--hermes-home",
                    str(hermes_home),
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(root), "USERPROFILE": str(root)},
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name, path in external_homes.items():
                with self.subTest(harness=name):
                    self.assertFalse(path.exists())
            self.assertTrue(list((hermes_home / "skills").glob("*/SKILL.md")))

    def test_edge_apply_blocks_runtime_provisioning_before_install(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phenotype = root / "agent.yaml"
            phenotype.write_text(
                "name: probe\n"
                "surfaces:\n"
                "  hermes:\n"
                "    enabled: true\n"
                "routers:\n"
                "  chat:\n"
                "    provider: hermes\n"
                "    model: test\n"
                "    secret_ref: missing.env:MISSING_KEY\n",
                encoding="utf-8",
            )
            install_home = root / "install"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "edge-apply"),
                    "--yaml",
                    str(phenotype),
                    "--home",
                    str(install_home),
                    "--hermes-home",
                    str(root / "profiles" / "edge"),
                    "--provision-runtime",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(root), "USERPROFILE": str(root)},
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("runtime provisioning is blocked", result.stderr)
            self.assertFalse(install_home.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
