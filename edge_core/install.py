from __future__ import annotations

import os
from pathlib import Path

from .config import RuntimeConfig, ensure_runtime_dirs, resolve_agent_config_path


def render(config: RuntimeConfig) -> list[Path]:
    ensure_runtime_dirs(config)
    rendered = config.root / "config" / "mentor-runtime.yaml"
    rendered.write_text(
        "\n".join(
            [
                f"name: {config.name}",
                f"codename: {config.codename}",
                f"language: {config.language}",
                f"root: {config.root}",
                f"reports_dir: {config.reports_dir}",
                f"threads_dir: {config.threads_dir}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return [rendered]


def apply(config: RuntimeConfig) -> list[Path]:
    ensure_runtime_dirs(config)
    source = config.root / "tools" / "edge"
    os.chmod(source, 0o755)
    local_bin = config.root / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    target = local_bin / "edge"
    target.write_text(
        f"#!/usr/bin/env sh\nexec python3 {source} \"$@\"\n",
        encoding="utf-8",
    )
    os.chmod(target, 0o755)
    written = [target]
    if os.environ.get("EDGE_INSTALL_GLOBAL") == "1":
        global_bin = Path.home() / ".local" / "bin"
        global_bin.mkdir(parents=True, exist_ok=True)
        global_target = global_bin / "edge"
        if global_target.exists() or global_target.is_symlink():
            global_target.unlink()
        global_target.symlink_to(source)
        written.append(global_target)
    return written


def doctor(config: RuntimeConfig) -> tuple[bool, list[str]]:
    checks: list[str] = []
    ok = True
    agent_path = resolve_agent_config_path(config.root)
    if not agent_path.exists():
        ok = False
        checks.append("missing agent config")
    else:
        checks.append(f"ok: agent config -> {agent_path}")
    for path in [config.state_dir, config.reports_dir, config.root / "blog"]:
        if not path.exists():
            ok = False
            checks.append(f"missing runtime directory: {path}")
        else:
            checks.append(f"ok: {path}")
    if not (config.root / "tools" / "edge").exists():
        ok = False
        checks.append("missing tools/edge")
    else:
        checks.append("ok: tools/edge")
    return ok, checks
