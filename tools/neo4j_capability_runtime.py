"""Hermetic runtime assembly for one pragmatic, low-authority broker capability lease.

This module does not launch Codex or install a service.  It constructs a sanitized child
environment and a token-free MCP config, then guarantees revocation and local environment cleanup
when the caller leaves the lease context.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time

from heartbeat_child_env import build_hardened_child_env


CAPABILITY_ENV = "EDGE_BROKER_CAPABILITY"
DEFAULT_BROKER_UNIT = "edge-neo4j-capability-broker.service"
DEFAULT_BROKER_RUNTIME = "edge-neo4j-capability-broker"
_PREFLIGHT_CALLS = (
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "cortex_health", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "cortex_recall", "arguments": {}}},
)


def capability_mcp_config(*, home, socket_path, dispatch_id):
    """Return config metadata only; the capability is inherited and never serialized here."""
    home = Path(home).resolve()
    return {
        "mcpServers": {
            "cortex": {
                "command": str(home / "tools" / "edge-python"),
                "args": [str(home / "tools" / "neo4j_capability_mcp.py")],
                "env": {
                    "EDGE_BROKER_SOCKET": str(socket_path),
                    "EDGE_DISPATCH_PLAN_ID": dispatch_id,
                },
            }
        }
    }


def codex_capability_command(base_command, *, home, socket_path, dispatch_id):
    """Add one token-free, allowlisted stdio MCP definition to ``codex exec``."""
    command = list(base_command)
    if len(command) < 3 or command[1] != "exec" or command[-1] != "-":
        raise ValueError("capability MCP requires a prompt-on-stdin codex exec command")
    home = Path(home).resolve()
    overrides = (
        ("mcp_servers.cortex.command", str(home / "tools" / "edge-python")),
        ("mcp_servers.cortex.args", [str(home / "tools" / "neo4j_capability_mcp.py")]),
        ("mcp_servers.cortex.env.EDGE_BROKER_SOCKET", str(socket_path)),
        ("mcp_servers.cortex.env.EDGE_DISPATCH_PLAN_ID", dispatch_id),
        ("mcp_servers.cortex.env_vars", [CAPABILITY_ENV]),
        ("mcp_servers.cortex.enabled_tools", [
            "cortex_health", "cortex_recall", "cortex_surf", "cortex_node", "cortex_search",
        ]),
    )
    rendered = []
    for key, value in overrides:
        rendered.extend(["-c", f"{key}={json.dumps(value, separators=(',', ':'))}"])
    return [*command[:-1], *rendered, command[-1]]


@contextmanager
def dispatch_capability_lease(
        authority, *, base_env, socket_path, dispatch_id, operations,
        ttl_seconds, call_budget, byte_budget):
    """Yield one child environment and always revoke/remove its temporary capability."""
    token = authority.issue(
        dispatch_id=dispatch_id,
        operations=operations,
        ttl_seconds=ttl_seconds,
        call_budget=call_budget,
        byte_budget=byte_budget,
    )
    child_env = build_hardened_child_env(base_env, required={
        "EDGE_BROKER_SOCKET": str(socket_path),
        "EDGE_DISPATCH_PLAN_ID": dispatch_id,
        CAPABILITY_ENV: token,
    })
    try:
        yield child_env
    finally:
        authority.revoke(token)
        child_env.pop(CAPABILITY_ENV, None)
        token = None


@contextmanager
def issued_capability_environment(*, base_env, socket_path, dispatch_id, capability):
    """Hold an externally issued grant only for one child-process launch.

    The separate broker owns revocation.  Exiting this context removes our local reference; callers
    must stop that one-shot broker (or use a future broker revocation endpoint) to revoke the grant.
    """
    child_env = build_hardened_child_env(base_env, required={
        "EDGE_BROKER_SOCKET": str(socket_path),
        "EDGE_DISPATCH_PLAN_ID": dispatch_id,
        CAPABILITY_ENV: capability,
    })
    try:
        yield child_env
    finally:
        child_env.pop(CAPABILITY_ENV, None)
        capability = None


@contextmanager
def supervised_broker_lease(
        *, home, dispatch_id, base_env, unit=DEFAULT_BROKER_UNIT,
        runtime_name=DEFAULT_BROKER_RUNTIME, start_timeout_seconds=30,
        run_command=subprocess.run):
    """Start one static broker, issue once, yield a narrow env, then destroy its authority."""
    if unit != DEFAULT_BROKER_UNIT or runtime_name != DEFAULT_BROKER_RUNTIME:
        raise ValueError("supervised broker identity is fixed")
    runtime_root = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    if not runtime_root.is_absolute():
        raise RuntimeError("XDG_RUNTIME_DIR is unavailable")
    runtime = runtime_root / runtime_name
    bootstrap_socket = runtime / "bootstrap.sock"
    broker_socket = runtime / "broker.sock"
    started = False
    try:
        identity = run_command(
            ["systemctl", "--user", "show", unit, "-p", "LoadState", "-p", "ExecStart"],
            capture_output=True, text=True, check=False,
        )
        expected_home = str(Path(home).resolve())
        if identity.returncode != 0 or "LoadState=loaded" not in identity.stdout \
                or f" --home {expected_home} " not in identity.stdout:
            raise RuntimeError("supervised broker identity does not match this install")
        start = run_command(
            ["systemctl", "--user", "start", unit], capture_output=True, text=True,
            check=False,
        )
        if start.returncode != 0:
            raise RuntimeError("supervised broker failed to start")
        started = True
        deadline = time.monotonic() + start_timeout_seconds
        while time.monotonic() < deadline and not bootstrap_socket.exists():
            time.sleep(0.05)
        if not bootstrap_socket.exists():
            raise RuntimeError("supervised broker bootstrap timed out")
        from neo4j_capability_deploy import bootstrap_once
        capability, limits = bootstrap_once(str(bootstrap_socket), dispatch_id)
        with issued_capability_environment(
                base_env=base_env, socket_path=broker_socket, dispatch_id=dispatch_id,
                capability=capability) as child_env:
            yield child_env, limits
    finally:
        if started:
            stop = run_command(
                ["systemctl", "--user", "stop", unit], capture_output=True, text=True,
                check=False,
            )
            if stop.returncode != 0:
                raise RuntimeError("supervised broker failed to stop")
            status = run_command(
                ["systemctl", "--user", "show", unit, "-p", "ActiveState", "-p", "MainPID"],
                capture_output=True, text=True, check=False,
            )
            if status.returncode != 0 or "ActiveState=inactive" not in status.stdout \
                    or "MainPID=0" not in status.stdout:
                raise RuntimeError("supervised broker cleanup is unconfirmed")


def run_deterministic_launcher_preflight(
        *, home, socket_path, dispatch_id, capability, base_env, timeout_seconds=20):
    """Exercise the real credential-free MCP child without an LLM and return sanitized facts."""
    home = Path(home).resolve()
    config = capability_mcp_config(
        home=home, socket_path=socket_path, dispatch_id=dispatch_id,
    )
    server = config["mcpServers"]["cortex"]
    argv = [server["command"], *server["args"]]
    encoded_config = json.dumps(config, sort_keys=True)
    if capability in encoded_config or CAPABILITY_ENV in encoded_config:
        raise RuntimeError("capability reached serialized MCP config")
    if any(capability in argument for argument in argv):
        raise RuntimeError("capability reached child argv")

    child_env = None
    with issued_capability_environment(
            base_env=base_env, socket_path=socket_path, dispatch_id=dispatch_id,
            capability=capability) as child_env:
        env_names = sorted(child_env)
        payload = "".join(json.dumps(call, separators=(",", ":")) + "\n"
                          for call in _PREFLIGHT_CALLS)
        completed = subprocess.run(
            argv, input=payload, capture_output=True, text=True, check=False,
            env=child_env, timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError("credential-free MCP child failed closed")
        try:
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("credential-free MCP child returned invalid JSON") from exc
        if len(responses) != len(_PREFLIGHT_CALLS):
            raise RuntimeError("credential-free MCP child returned an incomplete transcript")
        initialized = responses[0].get("result", {}).get("serverInfo", {}).get("name") \
            == "cortex-broker"
        health = responses[1].get("result", {}).get("structuredContent", {})
        recall = responses[2].get("result", {}).get("structuredContent", {})
        if not initialized or responses[1].get("result", {}).get("isError") \
                or responses[2].get("result", {}).get("isError"):
            raise RuntimeError("credential-free MCP child reported a dark leg")
        if not isinstance(health, dict) or not isinstance(recall, dict):
            raise RuntimeError("credential-free MCP child returned an invalid structure")
        summary = {
            "initialized": True,
            "health_ready": health.get("ready") is True,
            "health_fields": sorted(health),
            "recall_fields": sorted(recall),
            "recall_field_count": len(recall),
            "environment_names": env_names,
            "serialized_capability": False,
            "argv_capability": False,
            "llm_invoked": False,
        }
    if child_env is None or CAPABILITY_ENV in child_env:
        raise RuntimeError("launcher retained the local capability")
    summary["local_capability_discarded"] = True
    return summary
