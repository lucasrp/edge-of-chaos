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
