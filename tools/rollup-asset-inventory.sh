#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/paths.sh
source "$SCRIPT_DIR/../config/paths.sh"

python3 - "$@" <<'PY'
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KEY_GROUPS = (
    ("whatsapp", ("WA_", "WHATSAPP_")),
    ("meta", ("META_", "FB_", "FACEBOOK_")),
    ("openai", ("OPENAI_",)),
    ("exa", ("EXA_",)),
    ("github", ("GITHUB_", "GH_")),
    ("google", ("GOOGLE_", "GA4_", "GTM_")),
    ("cloudflare", ("CLOUDFLARE_", "CF_")),
    ("x_twitter", ("X_", "TWITTER_")),
    ("slack", ("SLACK_",)),
    ("vultr", ("VULTR_",)),
    ("telegram", ("TELEGRAM_",)),
    ("publer", ("PUBLER_",)),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 4, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 124, "", str(exc)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def split_env_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    paths = []
    for raw in value.split(":"):
        text = os.path.expandvars(os.path.expanduser(raw.strip()))
        if text:
            paths.append(Path(text))
    return paths


def rel_home(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(Path.home().resolve()))
    except Exception:
        return str(path)


def parse_key_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    names: set[str] = set()
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return sorted(names)


def group_key(name: str) -> str:
    upper = name.upper()
    for group, prefixes in KEY_GROUPS:
        if upper.startswith(prefixes):
            return group
    return "other"


def grouped_keys(names: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for name in names:
        grouped.setdefault(group_key(name), set()).add(name)
    return {group: sorted(values) for group, values in sorted(grouped.items())}


def parse_ssh_config(path: Path) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return hosts
    active: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts:
            continue
        key = parts[0].lower()
        if key == "host":
            active = []
            for name in parts[1:]:
                if any(ch in name for ch in "*?[]"):
                    continue
                hosts.setdefault(
                    name,
                    {
                        "ssh": True,
                        "role": "remote",
                        "source": str(path),
                        "ssh_status": "discovered",
                        "services": [],
                        "databases": [],
                        "ports": [],
                        "repos": [],
                        "keys": [],
                    },
                )
                active.append(name)
        elif key == "hostname":
            for name in active:
                hosts.setdefault(name, {})["ip"] = parts[1] if len(parts) > 1 else ""
        elif key == "user":
            for name in active:
                hosts.setdefault(name, {})["user"] = parts[1] if len(parts) > 1 else ""
    return hosts


def git_remote(path: Path) -> str:
    code, stdout, _ = run(["git", "remote", "get-url", "origin"], cwd=path, timeout=2)
    return stdout if code == 0 else ""


def git_branch(path: Path) -> str:
    code, stdout, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, timeout=2)
    return stdout if code == 0 else ""


def discover_repos(repo_root: Path) -> list[dict[str, Any]]:
    roots = split_env_paths(os.environ.get("EDGE_ASSET_REPO_SCAN_ROOTS"))
    if not roots:
        roots = [repo_root, *[item for item in Path.home().iterdir() if item.is_dir()][:40]]
    repos: dict[str, dict[str, Any]] = {}
    for root in roots:
        root = root.expanduser()
        candidates = [root]
        if root.is_dir() and not (root / ".git").exists():
            try:
                candidates.extend([item for item in root.iterdir() if item.is_dir()][:80])
            except Exception:
                pass
        for candidate in candidates:
            if not (candidate / ".git").exists():
                continue
            resolved = str(candidate.resolve())
            repos[resolved] = {
                "path": rel_home(candidate),
                "remote": git_remote(candidate),
                "branch": git_branch(candidate),
            }
    return sorted(repos.values(), key=lambda item: item["path"])


def sqlite_tables(path: Path) -> list[str]:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            return [str(row[0]) for row in rows[:80]]
        finally:
            conn.close()
    except Exception:
        return []


def discover_databases(state_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    roots = split_env_paths(os.environ.get("EDGE_ASSET_DB_SCAN_ROOTS"))
    if not roots:
        roots = [state_dir, Path.home() / "data", repo_root / "db"]
    seen: set[str] = set()
    databases: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            candidates = list(root.rglob("*.db"))[:120] if root.is_dir() else [root]
        except Exception:
            candidates = []
        for db_path in candidates:
            try:
                resolved = str(db_path.resolve())
            except Exception:
                resolved = str(db_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            databases.append({"path": rel_home(db_path), "tables": sqlite_tables(db_path)})
    return sorted(databases, key=lambda item: item["path"])


def parse_ss_ports(stdout: str) -> list[dict[str, Any]]:
    ports: dict[int, dict[str, Any]] = {}
    for line in stdout.splitlines():
        match = re.search(r":(\d+)\s", line)
        if not match:
            continue
        port = int(match.group(1))
        proc = ""
        proc_match = re.search(r'users:\(\("([^"]+)"', line)
        if proc_match:
            proc = proc_match.group(1)
        ports[port] = {"port": port, "process": proc}
    return [ports[key] for key in sorted(ports)]


def local_ports() -> list[dict[str, Any]]:
    code, stdout, _ = run(["ss", "-tlnp"], timeout=2)
    return parse_ss_ports(stdout) if code == 0 else []


REMOTE_CODE = r'''
import json, os, re, sqlite3, subprocess
from pathlib import Path

def run(cmd, timeout=4):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:
        return 124, "", str(exc)

def key_names(paths):
    out = set()
    pat = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for path in paths:
        p = Path(os.path.expanduser(path))
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = pat.match(line)
            if m:
                out.add(m.group(1))
    return sorted(out)

def tables(path):
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()[:80]]
        finally:
            c.close()
    except Exception:
        return []

def dbs():
    roots = [Path.home() / "edge", Path.home() / "data"]
    seen = set()
    out = []
    for root in roots:
        if not root.exists():
            continue
        for p in list(root.rglob("*.db"))[:160]:
            s = str(p)
            if s in seen:
                continue
            seen.add(s)
            out.append({"path": s, "tables": tables(p)})
    return out

def services():
    code, stdout, _ = run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"], timeout=4)
    out = []
    if code == 0:
        for line in stdout.splitlines()[:120]:
            parts = line.split()
            if parts:
                out.append({"name": parts[0].removesuffix(".service"), "systemd": parts[0], "type": "systemd"})
    return out

def ports():
    code, stdout, _ = run(["ss", "-tlnp"], timeout=3)
    out = []
    if code == 0:
        for line in stdout.splitlines():
            m = re.search(r":(\d+)\s", line)
            if not m:
                continue
            proc = ""
            pm = re.search(r'users:\(\("([^"]+)"', line)
            if pm:
                proc = pm.group(1)
            out.append({"port": int(m.group(1)), "process": proc})
    return sorted({item["port"]: item for item in out}.values(), key=lambda item: item["port"])

print(json.dumps({
    "ssh_status": "ok",
    "services": services(),
    "ports": ports(),
    "databases": dbs(),
    "keys": key_names(["~/edge/secrets/keys.env", "~/secrets/keys.env"]),
}, ensure_ascii=False))
'''


def scan_remote(host: str, timeout: int) -> tuple[dict[str, Any] | None, str]:
    if not shutil_which("ssh"):
        return None, "ssh_not_found"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={max(1, timeout)}", host, "python3", "-"]
    code, stdout, stderr = run(cmd, timeout=max(3, timeout + 3), input_text=REMOTE_CODE)
    if code != 0 or not stdout:
        return None, stderr or stdout or f"ssh exited {code}"
    try:
        payload = json.loads(stdout)
    except Exception as exc:
        return None, f"invalid remote json: {exc}"
    return payload if isinstance(payload, dict) else None, ""


def shutil_which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        path = Path(directory) / name
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def merge_key_names(payload: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for values in (payload.get("keys") or {}).values():
        if isinstance(values, list):
            names.update(str(item) for item in values)
    for host in (payload.get("hosts") or {}).values():
        for name in host.get("keys") or []:
            names.add(str(name))
    return sorted(names)


def iter_text(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        if value.strip():
            out.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            out.extend(iter_text(item))
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(iter_text(item))
    return out


def operator_pressure_asset_hints(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "state" / "operator-pressure" / "hot-digest.json"
    payload = read_json(path)
    texts = iter_text(payload)
    joined = "\n".join(texts)
    keys = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", joined)))
    ports = sorted({int(item) for item in re.findall(r"\b(?:porta|port)\s+(\d{2,5})\b", joined, flags=re.I)})
    hosts = sorted(set(re.findall(r"\bssh\s+([a-z][a-z0-9-]{2,})\b", joined, flags=re.I)))
    databases = sorted(set(re.findall(r"\b[\w./~-]+\.db\b", joined)))
    return {
        "source_path": str(path),
        "keys": keys,
        "ports": ports,
        "hosts": hosts,
        "databases": databases,
    }


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(os.environ["EDGE_REPO_DIR"]).expanduser()
    state_dir = Path(os.environ["EDGE_STATE_DIR"]).expanduser()
    output = Path(args.output or os.environ.get("ASSET_INVENTORY_FILE") or state_dir / "state" / "asset-inventory.json").expanduser()
    previous = read_json(output)
    generated_at = now_iso()

    key_names = parse_key_names(repo_root / "secrets" / "keys.env")
    operator_updates = operator_pressure_asset_hints(state_dir)
    key_names.extend(operator_updates.get("keys") or [])
    hosts = {
        "localhost": {
            "ssh": False,
            "role": "dev",
            "services": [],
            "ports": local_ports(),
            "databases": discover_databases(state_dir, repo_root),
            "repos": discover_repos(repo_root),
            "keys": key_names,
        }
    }
    repos = {}
    for repo in hosts["localhost"]["repos"]:
        remote = str(repo.get("remote") or repo.get("path") or "")
        repos[remote or repo["path"]] = repo

    ssh_hosts = parse_ssh_config(Path.home() / ".ssh" / "config")
    forced_hosts = [item.strip() for item in args.hosts.split(",") if item.strip()] if args.hosts else []
    forced_hosts.extend(str(item) for item in operator_updates.get("hosts") or [])
    for host in forced_hosts:
        ssh_hosts.setdefault(host, {"ssh": True, "role": "remote", "ssh_status": "discovered", "services": [], "databases": [], "ports": [], "repos": [], "keys": []})

    last_ssh_success = dict(previous.get("last_ssh_success") or {})
    ssh_errors: dict[str, str] = {}
    previous_hosts = previous.get("hosts") if isinstance(previous.get("hosts"), dict) else {}
    for host, base in sorted(ssh_hosts.items()):
        if args.no_ssh:
            cached = previous_hosts.get(host) if isinstance(previous_hosts.get(host), dict) else {}
            merged = {**base, **cached} if cached else dict(base)
            merged["ssh"] = True
            merged["ssh_status"] = "skipped"
            hosts[host] = merged
            continue
        remote_payload, error = scan_remote(host, args.ssh_timeout)
        if remote_payload:
            merged = dict(base)
            merged.update(remote_payload)
            merged["ssh"] = True
            merged["role"] = base.get("role") or "remote"
            merged["last_seen_at"] = generated_at
            hosts[host] = merged
            last_ssh_success[host] = generated_at
            key_names.extend(str(name) for name in merged.get("keys") or [])
        else:
            cached = previous_hosts.get(host) if isinstance(previous_hosts.get(host), dict) else {}
            merged = {**base, **cached} if cached else dict(base)
            merged["ssh"] = True
            merged["ssh_status"] = "stale_cached" if cached else "failed"
            merged["last_error"] = error
            hosts[host] = merged
            ssh_errors[host] = error

    key_names.extend(merge_key_names({"hosts": hosts, "keys": previous.get("keys") or {}}))
    keys = grouped_keys(sorted(set(key_names)))

    service_total = sum(len(host.get("services") or []) for host in hosts.values())
    database_total = sum(len(host.get("databases") or []) for host in hosts.values())
    repo_total = sum(len(host.get("repos") or []) for host in hosts.values())
    stale_host_total = sum(1 for host in hosts.values() if str(host.get("ssh_status") or "") in {"failed", "stale_cached"})
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source": "rollup-asset-inventory.sh",
        "summary": {
            "host_total": len(hosts),
            "ssh_host_total": sum(1 for host in hosts.values() if host.get("ssh")),
            "service_total": service_total,
            "database_total": database_total,
            "repo_total": repo_total,
            "key_total": sum(len(values) for values in keys.values()),
            "stale_host_total": stale_host_total,
        },
        "last_ssh_success": last_ssh_success,
        "ssh_errors": ssh_errors,
        "operator_pressure_updates": operator_updates,
        "hosts": hosts,
        "keys": keys,
        "repos": repos,
        "security": {
            "stores_secret_values": False,
            "keys_are_names_only": True,
            "indexed_in_search": False,
        },
    }
    write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build edge asset inventory without storing secret values")
    parser.add_argument("--output", help="Output JSON path (default: ASSET_INVENTORY_FILE)")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    parser.add_argument("--quiet", action="store_true", help="Suppress human summary")
    parser.add_argument("--no-ssh", action="store_true", help="Skip remote SSH probes and preserve cached hosts")
    parser.add_argument("--hosts", default=os.environ.get("EDGE_ASSET_SSH_HOSTS", ""), help="Comma-separated SSH hosts to scan")
    parser.add_argument("--ssh-timeout", type=int, default=int(os.environ.get("EDGE_ASSET_SSH_TIMEOUT", "5")), help="Per-host SSH connect timeout")
    args = parser.parse_args()

    payload = build_inventory(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    elif not args.quiet:
        summary = payload.get("summary") or {}
        print(
            "asset-inventory: "
            f"hosts={summary.get('host_total', 0)} "
            f"services={summary.get('service_total', 0)} "
            f"dbs={summary.get('database_total', 0)} "
            f"repos={summary.get('repo_total', 0)} "
            f"keys={summary.get('key_total', 0)} "
            f"stale_hosts={summary.get('stale_host_total', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
