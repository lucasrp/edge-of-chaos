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
import re
import sys
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory
from markupsafe import Markup

BASE = Path(__file__).resolve().parent

# Route writes through the canonical, locked eventlog append (ADR-0006), never a hand-rolled
# scan-for-max-seq-then-append (a race that forges duplicate seqs in the source of truth).
sys.path.insert(0, str(BASE.parent / "tools"))
import eventlog  # noqa: E402
import llm_routes  # noqa: E402 — o registry por-rota que o painel /llm consome (issue #55)

app = Flask(__name__)  # template_folder=blog/templates, static_folder=blog/static (the scaffold)

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
    ("/direction", "direction"),
    ("/docs", "docs"),
    ("/wiki", "wiki"),
    ("/llm", "llm"),
    ("/sources", "sources"),
    ("/ux-catalog", "ux-catalog"),
)


def _page(template, **ctx):
    """Render a full page through the Jinja scaffold (`base.html` + the shared head/nav partials),
    threading the standard context every surface shares (`nav_links` for the bar, `current` for the
    active marker). A surface passes its own page template (under `pages/`) + its fold context; any
    pre-rendered fragment HTML it threads in is wrapped Markup so Jinja does not double-escape it.
    The shared nav is ONE source of truth: every page (and the cortex head) includes
    `partials/nav.html` with these `nav_links` (the Slice-7 #37 contract)."""
    return render_template(template, nav_links=_NAV_LINKS, **ctx)


def _safe(html_str):
    """Wrap server-rendered fragment HTML (the existing f-string render helpers — thread regions,
    health strip, …) as Markup so the page template injects it verbatim. The fragment builders
    already html-escape every log-derived value at the boundary, so this re-marks ALREADY-safe HTML;
    it never trusts raw user input (that is escaped upstream in `_esc`/`html.escape`)."""
    return Markup(html_str)


def _published_slugs():
    """The set of slugs in the published fold — the only valid `target_ref`s. A vote/comment for a
    slug absent from this fold is a forged target (log poisoning), not a write."""
    return {
        e.get("payload", {}).get("slug", "")
        for e in _read_events()
        if e.get("type") == "artefato.published"
    }


# ── Node-targeted Voz — the Earmarked corrective write-path (Slice 6b, SURFACE.md / AUDIT.md gap D) ─
#
# A correction `target_ref` addresses a Cortex NODE directly, beyond the slug namespace: it carries
# the `node:<node_id>` prefix. A slug never contains `:` (publisher's SLUG_RE), so this is
# unambiguous against a bare-slug target_ref — the existing slug validation is untouched. The node
# ref is VALID iff <node_id> is a node in the group_id-scoped cortex payload (cortex_fold, already
# scoped + fail-dark): an unknown/forged node ref — or any ref while the graph is dark — fails closed,
# so the correction is rejected with NO append (the same trust posture as the slug allowlist).
_NODE_REF_PREFIX = "node:"

# The harm score stamped on a node-targeted correction (codex Slice-6b round-3 [medium]). An
# Earmarked correction is harm work BY CONSTRUCTION, so it must outrank the drain's keyword scan
# ceiling (the count of _HARM_MARKERS a body could hit) — set above it so a neutrally-worded
# correction loads before unrelated keyword-rich chatter, never overflowing the harm frontier.
_CORRECTION_HARM = 100.0


def _is_node_target_ref(target_ref):
    """True when a `target_ref` is a Cortex node ref (`node:<id>`) rather than a bare slug."""
    return isinstance(target_ref, str) and target_ref.startswith(_NODE_REF_PREFIX)


def _node_id_of(target_ref):
    """The `<node_id>` of a `node:<id>` target_ref (the part after the prefix)."""
    return target_ref[len(_NODE_REF_PREFIX):]


def _resolve_node_target_ref(target_ref):
    """Resolve a node `target_ref` to its matched EARMARKED node from ONE group-scoped cortex read
    (codex Slice-6b round-6 [medium]: validation + snapshot from the SAME fold, no TOCTOU window
    where the graph degrades between two reads and lands a correction without its node context).
    Returns the matched node dict (carrying title/label/ref) or None — fail-closed on a dark graph,
    an unknown node, or a non-Earmarked node:
      - the EARMARKED requirement is load-bearing (SURFACE.md: Earmarked is the harm frontier;
        CONTEXT.md: an inert node is navigable, not correctable) — a non-Earmarked target would
        expand Voz corrective authority beyond the harm-settled subset;
      - match on the STABLE `ref` (codex round-4), falling back to the render `id` for a raw fixture
        payload that carries no ref;
      - `earmarked is True` (not truthy): fail closed on type so schema drift ("false"/"0"/1) never
        crosses the boundary (codex round-2)."""
    if not _is_node_target_ref(target_ref):
        return None
    node_id = _node_id_of(target_ref)
    if not node_id:
        return None
    payload = cortex_fold()
    if not payload:
        return None  # fail-closed: a dark graph cannot vouch for any node
    for n in payload.get("nodes", []):
        matches = (n.get("ref") == node_id or (n.get("ref") is None and n.get("id") == node_id))
        if matches and n.get("earmarked") is True:
            return n
    return None


def _valid_node_target_ref(target_ref):
    """A node `target_ref` is valid iff it resolves to an Earmarked node in the group-scoped cortex
    payload (`_resolve_node_target_ref`) — fail-closed. Thin wrapper kept for the validation seam."""
    return _resolve_node_target_ref(target_ref) is not None


def _node_snapshot_of(node):
    """A durable {node_title, node_label} snapshot from an ALREADY-RESOLVED node (one read, no second
    fold). Persisted on the correction comment so the resolver/audit carries usable node context
    without a live graph lookup when the drain runs (the node may be reprojected / the graph dark by
    then) — a natural 'this claim is wrong' is settled against the actual claim, not a context-less
    body.

    node_title is the CLAIM `content` (no label fallback, codex round-7 [high]): a bare Earmarked node
    maps to a display title of its LABEL ("Entity"), which is NOT claim context — keying the snapshot
    on `content` keeps the route's missing-context gate truly fail-closed. A raw fixture node that
    predates the `content` field (no `content` key at all) falls back to its display `title`."""
    claim = node.get("content") if "content" in node else node.get("title")
    snap = {}
    if claim:
        # Bound the persisted claim (codex Slice-6b round-8 [high]): the full claim rides into the
        # live prompt (no truncation of the harmful clause), but an UNBOUNDED extracted claim could
        # blow the prompt/token budget — and with harm=100 the correction sits at the head of every
        # drain, wedging the corrective path (ADR-0017's max-tokens cap / never-an-oversized-prompt).
        # Cap at the same MAX_BODY_BYTES "prose, not a payload" bound the rest of the Voz write path
        # uses: comfortably larger than any realistic extracted claim, bounded by construction.
        snap["node_title"] = _cap_bytes(_as_str(claim), MAX_BODY_BYTES)
    if node.get("label"):
        snap["node_label"] = _as_str(node["label"])
    return snap


def _cap_bytes(text, limit):
    """Truncate `text` to at most `limit` UTF-8 bytes WITHOUT splitting a multibyte char (encode →
    slice → decode-ignore drops a dangling partial). Used to bound a persisted node claim so it can
    never blow the corrective drain's prompt budget (codex round-8)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", "ignore")


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
        if not isinstance(e, dict):
            continue
        yield _normalize_event(e)


# The payload fields the read folds use as a dict/set KEY (comment_id, clarify_id, slug, target_ref)
# or HTML-escape (body, question). log_is_intact rejects a corrupt-typed one, but the tolerant read
# boundary still yields the event — and a non-str KEY is unhashable (TypeError in a fold) while a
# non-str escape input crashes html.escape. Coercing these to str at the ONE shared boundary makes
# EVERY downstream fold safe over a corrupt log (Codex round-6), instead of guarding N fold sites.
#
# Direction KEY fields (id / supersedes / dropped-id) are DELIBERATELY NOT here: coercing a corrupt
# `id: ["bad"]` to the string "['bad']" would make eventlog.fold_direction FOLD it as an active
# curated steer — promoting POISONED data onto the trusted surface (codex Slice-4 round-2 [high]).
# The canonical fold instead SKIPS a non-string key field (fail-dark); the route relies on that, and
# coerces only display values (origin_comment_id/direction_id) at render time via _anchor_id/_esc.
_COERCE_STR_FIELDS = ("comment_id", "clarify_id", "slug", "target_ref", "body", "question")


def _normalize_event(e):
    """Make a yielded event safe for the tolerant read folds over a corrupt log (Codex round-4/5/6):
    a corrupt (non-dict) `payload` → {} (folds do `.get`/`**payload` on it); a corrupt-typed key/escape
    field → str (a non-str dict/set key is unhashable; a non-str escape input crashes html.escape).
    Returns a shallow-normalized copy; the ORIGINAL log is untouched, so _log_corrupt() (log_is_intact
    over the raw lines) still SURFACES the corruption as degraded — normalized for render, flagged for
    truth. `target_ref` is coerced only when PRESENT-and-non-None (None is the valid general-chat key)."""
    payload = e.get("payload")
    if not isinstance(payload, dict):
        return {**e, "payload": {}}
    fixes = {}
    for f in _COERCE_STR_FIELDS:
        v = payload.get(f)
        if v is None:
            continue  # absent, or a valid None target_ref — leave it
        if not isinstance(v, str):
            fixes[f] = str(v)
    return {**e, "payload": {**payload, **fixes}} if fixes else e


def _as_str(value):
    """Coerce a payload-derived value to a str (round-6): a corrupt-typed field — a slug/ts that is a
    list/int — would crash a string op (`.replace`, slicing, a dict key) downstream of the tolerant
    read boundary. Coercing keeps a corrupt log renderable (200); the strip still flags it degraded."""
    return value if isinstance(value, str) else str(value)


def _as_list(value):
    """Coerce a payload artifact field (cites/distills/proposes) to a list (round-7): a non-list value
    (`cites: 1`) is corruption log_is_intact does NOT reject, but _artifact_items iterates it →
    TypeError. None/falsy → []; a list passes through; any other scalar → [] (a corrupt scalar is not
    a meaningful single artifact, so drop it rather than render a bogus chip)."""
    return value if isinstance(value, list) else []


def _esc(value):
    """HTML-escape a payload-derived value, COERCING a non-string to str first. log_is_intact rejects
    a corrupt-typed field (e.g. a `voz.comment` whose `body` is a list), but the read boundary still
    yields that event — so a render fold that did `html.escape(corrupt_field)` would TypeError → 500
    on a shared surface (Codex round-6). Coerce-then-escape renders the corrupt field INERT (a 200),
    while the health strip flags the log degraded (log_is_intact over the raw log). Use this for any
    value sourced from a log payload; `html.escape` directly is fine for known-str literals/labels."""
    return html.escape(value if isinstance(value, str) else str(value))


def _anchor_id(prefix, value):
    """A stable, HTML-safe, INJECTIVE fragment id (`{prefix}-{sanitized}-{hash}`) for a drill-down
    anchor — used on BOTH ends of a steer⇄comment link so the href fragment and the target element id
    agree exactly. An id (a direction_id / comment_id) is normally a uuid-hex slug, but a
    corrupt/legacy one can carry whitespace or unsafe chars; an HTML `id` with a space is invalid and
    breaks the anchor. So collapse every non-[a-zA-Z0-9_-] run to a single `-` for a readable prefix,
    then append a short digest of the ORIGINAL value so distinct ids never collide (codex Slice-4
    round-5 [med]: `a:b`/`a/b`/`a b` all sanitize to `a-b` — a lossy collapse would drill the marker
    into the wrong steer). Same input → same output at both ends, so the anchor still matches. Coerce
    a non-str first (corrupt log, fail-dark)."""
    value = value if isinstance(value, str) else str(value)
    sanitized = re.sub(r'[^a-zA-Z0-9_-]+', '-', value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{sanitized}-{digest}"


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


def _folded_directions():
    """Map `comment_id` → the `direction_id` of the steer it folded into, from every
    `voz.resolved {outcome: folded-to-direction}` (SURFACE.md / ADR-0017). This is the comment→steer
    half of the bidirectional Voz→Direction link: the Direction surface links a steer back to its
    origin comment; the Voz rail uses THIS to link a folded Directive forward to /direction, so 'did
    my steer land?' is answerable from the comment too."""
    return {
        e.get("payload", {}).get("comment_id"): e.get("payload", {}).get("direction_id")
        for e in _read_events()
        if e.get("type") == "voz.resolved"
        and e.get("payload", {}).get("outcome") == "folded-to-direction"
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


def _clarify_block(c, clarifies_by_id, surface="thread"):
    """The edge's open clarification question(s) under a comment + a pre-linked answer composer (the
    same inline pattern as a reply, SURFACE.md "view/answer a clarification"). The mentee answers
    with a distinct `voz.clarify_answer` child event — never a new `voz.comment`.

    `surface` is the ancestor the answer form's htmx swap REPLACES — "thread" under a post (the
    `<ul class="thread">` the answer route re-renders) or "chat" in the standalone chat (the
    `<ul class="chat">`). htmx `hx-target` takes ONE extended selector, NOT a comma list (codex
    Slice-7 round-3 [high]): the old `closest .thread, closest .chat` parsed as `closest` + the
    malformed selector `.thread, closest .chat`, so on /chat (a `.chat` ancestor, no `.thread`) the
    target failed to resolve and a general parked clarify could never be answered from the UI. Each
    surface now emits the SINGLE `closest .<surface>` for an ancestor that actually exists there."""
    clarifies = clarifies_by_id.get(c.get("comment_id"), [])
    if not clarifies:
        return ""
    target = f"closest .{surface}"
    blocks = []
    for q in clarifies:
        qid = _esc(q.get("clarify_id", ""))
        blocks.append(
            '<li class="clarify">'
            f'<p class="question body">{_esc(q.get("question", ""))}</p>'
            '<p class="pending meta">aguardando sua resposta</p>'
            f'<form class="composer clarify-answer" hx-post="/clarify/{qid}/answer" '
            f'hx-target="{target}" hx-swap="outerHTML" '
            'hx-on::after-request="this.reset()">'
            f'<input type="hidden" name="clarify_id" value="{qid}">'
            # the SUBMITTING surface, so the answer route returns the matching fragment (chat vs
            # thread) — /chat renders slug-/node-targeted comments too, so target_ref alone can't tell
            # a chat submission from a thread one (codex Slice-7 round-4 [high]).
            f'<input type="hidden" name="surface" value="{html.escape(surface)}">'
            '<textarea name="body" placeholder="responda ao edge…" required></textarea>'
            '<button type="submit">responder</button></form></li>'
        )
    return f'<ul class="clarifies">{"".join(blocks)}</ul>'


def _folded_marker(c, folded_by_id):
    """The comment→steer half of the bidirectional Voz→Direction link: when this Directive folded
    into a curated steer (`voz.resolved{folded-to-direction}`), an inline marker drilling into
    /direction (SURFACE.md: 'renders the link bidirectionally, steer ⇄ originating comment'). The
    Direction surface links the steer back here; this links here forward to the steer. None otherwise."""
    if folded_by_id is None or c.get("comment_id") not in folded_by_id:
        return ""
    did = folded_by_id.get(c.get("comment_id"))
    # the fragment is sanitized via _anchor_id so it matches the steer element's id on /direction
    # (FIX 2: the marker used to point at #steer-{id} with no matching element — a dead anchor).
    anchor = f'#{_anchor_id("steer", did)}' if did else ""
    return (f'<p class="folded-marker meta">dobrado num steer · '
            f'<a href="/direction{anchor}">ver em Direction →</a></p>')


def _replies_block(c, replies_by_id, clarifies_by_id=None, folded_by_id=None, surface="thread"):
    """The replies under a comment + any open clarification question, or the 'agent responds next
    beat' affordance if it is open and unanswered. A parked `voz.clarify` renders inline as the
    edge's question with a pre-linked answer composer (ADR-0017: a parked chat stays answerable). A
    Directive that folded into a steer carries an inline link to /direction (the bidirectional link).
    `surface` ("thread"|"chat") is the swap ancestor the clarify form targets — see `_clarify_block`."""
    if clarifies_by_id is None:
        clarifies_by_id = _clarifications()
    if folded_by_id is None:
        folded_by_id = _folded_directions()
    clarify = _clarify_block(c, clarifies_by_id, surface)
    folded = _folded_marker(c, folded_by_id)
    replies = replies_by_id.get(c.get("comment_id"), [])
    if not replies:
        pending = '' if (clarify or folded) else '<p class="pending meta">edge responde no próximo beat</p>'
        return f'{pending}{clarify}{folded}'
    items = "".join(
        f'<li class="reply"><p class="body">{_esc(r.get("body", ""))}</p></li>'
        for r in replies
    )
    return f'<ul class="replies">{items}</ul>{clarify}{folded}'


def _render_comment(c, replies_by_id, clarifies_by_id=None, folded_by_id=None):
    # the stable per-comment anchor (FIX 3): a steer's provenance link drills into /chat#comment-{id},
    # and the post thread carries the same id so the originating comment is reachable in either view.
    anchor = html.escape(_anchor_id("comment", c.get("comment_id", "")))
    body = f'<p class="body">{_esc(c.get("body", ""))}</p>'
    # surface="thread": a post thread's clarify answer swaps the <ul class="thread"> the route returns.
    return (f'<li class="comment" id="{anchor}">{body}'
            f'{_replies_block(c, replies_by_id, clarifies_by_id, folded_by_id, surface="thread")}</li>')


def _render_thread(target_ref):
    comments = _comments(target_ref)
    replies_by_id = _replies()
    clarifies_by_id = _clarifications()
    folded_by_id = _folded_directions()  # computed once per render, threaded through (not per-comment)
    if not comments:
        items = '<li class="empty meta">sem comentários ainda</li>'
    else:
        items = "".join(_render_comment(c, replies_by_id, clarifies_by_id, folded_by_id) for c in comments)
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


def _target_ctx_label(target):
    """The chat item's context label for a comment's `target_ref`. Three cases:
      - a node ref (`node:<ref>`, Slice 6b): a Cortex-aware label drilling into /cortex — NEVER a
        `/e/node:….html` publication link (codex round-5 [medium]: a node correction is the harm
        item, and Direction provenance drills into /chat, so the audit path must reach the NODE, not
        a dead slug). The node ref also rides the /cortex search so the operator can locate the node.
      - a slug ref: the publication link into its blog entry (unchanged).
      - None: the general chat."""
    if _is_node_target_ref(target):
        node_id = _node_id_of(target)
        # /cortex?node=<ref> — a node-aware drill-down (the search island centers it); the ref is
        # url-encoded into a query param, html-escaped for the attribute (graph-derived, defensive).
        from urllib.parse import quote
        href = f"/cortex?node={quote(node_id, safe='')}"
        return (f'<a class="node-ctx ctx" href="{html.escape(href)}">'
                f'correção de nó · {_esc(node_id)}</a>')
    if target:
        return f'<a class="ctx" href="/e/{_esc(target)}.html">em {_esc(target)}</a>'
    return '<span class="ctx meta">chat geral</span>'


def _render_chat_item(c, replies_by_id, clarifies_by_id=None, folded_by_id=None):
    # the stable per-comment anchor (FIX 3): the chat renders EVERY comment, so a steer's provenance
    # link targets /chat#comment-{id} and this is the element it centers (sanitized via _anchor_id).
    anchor = html.escape(_anchor_id("comment", c.get("comment_id", "")))
    label = _target_ctx_label(c.get("target_ref"))
    body = f'<p class="body">{_esc(c.get("body", ""))}</p>'
    # surface="chat": the standalone chat has a .chat ancestor (no .thread), so the clarify answer
    # form swaps the <ul class="chat"> the answer route returns — see _clarify_block (round-3 [high]).
    return (f'<li class="chat-item" id="{anchor}">{label}{body}'
            f'{_replies_block(c, replies_by_id, clarifies_by_id, folded_by_id, surface="chat")}</li>')


def _render_chat():
    """The standalone chat: the unfiltered comment timeline, each item labelled by its target."""
    comments = [{**e["payload"], "ts": e.get("ts", "")}
                for e in _read_events() if e.get("type") == "voz.comment"]
    replies_by_id = _replies()
    clarifies_by_id = _clarifications()
    folded_by_id = _folded_directions()  # computed once per render, threaded through (not per-comment)
    if not comments:
        items = '<li class="empty meta">sem mensagens ainda</li>'
    else:
        items = "".join(_render_chat_item(c, replies_by_id, clarifies_by_id, folded_by_id) for c in comments)
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
    # Return the fragment for the SUBMITTING surface, not the comment's target_ref (codex Slice-7
    # round-4 [high]): /chat renders slug-/node-targeted comments too, so a clarify answered from the
    # chat must get back the <ul class="chat"> timeline — returning _render_thread(target) would let
    # htmx swap the whole chat list with a single-thread projection, dropping the timeline. The form
    # carries a validated `surface`; absent/unknown falls back to the target-based projection (a
    # post-thread or general chat), preserving the pre-round-4 behavior for any non-form caller.
    surface = request.form.get("surface")
    if surface == "chat":
        return _render_chat()
    if surface == "thread":
        return _render_thread(target)
    return _render_thread(target) if target else _render_chat()


@app.get("/chat")
def chat():
    return _page("pages/chat.html", current="/chat", htmx=True, chat_region=_safe(_chat_region()))


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
    intent = " ".join(_as_str(intent or "").split())
    return intent if len(intent) <= n else intent[:n].rstrip() + "…"


def _posts():
    """Project the eventlog into blog posts, newest-first.

    Folds `artefato.published` (slug + the artifacts it created) joined to its `intent.kernel`
    (the blurb). The log is append-order (oldest→newest); we reverse for newest-first.
    """
    published, kernels, teasers = [], {}, {}
    for e in _read_events():  # the shared iterator — skips blanks/garbage AND non-dict lines (round-4)
        t, p = e.get("type"), e.get("payload") or {}
        if not isinstance(p, dict):
            continue
        if t == "artefato.published":
            # coerce slug/ts to str + artifact fields to lists (round-6/7): a corrupt-typed slug/ts
            # would crash .replace()/[:10]; a non-list cites/distills/proposes (e.g. `cites: 1`, which
            # log_is_intact does NOT reject) would TypeError _artifact_items' iteration — a corrupt log
            # must still render 200 (the strip flags it degraded).
            published.append({
                "slug": _as_str(p.get("slug", "")),
                "ts": _as_str(e.get("ts", "")),
                "cites": _as_list(p.get("cites")),
                "distills": _as_list(p.get("distills")),
                "proposes": _as_list(p.get("proposes")),
            })
        elif t == "intent.kernel":
            kernels[_as_str(p.get("slug", ""))] = p.get("intent", "")
        elif t == "artefato.teaser":
            # a chamada de blog emitida junto com o artefato; last-write-wins re-teasers
            teasers[_as_str(p.get("slug", ""))] = _as_str(p.get("text", ""))
    posts = [{
        **a,
        "title": a["slug"].replace("-", " "),
        "date": a["ts"][:10],
        "blurb": _blurb(kernels.get(a["slug"], "")),
        "teaser": teasers.get(a["slug"], ""),
    } for a in published]
    posts.reverse()
    return posts


def _render_rail(slug):
    """The Voz rail under a post: vote control + the thread region (thread + fresh-nonce composer)."""
    return f'<div class="voz">{_render_votes(slug)}{_thread_region(slug)}</div>'


def _teaser_html(post):
    """A chamada como <p> por parágrafo (layout A); sem teaser, cai no blurb do kernel."""
    if post.get("teaser"):
        paras = [p.strip() for p in post["teaser"].split("\n\n") if p.strip()]
        return '<div class="teaser">' + "".join(
            f"<p>{html.escape(p)}</p>" for p in paras) + "</div>"
    return f'<p class="blurb">{html.escape(post["blurb"])}</p>'


def _render_post(post):
    slug = html.escape(post["slug"])
    return (
        '<article class="post">'
        f'<h2><a href="/e/{slug}.html">{html.escape(post["title"])}</a></h2>'
        f'<time class="meta">{html.escape(post["date"])}</time>'
        f'{_teaser_html(post)}'
        f'<p class="readmore"><a href="/e/{slug}.html">ler o artefato &rarr;</a></p>'
        f'{_render_rail(post["slug"])}'
        '</article>'
    )


@app.get("/")
def index():
    posts = _posts()
    body = "".join(_render_post(p) for p in posts) or '<p class="meta">sem artefatos ainda</p>'
    return _page("pages/index.html", current="/", htmx=True, posts_html=_safe(body))


# ── /ux-catalog — the living style guide (Slice 7 #37, docs/frontend.md §"UX Catalog") ───────────
#
# A self-documenting page: the design TOKENS (parsed LIVE from style.css :root, so the catalog can
# never drift from the actual stylesheet), the shared component VOCABULARY rendered as real
# instances (composer, vote pills, artifact chips, threads, steer cards, health metrics), and the
# Jinja MACROS in components/ui.html. "Antes de criar um componente, cheque o /ux-catalog."

# The :root token name → value pairs, e.g. (--accent, #7aa2f7). Letters/digits/hyphen names, any
# value up to the `;`. Parsed from the FIRST :root block (the identity source of truth).
_ROOT_TOKEN_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _design_tokens():
    """The design tokens (name, value) parsed LIVE from style.css's first `:root` block — so the
    /ux-catalog documents the ACTUAL stylesheet, never a hand-copied list that drifts. Returns an
    ordered list; an unreadable/absent stylesheet degrades to [] (the catalog still renders)."""
    try:
        css = (_static() / "style.css").read_text()
    except OSError:
        return []
    start = css.find(":root")
    if start == -1:
        return []
    block = css[start:css.find("}", start)]
    seen, tokens = set(), []
    for name, value in _ROOT_TOKEN_RE.findall(block):
        if name in seen:
            continue
        seen.add(name)
        tokens.append((name, value.strip()))
    return tokens


# The macro names registered in components/ui.html — listed on the catalog so a builder can find a
# reusable component before authoring a one-off. (The names mirror the `{% macro %}` defs there.)
_UI_MACROS = ("badge", "nav_pill", "action_button", "steer", "metric", "inspect_panel",
              "connects_to_pill")


@app.get("/ux-catalog")
def ux_catalog():
    """The living style guide: the design tokens (live from style.css), the shared component
    vocabulary rendered as real instances, and the Jinja macros. Read-only; zero API spend."""
    return _page("pages/ux_catalog.html", current="/ux-catalog",
                 tokens=_design_tokens(), macros=_UI_MACROS)


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


def _node_content(label, props):
    """The node's FULL CLAIM content — its first non-empty original content field (name/body/summary/
    slug/key, per _TITLE_FIELDS), whitespace-normalized but NOT truncated (codex Slice-6b round-8
    [high]: the corrective snapshot is the claim the resolver settles against — a harmful clause past
    the display-blurb cutoff must reach it, or a standing fold acts on incomplete context). Returns
    None when ABSENT (codex round-7 [high]): distinct from `_node_title`, which falls back to the bare
    LABEL — a label is NOT claim context, so the fail-closed missing-context gate keys on THIS."""
    for field in _TITLE_FIELDS.get(label, ()):
        val = props.get(field)
        if val:
            return " ".join(str(val).split())  # normalized, full — never truncated for the claim
    return None


def _node_title(label, props):
    """One human-readable DISPLAY line for a node (inspect node, v1) — the claim content (truncated to
    a light blurb), else the label (a display fallback so a contextless node still has a visible line).
    NOT corrective claim context — the correction snapshot uses the FULL `_node_content` (no truncation,
    no label fallback), see codex round-7/8."""
    content = _node_content(label, props)
    return _blurb(content, 140) if content else label


# A canonical artefato slug (publisher.SLUG_RE): lowercase alphanumerics + hyphens, no leading/
# trailing hyphen. A graph/log-derived slug that is NOT this shape is poisoned — never turned into a
# live href (codex round-1 [high]: a slug carrying `" onclick=...` must not reach the URL).
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _cluster_slug(label):
    """wiki_render's canonical cluster-slug rule (letters only — drops spaces, &, digits,
    punctuation), the ONE rule the wiki projection names its `cluster-<slug>.html` pages by. Mirrors
    publisher._cluster_slug so a Cortex Entity's `curated_cluster` drills into the matching /wiki page
    (`Introspective memory` → `introspectivememory` → /wiki/introspectivememory). Letters-only by
    construction, so a quote / handler / path char in the source label is dropped before it is a URL."""
    return re.sub(r"[^a-z]", "", (label or "").lower())


def _node_href(label, props):
    """The drill-down URL for a Cortex node → its source surface, so the graph stops being a
    disconnected island (AUDIT.md gap C, PLAN.md Slice 5b). Each maps to a REAL route:
      - Artefato (`slug`)            → /e/<slug>.html        (its blog entry)
      - Direction (`body`, no id)    → /direction            (the steer surface — the node has no
                                                              event id, so the robust target is the
                                                              scannable list, a real route)
      - Source (`key`)               → /docs/source-roadmap  (the source doc: what the edge reads)
      - Entity with `curated_cluster`→ /wiki/<cluster-slug>  (clusters are not graph nodes in v1; an
                                                              Entity bearing a curated_cluster IS the
                                                              cluster's graph presence)
    A node with no source surface (a bare Entity, Episodic, Genesis, Objective) → None (no dead
    link). The values are graph-derived, so coerce + URL-shape defensively (no breakout)."""
    if label == "Artefato":
        slug = props.get("slug")
        # only a CANONICAL slug (publisher's shape) becomes a live href — a poisoned slug carrying a
        # quote / handler / path char is not route-shaped, so it drills nowhere (no breakout vector).
        return f"/e/{slug}.html" if isinstance(slug, str) and _SLUG_RE.match(slug) else None
    if label == "Direction":
        return "/direction" if props.get("body") else None
    if label == "Source":
        return "/docs/source-roadmap" if (props.get("key") or props.get("name")) else None
    if label == "Entity":
        cluster = props.get("curated_cluster")
        slug = _cluster_slug(str(cluster)) if cluster else ""
        return f"/wiki/{slug}" if slug else None
    return None


# The recency stamp per node (Slice 6 filter axis), in priority order:
#   - `projected_at` — the Artefato projection's recency stamp (tools/publisher.py: the signal
#     recall-push orders by). The live Artefato node carries ONLY this, so it must come first or a
#     recent published Artefato would serialize ts:null and the recency filter would drop it
#     (codex round-3 [medium]).
#   - `created_at` / `valid_at` — Graphiti's extracted-layer stamps.
#   - `ts` — a plain fallback (fixtures / any spine node carrying one).
# First present wins — no extra query (already in properties(n), cheap). Coerced to a str the client
# orders/thresholds by; absent → None (no recency position — e.g. content-keyed Genesis/Objective/
# Direction, which carry no stamp). group-scoped like the rest of the fold (it reads only this node's
# already-scoped props).
_TS_FIELDS = ("projected_at", "created_at", "valid_at", "ts")


def _node_ts(props):
    for field in _TS_FIELDS:
        val = props.get(field)
        if val:
            return _as_str(val)
    return None


def _node_ref(id_, props):
    """The STABLE node reference for the corrective write-path (codex Slice-6b round-4 [medium]):
    Graphiti's `uuid` property when present (stable across graph rebuilds/reprojections — the durable
    key a correction's node provenance should ride), else the elementId `id_` as an in-session
    fallback so no node is left without a correction target. Coerced to a str (graph-derived)."""
    uuid_prop = props.get("uuid")
    if isinstance(uuid_prop, str) and uuid_prop:
        return uuid_prop
    return _as_str(id_)


def _context_only(label, props):
    """The medium-authority marker for a node (R10/F9/C5), from the ONE shared derivation
    (tools/cortex_provenance) so the dashboard and the MCP never diverge. Lazily imported so the blog
    still loads where tools/ is absent; fail-safe context_only=true for an extracted node on any error."""
    try:
        sys.path.insert(0, str(BASE.parent / "tools"))
        import cortex_provenance
        return cortex_provenance.context_only_for(label, props)
    except Exception:  # noqa: BLE001 — fail-safe: anything OUTSIDE the asserted spine is context_only.
        # Key on the asserted-spine set, NOT _TRUST_BY_LABEL (where Episodic="episodic" != "extracted"
        # would mis-mark a low-tier Episodic as order-bearing, codex final [P3]). Asserted spine →
        # order-bearing; everything else (extracted, episodic, unknown) → context_only (fail-safe).
        return label not in ("Genesis", "Objective", "Direction", "Artefato")


def _map_node(id_, label, props):
    """One Cortex node → the render payload: id, label, a human title, its trust tier (the
    brightness axis), the earmarked flag (the harm overlay — passed through so the overlay is wired
    end-to-end; harm overrides the dim regardless of trust tier), the source `href` — the
    drill-down into the node's real surface (blog entry / Direction / source doc / wiki cluster), so
    a node click navigates instead of dead-ending (the graph stops being an island) — and the
    recency `ts` (Slice 6: the recency filter axis, from the graph stamp; None when unstamped)."""
    return {
        "id": id_,
        # A STABLE node ref for the corrective write-path (codex Slice-6b round-4 [medium]): the
        # render `id` is the Neo4j elementId, which is REBUILT/REPROJECTED-unstable — persisting it as
        # a durable Voz target_ref would orphan a correction's node provenance after a graph rebuild.
        # So ship a stable ref: Graphiti's `uuid` property (stable across rebuilds) when present, else
        # the elementId as an in-session fallback. The correction validates + persists THIS, so a
        # correction stays attributable to the harm node across rebuilds (the id is render-only).
        "ref": _node_ref(id_, props),
        # The navigation ALIAS (codex final [P2]): the slug/key surf+recall emit and pass into
        # cortex_node — distinct from the rebuild-unstable `ref` (uuid/elementId). An Artefato's `slug`,
        # a Source's `key`. Carried so the MCP's slug→node drill-down resolves on a healthy graph
        # (surf returns a slug; cortex_node must open it). None when the node has no such alias.
        "slug": props.get("slug") or props.get("key"),
        "label": label,
        "title": _node_title(label, props),
        # the CLAIM content (no label fallback) — the corrective snapshot's context source, None when
        # the node carries no content field, so the missing-context gate is truly fail-closed (round-7).
        "content": _node_content(label, props),
        "trust": _TRUST_BY_LABEL.get(label, "extracted"),
        # R10/F9 — the dashboard inherits the SAME medium-authority marker the MCP returns (one
        # derivation, cortex_provenance), so the two reads do not diverge: an extracted/low-tier node
        # is context_only on the page too (C5). `trust` (above) stays the brightness axis; context_only
        # is the orthogonal authority axis. Fail-safe: unknown-Medium extracted ⇒ context_only=true.
        "context_only": _context_only(label, props),
        # Fail-closed ON TYPE (codex Slice-6b round-2 [high]): preserve ONLY a literal boolean True.
        # A `bool(...)` coercion would promote schema drift — a string "false"/"0" or an int 1 (all
        # truthy) — into an eligible harm node, expanding the node-targeted Voz corrective boundary
        # beyond the Earmarked harm-settled subset. Only `is True` crosses; anything else → False.
        "earmarked": props.get("earmarked") is True,
        "href": _node_href(label, props),
        "ts": _node_ts(props),
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
        # N1/R3 — bound the connect + pool-acquire so the standing read door (the MCP rides this fold
        # for cortex_node/cortex_search) DARKENS within a budget on a slow/absent graph, never hangs.
        try:
            budget = float(os.environ.get("EDGE_CORTEX_TIMEOUT", "5"))
        except (TypeError, ValueError):
            budget = 5.0
        drv = GraphDatabase.driver(uri, auth=(user, password),
                                   connection_timeout=budget, connection_acquisition_timeout=budget)
    except Exception:
        return None
    try:
        # N1/R3 — bound the QUERY execution too (not only the connect): a connected-but-stalling fold
        # query must darken within the budget, never hang the standing read door the MCP rides.
        try:
            from neo4j import Query
            nodes_q = Query(_CORTEX_NODES_QUERY, timeout=budget)
            edges_q = Query(_CORTEX_EDGES_QUERY, timeout=budget)
        except Exception:
            nodes_q, edges_q = _CORTEX_NODES_QUERY, _CORTEX_EDGES_QUERY
        with drv.session() as s:
            nodes = [_map_node(r["id"], r["label"], r["props"])
                     for r in s.run(nodes_q, g=group).data()]
            edges = [{"id": r["id"], "source": r["source"], "target": r["target"], "type": r["type"]}
                     for r in s.run(edges_q, g=group).data()]
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


def _cortex_list(payload):
    """The M21 rung-3 fallback — a server-rendered, navigable node list from the SAME {nodes, edges}
    payload. It is the tertiary rung BELOW the 2D Cytoscape fallback: shipped (hidden) on every
    /cortex render so it works even if JS is dead OR both WebGL renderers fail; the island reveals it
    only when 3D AND Cytoscape are both unavailable (M21 rung 3). Every node title is html-escaped at
    the boundary (a graph title derives from Direction/Source/Entity content — the same XSS posture as
    the embed); a node's drill-down link is rendered ONLY for an INTERNAL same-origin path (a leading
    "/", not "//") — the exact internal-path-only guard the inspect panel's appendLink applies — so a
    poisoned/external href is never turned into a live anchor. No fold/query change: this reads the
    payload the route already holds."""
    items = []
    for n in payload.get("nodes", []):
        label = _esc(n.get("label", ""))
        title = _esc(n.get("title", "") or n.get("id", ""))
        href = n.get("href")
        # internal same-origin path only (leading "/", not "//") — drop external / javascript: / //host
        link = ""
        if isinstance(href, str) and href[:1] == "/" and href[1:2] != "/":
            link = f' <a class="list-source" href="{_esc(href)}">abrir fonte →</a>'
        items.append(
            f'<li class="cortex-list-item"><span class="kind">{label}</span>'
            f'<span class="title">{title}</span>{link}</li>'
        )
    # Rendered VISIBLE by default (codex round-1 [high]): the list is the JS-DEAD navigable fallback,
    # so a failed/absent cortex.js (or JS disabled) must still leave a navigable list, never a blank
    # graph area. The island HIDES it (sets `hidden`) only AFTER a graph rung successfully paints —
    # progressive enhancement, the M21 "works even if JS is dead" posture.
    return (
        '<section id="cortex-list" class="cortex-list" aria-label="cortex node list">'
        '<h2>cortex — lista</h2>'
        '<p class="meta">O grafo navegável como lista — cada nó com seu tipo e a fonte (quando há). '
        'É a forma textual do Cortex (também o fallback quando não há renderizador gráfico).</p>'
        f'<ul class="cortex-list-nodes">{"".join(items)}</ul></section>'
    )


def _cortex_dark():
    """The honest dark state — no group or neo4j unreachable. Never an unscoped graph, never a 500."""
    return (
        '<section class="cortex-dark"><h2>cortex — dark</h2>'
        '<p class="meta">O grafo está escuro: sem group_id resolvido ou neo4j inacessível. '
        'A projeção é group-scoped e fail-closed — nunca uma query graph-wide. '
        'Resolva a identidade do install (EDGE_GROUP / agent.yaml) e confirme o neo4j.</p></section>'
    )


# The node-type labels the filter exposes, in trust order (space-0 first). One checkbox per label;
# the island maps a label → its node class and shows/hides deterministically over the loaded payload.
_CORTEX_FILTER_LABELS = ("Genesis", "Objective", "Direction", "Artefato", "Entity", "Source", "Episodic")


def _cortex_controls():
    """The search + filter controls (Slice 6) — find-and-jump search, node-type checkboxes,
    Earmarked-only toggle, recency slider. Static markup the island wires client-side; it reuses the
    shared style.css component vocabulary (no one-off styling). Rendered only when there is a graph
    to navigate (never on the dark page)."""
    types = "".join(
        f'<label class="ctrl-type"><input type="checkbox" name="cortex-type" value="{label}" checked> '
        f'{html.escape(label)}</label>'
        for label in _CORTEX_FILTER_LABELS
    )
    return (
        '<aside class="cortex-controls" aria-label="search and filter">'
        '<div class="ctrl-row">'
        '<input id="cortex-search" type="search" autocomplete="off" '
        'placeholder="buscar nó (label/tipo)…" aria-label="buscar nó">'
        '<span id="cortex-search-status" class="ctrl-status" role="status"></span>'
        '</div>'
        f'<div class="ctrl-row ctrl-types">{types}</div>'
        '<div class="ctrl-row">'
        '<label class="ctrl-toggle"><input id="cortex-earmarked" type="checkbox"> só Earmarked</label>'
        # The Episodic-collapse perf lever (Slice 6): a client-side render decision that folds the
        # faint Episodic haze out of the RENDERED set to keep the 3D render performant as the graph
        # grows (the fold payload is untouched). Reuses the shared .ctrl-toggle component vocabulary.
        '<label class="ctrl-toggle"><input id="cortex-collapse" type="checkbox"> colapsar Episodic</label>'
        '<label class="ctrl-recency">recência '
        '<input id="cortex-recency" type="range" min="0" max="100" value="0" '
        'aria-label="recência mínima"></label>'
        '</div>'
        # Slice 5 / M15 — PREV/NEXT traversal: step the selection along the island's stable, filter-
        # respecting traversalOrder (the reference's `← PREV / NEXT →`). Static markup the island wires.
        '<div class="ctrl-row cortex-traversal">'
        '<button id="cortex-prev" type="button" class="ctrl-btn" aria-label="nó anterior">← prev</button>'
        '<button id="cortex-next" type="button" class="ctrl-btn" aria-label="próximo nó">next →</button>'
        '</div>'
        '</aside>'
    )


def _cortex_usage_heat():
    """R11 — the READ-ONLY usage heat overlay. When EDGE_CORTEX_USAGE=on, render a heat block from
    state/cortex/usage.jsonl (the Usage signal, a NON-AUTHORITATIVE store — N4): the hot refs and their
    recency+frequency scores, so the operator can SEE the A/B treatment. OFF (default) → "" (absent
    entirely, the clean baseline). It is a RENDER of a non-authoritative store: NO write affordance, NO
    fold entry, NO graph mutation — it reads cortex_usage's scores and lays them over the page. Returns
    the overlay HTML, or "" when off / empty / on error (never blocks the page)."""
    try:
        sys.path.insert(0, str(BASE.parent / "tools"))
        import cortex_usage
        if not cortex_usage.enabled():
            return ""
        scores = cortex_usage._scores()
        if not scores:
            return ""
        # top hot refs by score (descending), bounded — a legible overlay, not the whole store.
        hot = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:25]
        data = _json_for_script({"hot": [{"ref": r, "score": round(s, 4)} for r, s in hot]})
        top = hot[0][1] or 1.0   # guard the heat-normalization division (all-zero / stale-decayed store)
        rows = "".join(
            f'<li class="usage-heat-item"><span class="ref">{_esc(r)}</span>'
            f'<span class="score" style="--heat:{min(1.0, s / top):.3f}">{s:.2f}</span></li>'
            for r, s in hot
        )
        # READ-ONLY by construction: a <section> + a <script> data block + a static list. No <form>, no
        # button, no POST — the overlay can carry no write affordance (N4). The data block is
        # _json_for_script-safe (the same XSS guard the fold embed uses).
        return (
            '<section id="cortex-usage-heat" class="cortex-usage-heat" aria-label="usage heat (read-only)">'
            '<h2>usage — heat</h2>'
            '<p class="meta">Sinal de uso (não-autoritativo, EDGE_CORTEX_USAGE=on): os nós mais lidos, '
            'por recência+frequência. Apenas leitura — não escreve no grafo, não entra em nenhum fold.</p>'
            f'<ul class="cortex-usage-heat-list">{rows}</ul>'
            f'<script id="cortex-usage-data" type="application/json">{data}</script>'
            '</section>'
        )
    except Exception:  # noqa: BLE001 — the overlay never blocks the page (it is a non-essential render)
        return ""


@app.get("/cortex")
def cortex():
    """Surf the agent's brain: the whole Cortex as a dark, force-directed constellation centered on
    space-0, trust-weighted, read-only. One live fold → a Cytoscape island; pan/zoom/click client-side.
    The search + filter controls (Slice 6) ride above the canvas — find-and-jump + type / Earmarked /
    recency narrowing, all client-side over the one loaded payload (no new server round-trips)."""
    payload = cortex_fold()
    if payload is None:
        graph = _cortex_dark()
        island = ""
        controls = ""
    else:
        controls = _cortex_controls()
        # the 3D mount the island draws into (M1), plus the server-rendered list fallback (M21 rung 3,
        # hidden until the island reveals it when both WebGL renderers fail / JS is dead).
        # R11 — the read-only usage heat overlay rides ABOVE the canvas when EDGE_CORTEX_USAGE=on
        # (absent otherwise). A render of the non-authoritative usage store: no write, no fold (N4).
        graph = _cortex_usage_heat() + '<div id="cortex"></div>' + _cortex_list(payload)
        data = _json_for_script(payload)  # XSS-safe to embed in a <script> data block
        island = (
            # The renderer libs are SELF-HOSTED (Slice 7 #37 / M18: no CDN supply chain) and loaded
            # ONLY on this view (a JS island, never the app shell — M19). 3d-force-graph is the default
            # renderer (M1); cytoscape is the mandated WebGL/init-failure fallback (M21 rung 2), shipped
            # alongside so the island can fall through the ladder client-side. The data block is
            # _json_for_script-safe (M17).
            '<script src="/static/vendor/3d-force-graph.min.js"></script>'
            '<script src="/static/vendor/cytoscape.min.js"></script>'
            f'<script id="cortex-data" type="application/json">{data}</script>'
            '<script src="/static/cortex.js"></script>'
        )
    return _page("pages/cortex.html", current="/cortex",
                 controls=_safe(controls), graph=_safe(graph), island=_safe(island))


@app.post("/cortex/<node_id>/comment")
def post_cortex_correction(node_id):
    """The Earmarked corrective write-path (Slice 6b): a node-targeted Voz correction. Posts a
    `voz.comment` whose `target_ref` is the Cortex NODE ref (`node:<id>`), so the mentee can CORRECT
    a harm-bearing node, not just see it. Rides the SAME Slice-1 gate + body-size limit + canonical
    append as every other Voz write; the node-ref validation is fail-closed (an unknown node id — or
    a dark graph — → 404, no append). The Slice-2 drain then resolves it like any Directive."""
    if not authorize_write():
        abort(403)  # per Slice 1 — unauthenticated / cross-origin → rejected, no append
    target_ref = f"{_NODE_REF_PREFIX}{node_id}"
    # Resolve validation + the node-context snapshot from ONE cortex read (codex round-6 [medium]):
    # no TOCTOU window where the graph degrades between a validate read and a snapshot read and lands
    # a correction without its node context.
    node = _resolve_node_target_ref(target_ref)
    if node is None:
        abort(404)  # a forged / unknown / non-Earmarked node ref (or a dark graph) — fail-closed
    snapshot = _node_snapshot_of(node)
    if "node_title" not in snapshot:
        # fail-closed: never persist a node correction with no usable CLAIM context (the title is the
        # node's content the resolver settles against; a bare label like "Entity" is not enough).
        abort(409)
    if _reject_oversized_body():
        abort(413)
    body = (request.form.get("body") or "").strip()
    if body:
        # Stamp a machine-readable harm signal (codex Slice-6b round-3 [medium]): an Earmarked
        # correction is harm work BY CONSTRUCTION — it targets the harm-bearing subset CONTEXT.md says
        # must be settled by Voz. The drain's deterministic harm-rank (_harm_score) honors an explicit
        # numeric `harm` field, so stamping it here makes a NEUTRALLY-worded correction rank as harm
        # work and load first — never overflow behind unrelated keyword-rich chatter (hidden safety
        # correction under backlog). The drain ranks on it; it is otherwise inert metadata on the log.
        # The node snapshot rides along so the resolver/audit sees the node it corrects.
        _append_voz("voz.comment", f"voz:{target_ref}",
                    {"target_ref": target_ref, "comment_id": uuid.uuid4().hex[:12], "body": body,
                     "harm": _CORRECTION_HARM, **snapshot},
                    idem_key=_comment_idem_key(request.form.get("comment_nonce"), body))
    # A small confirmation fragment for the inspect-panel composer (htmx swaps it in place).
    return ('<p class="correction-ok meta">correção registrada · '
            'vira um Directive que o edge resolve no próximo grill</p>')


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
    # coerce the top-level ts to str (round-7): _render_health_strip slices ts[:19], and a non-string
    # top-level ts (`ts: 123`) is NOT rejected by log_is_intact — the strip must fail dark, not 500.
    return {"ts": _as_str(last.get("ts", "")), "swept_sessions": swept}


def _log_cursor():
    """The log cursor = the max seq in the log (the read-model's currency). 0 on an empty log. Only
    INT seqs count — a schema-drifted dict event with a string/list `seq` (Codex round-2 [high]) is
    skipped, never fed to max() (mixed-type max raises), so a corrupt log degrades deterministically."""
    return max((e["seq"] for e in _dict_events()
                if isinstance(e.get("seq"), int)), default=0)


# The hard client-side deadline (seconds) on the graph-reachability probe — a neo4j that ACCEPTS a
# connection but stalls on query execution must not hang /briefing past this, regardless of whether
# the server honors the per-query timeout (Codex round-8). The strip degrades dark promptly.
_GRAPH_PROBE_DEADLINE = 4

# Test seam: a callable()->bool that replaces the real neo4j probe (tests inject a blocking/raising
# one to prove the deadline bounds /briefing without a live neo4j). None → the real probe.
GRAPH_PROBE = None


def _neo4j_probe():
    """The raw neo4j reachability probe: a single `RETURN 1` with BOTH a connection/pool timeout AND a
    server-side per-query transaction timeout. NEVER an LLM (zero API spend). Returns True/False; may
    block if neo4j accepts the connection then stalls — the caller bounds it with a hard deadline."""
    uri = os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = os.environ.get("EDGE_NEO4J_PASSWORD") or _neo4j_password()
    try:
        from neo4j import GraphDatabase, Query
        drv = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3,
                                   connection_acquisition_timeout=3, max_transaction_retry_time=0)
        try:
            with drv.session() as s:
                s.run(Query("RETURN 1", timeout=3)).consume()  # server-side query deadline too
            return True
        finally:
            drv.close()
    except Exception:
        return False


def _graph_reachable():
    """A CHEAP, BOUNDED graph-reachability probe for the health strip (neo4j only, NEVER an LLM —
    zero API spend). Distinct from cortex_fold() (which loads the WHOLE graph): the strip only needs a
    yes/no. The probe runs under a HARD client-side deadline in a daemon thread (Codex round-8): a
    neo4j that accepts the connection but stalls on the query cannot hang /briefing past the deadline —
    the strip degrades dark promptly. The Cortex fixture seam wins when set (tests stay hermetic).
    Returns True/False; NEVER raises (a dark graph is a degraded signal, not a crash)."""
    if os.environ.get("EDGE_CORTEX_FIXTURE"):
        return True
    if not _group():
        return False
    probe = GRAPH_PROBE or _neo4j_probe
    import threading
    result = {"ok": False}

    def _run():
        try:
            result["ok"] = bool(probe())
        except Exception:
            result["ok"] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(_GRAPH_PROBE_DEADLINE)
    # If the probe thread is still alive past the deadline (a stalled query), treat the graph as
    # unreachable (dark) and return immediately — the daemon thread cannot block process exit.
    return result["ok"] if not t.is_alive() else False


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
    return _page("pages/briefing.html", current="/briefing", htmx=True,
                 strip=_safe(strip), briefing_block=_safe(briefing_block))


# ── Direction surface (Slice 4, SURFACE.md §"Direction", AUDIT.md gap A, ADR-0007) ──────────────
#
# The steers, as a projeção: a fold of `direction.*` via `eventlog.direction_at` → the TWO tiers.
# `set` (curated, Voz-only — the active steers) renders PROMINENT and first; `proposed` (candidates
# awaiting the grill — artefato / grill achados) renders DIMMER below, the same trust-language as the
# Cortex graph (curated pops, the hypothesis cloud recedes). A read-only projection, no parallel store.
#
# The Voz→Direction provenance link (the loop's READ side; the write side is the Slice-2 drain): a
# `set` steer folded from a Directive carries `origin_comment_id`. The surface renders it
# BIDIRECTIONALLY (steer ⇄ originating comment) — a visible "from a Directive" marker that drills into
# the comment's chat/post context (the slug's post, or /chat for a general-chat Directive). Provenance
# is tier-disjoint: a `set` carries `origin_comment_id`, a `proposed` carries `from_artefato` — never
# the reverse (ADR-0007 / SURFACE.md). A pure fold over the one log; zero API spend.


def _origin_href(comment_id):
    """The drill-down URL for a steer's originating comment: a surface that ACTUALLY renders that
    comment, at its stable anchor (FIX 3). The old `/e/{slug}.html` pointed at the STATIC artifact
    file — which renders the post body, NOT the Voz rail / the comment — so the link landed nowhere.
    `/chat` renders EVERY comment (targeted or general), so the robust target is `/chat#comment-{id}`;
    the chat carries the matching `id="comment-{id}"` (sanitized identically via _anchor_id)."""
    return f"/chat#{_anchor_id('comment', comment_id)}"


def _provenance_block(origin_comment_id):
    """The steer⇄originating-comment provenance link for a `set` steer folded from a Directive
    (SURFACE.md: 'renders the link bidirectionally'). Rendered only when origin_comment_id is present
    (a non-Voz grill-direct set has none → no marker). Drills into a surface that renders the comment."""
    if not origin_comment_id:
        return ""
    href = _origin_href(origin_comment_id)
    cid = _esc(origin_comment_id)
    return (f'<p class="provenance meta">from a Directive · '
            f'<a href="{href}" data-origin-comment="{cid}">{cid}</a></p>')


def _render_set_item(item):
    """One curated (`set`) steer: its kind + body, plus the Voz provenance link where present. Carries
    a stable `id="steer-{sanitized id}"` (FIX 2) so the comment→steer marker (`_folded_marker` →
    `/direction#steer-{id}`) drills into THIS element — the href fragment and the id are sanitized
    identically via `_anchor_id`, so the anchor centers the actual steer instead of landing nowhere."""
    anchor = _anchor_id("steer", item.get("id", ""))
    kind = _esc(item.get("kind", "thread"))
    body = _esc(item.get("body", ""))
    prov = _provenance_block(item.get("origin_comment_id"))
    return (f'<li class="steer" id="{html.escape(anchor)}"><span class="kind">{kind}</span>'
            f'<p class="body">{body}</p>{prov}</li>')


def _render_proposed_item(item):
    """One candidate (`proposed`) steer: its kind + body, plus its artefato provenance (from_artefato)
    where present — tier-disjoint, NEVER an origin_comment_id (that rides only the curated tier)."""
    kind = _esc(item.get("kind", "thread"))
    body = _esc(item.get("body", ""))
    src = item.get("from_artefato")
    prov = (f'<p class="provenance meta">from <a href="/e/{_esc(src)}.html">{_esc(src)}</a></p>'
            if src else "")
    return (f'<li class="steer"><span class="kind">{kind}</span>'
            f'<p class="body">{body}</p>{prov}</li>')


def _direction_fold():
    """Fold direction.* → the two tiers, over the TOLERANT shared iterator (_read_events), so a
    JSON-valid non-dict / corrupt-payload line cannot 500 this surface — the same fail-soft posture
    every other read surface takes (Codex round-4 contract: one corrupt log must not crash a surface
    the shared nav routes into; /briefing's health strip still flags the corruption). NOT
    eventlog.direction_at (which folds via the strict eventlog.read — it TypeErrors on a non-dict
    line). The fold logic itself is reused via eventlog.fold_direction (no parallel fold)."""
    import eventlog
    evs = [e for e in _read_events() if e.get("type") in eventlog.DIRECTION_TYPES]
    return eventlog.fold_direction(evs)


def _render_direction():
    """Fold direction.* → the two tiers and render them: `set` (curated, prominent, first) then
    `proposed` (candidate, dimmer). Empty/dark folds render an honest marker, never a 500."""
    d = _direction_fold()
    sets, proposed = d.get("set", []), d.get("proposed", [])
    if not sets and not proposed:
        return '<p class="meta">sem direção ainda — nenhum steer.</p>'
    set_items = ("".join(_render_set_item(i) for i in sets)
                 or '<li class="empty meta">nenhum steer curado ainda</li>')
    prop_items = ("".join(_render_proposed_item(i) for i in proposed)
                  or '<li class="empty meta">nenhum candidato no momento</li>')
    return (
        '<section class="direction-tier set">'
        '<h2 class="tier-title">set — curados (Voz)</h2>'
        '<p class="tier-note meta">os steers ativos — a maior autoridade.</p>'
        f'<ul class="steers">{set_items}</ul></section>'
        '<section class="direction-tier proposed">'
        '<h2 class="tier-title">proposed — candidatos (grill achados)</h2>'
        '<p class="tier-note meta">hipóteses aguardando o grill — confiança menor.</p>'
        f'<ul class="steers">{prop_items}</ul></section>'
    )


@app.get("/direction")
def direction_surface():
    """The steers, scannable: the two tiers (`set` curated/prominent, `proposed` candidate/dimmer) +
    the Voz→Direction provenance link. A read-only fold of direction.* (eventlog.direction_at) — zero
    API spend. 'Did my steer land?' is answerable here for a folded Directive (the origin link)."""
    return _page("pages/direction.html", current="/direction", htmx=True,
                 direction_html=_safe(_render_direction()))


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


# ── Design-doc surfaces (Slice 5a, AUDIT.md gap C, PLAN.md Slice 5a) ─────────────────────────────
#
# Make the edge's documentation NAVIGABLE in-dashboard, not read as files. The FOUR design-doc types
# — glossary (CONTEXT.md), the ADRs (docs/adr/*.md), the Idiom standing page (state/idiom.md), and
# the Source roadmap (state/source-roadmap.md) — each list on `/docs` and render on `/docs/<doc_id>`.
#
# ⚠️ SECURITY (PLAN.md, do not skip): these docs are edge-authored AND source-derived, so the
# markdown can carry raw HTML, event handlers, or `javascript:` URLs. EVERY doc view renders through
# the SHARED allowlist sanitizer `docmd.render_doc_html` (the same boundary Slice 5b's wiki/cluster
# pages will reuse) — markdown → INERT HTML — so nothing executes same-origin in the authed
# dashboard. An injected `<script>` / `on*=` handler / `javascript:` URL could otherwise read state
# and fire an authenticated log-mutating POST, defeating the Slice-1 write gate. The doc surfaces are
# READ-ONLY (no write route), so they carry no auth gate; their boundary is the sanitizer.
import docmd  # noqa: E402  (the shared doc-rendering surface)


def _docs_root():
    """The repo root the doc sources live under (CONTEXT.md, docs/adr/, state/). The blog package
    sits one level down, so the root is BASE.parent — the same anchor _log() uses."""
    return BASE.parent


def _doc_path(env, *default_parts):
    """A doc source path, env-overridable for tests (CONTRACT C1 — a throwaway tree, never the real
    repo docs as the system under test). Unset → the install's real doc at <root>/<default_parts>."""
    override = os.environ.get(env)
    return Path(override) if override else _docs_root().joinpath(*default_parts)


def _adr_dir():
    return _doc_path("EDGE_DOCS_ADR_DIR", "docs", "adr")


def _adr_title(path):
    """An ADR's human title = its first `# ` heading line (the ADR convention), else the file stem.
    Read defensively — a missing/unreadable file falls back to the stem, never raises."""
    try:
        for line in path.read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem


def _doc_registry():
    """The ordered registry of every design-doc surface: (doc_id, kind, title, source Path). The
    `doc_id` is the stable, URL-safe handle a /docs/<doc_id> view resolves. ADRs expand to one entry
    per file (sorted by number); the three standing docs are single entries. Skips a source that is
    absent on disk, so an install missing a doc degrades (the entry just doesn't list) rather than
    offering a dead link."""
    entries = []
    glossary = _doc_path("EDGE_DOCS_GLOSSARY", "CONTEXT.md")
    if glossary.is_file():
        entries.append(("glossary", "glossary", "Glossary (CONTEXT.md)", glossary))
    idiom = _doc_path("EDGE_DOCS_IDIOM", "state", "idiom.md")
    if idiom.is_file():
        entries.append(("idiom", "standing page", "Idiom", idiom))
    roadmap = _doc_path("EDGE_DOCS_ROADMAP", "state", "source-roadmap.md")
    if roadmap.is_file():
        entries.append(("source-roadmap", "standing page", "Source roadmap", roadmap))
    adr_dir = _adr_dir()
    if adr_dir.is_dir():
        for f in sorted(adr_dir.glob("*.md")):
            entries.append((f"adr/{f.stem}", "ADR", _adr_title(f), f))
    return entries


def _doc_by_id(doc_id):
    """Resolve a `doc_id` to its (kind, title, Path), or None. The lookup is over the registry (the
    allowlist of real docs), so an arbitrary/forged id resolves to None → the route 404s. This is
    ALSO the path-traversal defense: a request can only reach a doc the registry enumerated, never an
    attacker-chosen filesystem path (`../../etc/passwd`)."""
    for did, kind, title, path in _doc_registry():
        if did == doc_id:
            return kind, title, path
    return None


@app.get("/docs")
def docs_index():
    """The design-doc index: every doc type (glossary, ADRs, Idiom, Source roadmap) as a navigable
    link — none forces the mentee to a file path. A read-only fold of the doc registry; zero API
    spend. Grouped by kind so the four types read as four sections, not one flat list."""
    by_kind = {}
    for did, kind, title, _ in _doc_registry():
        by_kind.setdefault(kind, []).append((did, title))
    sections = []
    for kind in ("glossary", "standing page", "ADR"):
        items = by_kind.get(kind)
        if not items:
            continue
        links = "".join(
            f'<li><a href="/docs/{html.escape(did)}">{html.escape(title)}</a></li>'
            for did, title in items)
        sections.append(f'<section class="doc-group"><h2>{html.escape(kind)}</h2>'
                        f'<ul class="doc-list">{links}</ul></section>')
    body = "".join(sections) or '<p class="meta">sem docs ainda</p>'
    return _page("pages/docs_index.html", current="/docs", body=_safe(body))


@app.get("/docs/<path:doc_id>")
def doc_view(doc_id):
    """A single design-doc, rendered markdown → INERT HTML through the SHARED sanitizer
    (docmd.render_doc_html). The `doc_id` resolves over the registry allowlist (an unknown/forged id
    or a traversal attempt → 404, never an arbitrary filesystem read). Read-only; zero API spend."""
    found = _doc_by_id(doc_id)
    if found is None:
        abort(404)
    kind, title, path = found
    try:
        source = path.read_text()
    except OSError:
        abort(404)
    rendered = docmd.render_doc_html(source)
    return _page("pages/doc_view.html", current="/docs", doc_title=title, doc_kind=kind,
                 doc_html=_safe(rendered))


# ── Emergent-knowledge surface — the wiki / Knowledge clusters (Slice 5b, AUDIT.md gap C) ────────
#
# The edge's emergent Knowledge clusters (the llm-wiki) live as rendered HTML pages
# (state/wiki/index.html + cluster-*.html) — `GET /wiki` indexes them and `GET /wiki/<cluster>`
# drills into one thread, in-dashboard, so the mentee never reaches them only as files.
#
# ⚠️ SECURITY (PLAN.md, do not skip): unlike the design docs (markdown → docmd), the wiki pages are
# FULL edge-generated, SOURCE-DERIVED HTML. They must NOT execute same-origin in the authed
# dashboard: an injected `<script>` / `on*=` handler / `javascript:` URL could otherwise read state
# and fire an authenticated log-mutating POST, defeating the Slice-1 write gate. So a cluster page is
# rendered INERT by ISOLATION, not by trusting a denylist scrub of arbitrary HTML: the raw page is
# served from a dedicated `/wiki/<cluster>/raw` route under a `default-src 'none'` + `sandbox` CSP
# and embedded in a `sandbox`ed iframe (NO allow-scripts, NO allow-same-origin) — scripts never run,
# handlers never fire, and even a hypothetical execution has no same-origin access to the dashboard.
# The /wiki INDEX never embeds raw HTML at all: it re-renders a server-built list of cluster links
# (the cluster *titles* are html-escaped), so the index page itself carries no source HTML.

# The restrictive CSP for a raw cluster response: forbid ALL active content (default-src 'none'), and
# add the `sandbox` directive as a second, header-level isolation even when loaded directly (no
# scripts, no same-origin, no forms). allow-* is DELIBERATELY absent — re-enabling scripts or
# same-origin would defeat the boundary.
_WIKI_RAW_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


def _wiki_root():
    """The directory the edge's wiki pages live under (index.html + cluster-*.html), env-overridable
    for tests (CONTRACT C1 — a throwaway tree, never the real state/wiki as the system under test).
    Unset → the install's real wiki at <root>/state/wiki."""
    override = os.environ.get("EDGE_WIKI_ROOT")
    return Path(override) if override else _docs_root() / "state" / "wiki"


def _cluster_title(path):
    """A cluster page's human title = its <title> (or the first <h1>), tag-stripped + unescaped, else
    the file stem. Read defensively — a missing/unreadable file falls back to the stem, never raises.
    Only ever used as ESCAPED text on the index, never as live markup."""
    try:
        text = path.read_text()
    except OSError:
        return path.stem
    for pat in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            # strip any nested tags (e.g. an <h1>Title <span>tag</span></h1>) then unescape entities.
            inner = re.sub(r"<[^>]+>", "", m.group(1))
            inner = html.unescape(inner).strip()
            if inner:
                return inner
    return path.stem


# The canonical wiki cluster-id shape — letters-only, the EXACT rule wiki_render names its
# `cluster-<slug>.html` pages by (_cluster_slug). The registry FAILS CLOSED on any other id (codex
# round-2 [high]): a corrupt/drifted wiki tree carrying a filename like `cluster-x" onclick=….html`
# must NOT enter the allowlist — the /wiki index is an unsandboxed authed page, and a non-canonical id
# interpolated into an href would be a same-origin breakout vector (an authenticated POST, defeating
# the Slice-1 gate). Only a letters-only id is a real cluster page; anything else is dropped.
_CLUSTER_ID_RE = re.compile(r"^[a-z]+$")


# A relative `cluster-<id>.html` link on the canonical wiki index.html — the CURRENT projection of
# which clusters exist (ADR-0005: the wiki is a re-rendered projection of the graph; index.html is
# its source of truth). We honor the index, not a raw on-disk glob.
_INDEX_CLUSTER_LINK = re.compile(r'href="cluster-([a-z]+)\.html"', re.IGNORECASE)


def _current_cluster_ids():
    """The set of cluster ids the CANONICAL index.html currently links (codex round-3 [medium],
    ADR-0005 rendered-projection): wiki_render overwrites current pages but does NOT prune retired /
    renamed / merged cluster files, so a raw glob would surface stale pages the projection dropped —
    the dashboard would disagree with the canonical wiki. The index IS the projection, so its links
    are the registry's allowlist.

    FAILS CLOSED when the index is missing/unreadable (codex round-4 [medium]): no readable index =
    no current projection, so it returns the EMPTY set — never a glob fallback that would re-enable
    the stale-file republication (a crashed/partial render or a deleted index must NOT resurface
    retired pages). Each id is gated to the canonical letters-only shape."""
    index = _wiki_root() / "index.html"
    try:
        text = index.read_text()
    except OSError:
        return set()  # fail closed — no projection means no current clusters, never a stale glob
    return {m.group(1).lower() for m in _INDEX_CLUSTER_LINK.finditer(text)
            if _CLUSTER_ID_RE.match(m.group(1).lower())}


def _cluster_registry():
    """The ordered registry of every CURRENT Knowledge cluster: (cluster_id, title, source Path). The
    `cluster_id` is the stable, URL-safe handle a /wiki/<cluster_id> view resolves. This is the
    ALLOWLIST: a /wiki/<id> view resolves only over this list, so a forged id / traversal attempt
    reaches no file (404), never an arbitrary filesystem read.

    The allowlist is the CURRENT projection — the cluster ids the canonical index.html links (codex
    round-3 [medium], ADR-0005): a stale cluster-*.html the renderer no longer links is NOT surfaced
    (the dashboard agrees with the canonical wiki, never republishes retired knowledge). A
    missing/unreadable index FAILS CLOSED (codex round-4 [medium]): `_current_cluster_ids()` returns
    the empty set, so the registry is empty — never a glob that would resurface retired pages. Every
    id is also gated to the canonical letters-only shape (codex round-2 [high]) — a malformed filename
    never enters the allowlist. Sorted by id for a stable index."""
    root = _wiki_root()
    if not root.is_dir():
        return []
    current = _current_cluster_ids()  # the index's own links; {} (empty) when there is no projection
    entries = []
    for f in sorted(root.glob("cluster-*.html")):
        cid = f.stem[len("cluster-"):]
        if not (cid and _CLUSTER_ID_RE.match(cid)):
            continue
        if cid not in current:  # honor the projection — list only clusters the index currently links
            continue
        entries.append((cid, _cluster_title(f), f))
    return entries


def _cluster_by_id(cluster_id):
    """Resolve a `cluster_id` to its source Path, or None. The lookup is over the registry allowlist,
    so an arbitrary/forged id (incl. a traversal attempt) resolves to None → the route 404s, never an
    arbitrary filesystem read."""
    for cid, _title, path in _cluster_registry():
        if cid == cluster_id:
            return path
    return None


def _wiki_href(cluster_id):
    """The in-dashboard drill-down URL for a cluster id (the rewrite target for a relative
    `cluster-<id>.html` link on the source index)."""
    return f"/wiki/{cluster_id}"


@app.get("/wiki")
def wiki_index():
    """The Knowledge-cluster index: every cluster as a navigable in-dashboard link (the relative
    `cluster-*.html` file links rewritten to /wiki/<id>). A server-built list — the index page embeds
    NO source HTML, so it carries no injection surface; the cluster titles are html-escaped. Read-only
    fold of the wiki registry; zero API spend."""
    items = "".join(
        # cid is letters-only by the registry's canonical gate; html.escape is belt-and-suspenders so
        # the index href can never carry a breakout even if the gate were ever loosened.
        f'<li><a href="{html.escape(_wiki_href(cid))}">{html.escape(title)}</a></li>'
        for cid, title, _ in _cluster_registry()
    )
    body = (f'<ul class="wiki-clusters">{items}</ul>' if items
            else '<p class="meta">sem clusters ainda</p>')
    return _page("pages/wiki_index.html", current="/wiki", body=_safe(body))


@app.get("/wiki/<cluster_id>")
def wiki_cluster(cluster_id):
    """A single Knowledge cluster, isolated in a `sandbox`ed iframe pointing at the raw sub-route. The
    `cluster_id` resolves over the registry allowlist (an unknown/forged id or traversal → 404). The
    raw edge-generated HTML never lands in THIS authed parent document — it lives only inside the
    sandboxed frame (no allow-scripts, no allow-same-origin), so nothing executes same-origin."""
    if _cluster_by_id(cluster_id) is None:
        abort(404)
    title = next((t for cid, t, _ in _cluster_registry() if cid == cluster_id), cluster_id)
    return _page("pages/wiki_cluster.html", current="/wiki",
                 cluster_id=cluster_id, cluster_title=title)


@app.get("/wiki/<cluster_id>/raw")
def wiki_cluster_raw(cluster_id):
    """The raw edge-generated cluster HTML — the iframe `src`. Served under a `default-src 'none'` +
    `sandbox` CSP and X-Frame-Options/nosniff, so even loaded directly it executes nothing and has no
    same-origin access to the dashboard. The id resolves over the registry allowlist (forged/traversal
    → 404). This is the ONE place the source HTML is served, and it is sandboxed at the header level."""
    path = _cluster_by_id(cluster_id)
    if path is None:
        abort(404)
    try:
        source = path.read_text()
    except OSError:
        abort(404)
    return source, 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Security-Policy": _WIKI_RAW_CSP,
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
    }


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


# ── /llm — o painel de rotas LLM (issue #55) ────────────────────────────────────────────────────
#
# Um adapter FINO sobre llm_routes: cada rota do agent.yaml com provider/modelo/credencial, probe
# real sob demanda e troca de provider sem editar YAML na mão — ambos atrás do authorize_write
# (probe gasta chamada real; a troca muta o fenótipo). A rota embedding rende EM SEPARADO com o
# aviso de que a assinatura não a cobre; os `llm.infra_error` recentes do log fecham o ciclo da
# issue: quota morta aparece como INFRA aqui, não como reprovação de revisor no close.


def _repo():
    """A raiz do repo do host (agent.yaml + secrets/). Overridável por env para teste."""
    return Path(os.environ.get("EDGE_REPO", BASE.parent))


def _llm_route_row(r, probe_result=None):
    cred_cls = "ok" if r["credential"] in ("ok", "assinatura") else "warn"
    probe_html = ""
    if probe_result is not None:
        state = "ok" if probe_result.get("ok") else "warn"
        probe_html = (f'<div class="meta probe-result {state}">probe: '
                      f'{_esc(probe_result.get("detail"))}'
                      + (f' (status {_esc(probe_result.get("status"))})'
                         if probe_result.get("status") else "") + "</div>")
    options = "".join(
        f'<option value="{p}"{" selected" if p == r["provider"] else ""}>{p}</option>'
        for p in llm_routes.KNOWN_PROVIDERS
        if not (r["embedding_route"] and p in llm_routes._llm.SUBSCRIPTION_PROVIDERS))
    return f"""<div class="llm-route" id="route-{_esc(r['route'])}">
  <h3>{_esc(r['route'])}</h3>
  <p class="meta">provider <strong>{_esc(r['provider'])}</strong> · modelo
  <strong>{_esc(r['model'])}</strong> · credencial
  <span class="{cred_cls}">{_esc(r['credential'])}</span>
  {('· <span class="meta">' + _esc(r['secret_ref']) + '</span>') if r.get('secret_ref') and not r['subscription'] else ''}</p>
  {probe_html}
  <form method="post" action="/llm/probe" class="inline">
    <input type="hidden" name="route" value="{_esc(r['route'])}">
    <button type="submit">probe</button>
  </form>
  <form method="post" action="/llm/provider" class="inline">
    <input type="hidden" name="route" value="{_esc(r['route'])}">
    <select name="provider">{options}</select>
    <button type="submit">trocar provider</button>
  </form>
</div>"""


def _llm_infra_errors(limit=5):
    """Os `llm.infra_error` mais recentes do log — o lado dashboard do contrato do close
    (issue #55): transporte/bilhetagem visível como infra, nunca reprovação silenciosa."""
    errs = [e for e in _read_events() if e.get("type") == "llm.infra_error"]
    return errs[-limit:][::-1]


def _llm_panel(probe_route=None, probe_result=None, error=None):
    rows, embedding_rows = [], []
    for r in llm_routes.routes(repo=_repo()):
        pr = probe_result if r["route"] == probe_route else None
        (embedding_rows if r["embedding_route"] else rows).append(_llm_route_row(r, pr))
    infra = "".join(
        f'<li class="warn">{_esc(e.get("ts", ""))} — status {_esc(e["payload"].get("status"))} — '
        f'{_esc(e["payload"].get("detail"))}</li>'
        for e in _llm_infra_errors())
    return _page(
        "pages/llm.html", current="/llm",
        error_html=_safe(f'<p class="warn llm-error">{_esc(error)}</p>' if error else ""),
        routes_html=_safe("".join(rows)),
        embedding_html=_safe("".join(embedding_rows)),
        infra_html=_safe(f"<ul>{infra}</ul>" if infra else '<p class="meta">nenhum</p>'))


@app.get("/llm")
def llm_panel():
    return _llm_panel()


@app.post("/llm/probe")
def llm_probe():
    if not authorize_write():   # um probe é uma chamada REAL (gasta cota/assinatura) → gated
        abort(403)
    route = (request.form.get("route") or "").strip()
    return _llm_panel(probe_route=route,
                      probe_result=llm_routes.probe_route(route, repo=_repo()))


@app.post("/llm/provider")
def llm_set_provider():
    if not authorize_write():
        abort(403)
    route = (request.form.get("route") or "").strip()
    provider = (request.form.get("provider") or "").strip()
    model = (request.form.get("model") or "").strip() or None
    try:
        llm_routes.set_provider(route, provider, repo=_repo(), model=model)
    except ValueError as e:
        return _llm_panel(error=str(e)), 400
    return app.redirect("/llm", code=303)


# ── /sources — o painel de yield do grounding (S7) ──────────────────────────────────────────────
#
# Um adapter FINO sobre grounding_yield (irmão do /llm sobre llm_routes): uma row por
# source×interface com tentativas/hits/citadas/mean sim/score/secas(por tier)/canário, dead-legs
# das fontes declaradas-sem-manifesto, e orphans/ambiguous/coarse/unconsumed no rodapé. É o degrau
# OBSERVE (#248): a tabela ACONSELHA, nunca roteia — não há choose_source aqui nem no módulo.


def _sources_panel_html():
    """O fragmento HTML do painel de yield — fold + roster do agent.yaml (E8: a fonte é DADO) +
    render, tudo em grounding_yield. Degrada num aviso, nunca 500 o painel."""
    import grounding_yield
    try:
        sources, _ = grounding_yield.sources_mod.load_sources(_repo() / "agent.yaml")
    except Exception:  # noqa: BLE001 — sem agent.yaml legível, o painel ainda abre
        sources = None
    return grounding_yield.sources_panel_html(log=_log(), sources=sources)


@app.get("/sources")
def sources_panel():
    try:
        panel = _sources_panel_html()
    except Exception as e:  # noqa: BLE001 — o painel nunca derruba o servidor
        panel = f'<p class="warn">painel de yield indisponível: {_esc(str(e))}</p>'
    return _page("pages/sources.html", current="/sources", panel_html=_safe(panel))


# Migrate on import so the very first read surface (index / chat) already reflects the switch.
_migrate_voz_lifecycle()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("BLOG_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLOG_PORT", str(DEFAULT_PORT))),
    )
