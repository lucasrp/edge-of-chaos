"""Shared OpenAI / Azure OpenAI client factory.

Auto-detects Azure based on key format + endpoint availability:
  - Key starts with sk-  →  standard OpenAI (api.openai.com)
  - Key does NOT start with sk- AND azure endpoint found  →  AzureOpenAI

Azure endpoint is loaded from (in order):
  1. AZURE_OPENAI_ENDPOINT env var
  2. URL_AZ_OPENAI env var
  3. secrets/azure-tcu.env file

API version defaults to AZURE_OPENAI_API_VERSION env var or 2025-03-01-preview.

Usage:
    from _shared.openai_client import make_openai_client, load_openai_env
    load_openai_env()
    client = make_openai_client(api_key=key, timeout=180)
    # Works identically whether OpenAI or AzureOpenAI
"""

import json
import os
import subprocess
from pathlib import Path

_SECRETS_DIR = None
AZURE_API_VERSION_DEFAULT = "2025-03-01-preview"

_env_loaded = False
_provider_config = None


def _get_secrets_dir() -> Path:
    global _SECRETS_DIR
    if _SECRETS_DIR is None:
        edge_dir = Path(os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))
        _SECRETS_DIR = edge_dir / "secrets"
    return _SECRETS_DIR


def load_openai_env():
    """Load API keys from per-tool .env files in secrets/."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    secrets = _get_secrets_dir()
    for env_file in ("openai.env", "xai.env", "keys.env", "azure-tcu.env"):
        path = secrets / env_file
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v and k not in os.environ:
                        os.environ[k] = v


def _load_azure_endpoint() -> str:
    """Load Azure OpenAI endpoint from env or secrets."""
    endpoint = (os.environ.get("AZURE_OPENAI_ENDPOINT")
                or os.environ.get("URL_AZ_OPENAI"))
    if endpoint:
        return endpoint.rstrip("/")

    secrets = _get_secrets_dir()
    for env_file in ("openai.env", "azure-tcu.env"):
        path = secrets / env_file
        if path.exists():
            for line in path.read_text().strip().split("\n"):
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip()
                if key in ("URL_AZ_OPENAI", "AZURE_OPENAI_ENDPOINT"):
                    return val.rstrip("/")
    return ""


def _is_azure_key(api_key: str) -> bool:
    return bool(api_key) and not api_key.startswith("sk-")


def _load_provider_config():
    """Check for llm-provider primitive and load its config (#194)."""
    global _provider_config
    if _provider_config is not None:
        return _provider_config

    edge_dir = Path(os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))
    codename = os.environ.get("EDGE_CODENAME", "ed")
    prim_path = edge_dir / "libexec" / codename / "llm-provider"

    if prim_path.exists() and os.access(prim_path, os.X_OK):
        try:
            result = subprocess.run(
                [str(prim_path)], capture_output=True, text=True, timeout=10,
                env={**os.environ, "EDGE_DIR": str(edge_dir)}
            )
            if result.returncode == 0 and result.stdout.strip():
                _provider_config = json.loads(result.stdout.strip())
                return _provider_config
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass

    _provider_config = {}
    return _provider_config


def make_openai_client(api_key=None, timeout=120, base_url=None):
    """Create OpenAI or AzureOpenAI client based on key type or llm-provider primitive.

    Priority:
    1. Explicit base_url (e.g. xAI) → standard OpenAI client
    2. llm-provider primitive exists → use its config
    3. Azure auto-detection (non-sk- key + endpoint)
    4. Standard OpenAI
    """
    from openai import OpenAI

    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    # Explicit base_url → always standard client (xAI, local, etc.)
    if base_url:
        kwargs = {"api_key": api_key, "base_url": base_url}
        if timeout:
            kwargs["timeout"] = timeout
        return OpenAI(**kwargs)

    # Check llm-provider primitive (#194)
    provider_cfg = _load_provider_config()
    if provider_cfg.get("provider") == "azure":
        from openai import AzureOpenAI
        kwargs = {
            "api_key": provider_cfg.get("api_key", api_key),
            "azure_endpoint": provider_cfg.get("endpoint", ""),
            "api_version": provider_cfg.get("api_version", AZURE_API_VERSION_DEFAULT),
        }
        if timeout:
            kwargs["timeout"] = timeout
        return AzureOpenAI(**kwargs)
    elif provider_cfg.get("provider") == "openrouter":
        kwargs = {
            "api_key": provider_cfg.get("api_key", api_key),
            "base_url": provider_cfg.get("endpoint", "https://openrouter.ai/api/v1"),
            "timeout": timeout,
        }
        return OpenAI(**kwargs)
    elif provider_cfg.get("provider") == "bedrock":
        # Bedrock uses its own SDK — fallback to standard for now
        pass

    # Azure auto-detection (legacy — kept for instances without llm-provider)
    if _is_azure_key(api_key):
        azure_endpoint = _load_azure_endpoint()
        if azure_endpoint:
            from openai import AzureOpenAI
            kwargs = {
                "api_key": api_key,
                "azure_endpoint": azure_endpoint,
                "api_version": os.environ.get(
                    "AZURE_OPENAI_API_VERSION", AZURE_API_VERSION_DEFAULT),
            }
            if timeout:
                kwargs["timeout"] = timeout
            return AzureOpenAI(**kwargs)

    # Standard OpenAI
    kwargs = {"api_key": api_key, "timeout": timeout}
    return OpenAI(**kwargs)
