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
import sys
import uuid
from pathlib import Path

from flask import Flask, abort, request, send_from_directory

BASE = Path(__file__).resolve().parent

# Route writes through the canonical, locked eventlog append (ADR-0006), never a hand-rolled
# scan-for-max-seq-then-append (a race that forges duplicate seqs in the source of truth).
sys.path.insert(0, str(BASE.parent / "tools"))
import eventlog  # noqa: E402

app = Flask(__name__)

# The default bind port (app.run + the origin allowlist default share this single source of truth,
# so the operator on the default URL is never rejected by an allowlist that drifted from app.run).
DEFAULT_PORT = 8766
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1", "[::1]")

# Body-size cap for a Voz write — a comment is prose, not a payload. Oversized → rejected, no
# append (defends the authoritative log against a flooded body). SURFACE.md: "a body-size limit".
MAX_BODY_BYTES = 8 * 1024
# Coarse outer guard: Flask rejects a request whose declared body exceeds this BEFORE parsing
# (so a flooded write never even materializes a form). Sits above MAX_BODY_BYTES to leave room for
# the form envelope / url-encoding; the prose itself is capped at MAX_BODY_BYTES on the parsed field.
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

# ── Voz write trust boundary (Slice 1, SURFACE.md / AUDIT.md gap B) ─────────────────────────────
#
# Every voz.* write mutates the authoritative log, so it sits behind a single-tenant auth gate +
# CSRF/origin check + target_ref validation + a body-size limit (ADR-0017: "the mentee's private,
# authed surface — a single trusted author"; SURFACE.md hardens that to *enforced, not assumed*).
# The gate rejects spoofing (cross-origin / unauthenticated), NOT the legitimate local mentee:
#   - a same-origin request from localhost is auto-granted (the operator on 127.0.0.1:<port>);
#   - a configured EDGE_DASH_TOKEN authorizes a reverse-proxied principal (X-Edge-Token);
#   - the request Origin/Referer must match the dashboard's own host (CSRF/cross-origin defense).
# Test seam: EDGE_DASH_AUTH = "on" (real gate) | "off" (disabled, pre-Slice-1) | "test:<who>"
# (a fixed authorized principal, no cookie dance).


def _auth_mode():
    return (os.environ.get("EDGE_DASH_AUTH") or "on").strip()


def _request_is_local():
    """The legitimate single-tenant operator: a request whose peer is loopback. The dashboard
    binds 127.0.0.1 (agent.yaml blog_host), so a loopback peer IS the local mentee — auto-granted,
    never gated against the operator. remote_addr is the socket peer (spoof-resistant for a
    bound-local server: a cross-origin browser cannot forge the TCP peer)."""
    addr = request.remote_addr or ""
    return addr in ("127.0.0.1", "::1", "localhost")


def _allowed_hosts():
    """The allowlist of host[:port] values that ARE this dashboard — what a legitimate same-origin
    Origin/Host must match. EDGE_DASH_ORIGIN (explicit, comma-separated) wins; else the configured
    bind host:port plus the loopback names. We validate against THIS set, never the request's own
    Host header (an attacker controls Host under DNS rebinding — matching request.host to itself is
    no check at all)."""
    explicit = os.environ.get("EDGE_DASH_ORIGIN")
    if explicit:
        # Normalize each entry to scheme-stripped host[:port] (the same shape _origin_ok compares),
        # so a configured `https://edge.example` matches an Origin of `https://edge.example`.
        return {_hostpart(h.strip()) for h in explicit.split(",") if h.strip()}
    host = os.environ.get("BLOG_HOST", "127.0.0.1")
    port = os.environ.get("BLOG_PORT", str(DEFAULT_PORT))
    hosts = {f"{host}:{port}", host}
    for name in LOOPBACK_NAMES:
        hosts.add(f"{name}:{port}")
        hosts.add(name)
    return hosts


def _host_is_loopback():
    """The request's CLAIMED host is a loopback name → it really is the operator's own browser on
    this box, not a public host a loopback reverse-proxy peer forwarded. The auto-grant keys on
    THIS (not the TCP peer alone): behind Caddy `reverse_proxy localhost:<port>` every external
    client is a loopback peer, so a peer-only auto-grant would let any public visitor write."""
    name = _hostpart(request.host).rsplit(":", 1)[0]
    return name in LOOPBACK_NAMES


def _hostpart(url_or_authority):
    """The host[:port] authority from a URL or a bare Host value (strip scheme + path)."""
    tail = url_or_authority.split("//", 1)[-1]
    return tail.split("/", 1)[0]


def _origin_ok():
    """CSRF / cross-origin + DNS-rebinding defense: a state-changing POST must come from an
    ALLOWLISTED dashboard origin. Both the request's own Host and its Origin/Referer must be in the
    allowlist — validating against the allowlist (not against request.host) is what defeats DNS
    rebinding, where the attacker's rebound name sends a matching Host AND Origin from a loopback
    peer. A cross-origin page (CSRF) carries the attacker's Origin → not in the allowlist → rejected."""
    allowed = _allowed_hosts()
    # The request's claimed Host must itself be a known dashboard host (defeats rebinding).
    if _hostpart(request.host) not in allowed:
        return False
    origin = request.headers.get("Origin")
    if origin:
        return _hostpart(origin) in allowed
    referer = request.headers.get("Referer")
    if referer:
        return _hostpart(referer) in allowed
    # No Origin/Referer (a non-browser client, e.g. curl from the box) — fall back to the peer
    # check: a loopback peer is the operator's own tool, not a cross-origin browser.
    return _request_is_local()


def authorize_write():
    """The single gate every log-mutating route calls. Returns the authorized principal (truthy)
    or None (reject → 403). Order: explicit test principal → disabled → configured token → local
    operator. CSRF/origin is enforced for any non-test, non-disabled grant.

    Route-agnostic by design: the future Slice-2 `POST /grill/drain` (a log-mutating route) is
    covered simply by calling this gate — no per-route auth. If the drain instead ships as a
    local-only tool (no HTTP endpoint), there is no public surface to gate. Either way the boundary
    holds: every HTTP write goes through `authorize_write()`."""
    mode = _auth_mode()
    if mode.startswith("test:"):
        return mode.split(":", 1)[1] or "test"
    if mode == "off":
        return "disabled"
    # Real gate: must pass the CSRF/origin check first (a cross-origin POST is rejected even if it
    # somehow carried a token — the token is for the reverse proxy's same-origin principal).
    if not _origin_ok():
        return None
    token = os.environ.get("EDGE_DASH_TOKEN")
    if token and request.headers.get("X-Edge-Token") == token:
        return "token"
    # The local-operator auto-grant requires BOTH a loopback peer AND a loopback claimed Host: the
    # peer rules out a remote socket, the Host rules out a public name forwarded by a loopback proxy
    # peer (Caddy). A forwarded public host must carry the token, never ride the loopback auto-grant.
    if _request_is_local() and _host_is_loopback():
        return "local"
    return None


def _published_slugs():
    """The set of slugs in the published fold — the only valid `target_ref`s. A vote/comment for a
    slug absent from this fold is a forged target (log poisoning), not a write."""
    return {
        e.get("payload", {}).get("slug", "")
        for e in _read_events()
        if e.get("type") == "artefato.published"
    }


def _reject_oversized_body():
    """Body-size limit: a comment is prose, not a payload. Reject (no append) when the comment body
    exceeds the cap. Measured on the parsed `body` field (the prose the mentee wrote), so the cap is
    on what lands in the log, not on the form envelope. The Flask-level MAX_CONTENT_LENGTH is the
    coarse outer guard against a flooded request before parsing. Returns True → reject."""
    body = request.form.get("body") or ""
    return len(body.encode("utf-8")) > MAX_BODY_BYTES


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
    """Append ONE event through the canonical, locked eventlog primitive (ADR-0006) — monotonic
    seq under an flock, never a scan-for-max-seq-then-append (a race that forges duplicate seqs in
    the source of truth). The blog's log path (EDGE_BLOG_LOG, test-overridable) is passed through."""
    return eventlog.append(type_, subject, payload, log=_log())


def _append_voz(type_, subject, payload, idem_key=None):
    """A Voz write: the canonical locked append, with an OPTIONAL idempotency key that dedupes a
    double-click / retry. The key check runs as the eventlog `precondition` — evaluated UNDER the
    lock against the durable log, so it is authoritative (not a TOCTOU fast-fail): a concurrent
    retry with the same key cannot slip a duplicate in. The key is stored on the payload so a replay
    of the log can re-derive the dedupe. Returns the stamped event, or the existing one on a dup."""
    if not idem_key:
        return eventlog.append(type_, subject, payload, log=_log())

    payload = {**payload, "idem_key": idem_key}

    def _not_already_appended():
        for e in _read_events():
            if e.get("type") == type_ and e.get("payload", {}).get("idem_key") == idem_key:
                raise _DuplicateWrite(e)

    try:
        return eventlog.append_batch(
            [(type_, subject, payload)], log=_log(), precondition=_not_already_appended)[0]
    except _DuplicateWrite as dup:
        return dup.event


class _DuplicateWrite(Exception):
    """Raised under the eventlog lock when an idempotency key already exists — aborts the append
    with nothing written, and carries the existing event so the route returns the same result."""

    def __init__(self, event):
        super().__init__("duplicate idempotency key")
        self.event = event


def _comments(target_ref):
    """Fold the comment thread for a target (slug, or None for the general chat)."""
    return [
        {**e["payload"], "ts": e.get("ts", "")}
        for e in _read_events()
        if e.get("type") == "voz.comment" and e.get("payload", {}).get("target_ref") == target_ref
    ]


def _comment_nonce(target_ref):
    """The render nonce for a comment composer's idempotency key: the thread's comment count,
    stable across one render and advancing after each successful comment. A double-click on the
    same render dedupes to one Directive; a deliberate second comment (count advanced) is distinct."""
    n = sum(1 for _ in _comments(target_ref))
    return f"comment:{target_ref}:{n}"


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


def _vote_count(slug):
    """How many `voz.vote` events this slug has — the render-state nonce for the vote idempotency
    key (advances on each successful append, so it's stable across one render but distinct after a
    deliberate new toggle)."""
    return sum(1 for e in _read_events()
               if e.get("type") == "voz.vote" and e.get("payload", {}).get("slug") == slug)


def _vote_state(slug):
    """The mentee's *current* vote for a slug (single-tenant toggle): the latest `voz.vote`
    value wins → 1 (like), -1 (dislike), or 0 (none). A like is a toggle, capped at 1 — not a
    running sum."""
    state = 0
    for e in _read_events():
        if e.get("type") == "voz.vote" and e.get("payload", {}).get("slug") == slug:
            state = e["payload"].get("value", 0)
    return state


def _vote_nonce(slug):
    """The render nonce for the vote idempotency key: stable across one render, advances on each
    successful vote (the count). Combined with the submitted value in the route, it dedupes a
    same-button double-click while keeping a 👍-then-👎 from one render as two distinct actions."""
    return f"vote:{slug}:{_vote_count(slug)}"


def _render_votes(slug):
    state = _vote_state(slug)
    s = html.escape(slug)
    nonce = html.escape(_vote_nonce(slug))

    def btn(val, emoji, cls):
        active = state == val
        return (f'<button type="submit" class="vote {cls}{" active" if active else ""}" '
                f'name="value" value="{val}" aria-pressed="{"true" if active else "false"}">'
                f'{emoji} <span class="count">{1 if active else 0}</span></button>')

    return (
        f'<form class="votes" hx-post="/e/{s}/vote" hx-target="closest .votes" hx-swap="outerHTML">'
        f'<input type="hidden" name="idem_nonce" value="{nonce}">'
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
    if not authorize_write():
        abort(403)
    if slug not in _published_slugs():
        abort(404)  # forged target_ref — a slug absent from the published fold
    if _reject_oversized_body():
        abort(413)
    body = (request.form.get("body") or "").strip()
    if body:
        _append_voz("voz.comment", f"voz:{slug}",
                    {"target_ref": slug, "comment_id": uuid.uuid4().hex[:12], "body": body},
                    idem_key=request.form.get("comment_nonce"))
    return _render_thread(slug)


@app.post("/chat/comment")
def post_chat_comment():
    if not authorize_write():
        abort(403)
    if _reject_oversized_body():
        abort(413)
    body = (request.form.get("body") or "").strip()
    if body:
        _append_voz("voz.comment", "voz:chat",
                    {"target_ref": None, "comment_id": uuid.uuid4().hex[:12], "body": body},
                    idem_key=request.form.get("comment_nonce"))
    return _render_chat()


@app.get("/chat")
def chat():
    nonce = html.escape(_comment_nonce(None))
    form = ('<form class="composer" hx-post="/chat/comment" hx-target="#chat" hx-swap="outerHTML" '
            'hx-on::after-request="this.reset()">'
            f'<input type="hidden" name="comment_nonce" value="{nonce}">'
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
    if not authorize_write():
        abort(403)
    if slug not in _published_slugs():
        abort(404)  # a vote always targets a publication — reject a forged slug
    clicked = 1 if request.form.get("value") != "-1" else -1
    # toggle: clicking the active button clears it (→0); otherwise set/switch to the clicked value
    new = 0 if _vote_state(slug) == clicked else clicked
    # Dedup key = the render nonce + the clicked value, so a same-button double-click dedupes but
    # a 👍-then-👎 from one render are two distinct actions (different value → different key).
    nonce = request.form.get("idem_nonce")
    idem = f"{nonce}:{clicked}" if nonce else None
    _append_voz("voz.vote", f"voz:{slug}", {"slug": slug, "value": new}, idem_key=idem)
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
    nonce = html.escape(_comment_nonce(slug))
    composer = (
        f'<form class="composer" hx-post="/e/{s}/comment" hx-target="#thread-{s}" '
        'hx-swap="outerHTML" hx-on::after-request="this.reset()">'
        f'<input type="hidden" name="comment_nonce" value="{nonce}">'
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
        '<p class="meta"><a href="/chat">chat com o edge →</a> · '
        '<a href="/cortex">surf the brain (cortex) →</a></p>'
        f'{body}</main>'
        "</body></html>"
    )


# ── Cortex graph — surf the agent's brain (SURFACE.md §"Cortex graph") ──────────────────────────
#
# A read-only fold of the WHOLE Cortex, group_id-scoped and fail-dark, shipped as one {nodes, edges}
# JSON payload to a Cytoscape JS island (loaded only on this view, never the app shell). The island
# draws a dark, force-directed constellation centered on space-0, with trust-weighted brightness:
# space-0 brightest → asserted spine bright → extracted Entity/Source dim → Episodic faintest.
# Live fold per request: one Cypher query → JSON → island; pan/zoom/click is client-side, no re-query.

# Trust tier per label (the brightness axis). Genesis (space-0) is its own tier — the luminous core.
_TRUST_BY_LABEL = {
    "Genesis": "space0",
    "Objective": "asserted", "Direction": "asserted", "Artefato": "asserted",
    "Entity": "extracted", "Source": "extracted",
    "Episodic": "episodic",
}

# The human-readable title per label — what a clicked node shows (inspect node, v1).
_TITLE_FIELDS = {
    "Genesis": ("codename",),
    "Objective": ("body",),
    "Direction": ("body",),
    "Artefato": ("slug",),
    "Entity": ("name",),
    "Source": ("name", "source_description", "key"),
    "Episodic": ("name", "summary"),
}

# The whole-Cortex fold, group-scoped on BOTH endpoints of every edge. We never run a graph-wide
# MATCH: the fleet co-locates installs in one neo4j keyed by group_id, so an unscoped query would
# leak another install's brain — and render as a *successful* graph, not an obvious failure. Nodes
# and edges are two scoped passes so an isolated (edgeless) node still renders.
_CORTEX_NODES_QUERY = (
    "MATCH (n {group_id:$g}) "
    "RETURN elementId(n) AS id, labels(n)[0] AS label, properties(n) AS props"
)
_CORTEX_EDGES_QUERY = (
    "MATCH (a {group_id:$g})-[r]->(b {group_id:$g}) "
    "RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target, type(r) AS type"
)


def _cortex_fixture():
    """The TDD seam: EDGE_CORTEX_FIXTURE points at a {nodes, edges} JSON file. Set → the fold reads
    it (no live neo4j); unset → live neo4j. Returns the parsed payload or None."""
    path = os.environ.get("EDGE_CORTEX_FIXTURE")
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _node_title(label, props):
    """One human-readable line for a node (inspect node, v1) — first non-empty title field, else
    the label. Truncated so the payload stays light."""
    for field in _TITLE_FIELDS.get(label, ()):
        val = props.get(field)
        if val:
            return _blurb(str(val), 140)
    return label


def _map_node(id_, label, props):
    """One Cortex node → the render payload: id, label, a human title, its trust tier (the
    brightness axis), and the earmarked flag (the harm overlay — passed through so the overlay is
    wired end-to-end; harm overrides the dim regardless of trust tier)."""
    return {
        "id": id_,
        "label": label,
        "title": _node_title(label, props),
        "trust": _TRUST_BY_LABEL.get(label, "extracted"),
        "earmarked": bool(props.get("earmarked")),
    }


def _cortex_live(group):
    """Fold the WHOLE Cortex for `group` from neo4j into {nodes, edges}. group_id-scoped on every
    node and both edge endpoints. Returns the payload, or None on a genuine degrade (no driver,
    graph unreachable). NEVER raises (the dark leg darkens only this view, like recall's CONTRACT C1)."""
    uri = os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = os.environ.get("EDGE_NEO4J_PASSWORD") or _neo4j_password()
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None
    try:
        drv = GraphDatabase.driver(uri, auth=(user, password))
    except Exception:
        return None
    try:
        with drv.session() as s:
            nodes = [_map_node(r["id"], r["label"], r["props"])
                     for r in s.run(_CORTEX_NODES_QUERY, g=group).data()]
            edges = [{"id": r["id"], "source": r["source"], "target": r["target"], "type": r["type"]}
                     for r in s.run(_CORTEX_EDGES_QUERY, g=group).data()]
            return {"nodes": nodes, "edges": edges}
    except Exception:
        return None
    finally:
        try:
            drv.close()
        except Exception:
            pass


def _neo4j_password():
    """The install's neo4j password via _identity (genotype tool), or the env fallback. Imported
    lazily so the blog runs even where tools/ is absent."""
    try:
        sys.path.insert(0, str(BASE.parent / "tools"))
        import _identity
        return _identity.neo4j_password()
    except Exception:
        return os.environ.get("EDGE_NEO4J_PASSWORD")


def _group():
    """The install's graph group_id via _identity (EDGE_GROUP → agent.yaml). None if unresolved →
    the fold goes dark rather than running an unscoped, cross-install query."""
    try:
        sys.path.insert(0, str(BASE.parent / "tools"))
        import _identity
        return _identity.group()
    except Exception:
        return os.environ.get("EDGE_GROUP") or None


_GROUP_AUTO = object()


def cortex_fold(group=_GROUP_AUTO):
    """The whole-Cortex fold for this install: {nodes, edges} or None (dark). The fixture seam wins
    when set (tests, no live neo4j); else it resolves the install group_id and reads live neo4j,
    fail-dark if the group is absent (NEVER a graph-wide MATCH — cross-install isolation is the
    group_id, enforced at the query). `group` defaults to the resolved install identity."""
    fixture = _cortex_fixture()
    if fixture is not None:
        return fixture
    if group is _GROUP_AUTO:
        group = _group()
    if not group:
        return None
    return _cortex_live(group)


def _cortex_dark():
    """The honest dark state — no group or neo4j unreachable. Never an unscoped graph, never a 500."""
    return (
        '<section class="cortex-dark"><h2>cortex — dark</h2>'
        '<p class="meta">O grafo está escuro: sem group_id resolvido ou neo4j inacessível. '
        'A projeção é group-scoped e fail-closed — nunca uma query graph-wide. '
        'Resolva a identidade do install (EDGE_GROUP / agent.yaml) e confirme o neo4j.</p></section>'
    )


@app.get("/cortex")
def cortex():
    """Surf the agent's brain: the whole Cortex as a dark, force-directed constellation centered on
    space-0, trust-weighted, read-only. One live fold → a Cytoscape island; pan/zoom/click client-side."""
    payload = cortex_fold()
    if payload is None:
        graph = _cortex_dark()
        island = ""
    else:
        graph = '<div id="cortex"></div>'
        data = json.dumps(payload).replace("</", "<\\/")  # safe to embed in <script>
        island = (
            '<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>'
            f'<script id="cortex-data" type="application/json">{data}</script>'
            '<script src="/static/cortex.js"></script>'
        )
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — cortex</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '</head><body class="cortex-page">'
        '<header class="cortex-head"><h1>edge — cortex</h1>'
        '<a class="meta" href="/">← artefatos</a>'
        '<p class="meta">surf the agent\'s brain — pan, zoom, clique num nó. '
        'space-0 é o núcleo; o brilho cai com a confiança.</p></header>'
        f'<main class="cortex-main">{graph}</main>'
        f'{island}'
        '</body></html>'
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
        port=int(os.environ.get("BLOG_PORT", str(DEFAULT_PORT))),
    )
