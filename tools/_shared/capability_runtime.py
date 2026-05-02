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
    SECRETS_DIR,
    SOURCES_MANIFEST_FILE,
    STATE_EVENTS_FILE,
    TOOLS_DIR,
)
from .telemetry import log_capability_invocation, log_capability_probe_completed  # noqa: E402

WINDOW_DAYS = 30
STATUS_ORDER = {
    "broken": 0,
    "degraded": 1,
    "probed": 2,
    "active": 3,
    "available": 4,
    "unknown": 5,
}

INTEGRATION_CATALOG: dict[str, dict[str, Any]] = {
    "assertia-db": {
        "name": "assertia_db",
        "label": "Assertia DB",
        "kind": "product_usage_database",
        "roles": ["search", "database"],
        "candidate_capabilities": [],
    },
    "bob": {
        "name": "bob",
        "label": "Bob",
        "kind": "instance_access",
        "roles": [],
        "candidate_capabilities": [],
    },
    "digitalocean": {
        "name": "digitalocean",
        "label": "DigitalOcean",
        "kind": "cloud_infrastructure",
        "roles": [],
        "candidate_capabilities": [],
    },
    "exa": {
        "name": "exa",
        "label": "Exa",
        "kind": "search_engine",
        "roles": ["search", "external_search"],
        "candidate_capabilities": ["sources.aggregate"],
    },
    "grafana-loki": {
        "name": "grafana",
        "label": "Grafana Loki",
        "kind": "observability_database",
        "roles": ["search", "observability"],
        "candidate_capabilities": [],
    },
    "joao": {
        "name": "joao",
        "label": "Joao",
        "kind": "instance_access",
        "roles": [],
        "candidate_capabilities": [],
    },
    "keys": {
        "name": "legacy_keys_bundle",
        "label": "Legacy Keys Bundle",
        "kind": "shared_secret_bundle",
        "roles": [],
        "candidate_capabilities": [],
    },
    "moltbook": {
        "name": "moltbook",
        "label": "Moltbook",
        "kind": "social_platform",
        "roles": ["publish"],
        "candidate_capabilities": [],
    },
    "meta": {
        "name": "meta",
        "label": "Meta Marketing API",
        "kind": "ads_platform",
        "roles": ["signals", "search", "external_context"],
        "candidate_capabilities": ["source.meta"],
    },
    "netlify": {
        "name": "netlify",
        "label": "Netlify",
        "kind": "deployment_platform",
        "roles": [],
        "candidate_capabilities": [],
    },
    "openai": {
        "name": "openai",
        "label": "OpenAI",
        "kind": "llm_provider",
        "roles": [],
        "candidate_capabilities": [],
    },
    "slack": {
        "name": "slack",
        "label": "Slack",
        "kind": "communication_platform",
        "roles": [],
        "candidate_capabilities": [],
    },
    "vultr": {
        "name": "vultr",
        "label": "Vultr",
        "kind": "cloud_infrastructure",
        "roles": [],
        "candidate_capabilities": [],
    },
    "x-api": {
        "name": "x",
        "label": "X API",
        "kind": "social_source",
        "roles": ["search", "external_search"],
        "candidate_capabilities": ["sources.aggregate"],
    },
    "xai": {
        "name": "xai",
        "label": "xAI",
        "kind": "llm_provider",
        "roles": [],
        "candidate_capabilities": [],
    },
}

AGGREGATE_SOURCE_ALIASES = {
    "claude-web": "claude_builtin",
    "claude_web": "claude_builtin",
    "claude": "claude_builtin",
    "hackernews": "hn",
    "hacker-news": "hn",
    "semanticscholar": "semantic_scholar",
    "semantic-scholar": "semantic_scholar",
    "semscholar": "semantic_scholar",
    "huggingface": "hf_papers",
    "hf": "hf_papers",
}
AGGREGATE_SOURCE_PROVIDERS = {
    "arxiv",
    "claude_builtin",
    "exa",
    "github",
    "hf_papers",
    "hn",
    "reddit",
    "semantic_scholar",
    "x",
}
BOUND_STATUSES = {"available", "active", "probed"}
DEGRADED_STATUSES = {"degraded", "broken"}


def _normalize_effective_status(value: Any) -> str:
    status = str(value or "unknown").strip() or "unknown"
    if status in {"missing", "optional-missing", "drifted", "contract-only", "declared"}:
        return "degraded"
    return status


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


def _normalize_roles(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    roles: list[str] = []
    for item in value:
        role = str(item or "").strip()
        if role and role not in roles:
            roles.append(role)
    return roles


def _parse_env_file(path: Path) -> list[str]:
    vars_present: list[str] = []
    if not path.exists():
        return vars_present
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return vars_present
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            vars_present.append(key)
    return sorted(set(vars_present))


def _canonical_source_provider(name: str) -> str:
    key = str(name or "").strip().lower().replace(" ", "_")
    return AGGREGATE_SOURCE_ALIASES.get(key, key)


def _load_sources_manifest() -> list[dict[str, Any]]:
    if not SOURCES_MANIFEST_FILE.exists():
        return []
    try:
        raw = yaml.safe_load(SOURCES_MANIFEST_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    items = raw.get("sources") if isinstance(raw, dict) else []
    return [item for item in items if isinstance(item, dict) and str(item.get("name") or "").strip()] if isinstance(items, list) else []


def _load_static_registry() -> list[dict[str, Any]]:
    tpl_path = CAPABILITIES_CONFIG_FILE.with_suffix(CAPABILITIES_CONFIG_FILE.suffix + ".tpl")

    def load_items(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = raw.get("capabilities") if isinstance(raw, dict) else []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    merged: dict[str, dict[str, Any]] = {}
    for item in load_items(tpl_path):
        name = str(item.get("name") or "").strip()
        if name:
            merged[name] = dict(item)
    for item in load_items(CAPABILITIES_CONFIG_FILE):
        name = str(item.get("name") or "").strip()
        if name:
            merged[name] = dict(item)
    capabilities: list[dict[str, Any]] = []
    for item in merged.values():
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
        capability["roles"] = _normalize_roles(item.get("roles"))
        capability["search_adapter"] = str(item.get("search_adapter") or "").strip()
        capability["search_scope"] = str(item.get("search_scope") or "").strip()
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
    else:
        effective_status = "degraded"
        problems = ["required_command_missing" if required else "optional_command_missing"]
    skills = item.get("skills") or []
    normalized_skill = _normalize_skill(skill)
    return {
        "name": name,
        "kind": "external_cli",
        "source": "static_registry",
        "description": str(item.get("description") or "").strip(),
        "required": required,
        "roles": list(item.get("roles") or []),
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
    effective_status = _normalize_effective_status(item.get("effective_status"))
    normalized_skill = _normalize_skill(skill)
    roles = _normalize_roles(item.get("roles")) or ["search"]
    if "source" not in roles:
        roles.append("source")
    return {
        "name": name,
        "kind": "primitive",
        "source": "primitives_status",
        "primitive_name": item.get("name"),
        "description": str(item.get("description") or "").strip(),
        "required": False,
        "roles": roles,
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
    required_degraded_total = sum(1 for row in rows if row.get("effective_status") == "degraded" and row.get("required"))
    broken_total = counts.get("broken", 0)
    degraded_total = counts.get("degraded", 0)
    if required_degraded_total or broken_total:
        health_status = "fail"
    elif degraded_total:
        health_status = "degraded"
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
        "degraded_total": degraded_total,
        "required_degraded_total": required_degraded_total,
        "optional_degraded_total": max(0, degraded_total - required_degraded_total),
        "broken_total": broken_total,
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


def build_configured_integrations(*, skill: str | None = None) -> dict[str, Any]:
    capability_payload = build_capability_status(skill=skill)
    capability_rows = {
        str(item.get("name") or "").strip(): item
        for item in (capability_payload.get("capabilities") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    def _binding_status(candidate_capabilities: list[str]) -> str:
        if not candidate_capabilities:
            return "not_applicable"
        matched = [capability_rows.get(name) for name in candidate_capabilities if capability_rows.get(name)]
        if not matched:
            return "absent"
        statuses = {str(item.get("effective_status") or "unknown") for item in matched if isinstance(item, dict)}
        if statuses & {"available", "active", "probed"}:
            return "present"
        if statuses & {"degraded", "broken"}:
            return "degraded"
        return "absent"

    integrations: list[dict[str, Any]] = []
    if SECRETS_DIR.exists():
        for path in sorted(SECRETS_DIR.glob("*.env")):
            secret_key = path.stem
            catalog_entry = INTEGRATION_CATALOG.get(secret_key, {})
            candidate_capabilities = list(catalog_entry.get("candidate_capabilities") or [])
            integration = {
                "name": str(catalog_entry.get("name") or secret_key.replace("-", "_")),
                "label": str(catalog_entry.get("label") or path.stem),
                "kind": str(catalog_entry.get("kind") or "external_integration"),
                "roles": list(catalog_entry.get("roles") or []),
                "status": "configured",
                "secret_file": path.name,
                "vars_present": _parse_env_file(path),
                "candidate_capabilities": candidate_capabilities,
            }
            integration["capability_binding"] = _binding_status(candidate_capabilities)
            integrations.append(integration)

    integrations.sort(key=lambda item: (item.get("capability_binding") != "absent", str(item.get("name") or "")))
    unbound = [
        item
        for item in integrations
        if item.get("capability_binding") == "absent" and item.get("candidate_capabilities")
    ]
    summary = {
        "integration_total": len(integrations),
        "unbound_total": len(unbound),
        "bound_total": sum(1 for item in integrations if item.get("capability_binding") == "present"),
        "degraded_total": sum(1 for item in integrations if item.get("capability_binding") == "degraded"),
        "not_applicable_total": sum(1 for item in integrations if item.get("capability_binding") == "not_applicable"),
    }
    return {
        "summary": summary,
        "configured_integrations": integrations,
        "unbound_integrations": unbound,
    }


def build_source_bindings(*, skill: str | None = None) -> dict[str, Any]:
    """Resolve runtime-declared source intents into executable capability bindings."""
    now = _now()
    capability_payload = build_capability_status(skill=skill)
    capability_rows = {
        str(item.get("name") or "").strip(): item
        for item in (capability_payload.get("capabilities") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    aggregate = capability_rows.get("sources.aggregate") or {}
    aggregate_status = str(aggregate.get("effective_status") or "unknown")
    aggregate_available = aggregate_status in BOUND_STATUSES
    sources = _load_sources_manifest()
    bindings: list[dict[str, Any]] = []

    for source in sources:
        source_name = str(source.get("name") or "").strip()
        if not source_name:
            continue
        roles = _normalize_roles(source.get("roles"))
        primary = bool(source.get("primary", False))
        primitive_name = f"source.{source_name}"
        primitive = capability_rows.get(primitive_name) or {}
        primitive_status = str(primitive.get("effective_status") or "unknown")
        provider = _canonical_source_provider(source_name)
        source_roles_search = not roles or "search" in roles or "source" in roles

        binding_status = "absent"
        binding_mode = "none"
        capability = primitive_name
        problems = list(primitive.get("problems") or [])
        evidence: dict[str, Any] = {
            "primitive_status": primitive_status,
            "aggregate_status": aggregate_status,
            "manifest_status": source.get("status") or "",
        }

        if source_roles_search and provider in AGGREGATE_SOURCE_PROVIDERS and aggregate_available:
            binding_status = "present"
            binding_mode = "sources.aggregate"
            capability = "sources.aggregate"
            evidence["aggregate_provider"] = provider
        elif primitive_status in BOUND_STATUSES:
            binding_status = "present"
            binding_mode = "primitive"
        elif primitive_status in DEGRADED_STATUSES:
            binding_status = "degraded"
            binding_mode = "primitive"
        else:
            binding_status = "absent"
            binding_mode = "primitive" if primitive else "none"
            if "declared_unbound" not in problems:
                problems.append("declared_unbound")

        warning = ""
        if binding_status == "absent":
            warning = "configured_integration_without_binding"
        elif binding_status == "degraded":
            warning = "configured_integration_binding_degraded"

        bindings.append(
            {
                "source": source_name,
                "description": str(source.get("description") or ""),
                "roles": roles,
                "primary": primary,
                "capability": capability,
                "binding_status": binding_status,
                "binding_mode": binding_mode,
                "problems": problems,
                "warning": warning,
                "evidence": evidence,
            }
        )

    counts = Counter(item["binding_status"] for item in bindings)
    unbound = [item for item in bindings if item.get("binding_status") == "absent"]
    degraded = [item for item in bindings if item.get("binding_status") == "degraded"]
    summary = {
        "generated_at": now.isoformat(),
        "source_total": len(bindings),
        "bound_total": counts.get("present", 0),
        "unbound_total": counts.get("absent", 0),
        "degraded_total": counts.get("degraded", 0),
        "counts_by_binding_status": dict(sorted(counts.items())),
        "health_status": "fail" if unbound else "degraded" if degraded else "ok",
        "source_path": str(SOURCES_MANIFEST_FILE),
    }
    return {
        "summary": summary,
        "bindings": bindings,
        "unbound_source_bindings": unbound,
        "degraded_source_bindings": degraded,
        "warnings": [
            {
                "source": item["source"],
                "warning": item["warning"],
                "capability": item["capability"],
                "problems": item.get("problems") or [],
            }
            for item in bindings
            if item.get("warning")
        ],
    }


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
    if effective_status == "degraded":
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
