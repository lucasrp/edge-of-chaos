"""Hermetic credential-free MCP, environment, and file-descriptor delivery tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from heartbeat_child_env import build_hardened_child_env  # noqa: E402
import neo4j_capability_mcp as adapter_module  # noqa: E402
from neo4j_capability_auth import CapabilityAuthority  # noqa: E402
from neo4j_capability_runtime import (  # noqa: E402
    CAPABILITY_ENV, capability_mcp_config, codex_capability_command,
    dispatch_capability_lease,
    issued_capability_environment, run_deterministic_launcher_preflight,
    supervised_broker_lease,
)


TOKEN = "temporary-capability-" + "x" * 32


class HardenedEnvironment(unittest.TestCase):
    def test_allowlist_preserves_runtime_metadata_and_removes_secrets(self):
        base = {
            "PATH": "/usr/bin", "HOME": "/home/operator", "LANG": "en_US.UTF-8",
            "EDGE_NEO4J_PASSWORD": "canary", "OPENAI_API_KEY": "canary",
            "OP_SERVICE_ACCOUNT_TOKEN": "canary", "SSH_AUTH_SOCK": "/tmp/agent.sock",
            "DOCKER_HOST": "unix:///var/run/docker.sock", "UNRELATED": "drop-me",
        }
        env = build_hardened_child_env(base, required={
            "EDGE_DISPATCH_PLAN_ID": "dispatch-4", "EDGE_BROKER_SOCKET": "/run/user/1000/x.sock",
            "EDGE_BROKER_CAPABILITY": TOKEN,
            "EDGE_RUNTIME_ROOT": "/var/lib/edge-codex-heartbeat/runtime-output",
        })
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["EDGE_BROKER_CAPABILITY"], TOKEN)
        self.assertEqual(
            env["EDGE_RUNTIME_ROOT"],
            "/var/lib/edge-codex-heartbeat/runtime-output",
        )
        encoded = json.dumps(env)
        self.assertNotIn("canary", encoded)
        for name in ("EDGE_NEO4J_PASSWORD", "OPENAI_API_KEY", "OP_SERVICE_ACCOUNT_TOKEN",
                     "SSH_AUTH_SOCK", "DOCKER_HOST", "UNRELATED"):
            self.assertNotIn(name, env)

    def test_required_secret_or_unknown_environment_name_is_rejected(self):
        for name in ("EDGE_NEO4J_PASSWORD", "OPENAI_API_KEY", "ANY_NEW_FIELD"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_hardened_child_env({}, required={name: "value"})


class CredentialFreeMCP(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def call(path, envelope):
            self.calls.append((path, envelope))
            return {"ok": True, "result": {"nodes": [{"slug": "safe"}]}}

        self.adapter = adapter_module.CapabilityMCP(
            socket_path="/tmp/synthetic.sock", dispatch_id="dispatch-4",
            capability=TOKEN, call=call,
        )

    def test_lists_only_five_brokered_read_tools(self):
        response = self.adapter.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(names, {"cortex_health", "cortex_recall", "cortex_surf",
                                 "cortex_node", "cortex_search"})

    def test_tool_call_builds_authorized_envelope_without_group_or_cypher(self):
        response = self.adapter.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                        "params": {"name": "cortex_search",
                                                   "arguments": {"query": "memory", "limit": 3}}})
        self.assertFalse(response["result"]["isError"])
        _path, envelope = self.calls[-1]
        self.assertEqual(envelope["dispatch_id"], "dispatch-4")
        self.assertEqual(envelope["capability"], TOKEN)
        self.assertEqual(envelope["request"]["operation"], "search")
        self.assertNotIn("group", json.dumps(envelope))
        self.assertNotIn("cypher", json.dumps(envelope).lower())

    def test_transport_outage_is_an_honest_dark_tool_result(self):
        def unavailable(_path, _envelope):
            raise adapter_module.TransportError("down")

        adapter = adapter_module.CapabilityMCP(
            socket_path="/tmp/missing.sock", dispatch_id="dispatch-4",
            capability=TOKEN, call=unavailable,
        )
        response = adapter.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                   "params": {"name": "cortex_recall", "arguments": {}}})
        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertTrue(result["structuredContent"]["dark"])
        self.assertNotIn(TOKEN, json.dumps(response))

    def test_missing_socket_dispatch_or_capability_fails_loud_at_construction(self):
        for values in ((None, "dispatch", TOKEN), ("/tmp/x", None, TOKEN),
                       ("/tmp/x", "dispatch", None)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                adapter_module.CapabilityMCP(
                    socket_path=values[0], dispatch_id=values[1], capability=values[2]
                )

    def test_source_imports_no_graph_identity_or_secret_modules(self):
        source = (REPO / "tools" / "neo4j_capability_mcp.py").read_text()
        for forbidden in ("import neo4j", "import _identity", "import _secrets", "GraphDatabase",
                          "EDGE_NEO4J_PASSWORD"):
            self.assertNotIn(forbidden, source)


class FileDescriptorDelivery(unittest.TestCase):
    def test_adapter_can_read_token_from_inherited_fd_without_environment_value(self):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, TOKEN.encode())
            os.close(write_fd)
            write_fd = -1
            token = adapter_module.read_capability_fd(read_fd)
            read_fd = -1
        finally:
            for fd in (read_fd, write_fd):
                if fd >= 0:
                    os.close(fd)
        self.assertEqual(token, TOKEN)
        self.assertNotIn(TOKEN, os.environ.values())

    def test_any_parent_process_that_inherits_fd_can_read_the_token(self):
        """Negative proof: pass_fds exposes the descriptor to the process, not just its future MCP."""
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, TOKEN.encode())
            os.close(write_fd)
            write_fd = -1
            code = "import os,sys; sys.stdout.write(os.read(int(sys.argv[1]),256).decode())"
            result = subprocess.run(
                [sys.executable, "-c", code, str(read_fd)], pass_fds=(read_fd,),
                capture_output=True, text=True, check=True,
                env=build_hardened_child_env(os.environ, required={"EDGE_CAPABILITY_FD": str(read_fd)}),
            )
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)
        self.assertEqual(result.stdout, TOKEN)


class PragmaticLease(unittest.TestCase):
    def setUp(self):
        self.counter = 0

        def tokens():
            self.counter += 1
            return f"lease-{self.counter:04d}-" + "z" * 40

        self.authority = CapabilityAuthority(token_factory=tokens)

    def _lease(self):
        return dispatch_capability_lease(
            self.authority,
            base_env={"PATH": "/usr/bin", "EDGE_NEO4J_PASSWORD": "never-copy"},
            socket_path="/tmp/synthetic.sock",
            dispatch_id="dispatch-lease",
            operations={"health", "recall"},
            ttl_seconds=30,
            call_budget=4,
            byte_budget=4096,
        )

    def test_lease_exposes_only_bounded_token_then_revokes_and_removes_it(self):
        with self._lease() as env:
            token = env[CAPABILITY_ENV]
            self.assertNotIn("EDGE_NEO4J_PASSWORD", env)
            self.assertFalse(self.authority.snapshot(token)["revoked"])
        self.assertNotIn(CAPABILITY_ENV, env)
        self.assertTrue(self.authority.snapshot(token)["revoked"])

    def test_exception_still_revokes_and_removes_capability(self):
        env = None
        token = None
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with self._lease() as env:
                token = env[CAPABILITY_ENV]
                raise RuntimeError("synthetic failure")
        self.assertNotIn(CAPABILITY_ENV, env)
        self.assertTrue(self.authority.snapshot(token)["revoked"])

    def test_mcp_config_never_serializes_capability(self):
        config = capability_mcp_config(
            home=REPO, socket_path="/tmp/synthetic.sock", dispatch_id="dispatch-lease"
        )
        encoded = json.dumps(config)
        self.assertNotIn(TOKEN, encoded)
        self.assertNotIn(CAPABILITY_ENV, encoded)
        self.assertNotIn("EDGE_NEO4J_PASSWORD", encoded)
        self.assertTrue(config["mcpServers"]["cortex"]["args"][0].endswith(
            "tools/neo4j_capability_mcp.py"
        ))

    def test_mcp_main_pops_capability_before_serving(self):
        environment = {
            CAPABILITY_ENV: TOKEN,
            "EDGE_BROKER_SOCKET": "/tmp/synthetic.sock",
            "EDGE_DISPATCH_PLAN_ID": "dispatch-lease",
        }
        observed = {}

        def fake_serve(adapter):
            observed["token_absent"] = CAPABILITY_ENV not in os.environ
            observed["adapter_has_token"] = adapter.capability == TOKEN

        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(adapter_module, "serve_stdio", fake_serve):
            adapter_module.main()
        self.assertTrue(observed["token_absent"])
        self.assertTrue(observed["adapter_has_token"])

    def test_our_config_and_audit_fixture_do_not_persist_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._lease() as env:
                token = env[CAPABILITY_ENV]
                config = capability_mcp_config(
                    home=REPO, socket_path="/tmp/synthetic.sock", dispatch_id="dispatch-lease"
                )
                config_path = Path(tmp) / "mcp.json"
                config_path.write_text(json.dumps(config))
                audit_path = Path(tmp) / "audit.jsonl"
                audit_path.write_text(json.dumps({"dispatch_id": "dispatch-lease",
                                                  "outcome": "revoked"}) + "\n")
            landed = config_path.read_text() + audit_path.read_text()
            self.assertNotIn(token, landed)


class DeterministicLauncherPreflight(unittest.TestCase):
    def test_codex_command_declares_env_name_without_serializing_capability(self):
        base = ["/opt/codex", "exec", "--ephemeral", "-"]
        command = codex_capability_command(
            base, home=REPO, socket_path="/tmp/broker.sock",
            dispatch_id="launcher-preflight",
        )
        encoded = json.dumps(command)
        self.assertIn("mcp_servers.cortex.env_vars", encoded)
        self.assertIn(CAPABILITY_ENV, encoded)
        self.assertNotIn(TOKEN, encoded)
        self.assertEqual(command[-1], "-")

    def test_codex_command_rejects_a_non_codex_or_non_stdin_shape(self):
        for command in (["claude", "-p", "-"], ["codex", "exec", "prompt"]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                codex_capability_command(
                    command, home=REPO, socket_path="/tmp/x", dispatch_id="dispatch",
                )

    @mock.patch("neo4j_capability_deploy.bootstrap_once", return_value=(TOKEN, {"call_budget": 4}))
    @mock.patch("neo4j_capability_runtime.Path.exists", return_value=True)
    def test_supervised_broker_starts_yields_and_confirms_stop(self, _exists, _bootstrap):
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if "ExecStart" in command:
                stdout = f"LoadState=loaded\nExecStart=x --home {REPO.resolve()} y\n"
            elif "show" in command:
                stdout = "ActiveState=inactive\nMainPID=0\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}, clear=False):
            with supervised_broker_lease(
                    home=REPO, dispatch_id="launcher-preflight",
                    base_env={"PATH": "/usr/bin"}, run_command=run) as (env, limits):
                self.assertEqual(env[CAPABILITY_ENV], TOKEN)
                self.assertEqual(limits["call_budget"], 4)
            self.assertNotIn(CAPABILITY_ENV, env)
        self.assertIn("ExecStart", calls[0])
        self.assertEqual(calls[1][2], "start")
        self.assertEqual(calls[-2][2], "stop")
        self.assertIn("show", calls[-1])

    @mock.patch("neo4j_capability_runtime.Path.exists", return_value=True)
    def test_supervised_broker_refuses_unconfirmed_cleanup(self, _exists):
        def run(command, **_kwargs):
            if "stop" in command:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")
            stdout = f"LoadState=loaded\nExecStart=x --home {REPO.resolve()} y\n" \
                if "ExecStart" in command else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}, clear=False), \
                mock.patch("neo4j_capability_deploy.bootstrap_once",
                           return_value=(TOKEN, {})), \
                self.assertRaisesRegex(RuntimeError, "failed to stop"):
            with supervised_broker_lease(
                    home=REPO, dispatch_id="launcher-preflight",
                    base_env={"PATH": "/usr/bin"}, run_command=run):
                pass

    def test_supervised_broker_rejects_a_unit_owned_by_another_install(self):
        def run(command, **_kwargs):
            stdout = "LoadState=loaded\nExecStart=x --home /srv/another-tenant y\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}, clear=False), \
                self.assertRaisesRegex(RuntimeError, "identity does not match"):
            with supervised_broker_lease(
                    home=REPO, dispatch_id="launcher-preflight",
                    base_env={"PATH": "/usr/bin"}, run_command=run):
                pass

    def test_external_grant_is_allowlisted_then_discarded_locally(self):
        with issued_capability_environment(
                base_env={"PATH": "/usr/bin", "OPENAI_API_KEY": "never-copy"},
                socket_path="/tmp/broker.sock", dispatch_id="launcher-preflight",
                capability=TOKEN) as env:
            self.assertEqual(env[CAPABILITY_ENV], TOKEN)
            self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn(CAPABILITY_ENV, env)

    @mock.patch("neo4j_capability_runtime.subprocess.run")
    def test_real_child_seam_is_summarized_without_content_or_llm(self, run):
        replies = [
            {"jsonrpc": "2.0", "id": 1,
             "result": {"serverInfo": {"name": "cortex-broker"}}},
            {"jsonrpc": "2.0", "id": 2,
             "result": {"isError": False, "structuredContent": {
                 "ready": True, "protocol": "v1"}}},
            {"jsonrpc": "2.0", "id": 3,
             "result": {"isError": False, "structuredContent": {
                 "nodes": [{"sensitive": "not returned by summary"}], "truncated": False}}},
        ]
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="\n".join(map(json.dumps, replies)) + "\n", stderr="",
        )
        result = run_deterministic_launcher_preflight(
            home=REPO, socket_path="/tmp/broker.sock", dispatch_id="launcher-preflight",
            capability=TOKEN,
            base_env={"PATH": "/usr/bin", "OPENAI_API_KEY": "never-copy"},
        )
        self.assertTrue(result["initialized"])
        self.assertTrue(result["health_ready"])
        self.assertEqual(result["recall_fields"], ["nodes", "truncated"])
        self.assertTrue(result["local_capability_discarded"])
        self.assertFalse(result["llm_invoked"])
        self.assertNotIn("sensitive", json.dumps(result))
        called = run.call_args
        self.assertNotIn(TOKEN, json.dumps(called.args))
        self.assertNotIn("OPENAI_API_KEY", called.kwargs["env"])

    @mock.patch("neo4j_capability_runtime.subprocess.run")
    def test_child_failure_is_closed_and_local_grant_is_not_retained(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=7, stdout="", stderr="synthetic failure",
        )
        with self.assertRaisesRegex(RuntimeError, "failed closed"):
            run_deterministic_launcher_preflight(
                home=REPO, socket_path="/tmp/broker.sock",
                dispatch_id="launcher-preflight", capability=TOKEN,
                base_env={"PATH": "/usr/bin"},
            )



if __name__ == "__main__":
    unittest.main()
