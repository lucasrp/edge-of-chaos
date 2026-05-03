from __future__ import annotations

import http.server
import socketserver
from functools import partial

from .config import RuntimeConfig
from .reports import build_blog


def serve_blog(config: RuntimeConfig, *, port: int) -> None:
    build_blog(config)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(config.root / "blog"))
    with socketserver.TCPServer(("", port), handler) as server:
        print(f"Serving static blog at http://127.0.0.1:{port}/")
        server.serve_forever()
