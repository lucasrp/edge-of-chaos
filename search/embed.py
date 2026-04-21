"""Embedding provider for edge-memory.

Uses the agnostic router handler (#222). Endpoint/key/model are declared in
config/runtime-routers.yaml routers.embedding — no provider knowledge here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from _shared.router_client import make_client  # noqa: E402

MAX_CHARS = 8000  # ~2000 tokens, safe limit


def embed_text(text: str) -> list[float]:
    client, model = make_client("embedding")
    resp = client.embeddings.create(model=model, input=text[:MAX_CHARS])
    return resp.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    client, model = make_client("embedding")
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = [t[:MAX_CHARS] for t in texts[i : i + batch_size]]
        resp = client.embeddings.create(model=model, input=batch)
        all_embeddings.extend([d.embedding for d in resp.data])

    return all_embeddings
