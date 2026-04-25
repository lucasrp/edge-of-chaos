"""Agnostic OpenAI-compatible router client.

Single abstraction for every LLM/embedding call in the codebase. The rendered
runtime router config declares everything (base_url, secret ref, headers,
query, model). The code has no per-provider branches — anything that speaks
the OpenAI contract
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
import shutil
import subprocess
import sys
import time
import uuid
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .telemetry import log_event, log_llm_call

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import ROUTERS_CONFIG_FILE, SECRETS_DIR  # noqa: E402

# --- Legacy fallback: used when runtime router config is absent. Mirrors the
# pre-#222 behavior (OpenAI default + xAI for grok). Kept tight so old installs
# keep working until they render runtime-routers.yaml.
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

CLAUDE_FALLBACK_MODEL = "claude-cli"


@lru_cache(maxsize=1)
def _load_runtime_routers() -> dict[str, dict[str, Any]]:
    if yaml is None or not ROUTERS_CONFIG_FILE.exists():
        return {}
    try:
        data = yaml.safe_load(ROUTERS_CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    routers = data.get("routers") if isinstance(data, dict) else {}
    if not isinstance(routers, dict):
        return {}

    resolved: dict[str, dict[str, Any]] = {}
    for purpose, cfg in routers.items():
        if not purpose or not isinstance(cfg, dict):
            continue
        base_url = str(cfg.get("base_url", "")).strip()
        secret_ref = str(cfg.get("secret_ref", "")).strip()
        model = str(cfg.get("model", "")).strip()
        if not (base_url and secret_ref and model):
            continue
        payload = {
            "base_url": base_url,
            "secret_ref": secret_ref,
            "model": model,
            "headers": dict(cfg.get("headers") or {}),
            "query": dict(cfg.get("query") or {}),
        }
        resolved[str(purpose)] = payload
    return resolved


def _resolve_legacy(purpose: str) -> dict[str, Any] | None:
    spec = _LEGACY_DEFAULTS.get(purpose)
    if spec is None:
        return None
    model = spec["model_default"]
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
      1. config/runtime-routers.yaml routers.<purpose>
      2. legacy defaults (_LEGACY_DEFAULTS) — back-compat for installs that
         haven't rendered runtime routers yet.
    """
    routers = _load_runtime_routers()
    cfg = routers.get(purpose)
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
        "Declare it in config/runtime-routers.yaml."
    )


def find_router_for_model(model: str) -> tuple[str, dict[str, Any]]:
    """Reverse lookup — find the first router whose model == <model>.

    Used when a caller has a hard model slug (e.g. from --model CLI flag) and
    needs to resolve which router owns it. Falls back to legacy defaults so
    pre-existing model strings like 'grok-4.20-...' still work.
    """
    routers = _load_runtime_routers()
    for name, cfg in routers.items():
        if cfg and cfg.get("model") == model:
            return name, load_router_config(name)
    # Legacy prefix match. When the user *has* declared routers but the
    # requested model doesn't match any of them, we still fall through here —
    # warn loudly so a mismatched --model slug doesn't silently hit
    # api.openai.com with a non-OpenAI key (issue #233).
    declared = [cfg.get("model") for cfg in routers.values() if isinstance(cfg, dict)]
    for purpose, spec in _LEGACY_DEFAULTS.items():
        if model.startswith(spec["model_default"].split("-")[0]):
            cfg = _resolve_legacy(purpose)
            if cfg:
                cfg["model"] = model  # caller's override wins
                if declared:
                    print(
                        f"WARN router_client: model={model!r} not declared "
                        f"in runtime routers (declared: {declared}). "
                        f"Falling back to legacy endpoint {cfg['base_url']} "
                        f"using {cfg['secret_ref']}. This will fail if your "
                        f"key is not for that provider.",
                        file=sys.stderr,
                    )
                return purpose, cfg
    raise KeyError(
        f"No router declares model={model!r}. "
        f"Declared in runtime config: {declared or '(none)'}."
    )


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


def resolve_claude_bin() -> str:
    env_override = os.environ.get("EDGE_CLAUDE_BIN") or os.environ.get("CLAUDE_BIN")
    candidates: list[str] = []
    if env_override:
        candidates.append(env_override)

    path_hit = shutil.which("claude")
    if path_hit:
        candidates.append(path_hit)

    home = Path.home()
    candidates.extend(
        [
            str(home / ".local" / "bin" / "claude"),
            str(home / "bin" / "claude"),
        ]
    )
    for glob_hit in sorted((home / ".nvm" / "versions" / "node").glob("*/bin/claude"), reverse=True):
        candidates.append(str(glob_hit))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError("claude CLI not found on PATH or common install locations")


def claude_cli_available() -> bool:
    try:
        resolve_claude_bin()
        return True
    except FileNotFoundError:
        return False


def call_claude_cli_text(prompt: str, *, timeout: int = 60) -> str:
    """Invoke the local Claude CLI and return plain text output."""
    result = subprocess.run(
        [resolve_claude_bin(), "-p", prompt, "--dangerously-skip-permissions"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        raise RuntimeError(
            f"claude CLI exited {result.returncode}: {stderr_tail or '(no stderr)'}"
        )
    text = (result.stdout or "").strip()
    if not text:
        raise RuntimeError("claude CLI produced empty output")
    return text


def _safe_error_text(exc: Exception, limit: int = 500) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _log_provider_degradation(
    *,
    router: str,
    model: str,
    resource: str,
    exc: Exception,
    fallback: str | None,
    stage: str,
) -> None:
    try:
        log_event(
            "llm_provider_degraded",
            router=router,
            model=model,
            resource=resource,
            stage=stage,
            error_type=type(exc).__name__,
            error=_safe_error_text(exc),
            fallback=fallback or "",
        )
    except Exception:
        pass


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip())
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    return str(content)


def _message_field(message: Any, field: str, default: Any = "") -> Any:
    if isinstance(message, dict):
        return message.get(field, default)
    return getattr(message, field, default)


def _messages_to_prompt(messages: list[Any]) -> str:
    sections: list[str] = []
    for message in messages or []:
        role = str(_message_field(message, "role", "user") or "user")
        content = _content_to_text(_message_field(message, "content", ""))
        if not content.strip():
            continue
        sections.append(f"## {role.title()}\n\n{content.strip()}")
    return "\n\n".join(sections).strip()


def _responses_input_to_prompt(input_value: Any, tools: list[Any] | None) -> str:
    sections: list[str] = []
    if isinstance(input_value, str):
        sections.append(input_value.strip())
    elif isinstance(input_value, list):
        for item in input_value:
            role = str(_message_field(item, "role", "user") or "user")
            content = _content_to_text(_message_field(item, "content", ""))
            if not content.strip():
                continue
            sections.append(f"## {role.title()}\n\n{content.strip()}")
    elif input_value is not None:
        sections.append(str(input_value).strip())

    tool_types: list[str] = []
    for tool in tools or []:
        if isinstance(tool, dict):
            tool_type = str(tool.get("type") or "").strip()
        else:
            tool_type = str(getattr(tool, "type", "") or "").strip()
        if tool_type:
            tool_types.append(tool_type)
    if tool_types:
        sections.append(
            "## Requested tools\n\n"
            + "\n".join(f"- {tool_type} (not available in local Claude CLI fallback)" for tool_type in tool_types)
        )
    return "\n\n".join(section for section in sections if section).strip()


def _fallback_prompt(resource_name: str, kwargs: dict[str, Any]) -> str:
    if resource_name == "chat.completions":
        return _messages_to_prompt(list(kwargs.get("messages") or []))
    if resource_name == "responses":
        return _responses_input_to_prompt(kwargs.get("input"), list(kwargs.get("tools") or []))
    return ""


def _should_fallback_to_claude(exc: Exception, resource_name: str) -> bool:
    if resource_name == "embeddings":
        return False
    if not claude_cli_available():
        return False
    status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403, 429}:
        return True
    lowered = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "insufficient_quota",
        "quota",
        "rate limit",
        "429",
        "401",
        "403",
        "unauthoriz",
        "forbidden",
        "timeout",
        "timed out",
        "timedout",
        "connection error",
        "api connection",
        "service unavailable",
    )
    return any(needle in lowered for needle in needles)


def _build_chat_fallback_response(text: str) -> Any:
    return SimpleNamespace(
        id=f"{CLAUDE_FALLBACK_MODEL}-{uuid.uuid4().hex[:8]}",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, tool_calls=None)
            )
        ],
        usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


def _build_responses_fallback_response(text: str) -> Any:
    return SimpleNamespace(
        id=f"{CLAUDE_FALLBACK_MODEL}-{uuid.uuid4().hex[:8]}",
        output=[SimpleNamespace(type="message", content=[SimpleNamespace(text=text, annotations=[])])],
        output_text=text,
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
    )


def _call_claude_fallback(resource_name: str, kwargs: dict[str, Any], *, timeout_s: int) -> Any:
    prompt = _fallback_prompt(resource_name, kwargs)
    if not prompt.strip():
        raise RuntimeError(f"cannot build Claude fallback prompt for resource={resource_name}")
    text = call_claude_cli_text(prompt, timeout=timeout_s)
    if resource_name == "responses":
        return _build_responses_fallback_response(text)
    return _build_chat_fallback_response(text)


class _ClaudeFallbackCreate:
    """OpenAI-shaped `.create()` shim backed only by local Claude CLI."""

    def __init__(self, router: str, default_model: str, resource_name: str, fallback_timeout_s: int, setup_error: str) -> None:
        self._router = router
        self._default_model = default_model
        self._resource_name = resource_name
        self._fallback_timeout_s = fallback_timeout_s
        self._setup_error = setup_error

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model") or self._default_model
        if self._resource_name == "embeddings":
            raise RuntimeError(
                "Claude CLI fallback does not support embeddings; use FTS-only/no-embed degradation."
            )
        started = time.monotonic()
        try:
            resp = _call_claude_fallback(
                self._resource_name,
                kwargs,
                timeout_s=self._fallback_timeout_s,
            )
        except Exception as exc:
            _log_provider_degradation(
                router=self._router,
                model=str(model),
                resource=self._resource_name,
                exc=exc,
                fallback=None,
                stage="claude_fallback_failed",
            )
            raise
        latency_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            router=f"{self._router}:claude-fallback",
            model=CLAUDE_FALLBACK_MODEL,
            tokens_in=0,
            tokens_out=0,
            latency_ms=latency_ms,
            fallback_for=model,
            resource=self._resource_name,
            setup_fallback=True,
            setup_error=self._setup_error,
        )
        return resp


class _ClaudeFallbackResource:
    def __init__(self, router: str, default_model: str, resource_name: str, fallback_timeout_s: int, setup_error: str) -> None:
        self._router = router
        self._default_model = default_model
        self._resource_name = resource_name
        self._fallback_timeout_s = fallback_timeout_s
        self._setup_error = setup_error

    def __getattr__(self, name: str) -> Any:
        if name == "create":
            return _ClaudeFallbackCreate(
                self._router,
                self._default_model,
                self._resource_name,
                self._fallback_timeout_s,
                self._setup_error,
            )
        raise AttributeError(name)


class _ClaudeFallbackChat:
    def __init__(self, router: str, default_model: str, fallback_timeout_s: int, setup_error: str) -> None:
        self._router = router
        self._default_model = default_model
        self._fallback_timeout_s = fallback_timeout_s
        self._setup_error = setup_error

    def __getattr__(self, name: str) -> Any:
        if name == "completions":
            return _ClaudeFallbackResource(
                self._router,
                self._default_model,
                "chat.completions",
                self._fallback_timeout_s,
                self._setup_error,
            )
        raise AttributeError(name)


class _ClaudeFallbackClient:
    """Minimal OpenAI-compatible client used when external setup fails."""

    def __init__(self, router: str, default_model: str, fallback_timeout_s: int, setup_error: str) -> None:
        self._router = router
        self._default_model = default_model
        self._fallback_timeout_s = fallback_timeout_s
        self._setup_error = setup_error

    def __getattr__(self, name: str) -> Any:
        if name == "chat":
            return _ClaudeFallbackChat(
                self._router,
                self._default_model,
                self._fallback_timeout_s,
                self._setup_error,
            )
        if name in ("responses", "embeddings"):
            return _ClaudeFallbackResource(
                self._router,
                self._default_model,
                name,
                self._fallback_timeout_s,
                self._setup_error,
            )
        raise AttributeError(name)


def _purpose_allows_claude_fallback(purpose: str | None, model: str | None) -> bool:
    if str(purpose or "").strip() == "embedding":
        return False
    if "embedding" in str(model or "").lower():
        return False
    return claude_cli_available()


def _fallback_only_client(
    *,
    router: str,
    model: str,
    timeout: float | None,
    exc: Exception,
    resource: str,
    stage: str,
) -> tuple[Any, str]:
    timeout_s = int(timeout) if timeout else 60
    setup_error = _safe_error_text(exc)
    _log_provider_degradation(
        router=router,
        model=model,
        resource=resource,
        exc=exc,
        fallback=CLAUDE_FALLBACK_MODEL,
        stage=stage,
    )
    return _ClaudeFallbackClient(router, model, timeout_s, setup_error), model


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
      purpose: router name from config/runtime-routers.yaml (chat, review, embedding, …).
      model: override — if passed, resolves the router by model lookup.
             When both purpose and model are passed, purpose's router is used
             but model overrides the router-declared model slug.
      timeout: passed to the OpenAI SDK constructor.
      **kwargs: forwarded to OpenAI() (e.g., max_retries).
    """
    try:
        from openai import OpenAI  # imported lazily so tests without SDK don't break on import
    except ImportError as exc:  # pragma: no cover
        if _purpose_allows_claude_fallback(purpose, model):
            return _fallback_only_client(
                router=purpose or "unknown",
                model=model or CLAUDE_FALLBACK_MODEL,
                timeout=timeout,
                exc=exc,
                resource="client",
                stage="sdk_import",
            )
        raise RuntimeError(
            "openai package is required: pip install openai"
        ) from exc

    if purpose is None and model is None:
        raise ValueError("make_client requires purpose or model.")

    try:
        if purpose is not None:
            cfg = load_router_config(purpose)
            if model is not None:
                cfg["model"] = model
            purpose_name = purpose
        else:
            purpose_name, cfg = find_router_for_model(model)  # type: ignore[arg-type]
    except Exception as exc:
        if _purpose_allows_claude_fallback(purpose, model):
            return _fallback_only_client(
                router=purpose or "unknown",
                model=model or CLAUDE_FALLBACK_MODEL,
                timeout=timeout,
                exc=exc,
                resource="router",
                stage="router_config",
            )
        raise

    try:
        api_key = load_secret(cfg["secret_ref"])
    except Exception as exc:
        if _purpose_allows_claude_fallback(purpose, cfg["model"]):
            return _fallback_only_client(
                router=purpose_name,
                model=cfg["model"],
                timeout=timeout,
                exc=exc,
                resource="secret",
                stage="secret_resolution",
            )
        raise
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

    try:
        client = OpenAI(**client_kwargs)
    except Exception as exc:
        if _purpose_allows_claude_fallback(purpose, cfg["model"]):
            return _fallback_only_client(
                router=purpose_name,
                model=cfg["model"],
                timeout=timeout,
                exc=exc,
                resource="client",
                stage="client_init",
            )
        raise
    fallback_timeout_s = int(timeout) if timeout else 60
    return _wrap_with_telemetry(client, purpose_name, cfg["model"], fallback_timeout_s), cfg["model"]


def _resolve_purpose_name(model: str) -> str:
    try:
        name, _ = find_router_for_model(model)
        return name
    except KeyError:
        return "unknown"


class _InstrumentedCreate:
    """Wrap `resource.create(...)` so every call emits an llm_call event."""

    def __init__(self, inner_create: Any, router: str, default_model: str, resource_name: str, fallback_timeout_s: int) -> None:
        self._inner = inner_create
        self._router = router
        self._default_model = default_model
        self._resource_name = resource_name
        self._fallback_timeout_s = fallback_timeout_s

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model") or self._default_model
        t0 = time.monotonic()
        try:
            resp = self._inner(*args, **kwargs)
        except Exception as exc:
            dt_ms = int((time.monotonic() - t0) * 1000)
            fallback_candidate = _should_fallback_to_claude(exc, self._resource_name)
            log_llm_call(
                router=self._router, model=model, tokens_in=0, tokens_out=0,
                latency_ms=dt_ms, error=True,
                fallback_candidate=fallback_candidate,
            )
            _log_provider_degradation(
                router=self._router,
                model=str(model),
                resource=self._resource_name,
                exc=exc,
                fallback=CLAUDE_FALLBACK_MODEL if fallback_candidate else None,
                stage="remote_call",
            )
            if fallback_candidate:
                fallback_started = time.monotonic()
                try:
                    fallback_resp = _call_claude_fallback(
                        self._resource_name,
                        kwargs,
                        timeout_s=self._fallback_timeout_s,
                    )
                except Exception as fallback_exc:
                    _log_provider_degradation(
                        router=self._router,
                        model=CLAUDE_FALLBACK_MODEL,
                        resource=self._resource_name,
                        exc=fallback_exc,
                        fallback=None,
                        stage="claude_fallback_failed",
                    )
                    raise
                fallback_dt_ms = int((time.monotonic() - fallback_started) * 1000)
                log_llm_call(
                    router=f"{self._router}:claude-fallback",
                    model=CLAUDE_FALLBACK_MODEL,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=fallback_dt_ms,
                    fallback_for=model,
                    resource=self._resource_name,
                )
                return fallback_resp
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

    def __init__(self, inner: Any, router: str, default_model: str, resource_name: str, fallback_timeout_s: int) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model
        self._resource_name = resource_name
        self._fallback_timeout_s = fallback_timeout_s

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "create":
            return _InstrumentedCreate(attr, self._router, self._default_model, self._resource_name, self._fallback_timeout_s)
        return attr


class _InstrumentedChat:
    """Proxy client.chat, wrap client.chat.completions."""

    def __init__(self, inner: Any, router: str, default_model: str, fallback_timeout_s: int) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model
        self._fallback_timeout_s = fallback_timeout_s

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "completions":
            return _InstrumentedResource(attr, self._router, self._default_model, "chat.completions", self._fallback_timeout_s)
        return attr


class _InstrumentedClient:
    """Thin proxy over the OpenAI SDK client. Wraps `chat.completions.create`,
    `embeddings.create`, and `responses.create` to emit llm_call telemetry.
    Every other attribute passes through unchanged."""

    def __init__(self, inner: Any, router: str, default_model: str, fallback_timeout_s: int) -> None:
        self._inner = inner
        self._router = router
        self._default_model = default_model
        self._fallback_timeout_s = fallback_timeout_s

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name == "chat":
            return _InstrumentedChat(attr, self._router, self._default_model, self._fallback_timeout_s)
        if name in ("embeddings", "responses"):
            return _InstrumentedResource(attr, self._router, self._default_model, name, self._fallback_timeout_s)
        return attr


def _wrap_with_telemetry(client: Any, router: str, default_model: str, fallback_timeout_s: int) -> Any:
    """Opt-out via env: ED_TELEMETRY_DISABLE=1."""
    if os.environ.get("ED_TELEMETRY_DISABLE") == "1":
        return client
    return _InstrumentedClient(client, router, default_model, fallback_timeout_s)


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
    "CLAUDE_FALLBACK_MODEL",
    "call_claude_cli_text",
    "claude_cli_available",
    "load_router_config",
    "find_router_for_model",
    "load_secret",
    "make_client",
    "resolve_claude_bin",
]
