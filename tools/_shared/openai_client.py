"""Shared OpenAI client factory for edge-of-chaos tools.

Loads API keys from secrets/*.env and creates OpenAI-compatible clients
(works for both OpenAI and xAI/Grok via base_url override).
"""

import os
from pathlib import Path

from openai import OpenAI


def load_openai_env():
    """Load API keys from per-tool .env files in secrets/."""
    edge_dir = Path(os.environ.get("EDGE_DIR", os.path.expanduser("~/edge")))
    secrets = edge_dir / "secrets"
    for env_file in ("openai.env", "xai.env", "keys.env"):
        path = secrets / env_file
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v and k not in os.environ:
                        os.environ[k] = v


def make_openai_client(api_key=None, timeout=120, base_url=None):
    """Create an OpenAI client. Supports xAI/Grok via base_url."""
    kwargs = {"timeout": timeout}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
