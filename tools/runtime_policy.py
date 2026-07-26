"""Central fail-closed harness policy for the Hermes-only derivative."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
from typing import Any

ALLOWED_HARNESSES = frozenset({"hermes"})
ALLOWED_EMBEDDING_PROVIDERS = frozenset({"openai", "openrouter", "azure", "custom"})
_FORBIDDEN_MODEL_MARKERS = ("claude", "codex", "grok")


class RuntimePolicyError(ValueError):
    """A requested runtime capability violates the derivative policy."""


def require_allowed_harness(harness: object) -> str:
    """Return the canonical harness or fail before any caller side effect."""
    if not isinstance(harness, str) or harness not in ALLOWED_HARNESSES:
        raise RuntimePolicyError(
            f"harness {harness!r} is forbidden; allowed harnesses: hermes"
        )
    return harness


def require_allowed_adversarials(values: object) -> tuple[str, ...]:
    """Allow only Hermes sessions or the explicit same-model ``self`` fallback."""
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise RuntimePolicyError("adversarials must be a list")
    allowed = []
    for value in values:
        if value == "self":
            allowed.append(value)
            continue
        allowed.append(require_allowed_harness(value))
    return tuple(allowed)


def require_dedicated_hermes_home(
    home: object,
    *,
    default_home: object | None = None,
) -> Path:
    """Require an explicit Hermes home that is not the active/global profile."""
    if not isinstance(home, (str, Path)) or not str(home).strip():
        raise RuntimePolicyError("an explicit dedicated Hermes home is required")
    resolved = Path(home).expanduser().resolve(strict=False)
    global_home = (
        Path.home() / ".hermes"
        if default_home is None
        else Path(default_home).expanduser()
    ).resolve(strict=False)
    if resolved == global_home:
        raise RuntimePolicyError(
            f"Hermes home {resolved} is the global/default profile; use a dedicated profile"
        )
    return resolved


def require_session_ingestion_ready() -> None:
    """Session ingestion stays dark until a reviewed Hermes-native reader exists."""
    raise RuntimePolicyError(
        "session ingestion is dark until a Hermes-native session reader is implemented"
    )


def require_hermes_safe_skill_tree(skills_root: Path | str) -> Path:
    """Reject provisioned instructions that mention an external harness."""
    root = Path(skills_root)
    forbidden = re.compile(r"\b(?:claude|codex|grok)\b", re.IGNORECASE)
    for path in sorted(root.rglob("*.md")) if root.exists() else ():
        if forbidden.search(path.read_text(encoding="utf-8")):
            raise RuntimePolicyError(
                f"skill {path.relative_to(root)} references a forbidden external harness"
            )
    return root


def require_allowed_embedding_router(router: object) -> dict:
    """Validate the narrow API-only exception used exclusively for embeddings."""
    if not isinstance(router, dict):
        raise RuntimePolicyError("embedding router must be a mapping")
    provider = router.get("provider")
    if not isinstance(provider, str) or provider not in ALLOWED_EMBEDDING_PROVIDERS:
        raise RuntimePolicyError(
            f"embedding provider {provider!r} is forbidden; allowed providers: "
            + ", ".join(sorted(ALLOWED_EMBEDDING_PROVIDERS))
        )
    model = router.get("model")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise RuntimePolicyError("embedding model must be a non-empty string")
        lowered = model.lower()
        if any(marker in lowered for marker in _FORBIDDEN_MODEL_MARKERS):
            raise RuntimePolicyError(f"embedding model {model!r} selects a forbidden model family")
    if provider in {"azure", "custom"}:
        base_url = router.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise RuntimePolicyError(f"embedding provider {provider!r} requires explicit base_url")
    return router


def require_hermes_only_surfaces(cfg: object) -> dict:
    """Reject any explicitly declared surface outside the Hermes allowlist."""
    if not isinstance(cfg, dict):
        raise RuntimePolicyError("runtime config must be a mapping")
    surfaces = cfg.get("surfaces")
    if surfaces is None:
        surfaces = {}
    if not isinstance(surfaces, dict):
        raise RuntimePolicyError("surfaces must be a mapping")
    forbidden = sorted(set(surfaces) - ALLOWED_HARNESSES)
    if forbidden:
        raise RuntimePolicyError(
            "forbidden surfaces declared: " + ", ".join(forbidden)
        )
    return surfaces


def _require_no_forbidden_selector_markers(value: object, path: str) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_MODEL_MARKERS):
            raise RuntimePolicyError(f"{path} references a forbidden external harness")
        return
    if isinstance(value, dict):
        inert_text_fields = {"directive", "prompt", "description", "instruction", "instructions"}
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(key, str):
                lowered = key.lower()
                if any(marker in lowered for marker in _FORBIDDEN_MODEL_MARKERS):
                    raise RuntimePolicyError(f"{child} references a forbidden external harness")
                if lowered in inert_text_fields:
                    continue
            _require_no_forbidden_selector_markers(item, child)
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            _require_no_forbidden_selector_markers(item, f"{path}[{index}]")


def require_hermes_only_runtime_config(cfg: object) -> dict:
    """Validate every public harness selector in an agent configuration."""
    require_hermes_only_surfaces(cfg)
    assert isinstance(cfg, dict)  # narrowed by require_hermes_only_surfaces
    for selector in ("primary", "adversarials", "heartbeat", "execution_subagents", "subagents"):
        if selector in cfg:
            _require_no_forbidden_selector_markers(cfg[selector], selector)

    routers = cfg.get("routers")
    if routers is None:
        routers = {}
    if not isinstance(routers, dict):
        raise RuntimePolicyError("routers must be a mapping")
    for route, router in routers.items():
        if route == "embedding":
            require_allowed_embedding_router(router)
            continue
        if not isinstance(router, dict):
            raise RuntimePolicyError(f"router {route!r} must be a mapping")
        provider = router.get("provider")
        if provider is None:
            raise RuntimePolicyError(f"router {route!r} must declare provider=hermes")
        require_allowed_harness(provider)

    heartbeat = cfg.get("heartbeat")
    if heartbeat is None:
        heartbeat = {}
    if not isinstance(heartbeat, dict):
        raise RuntimePolicyError("heartbeat must be a mapping")
    heartbeat_cli = heartbeat.get("cli")
    if heartbeat_cli is not None:
        require_allowed_harness(heartbeat_cli)
    return cfg


def run_for_harness(
    harness: object,
    operation: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Validate the harness, then and only then invoke ``operation``."""
    require_allowed_harness(harness)
    return operation(*args, **kwargs)
