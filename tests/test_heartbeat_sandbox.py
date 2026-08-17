"""WP1: pure, fail-closed policy model for a sandboxed heartbeat."""

import tempfile
import unittest
import importlib.machinery
import shutil
import subprocess
from pathlib import Path

import yaml

from tools import heartbeat_sandbox as hs


class WritableRootValidation(unittest.TestCase):
    def test_rejects_relative_and_broad_roots(self):
        for value in ("edge-install", "/", "/home", "/mnt/c", str(Path.home())):
            with self.subTest(value=value), self.assertRaises(hs.SandboxPolicyError):
                hs.validate_writable_root(value)

    def test_accepts_a_specific_install(self):
        self.assertEqual(
            hs.validate_writable_root("/home/operator/edge-install"),
            Path("/home/operator/edge-install"),
        )


class DeclaredSources(unittest.TestCase):
    def test_deduplicates_direct_and_interface_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / "home" / "edge"
            source = root / "sources" / "vault"
            install.mkdir(parents=True)
            source.mkdir(parents=True)
            cfg = {"sources": [{
                "name": "vault",
                "path": str(source),
                "interfaces": [{"via": f"path:{source}"}],
            }]}
            rows = hs.declared_read_only_roots(
                cfg, writable_root=install.resolve(), require_exists=True
            )
            self.assertEqual(rows, [{"path": str(source), "sources": "vault"}])

    def test_missing_source_fails_closed(self):
        cfg = {"sources": [{"name": "lost", "path": "/definitely/not/here"}]}
        with self.assertRaisesRegex(hs.SandboxPolicyError, "does not exist"):
            hs.declared_read_only_roots(
                cfg,
                writable_root=Path("/home/operator/edge-install"),
                require_exists=True,
            )

    def test_source_may_not_overlap_writable_install(self):
        cfg = {"sources": [{"name": "bad", "path": "/home/operator/edge-install/state"}]}
        with self.assertRaisesRegex(hs.SandboxPolicyError, "overlaps"):
            hs.declared_read_only_roots(
                cfg,
                writable_root=Path("/home/operator/edge-install"),
                require_exists=False,
            )


class PolicyShape(unittest.TestCase):
    def test_policy_is_explicit_about_timer_and_residual_egress(self):
        policy = hs.build_policy(
            {"sources": []},
            edge_home="/home/operator/edge-install",
            require_sources_exist=False,
            operator_home=Path("/home/operator"),
        )
        self.assertEqual(policy["schema"], hs.POLICY_SCHEMA)
        self.assertFalse(policy["cadence"]["may_enable_timer"])
        self.assertFalse(policy["network"]["complete_egress_isolation"])
        self.assertIn("SSH_AUTH_SOCK", policy["unset_environment"])
        self.assertIn("/home/operator/.ssh", policy["inaccessible_paths"])
        self.assertIn("/mnt/c/Users/operator/.ssh", policy["inaccessible_paths"])

    def test_loader_binds_yaml_to_owning_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "edge"
            install.mkdir()
            config = install / "agent.yaml"
            config.write_text(yaml.safe_dump({
                "edge_home": str(install),
                "sources": [],
            }), encoding="utf-8")
            policy = hs.load_policy(config)
            self.assertEqual(policy["writable_root"], str(install.resolve()))

    def test_loader_rejects_yaml_claiming_another_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "edge"
            install.mkdir()
            config = install / "agent.yaml"
            config.write_text(yaml.safe_dump({
                "edge_home": "/home/operator/another-edge",
                "sources": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(hs.SandboxPolicyError, "does not match"):
                hs.load_policy(config)


class PersistentBridgePolicy(unittest.TestCase):
    def _metadata(self, mode):
        return {"owner": "edge-codex-heartbeat", "group": "edge-codex-heartbeat", "mode": mode}

    def _build(self, **overrides):
        values = {
            "cfg": {"sources": []},
            "edge_home": "/home/operator/edge-install",
            "runtime_output_root": "/var/lib/edge-codex-heartbeat/runtime-output",
            "codex_home": "/var/lib/edge-codex-heartbeat/codex-home",
            "service_identity": "edge-codex-heartbeat",
            "runtime_metadata": self._metadata("0700"),
            "codex_home_metadata": self._metadata("0700"),
            "auth_file_metadata": self._metadata("0600"),
            "operator_home": Path("/home/operator"),
            "require_sources_exist": False,
        }
        values.update(overrides)
        return hs.build_persistent_bridge_policy(**values)

    def test_separates_immutable_runtime_and_credential_roots(self):
        policy = self._build()
        self.assertEqual(policy["schema"], hs.PERSISTENT_BRIDGE_SCHEMA)
        self.assertEqual(policy["immutable_input_root"], "/home/operator/edge-install")
        self.assertEqual(
            policy["runtime_output_root"],
            "/var/lib/edge-codex-heartbeat/runtime-output",
        )
        self.assertEqual(
            policy["auth_file"],
            "/var/lib/edge-codex-heartbeat/codex-home/auth.json",
        )
        self.assertFalse(policy["cadence"]["may_enable_timer"])
        self.assertFalse(policy["enforcement"]["implemented"])
        self.assertFalse(policy["enforcement"]["credential_content_present"])

    def test_rejects_runtime_or_credentials_inside_install(self):
        for field, path in (
            ("runtime_output_root", "/home/operator/edge-install/state/beat"),
            ("codex_home", "/home/operator/edge-install/state/beat/codex-home"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                    hs.SandboxPolicyError, "overlaps immutable"):
                self._build(**{field: path})

    def test_rejects_overlapping_private_roots(self):
        with self.assertRaisesRegex(hs.SandboxPolicyError, "must not overlap"):
            self._build(
                codex_home="/var/lib/edge-codex-heartbeat/runtime-output/codex-home"
            )

    def test_rejects_broad_temporary_and_mounted_roots(self):
        for field, path in (
            ("runtime_output_root", "/var/lib"),
            ("runtime_output_root", "/tmp/edge-runtime"),
            ("codex_home", "/mnt/c/edge-codex-home"),
        ):
            with self.subTest(field=field), self.assertRaises(hs.SandboxPolicyError):
                self._build(**{field: path})

    def test_rejects_wrong_identity_or_permissive_mode(self):
        with self.assertRaisesRegex(hs.SandboxPolicyError, "service_identity"):
            self._build(runtime_metadata={"owner": "pedro", "group": "pedro", "mode": "0700"})
        with self.assertRaisesRegex(hs.SandboxPolicyError, "0700"):
            self._build(codex_home_metadata=self._metadata("0600"))
        with self.assertRaisesRegex(hs.SandboxPolicyError, "0600"):
            self._build(auth_file_metadata=self._metadata("0700"))

    def test_rejects_private_root_overlapping_declared_source(self):
        with self.assertRaisesRegex(hs.SandboxPolicyError, "overlaps declared source"):
            self._build(cfg={"sources": [{
                "name": "unsafe-source",
                "path": "/var/lib/edge-codex-heartbeat",
            }]})

    def test_rejects_symlink_in_private_path_before_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            link = root / "redirect"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(hs.SandboxPolicyError, "symlink"):
                self._build(runtime_output_root=link / "runtime-output")

    def test_inert_service_candidate_has_exact_split_and_no_activation(self):
        policy = self._build()
        unit = hs.render_persistent_bridge_candidate(policy)
        self.assertIn("User=edge-codex-heartbeat", unit)
        self.assertIn("Group=edge-codex-heartbeat", unit)
        self.assertRegex(unit, r'ExecStart="/[^"]*/false"')
        self.assertIn("ReadOnlyPaths=/home/operator/edge-install", unit)
        self.assertIn(
            "ReadWritePaths=/var/lib/edge-codex-heartbeat/runtime-output", unit
        )
        self.assertIn(
            "ReadWritePaths=/var/lib/edge-codex-heartbeat/codex-home", unit
        )
        self.assertIn(
            "Environment=EDGE_RUNTIME_ROOT=/var/lib/edge-codex-heartbeat/runtime-output",
            unit,
        )
        self.assertNotIn("auth.json", unit)
        self.assertNotIn("tools/edge-heartbeat", unit)
        self.assertNotIn("codex exec", unit)
        self.assertNotIn("\n[Install]\n", unit)
        self.assertNotIn("WantedBy=", unit)

    def test_candidate_rejects_activation_or_non_inert_command(self):
        policy = self._build()
        policy["cadence"]["may_enable_timer"] = True
        with self.assertRaisesRegex(hs.SandboxPolicyError, "timer"):
            hs.render_persistent_bridge_candidate(policy)
        policy = self._build()
        with self.assertRaisesRegex(hs.SandboxPolicyError, "false executable"):
            hs.render_persistent_bridge_candidate(
                policy, fail_closed_bin="/opt/edge/tools/edge-heartbeat"
            )

    def test_inert_candidate_passes_systemd_static_verification(self):
        verifier = shutil.which("systemd-analyze")
        if verifier is None:
            self.skipTest("systemd-analyze is unavailable")
        unit = hs.render_persistent_bridge_candidate(self._build())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edge-persistent-auth-candidate.service"
            path.write_text(unit, encoding="utf-8")
            result = subprocess.run(
                [verifier, "verify", str(path)], capture_output=True, text=True
            )
        if result.returncode != 0 and "Operation not permitted" in result.stderr:
            self.skipTest("sandbox blocks systemd user-lookup sockets")
        self.assertEqual(result.returncode, 0, result.stderr)


class RenderOnlySystemdUnit(unittest.TestCase):
    def _policy(self):
        return hs.build_policy(
            {"sources": [{
                "name": "vault",
                "path": "/mnt/d/Users/windows-user/Documents/reference-vault",
            }]},
            edge_home="/home/operator/edge-install",
            require_sources_exist=False,
            operator_home=Path("/home/operator"),
        )

    def test_unit_is_hardened_but_can_only_dry_run(self):
        unit = hs.render_test_service(
            self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat"
        )
        self.assertIn('"/opt/edge/tools/edge-heartbeat" --home ', unit)
        self.assertIn("--dry-run", unit)
        for directive in (
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "NoNewPrivileges=true",
            "CapabilityBoundingSet=",
            "PrivateDevices=true",
            "ProtectClock=true",
            "ProtectHostname=true",
            "ProtectProc=invisible",
            "ProcSubset=pid",
            "RestrictRealtime=true",
            "ReadWritePaths=/home/operator/edge-install",
            r"ReadOnlyPaths=/mnt/d/Users/windows-user/Documents/reference-vault",
            "InaccessiblePaths=-/home/operator/.ssh",
            "InaccessiblePaths=-/mnt/d/Users/windows-user/.ssh",
            "UnsetEnvironment=",
        ):
            self.assertIn(directive, unit)

    def test_unit_has_no_install_section_or_timer_activation(self):
        unit = hs.render_test_service(
            self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat"
        )
        self.assertNotIn("\n[Install]\n", unit)
        self.assertNotIn("WantedBy=", unit)
        self.assertNotIn("systemctl", unit)
        self.assertNotIn("edge-heartbeat.timer", unit)

    def test_renderer_rejects_policy_that_may_enable_timer(self):
        policy = self._policy()
        policy["cadence"]["may_enable_timer"] = True
        with self.assertRaisesRegex(hs.SandboxPolicyError, "timer prohibition"):
            hs.render_test_service(
                policy, heartbeat_bin="/opt/edge/tools/edge-heartbeat"
            )

    def test_systemd_specifiers_are_neutralized(self):
        policy = self._policy()
        policy["read_only_roots"].append({"path": "/srv/100%/read", "sources": "x"})
        unit = hs.render_test_service(
            policy, heartbeat_bin="/opt/edge/tools/edge-heartbeat"
        )
        self.assertIn('/srv/100%%/read', unit)

    def test_preflight_unit_reuses_boundary_without_dry_run_or_timer(self):
        unit = hs.render_preflight_service(
            self._policy(),
            preflight_bin="/opt/edge/tools/heartbeat-sandbox-preflight",
            fixture="/tmp/edge-sandbox-fixture",
        )
        self.assertIn(
            'ExecStart="/opt/edge/tools/heartbeat-sandbox-preflight" '
            '--home "/home/operator/edge-install" --fixture "/tmp/edge-sandbox-fixture"',
            unit,
        )
        self.assertNotIn("--dry-run", unit)
        self.assertIn("ReadOnlyPaths=/tmp/edge-sandbox-fixture", unit)
        self.assertNotIn("edge-heartbeat.timer", unit)
        self.assertNotIn("\n[Install]\n", unit)

    def test_pilot_is_fixed_codex_bounded_and_has_no_install_section(self):
        unit = hs.render_pilot_service(
            self._policy(),
            heartbeat_bin="/opt/edge/tools/edge-heartbeat",
            cli="codex",
            timeout_seconds=600,
            codex_home="/home/operator/edge-install/state/beat/codex-pilot-home",
            dispatch_id="brokered-pilot-fixture-01",
        )
        self.assertIn(
            'ExecStart="/opt/edge/tools/edge-heartbeat" '
            '--home "/home/operator/edge-install" --cli codex '
            '--supervised-cortex-broker --dispatch-id brokered-pilot-fixture-01 '
            '--timeout-seconds 600',
            unit,
        )
        self.assertIn("TimeoutStartSec=11min", unit)
        self.assertIn(
            "Environment=CODEX_HOME=/home/operator/edge-install/state/beat/codex-pilot-home",
            unit,
        )
        self.assertNotIn("--dry-run", unit)
        self.assertNotIn("\n[Install]\n", unit)
        self.assertNotIn("edge-heartbeat.timer", unit)
        self.assertEqual(unit.count("--supervised-cortex-broker"), 1)

    def test_pilot_refuses_random_or_long_timeout(self):
        with self.assertRaises(hs.SandboxPolicyError):
            hs.render_pilot_service(
                self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat",
                cli="random", timeout_seconds=600,
                dispatch_id="pilot-random",
            )
        with self.assertRaises(hs.SandboxPolicyError):
            hs.render_pilot_service(
                self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat",
                cli="codex", timeout_seconds=601,
                codex_home="/home/operator/edge-install/state/beat/codex-pilot-home",
                dispatch_id="pilot-long",
            )

    def test_codex_home_is_required_and_must_stay_under_install(self):
        with self.assertRaisesRegex(hs.SandboxPolicyError, "requires"):
            hs.render_pilot_service(
                self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat",
                cli="codex", timeout_seconds=600,
                dispatch_id="pilot-missing-home",
            )
        with self.assertRaisesRegex(hs.SandboxPolicyError, "below"):
            hs.render_pilot_service(
                self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat",
                cli="codex", timeout_seconds=600, codex_home="/tmp/codex-home",
                dispatch_id="pilot-bad-home",
            )

    def test_pilot_requires_a_fixed_safe_dispatch_id(self):
        for dispatch_id in (None, "", "bad dispatch", "x" * 129):
            with self.subTest(dispatch_id=dispatch_id), self.assertRaisesRegex(
                    hs.SandboxPolicyError, "dispatch_id"):
                hs.render_pilot_service(
                    self._policy(), heartbeat_bin="/opt/edge/tools/edge-heartbeat",
                    cli="codex", timeout_seconds=600,
                    codex_home="/home/operator/edge-install/state/beat/codex-pilot-home",
                    dispatch_id=dispatch_id,
                )


class PreflightBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "tools" / "heartbeat-sandbox-preflight"
        cls.module = importlib.machinery.SourceFileLoader(
            "heartbeat_sandbox_preflight_test", str(path)
        ).load_module()

    def test_unsandboxed_fixture_write_is_detected_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home" / "edge-install"
            fixture = root / "fixture"
            home.mkdir(parents=True)
            fixture.mkdir()
            policy = hs.build_policy(
                {"sources": []}, edge_home=home, require_sources_exist=False,
                operator_home=root / "operator",
            )
            receipt, passed = self.module.run(home, fixture, policy)
            self.assertFalse(passed)
            self.assertFalse(receipt["fixture_write"]["denied"])
            self.assertFalse(receipt["symlink_escape_write"]["denied"])
            self.assertFalse(receipt["llm_invoked"])
            self.assertFalse(receipt["timer_touched"])


if __name__ == "__main__":
    unittest.main()
