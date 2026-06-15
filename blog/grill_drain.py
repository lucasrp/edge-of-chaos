"""Slice 2 — the grill drain loop + the `voz.resolved` lifecycle (AUDIT.md gap B, ADR-0017).

Directs answers back on its own — no hand-appended replies. The drain:

  1. captures a `start_cursor` (max event seq) + the **actionable set** (open comments that are not
     parked-without-answer);
  2. loads a **deterministic harm-ranked CAPPED batch** of that set (overflow stays open + visible);
  3. generates a `voz.reply` per loaded comment via a **pluggable reply-generator** — `reply_fn`,
     injected so tests stub it (NO real LLM call in the suite); a live run wires it to the edge's
     chat router (gpt-5.4, on ~/edge/secrets/openai.env — **this spends the user's OpenAI API**);
  4. appends each chat's close in ONE **idempotent `append_batch`** keyed by `comment_id` +
     `grill_run_id`, under the **version guard** `unchanged_since(comment_id, start_cursor)` — so a
     stale/concurrent drain cannot double-close, and a crash leaves a chat fully resolved-or-open;
  5. when a loaded comment is a **standing Directive**, atomically appends `direction.set` +
     `voz.resolved{outcome: folded-to-direction, origin_comment_id, direction_id}`.

The lifecycle switch (`open_comments()` keys on terminal `voz.resolved` absence) ships atomically
with an **idempotent legacy back-fill** so historical reply-only comments are not re-opened nor
reprocessed. All reads are folds over the one log — no parallel store (ADR-0005/0006).
"""
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "tools"))
import eventlog  # noqa: E402

# The default cap: a drain loads at most this many chats (SURFACE.md: "a max chats/tokens cap"; the
# overflow stays open + visible, never an oversized prompt). Caller-overridable.
DEFAULT_BATCH_CAP = 8


def _events(log):
    """Every event in the log, oldest→newest (a thin wrapper over the canonical read)."""
    return eventlog.read(log=log)


# ── The lifecycle folds — openness, the actionable set, consistency ─────────────────────────────


def terminally_resolved(log):
    """`comment_id`s with a TERMINAL `voz.resolved`. A `voz.reply` is presentation only; a parked
    `voz.clarify` is non-terminal. Openness keys on the ABSENCE of a member here (ADR-0017)."""
    return {e["payload"].get("comment_id")
            for e in _events(log) if e.get("type") == "voz.resolved"}


def open_comments(log):
    """Every `voz.comment` with no terminal `voz.resolved` (any target). A replied-but-unresolved
    or parked chat is still open. A fold, not a flag."""
    resolved = terminally_resolved(log)
    return [e["payload"] for e in _events(log)
            if e.get("type") == "voz.comment"
            and e["payload"].get("comment_id") not in resolved]


def _awaiting_clarification(log):
    """`comment_id`s parked by a `voz.clarify` with NO subsequent `voz.clarify_answer` for that
    clarify. A parked-without-answer chat is open but NOT actionable (it lives only in the
    awaiting-clarification health count, never re-loaded — so it can't consume the cap every grill
    and starve fresh directives, SURFACE.md / ADR-0017)."""
    parked = {}          # comment_id -> set(clarify_id) still unanswered
    answered = set()     # clarify_ids that have a clarify_answer
    for e in _events(log):
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.clarify":
            parked.setdefault(p.get("comment_id"), set()).add(p.get("clarify_id"))
        elif t == "voz.clarify_answer":
            answered.add(p.get("clarify_id"))
    return {cid for cid, clarifies in parked.items() if clarifies - answered}


def actionable_set(log):
    """What a grill MAY load: open comments that are EITHER not awaiting clarification OR parked
    *with* a linked `voz.clarify_answer` (the answer re-enters the chat into the actionable set,
    terminally resolvable at the next grill). A parked-without-answer chat is excluded. SURFACE.md
    "Actionable set" invariant. Returns the comment payloads, in append order (deterministic)."""
    awaiting = _awaiting_clarification(log)
    return [c for c in open_comments(log) if c.get("comment_id") not in awaiting]


def consistency_errors(log):
    """Resolution-consistency errors for the health strip (SURFACE.md): a DUPLICATE `voz.resolved`
    (more than one terminal outcome for a `comment_id`), an ORPHAN `voz.resolved` (no preceding
    `voz.comment`), and a `folded-to-direction`/`retired-direction` whose `direction_id` has no
    matching `direction.set`/`direction.dropped`. Symmetric across create/promote/retire."""
    comment_ids, resolved_counts, set_ids, dropped_ids = set(), {}, set(), set()
    folds = []  # (comment_id, outcome, direction_id)
    for e in _events(log):
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.comment":
            comment_ids.add(p.get("comment_id"))
        elif t == "voz.resolved":
            cid = p.get("comment_id")
            resolved_counts[cid] = resolved_counts.get(cid, 0) + 1
            if p.get("outcome") in ("folded-to-direction", "retired-direction"):
                folds.append((cid, p.get("outcome"), p.get("direction_id")))
        elif t == "direction.set":
            set_ids.add(p.get("id"))
        elif t == "direction.dropped":
            dropped_ids.add(p.get("id"))
    errors = []
    for cid, n in resolved_counts.items():
        if n > 1:
            errors.append({"kind": "duplicate-resolved", "comment_id": cid, "count": n})
        if cid not in comment_ids:
            errors.append({"kind": "orphan-resolved", "comment_id": cid})
    for cid, outcome, did in folds:
        target = set_ids if outcome == "folded-to-direction" else dropped_ids
        if did not in target:
            errors.append({"kind": "dangling-direction", "comment_id": cid,
                           "outcome": outcome, "direction_id": did})
    return errors


# ── The legacy back-fill — shipped atomically with the lifecycle switch ──────────────────────────


def backfill_legacy_resolved(log, grill_run_id="legacy-backfill"):
    """Idempotently back-fill `voz.resolved{outcome: replied}` for every historical `voz.comment`
    that has a `voz.reply` but NO terminal `voz.resolved` (legacy-settled). Flipping `open_comments`
    to key on `voz.resolved` would otherwise RE-OPEN already-answered threads (incl. a hand-appended
    reply like the operator's "oi"); this back-fill keeps them closed. Re-running adds NOTHING (the
    second pass sees the resolved it wrote → empty) — proven idempotent. Returns the appended events."""
    replied = {e["payload"].get("comment_id")
               for e in _events(log) if e.get("type") == "voz.reply"}
    resolved = terminally_resolved(log)
    targets = [cid for cid in replied if cid and cid not in resolved]
    # Deterministic order (append order of the comments) so a replay is byte-stable.
    order = [e["payload"].get("comment_id") for e in _events(log)
             if e.get("type") == "voz.comment"]
    targets = [cid for cid in order if cid in targets]
    if not targets:
        return []
    batch = [("voz.resolved", "voz:backfill",
              {"comment_id": cid, "outcome": "replied", "grill_run_id": grill_run_id})
             for cid in targets]
    return eventlog.append_batch(batch, log=log)


# ── Harm ranking + the cap — deterministic batch selection ───────────────────────────────────────

# Harm-bearing markers on a comment (SURFACE.md: "a deterministic harm-ranked batch"). A higher
# score loads first; ties break on append order (the comment's seq) so selection is deterministic.
_HARM_MARKERS = ("harm", "earmark", "wrong", "unsafe", "danger", "correct", "broken")


def _harm_score(comment):
    """A deterministic harm rank for batch ordering. An explicit numeric `harm` field wins; else a
    coarse keyword signal over the body. Never an LLM call — selection must be reproducible."""
    explicit = comment.get("harm")
    if isinstance(explicit, (int, float)):
        return float(explicit)
    body = (comment.get("body") or "").lower()
    return float(sum(1 for m in _HARM_MARKERS if m in body))


def rank_and_cap(comments, cap):
    """Deterministically order the actionable comments harm-first (ties → append order) and split
    into (loaded, overflow) at the cap. The overflow is NOT dropped — it stays open + visible for
    the next grill (the caller never closes it). SURFACE.md: "the overflow stays open and visible —
    never an oversized prompt"."""
    ordered = sorted(enumerate(comments), key=lambda iv: (-_harm_score(iv[1]), iv[0]))
    ordered = [c for _, c in ordered]
    return ordered[:cap], ordered[cap:]


# ── The drain — capture cursor, load capped batch, generate, close atomically ────────────────────


def _start_cursor(log):
    """The grill's start cursor = the max event seq at drain start. The version guard is relative to
    THIS: a close fails unless no voz.resolved/voz.clarify for the chat appeared since it."""
    evs = _events(log)
    return evs[-1]["seq"] if evs else 0


def _is_standing_directive(plan):
    """A loaded chat the reply-generator marked as moving strategy → folds to a `set` steer
    (SURFACE.md / ADR-0007: a Direct Voz folded-to-direction always emits direction.set, curated,
    carrying origin_comment_id). The reply-generator decides (it has the chat in context); the drain
    only executes the fold deterministically."""
    return bool(plan.get("directive") or plan.get("direction_body"))


def _unchanged_since(log, comment_id, start_cursor):
    """The version guard predicate: True iff NO voz.resolved or voz.clarify for `comment_id` has
    appeared since `start_cursor` (SURFACE.md "Atomic close"). `still_open` alone is insufficient —
    a parked chat is still open — so we test BOTH terminal and parked events past the cursor."""
    for e in _events(log):
        if e["seq"] <= start_cursor:
            continue
        if e.get("type") in ("voz.resolved", "voz.clarify") \
                and e["payload"].get("comment_id") == comment_id:
            return False
    return True


class StaleDrain(Exception):
    """Raised under the eventlog lock when the version guard fails — a concurrent/stale drain
    already closed (resolved OR parked) this chat since the start cursor. The batch is dropped with
    nothing written, so two grills cannot double-close one chat."""


def _close_one(log, comment, plan, grill_run_id, start_cursor):
    """Append ONE chat's close as a single idempotent `append_batch` keyed by comment_id +
    grill_run_id, under the version guard. Returns the stamped events, or [] if the guard dropped a
    stale batch. The batch is one of:
      - replied:            voz.reply + voz.resolved{replied}
      - folded-to-direction: voz.reply + direction.set + voz.resolved{folded-to-direction, ...}
      - parked:             voz.clarify (non-terminal — no voz.resolved; the chat stays open)
    All under ONE write, so a crash leaves the chat fully closed-or-open, never half (ADR-0017)."""
    cid = comment["comment_id"]
    target = comment.get("target_ref")
    subject = f"voz:{target or 'chat'}"

    # Idempotency: a re-run with the same comment_id + grill_run_id must add nothing (a retry
    # replays the identical planned batch). Checked UNDER the lock so it's authoritative.
    def _precondition():
        for e in _events(log):
            p = e.get("payload", {})
            if e.get("type") in ("voz.resolved", "voz.clarify") \
                    and p.get("comment_id") == cid and p.get("grill_run_id") == grill_run_id:
                raise _AlreadyClosed(cid)
        # The version guard: drop a stale batch (a concurrent grill closed this chat since start).
        if not _unchanged_since(log, cid, start_cursor):
            raise StaleDrain(cid)

    if plan.get("park"):
        # Parked: a non-terminal voz.clarify keeps the chat open (autonomous grill may only park).
        events = [("voz.clarify", subject,
                   {"comment_id": cid, "clarify_id": uuid.uuid4().hex[:12],
                    "question": plan.get("question", "could you clarify?"),
                    "grill_run_id": grill_run_id})]
    elif _is_standing_directive(plan):
        # Folded-to-direction: voz.reply + direction.set + voz.resolved{folded-to-direction}, all
        # atomic. The set steer carries origin_comment_id; voz.resolved carries its direction_id.
        direction_id = plan.get("direction_id") or uuid.uuid4().hex[:12]
        events = [
            ("voz.reply", subject, {"comment_id": cid, "body": plan["reply"]}),
            ("direction.set", "direction",
             {"id": direction_id, "body": plan.get("direction_body", comment["body"]),
              "kind": plan.get("kind", "thread"), "supersedes": None,
              "origin_comment_id": cid}),
            ("voz.resolved", subject,
             {"comment_id": cid, "outcome": "folded-to-direction",
              "origin_comment_id": cid, "direction_id": direction_id,
              "grill_run_id": grill_run_id}),
        ]
    else:
        # Replied: voz.reply + terminal voz.resolved{replied}.
        events = [
            ("voz.reply", subject, {"comment_id": cid, "body": plan["reply"]}),
            ("voz.resolved", subject,
             {"comment_id": cid, "outcome": "replied", "grill_run_id": grill_run_id}),
        ]
    try:
        return eventlog.append_batch(events, log=log, precondition=_precondition)
    except _AlreadyClosed:
        return []  # idempotent re-run: this chat already closed under this grill_run_id
    except StaleDrain:
        return []  # stale/concurrent batch dropped by the version guard


class _AlreadyClosed(Exception):
    """Raised under the lock when this (comment_id, grill_run_id) already closed — the idempotent
    re-run path: nothing is written, the drain reports the chat as already handled."""


def drain(log, reply_fn, grill_run_id=None, cap=DEFAULT_BATCH_CAP):
    """Run one grill drain over `log`.

    Captures the start cursor + actionable set, loads a deterministic harm-ranked CAPPED batch,
    and for each LOADED comment calls `reply_fn(comment) -> plan` to get the close plan, then
    appends that chat's close atomically under the version guard. The OVERFLOW (actionable beyond
    the cap, plus post-cursor arrivals) is left open + visible — never dropped, never one oversized
    prompt.

    `reply_fn` is the **pluggable reply-generator** (injected). A plan is a dict:
      - {"reply": str}                                   → replied
      - {"reply": str, "directive": True, ...}           → folded-to-direction (a standing steer)
      - {"park": True, "question": str}                  → parked (non-terminal voz.clarify)
    Tests pass a STUB — no real LLM. A live run wires `reply_fn` to the edge's chat router
    (gpt-5.4, on ~/edge/secrets/openai.env), which **spends the user's OpenAI API per call**.

    Returns the list of LOADED comments (those the drain attempted to close this run)."""
    grill_run_id = grill_run_id or uuid.uuid4().hex[:12]
    start_cursor = _start_cursor(log)
    loaded, _overflow = rank_and_cap(actionable_set(log), cap)
    for comment in loaded:
        plan = reply_fn(comment)
        _close_one(log, comment, plan, grill_run_id, start_cursor)
    return loaded


# ── The LIVE reply-generator — wired to the edge's chat router. SPENDS THE USER'S OpenAI API. ─────
#
# ⚠️ COST: each call hits the edge's `chat` router (gpt-5.4, on ~/edge/secrets/openai.env — the
# user's OpenAI API key), billed PER CALL. This factory is NEVER invoked by the test suite (every
# test injects a stub) and the HTTP route never builds it unless the operator explicitly opts in
# (EDGE_DRAIN_LIVE=1). The model is configured in agent.yaml `routers.chat.model` (gpt-5.4); swap
# it there. To run a live drain from a local tool: `drain(log, live_reply_generator())`.

def live_reply_generator():
    """Build the LIVE reply-generator (callable(comment) -> plan) on the edge's chat router.

    ⚠️ Returns a callable that SPENDS THE USER'S OpenAI API per invocation (gpt-5.4 on
    ~/edge/secrets/openai.env). Imported lazily so the module loads with no edge runtime present;
    raises if the runtime/secret is unavailable rather than silently degrading. The model lives in
    agent.yaml `routers.chat`."""
    import importlib
    import os
    tools = str(BASE.parent / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    _llm = importlib.import_module("_llm")
    _secrets = importlib.import_module("_secrets")
    import yaml
    cfg = yaml.safe_load((BASE.parent / "agent.yaml").read_text()) or {}
    router = (cfg.get("routers") or {}).get("chat") or {}
    # secret_ref is "<file>.env:<VAR>"; load the install's env dir, then read VAR (#22, ADR-0011).
    _secrets.load_env(BASE.parent / "secrets")
    var = (router.get("secret_ref") or "").split(":", 1)[-1] or "OPENAI_API_KEY"
    api_key = os.environ.get(var)
    if not api_key:
        raise RuntimeError(f"live drain: no API key for chat router ({var}) — refusing to spend.")
    client = _llm.make_client(router, api_key)
    model = router.get("model")

    def gen(comment):
        prompt = ("You are the edge replying to a mentee Directive on the Voz rail. Reply directly, "
                  "technically, skeptically — name the tradeoff. Directive:\n\n" + comment["body"])
        return {"reply": _llm.complete(client, model, prompt)}

    return gen
