#!/usr/bin/env python3
"""Blog v0 — serve os artefatos HTML do edge, listados em estilo-blog a partir do eventlog.

O índice é uma PROJEÇÃO do log (ADR-0005: a página re-renderiza do log, sem store paralelo): cada
`artefato.published` vira um post (título, data, blurb do `intent.kernel`) com links para os artefatos
que o dispatch criou (cites/distills/proposes), mais recente primeiro. As entries continuam servidas de
`entries/*.html`. Paths overridáveis por env (EDGE_BLOG_ENTRIES/STATIC/LOG) para teste.
"""
import html
import json
import os
from pathlib import Path

from flask import Flask, abort, send_from_directory

BASE = Path(__file__).resolve().parent

app = Flask(__name__)


def _entries():
    return Path(os.environ.get("EDGE_BLOG_ENTRIES", BASE / "entries"))


def _static():
    return Path(os.environ.get("EDGE_BLOG_STATIC", BASE / "static"))


def _log():
    return Path(os.environ.get("EDGE_BLOG_LOG", BASE.parent / "state" / "events" / "log.jsonl"))


def _blurb(intent, n=220):
    """One-line blog blurb from the artefato's intent kernel."""
    intent = " ".join((intent or "").split())
    return intent if len(intent) <= n else intent[:n].rstrip() + "…"


def _posts():
    """Project the eventlog into blog posts, newest-first.

    Folds `artefato.published` (slug + the artifacts it created) joined to its `intent.kernel`
    (the blurb). The log is append-order (oldest→newest); we reverse for newest-first.
    """
    log = _log()
    if not log.is_file():
        return []
    published, kernels = [], {}
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t, p = e.get("type"), e.get("payload", {})
        if t == "artefato.published":
            published.append({
                "slug": p.get("slug", ""),
                "ts": e.get("ts", ""),
                "cites": p.get("cites", []) or [],
                "distills": p.get("distills", []) or [],
                "proposes": p.get("proposes", []) or [],
            })
        elif t == "intent.kernel":
            kernels[p.get("slug", "")] = p.get("intent", "")
    posts = [{
        **a,
        "title": a["slug"].replace("-", " "),
        "date": a["ts"][:10],
        "blurb": _blurb(kernels.get(a["slug"], "")),
    } for a in published]
    posts.reverse()
    return posts


def _artifact_items(post):
    items = []
    for c in post["cites"]:
        items.append(f'<li class="cite">cites · {html.escape(str(c))}</li>')
    for d in post["distills"]:
        items.append(f'<li class="distill">distills · {html.escape(str(d))}</li>')
    for pr in post["proposes"]:
        body = pr.get("body", "") if isinstance(pr, dict) else str(pr)
        items.append(f'<li class="proposes">proposes · {html.escape(body)}</li>')
    return f'<ul class="artifacts">{"".join(items)}</ul>' if items else ""


def _render_post(post):
    slug = html.escape(post["slug"])
    return (
        '<article class="post">'
        f'<h2><a href="/e/{slug}.html">{html.escape(post["title"])}</a></h2>'
        f'<time class="meta">{html.escape(post["date"])}</time>'
        f'<p class="blurb">{html.escape(post["blurb"])}</p>'
        f'{_artifact_items(post)}'
        '</article>'
    )


@app.get("/")
def index():
    posts = _posts()
    body = "".join(_render_post(p) for p in posts) or '<p class="meta">sem artefatos ainda</p>'
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — artefatos</title>'
        '<link rel="stylesheet" href="/static/style.css"></head><body>'
        f'<main class="blog"><h1>edge — artefatos</h1>{body}</main>'
        "</body></html>"
    )


@app.get("/e/<path:name>")
def entry(name):
    entries = _entries()
    p = entries / name
    if not p.is_file() or p.suffix != ".html":
        abort(404)
    return send_from_directory(entries, name)


@app.get("/static/<path:fname>")
def static_files(fname):
    return send_from_directory(_static(), fname)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("BLOG_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLOG_PORT", "8766")),
    )
