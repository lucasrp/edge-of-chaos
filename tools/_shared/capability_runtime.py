"""Capability runtime — unify primitives and CLI wrappers behind one surface."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    CAPABILITIES_CONFIG_FILE,
    CAPABILITIES_STATUS_FILE,
    EDGE_REPO_DIR,
    PRIMITIVES_STATUS_FILE,
    SEARCH_DIR,
    STATE_EVENTS_FILE,
    TOOLS_DIR,
)
from .telemetry import log_capability_invocation, log_capability_probe_completed  # noqa: E402

WINDOW_DAYS = 30
STATUS_ORDER = {
    "broken": 0,
    "drifted": 1,
    "missing": 2,
    "optional-missing": 3,
    "probed": 4,
    "active": 5,
    "available": 6,
    "contract-only": 7,
    "declared": 8,
    "unknown": 9,
}


def _normalize_skill(skill: str | None) -> str:
    raw = str(skill or "").strip().lstrip("/")
    if raw.startswith("ed-"):
        raw = raw[3:]
    return raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _normalize_command(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _load_static_registry() -> list[dict[str, Any]]:
    config_path = CAPABILITIES_CONFIG_FILE
    if not config_path.exists():
        tpl_path = CAPABILITIES_CONFIG_FILE.with_suffix(CAPABILITIES_CONFIG_FILE.suffix + ".tpl")
        if tpl_path.exists():
            config_path = tpl_path
    if not config_path.exists():
        return []
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    items = raw.get("capabilities") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return []
    capabilities: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        capability = dict(item)
        capability["name"] = name
        capability["kind"] = str(item.get("kind") or "external_cli").strip() or "external_cli"
        capability["command"] = _normalize_command(item.get("command"))
        capability["probe"] = _normalize_command(item.get("probe"))
        capability["passthrough"] = bool(item.get("passthrough", True))
        capability["required"] = bool(item.get("required", False))
        skills = item.get("skills") or []
        capability["skills"] = [str(skill).strip() for skill in skills if str(skill).strip()] if isinstance(skills, list) else []
        capabilities.append(capability)
    return capabilities


def _load_primitives_payload() -> dict[str, Any]:
    if PRIMITIVES_STATUS_FILE.exists():
        try:
            return json.loads(PRIMITIVES_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    tool = EDGE_REPO_DIR / "tools" / "edge-primitives"
    result = subprocess.run(
        [sys.executable, str(tool), "status", "--json"],
        cwd=str(EDGE_REPO_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout:
        return {"summary": {}, "sources": []}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"summary": {}, "sources": []}


def _collect_capability_events(now: datetime) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    cutoff = now - timedelta(days=WINDOW_DAYS)
    invocations = defaultdict(lambda: {"invoke_30d": 0, "invoke_fail_30d": 0, "last_invoke_ts": "", "last_exit_code": None})
    probes = defaultdict(lambda: {"last_probe_ts": "", "last_probe_ok": None, "last_probe_exit_code": None})
    for event in _iter_jsonl(STATE_EVENTS_FILE) or []:
        payload = event.get("payload") or {}
        name = str(payload.get("capability") or "").strip()
        if not name:
            continue
        ts = _parse_ts(event.get("ts"))
        if event.get("type") == "CapabilityInvocationObserved":
            if ts is not None and ts >= cutoff:
                bucket = invocations[name]
                bucket["invoke_30d"] += 1
                if not payload.get("ok", False):
                    bucket["invoke_fail_30d"] += 1
                if event.get("ts", "") >= bucket["last_invoke_ts"]:
                    bucket["last_invoke_ts"] = event.get("ts", "")
                    bucket["last_exit_code"] = payload.get("exit_code")
        elif event.get("type") == "CapabilityProbeCompleted":
            bucket = probes[name]
            if event.get("ts", "") >= bucket["last_probe_ts"]:
                bucket["last_probe_ts"] = event.get("ts", "")
                bucket["last_probe_ok"] = payload.get("ok")
                bucket["last_probe_exit_code"] = payload.get("exit_code")
    return invocations, probes


def _resolve_command_head(head: str) -> tuple[str | None, bool]:
    if not head:
        return None, False
    if "/" in head:
        path = Path(head).expanduser()
        return str(path), path.exists() and path.is_file()
    for candidate in (TOOLS_DIR / head, SEARCH_DIR / head, EDGE_REPO_DIR / head):
        if candidate.exists() and candidate.is_file():
            return str(candidate), True
    resolved = shutil.which(head)
    return resolved, resolved is not None


def _resolve_command(command: list[str]) -> tuple[list[str], bool]:
    if not command:
        return [], False
    resolved_head, available = _resolve_command_head(command[0])
    if not resolved_head:
        return list(command), False
    return [resolved_head, *command[1:]], available


def _static_capability_row(item: dict[str, Any], *, invocations: dict[str, Any], probes: dict[str, Any], skill: str | None = None) -> dict[str, Any]:
    command = item.get("command") or []
    resolved_command, available = _resolve_command(command)
    resolved_probe, _ = _resolve_command(item.get("probe") or [])
    name = item["name"]
    probe_event = probes.get(name, {})
    invocation_event = invocations.get(name, {})
    required = bool(item.get("required", False))
    if available and probe_event.get("last_probe_ok") is False:
        effective_status = "broken"
        problems = ["last_probe_failed"]
    elif available:
        effective_status = "available"
        problems = []
    elif required:
        effective_status = "missing"
        problems = ["required_command_missing"]
    else:
        effective_status = "optional-missing"
        problems = ["optional_command_missing"]
    skills = item.get("skills") or []
    normalized_skill = _normalize_skill(skill)
    return {
        "name": name,
        "kind": "external_cli",
        "source": "static_registry",
        "description": str(item.get("description") or "").strip(),
        "required": required,
        "skills": skills,
        "recommended_for_skill": bool(normalized_skill and normalized_skill in skills),
        "configured_command": command,
        "probe": item.get("probe") or [],
        "resolved_command": resolved_command or command,
        "resolved_probe": resolved_probe or (item.get("probe") or []),
        "passthrough": bool(item.get("passthrough", True)),
        "available": available,
        "effective_status": effective_status,
        "problems": problems,
        "invoke_30d": invocation_event.get("invoke_30d", 0),
        "invoke_fail_30d": invocation_event.get("invoke_fail_30d", 0),
        "last_invoke_ts": invocation_event.get("last_invoke_ts", ""),
        "last_invoke_exit_code": invocation_event.get("last_exit_code"),
        "last_probe_ts": probe_event.get("last_probe_ts", ""),
        "last_probe_ok": probe_event.get("last_probe_ok"),
        "last_probe_exit_code": probe_event.get("last_probe_exit_code"),
    }


def _primitive_capability_row(item: dict[str, Any], *, invocations: dict[str, Any], probes: dict[str, Any], skill: str | None = None) -> dict[str, Any]:
    name = f"source.{item.get('name')}"
    probe_event = probes.get(name, {})
    invocation_event = invocations.get(name, {})
    effective_status = str(item.get("effective_status") or "unknown")
    normalized_skill = _normalize_skill(skill)
    return {
        "name": name,
        "kind": "primitive",
        "source": "primitives_status",
        "primitive_name": item.get("name"),
        "description": str(item.get("description") or "").strip(),
        "required": False,
        "skills": ["sources", "research", "discovery", "report", "strategy", "planner", "autonomy"],
        "recommended_for_skill": bool(normalized_skill and normalized_skill in {"sources", "research", "discovery", "report", "strategy", "planner", "autonomy"}),
        "configured_command": [str(item.get("binary_path") or "")] if item.get("binary_path") else [],
        "resolved_command": [str(item.get("binary_path") or "")] if item.get("binary_path") else [],
        "passthrough": True,
        "available": bool(item.get("binary_exists")),
        "effective_status": effective_status,
        "problems": list(item.get("problems") or []),
        "manifest_status": item.get("manifest_status"),
        "probe_status": item.get("probe_status"),
        "meta_exists": bool(item.get("meta_exists")),
        "binary_exists": bool(item.get("binary_exists")),
        "usage_30d": int(item.get("usage_30d", 0) or 0),
        "invoke_30d": invocation_event.get("invoke_30d", 0),
        "invoke_fail_30d": invocation_event.get("invoke_fail_30d", 0),
        "last_invoke_ts": invocation_event.get("last_invoke_ts", ""),
        "last_invoke_exit_code": invocation_event.get("last_exit_code"),
        "last_probe_ts": probe_event.get("last_probe_ts") or item.get("last_probe_ts", ""),
        "last_probe_ok": probe_event.get("last_probe_ok"),
        "last_probe_exit_code": probe_event.get("last_probe_exit_code") or item.get("last_probe_exit_code"),
    }


def build_capability_status(*, skill: str | None = None) -> dict[str, Any]:
    now = _now()
    invocations, probes = _collect_capability_events(now)
    payload = _load_primitives_payload()
    rows: list[dict[str, Any]] = []
    for item in _load_static_registry():
        rows.append(_static_capability_row(item, invocations=invocations, probes=probes, skill=skill))
    for item in payload.get("sources") or []:
        if isinstance(item, dict) and item.get("name"):
            rows.append(_primitive_capability_row(item, invocations=invocations, probes=probes, skill=skill))

    rows.sort(key=lambda row: (STATUS_ORDER.get(str(row.get("effective_status") or "unknown"), 99), str(row.get("name") or "")))
    counts = Counter(str(row.get("effective_status") or "unknown") for row in rows)
    kind_counts = Counter(str(row.get("kind") or "unknown") for row in rows)
    required_missing_total = sum(1 for row in rows if row.get("effective_status") == "missing" and row.get("required"))
    broken_total = counts.get("broken", 0)
    drifted_total = counts.get("drifted", 0)
    optional_missing_total = counts.get("optional-missing", 0)
    if required_missing_total or broken_total:
        health_status = "fail"
    elif drifted_total or optional_missing_total:
        health_status = "warn"
    else:
        health_status = "ok"

    recommended = [
        {
            "name": row["name"],
            "kind": row["kind"],
            "description": row.get("description", ""),
            "effective_status": row.get("effective_status"),
        }
        for row in rows
        if row.get("recommended_for_skill") and row.get("effective_status") in {"available", "active", "probed"}
    ][:5]

    summary = {
        "generated_at": now.isoformat(),
        "window_days": WINDOW_DAYS,
        "capability_total": len(rows),
        "static_total": sum(1 for row in rows if row.get("source") == "static_registry"),
        "primitive_total": sum(1 for row in rows if row.get("source") == "primitives_status"),
        "available_total": sum(1 for row in rows if row.get("effective_status") in {"available", "active", "probed"}),
        "missing_total": counts.get("missing", 0),
        "optional_missing_total": optional_missing_total,
        "broken_total": broken_total,
        "drifted_total": drifted_total,
        "counts_by_effective_status": dict(sorted(counts.items(), key=lambda item: (STATUS_ORDER.get(item[0], 99), item[0]))),
        "counts_by_kind": dict(sorted(kind_counts.items())),
        "health_status": health_status,
        "recommended_for_skill_total": len(recommended),
        "skill": skill or "",
    }
    status_payload = {
        "generated_at": now.isoformat(),
        "repo_root": str(EDGE_REPO_DIR),
        "config_path": str(CAPABILITIES_CONFIG_FILE),
        "output_path": str(CAPABILITIES_STATUS_FILE),
        "summary": summary,
        "recommended": recommended,
        "capabilities": rows,
    }
    CAPABILITIES_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAPABILITIES_STATUS_FILE.write_text(json.dumps(status_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status_payload


def get_capability(name: str, *, skill: str | None = None) -> dict[str, Any] | None:
    payload = build_capability_status(skill=skill)
    for item in payload.get("capabilities") or []:
        if item.get("name") == name:
            return item
    return None


def invoke_capability(name: str, argv: list[str], *, skill: str | None = None) -> subprocess.CompletedProcess[str]:
    capability = get_capability(name, skill=skill)
    if capability is None:
        raise RuntimeError(f"unknown capability: {name}")
    command = list(capability.get("resolved_command") or capability.get("configured_command") or [])
    if not command:
        raise RuntimeError(f"capability has no command: {name}")
    effective_status = str(capability.get("effective_status") or "unknown")
    if effective_status in {"missing", "optional-missing", "contract-only", "declared"}:
        raise RuntimeError(f"capability unavailable: {name} ({effective_status})")
    final_cmd = command + (argv if capability.get("passthrough", True) else [])
    started = time.monotonic()
    result = subprocess.run(final_cmd, cwd=str(EDGE_REPO_DIR), capture_output=True, text=True)
    dt_ms = int((time.monotonic() - started) * 1000)
    log_capability_invocation(
        name,
        kind=str(capability.get("kind") or "unknown"),
        command=final_cmd,
        exit_code=result.returncode,
        ok=result.returncode == 0,
        latency_ms=dt_ms,
        skill=skill or "",
    )
    return result


def probe_capability(name: str, *, skill: str | None = None) -> subprocess.CompletedProcess[str]:
    capability = get_capability(name, skill=skill)
    if capability is None:
        raise RuntimeError(f"unknown capability: {name}")
    if capability.get("kind") == "primitive":
        command = list(capability.get("resolved_command") or [])
        if not command:
            raise RuntimeError(f"primitive capability unavailable: {name}")
        probe_cmd = command + ["--help"]
    else:
        probe_cmd = list(capability.get("resolved_command") or capability.get("configured_command") or [])
        resolved_probe = list(_normalize_command(capability.get("resolved_probe")))
        configured_probe = list(_normalize_command(capability.get("probe")))
        if resolved_probe:
            probe_cmd = resolved_probe
        elif configured_probe:
            probe_cmd = configured_probe
    if not probe_cmd:
        raise RuntimeError(f"capability has no probe command: {name}")
    started = time.monotonic()
    result = subprocess.run(probe_cmd, cwd=str(EDGE_REPO_DIR), capture_output=True, text=True)
    dt_ms = int((time.monotonic() - started) * 1000)
    log_capability_probe_completed(
        name,
        kind=str(capability.get("kind") or "unknown"),
        command=probe_cmd,
        exit_code=result.returncode,
        ok=result.returncode == 0,
        latency_ms=dt_ms,
        skill=skill or "",
    )
    return result
