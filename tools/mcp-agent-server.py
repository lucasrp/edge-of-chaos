#!/usr/bin/env python3
"""MCP stdio server exposing agent primitives as tools.

Reads sources-manifest.yaml + libexec/<codename>/*.meta.yaml to discover
primitives, registers each as an MCP tool via FastMCP. Invocation runs
the underlying script via subprocess and returns its stdout.

Environment: EDGE_DIR (default: ~/edge)
Part of issue #133.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

EDGE_DIR = Path(os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))


def _read_codename() -> str:
    agent_yaml = EDGE_DIR / "agent.yaml"
    if agent_yaml.exists():
        try:
            cfg = yaml.safe_load(agent_yaml.read_text())
            return cfg.get("codename", cfg.get("name", "ed"))
        except Exception:
            pass
    return "ed"


def _load_manifest() -> list[dict]:
    manifest = EDGE_DIR / "state" / "sources-manifest.yaml"
    if not manifest.exists():
        return []
    try:
        data = yaml.safe_load(manifest.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_meta(meta_path: Path) -> dict:
    if not meta_path.exists():
        return {}
    try:
        return yaml.safe_load(meta_path.read_text()) or {}
    except Exception:
        return {}


def _build_env() -> dict:
    """Build env dict with EDGE_DIR and secrets loaded."""
    env = os.environ.copy()
    env["EDGE_DIR"] = str(EDGE_DIR)
    keys_env = EDGE_DIR / "secrets" / "keys.env"
    if keys_env.exists():
        try:
            for line in keys_env.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        except Exception:
            pass
    return env


def _run_primitive(primitive_path: str, args: list[str], env: dict) -> str:
    try:
        r = subprocess.run(
            [primitive_path] + args,
            capture_output=True, text=True, timeout=120,
            env=env, cwd=str(EDGE_DIR),
        )
        output = r.stdout.strip()
        if r.returncode != 0 and not output:
            output = json.dumps({"ok": False, "error": r.stderr.strip() or f"exit {r.returncode}", "code": r.returncode})
        return output
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "timeout (120s)", "code": -1})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc), "code": -1})


def _register_tool(mcp_server, name: str, description: str, prim_path: str, env: dict):
    """Register a single primitive as an MCP tool."""
    async def handler(query: str, operation: str = "search") -> str:
        args = [operation, query] if operation else [query]
        return _run_primitive(prim_path, args, env)
    handler.__name__ = name.replace("-", "_")
    handler.__doc__ = description
    mcp_server.tool(name=name, description=description)(handler)


def main():
    codename = _read_codename()
    libexec_dir = EDGE_DIR / "libexec" / codename
    manifest = _load_manifest()
    env = _build_env()

    mcp = FastMCP(
        "edge-agent",
        instructions="Agent primitives for external data sources. Each tool wraps a CLI primitive that returns JSON.",
    )

    registered = 0
    seen: set[str] = set()

    # Register from manifest (primary source of truth)
    for entry in manifest:
        name = entry.get("name", "")
        status = entry.get("status", "")
        if not name or status not in ("active", "contract-only"):
            continue
        prim_path = libexec_dir / name
        if not prim_path.exists():
            continue
        meta = _load_meta(libexec_dir / f"{name}.meta.yaml")
        desc = meta.get("description", entry.get("description", name))
        _register_tool(mcp, name, desc, str(prim_path), env)
        seen.add(name)
        registered += 1

    # Also pick up executables with .meta.yaml not in manifest
    if libexec_dir.exists():
        for item in sorted(libexec_dir.iterdir()):
            if item.name in seen or item.suffix or not item.is_file():
                continue
            if not os.access(item, os.X_OK):
                continue
            meta = _load_meta(libexec_dir / f"{item.name}.meta.yaml")
            if not meta:
                continue
            _register_tool(mcp, item.name, meta.get("description", item.name), str(item), env)
            registered += 1

    print(f"edge-agent MCP: {registered} tools from libexec/{codename}/", file=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
