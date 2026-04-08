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

import os
from pathlib import Path

_SECRETS_DIR = None
AZURE_API_VERSION_DEFAULT = "2025-03-01-preview"

_env_loaded = False


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


def make_openai_client(api_key=None, timeout=120, base_url=None):
    """Create OpenAI or AzureOpenAI client based on key type.

    - If base_url is given (e.g. xAI), always standard OpenAI client.
    - If key is Azure-style and endpoint available, AzureOpenAI.
    - Otherwise, standard OpenAI.
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

    # Azure detection
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
