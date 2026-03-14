"""Embedding provider for edge-memory."""

import os
from pathlib import Path

from openai import OpenAI

MODEL = "text-embedding-3-small"
MAX_CHARS = 8000  # ~2000 tokens, safe limit


def _load_key() -> str:
    env_file = Path.home() / "edge" / "secrets" / "openai.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not found. Set it in ~/edge/secrets/openai.env"
        )
    return api_key


def embed_text(text: str) -> list[float]:
    api_key = _load_key()
    client = OpenAI(api_key=api_key)
    # Truncate to avoid token limits
    truncated = text[:MAX_CHARS]
    resp = client.embeddings.create(model=MODEL, input=truncated)
    return resp.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    api_key = _load_key()
    client = OpenAI(api_key=api_key)
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = [t[:MAX_CHARS] for t in texts[i : i + batch_size]]
        resp = client.embeddings.create(model=MODEL, input=batch)
        all_embeddings.extend([d.embedding for d in resp.data])

    return all_embeddings
