#!/usr/bin/env python3
"""Blog v0 — serve os artefatos HTML do edge: index + entries/*.html + static.

Os artefatos são páginas HTML completas (geradas no heartbeat). O blog lista e serve.
Paths são overridáveis por env (EDGE_BLOG_ENTRIES/STATIC) para teste.
"""
import os
from pathlib import Path

from flask import Flask, abort, send_from_directory

BASE = Path(__file__).resolve().parent
ENTRIES = Path(os.environ.get("EDGE_BLOG_ENTRIES", BASE / "entries"))
STATIC = Path(os.environ.get("EDGE_BLOG_STATIC", BASE / "static"))

app = Flask(__name__)


def _entries():
    ENTRIES.mkdir(parents=True, exist_ok=True)
    return sorted(ENTRIES.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)


@app.get("/")
def index():
    items = "".join(
        f'<li><a href="/e/{p.name}">{p.stem.replace("-", " ")}</a></li>' for p in _entries()
    ) or '<li class="meta">sem artefatos ainda</li>'
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — artefatos</title>'
        '<link rel="stylesheet" href="/static/style.css"></head><body>'
        f'<article class="report"><h1>edge — artefatos</h1><ul>{items}</ul></article>'
        "</body></html>"
    )


@app.get("/e/<path:name>")
def entry(name):
    p = ENTRIES / name
    if not p.is_file() or p.suffix != ".html":
        abort(404)
    return send_from_directory(ENTRIES, name)


@app.get("/static/<path:fname>")
def static_files(fname):
    return send_from_directory(STATIC, fname)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("BLOG_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLOG_PORT", "8766")),
    )
