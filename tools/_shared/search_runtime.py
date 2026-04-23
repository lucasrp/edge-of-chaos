"""Shared runtime policy for web search routing and fallback unlocks."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import CONFIG_DIR, RUNTIME_PROTOCOL_DIR, SECRETS_DIR  # noqa: E402

DEFAULT_SEARCH_POLICY = {
    "builtin_web_search": False,
    "web_provider": "exa",
    "web_fallback": "claude_web",
}
DEFAULT_FALLBACK_TTL_SECONDS = 900


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _features_path() -> Path:
    runtime_path = CONFIG_DIR / "features.yaml"
    if runtime_path.exists():
        return runtime_path
    return CONFIG_DIR / "features.yaml.tpl"


def _allowance_path() -> Path:
    return RUNTIME_PROTOCOL_DIR / "web-search-fallback.json"


def load_search_policy() -> dict[str, Any]:
    path = _features_path()
    policy = dict(DEFAULT_SEARCH_POLICY)
    policy["source_path"] = str(path)
    if yaml is None or not path.exists():
        return policy
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return policy
    if not isinstance(data, dict):
        return policy
    search_cfg = data.get("search") or {}
    if not isinstance(search_cfg, dict):
        return policy
    policy["builtin_web_search"] = _parse_bool(
        search_cfg.get("builtin_web_search"),
        DEFAULT_SEARCH_POLICY["builtin_web_search"],
    )
    policy["web_provider"] = (
        str(search_cfg.get("web_provider") or DEFAULT_SEARCH_POLICY["web_provider"]).strip()
        or DEFAULT_SEARCH_POLICY["web_provider"]
    )
    policy["web_fallback"] = (
        str(search_cfg.get("web_fallback") or DEFAULT_SEARCH_POLICY["web_fallback"]).strip()
        or DEFAULT_SEARCH_POLICY["web_fallback"]
    )
    return policy


def read_builtin_web_search_allowance() -> dict[str, Any] | None:
    path = _allowance_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    expires_at = str(payload.get("expires_at") or "").strip()
    if not expires_at:
        return None
    try:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    if expires_dt <= _now():
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return payload


def write_builtin_web_search_allowance(
    reason: str,
    *,
    query: str = "",
    provider: str = "",
    source: str = "",
    ttl_seconds: int = DEFAULT_FALLBACK_TTL_SECONDS,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    payload = {
        "version": 1,
        "reason": reason,
        "query": query[:500],
        "provider": provider,
        "source": source,
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(1, ttl_seconds))).isoformat(),
        "details": details or {},
    }
    path = _allowance_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def clear_builtin_web_search_allowance() -> None:
    path = _allowance_path()
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError:
        pass


def search_runtime_summary() -> dict[str, Any]:
    policy = load_search_policy()
    allowance = read_builtin_web_search_allowance()
    return {
        "builtin_web_search": bool(policy.get("builtin_web_search", False)),
        "web_provider": str(policy.get("web_provider") or DEFAULT_SEARCH_POLICY["web_provider"]),
        "web_fallback": str(policy.get("web_fallback") or DEFAULT_SEARCH_POLICY["web_fallback"]),
        "builtin_web_search_unlocked": allowance is not None,
        "builtin_web_search_unlocked_until": str(allowance.get("expires_at") or "") if allowance else "",
        "builtin_web_search_unlock_reason": str(allowance.get("reason") or "") if allowance else "",
        "edge_search_unrestricted": True,
        "policy_source_path": str(policy.get("source_path") or _features_path()),
    }


def load_exa_api_key() -> str:
    env_value = os.environ.get("EXA_API_KEY", "").strip()
    if env_value:
        return env_value
    secrets_path = SECRETS_DIR / "exa.env"
    if not secrets_path.exists():
        return ""
    for line in secrets_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("EXA_API_KEY="):
            continue
        value = line.split("=", 1)[1].strip()
        if value:
            return value
    return ""


__all__ = [
    "DEFAULT_FALLBACK_TTL_SECONDS",
    "clear_builtin_web_search_allowance",
    "load_exa_api_key",
    "load_search_policy",
    "read_builtin_web_search_allowance",
    "search_runtime_summary",
    "write_builtin_web_search_allowance",
]
