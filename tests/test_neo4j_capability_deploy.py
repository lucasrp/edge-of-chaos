"""Hermetic deployment preflight tests; no service installation or live graph."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from neo4j_capability_auth import CapabilityAuthority  # noqa: E402
from neo4j_capability_deploy import (  # noqa: E402
    BOOTSTRAP_VERSION, DEFAULT_BYTE_BUDGET, DEFAULT_CALL_BUDGET, DEFAULT_OPERATIONS,
    DEFAULT_TTL_SECONDS, OneShotBootstrap, render_broker_service,
    bootstrap_once,
)


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.authority = CapabilityAuthority(token_factory=lambda: "b" * 48)
        self.bootstrap = OneShotBootstrap(self.authority)

    def test_exactly_one_bounded_grant_is_issued(self):
        response = self.bootstrap.handle({"version": BOOTSTRAP_VERSION,
                                          "dispatch_id": "dispatch-preflight"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["limits"], {
            "ttl_seconds": DEFAULT_TTL_SECONDS,
            "call_budget": DEFAULT_CALL_BUDGET,
            "byte_budget": DEFAULT_BYTE_BUDGET,
            "operations": sorted(DEFAULT_OPERATIONS),
        })
        state = self.authority.snapshot(response["capability"])
        self.assertEqual(state["dispatch_id"], "dispatch-preflight")
        self.assertEqual(state["calls_remaining"], DEFAULT_CALL_BUDGET)
        second = self.bootstrap.handle({"version": BOOTSTRAP_VERSION,
                                        "dispatch_id": "dispatch-other"})
        self.assertEqual(second["error"]["code"], "bootstrap_closed")

    def test_malformed_first_attempt_closes_nothing_and_issues_nothing(self):
        response = self.bootstrap.handle({"dispatch_id": "x", "group": "foreign"})
        self.assertEqual(response["error"]["code"], "invalid_bootstrap")
        self.assertFalse(self.bootstrap.closed)

    def test_secret_shaped_dispatch_is_rejected_without_reflection(self):
        response = self.bootstrap.handle({"version": BOOTSTRAP_VERSION,
                                          "dispatch_id": "TOKEN=canary"})
        self.assertNotIn("canary", json.dumps(response))

    def test_bootstrap_client_returns_token_without_printing_or_persisting(self):
        captured = []

        def call(path, request):
            captured.append((path, request))
            return self.bootstrap.handle(request)

        token, limits = bootstrap_once("/tmp/bootstrap.sock", "dispatch-preflight", call=call)
        self.assertEqual(token, "b" * 48)
        self.assertEqual(limits["call_budget"], DEFAULT_CALL_BUDGET)
        self.assertNotIn(token, json.dumps(captured))

    def test_bootstrap_client_fails_closed_on_denial_or_bad_dispatch(self):
        with self.assertRaises(ValueError):
            bootstrap_once("/tmp/bootstrap.sock", "TOKEN=canary", call=lambda *_: {})
        with self.assertRaises(RuntimeError):
            bootstrap_once("/tmp/bootstrap.sock", "dispatch-ok", call=lambda *_: {"ok": False})


class StaticUnit(unittest.TestCase):
    def test_unit_is_static_loopback_only_and_has_no_secret_literal(self):
        unit = render_broker_service(edge_home="/home/operator/edge-install")
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("timer", unit.lower())
        self.assertNotIn("heartbeat", unit.lower())
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", unit)
        self.assertIn("RuntimeDirectoryMode=0700", unit)
        self.assertIn("CapabilityBoundingSet=\n", unit)
        self.assertIn("ProtectProc=invisible", unit)
        self.assertIn("ProcSubset=pid", unit)
        self.assertIn("MemoryDenyWriteExecute=true", unit)
        self.assertNotIn("EDGE_NEO4J_PASSWORD", unit)
        self.assertNotIn("Environment=", unit)
        self.assertNotIn("EnvironmentFile=", unit)

    def test_broad_or_relative_home_is_rejected(self):
        for home in ("edge-install", "/", "/home"):
            with self.subTest(home=home), self.assertRaises(ValueError):
                render_broker_service(edge_home=home)

    def test_entrypoint_is_operator_owned_and_not_group_or_other_writable(self):
        entrypoint = REPO / "tools" / "edge-neo4j-capability-broker"
        self.assertTrue(entrypoint.is_file())
        metadata = entrypoint.stat()
        self.assertEqual(metadata.st_uid, os.getuid())
        self.assertFalse(stat.S_IMODE(metadata.st_mode) & 0o022)

    def test_check_config_uses_only_private_temporary_runtime(self):
        import importlib.machinery
        import importlib.util
        path = REPO / "tools" / "edge-neo4j-capability-broker"
        loader = importlib.machinery.SourceFileLoader("broker_entrypoint_test", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            runtime.mkdir(mode=0o700)
            os.chmod(runtime, 0o700)
            # No live branch: check-config returns before importing identity/secrets/backend runtime.
            self.assertEqual(module.main(["--home", str(REPO), "--runtime-dir", str(runtime),
                                          "--check-config"]), 0)
            with self.assertRaisesRegex(RuntimeError, "must resolve"):
                module.main(["--home", "/home/operator/not-this-install",
                             "--runtime-dir", str(runtime), "--check-config"])

    def test_check_config_accepts_a_phenotype_tools_symlink(self):
        import importlib.machinery
        import importlib.util
        path = REPO / "tools" / "edge-neo4j-capability-broker"
        loader = importlib.machinery.SourceFileLoader("broker_entrypoint_symlink_test", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            phenotype = Path(tmp) / "phenotype"
            phenotype.mkdir()
            (phenotype / "tools").symlink_to(REPO / "tools", target_is_directory=True)
            runtime = Path(tmp) / "runtime"
            runtime.mkdir(mode=0o700)
            os.chmod(runtime, 0o700)
            self.assertEqual(module.main(["--home", str(phenotype),
                                          "--runtime-dir", str(runtime),
                                          "--check-config"]), 0)

    def test_group_is_resolved_only_from_target_agent_yaml(self):
        import importlib.machinery
        import importlib.util
        path = REPO / "tools" / "edge-neo4j-capability-broker"
        loader = importlib.machinery.SourceFileLoader("broker_identity_test", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            phenotype = Path(tmp)
            (phenotype / "agent.yaml").write_text("graph_group: target-group\n")
            old = os.environ.get("EDGE_GROUP")
            os.environ["EDGE_GROUP"] = "foreign-environment-group"
            try:
                self.assertEqual(module._group_from_home(phenotype), "target-group")
            finally:
                if old is None:
                    os.environ.pop("EDGE_GROUP", None)
                else:
                    os.environ["EDGE_GROUP"] = old
            (phenotype / "agent.yaml").write_text("language: pt-BR\n")
            with self.assertRaisesRegex(RuntimeError, "no graph group"):
                module._group_from_home(phenotype)

    def test_live_entrypoint_uses_bounded_ten_minute_single_bootstrap_wait(self):
        source = (REPO / "tools" / "edge-neo4j-capability-broker").read_text()
        self.assertIn("UnixBrokerServer(bootstrap_path, bootstrap.handle, timeout=600.0)", source)
        self.assertEqual(source.count("server.serve_once()"), 2)


if __name__ == "__main__":
    unittest.main()
