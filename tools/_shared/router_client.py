"""Agnostic OpenAI-compatible router client.

Single abstraction for every LLM/embedding call in the codebase. The YAML
declares everything (base_url, secret ref, headers, query, model). The code
has no per-provider branches — anything that speaks the OpenAI contract
(direct OpenAI, Azure, xAI, OpenRouter, LiteLLM, Groq, Together, vLLM…) is
reachable with the same function.

Providers that do NOT speak OpenAI-compatible (Bedrock native, Vertex native)
are expected to sit behind a translator (LiteLLM, OpenRouter, portkey). The
agent never sees them directly.

Resolves issue #222.
"""

from __future__ import annotations

import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from .telemetry import log_llm_call

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import EDGE_DIR, SECRETS_DIR  # noqa: E402

AGENT_YAML = EDGE_DIR / "agent.yaml"

# --- Legacy fallback: used when agent.yaml has no routers: block. Mirrors
# the pre-#222 behavior (OpenAI default + xAI for grok). Prefix-match on the
# model slug picks the right one. Kept tight so installs without routers:
# keep working.
_LEGACY_DEFAULTS: dict[str, dict[str, Any]] = {
    "chat": {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai.env:OPENAI_API_KEY",
        "model_key": "openai_model",
        "model_default": "gpt-5.4",
    },
    "chat_mini": {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai.env:OPENAI_API_KEY",
        "model_key": "openai_model_mini",
        "model_default": "gpt-4.1-mini",
    },
    "review": {
        "base_url": "https://api.x.ai/v1",
        "secret_ref": "xai.env:XAI_API_KEY",
        "model_key": "grok_model",
        "model_default": "grok-4.20-multi-agent-beta-0309",
    },
    "embedding": {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai.env:OPENAI_API_KEY",
        "model_key": None,
        "model_default": "text-embedding-3-small",
    },
    "deepresearch": {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai.env:OPENAI_API_KEY",
        "model_key": "openai_model",
        "model_default": "gpt-5.4",
    },
}


@lru_cache(maxsize=1)
def _load_agent_yaml() -> dict[str, Any]:
    if yaml is None or not AGENT_YAML.exists():
        return {}
    try:
        data = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_legacy(purpose: str) -> dict[str, Any] | None:
    spec = _LEGACY_DEFAULTS.get(purpose)
    if spec is None:
        return None
    agent = _load_agent_yaml()
    model = spec["model_default"]
    if spec["model_key"] and agent.get(spec["model_key"]):
        model = agent[spec["model_key"]]
    return {
        "base_url": spec["base_url"],
        "secret_ref": spec["secret_ref"],
        "model": model,
        "headers": {},
        "query": {},
    }


def load_router_config(purpose: str) -> dict[str, Any]:
    """Return the resolved router config for a purpose.

    Lookup order:
      1. agent.yaml routers.<purpose>
      2. legacy defaults (_LEGACY_DEFAULTS) — back-compat for installs that
         haven't declared routers: yet.
    """
    agent = _load_agent_yaml()
    routers = agent.get("routers") or {}
    cfg = routers.get(purpose) if isinstance(routers, dict) else None
    if cfg:
        return {
            "base_url": cfg["base_url"],
            "secret_ref": cfg["secret_ref"],
            "model": cfg["model"],
            "headers": dict(cfg.get("headers") or {}),
            "query": dict(cfg.get("query") or {}),
        }
    legacy = _resolve_legacy(purpose)
    if legacy:
        return legacy
    raise KeyError(
        f"No router found for purpose={purpose!r}. "
        "Declare it under routers: in agent.yaml."
    )


def find_router_for_model(model: str) -> tuple[str, dict[str, Any]]:
    """Reverse lookup — find the first router whose model == <model>.

    Used when a caller has a hard model slug (e.g. from --model CLI flag) and
    needs to resolve which router owns it. Falls back to legacy defaults so
    pre-existing model strings like 'grok-4.20-...' still work.
    """
    agent = _load_agent_yaml()
    routers = agent.get("routers") or {}
    if isinstance(routers, dict):
        for name, cfg in routers.items():
            if cfg and cfg.get("model") == model:
                return name, load_router_config(name)
    # Legacy prefix match
    for purpose, spec in _LEGACY_DEFAULTS.items():
        if model.startswith(spec["model_default"].split("-")[0]):
            cfg = _resolve_legacy(purpose)
            if cfg:
                cfg["model"] = model  # caller's override wins
                return purpose, cfg
    raise KeyError(f"No router declares model={model!r}.")


def load_secret(secret_ref: str) -> str:
    """Resolve a secret reference like 'openai.env:OPENAI_API_KEY'.

    Lookup order:
      1. process environment (always wins — allows --env overrides)
      2. file named secrets/<file>, KEY=VALUE lines
    """
    if ":" not in secret_ref:
        raise ValueError(
            f"Invalid secret_ref={secret_ref!r}; expected 'file.env:VAR_NAME'."
        )
    filename, var = secret_ref.split(":", 1)
    val = os.environ.get(var)
    if val:
        return val
    path = SECRETS_DIR / filename
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == var:
                return v.strip()
    raise RuntimeError(
        f"Secret {var!r} not found in environment or {path}."
    )


_SUBST_RE = re.compile(r"\$\{(\w+)\}")


def _substitute(template: str, mapping: dict[str, str]) -> str:
    """Replace ${NAME} tokens using mapping. Leaves unknown tokens untouched."""
    def _sub(m: re.Match[str]) -> str:
        return mapping.get(m.group(1), m.group(0))
    return _SUBST_RE.sub(_sub, template)


def make_client(
    purpose: str | None = None,
    *,
    model: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Build an OpenAI-compatible client for the given purpose (or model).

    Returns (client, model_name). Caller uses the client like any OpenAI SDK
    instance: client.chat.completions.create(...), client.embeddings.create(...),
    client.responses.create(...).

    Args:
      purpose: router name from agent.yaml (chat, review, embedding, …).
      model: override — if passed, resolves the router by model lookup.
             When both purpose and model are passed, purpose's router is used
             but model overrides the router-declared model slug.
      timeout: passed to the OpenAI SDK constructor.
      **kwargs: forwarded to OpenAI() (e.g., max_retries).
    """
    try:
        from openai import OpenAI  # imported lazily so tests without SDK don't break on import
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai package is required: pip install openai"
        ) from exc

    if purpose is None and model is None:
        raise ValueError("make_client requires purpose or model.")

    if purpose is not None:
        cfg = load_router_config(purpose)
        if model is not None:
            cfg["model"] = model
    else:
        _, cfg = find_router_for_model(model)  # type: ignore[arg-type]

    api_key = load_secret(cfg["secret_ref"])
    subst = {"key": api_key, "KEY": api_key}
    headers = {k: _substitute(str(v), subst) for k, v in cfg.get("headers", {}).items()}
    query = {k: _substitute(str(v), subst) for k, v in cfg.get("query", {}).items()}

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": cfg["base_url"],
    }
    if headers:
        client_kwargs["default_headers"] = headers
    if query:
        client_kwargs["default_query"] = query
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    client_kwargs.update(kwargs)

    client = OpenAI(**client_kwargs)
    purpose_name = purpose if purpose is not None else _resolve_purpose_name(cfg["model"])
    return _wrap_with_telemetry(client, purpose_name, cfg["model"]), cfg["model"]


def _resolve_purpose_name(model: str) -> str:
    try:
        name, _ = find_router_for_model(model)
        return name
    except KeyError:
        return "unknown"


class _InstrumentedCreate:
    """Wrap `resource.create(...)` so every call emits an llm_call event."""

    def __init__(self, inner_create: Any, router: str, default_model: str) -> None:
        self._inner = inner_create
        self._router = router
        self._default_model = default_model

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model") or self._default_model
        t0 = time.monotonic()
        try:
            resp = self._inner(*args, **kwargs)
        except Exception:
            dt_ms = int((time.monotonic() - t0) * 1000)
            log_llm_call(
                router=self._router, model=model, tokens_in=0, tokens_out=0,
                latency_ms=dt_ms, error=True,
            )
            raise
        dt_ms = int((time.monotonic() - t0) * 1000)
        tokens_in, tokens_out = _extract_tokens(resp)
        log_llm_call(
            router=self._router, model=model,
            tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=dt_ms,
        )
        return resp


class _InstrumentedResource:
    """Proxy a resource object (e.g., chat.completions). Wraps `.create` only."""

    def __init__(self, inner: Any, router: str, default_model: str) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "create":
            return _InstrumentedCreate(attr, self._router, self._default_model)
        return attr


class _InstrumentedChat:
    """Proxy client.chat, wrap client.chat.completions."""

    def __init__(self, inner: Any, router: str, default_model: str) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "completions":
            return _InstrumentedResource(attr, self._router, self._default_model)
        return attr


class _InstrumentedClient:
    """Thin proxy over the OpenAI SDK client. Wraps `chat.completions.create`,
    `embeddings.create`, and `responses.create` to emit llm_call telemetry.
    Every other attribute passes through unchanged."""

    def __init__(self, inner: Any, router: str, default_model: str) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "chat":
            return _InstrumentedChat(attr, self._router, self._default_model)
        if name in ("embeddings", "responses"):
            return _InstrumentedResource(attr, self._router, self._default_model)
        return attr


def _wrap_with_telemetry(client: Any, router: str, default_model: str) -> Any:
    """Opt-out via env: ED_TELEMETRY_DISABLE=1."""
    if os.environ.get("ED_TELEMETRY_DISABLE") == "1":
        return client
    return _InstrumentedClient(client, router, default_model)


def _extract_tokens(resp: Any) -> tuple[int, int]:
    """Pull (prompt, completion) tokens from OpenAI-shaped responses.
    Returns (0, 0) when usage is missing — don't block on it."""
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return 0, 0
        ti = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) or 0
        to = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) or 0
        return int(ti), int(to)
    except Exception:
        return 0, 0


__all__ = [
    "load_router_config",
    "find_router_for_model",
    "load_secret",
    "make_client",
]
