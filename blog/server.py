#!/usr/bin/env python3
"""Blog v0 — serve os artefatos HTML do edge, listados em estilo-blog a partir do eventlog.

O índice é uma PROJEÇÃO do log (ADR-0005: a página re-renderiza do log, sem store paralelo): cada
`artefato.published` vira um post (título, data, blurb do `intent.kernel`) com links para os artefatos
que o dispatch criou (cites/distills/proposes), mais recente primeiro. As entries continuam servidas de
`entries/*.html`. Paths overridáveis por env (EDGE_BLOG_ENTRIES/STATIC/LOG) para teste.
"""
import hashlib
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


# ── Shared header/nav + design system (cross-cutting, starts at Slice 3 per PLAN.md) ────────────
#
# ONE navigation linking every surface — "one app, not a pile of pages". Built from the shared
# style.css design vocabulary (the .meta tokens, the dark theme); the only new component class is
# `.site-nav`, an EXTENSION of the shared set, not a one-off per-surface style. Every read surface
# (blog index, /chat, /briefing) carries the full bar; the full-canvas /cortex carries a corner
# subset (it is a full-screen island, so the bar would fight the canvas).
_NAV_LINKS = (
    ("/", "artefatos"),
    ("/cortex", "cortex"),
    ("/chat", "chat"),
    ("/briefing", "briefing"),
)


def _site_nav(current):
    """The shared header/nav, rendered with the CURRENT surface marked (aria-current="page") so the
    bar reads as one app. `current` is the active path ("/", "/cortex", "/chat", "/briefing")."""
    items = []
    for path, label in _NAV_LINKS:
        active = ' aria-current="page"' if path == current else ""
        items.append(f'<a href="{path}"{active}>{html.escape(label)}</a>')
    return f'<nav class="site-nav">{"".join(items)}</nav>'


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
    """Yield every event in the log, oldest→newest, skipping blanks/garbage. "Garbage" includes a
    JSON-valid but NON-dict line (`[]`, `42`, a bare string) — one of the corruption cases
    log_is_intact rejects: every read fold here indexes events with `e.get(...)`, so a non-dict would
    AttributeError the surface. Since the shared nav routes the mentee across these surfaces, ONE
    corrupt log must not 500 `/` or `/chat` while `/briefing` degrades cleanly (Codex round-4) — so
    the shared iterator skips non-dicts centrally; the health strip still SURFACES the corruption via
    _log_corrupt (log_is_intact over the raw lines), so it is flagged, not silently swallowed."""
    log = _log()
    if not log.is_file():
        return
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            yield e


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


def _comment_idem_key(nonce, body):
    """The idempotency key for a comment append = the render nonce + a digest of the body. The
    nonce alone is stable across a render (it does not advance until the page reloads), so keying
    on it ALONE would dedupe two *distinct* follow-up comments typed into the same still-rendered
    composer into one — silently dropping the second. Binding the body means only a TRUE resubmit
    (same render, identical text — a double-fire) dedupes; a different follow-up is a new key, so it
    appends. Mirrors the vote route, which keys on nonce + the submitted value."""
    if not nonce:
        return None
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{nonce}:{digest}"


def _replies():
    """Fold edge replies keyed by the comment_id they answer."""
    out = {}
    for e in _read_events():
        if e.get("type") == "voz.reply":
            p = e.get("payload", {})
            out.setdefault(p.get("comment_id"), []).append({**p, "ts": e.get("ts", "")})
    return out


def _terminally_resolved():
    """The set of `comment_id`s that have a TERMINAL `voz.resolved` (ADR-0017 / SURFACE.md). This
    — not `voz.reply` presence — is what closes a chat: a `voz.reply` is presentation only, a
    parked `voz.clarify` is non-terminal (the chat stays open). `open_comments()` keys on the
    ABSENCE of a member here."""
    return {
        e.get("payload", {}).get("comment_id")
        for e in _read_events()
        if e.get("type") == "voz.resolved"
    }


def open_comments():
    """The answer queue: every `voz.comment` with no TERMINAL `voz.resolved` yet (any target). A
    fold, not a flag (ADR-0017). A replied-but-unresolved comment is still open; a parked
    `voz.clarify` chat is still open; only a terminal `voz.resolved` closes it."""
    resolved = _terminally_resolved()
    return [
        {**e["payload"], "ts": e.get("ts", "")}
        for e in _read_events()
        if e.get("type") == "voz.comment" and e.get("payload", {}).get("comment_id") not in resolved
    ]


def _clarifications():
    """Fold parked `voz.clarify` questions keyed by the comment_id they ask about, dropping any
    whose `voz.clarify_answer` has already landed (an answered clarify is no longer awaiting the
    mentee). This is what the dashboard renders inline so a parked chat is answerable, not stuck."""
    answered = {e.get("payload", {}).get("clarify_id")
                for e in _read_events() if e.get("type") == "voz.clarify_answer"}
    out = {}
    for e in _read_events():
        if e.get("type") == "voz.clarify":
            p = e.get("payload", {})
            if p.get("clarify_id") in answered:
                continue
            out.setdefault(p.get("comment_id"), []).append(p)
    return out


def _clarify_block(c, clarifies_by_id):
    """The edge's open clarification question(s) under a comment + a pre-linked answer composer (the
    same inline pattern as a reply, SURFACE.md "view/answer a clarification"). The mentee answers
    with a distinct `voz.clarify_answer` child event — never a new `voz.comment`."""
    clarifies = clarifies_by_id.get(c.get("comment_id"), [])
    if not clarifies:
        return ""
    blocks = []
    for q in clarifies:
        qid = html.escape(q.get("clarify_id", ""))
        blocks.append(
            '<li class="clarify">'
            f'<p class="question body">{html.escape(q.get("question", ""))}</p>'
            '<p class="pending meta">aguardando sua resposta</p>'
            f'<form class="composer clarify-answer" hx-post="/clarify/{qid}/answer" '
            'hx-target="closest .thread, closest .chat" hx-swap="outerHTML" '
            'hx-on::after-request="this.reset()">'
            f'<input type="hidden" name="clarify_id" value="{qid}">'
            '<textarea name="body" placeholder="responda ao edge…" required></textarea>'
            '<button type="submit">responder</button></form></li>'
        )
    return f'<ul class="clarifies">{"".join(blocks)}</ul>'


def _replies_block(c, replies_by_id, clarifies_by_id=None):
    """The replies under a comment + any open clarification question, or the 'agent responds next
    beat' affordance if it is open and unanswered. A parked `voz.clarify` renders inline as the
    edge's question with a pre-linked answer composer (ADR-0017: a parked chat stays answerable)."""
    if clarifies_by_id is None:
        clarifies_by_id = _clarifications()
    clarify = _clarify_block(c, clarifies_by_id)
    replies = replies_by_id.get(c.get("comment_id"), [])
    if not replies:
        pending = '' if clarify else '<p class="pending meta">edge responde no próximo beat</p>'
        return f'{pending}{clarify}'
    items = "".join(
        f'<li class="reply"><p class="body">{html.escape(r.get("body", ""))}</p></li>'
        for r in replies
    )
    return f'<ul class="replies">{items}</ul>{clarify}'


def _render_comment(c, replies_by_id, clarifies_by_id=None):
    body = f'<p class="body">{html.escape(c.get("body", ""))}</p>'
    return f'<li class="comment">{body}{_replies_block(c, replies_by_id, clarifies_by_id)}</li>'


def _render_thread(target_ref):
    comments = _comments(target_ref)
    replies_by_id = _replies()
    clarifies_by_id = _clarifications()
    if not comments:
        items = '<li class="empty meta">sem comentários ainda</li>'
    else:
        items = "".join(_render_comment(c, replies_by_id, clarifies_by_id) for c in comments)
    return f'<ul class="thread">{items}</ul>'


def _comment_composer(slug):
    """The per-post comment composer, rendered with the CURRENT fresh nonce. It posts to and swaps
    the whole thread region (thread + this composer), so each successful append re-renders the
    composer with an ADVANCED nonce — a deliberate repeat (same body) then carries a new key and is
    not mistaken for a transport retry (Codex gate: the stable-render-nonce same-body drop)."""
    s = html.escape(slug)
    nonce = html.escape(_comment_nonce(slug))
    return (
        f'<form class="composer" hx-post="/e/{s}/comment" hx-target="#thread-region-{s}" '
        'hx-swap="outerHTML" hx-on::after-request="this.reset()">'
        f'<input type="hidden" name="comment_nonce" value="{nonce}">'
        '<textarea name="body" placeholder="comente (vira um Directive)…" required></textarea>'
        '<button type="submit">comentar</button></form>'
    )


def _thread_region(slug):
    """The swappable per-post region = the thread + a fresh-nonce composer. Returned by the comment
    route so the swap refreshes the composer's nonce on every successful append."""
    s = html.escape(slug)
    return (f'<div class="thread-region" id="thread-region-{s}">'
            f'{_render_thread(slug)}{_comment_composer(slug)}</div>')


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


def _render_chat_item(c, replies_by_id, clarifies_by_id=None):
    target = c.get("target_ref")
    label = (f'<a class="ctx" href="/e/{html.escape(target)}.html">em {html.escape(target)}</a>'
             if target else '<span class="ctx meta">chat geral</span>')
    body = f'<p class="body">{html.escape(c.get("body", ""))}</p>'
    return (f'<li class="chat-item">{label}{body}'
            f'{_replies_block(c, replies_by_id, clarifies_by_id)}</li>')


def _render_chat():
    """The standalone chat: the unfiltered comment timeline, each item labelled by its target."""
    comments = [{**e["payload"], "ts": e.get("ts", "")}
                for e in _read_events() if e.get("type") == "voz.comment"]
    replies_by_id = _replies()
    clarifies_by_id = _clarifications()
    if not comments:
        items = '<li class="empty meta">sem mensagens ainda</li>'
    else:
        items = "".join(_render_chat_item(c, replies_by_id, clarifies_by_id) for c in comments)
    return f'<ul class="chat">{items}</ul>'


def _chat_composer():
    """The standalone-chat composer with the CURRENT fresh nonce. Posts to and swaps the whole chat
    region (timeline + this composer), so each successful append advances the nonce — a deliberate
    same-body repeat then carries a new key and is not deduped as a transport retry."""
    nonce = html.escape(_comment_nonce(None))
    return ('<form class="composer" hx-post="/chat/comment" hx-target="#chat-region" '
            'hx-swap="outerHTML" hx-on::after-request="this.reset()">'
            f'<input type="hidden" name="comment_nonce" value="{nonce}">'
            '<textarea name="body" placeholder="fale com o edge…" required></textarea>'
            '<button type="submit">enviar</button></form>')


def _chat_region():
    """The swappable standalone-chat region = a fresh-nonce composer + the timeline. Returned by the
    chat-comment route so the swap refreshes the composer's nonce on every successful append."""
    return (f'<div class="chat-region" id="chat-region">'
            f'{_chat_composer()}<div id="chat">{_render_chat()}</div></div>')


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
                    idem_key=_comment_idem_key(request.form.get("comment_nonce"), body))
    # Return the whole region (thread + a FRESH-nonce composer) so the swap advances the nonce —
    # a deliberate same-body repeat then carries a new key and is not dropped as a retry.
    return _thread_region(slug)


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
                    idem_key=_comment_idem_key(request.form.get("comment_nonce"), body))
    # The whole region (fresh-nonce composer + timeline) so the swap advances the nonce.
    return _chat_region()


def _clarify_target(clarify_id):
    """Resolve the target_ref of the comment a clarify_id asks about — so the answer route can
    re-render the right projection (the slug thread, or the general chat). Returns (found, target)."""
    comment_of = {}  # clarify_id -> comment_id
    target_of = {}   # comment_id -> target_ref
    for e in _read_events():
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.clarify":
            comment_of[p.get("clarify_id")] = p.get("comment_id")
        elif t == "voz.comment":
            target_of[p.get("comment_id")] = p.get("target_ref")
    cid = comment_of.get(clarify_id)
    if cid is None:
        return False, None
    return True, target_of.get(cid)


@app.post("/clarify/<clarify_id>/answer")
def post_clarify_answer(clarify_id):
    """Answer a parked `voz.clarify` with a DISTINCT child event `voz.clarify_answer` (SURFACE.md /
    ADR-0017) — never a `voz.comment`, so it never opens a new chat or re-enters the backlog. Rides
    the Slice-1 auth gate + body-size limit (it mutates the authoritative log). Re-renders the
    comment's projection (slug thread or general chat) so the inline question is resolved."""
    if not authorize_write():
        abort(403)
    if _reject_oversized_body():
        abort(413)
    found, target = _clarify_target(clarify_id)
    if not found:
        abort(404)  # an answer for a clarify that does not exist — a forged child ref
    body = (request.form.get("body") or "").strip()
    if body:
        # Single-writer per clarify_id (idem key = the clarify_id ALONE, not clarify_id+body): a
        # parked question has ONE answer, so a stale-tab/retry with DIFFERENT text is dropped under
        # the lock — never a second, conflicting voz.clarify_answer the close could resolve on the
        # wrong one (the answer the drain snapshotted is the only answer there can be). First wins.
        _append_voz("voz.clarify_answer", f"voz:{target or 'chat'}",
                    {"clarify_id": clarify_id, "body": body},
                    idem_key=f"clarify-answer:{clarify_id}")
    return _render_thread(target) if target else _render_chat()


@app.get("/chat")
def chat():
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — chat</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '<script src="https://unpkg.com/htmx.org@1.9.12"></script></head><body>'
        f'{_site_nav("/chat")}'
        f'<main class="blog"><h1>edge — chat</h1>'
        f'{_chat_region()}</main>'
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
    published, kernels = [], {}
    for e in _read_events():  # the shared iterator — skips blanks/garbage AND non-dict lines (round-4)
        t, p = e.get("type"), e.get("payload") or {}
        if not isinstance(p, dict):
            continue
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
    """The Voz rail under a post: vote control + the thread region (thread + fresh-nonce composer)."""
    return f'<div class="voz">{_render_votes(slug)}{_thread_region(slug)}</div>'


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
        f'{_site_nav("/")}'
        '<main class="blog"><h1>edge — artefatos</h1>'
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


def _json_for_script(payload):
    """Serialize a payload as JSON safe to embed in a `<script>` data block. A `<script
    type="application/json">` is raw-text until the parser hits a `</script` (case-insensitive), and
    a bare `<`/`>` plus the JSON line separators U+2028/U+2029 are the script-context breakout
    vectors. We escape `<`, `>`, `&` (as unicode escapes JSON still parses) and the separators —
    case-independent and complete, so a graph node title carrying `</SCRIPT><script>…` (titles
    derive from Direction/Source/Entity content) can never break out and drive a same-origin
    mutating POST, which would defeat the Slice-1 write gate."""
    out = (json.dumps(payload)
           .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    # U+2028 / U+2029 are valid in JSON strings but break a <script> data block — escape them.
    out = out.replace(chr(0x2028), "\\u2028").replace(chr(0x2029), "\\u2029")
    return out


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
        data = _json_for_script(payload)  # XSS-safe to embed in a <script> data block
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
        f'{_site_nav("/cortex")}'
        '<p class="meta">surf the agent\'s brain — pan, zoom, clique num nó. '
        'space-0 é o núcleo; o brilho cai com a confiança.</p></header>'
        f'<main class="cortex-main">{graph}</main>'
        f'{island}'
        '</body></html>'
    )


# ── Briefing surface + read-model health strip (Slice 3, SURFACE.md §"Briefing", AUDIT.md gap A) ──
#
# The self-state landing: render `tools/briefing.py::compose_briefing` — the EXACT text the edge
# wakes to (Memento's tattoo) — as the wake artifact, no mentee-specific recomposition (SURFACE.md:
# "reuses the wake artifact, no drift"). ⚠️ COST: compose_briefing is a PURE FOLD over the log +
# genotype — it makes NO LLM/API call. The two non-log legs that could touch the world are pinned
# to their non-generating values on render: clusters=None (the Tier-0 value — never _AUTO, which
# would navigate neo4j) and recap=None (a slot marker, never an LLM-synthesized recap). So rendering
# /briefing costs ZERO API spend (the operator just got burned on spend — this route is paranoid).
#
# Above the briefing sits the read-model HEALTH STRIP — the degraded-mode signal a composed briefing
# cannot give (a briefing can read plausible while the folds beneath it are stale: SURFACE.md cites a
# real wake where the sweep degraded to swept_sessions:0 yet the briefing composed clean). It folds
# the log independently of the composer, and fails DARK (a visible degraded band), never blank.


def _briefing_paths():
    """The genotype inputs compose_briefing reads (agent.yaml + memory/), env-overridable for tests
    (CONTRACT C1: a test points these at a throwaway genotype, never real state/). Unset → the
    install's real genotype (the briefing IS the install's self-state)."""
    from pathlib import Path as _P
    agent_yaml = os.environ.get("EDGE_BRIEFING_AGENT_YAML")
    memory = os.environ.get("EDGE_BRIEFING_MEMORY")
    return (_P(agent_yaml) if agent_yaml else None, _P(memory) if memory else None)


def _compose_briefing_text():
    """Call tools/briefing.compose_briefing as a PURE projection of THIS dashboard's log — clusters
    and recap pinned to None so the render makes ZERO API/LLM call (and never even probes neo4j).
    Returns the composed markdown string, or None on a fail-closed genotype error (a thin agent.yaml /
    absent doctrine) so the route can render dark rather than 500 (CONTRACT C1: degrade this view)."""
    sys.path.insert(0, str(BASE.parent / "tools"))
    import briefing
    agent_yaml, memory = _briefing_paths()
    kwargs = {"log": _log(), "clusters": None, "recap": None}
    if agent_yaml is not None:
        kwargs["agent_yaml"] = agent_yaml
    if memory is not None:
        kwargs["memory"] = memory
    try:
        # roster reads agent.yaml too — resolve it INSIDE the catch (Codex [medium]): a thin/malformed
        # override agent.yaml makes source_roster raise BriefingIdentityError, which must fail DARK
        # here exactly like the default path (where compose_briefing resolves the roster under its own
        # fail-closed), never escape to a 500.
        if agent_yaml is not None:
            kwargs["roster"] = briefing.source_roster(agent_yaml=agent_yaml)
        return briefing.compose_briefing(**kwargs)
    except briefing.BriefingIdentityError:
        return None
    except Exception:
        return None


def _dict_events():
    """`_read_events()` filtered to dict envelopes only — a JSON-VALID but schema-drifted line (`[]`,
    `42`, a bare string) parses fine yet has no `.get`, so a fold that calls `e.get(...)` on it would
    crash (Codex [high]). The health-strip folds read through this so a corrupt/upgraded log degrades
    DARK, never 500s the landing (the same posture the drain takes on a schema-drifted line)."""
    return (e for e in _read_events() if isinstance(e, dict))


def _log_corrupt():
    """True when the authoritative log is NOT intact — reusing the ONE strict integrity predicate the
    drain gates on (`grill_drain.log_is_intact`): a malformed (non-JSON) line, a JSON-valid non-dict,
    a missing/non-int/non-contiguous `seq` (a gap forges a duplicate seq under append_batch), or a
    poisoned payload field. Codex round-3 [high]: the strip's own `_read_events()` SILENTLY DROPS a
    JSONDecodeError line, so a truly malformed line was invisible — /briefing could read healthy while
    the drain refuses to run (the Voz write path is dead). Sharing log_is_intact gives the strip and
    the drain ONE corruption model, so a corrupt log SURFACES as degraded instead of hiding. NEVER
    raises — a probe failure is itself a degraded signal (returns True)."""
    try:
        import grill_drain
        return not grill_drain.log_is_intact(_log())
    except Exception:
        return True


def _last_dispatch():
    """The newest `dispatch.open` (the wake stamp, ADR-0016): {ts, swept_sessions} or None. The
    `swept_sessions` is the documented degrade signal — a value of 0 is a degraded sweep (a
    context-window overflow swept nothing) even though the briefing composes clean."""
    last = None
    for e in _dict_events():
        if e.get("type") == "dispatch.open":
            last = e
    if last is None:
        return None
    payload = last.get("payload")
    swept = payload.get("swept_sessions") if isinstance(payload, dict) else None
    return {"ts": last.get("ts", ""), "swept_sessions": swept}


def _log_cursor():
    """The log cursor = the max seq in the log (the read-model's currency). 0 on an empty log. Only
    INT seqs count — a schema-drifted dict event with a string/list `seq` (Codex round-2 [high]) is
    skipped, never fed to max() (mixed-type max raises), so a corrupt log degrades deterministically."""
    return max((e["seq"] for e in _dict_events()
                if isinstance(e.get("seq"), int)), default=0)


def _graph_reachable():
    """A CHEAP, BOUNDED graph-reachability probe for the health strip (neo4j only, NEVER an LLM —
    zero API spend). Distinct from cortex_fold() (which loads the WHOLE graph): the strip only needs
    a yes/no, so a single `RETURN 1` under a short connection timeout suffices and an unreachable
    neo4j degrades fast (a few seconds), not a 60s hang on the landing. The Cortex fixture seam wins
    when set, so tests stay hermetic (a fixture means the dashboard renders the graph → reachable).
    Returns True/False; NEVER raises (a dark graph is a degraded signal, not a crash)."""
    if os.environ.get("EDGE_CORTEX_FIXTURE"):
        return True
    group = _group()
    if not group:
        return False
    uri = os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = os.environ.get("EDGE_NEO4J_PASSWORD") or _neo4j_password()
    try:
        from neo4j import GraphDatabase
        drv = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3,
                                   connection_acquisition_timeout=3, max_transaction_retry_time=0)
        try:
            with drv.session() as s:
                s.run("RETURN 1").consume()
            return True
        finally:
            drv.close()
    except Exception:
        return False


def _degraded_strip(reason):
    """The fail-dark fallback the health strip renders when its OWN fold raises — a fully-degraded band
    (`degraded: True`) rather than a 500. The strip's whole job is to be the degraded-mode signal, so
    it must itself never crash the landing (Codex round-1/2 [high]). The bad-state is carried as
    explicit `*_bad` booleans (not derived from the displayed values with `> 0`), so the renderer never
    compares a string placeholder with an int — that chained TypeError was the round-2 finding."""
    return {"dispatch_ts": None, "log_cursor": "—", "swept_sessions": None,
            "swept_degraded": True, "graph_reachable": False, "open_directives": "—",
            "voz_backlog": "—", "voz_backlog_bad": True, "awaiting_clarification": "—",
            "consistency_errors": "—", "consistency_bad": True,
            "degraded": True, "fold_error": reason}


def health_strip_data():
    """Fold the read-model health strip from the log (SURFACE.md §Briefing "read-model health strip").
    Every metric is a fold, no parallel store. `degraded` is the fail-dark flag: True when any signal
    is degraded (a swept-nothing sweep, an unreachable graph, or a resolution-consistency error) — the
    band renders visibly degraded, never blank. NEVER raises (a degraded/corrupt read-model is the
    very thing the strip signals): a fold exception (e.g. a schema-drifted log line) returns the
    fully-degraded fallback, not a 500 (Codex [high])."""
    import grill_drain
    try:
        log = _log()
        # dispatch + cursor read through _dict_events() (schema-drift safe — Codex [high]).
        dispatch = _last_dispatch()
        swept = dispatch.get("swept_sessions") if dispatch else None
        log_cursor = _log_cursor()
        # Graph reachability — a CHEAP, BOUNDED probe (neo4j only, never an LLM): a single RETURN 1
        # under a short timeout, so an unreachable neo4j degrades fast rather than hanging the landing.
        graph_reachable = _graph_reachable()
        try:
            open_directives = len(grill_drain.open_comments(log))
            actionable = len(grill_drain.actionable_set(log))
            awaiting = open_directives - actionable  # parked voz.clarify with no answer
            consistency = grill_drain.consistency_errors(log)
        except Exception:
            # the Voz folds degraded — surface it as a degraded strip rather than crashing the landing.
            open_directives = actionable = awaiting = 0
            consistency = [{"kind": "voz-fold-degraded"}]
        backlog = max(open_directives - awaiting, 0)  # eligible-but-unloaded overflow (actionable)
        swept_degraded = swept == 0  # the documented degrade: a sweep that swept nothing
        log_corrupt = _log_corrupt()  # the same integrity model the drain gates on — surface, don't hide
        degraded = (swept_degraded or (not graph_reachable) or bool(consistency) or log_corrupt)
        return {
            "dispatch_ts": dispatch["ts"] if dispatch else None,
            "log_cursor": log_cursor,
            "swept_sessions": swept,
            "swept_degraded": swept_degraded,
            "graph_reachable": graph_reachable,
            "open_directives": open_directives,
            "voz_backlog": backlog,
            "voz_backlog_bad": backlog > 0,
            "awaiting_clarification": awaiting,
            "consistency_errors": len(consistency),
            "consistency_bad": bool(consistency),
            "degraded": degraded,
        }
    except Exception as e:
        # the read-model fold itself raised (a corrupt log past what _dict_events filters) — fail DARK.
        return _degraded_strip(f"{type(e).__name__}")


def _metric(label, key, value, bad=False):
    """One health-strip cell: a labelled metric carrying a stable data-metric hook (for tests + a
    future poller) and a `bad` flag that paints the degraded ones."""
    cls = "metric bad" if bad else "metric"
    return (f'<span class="{cls}"><span class="m-label">{html.escape(label)}</span>'
            f'<span class="m-val" data-metric="{key}">{html.escape(str(value))}</span></span>')


def _render_health_strip():
    """The compact health band above the briefing — the degraded-mode signal. Fails DARK: a degraded
    fold paints the band `degraded` (a visible amber state), never a blank. Each cell folds the log."""
    h = health_strip_data()
    dispatch = h["dispatch_ts"][:19].replace("T", " ") if h["dispatch_ts"] else "—"
    swept = h["swept_sessions"] if h["swept_sessions"] is not None else "—"
    graph = "reachable" if h["graph_reachable"] else "DARK"
    cells = [
        _metric("last dispatch", "last-dispatch", dispatch),
        _metric("log cursor", "log-cursor", h["log_cursor"]),
        _metric("swept sessions", "swept-sessions", swept, bad=h["swept_degraded"]),
        _metric("graph", "graph-reachable", graph, bad=not h["graph_reachable"]),
        _metric("open Directives", "open-directives", h["open_directives"]),
        # bad-state from explicit booleans (never re-derived with `> 0` — a degraded fallback carries
        # string placeholders, and comparing those with an int would TypeError → 500, Codex round-2).
        _metric("Voz backlog", "voz-backlog", h["voz_backlog"], bad=h["voz_backlog_bad"]),
        _metric("awaiting clarify", "awaiting-clarification", h["awaiting_clarification"]),
        _metric("consistency errors", "consistency-errors", h["consistency_errors"],
                bad=h["consistency_bad"]),
    ]
    cls = "health-strip degraded" if h["degraded"] else "health-strip"
    note = ('<p class="health-note meta">read-model degraded — a fold beneath the briefing is stale '
            'or failing (a swept-nothing sweep, an unreachable graph, or a resolution-consistency '
            'error). The composed briefing may read clean regardless.</p>') if h["degraded"] else ""
    return (f'<section class="{cls}" aria-label="read-model health">'
            f'<h2 class="health-title">read-model health</h2>'
            f'<div class="health-metrics">{"".join(cells)}</div>{note}</section>')


@app.get("/briefing")
def briefing_surface():
    """The self-state landing: the read-model health strip (degraded-mode signal) above the composed
    wake-briefing (Memento's tattoo — exactly what the edge wakes to). A PURE projection — ZERO API
    spend on render (compose_briefing is a fold; clusters/recap pinned to None). Fails DARK (a visible
    degraded band), never blank, when a fold degrades."""
    strip = _render_health_strip()
    text = _compose_briefing_text()
    if text is None:
        # compose_briefing failed closed (a thin genotype) — render DARK, not a 500. The health strip
        # still renders (it folds the log independently of the composer).
        briefing_block = ('<section class="briefing-dark"><h2>briefing — dark</h2>'
                          '<p class="meta">A briefing não pôde compor: identidade genótipo fina '
                          '(agent.yaml/memory). É fail-closed — resolva a identidade do install '
                          '(ADR-0009). O health strip acima ainda projeta do log.</p></section>')
    else:
        briefing_block = f'<pre class="briefing-text">{html.escape(text)}</pre>'
    return (
        '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
        '<title>edge — briefing</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '<script src="https://unpkg.com/htmx.org@1.9.12"></script></head><body>'
        f'{_site_nav("/briefing")}'
        '<main class="blog briefing-page"><h1>edge — briefing</h1>'
        '<p class="meta">a self-state landing — exatamente o que o edge lê ao acordar '
        '(Memento\'s tattoo), com o health strip do read-model acima.</p>'
        f'{strip}{briefing_block}</main>'
        '</body></html>'
    )


# ── Slice 2 — the grill drain route (POST /grill/drain), behind the Slice-1 auth gate ───────────
#
# The drain directs answers back on its own (the grill_drain module). This HTTP entry point sits
# behind authorize_write() exactly like every other log-mutating route (a drain appends to the
# authoritative log). ⚠️ COST: the reply-generator hits the edge's chat router (gpt-5.4 on the
# user's OpenAI API), billed per call. So the route NEVER spends by default — a live drain runs only
# when the operator opts in with EDGE_DRAIN_LIVE=1 (otherwise 503, no append). Tests inject a stub
# via DRAIN_REPLY_GENERATOR (zero real LLM calls). The drain itself can also run as a local-only
# tool: `grill_drain.drain(log, grill_drain.live_reply_generator())`.

# A test/local seam: when set (callable(comment)->plan), the route uses it instead of the live
# generator — so the suite drives the route end-to-end with NO API spend.
DRAIN_REPLY_GENERATOR = None


@app.post("/grill/drain")
def grill_drain_route():
    if not authorize_write():
        abort(403)  # per Slice 1 — unauthenticated / cross-origin → rejected, no append
    import grill_drain
    # The lifecycle switch (open_comments keys on voz.resolved) is live the moment this ships, so the
    # legacy back-fill must run INDEPENDENTLY of the reply generator — else an upgraded install with
    # historical voz.reply-only comments shows them as open until a (possibly never-run) live drain.
    # Idempotent + lock-guarded, so running it on every drain (incl. the no-generator path) is free
    # after the first and cannot reopen/reprocess (ADR-0017: the switch ships WITH the back-fill).
    # Fail-soft (same contract as the startup migration): a malformed/schema-drifted legacy line must
    # not 500 the route — degrade to the controlled response, never crash before it.
    # Validate the authoritative log up front, with the SAME strict parse the canonical append uses
    # to stamp seqs. A malformed/schema-drifted line makes any append raise (a miscounted base seq
    # corrupts the source of truth), so we degrade BEFORE building or calling any reply generator (no
    # API spend), before the back-fill, before any close — independent of whether there is a legacy
    # back-fill target (the back-fill returns early with no target and so cannot be the detector).
    if not grill_drain.log_is_intact(_log()):
        return (json.dumps({"status": "migration-degraded", "backfill": "degraded",
                            "detail": "the event log has a malformed line; no drain performed, no "
                                      "append, no generator invoked — resolve the log first"}),
                503, {"Content-Type": "application/json"})
    # Log is intact → run the guarded migration. (Kept fail-soft as a belt-and-suspenders backstop;
    # on an intact log it cannot raise.) drain() below is called with run_backfill=False so it never
    # re-enters the unguarded back-fill.
    migrate_ok = True
    try:
        grill_drain.backfill_legacy_resolved(_log())
    except Exception:
        migrate_ok = False
    if not migrate_ok:
        return (json.dumps({"status": "migration-degraded", "backfill": "degraded",
                            "detail": "legacy back-fill could not complete; no drain, no append"}),
                503, {"Content-Type": "application/json"})
    reply_fn = DRAIN_REPLY_GENERATOR
    if reply_fn is None:
        if os.environ.get("EDGE_DRAIN_LIVE") != "1":
            # Default: refuse to spend the user's OpenAI API. The migration already ran above; this
            # path appends no reply (no generator) — only the lifecycle back-fill, which is correct.
            return (json.dumps({"status": "no-generator", "backfill": "ok",
                                "detail": "live drain disabled (set EDGE_DRAIN_LIVE=1 to spend the "
                                          "edge OpenAI API); legacy back-fill applied"}),
                    503, {"Content-Type": "application/json"})
        reply_fn = grill_drain.live_reply_generator()  # ⚠️ spends the user's OpenAI API
    # run_backfill=False: the guarded migration above already ran — never re-enter it unguarded here.
    loaded = grill_drain.drain(_log(), reply_fn, run_backfill=False)
    return (json.dumps({"status": "drained", "backfill": "ok",
                        "loaded": [c.get("comment_id") for c in loaded]}),
            200, {"Content-Type": "application/json"})


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


def _migrate_voz_lifecycle():
    """Startup migration (ADR-0017): run the idempotent legacy back-fill BEFORE any open_comments()
    projection is exposed, so the read-side switch (openness keys on terminal voz.resolved) never
    shows a historical voz.reply-only chat as open. Independent of the drain / reply generator.
    Idempotent + lock-guarded, fail-soft (a missing/locked log must not crash server startup).

    Gated by log_is_intact (the SAME strict check the route uses): on a corrupt / seq-gapped log the
    back-fill must NOT run — append_batch stamps from base=len(read()), so on a gapped log it would
    forge a DUPLICATE seq and worsen the authoritative log. A corrupt log degrades (stays as-is);
    the route surfaces it (backfill: degraded)."""
    try:
        import grill_drain
        if grill_drain.log_is_intact(_log()):
            grill_drain.backfill_legacy_resolved(_log())
    except Exception:
        pass  # never block startup on the migration; the route also back-fills as a backstop


# Migrate on import so the very first read surface (index / chat) already reflects the switch.
_migrate_voz_lifecycle()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("BLOG_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLOG_PORT", str(DEFAULT_PORT))),
    )
