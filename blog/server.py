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
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, request, send_from_directory

BASE = Path(__file__).resolve().parent

app = Flask(__name__)


def _entries():
    return Path(os.environ.get("EDGE_BLOG_ENTRIES", BASE / "entries"))


def _static():
    return Path(os.environ.get("EDGE_BLOG_STATIC", BASE / "static"))


def _log():
    return Path(os.environ.get("EDGE_BLOG_LOG", BASE.parent / "state" / "events" / "log.jsonl"))


def _read_events():
    """Yield every event in the log, oldest→newest, skipping blanks/garbage."""
    log = _log()
    if not log.is_file():
        return
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _append(type_, subject, payload):
    """Append ONE event to the log — the only write path (no parallel store, ADR-0006)."""
    event = {
        "seq": max((e.get("seq", 0) for e in _read_events()), default=0) + 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type_,
        "subject": subject,
        "payload": payload,
    }
    with _log().open("a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def _comments(target_ref):
    """Fold the comment thread for a target (slug, or None for the general chat)."""
    return [
        {**e["payload"], "ts": e.get("ts", "")}
        for e in _read_events()
        if e.get("type") == "voz.comment" and e.get("payload", {}).get("target_ref") == target_ref
    ]


def _replies():
    """Fold edge replies keyed by the comment_id they answer."""
    out = {}
    for e in _read_events():
        if e.get("type") == "voz.reply":
            p = e.get("payload", {})
            out.setdefault(p.get("comment_id"), []).append({**p, "ts": e.get("ts", "")})
    return out


def open_comments():
    """The answer queue: every comment with no `voz.reply` yet (any target). A fold, not a flag."""
    answered = set(_replies())
    return [
        {**e["payload"], "ts": e.get("ts", "")}
        for e in _read_events()
        if e.get("type") == "voz.comment" and e.get("payload", {}).get("comment_id") not in answered
    ]


def _replies_block(c, replies_by_id):
    """The replies under a comment, or the 'agent responds next beat' affordance if it is open."""
    replies = replies_by_id.get(c.get("comment_id"), [])
    if not replies:
        return '<p class="pending meta">edge responde no próximo beat</p>'
    items = "".join(
        f'<li class="reply"><p class="body">{html.escape(r.get("body", ""))}</p></li>'
        for r in replies
    )
    return f'<ul class="replies">{items}</ul>'


def _render_comment(c, replies_by_id):
    body = f'<p class="body">{html.escape(c.get("body", ""))}</p>'
    return f'<li class="comment">{body}{_replies_block(c, replies_by_id)}</li>'


def _render_thread(target_ref):
    comments = _comments(target_ref)
    replies_by_id = _replies()
    if not comments:
        items = '<li class="empty meta">sem comentários ainda</li>'
    else:
        items = "".join(_render_comment(c, replies_by_id) for c in comments)
    return f'<ul class="thread" id="thread-{html.escape(target_ref)}">{items}</ul>'


def _vote_state(slug):
    """The mentee's *current* vote for a slug (single-tenant toggle): the latest `voz.vote`
    value wins → 1 (like), -1 (dislike), or 0 (none). A like is a toggle, capped at 1 — not a
    running sum."""
    state = 0
    for e in _read_events():
        if e.get("type") == "voz.vote" and e.get("payload", {}).get("slug") == slug:
            state = e["payload"].get("value", 0)
    return state


def _render_votes(slug):
    state = _vote_state(slug)
    s = html.escape(slug)

    def btn(val, emoji, cls):
        active = state == val
        return (f'<button type="submit" class="vote {cls}{" active" if active else ""}" '
                f'name="value" value="{val}" aria-pressed="{"true" if active else "false"}">'
                f'{emoji} <span class="count">{1 if active else 0}</span></button>')

    return (
        f'<form class="votes" hx-post="/e/{s}/vote" hx-target="closest .votes" hx-swap="outerHTML">'
        f'{btn(1, "👍", "like")}{btn(-1, "👎", "dislike")}'
        '</form>'
    )


def _render_chat_item(c, replies_by_id):
    target = c.get("target_ref")
    label = (f'<a class="ctx" href="/e/{html.escape(target)}.html">em {html.escape(target)}</a>'
             if target else '<span class="ctx meta">chat geral</span>')
    body = f'<p class="body">{html.escape(c.get("body", ""))}</p>'
    return f'<li class="chat-item">{label}{body}{_replies_block(c, replies_by_id)}</li>'


def _render_chat():
    """The standalone chat: the unfiltered comment timeline, each item labelled by its target."""
    comments = [{**e["payload"], "ts": e.get("ts", "")}
                for e in _read_events() if e.get("type") == "voz.comment"]
    replies_by_id = _replies()
    if not comments:
        items = '<li class="empty meta">sem mensagens ainda</li>'
    else:
        items = "".join(_render_chat_item(c, replies_by_id) for c in comments)
    return f'<ul class="chat">{items}</ul>'


@app.post("/e/<slug>/comment")
def post_comment(slug):
    body = (request.form.get("body") or "").strip()
    if body:
        _append("voz.comment", f"voz:{slug}",
                 {"target_ref": slug, "comment_id": uuid.uuid4().hex[:12], "body": body})
    return _render_thread(slug)


@app.post("/chat/comment")
def post_chat_comment():
    body = (request.form.get("body") or "").strip()
    if body:
        _append("voz.comment", "voz:chat",
                 {"target_ref": None, "comment_id": uuid.uuid4().hex[:12], "body": body})
    return _render_chat()


@app.get("/chat")
def chat():
    form = ('<form class="composer" hx-post="/chat/comment" hx-target="#chat" hx-swap="outerHTML" '
            'hx-on::after-request="this.reset()">'
            '<textarea name="body" placeholder="fale com o edge…" required></textarea>'
            '<button type="submit">enviar</button></form>')
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — chat</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '<script src="https://unpkg.com/htmx.org@1.9.12"></script></head><body>'
        f'<main class="blog"><h1>edge — chat</h1><a class="meta" href="/">← artefatos</a>'
        f'{form}<div id="chat">{_render_chat()}</div></main>'
        "</body></html>"
    )


@app.post("/e/<slug>/vote")
def post_vote(slug):
    clicked = 1 if request.form.get("value") != "-1" else -1
    # toggle: clicking the active button clears it (→0); otherwise set/switch to the clicked value
    new = 0 if _vote_state(slug) == clicked else clicked
    _append("voz.vote", f"voz:{slug}", {"slug": slug, "value": new})
    return _render_votes(slug)


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


def _render_rail(slug):
    """The Voz rail under a post: vote control + comment thread + composer (htmx-wired)."""
    s = html.escape(slug)
    composer = (
        f'<form class="composer" hx-post="/e/{s}/comment" hx-target="#thread-{s}" '
        'hx-swap="outerHTML" hx-on::after-request="this.reset()">'
        '<textarea name="body" placeholder="comente (vira um Directive)…" required></textarea>'
        '<button type="submit">comentar</button></form>'
    )
    return f'<div class="voz">{_render_votes(slug)}{_render_thread(slug)}{composer}</div>'


def _render_post(post):
    slug = html.escape(post["slug"])
    return (
        '<article class="post">'
        f'<h2><a href="/e/{slug}.html">{html.escape(post["title"])}</a></h2>'
        f'<time class="meta">{html.escape(post["date"])}</time>'
        f'<p class="blurb">{html.escape(post["blurb"])}</p>'
        f'{_artifact_items(post)}'
        f'{_render_rail(post["slug"])}'
        '</article>'
    )


@app.get("/")
def index():
    posts = _posts()
    body = "".join(_render_post(p) for p in posts) or '<p class="meta">sem artefatos ainda</p>'
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — artefatos</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '<script src="https://unpkg.com/htmx.org@1.9.12"></script></head><body>'
        '<main class="blog"><h1>edge — artefatos</h1>'
        '<p class="meta"><a href="/chat">chat com o edge →</a></p>'
        f'{body}</main>'
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
