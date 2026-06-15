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


def _events(log, until_seq=None):
    """Every event in the log, oldest→newest. `until_seq` bounds the fold at a cursor (seq <= n) —
    the snapshot the cursor-bound actionable set reads.

    TOLERANT of malformed / schema-drifted lines (skips garbage), like the server's `_read_events`
    projection — a single bad legacy line must NOT crash the lifecycle fold or the migration (the
    canonical `eventlog.read` would raise on it). This keeps the back-fill fail-soft by construction,
    so both the startup migration AND the drain route stay robust on an upgraded log."""
    import json
    from pathlib import Path
    p = Path(log)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if until_seq is not None and e.get("seq", 0) > until_seq:
            continue
        out.append(e)
    return out


def log_is_intact(log):
    """True iff EVERY non-blank line is a well-formed EVENT ENVELOPE — not merely valid JSON. The
    route validates this up front: a malformed OR schema-drifted line makes a canonical append
    raise (a miscounted base seq corrupts the source of truth) or the drain folds raise on a missing
    field (`e['seq']`, `e['payload'].get(...)`). So the drain must degrade BEFORE building/calling a
    reply generator (no API spend) or any close — and a JSON-only check is insufficient: a valid
    JSON line with a non-dict payload or missing seq would pass it and 500 the drain later.

    The envelope every fold indexes: a dict carrying an int `seq`, a str `type`, and a dict
    `payload`. (Matches what `eventlog` stamps and what the lifecycle folds read.)

    Beyond the envelope, the STRING payload fields the drain/render folds index must themselves be
    strings — an envelope-valid `voz.comment` with a non-string `body` would pass an envelope-only
    check, then crash `_harm_score().lower()` (drain) or `html.escape()` (render). So those fields
    are validated per type too, and a poisoned-but-valid-JSON event degrades the route deterministically."""
    import json
    from pathlib import Path
    p = Path(log)
    if not p.is_file():
        return True
    expected_seq = 0  # eventlog stamps seq = base+i+1 → a clean log is exactly 1,2,3,... in file order
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(e, dict):
            return False
        if not isinstance(e.get("seq"), int):
            return False
        # The seq invariant the cursor-bound drain depends on: contiguous + increasing in file order
        # (matches append_batch's base=len(read()) stamping). A gap / out-of-order / duplicate seq
        # would let a high-seq voz.resolved hide past the start cursor or a comment vanish from the
        # cursor-bound batch — so a seq-corrupt log degrades, not silently mis-drains.
        expected_seq += 1
        if e["seq"] != expected_seq:
            return False
        if not isinstance(e.get("type"), str):
            return False
        payload = e.get("payload")
        if not isinstance(payload, dict):
            return False
        t = e["type"]
        # REQUIRED fields the drain indexes DIRECTLY (e.g. comment["body"] in _build_live_prompt /
        # _harm_score) must be PRESENT and a non-empty string — a missing one would KeyError the
        # live drain, a non-string would crash .lower(). Must-exist, not just valid-if-present.
        for field in _REQUIRED_STRING_FIELDS.get(t, ()):
            v = payload.get(field)
            if not isinstance(v, str) or not v.strip():
                return False
        # PRESENT-ONLY fields: only a fold/render touches them, and only when present — a non-string
        # here would crash html.escape, but absence is handled elsewhere, so reject only a present non-str.
        for field in _OPTIONAL_STRING_FIELDS.get(t, ()):
            if field in payload and not isinstance(payload[field], str):
                return False
    return True


# Fields the drain indexes directly → must be present non-empty strings (a missing one KeyErrors).
# voz.comment.comment_id is indexed in clarify_context / _close_one; body in _build_live_prompt.
_REQUIRED_STRING_FIELDS = {
    "voz.comment": ("comment_id", "body"),
}
# Fields only a fold/render touches when present → reject a present non-string (poison/unhashable),
# tolerate absence. Includes every id used as a SET/DICT KEY in the folds (comment_id / clarify_id):
# a non-string there (e.g. a list) is unhashable and would TypeError _awaiting_clarification /
# _clarify_touched / terminally_resolved, instead of the promised fail-closed degrade.
_OPTIONAL_STRING_FIELDS = {
    "voz.reply": ("comment_id", "body"),
    "voz.clarify": ("comment_id", "clarify_id", "question"),
    "voz.clarify_answer": ("clarify_id", "body"),
    "voz.resolved": ("comment_id",),
    # direction.set.id is the fold's dict KEY (`items[iid]` in fold_direction) — a non-string is
    # unhashable and TypeErrors the fold / consistency check / direction_at. PRESENT-only: a legacy
    # {plan} blob with no id folds to a single "_plan" item, so absence is valid, a non-string is not.
    "direction.set": ("body", "id"),
}


# ── The lifecycle folds — openness, the actionable set, consistency ─────────────────────────────


def terminally_resolved(log, until_seq=None):
    """`comment_id`s with a TERMINAL `voz.resolved`. A `voz.reply` is presentation only; a parked
    `voz.clarify` is non-terminal. Openness keys on the ABSENCE of a member here (ADR-0017)."""
    return {e["payload"].get("comment_id")
            for e in _events(log, until_seq) if e.get("type") == "voz.resolved"}


def open_comments(log, until_seq=None):
    """Every `voz.comment` with no terminal `voz.resolved` (any target). A replied-but-unresolved
    or parked chat is still open. A fold, not a flag. `until_seq` bounds it at a cursor."""
    resolved = terminally_resolved(log, until_seq)
    return [e["payload"] for e in _events(log, until_seq)
            if e.get("type") == "voz.comment"
            and e["payload"].get("comment_id") not in resolved]


def _awaiting_clarification(log, until_seq=None):
    """`comment_id`s parked by a `voz.clarify` with NO subsequent `voz.clarify_answer` for that
    clarify. A parked-without-answer chat is open but NOT actionable (it lives only in the
    awaiting-clarification health count, never re-loaded — so it can't consume the cap every grill
    and starve fresh directives, SURFACE.md / ADR-0017)."""
    parked = {}          # comment_id -> set(clarify_id) still unanswered
    answered = set()     # clarify_ids that have a clarify_answer
    for e in _events(log, until_seq):
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.clarify":
            parked.setdefault(p.get("comment_id"), set()).add(p.get("clarify_id"))
        elif t == "voz.clarify_answer":
            answered.add(p.get("clarify_id"))
    return {cid for cid, clarifies in parked.items() if clarifies - answered}


def actionable_set(log, until_seq=None):
    """What a grill MAY load: open comments that are EITHER not awaiting clarification OR parked
    *with* a linked `voz.clarify_answer` (the answer re-enters the chat into the actionable set,
    terminally resolvable at the next grill). A parked-without-answer chat is excluded. SURFACE.md
    "Actionable set" invariant. `until_seq` bounds it at the grill's start cursor, so a comment
    arriving AFTER the cursor cannot enter THIS batch (ADR-0017 cursor-bound invariant — ordering is
    not race-dependent). Returns the comment payloads, in append order (deterministic)."""
    awaiting = _awaiting_clarification(log, until_seq)
    return [c for c in open_comments(log, until_seq) if c.get("comment_id") not in awaiting]


def clarify_context(log, comment_id, until_seq=None):
    """The linked clarification Q/A history for a comment: a list of {question, answer} for every
    `voz.clarify` on this comment_id paired with its `voz.clarify_answer` (answer None if still
    awaiting). The drain passes this to `reply_fn` so the generator RESOLVES using the mentee's
    answer (ADR-0017 'seeing that linked answer'), not just the comment body. Empty list if none."""
    questions, answers = [], {}
    for e in _events(log, until_seq):
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.clarify" and p.get("comment_id") == comment_id:
            questions.append((p.get("clarify_id"), p.get("question")))
        elif t == "voz.clarify_answer":
            answers[p.get("clarify_id")] = p.get("body")
    return [{"clarify_id": qid, "question": q, "answer": answers.get(qid)}
            for qid, q in questions]


def consistency_errors(log):
    """Resolution-consistency errors for the health strip (SURFACE.md): a DUPLICATE `voz.resolved`
    (more than one terminal outcome for a `comment_id`), an ORPHAN `voz.resolved` (no preceding
    `voz.comment`), and a `folded-to-direction`/`retired-direction` whose `direction_id` has no
    matching `direction.set`/`direction.dropped`. Symmetric across create/promote/retire."""
    comment_ids, resolved_counts = set(), {}
    set_origin, dropped_origin = {}, {}  # direction id -> origin_comment_id (None if absent)
    folds = []  # (comment_id, outcome, direction_id, resolved_origin)
    for e in _events(log):
        t, p = e.get("type"), e.get("payload", {})
        if t == "voz.comment":
            comment_ids.add(p.get("comment_id"))
        elif t == "voz.resolved":
            cid = p.get("comment_id")
            resolved_counts[cid] = resolved_counts.get(cid, 0) + 1
            if p.get("outcome") in ("folded-to-direction", "retired-direction"):
                folds.append((cid, p.get("outcome"), p.get("direction_id"),
                              p.get("origin_comment_id")))
        elif t == "direction.set":
            set_origin[p.get("id")] = p.get("origin_comment_id")
        elif t == "direction.dropped":
            dropped_origin[p.get("id")] = p.get("origin_comment_id")
    errors = []
    for cid, n in resolved_counts.items():
        if n > 1:
            errors.append({"kind": "duplicate-resolved", "comment_id": cid, "count": n})
        if cid not in comment_ids:
            errors.append({"kind": "orphan-resolved", "comment_id": cid})
    for cid, outcome, did, resolved_origin in folds:
        origins = set_origin if outcome == "folded-to-direction" else dropped_origin
        if did not in origins:
            errors.append({"kind": "dangling-direction", "comment_id": cid,
                           "outcome": outcome, "direction_id": did})
            continue
        # ADR-0007 / SURFACE.md provenance: the matched Direction mutation MUST carry an
        # origin_comment_id, and it must equal the resolved event's origin_comment_id — else the
        # steer⇄comment audit link is broken (a folded Directive with no/with wrong provenance).
        dir_origin = origins[did]
        if not dir_origin:
            errors.append({"kind": "provenance-missing", "comment_id": cid,
                           "outcome": outcome, "direction_id": did})
        elif dir_origin != resolved_origin:
            errors.append({"kind": "provenance-mismatch", "comment_id": cid,
                           "outcome": outcome, "direction_id": did,
                           "direction_origin": dir_origin, "resolved_origin": resolved_origin})
    return errors


# ── The legacy back-fill — shipped atomically with the lifecycle switch ──────────────────────────


def _legacy_targets(log):
    """`comment_id`s (in append order, deterministic) with a REAL `voz.reply` but NO terminal
    `voz.resolved` — the legacy-settled set the back-fill closes. A reply counts only if its body is
    a non-empty string: a bodyless / blank / schema-drifted `voz.reply` is NOT a usable answer, so
    back-filling `voz.resolved{replied}` from it would silently close an unanswered directive
    (ADR-0017) — that comment must stay open, not be marked legacy-settled."""
    replied = {e["payload"].get("comment_id")
               for e in _events(log)
               if e.get("type") == "voz.reply"
               and isinstance(e["payload"].get("body"), str) and e["payload"]["body"].strip()}
    resolved = terminally_resolved(log)
    # A comment with ANY voz.clarify history is DRAIN-OWNED, not a plain reply-only legacy chat —
    # the drain must terminally resolve it so it consumes the answer + clarify_context (ADR-0017).
    # Excluding only *awaiting* clarifies is insufficient: once answered, the comment leaves
    # _awaiting_clarification and an old reply would let the back-fill close it before the drain runs.
    # So exclude every clarify-touched comment from the reply-only back-fill, answered or not.
    clarify_owned = _clarify_touched(log)
    target_set = {cid for cid in replied
                  if cid and cid not in resolved and cid not in clarify_owned}
    order = [e["payload"].get("comment_id") for e in _events(log)
             if e.get("type") == "voz.comment"]
    return [cid for cid in order if cid in target_set]


def _clarify_touched(log):
    """`comment_id`s that have EVER been parked with a `voz.clarify` — answered or not. These are
    drain-owned (the drain consumes the answer + clarify_context to resolve them terminally), so the
    reply-only legacy back-fill must never close them, even after the clarify is answered."""
    return {e["payload"].get("comment_id")
            for e in _events(log) if e.get("type") == "voz.clarify"}


def backfill_legacy_resolved(log, grill_run_id="legacy-backfill", _force_targets=None):
    """Idempotently back-fill `voz.resolved{outcome: replied}` for every historical `voz.comment`
    that has a `voz.reply` but NO terminal `voz.resolved` (legacy-settled). Flipping `open_comments`
    to key on `voz.resolved` would otherwise RE-OPEN already-answered threads (incl. a hand-appended
    reply like the operator's "oi"); this back-fill keeps them closed.

    Idempotent even under CONCURRENT drains: the unresolved set is RE-COMPUTED under the eventlog
    lock (the `precondition`) against the durable log no concurrent writer can change, and any
    `comment_id` a racing drain already resolved is dropped from the batch there — so two concurrent
    back-fills never serialize a duplicate terminal `voz.resolved` (a permanent consistency error).
    Re-running adds NOTHING once the log is migrated. Returns the appended events.

    `_force_targets` (test seam) injects a stale pre-observed target list to exercise the race; the
    under-lock recheck still drops an already-resolved one."""
    targets = _force_targets if _force_targets is not None else _legacy_targets(log)
    if not targets:
        return []

    appended = []

    def _under_lock():
        # Re-derive the still-eligible subset UNDER the lock (authoritative), preserving the caller's
        # order. A target a concurrent drain resolved — or PARKED (a voz.clarify) — since we observed
        # it is dropped here, so a race can't back-fill over a now-parked or now-resolved chat.
        resolved_now = terminally_resolved(log)
        clarify_owned_now = _clarify_touched(log)
        live = [cid for cid in targets
                if cid not in resolved_now and cid not in clarify_owned_now]
        appended[:] = [("voz.resolved", "voz:backfill",
                        {"comment_id": cid, "outcome": "replied", "grill_run_id": grill_run_id})
                       for cid in live]
        if not appended:
            raise _NothingToBackfill()

    try:
        return eventlog.append_batch(appended, log=log, precondition=_under_lock)
    except _NothingToBackfill:
        return []


class _NothingToBackfill(Exception):
    """Raised under the lock when the recheck finds every target already resolved (a concurrent
    drain won the race) — aborts the back-fill with nothing written."""


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


def drain(log, reply_fn, grill_run_id=None, cap=DEFAULT_BATCH_CAP, run_backfill=True):
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
    # Serialize the WHOLE drain (snapshot → generate → close) across processes with an exclusive
    # flock on a sibling lockfile. The append-time version guard already keeps DATA consistent under
    # concurrency, but without this lock two overlapping live drains could each invoke the PAID
    # reply-generator for the same loaded comment before either close runs — the loser's expensive
    # OpenAI call is then discarded by the guard (a wasted spend, not idempotent). The lock makes the
    # second drain re-read the now-closed state and never generate for an already-resolved comment.
    with _drain_lock(log):
        # Fail closed on a corrupt log in the CORE path (not only the HTTP route): a malformed /
        # schema-drifted / seq-gapped log makes any canonical append forge a duplicate seq and the
        # folds raise — so degrade (no back-fill, no generation, no append) here too. This protects a
        # local-tool caller that bypasses the route's gate. The check is under the drain lock, so it
        # is consistent with the close attempts below.
        if not log_is_intact(log):
            return []
        # Ship the lifecycle switch atomically with the back-fill (ADR-0017 migration; acceptance h):
        # close every historical reply-only comment so the switch never RE-OPENS / the drain never
        # RE-PROCESSES it. Idempotent. `run_backfill=False` lets a caller that already migrated under
        # its own fail-soft guard (the HTTP route) skip this second, unguarded call.
        if run_backfill:
            backfill_legacy_resolved(log)
        start_cursor = _start_cursor(log)
        # Snapshot the actionable set AT the cursor: a comment arriving after start_cursor stays open
        # as overflow — batch selection is cursor-bound, never race-dependent (ADR-0017).
        loaded, _overflow = rank_and_cap(actionable_set(log, until_seq=start_cursor), cap)
        for comment in loaded:
            # Enrich each loaded comment with its linked clarify Q/A so reply_fn resolves USING the
            # mentee's answer (ADR-0017 'seeing that linked answer'), not just the comment body.
            comment = {**comment,
                       "clarify": clarify_context(log, comment["comment_id"], until_seq=start_cursor)}
            plan = reply_fn(comment)
            _close_one(log, comment, plan, grill_run_id, start_cursor)
        return loaded


import contextlib  # noqa: E402
import fcntl  # noqa: E402


@contextlib.contextmanager
def _drain_lock(log):
    """An exclusive cross-process lock for the duration of a drain — serializes overlapping drains
    so the paid reply-generator is never invoked twice for the same comment (cost-idempotency). A
    sibling lockfile beside the log, flock-held, mirrors eventlog's locking discipline. Separate
    from the eventlog append lock (a finer lock the closes still take) — this one spans the whole
    snapshot→generate→close window, which the append lock deliberately does not."""
    from pathlib import Path
    lock = Path(log).with_name(Path(log).name + ".drain.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


# ── The LIVE reply-generator — wired to the edge's chat router. SPENDS THE USER'S OpenAI API. ─────
#
# ⚠️ COST: each call hits the edge's `chat` router (gpt-5.4, on ~/edge/secrets/openai.env — the
# user's OpenAI API key), billed PER CALL. This factory is NEVER invoked by the test suite (every
# test injects a stub) and the HTTP route never builds it unless the operator explicitly opts in
# (EDGE_DRAIN_LIVE=1). The model is configured in agent.yaml `routers.chat.model` (gpt-5.4); swap
# it there. To run a live drain from a local tool: `drain(log, live_reply_generator())`.

_LIVE_PROMPT = (
    "You are the edge resolving a mentee Directive on the Voz rail. Reply directly, technically, "
    "skeptically — name the tradeoff. Decide the OUTCOME and return ONLY JSON:\n"
    '  - a plain answer:      {"outcome":"reply","reply":"<your reply>"}\n'
    '  - a STANDING steer     {"outcome":"directive","reply":"<your reply>",'
    '"direction_body":"<the steer, imperative>"}  (use this only when the Directive moves strategy)\n'
    '  - you must ASK first:  {"outcome":"park","question":"<your clarifying question>"}\n'
    "Directive:\n\n")


def _build_live_prompt(comment):
    """The live prompt for a loaded comment, folding in any clarification Q/A so the reply RESOLVES
    using the mentee's answer, never re-asks past it (ADR-0017 'seeing that linked answer')."""
    prompt = _LIVE_PROMPT + comment["body"]
    for qa in comment.get("clarify") or []:
        prompt += f"\n\nYou earlier asked: {qa['question']}"
        if qa.get("answer"):
            prompt += f"\nThe mentee answered: {qa['answer']}"
    return prompt


def parse_live_plan(raw):
    """Parse a model's raw output into a VALIDATED close plan. A `directive` outcome folds to
    `direction.set` (carrying the steer body); a `reply` is a plain terminal reply; ANYTHING the
    model returns that does not validate (not JSON, unknown outcome, missing required field) is
    coerced to a PARK — an autonomous grill may only park, never fabricate a terminal `replied` that
    would silently close a standing Directive as a plain reply and hide a lost steer (ADR-0017)."""
    import json
    park = {"park": True, "question": "Could you clarify what you'd like me to do with this?"}

    def _str(v):
        """A non-empty STRING field, else None — the render path html.escapes these, so a non-str
        (dict/list/number) or blank must never be persisted (it would poison the log / 500 a view)."""
        return v.strip() if isinstance(v, str) and v.strip() else None

    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return park
    if not isinstance(d, dict):
        return park
    outcome = d.get("outcome")
    if outcome == "park":
        q = _str(d.get("question"))
        return {"park": True, "question": q} if q else park
    if outcome == "directive":
        reply, body = _str(d.get("reply")), _str(d.get("direction_body"))
        if reply and body:
            return {"reply": reply, "directive": True, "direction_body": body}
        return park  # a directive with no valid reply+steer body is not a fold → park, don't fake
    if outcome == "reply":
        reply = _str(d.get("reply"))
        return {"reply": reply} if reply else park
    return park  # unknown / missing outcome → park, never fabricate a terminal outcome


def structured_reply_generator(model_fn):
    """A reply-generator (callable(comment) -> validated plan) over an injected `model_fn(prompt) ->
    raw_text`. Separating the model call lets tests drive the full structured/fold/park contract with
    a FAKE completer (no real LLM). `live_reply_generator()` wires `model_fn` to the edge chat router."""
    def gen(comment):
        return parse_live_plan(model_fn(_build_live_prompt(comment)))
    return gen


def live_reply_generator():
    """Build the LIVE reply-generator on the edge's chat router (structured outcome contract).

    ⚠️ Returns a callable that SPENDS THE USER'S OpenAI API per invocation (gpt-5.4 on
    ~/edge/secrets/openai.env). Imported lazily so the module loads with no edge runtime present;
    raises if the runtime/secret is unavailable rather than silently degrading. The model lives in
    agent.yaml `routers.chat`. The returned generator classifies each Directive (reply / standing /
    park) so a live drain DOES fold standing steers to direction.set — never closes one as a plain
    `replied` (parse_live_plan parks on any unclassifiable output)."""
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
    return structured_reply_generator(lambda prompt: _llm.complete(client, model, prompt))
