"""eventlog — Tier-0 append-only event log, the source of truth (ADR-0006). Genotype tool.

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated. Nothing is
true unless it is an event here. The graph and the standing pages are projections of this log —
folds that replay deterministically, so a past cursor reconstructs that past state byte-faithfully
(strategic versioning). No event-store framework: append-only JSONL + pure-function folds.
"""
import fcntl
import hashlib
import inspect
import json
import math
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

# persist ONLY well-formed authored declarations (each matches its proof bind)
from lineage import (
    EXPERIMENT_ID_RE,
    normalize_bears_on,
    normalize_experiment_curation,
    normalize_lineage,
    normalize_para,
    normalize_reports_on,
)

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "state" / "events" / "log.jsonl"
DIRECTION = REPO / "state" / "direction.md"
CORPUS = REPO / "state" / "corpus.md"


def cosine(a, b):
    """Pure cosine similarity over two equal-length numeric vectors (ADR-0009, source-feedback
    hypothesis tier — embedding attribution). A zero vector yields 0.0, never a divide-by-zero —
    degrade, never crash. The actual OpenAI embedding call lives in sweep; only the math is here."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _physical_len(log):
    """The count of physical (non-blank) lines in the log — the AUTHORITATIVE write base for seq
    stamping (`seq = base + i + 1`), decoupled from the tolerant projection `read()`. `read()` now
    SKIPS a JSON-valid non-dict line (codex Slice-4 round-2), so using `len(read())` as the append
    base would UNDERCOUNT a log with a corrupt non-event line mid-history and stamp a DUPLICATE seq —
    corrupting the append-only source of truth under the exact corruption model this slice survives
    (codex round-3 [high]). The seq invariant (`log_is_intact`: seqs are exactly 1..N in file order)
    is physical-line-count-based, so the write base must be too — strict for writes, tolerant only
    for read-side projections."""
    log = Path(log)
    if not log.exists():
        return 0
    # `line.strip()` — the SAME blank-line semantics log_is_intact uses (it skips `not line.strip()`).
    # A whitespace-only line is NOT a seq slot; counting it would stamp the next seq one too high and
    # permanently break contiguity (codex Slice-4 round-5 [high]). A JSON-valid corrupt non-event line
    # (`[]`) IS counted — it occupied a seq when written, so the base must include it.
    return sum(1 for line in log.read_text().splitlines() if line.strip())


def append(type, subject, payload, log=LOG):
    """Append ONE event as a JSON line; stamp a monotonic seq + ISO ts. Returns the event."""
    return append_batch([(type, subject, payload)], log=log)[0]


def append_batch(events, log=LOG, precondition=None):
    """Append SEVERAL events as JSON lines in ONE indivisible file write — there is no
    intermediate state in which only some of them landed (C3 atomicity, #3). Each is stamped
    with a monotonic seq + ISO ts, continuing the log's count. `events` is a list of
    (type, subject, payload) tuples; returns the stamped events.

    The ENTIRE read-base / stamp / write critical section is serialized across concurrent
    writers by an exclusive `fcntl.flock` on a sibling lockfile: two overlapping callers would
    otherwise read the same `base` and append duplicate seq ranges, breaking the cursor/replay
    invariant the folds depend on. We flush + fsync before releasing the lock, so the next
    writer's `read()` sees a fully-durable log when it computes its own base.

    `precondition` (optional) is a zero-arg callable evaluated UNDER the lock, against the
    durable log state no concurrent writer can change — it may raise to abort the append with
    nothing written. This is what makes a check-then-append (e.g. the ADR-0016 wake gate)
    authoritative rather than a TOCTOU fast-fail."""
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    lock = log.with_name(log.name + ".lock")
    with lock.open("w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            if precondition is not None:
                precondition()
            base = _physical_len(log)
            stamped = [{"seq": base + i + 1, "ts": datetime.now(timezone.utc).isoformat(),
                        "type": t, "subject": s, "payload": p}
                       for i, (t, s, p) in enumerate(events)]
            with log.open("a") as fh:
                fh.write("".join(json.dumps(ev) + "\n" for ev in stamped))
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    return stamped


def read(types=None, until_seq=None, until_ts=None, log=LOG):
    """Replay the log in order, optionally keeping only `types` and stopping at a cursor
    (until_seq: seq<=n; until_ts: ts<=t). The cursor is what makes replay reconstruct a past.

    Skips a JSON-valid NON-dict line (`[]`, `42`, a bare string): it is not an event envelope, and
    the filters below index `e["type"]`/`e["seq"]`/`e["ts"]`, so a non-dict would TypeError the read
    BEFORE any tolerant fold (e.g. fold_direction) could apply — aborting the sweep's projection on a
    corrupt log (codex Slice-4 round-2 [medium]). Skipping centrally keeps the projections fail-dark;
    log_is_intact still surfaces the corruption as degraded (the raw lines are untouched)."""
    log = Path(log)
    if not log.exists():
        return []
    events = [e for line in log.read_text().splitlines() if line.strip()
              for e in [json.loads(line)] if isinstance(e, dict)]
    if types is not None:
        events = [e for e in events if e.get("type") in types]
    if until_seq is not None:
        events = [e for e in events if e["seq"] <= until_seq]
    if until_ts is not None:
        events = [e for e in events if e["ts"] <= until_ts]
    return events


DIRECTION_TYPES = [
    "direction.proposed", "direction.set", "direction.dropped", "sessao.excluded",
    "session.topics.generation",
]
KIND_ORDER = ["phase", "priority", "constraint", "thread"]


def fold_direction(events):
    """Pure fold of direction.* events → addressable items in two tiers (ADR-0007).

    Per-id, in seq order: `direction.proposed` opens/updates a `proposed` item; `direction.set`
    opens/updates a `set` item and **outranks** proposed for the same id (curado > hipótese, a
    correção sempre ganha); `direction.dropped` removes the id (persist-until-dropped — nothing is
    lost by omission). Returns {"set": [...], "proposed": [...]} in insertion order.

    Fail-dark over a corrupt log (Slice 4 [high]): `id`/`supersedes` are used AS dict keys, so a
    JSON-valid event with a non-string (unhashable, e.g. list) key field would TypeError this fold —
    the canonical fold every projection (direction_at/project_direction/the sweep) flows through.
    A corrupt-keyed event is SKIPPED, not crashed; the valid steers still fold (the health strip /
    log_is_intact surfaces the corruption as degraded). `supersedes` is honored only when usable.
    """
    def _key(v):  # a usable dict key = a hashable str; anything else is corrupt → not a key
        return v if isinstance(v, str) else None

    events = [event for event in events if isinstance(event, dict)]
    excluded_sessions = {
        payload["sessao_id"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") == "sessao.excluded"
        and isinstance(payload, dict)
        and isinstance(payload.get("sessao_id"), str)
    }
    generations = [
        event for event in events
        if event.get("type") == "session.topics.generation"
        and isinstance(event.get("payload"), dict)
        and isinstance(event["payload"].get("session_ids"), list)
    ]
    active_generation = (set(generations[-1]["payload"]["session_ids"])
                         if generations else None)
    items = {}  # id -> item (carries 'tier')
    for e in events:
        t = e.get("type")
        payload = e.get("payload")
        # a TRUTHY non-dict payload (a string / non-empty list) would AttributeError p.get(...) below
        # — `or {}` only catches the falsy case (codex Slice-4 round-3 [medium]). isinstance is the
        # real guard: a non-dict payload folds to {} (no foldable item), the valid events still fold.
        p = payload if isinstance(payload, dict) else {}
        if t == "direction.proposed":
            iid = _key(p.get("id"))
            if iid is None:
                continue  # absent OR corrupt-typed id — not a foldable proposed item
            relates_to = p.get("relates_to")
            if (isinstance(relates_to, list)
                    and any(isinstance(ref, dict)
                            and ref.get("session") in excluded_sessions
                            for ref in relates_to)):
                continue  # automatic proposal has contaminated/non-operator voice evidence
            if (active_generation is not None and isinstance(relates_to, list)
                    and any(isinstance(ref, dict) and isinstance(ref.get("session"), str)
                            and ref["session"] not in active_generation
                            for ref in relates_to)):
                continue  # recent-topic proposal no longer has evidence in the active generation
            if items.get(iid, {}).get("tier") == "set":
                continue  # set outranks proposed
            items[iid] = {"id": iid, "body": p.get("body", ""), "kind": p.get("kind", "thread"),
                          "from_artefato": p.get("from_artefato"), "relates_to": relates_to,
                          "tier": "proposed"}
        elif t == "direction.set":
            raw_id = p.get("id")
            if raw_id is not None and _key(raw_id) is None:
                continue  # a present-but-corrupt id can't key the fold — skip (fail-dark)
            iid = _key(raw_id) or "_plan"  # legacy {plan} blob (no id) folds to a single set item
            sup = _key(p.get("supersedes"))  # a corrupt supersedes is ignored, never an items.pop key
            if sup and sup != iid:
                items.pop(sup, None)  # a set RETIRES the (different) id it supersedes — not just
                                      # same-id overwrite/dropped. Codex #28-review: supersedes was
                                      # stored but never honored, leaving the old steer active.
            items[iid] = {"id": iid, "body": p.get("body", p.get("plan", "")),
                          "kind": p.get("kind", "thread"), "supersedes": sup,
                          "origin_comment_id": p.get("origin_comment_id"),
                          "tier": "set"}
        elif t == "direction.dropped":
            items.pop(_key(p.get("id")), None)
    return {"set": [i for i in items.values() if i["tier"] == "set"],
            "proposed": [i for i in items.values() if i["tier"] == "proposed"]}


def direction_at(seq=None, ts=None, log=LOG):
    """Fold direction.* events up to a cursor → {"set":[...], "proposed":[...]} (ADR-0007).
    Pure: replaying to a past cursor reconstructs that past, both tiers — strategic versioning.
    Returns None when there are no direction events at all."""
    evs = read(types=DIRECTION_TYPES, until_seq=seq, until_ts=ts, log=log)
    return fold_direction(evs) if evs else None


def _require_body(body, what):
    """Reject an empty/whitespace feeder body before it lands (Codex gate finding [high]): a stage-(ii)
    feeder with no real content must never be writable, so the grill gate's 'landed' is never hollow."""
    if not (body and body.strip()):
        raise ValueError(f"cannot append {what} with an empty/whitespace body")


def propose(id, body, kind="thread", from_artefato=None, relates_to=None, log=LOG):
    """Append a `direction.proposed` item (the non-curated tier — grill achados / artefato candidates).
    Raises ValueError on an empty/whitespace body — no hollow direction lands."""
    _require_body(body, "direction.proposed")
    return append("direction.proposed", "direction",
                  {"id": id, "body": body, "kind": kind,
                   "from_artefato": from_artefato, "relates_to": relates_to}, log=log)


def set_direction(id, body, kind="thread", supersedes=None, log=LOG):
    """Append a `direction.set` item (the curated tier — Voz only; promotes/supersedes a proposed id).
    Raises ValueError on an empty/whitespace body — no hollow direction lands."""
    _require_body(body, "direction.set")
    return append("direction.set", "direction",
                  {"id": id, "body": body, "kind": kind, "supersedes": supersedes}, log=log)


def drop(id, reason="", log=LOG):
    """Append a `direction.dropped` event — retire a thread (the only way an item leaves)."""
    return append("direction.dropped", "direction", {"id": id, "reason": reason}, log=log)


OBJECTIVE_TYPES = ["objective.set"]


def set_objective(body, rationale=None, log=LOG):
    """Append an `objective.set` event — the mentee's **confirmed objective** (abduced from behavior,
    confirmed by Voz). The grill's anchor, first-class. It MAY contradict the declared agent.yaml
    mission: this is the *revealed/confirmed* objective, not the stated one (when they diverge, that
    is the highest-insight finding). Latest-wins, versioned — mirrors set_direction. `rationale` is
    the optional why (e.g. the say-A-do-B gap that yielded this read). Raises ValueError on an
    empty/whitespace body, and strips the stored body — no hollow objective lands."""
    _require_body(body, "objective.set")
    return append("objective.set", "objective", {"body": body.strip(), "rationale": rationale}, log=log)


def objective_at(seq=None, ts=None, log=LOG):
    """Fold `objective.set` events up to a cursor → the latest objective {"body", "rationale"} (the
    anchor everything is measured against). Latest-wins (mirrors direction_at's curated tier). Pure:
    replaying to a past cursor reconstructs that past anchor — strategic versioning. None when no
    objective has ever been set (the sensible empty-case for a saved-as-confirmed-hypothesis prior)."""
    evs = read(types=OBJECTIVE_TYPES, until_seq=seq, until_ts=ts, log=log)
    if not evs:
        return None
    p = evs[-1].get("payload", {}) or {}
    return {"body": p.get("body", ""), "rationale": p.get("rationale")}


REPORT_TYPES = ["direction.report"]


def report_direction(body, distills=None, cites=None, log=LOG):
    """Append a `direction.report` event — the rolling steer ("o direcionamento"): the **full prose
    report** (objective + the steer + the live insight) the briefing injects every wake and the grill
    reads as the prior. Additive to Direction (the proposed/set bullets are the skeleton; this report
    is the flesh). Provenance — "show your work": `distills` = the existing **threads** it synthesized
    from, `cites` = the **sources**; link only real ones (never fabricate), so the steer is traceable,
    not pronounced. Telephone-game guard: each report re-derives from the data, the prior is one input
    for continuity — not the source of truth; never summarize-the-summary. Raises ValueError on an
    empty/whitespace body — no hollow direcionamento lands."""
    _require_body(body, "direction.report")
    return append("direction.report", "direction",
                  {"body": body, "distills": distills or [], "cites": cites or []}, log=log)


def report_at(seq=None, ts=None, log=LOG):
    """Fold `direction.report` events up to a cursor → {"latest": {...}|None, "lineage": [...]}. The
    **latest** is what the briefing injects (the present steer); the **lineage** is the priors the
    grill reads to re-derive against, newest-first (saved-as-confirmed-hypothesis — priors, not
    gospel). Pure: replaying to a past cursor reconstructs that past report + its lineage — strategic
    versioning, as direction_at. Empty → {"latest": None, "lineage": []}."""
    evs = read(types=REPORT_TYPES, until_seq=seq, until_ts=ts, log=log)
    items = [{"body": (e.get("payload") or {}).get("body", ""),
              "distills": (e.get("payload") or {}).get("distills", []),
              "cites": (e.get("payload") or {}).get("cites", []),
              "ts": e.get("ts")} for e in evs]
    lineage = list(reversed(items))
    return {"latest": lineage[0] if lineage else None, "lineage": lineage}


def publish_artefato(slug, intent, proposes=None, distills=None, cites=None, log=LOG):
    """MIGRATION/TEST-ONLY (S2, E1c): the legacy two-arg publish wrapper. It carries NO
    `dispatch_id`, so on the CANONICAL log it now fails loud inside `publish_artefato_atomic`
    — by design: production publishes go through publisher.publish → publish_artefato_atomic
    with the proof-bound dispatch_id (E1b), and this wrapper's only remaining call-sites are
    tests/migrations over custom logs (verified at the S2 slice: zero production callers).
    Kept so the legacy shape stays exercisable, never grown the param (the call-sites say so).

    `intent` is REQUIRED (positional, no default). The call publishes the `artefato.published`
    AND its `intent.kernel` in ONE indivisible write via `publish_artefato_atomic` — so this
    path pairs the kernel and **cannot** ship C3 debt (Codex re-review #2/round 2). An
    empty/missing intent raises before anything lands: there is NO kernel-less path. The
    Artefato **declares** candidate steers in `proposes`; it does NOT write Direction itself —
    the sweep consolidates them. Returns (published_event, kernel_event).

    Manufacturing kernel-less C3 debt on purpose (for the migration over a legacy log or to exercise
    the `artefatos_without_kernel`/`require_kernels` detectors) is reserved to the explicitly-named,
    non-producer-facing `_append_orphan_published_for_test` — never this function."""
    return publish_artefato_atomic(slug, intent, proposes=proposes, distills=distills,
                                   cites=cites, log=log)


def _append_orphan_published_for_test(slug, proposes=None, distills=None, cites=None, log=LOG):
    """MIGRATION/DETECTOR-ONLY, NOT producer-facing: append a BARE `artefato.published` with no
    `intent.kernel` — i.e. deliberately manufacture C3 debt. This exists solely so the C3 detectors
    (`artefatos_without_kernel`, `require_kernels`) and any migration over a legacy log have a way to
    create/observe the kernel-less state; the producer-facing `publish_artefato` (with an intent)
    cannot. The leading underscore + name make it unmistakably off the production path."""
    return append("artefato.published", f"artefato:{slug}",
                  {"slug": slug, "proposes": proposes or [], "distills": distills or [],
                   "cites": cites or []}, log=log)


def _stripped_intent(intent):
    """The C3 content rule: a kernel's *why* counts only when it is a non-empty stripped string.
    Returns the stripped intent, or None for a non-string / blank / whitespace intent — so a hollow
    kernel never becomes a recorded why (Codex gate round-4 [high])."""
    if isinstance(intent, str) and intent.strip():
        return intent.strip()
    return None


def kernel(slug, intent, log=LOG):
    """Append an `intent.kernel` event (CONTRACT C3) — the durable *why* of a dispatch's Artefato:
    what is open, the next bet. Mandatory at close; the corpus folds it alongside artefato.published
    (paired by slug), and the briefing's Recap projects it. The kernel and a cold transcript can
    disagree on intent; the kernel wins. Raises ValueError on a non-string / empty / whitespace
    intent, and stores the STRIPPED intent — a hollow kernel can never be the recorded why and so
    can never clear C3 debt (Codex gate round-4 [high])."""
    stripped = _stripped_intent(intent)
    if stripped is None:
        raise ValueError(f"cannot append intent.kernel for {slug!r} with an empty/non-string intent")
    return append("intent.kernel", f"artefato:{slug}", {"slug": slug, "intent": stripped}, log=log)


# R6 (S10) — the countable adoption telemetry fields. A record is "usable" only if it carries ALL of them
# (each a real value); any missing/partial/malformed payload is replaced with an error-marked record whose
# countable fields are ALL null (uncountable), so dashboards never read false adoption telemetry.
_ADOPTION_FIELDS = ("owed", "satisfied", "degraded", "shortfall", "capability_state")


def _normalized_adoption(slug, skill, adoption):
    """Return a WELL-SHAPED artefato.adoption payload for `slug`. A caller's dict is accepted as COUNTABLE
    telemetry ONLY when `error` is falsy AND every `_ADOPTION_FIELDS` value is a real bool. Anything else —
    None, non-dict, a record carrying an `error`, a missing/non-bool countable field — becomes an
    error-marked record whose countable fields are ALL null (uncountable), so dashboards never read false
    or half telemetry (Codex S10). An errored caller record's `error` message is preserved."""
    def _err(reason):
        return {"slug": slug, "producer": skill, "owed": None, "satisfied": None,
                "degraded": None, "shortfall": None, "capability_state": None, "error": reason}
    if adoption is None:
        return _err("no-adoption-supplied")
    if not isinstance(adoption, dict):
        return _err("malformed-adoption")
    if adoption.get("error"):
        return _err(adoption["error"])   # an errored caller record → null countable, keep the message
    if not all(isinstance(adoption.get(k), bool) for k in _ADOPTION_FIELDS):
        return _err("malformed-adoption")
    if not (isinstance(skill, str) and skill.strip()):
        return _err("malformed-adoption")   # countable per-producer telemetry needs a real producer
    merged = dict(adoption)
    merged["slug"] = slug
    merged["producer"] = skill    # overwrite, never trust a caller-supplied producer (anti-misattribution)
    merged["error"] = None
    return merged


def _is_canonical_log(log):
    """True iff `log` IS the install's canonical event log — compared by NORMALIZED PATH, the
    same rule as publisher._is_canonical_log (path-equivalence, not object identity). The E1c
    compatibility contract keys on this: `dispatch_id` is REQUIRED exactly where the yield join
    (S7) will read it — the canonical log; a temp/custom log (tests, dry-runs) tolerates an
    absent id and records null honestly. Reads the module-level LOG at CALL time (not a bound
    default) so a test can point the canonical path at a fixture. A non-path log → not
    canonical (never raises)."""
    if log is LOG:
        return True
    try:
        return Path(log).resolve() == Path(LOG).resolve()
    except Exception:  # noqa: BLE001 — a non-path log → not canonical
        return False


def test_dispatch_id():
    """TEST-ONLY (S2, E1c): mint a SYNTHETIC dispatch_id for tests/custom logs — VISIBLY
    synthetic (`test-` prefix) so it can never be mistaken for a predispatch-minted identity
    in a real join. Production dispatches get their id from predispatch.mint_dispatch_id() at
    wake and carry it explicitly (E1); this helper exists so a test exercising the
    canonical-path requirement injects an id instead of weakening the requirement."""
    return f"test-{secrets.token_hex(8)}"


def publish_artefato_atomic(slug, intent, proposes=None, distills=None, cites=None,
                            spec=None, log=LOG, *, lineage=None, skill=None, require_wake=False,
                            adoption=None, dispatch_id=None, residuals=None, gate=None,
                            bears_on=None, para=None, reports_on=None,
                            experiment_curation=None, _rite_authorized=False):
    """Publish an Artefato AND its `intent.kernel` in ONE indivisible write (CONTRACT C3 at the
    publish seam): you cannot publish without the *why*. Both events land in a single
    `append_batch` — there is no crash window in which `published` exists without its kernel (#3).
    Raises ValueError when intent is missing/empty — the kernel is mandatory, so the published
    event never lands without it. Additive: the legacy publish_artefato + kernel two-call path
    stays callable. Returns (published_event, kernel_event).

    Codex round-10 [high]: the published event carries the proof-bound `spec` (the Artefato
    `content`) in its payload, INSIDE this same single batch. The page (blog/entries/<slug>.html)
    is a PROJECTION (ADR-0006: the log is truth); carrying the spec makes the page fully
    regenerable from the log alone, so a page-write failure after this commit is recoverable
    (publisher.reproject_missing_pages) rather than an unrecoverable dangling-state.

    Cortex-v1 (brick-1, slice L2): the payload also carries the authored typed `lineage` (keyword-
    only; the legacy positional form stops at `log`) — builds_on/supersedes/contradicts, the same
    list the close proof binds — so it folds onto the corpus item (fold_corpus) and a later slice
    replays it as DIRECTED edges. No lineage folds to [].

    S2 (E1/E1b/E1c): the payload carries `dispatch_id` — the identity the yield join (S7) keys
    on, minted at predispatch and carried EXPLICITLY to this seam (never reconstructed from
    "the last dispatch.open before the publish", E1). REQUIRED on the CANONICAL log: an
    absent/empty id fails loud with nothing written (opcional-em-produção reabriria o join sem
    identidade, E1c). A temp/custom log (tests, dry-runs) tolerates an absent id — recorded as
    null, never fabricated; tests wanting a real-shaped id inject `test_dispatch_id()`.

    Curadoria autoral: the payload also carries `para_default` — the operador-mentee name
    (`_identity.mentee()`) derived HERE when the authored `para` is empty (todo artefato é PARA
    alguém), the `origin` pattern: derived at the seam, never a caller arg, never in the digest
    (install identity, not forgeable producer data). An explicit `para` keeps it None."""
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")
    # The legacy prose publish road is CLOSED for the rito-migrated producers at the COMMIT
    # primitive itself (codex adversarial gate), not just at publisher.publish: a migrated
    # producer's ONLY road to a published event is the rite (rito.run_rito → publisher.publish_rito,
    # which passes _rite_authorized=True here). A direct atomic commit for a migrated skill is
    # refused — so no back door (a hand-rolled eventlog.publish_artefato_atomic snippet, or a
    # close.run_close publish_fn pointed here) can land a legacy artefato. prototype/lazer excepted.
    import producer_descriptor  # lazy: keep the storage layer import-light
    if not _rite_authorized and skill in producer_descriptor.RITO_PRODUCERS:
        raise ValueError(
            f"{skill}: legacy publish is closed for rito producers — commit through the rite "
            "(rito.run_rito → publisher.publish_rito), not a direct atomic commit "
            "(docs/rito-runtime.md). prototype/lazer excepted.")
    if _is_canonical_log(log) and not (isinstance(dispatch_id, str) and dispatch_id.strip()):
        raise ValueError(
            f"cannot publish artefato {slug!r} to the canonical log without a dispatch_id "
            "(E1c: the yield join's identity — minted by tools/predispatch.py at wake, read "
            "from its DISPATCH_ID line and carried explicitly; tests/custom logs inject "
            "eventlog.test_dispatch_id())")

    def _wake_gate():
        # ADR-0016, authoritative form (codex gate): evaluated UNDER append_batch's lock, so one
        # stamp admits exactly ONE publish — a concurrent caller that raced past an early
        # fast-fail check still loses here, with nothing written. S2 gate D1: an id-carrying
        # publish gates on the IDENTITY-HELD check (E1: the id is consumed under THIS lock —
        # concurrent dispatches never spend each other's stamps, and an id no wake minted never
        # publishes); the legacy global check remains only for id-less callers.
        if isinstance(dispatch_id, str) and dispatch_id.strip():
            if not wake_fresh_for(dispatch_id, log=log):
                raise RuntimeError(
                    f"no-wake: cannot publish {slug!r} under dispatch_id {dispatch_id!r} — "
                    "no unconsumed dispatch.open minted that id on this log (E1 identity-held "
                    "gate; ADR-0016: run tools/predispatch.py and carry ITS id; one wake per "
                    "publish)")
            # A beat-origin wake is autonomous exploration.  Its open Direction/Wayfind state is
            # context, not evidence that a publishable topic exists.  O dente NA CANETA
            # (ADR-0024): a beat publish spends the wake only against a LIVE pauta.proposta —
            # the funnel whose floors already judged the topic (substrato, delta_voz baseline,
            # gate da abordagem).  A user_requested dispatch is already opened by the user's
            # explicit request and does not need this ambient gate.
            if _is_canonical_log(log) and dispatch_origin(dispatch_id, log=log) == "beat":
                import pauta as _pauta  # lazy: pauta imports eventlog at module load
                if not isinstance(_pauta.proposta_for(dispatch_id, log=log), dict):
                    raise RuntimeError(
                        f"no-proposta: cannot publish {slug!r} under beat dispatch "
                        f"{dispatch_id!r} — o dente (ADR-0024): sem pauta.proposta viva; rode "
                        "o funil da Pauta (tools/pauta.py sortear -> shortlist -> propose)")
        elif not wake_fresh(log=log):
            raise RuntimeError(
                f"no-wake: cannot publish {slug!r} — no dispatch.open newer than the last "
                "artefato.published on this log (ADR-0016: run tools/predispatch.py; "
                "one wake per publish)")

    # Curadoria autoral (§6, regra do operador 2026-07-05): todo artefato é PARA alguém — com
    # `para` autorado vazio, o alvo default é o operador/mentee. DERIVADO aqui na costura (o
    # padrão `origin`, codex meta-gate #5: nunca um arg de caller) e FORA do digest (identidade
    # do install, não dado forjável de produtor); `para` no evento fica HONESTO (só o autorado,
    # digest-bound). Runtime degrade: mentee irresolvível → None, nunca um literal nem um crash.
    para = normalize_para(para)
    try:
        import _identity
        para_default = None if para else _identity.mentee()
    except Exception:  # noqa: BLE001 — identity must never block a publish (degrade, não crash)
        para_default = None
    # R6 (S10): EVERY published artefato carries a WELL-SHAPED adoption event in the SAME indivisible batch
    # — durable, no crash window, and no caller of this boundary (publisher, the legacy publish_artefato
    # wrapper, a direct call) can commit a published artefato with NO or MALFORMED adoption telemetry
    # (Codex S10). A None / partial / non-dict payload is replaced with an error-marked record whose
    # countable fields are all null (uncountable), so dashboards never read false telemetry.
    adoption = _normalized_adoption(slug, skill, adoption)
    reports_on = normalize_reports_on(reports_on)
    experiment_curations = normalize_experiment_curation(
        reports_on, experiment_curation, report_slug=slug, by=skill)
    events = [
        ("artefato.published", f"artefato:{slug}",
         {"slug": slug, "proposes": proposes or [], "distills": distills or [],
          "cites": cites or [], "lineage": normalize_lineage(lineage), "spec": spec,
          "skill": skill, "dispatch_id": dispatch_id,
          # ticket 05 (hierarquia de ORIGEM): the artefato CARRIES where it came from — DERIVED
          # here from the minting dispatch.open (codex meta-gate #5: no caller arg, so a producer
          # can never fabricate user_requested the wake did not declare). Default beat: an
          # artefato of unknown origin weighs as exploração, never as o gradiente.
          "origin": dispatch_origin(dispatch_id, log=log),
          # S6 (design-close §3/§5): the unaddressed criticism a publish-with-residuals carried, as a
          # FIRST-CLASS event field (distinct name from the `residual` channel). None on a normal publish.
          "residuals": residuals,
          # B.1 (ticket B): o verdict do gate como campo do MESMO batch atômico — sem novo tipo de
          # evento, replayável (o grafo já computava e jogava fora). None num publish legado/sem gate.
          "gate": gate,
          # Ticket A (ontologia §2b/§6): bears_on = as declarações valenciadas artefato→hipótese
          # (multivalência nativa, O-6), para = os parceiros-alvo (artefato-PARA->parceiro) e
          # reports_on = o(s) Experiment(s) que este report-artefato torna navegáveis —
          # NORMALIZADOS aqui (o mesmo sanitizer que o proof digest usa), digest-bound como lineage.
          "bears_on": normalize_bears_on(bears_on), "para": para,
          "reports_on": reports_on,
          # curadoria autoral: o alvo default (mentee) quando o autorado é vazio — derivado
          # acima, campo próprio (o `para` autorado nunca se mistura com o derivado).
          "para_default": para_default}),
        ("intent.kernel", f"artefato:{slug}", {"slug": slug, "intent": intent}),
        ("artefato.adoption", f"artefato:{slug}", adoption),
        # tkt-003: Assemble queue is log truth — every publish enters assembly.pending
        # (same batch as published so there is no crash window without a pending row).
        # package_id is per-item (slug); drain via mark_assembly_done/failed (Assemble worker).
        ("assembly.pending", f"assembly:artefato:{slug}", {
            "package_id": f"artefato:{slug}",
            "kind": "artefato",
            "ref": slug,
            "by": skill,
            "dispatch_id": dispatch_id,
        }),
    ]
    events.extend(
        ("experiment.curated", f"experiment:{curation['experiment_id']}", curation)
        for curation in experiment_curations
    )
    written = append_batch(events, log=log, precondition=_wake_gate if require_wake else None)
    return written[0], written[1]


def require_kernels(log=LOG):
    """Guard form of the C3 invariant (vs the non-fatal `artefatos_without_kernel` reader the sweep
    warns with): RAISES ValueError listing the offending slugs when any published Artefato lacks a
    matching `intent.kernel`. The publisher calls this to refuse a close with C3 debt."""
    bare = artefatos_without_kernel(log=log)
    if bare:
        raise ValueError(f"artefatos published without an intent kernel (C3): {bare}")


def dispatch_open(payload=None, log=LOG):
    """Append a `dispatch.open` event — the wake stamp (ADR-0016). Written by the entry-driver
    (tools/predispatch.py) after the mechanical pre-dispatch floor lands (sweep → briefing →
    recall brief). The payload carries the sweep yield (the read-side metric the Direction wants
    instrumented). The publisher refuses to publish without a stamp newer than the last
    `artefato.published` — no wake, no publish."""
    return append("dispatch.open", "dispatch", payload or {}, log=log)


def wake_fresh(log=LOG):
    """True when a `dispatch.open` is newer than the last `artefato.published` (ADR-0016) — one
    wake per publish; a stamp is consumed by the publish it precedes and cannot be reused.

    LEGACY GLOBAL form (S2 gate D1): compares global maxima, so concurrent dispatches spend
    each other's stamps (the race ADR-0016's Consequences accepted, now hardened). The canonical
    id-carrying publish path gates on the IDENTITY-HELD `wake_fresh_for` instead; this stays for
    id-less callers (the pre-S2 shape) only."""
    evs = read(types=["dispatch.open", "artefato.published"], log=log)
    last_open = max((e["seq"] for e in evs if e["type"] == "dispatch.open"), default=None)
    last_pub = max((e["seq"] for e in evs if e["type"] == "artefato.published"), default=None)
    return last_open is not None and (last_pub is None or last_open > last_pub)


def wake_fresh_for(dispatch_id, log=LOG):
    """The IDENTITY-HELD wake gate (S2 gate D1, refines ADR-0016 per E1: the id is consumed
    under the same lock, never a global boolean): True iff a `dispatch.open` whose payload
    MINTED this dispatch_id exists AND no `artefato.published` has consumed it yet. Two
    concurrent dispatches each hold their own stamp — neither publish spends the other's — and
    an id no wake ever minted can never publish (proof-bound ≠ provenance: the digest proves
    what was reviewed; THIS proves the wake that named it ran). A hollow/non-string id is never
    fresh (nothing to hold). Same payload tolerance as the other folds: a corrupt/non-dict
    payload simply never matches."""
    if not (isinstance(dispatch_id, str) and dispatch_id.strip()):
        return False
    evs = read(types=["dispatch.open", "artefato.published"], log=log)

    def _did(e):
        p = e.get("payload")
        return p.get("dispatch_id") if isinstance(p, dict) else None
    opened = any(e["type"] == "dispatch.open" and _did(e) == dispatch_id for e in evs)
    consumed = any(e["type"] == "artefato.published" and _did(e) == dispatch_id for e in evs)
    return opened and not consumed


ORIGINS = ("user_requested", "beat")


def dispatch_origin(dispatch_id, log=LOG):
    """Ticket 05 (hierarquia de ORIGEM): the origin the dispatch declared — `user_requested`
    (o pedido do usuário é o gradiente: exatamente onde está a cognição dele AGORA) or `beat`
    (exploração — indistinguível de ruído). Folds from the `dispatch.open` that minted this
    dispatch_id. DEFAULT `beat`: a legacy stamp (no origin key), an unknown/hollow id, or a
    junk value all fold to `beat` — a user_requested origin is never fabricated."""
    if not (isinstance(dispatch_id, str) and dispatch_id.strip()):
        return "beat"
    for e in read(types=["dispatch.open"], log=log):
        p = e.get("payload")
        if isinstance(p, dict) and p.get("dispatch_id") == dispatch_id:
            origin = p.get("origin")
            return origin if origin in ORIGINS else "beat"
    return "beat"





def source_signal(slug, ref, kind, similarity, log=LOG):
    """Append a `source.signal` event (ADR-0009, source-feedback hypothesis tier). The **score**
    lands in the log — the cosine of a cited snippet vs the Artefato body — keyed to the cited
    source (ref, kind: mundo|atividade) and the Artefato (slug). Only the score, never the vectors
    (no separate DB, no vector store); `fold_source_yield` aggregates per source, the grill consults it."""
    return append("source.signal", f"artefato:{slug}",
                  {"slug": slug, "ref": ref, "kind": kind, "similarity": similarity}, log=log)


def artefatos_without_kernel(log=LOG):
    """The C3 invariant as a pure fold: published Artefato slugs with no matching `intent.kernel`,
    in publish order. Edge work without a recorded intent is incomplete — this is what makes
    "no Artefato closes without a kernel" mechanically checkable (the sweep/grill consult it)."""
    evs = read(types=["artefato.published", "intent.kernel"], log=log)
    first_published = {}  # slug -> seq of its first publish (when debt opens)
    published = []        # slugs in publish order
    for e in evs:
        if e["type"] != "artefato.published":
            continue
        slug = (e.get("payload") or {}).get("slug")
        published.append(slug)
        first_published.setdefault(slug, e["seq"])
    # a slug clears debt only with a kernel whose intent is a non-empty stripped string AND whose
    # seq is at/after the slug's first publish — a blank/whitespace/None or stale pre-publish kernel
    # does NOT clear debt (Codex gate round-4 [high])
    kerneled = {(e.get("payload") or {}).get("slug")
                for e in evs
                if e["type"] == "intent.kernel"
                and _stripped_intent((e.get("payload") or {}).get("intent")) is not None
                and e["seq"] >= first_published.get((e.get("payload") or {}).get("slug"), float("inf"))}
    return [s for s in published if s not in kerneled]


CORPUS_TYPES = ["artefato.published", "intent.kernel"]


def fold_corpus(events):
    """Pure fold of `{artefato.published, intent.kernel}` events → the corpus (ADR-0009): the edge's
    own published steps, each paired with its *why*. In one pass, seq order: an `artefato.published`
    opens a corpus item keyed by slug (carrying its proposes/distills/cites, the authored typed
    lineage so a later replay can re-derive its DIRECTED edges, the proof-bound spec so the page
    projection is regenerable from the log, and published ts); an `intent.kernel`
    writes the `intent` onto its slug's item. An Artefato with no kernel folds with
    `intent=None` (a step whose why is not yet recorded — C3 debt). Returns items in publish order."""
    items = {}  # slug -> item
    for e in events:
        t, p = e.get("type"), e.get("payload", {}) or {}
        slug = p.get("slug")
        if slug is None:
            continue
        if t == "artefato.published":
            items[slug] = {"slug": slug, "intent": None, "proposes": p.get("proposes", []),
                           "distills": p.get("distills", []), "cites": p.get("cites", []),
                           "lineage": p.get("lineage", []),
                           "spec": p.get("spec"), "skill": p.get("skill"),
                           # ticket 05: origin rides the fold so read models can weigh
                           # user_requested ≫ beat; a legacy event folds to beat (honest default).
                           "origin": p.get("origin") if p.get("origin") in ORIGINS else "beat",
                           # B.1: o gate persistido acompanha o item — um reproject restaura as
                           # flat props; evento legado sem gate folda None (forward-only).
                           "gate": p.get("gate"),
                           # Ticket A: bears_on/para acompanham o item para o replay das arestas
                           # valenciadas/PARA; evento legado folda [] (forward-only, sem backfill).
                           "bears_on": p.get("bears_on") or [], "para": p.get("para") or [],
                           "reports_on": p.get("reports_on") or [],
                           # curadoria autoral: o alvo default acompanha o replay; evento
                           # pré-adoção folda None (forward-only, sem backfill).
                           "para_default": p.get("para_default"),
                           "ts": e.get("ts"), "latest_ts": e.get("ts")}
        elif t == "intent.kernel" and slug in items:
            # content rule: only a non-empty stripped intent becomes the why; a blank kernel renders
            # no open-bet. Ordering: `slug in items` already drops a stale pre-publish kernel.
            stripped = _stripped_intent(p.get("intent"))
            if stripped is not None:
                items[slug]["intent"] = stripped
            # `latest_ts` advances to the kernel event ts (Codex P3): the graph-recovery freshness
            # check compares against it, so a kernel ADDED LATER (legacy C3-debt repair) makes the
            # slug STALE relative to the graph and re-projects — the stale empty kernel is replaced.
            kts = e.get("ts")
            if kts and (items[slug].get("latest_ts") is None or kts > items[slug]["latest_ts"]):
                items[slug]["latest_ts"] = kts
    return list(items.values())


def artefatos_for_thread(thread, seq=None, ts=None, log=LOG):
    """The two-way view of provenance (ADR-0009): given a thread (a `distills` ref, e.g. cluster:…),
    the Artefato slugs that hang off it, in publish order — the reverse of artefato →distills→ thread.
    A pure fold of the corpus (no new event): thread maintenance reads it to know what a thread carries.
    Empty when no Artefato distills that thread (never a fabricated link). Cursor-aware, as corpus_at."""
    return [it["slug"] for it in corpus_at(seq=seq, ts=ts, log=log)
            if thread in (it.get("distills") or [])]


def corpus_at(seq=None, ts=None, log=LOG):
    """Fold `{artefato.published, intent.kernel}` events up to a cursor → the corpus, a list of items
    in publish order (ADR-0009). Pure: replaying to a past cursor reconstructs that past corpus —
    strategic versioning, the same property direction_at has. Returns [] when there is no corpus yet
    (an empty list is the sensible empty-case for a list-returning fold)."""
    return fold_corpus(read(types=CORPUS_TYPES, until_seq=seq, until_ts=ts, log=log))


ASSET_TYPES = ["artefato.asset"]
ASSET_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ASSET_KINDS = ("html", "js", "css", "data", "image")


def _validated_asset_slug(slug, field="asset_slug"):
    if not (isinstance(slug, str) and ASSET_SLUG_RE.fullmatch(slug)):
        raise ValueError(f"{field} must match {ASSET_SLUG_RE.pattern}, got {slug!r}")
    return slug


def publish_artefato_asset(asset_slug, *, path, kind, sha256, skill=None, parent_slug=None,
                           media_type=None, role=None, log=LOG):
    """Record a generated standalone artifact file as a first-class Artefato asset (#108).

    Normal close-published pages already have `artefato.published`. This event is for companion
    files such as content-addressed interactive HTML and JS assets that otherwise lived only as
    filesystem blobs. The bytes stay on disk; the log records their address, hash and optional
    parent Artefato so the graph can project a navigable node.
    """
    asset_slug = _validated_asset_slug(asset_slug)
    if parent_slug is not None:
        parent_slug = _validated_asset_slug(parent_slug, "parent_slug")
    if kind not in ASSET_KINDS:
        raise ValueError(f"artefato asset kind must be one of {ASSET_KINDS}, got {kind!r}")
    if not (isinstance(path, str) and path.strip()):
        raise ValueError("artefato asset path must be a non-blank string")
    if not (isinstance(sha256, str) and re.fullmatch(r"[0-9a-f]{64}", sha256)):
        raise ValueError("artefato asset sha256 must be a 64-character lowercase hex digest")
    payload = {
        "asset_slug": asset_slug,
        "path": path.strip(),
        "kind": kind,
        "sha256": sha256,
        "skill": skill,
        "parent_slug": parent_slug,
        "media_type": media_type,
        "role": role,
    }
    for e in read(types=ASSET_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if p.get("asset_slug") != asset_slug:
            continue
        if {k: p.get(k) for k in payload} == payload:
            return e
        raise ValueError(f"artefato asset {asset_slug!r} already exists with different metadata")
    return append("artefato.asset", f"artefato:{asset_slug}", payload, log=log)


def fold_artefato_assets(events):
    """Pure fold of `artefato.asset` → {asset_slug: asset metadata}. Last valid event wins."""
    out = {}
    for e in events:
        if e.get("type") != "artefato.asset":
            continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        slug = p.get("asset_slug")
        if not (isinstance(slug, str) and ASSET_SLUG_RE.fullmatch(slug)):
            continue
        out[slug] = {
            "asset_slug": slug,
            "path": p.get("path"),
            "kind": p.get("kind"),
            "sha256": p.get("sha256"),
            "skill": p.get("skill"),
            "parent_slug": p.get("parent_slug"),
            "media_type": p.get("media_type"),
            "role": p.get("role"),
            "ts": e.get("ts"),
            "seq": e.get("seq"),
        }
    return out


def artefato_assets_at(seq=None, ts=None, log=LOG):
    """Fold generated standalone Artefato assets up to a cursor. Empty → {}."""
    return fold_artefato_assets(read(types=ASSET_TYPES, until_seq=seq, until_ts=ts, log=log))


SESSION_TOPIC_TYPES = [
    "session.topic", "session.topics.snapshot", "session.topics.generation",
    "sessao.excluded",
]
SESSION_TOPIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _validated_session_topic_id(value, field):
    if not (isinstance(value, str) and SESSION_TOPIC_ID_RE.fullmatch(value)):
        raise ValueError(f"{field} must match {SESSION_TOPIC_ID_RE.pattern}, got {value!r}")
    return value


def _normalized_topic_fragment(fragment):
    if not isinstance(fragment, dict):
        raise ValueError("session.topic fragments must be dicts")
    snippet = fragment.get("snippet")
    text = fragment.get("text")
    body = snippet if isinstance(snippet, str) and snippet.strip() else text
    if not (isinstance(body, str) and body.strip()):
        raise ValueError("session.topic fragment needs a non-blank snippet/text")
    turn = fragment.get("turn")
    if isinstance(turn, bool) or not isinstance(turn, int) or turn <= 0:
        raise ValueError("session.topic fragment turn must be a positive integer")
    out = {
        "fragment_id": fragment.get("fragment_id"),
        "session": fragment.get("session"),
        "surface": fragment.get("surface"),
        "path": fragment.get("path"),
        "turn": turn,
        "snippet": " ".join(body.split())[:500],
    }
    fid_seed = json.dumps({k: out.get(k) for k in ("session", "surface", "path", "turn", "snippet")},
                          sort_keys=True, ensure_ascii=False)
    if not (isinstance(out["fragment_id"], str)
            and SESSION_TOPIC_ID_RE.fullmatch(out["fragment_id"])):
        out["fragment_id"] = "vf:" + hashlib.sha256(fid_seed.encode("utf-8")).hexdigest()[:24]
    return out


def _session_topic_hash(payload):
    canonical = {
        "session_id": payload.get("session_id"),
        "surface": payload.get("surface"),
        "path": payload.get("path"),
        "topic_id": payload.get("topic_id"),
        "title": payload.get("title"),
        "score": payload.get("score"),
        "keywords": payload.get("keywords") or [],
        "fragments": payload.get("fragments") or [],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def record_session_topic(session_id, topic_id, *, title, surface, path=None, score=0,
                         keywords=None, fragments=None, window_days=None, log=LOG):
    """Append/update the automatic session-topic index.

    This is the non-curated navigation layer: operator-authored session fragments are grouped into
    topic hypotheses. The event records the raw anchors and snippets so Direction can point at them
    without being their only durable home. Re-emitting identical content is idempotent; changed
    evidence appends a newer version, preserving the contradiction/history in the log.
    """
    session_id = _validated_session_topic_id(session_id, "session_id")
    topic_id = _validated_session_topic_id(topic_id, "topic_id")
    if not (isinstance(title, str) and title.strip()):
        raise ValueError("session.topic title must be non-blank")
    if surface not in ("claude", "codex", "grok"):
        raise ValueError("session.topic surface must be 'claude', 'codex', or 'grok'")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("session.topic score must be a finite number")
    if fragments is None:
        fragments = []
    if not isinstance(fragments, list) or not fragments:
        raise ValueError("session.topic needs at least one fragment")
    clean_fragments = []
    for f in fragments:
        if not isinstance(f, dict):
            raise ValueError("session.topic fragments must be dicts")
        clean = _normalized_topic_fragment({**f, "session": f.get("session") or session_id,
                                            "surface": f.get("surface") or surface})
        clean_fragments.append(clean)
    clean_keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    payload = {
        "session_id": session_id,
        "surface": surface,
        "path": str(path) if path else None,
        "topic_id": topic_id,
        "title": title.strip(),
        "score": score,
        "keywords": clean_keywords[:12],
        "fragments": clean_fragments,
        "window_days": window_days,
    }
    payload["content_hash"] = _session_topic_hash(payload)
    for e in read(types=SESSION_TOPIC_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if (p.get("session_id") == session_id and p.get("topic_id") == topic_id
                and p.get("content_hash") == payload["content_hash"]):
            return e
    return append("session.topic", f"session:{session_id}", payload, log=log)


def record_session_topics_snapshot(session_id, topic_ids, *, window_days=None, log=LOG):
    """Declare the current automatic topic set for one operator session.

    Topic events stay append-only. A later snapshot can retire a topic that no longer has valid
    voice fragments after provenance/scaffolding corrections, without deleting its audit trail.
    """
    session_id = _validated_session_topic_id(session_id, "session_id")
    if not isinstance(topic_ids, list):
        raise ValueError("session topic snapshot topic_ids must be a list")
    clean = sorted({_validated_session_topic_id(topic_id, "topic_id")
                    for topic_id in topic_ids})
    payload = {"session_id": session_id, "topic_ids": clean, "window_days": window_days}
    payload["content_hash"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    for event in reversed(read(types=["session.topics.snapshot"], log=log)):
        previous = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if previous.get("session_id") == session_id:
            if previous.get("content_hash") == payload["content_hash"]:
                return event
            break
    return append("session.topics.snapshot", f"session:{session_id}", payload, log=log)


def record_session_topics_generation(session_ids, *, window_days=None, log=LOG):
    """Declare the sessions in the latest authoritative recent-voice scan."""
    if not isinstance(session_ids, list):
        raise ValueError("session topic generation session_ids must be a list")
    clean = sorted({_validated_session_topic_id(session_id, "session_id")
                    for session_id in session_ids})
    payload = {"session_ids": clean, "window_days": window_days}
    payload["content_hash"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    previous_events = read(types=["session.topics.generation"], log=log)
    if previous_events:
        previous = previous_events[-1].get("payload")
        if isinstance(previous, dict) and previous.get("content_hash") == payload["content_hash"]:
            return previous_events[-1]
    return append("session.topics.generation", "session-topics", payload, log=log)


def fold_session_topics(events):
    """Pure fold of `session.topic` -> sessions/topics/fragments navigation index.

    Latest content hash wins per (session, topic). The fold keeps all three doors because agents
    enter memory from different questions: "what happened in this session?", "where is this topic
    alive?", or "which exact utterance grounded this?".
    """
    events = [event for event in events if isinstance(event, dict)]
    excluded_sessions = {
        payload["sessao_id"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") == "sessao.excluded"
        and isinstance(payload, dict)
        and isinstance(payload.get("sessao_id"), str)
    }
    snapshots = {}
    for event in events:
        if event.get("type") != "session.topics.snapshot":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        sid, topic_ids = payload.get("session_id"), payload.get("topic_ids")
        if (isinstance(sid, str) and isinstance(topic_ids, list)
                and all(isinstance(topic_id, str) for topic_id in topic_ids)):
            snapshots[sid] = (event.get("seq", -1), set(topic_ids))
    generations = [
        event for event in events
        if event.get("type") == "session.topics.generation"
        and isinstance(event.get("payload"), dict)
        and isinstance(event["payload"].get("session_ids"), list)
    ]
    generation = ((generations[-1].get("seq", -1),
                   set(generations[-1]["payload"]["session_ids"]))
                  if generations else None)
    latest = {}
    for e in events:
        if e.get("type") != "session.topic":
            continue
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        sid, tid = p.get("session_id"), p.get("topic_id")
        if not (isinstance(sid, str) and isinstance(tid, str)):
            continue
        if sid in excluded_sessions:
            continue
        if generation is not None and e.get("seq", -1) < generation[0] and sid not in generation[1]:
            continue
        snapshot = snapshots.get(sid)
        if (snapshot is not None and e.get("seq", -1) < snapshot[0]
                and tid not in snapshot[1]):
            continue
        latest[(sid, tid)] = (e, p)

    sessions_out, topics_out, fragments_out = {}, {}, {}
    for (sid, tid), (e, p) in latest.items():
        sess = sessions_out.setdefault(sid, {
            "session_id": sid,
            "surface": p.get("surface"),
            "path": p.get("path"),
            "topics": [],
            "fragments": [],
            "latest_ts": None,
        })
        if tid not in sess["topics"]:
            sess["topics"].append(tid)
        if e.get("ts") and (sess["latest_ts"] is None or e["ts"] > sess["latest_ts"]):
            sess["latest_ts"] = e["ts"]
        topic = topics_out.setdefault(tid, {
            "topic_id": tid,
            "title": p.get("title") or tid,
            "score": 0,
            "keywords": [],
            "sessions": [],
            "fragments": [],
            "latest_ts": None,
        })
        topic["score"] += p.get("score") if isinstance(p.get("score"), (int, float)) else 0
        if sid not in topic["sessions"]:
            topic["sessions"].append(sid)
        for kw in p.get("keywords") or []:
            if isinstance(kw, str) and kw and kw not in topic["keywords"]:
                topic["keywords"].append(kw)
        if e.get("ts") and (topic["latest_ts"] is None or e["ts"] > topic["latest_ts"]):
            topic["latest_ts"] = e["ts"]
        for f in p.get("fragments") or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("fragment_id")
            if not isinstance(fid, str):
                continue
            frag = {
                "fragment_id": fid,
                "session_id": sid,
                "surface": f.get("surface") or p.get("surface"),
                "path": f.get("path") or p.get("path"),
                "turn": f.get("turn"),
                "snippet": f.get("snippet"),
                "topic_id": tid,
                "topic_title": topic["title"],
                "ts": e.get("ts"),
            }
            fragments_out[fid] = frag
            if fid not in sess["fragments"]:
                sess["fragments"].append(fid)
            if fid not in topic["fragments"]:
                topic["fragments"].append(fid)
    for sess in sessions_out.values():
        sess["topics"].sort()
        sess["fragments"].sort()
    for topic in topics_out.values():
        topic["sessions"].sort()
        topic["fragments"].sort()
        topic["keywords"] = topic["keywords"][:20]
    return {"sessions": sessions_out, "topics": topics_out, "fragments": fragments_out}


def session_topics_at(seq=None, ts=None, log=LOG):
    """Fold the automatic Voz/session topic index up to a cursor. Empty -> three empty maps."""
    return fold_session_topics(read(types=SESSION_TOPIC_TYPES, until_seq=seq, until_ts=ts, log=log))


# ---------------------------------------------------------------------------
# Lentes de Atividade/Direction v2 — S1: atividade events + fold.
# ---------------------------------------------------------------------------

ATIVIDADE_TYPES = [
    "atividade.opened", "atividade.touched", "atividade.closed",
    "atividade.reopened", "atividade.bears_on", "sessao.racionalizada", "sessao.excluded",
]
RUN_TYPES = ["run.opened", "run.closed", "instrumento.falhou"]
ARCO_TYPES = ["arco.opened", "arco.closed", "arco.moved"]
FATO_TYPES = ["fato.observed", "instrumento.falhou"]
MARCO_TYPES = ["marco.set"]
CLAIM_TYPES = ["hypothesis.declared", "hypothesis.superseded",
               "claim.hypothesized", "claim.promoted"]
CONTEST_TYPES = ["contest.raised", "contest.adjudicated"]
WAYFIND_TYPES = [
    "map.opened", "map.state", "ticket.opened", "ticket.closed", "ticket.declined",
    "ticket.reopened", "ticket.deps_changed", "move.proposed", "move.ratified",
    "move.declined",
    "sessao.racionalizada", "sessao.excluded",
]
_MAP_STATES = ("ativado", "pausado", "arquivado")
_MOVE_EFFECT_TYPES = {
    "ticket.close": "ticket.closed", "ticket.open": "ticket.opened",
    "ticket.reopen": "ticket.reopened", "atividade.close": "atividade.closed",
    "atividade.reopen": "atividade.reopened", "map.archive": "map.state",
    "arco.move": "arco.moved", "contest": "contest.raised",
    "falsificador_aconteceu": "contest.raised",
}
_OPERACAO_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TIPO_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_LENS_TIERS = ("asserted", "llm_judged")
_ACTIVITY_AUTHORS = ("operador", "grill", "racionalizador")
_ACTIVITY_STATES = ("cumprida", "abandonada", "superada_por")
_BEARING_VALENCES = ("supports", "refutes", "qualifies", "inconclusive", "no_bearing")


def _operator_session_overlay(events):
    """Hide LLM derivations from sessions later classified as non-operator provenance.

    ``sessao.excluded`` is an append-only correction: raw transcripts and audit events remain in
    truth, while report-facing folds stop attributing delegated execution to the operator. An
    asserted activity gesture pins that grain, because the operator explicitly adopted it later.
    """
    events = [event for event in events if isinstance(event, dict)]
    excluded_sessions = {
        payload["sessao_id"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") == "sessao.excluded"
        and isinstance(payload, dict)
        and isinstance(payload.get("sessao_id"), str)
        and payload["sessao_id"]
    }
    if not excluded_sessions:
        return events
    excluded_rationalizations = {
        payload["rationalization_id"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") == "sessao.racionalizada"
        and isinstance(payload, dict)
        and payload.get("sessao_id") in excluded_sessions
        and isinstance(payload.get("rationalization_id"), str)
        and payload["rationalization_id"]
    }
    excluded_activity_grains = {
        payload["ulid"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") == "atividade.opened"
        and isinstance(payload, dict)
        and (payload.get("origem_sessao") in excluded_sessions
             or payload.get("rationalization_id") in excluded_rationalizations)
        and isinstance(payload.get("ulid"), str)
    }
    pinned = {
        payload["ref"]
        for event in events
        for payload in [event.get("payload")]
        if event.get("type") in {
            "atividade.touched", "atividade.closed", "atividade.reopened",
            "atividade.bears_on",
        }
        and isinstance(payload, dict)
        and payload.get("tier") == "asserted"
        and payload.get("ref") in excluded_activity_grains
    }
    current = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = event.get("type")
        if event_type == "sessao.excluded":
            current.append(event)
            continue
        if event_type == "sessao.racionalizada" and payload.get("sessao_id") in excluded_sessions:
            continue
        belongs_to_excluded = (
            payload.get("origem_sessao") in excluded_sessions
            or payload.get("rationalization_id") in excluded_rationalizations
            or (event_type == "atividade.touched"
                and payload.get("sessao") in excluded_sessions
                and payload.get("tier") != "asserted")
        )
        if belongs_to_excluded:
            if (event_type == "atividade.opened"
                    and payload.get("ulid") in pinned):
                current.append(event)
            continue
        current.append(event)
    return current


class AmbiguousRef(ValueError):
    """A short human ref has no operation bind, so resolving it would be a guess."""


def _lens_nonblank(value, field):
    if not (isinstance(value, str) and value.strip()):
        raise ValueError(f"`{field}` must be a non-blank string")
    return value.strip()


def _lens_choice(value, field, choices):
    if value not in choices:
        raise ValueError(f"`{field}` must be one of {choices}")
    return value


def _lens_operacao(value):
    value = _lens_nonblank(value, "operacao")
    if not _OPERACAO_RE.fullmatch(value):
        raise ValueError("`operacao` must match ^[a-z0-9][a-z0-9-]*$")
    return value


def _next_lens_num(events, operacao, prefix):
    highest = 0
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        num = payload.get("num")
        if payload.get("operacao") != operacao or not isinstance(num, str):
            continue
        match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", num)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def open_atividade(*, operacao, finalidade, eval=None, arco=None, tipo_ref=None,
                   tier, author, origem_sessao=None, derivation_key=None,
                   dispatch_id=None, log=LOG):
    """Open one purpose-bearing activity; allocate its human num under the append flock."""
    operacao = _lens_operacao(operacao)
    finalidade = _lens_nonblank(finalidade, "finalidade")
    _lens_choice(tier, "tier", _LENS_TIERS)
    _lens_choice(author, "author", _ACTIVITY_AUTHORS)
    if dispatch_id is not None:
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if eval is not None:
        if not isinstance(eval, dict):
            raise ValueError("`eval` must be a dict containing a non-blank `regua`")
        normalized_eval = dict(eval)
        normalized_eval["regua"] = _lens_nonblank(eval.get("regua"), "eval.regua")
        eval = normalized_eval
    if tipo_ref is not None:
        tipo_ref = _lens_nonblank(tipo_ref, "tipo_ref")
        if not _TIPO_REF_RE.fullmatch(tipo_ref):
            raise ValueError("`tipo_ref` must match ^[a-z0-9][a-z0-9-]*$")
    if tier == "llm_judged":
        origem_sessao = _lens_nonblank(origem_sessao, "origem_sessao")
        derivation_key = _lens_nonblank(derivation_key, "derivation_key")
        if author != "racionalizador":
            raise ValueError("llm_judged atividade must have author='racionalizador'")
    elif origem_sessao is not None or derivation_key is not None:
        raise ValueError("asserted atividade cannot carry origem_sessao/derivation_key")
    elif author not in ("operador", "grill"):
        raise ValueError("asserted atividade must have author operador or grill")
    if arco is not None:
        arco = _resolve_lens_ref(
            arco, read(log=log), operacao=operacao, kinds={"arco"})["ulid"]
    ulid = _ulid()
    payload = {
        "ulid": ulid, "num": None, "operacao": operacao, "finalidade": finalidade,
        "eval": eval, "arco": arco, "tipo_ref": tipo_ref, "tier": tier, "author": author,
        "origem_sessao": origem_sessao, "derivation_key": derivation_key,
        "dispatch_id": dispatch_id,
    }

    def _allocate_num():
        payload["num"] = _next_lens_num(read(log=log), operacao, "atv")

    return append_batch(
        [("atividade.opened", f"atividade:{ulid}", payload)],
        log=log, precondition=_allocate_num,
    )[0]


def _lens_entities(events):
    """Index addressable grains without trusting malformed events (fold/read side is dark)."""
    entities = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type in ("hypothesis.declared", "claim.hypothesized"):
            if event_type == "claim.hypothesized" and not _foldable_hypothesized_claim(payload):
                continue
            ulid = payload.get("ulid")
            if isinstance(ulid, str):
                entities.append({"kind": "hypothesis" if event_type.startswith("hypothesis")
                                 else "claim", "ulid": ulid, "num": None,
                                 "operacao": None, "full": None})
            continue
        if event_type == "fato.observed":
            if not _foldable_fact_observed(payload):
                continue
            ulid, num, operacao = (payload.get("ulid"), payload.get("num"),
                                   payload.get("operacao"))
            if all(isinstance(value, str) for value in (ulid, num, operacao)):
                entities.append({"kind": "fato", "ulid": ulid, "num": num,
                                 "operacao": operacao, "full": f"{operacao}/{num}"})
            continue
        if not (isinstance(event_type, str) and event_type.endswith(".opened")):
            continue
        kind = event_type.split(".", 1)[0]
        if ((kind == "atividade" and not _foldable_activity_open(payload))
                or (kind == "run" and not _foldable_run_open(payload))
                or (kind == "arco" and not _foldable_arco_open(payload))
                or (kind == "map" and not _foldable_map_open(payload))):
            continue
        ulid, num, operacao = payload.get("ulid"), payload.get("num"), payload.get("operacao")
        if not (isinstance(ulid, str) and isinstance(num, str) and isinstance(operacao, str)):
            continue
        entities.append({"kind": kind, "ulid": ulid, "num": num,
                         "operacao": operacao, "full": f"{operacao}/{num}"})
    # Tickets inherit their operation namespace from their map; ticket.opened intentionally
    # stores only `map`, not a redundant operation field.
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "ticket.opened":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if not _foldable_ticket_open(payload):
            continue
        ulid, num, map_ref = payload.get("ulid"), payload.get("num"), payload.get("map")
        if not (isinstance(ulid, str) and isinstance(num, str) and isinstance(map_ref, str)):
            continue
        parent = next(
            (entity for entity in entities
             if entity["kind"] == "map" and map_ref in (entity["ulid"], entity["full"])),
            None,
        )
        if parent is not None and not any(entity["ulid"] == ulid for entity in entities):
            entities.append({"kind": "ticket", "ulid": ulid, "num": num,
                             "operacao": parent["operacao"],
                             "full": f"{parent['operacao']}/{num}"})
    return entities


def _resolve_lens_ref(ref, events, *, operacao=None, kinds=None):
    ref = _lens_nonblank(ref, "ref")
    entities = _lens_entities(events)
    if kinds is not None:
        entities = [entity for entity in entities if entity["kind"] in kinds]
    matches = [entity for entity in entities if ref in (entity["ulid"], entity["full"])]
    if not matches and re.fullmatch(r"(?:atv|run|arc|map|tkt|fat)-\d+", ref):
        if operacao is None:
            raise AmbiguousRef(
                f"short ref {ref!r} requires an explicit `operacao` bind; use <operacao>/{ref}")
        bound = f"{_lens_operacao(operacao)}/{ref}"
        matches = [entity for entity in entities if entity["full"] == bound]
    if len(matches) != 1:
        expected = "" if kinds is None else f" of kind {sorted(kinds)}"
        raise ValueError(f"ref {ref!r} does not resolve to exactly one existing grain{expected}")
    return matches[0]


def _activity_expectation(expects, target, log):
    if expects is None:
        return
    if not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict or None")
    current = atividades_at(log=log).get(target["full"])
    if current is None:
        raise ValueError(f"stale activity {target['full']!r}: no current state")
    mismatches = {}
    for field, expected in expects.items():
        actual = current.get(field)
        matches = (actual in expected if isinstance(expected, (list, tuple, set))
                   else actual == expected)
        if not matches:
            mismatches[field] = {"expected": expected, "actual": actual}
    if mismatches:
        raise ValueError(
            f"stale activity {target['full']!r}: current state mismatches {mismatches}")


def touch_atividade(*, ref, sessao, novo=None, files=None, spans=None, tier,
                    operacao=None, dispatch_id=None, expects=None, log=LOG):
    """Record one session×activity touch; refs are canonicalized to the activity ULID."""
    sessao = _lens_nonblank(sessao, "sessao")
    _lens_choice(tier, "tier", _LENS_TIERS)
    if novo is not None:
        novo = _lens_nonblank(novo, "novo")
    if files is None:
        files = []
    if not isinstance(files, list) or not all(isinstance(path, str) and path.strip() for path in files):
        raise ValueError("`files` must be a list of non-blank paths")
    files = [path.strip() for path in files]
    if spans is None:
        spans = []
    if not isinstance(spans, list):
        raise ValueError("`spans` must be a list of transcript span dicts")
    normalized_spans = []
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("each `spans` item must be {sessao, ini, fim}")
        span_session = _lens_nonblank(span.get("sessao"), "spans.sessao")
        start, end = span.get("ini"), span.get("fim")
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, int) or not isinstance(end, int)
                or start < 0 or end < start):
            raise ValueError("each transcript span needs integer 0 <= ini <= fim")
        normalized_spans.append({"sessao": span_session, "ini": start, "fim": end})
    spans = normalized_spans
    if dispatch_id is not None:
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if expects is not None and not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict or None")
    events = read(log=log)
    target = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"atividade"})
    payload = {"ref": target["ulid"], "sessao": sessao, "novo": novo,
               "files": files, "spans": spans, "tier": tier,
               "operacao": target["operacao"], "dispatch_id": dispatch_id}

    def _one_touch_per_session_activity():
        _activity_expectation(expects, target, log)
        for event in read(types=["atividade.touched"], log=log):
            previous = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if previous.get("ref") == target["ulid"] and previous.get("sessao") == sessao:
                raise ValueError(
                    f"one touch per session×activity: {sessao!r} already touched {target['full']}")

    return append_batch(
        [("atividade.touched", f"atividade:{target['ulid']}", payload)],
        log=log, precondition=_one_touch_per_session_activity,
    )[0]


def _activity_curatorial_fields(*, tier, author, rationale, dispatch_id, log):
    _lens_choice(tier, "tier", _LENS_TIERS)
    _lens_choice(author, "author", _ACTIVITY_AUTHORS)
    if tier == "llm_judged":
        raise ValueError("racionalizador never writes atividade.closed/reopened directly")
    if author not in ("operador", "grill"):
        raise ValueError("asserted atividade.closed/reopened author must be operador or grill")
    if rationale is not None:
        rationale = _lens_nonblank(rationale, "rationale")
    if dispatch_id is not None:
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if _is_canonical_log(log):
        rationale = _lens_nonblank(rationale, "rationale")
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    return rationale, dispatch_id


def close_atividade(*, ref, estado, julgamento, superada_por=None, tier, author,
                    rationale=None, dispatch_id=None, operacao=None, expects=None, log=LOG):
    """Append a dated, non-destructive activity closure/amendment."""
    _lens_choice(estado, "estado", _ACTIVITY_STATES)
    julgamento = _lens_nonblank(julgamento, "julgamento")
    rationale, dispatch_id = _activity_curatorial_fields(
        tier=tier, author=author, rationale=rationale, dispatch_id=dispatch_id, log=log)
    events = read(log=log)
    target = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"atividade"})
    successor = None
    if estado == "superada_por":
        if superada_por is None:
            raise ValueError("estado='superada_por' requires a valid `superada_por` ref")
        successor = _resolve_lens_ref(
            superada_por, events, operacao=operacao, kinds={"atividade"})["ulid"]
        if successor == target["ulid"]:
            raise ValueError("`superada_por` must refer to another activity")
    elif superada_por is not None:
        raise ValueError("`superada_por` is only valid when estado='superada_por'")
    payload = {
        "ref": target["ulid"], "estado": estado, "julgamento": julgamento,
        "superada_por": successor, "tier": tier, "author": author,
        "rationale": rationale, "dispatch_id": dispatch_id,
        "operacao": target["operacao"],
    }
    if expects is not None and not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict or None")

    def _expected_state_still_holds():
        _activity_expectation(expects, target, log)

    return append_batch(
        [("atividade.closed", f"atividade:{target['ulid']}", payload)],
        log=log, precondition=_expected_state_still_holds,
    )[0]


def reopen_atividade(*, ref, motivo, evidencia=None, tier, author, rationale=None,
                     dispatch_id=None, operacao=None, expects=None, log=LOG):
    """Explicitly reopen a terminal activity; the state check is serialized with the write."""
    motivo = _lens_nonblank(motivo, "motivo")
    rationale, dispatch_id = _activity_curatorial_fields(
        tier=tier, author=author, rationale=rationale, dispatch_id=dispatch_id, log=log)
    target = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao, kinds={"atividade"})
    payload = {
        "ref": target["ulid"], "motivo": motivo, "evidencia": evidencia,
        "author": author, "tier": tier, "rationale": rationale,
        "dispatch_id": dispatch_id, "operacao": target["operacao"],
    }
    if expects is not None and not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict or None")

    def _must_be_closed():
        _activity_expectation(expects, target, log)
        current = atividades_at(log=log).get(target["full"])
        if current is None:
            raise ValueError(f"activity {target['full']!r} no longer resolves")
        if current.get("estado") in ("aberta", "reaberta"):
            raise ValueError(f"cannot reopen activity {target['full']!r}: it is already aberta")

    return append_batch(
        [("atividade.reopened", f"atividade:{target['ulid']}", payload)],
        log=log, precondition=_must_be_closed,
    )[0]


def bears_on(*, ref, alvo, valencia, evidencia=None, tier, operacao=None,
             dispatch_id=None, expects=None, log=LOG):
    """Link an activity to an existing grain with one vocabulary-wide valence."""
    _lens_choice(valencia, "valencia", _BEARING_VALENCES)
    _lens_choice(tier, "tier", _LENS_TIERS)
    if dispatch_id is not None:
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if expects is not None and not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict or None")
    events = read(log=log)
    source = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"atividade"})
    target = _resolve_lens_ref(
        alvo, events, operacao=operacao,
        kinds={"atividade", "arco", "ticket", "claim", "hypothesis"},
    )
    payload = {"ref": source["ulid"], "alvo": target["ulid"],
               "valencia": valencia, "evidencia": evidencia, "tier": tier,
               "dispatch_id": dispatch_id, "operacao": source["operacao"]}

    def _source_expectation_still_holds():
        _activity_expectation(expects, source, log)

    return append_batch(
        [("atividade.bears_on", f"atividade:{source['ulid']}", payload)],
        log=log, precondition=_source_expectation_still_holds,
    )[0]


def _lens_derivation(tier, derivation_key):
    _lens_choice(tier, "tier", _LENS_TIERS)
    if tier == "llm_judged":
        return _lens_nonblank(derivation_key, "derivation_key")
    if derivation_key is not None:
        raise ValueError("asserted grain cannot carry `derivation_key`")
    return None


def open_run(*, atividades, config, eval=None, leva=None, nao_mede=None, tier,
             derivation_key=None, operacao=None, prediction_hash=None, log=LOG):
    """Pre-register a replayable N:M run; prediction_hash is substrate-computed."""
    if prediction_hash is not None:
        raise ValueError("caller must not supply `prediction_hash`; the run pen computes it")
    if not isinstance(atividades, list) or not atividades:
        raise ValueError("`atividades` must be a non-empty list of existing activity refs")
    if not isinstance(config, dict) or not config:
        raise ValueError("`config` must be a non-empty replayable dict")
    if not isinstance(eval, dict):
        raise ValueError("`eval` must pre-register non-blank metric and predicao")
    metric = _lens_nonblank(eval.get("metric"), "eval.metric")
    prediction = _lens_nonblank(eval.get("predicao"), "eval.predicao")
    normalized_eval = {"metric": metric, "predicao": prediction}
    canonical = json.dumps(normalized_eval, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    prediction_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    derivation_key = _lens_derivation(tier, derivation_key)
    events = read(log=log)
    resolved_activities = [
        _resolve_lens_ref(ref, events, operacao=operacao, kinds={"atividade"})
        for ref in atividades
    ]
    operations = {activity["operacao"] for activity in resolved_activities}
    if len(operations) != 1:
        raise ValueError("all `atividades` in one run must belong to the same operacao")
    operation = next(iter(operations))
    if operacao is not None and _lens_operacao(operacao) != operation:
        raise ValueError("`operacao` bind does not match the run's activities")
    if nao_mede is None:
        nao_mede = []
    if not isinstance(nao_mede, list):
        raise ValueError("`nao_mede` must be a list of resolvable grain refs")
    resolved_non_measurements = []
    for ref in nao_mede:
        target = _resolve_lens_ref(
            ref, events, operacao=operation,
            kinds={"atividade", "arco", "ticket", "claim", "hypothesis"},
        )["ulid"]
        if target not in resolved_non_measurements:
            resolved_non_measurements.append(target)
    if leva is not None:
        leva = _lens_nonblank(leva, "leva")
    ulid = _ulid()
    payload = {
        "ulid": ulid, "num": None, "operacao": operation,
        "atividades": [activity["ulid"] for activity in resolved_activities],
        "leva": leva, "config": dict(config), "eval": normalized_eval,
        "prediction_hash": prediction_hash, "nao_mede": resolved_non_measurements,
        "tier": tier, "derivation_key": derivation_key,
    }

    def _allocate_num():
        payload["num"] = _next_lens_num(read(log=log), operation, "run")

    return append_batch(
        [("run.opened", f"run:{ulid}", payload)], log=log, precondition=_allocate_num,
    )[0]


def close_run(*, ref, resultado, bears_on=None, tier, operacao=None, log=LOG):
    """Close/amend a run, refusing claims over capabilities pre-registered as not measured."""
    resultado = _lens_nonblank(resultado, "resultado")
    _lens_choice(tier, "tier", _LENS_TIERS)
    events = read(log=log)
    target = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"run"})
    current = runs_at(log=log).get(target["full"])
    if current is None:
        raise ValueError(f"run {target['full']!r} does not fold from its opening event")
    if bears_on is None:
        bears_on = []
    if not isinstance(bears_on, list):
        raise ValueError("`bears_on` must be a list of {alvo, valencia}")
    normalized_bearings = []
    for bearing in bears_on:
        if not isinstance(bearing, dict):
            raise ValueError("each `bears_on` item must be {alvo, valencia}")
        valence = _lens_choice(bearing.get("valencia"), "bears_on.valencia", _BEARING_VALENCES)
        resolved = _resolve_lens_ref(
            bearing.get("alvo"), events, operacao=target["operacao"],
            kinds={"atividade", "arco", "ticket", "claim", "hypothesis"},
        )["ulid"]
        if resolved in current.get("nao_mede", []) and valence != "no_bearing":
            raise ValueError(
                f"run {target['full']} declared alvo {resolved!r} in `nao_mede`; "
                "only valencia='no_bearing' is valid")
        normalized_bearings.append({"alvo": resolved, "valencia": valence})
    payload = {"ref": target["ulid"], "resultado": resultado,
               "bears_on": normalized_bearings, "tier": tier}
    return append("run.closed", f"run:{target['ulid']}", payload, log=log)


def observe_fato(*, atividade, body, run=None, leva=None, endereco=None, medida=None,
                 tier, operacao=None, log=LOG):
    """Record an addressed raw fact; judgment remains on its aggregate, never this frame."""
    body = _lens_nonblank(body, "body")
    _lens_choice(tier, "tier", _LENS_TIERS)
    events = read(log=log)
    parent = _resolve_lens_ref(
        atividade, events, operacao=operacao, kinds={"atividade"})
    operation = parent["operacao"]
    run_ulid = None
    if run is not None:
        resolved_run = _resolve_lens_ref(run, events, operacao=operation, kinds={"run"})
        folded_run = runs_at(log=log).get(resolved_run["full"])
        if folded_run is None or parent["ulid"] not in folded_run.get("atividades", []):
            raise ValueError("`run` must be an existing run joined to `atividade`")
        run_ulid = resolved_run["ulid"]
    if leva is not None:
        leva = _lens_nonblank(leva, "leva")
    if medida is not None:
        if not isinstance(medida, dict) or "valor" not in medida:
            raise ValueError("`medida` must be {valor, como} when present")
        medida = dict(medida)
        medida["como"] = _lens_nonblank(medida.get("como"), "medida.como")
    ulid = _ulid()
    payload = {
        "ulid": ulid, "num": None, "operacao": operation,
        "atividade": parent["ulid"], "run": run_ulid, "leva": leva,
        "body": body, "endereco": endereco, "medida": medida, "tier": tier,
    }

    def _allocate_num():
        payload["num"] = _next_lens_num(read(log=log), operation, "fat")

    return append_batch(
        [("fato.observed", f"fato:{ulid}", payload)], log=log, precondition=_allocate_num,
    )[0]


def instrument_failure(*, instrumento, leva, detalhe, log=LOG):
    """Record a first-class instrument failure joined to evidence by its batch identifier."""
    instrumento = _lens_nonblank(instrumento, "instrumento")
    leva = _lens_nonblank(leva, "leva")
    detalhe = _lens_nonblank(detalhe, "detalhe")
    payload = {"instrumento": instrumento, "leva": leva, "detalhe": detalhe}
    return append("instrumento.falhou", f"leva:{leva}", payload, log=log)


def open_arco(*, operacao, nome, tier, author, log=LOG):
    """Open a named super-activity with its own operation-scoped human identity."""
    operacao = _lens_operacao(operacao)
    nome = _lens_nonblank(nome, "nome")
    _lens_choice(tier, "tier", _LENS_TIERS)
    _lens_choice(author, "author", _ACTIVITY_AUTHORS)
    if ((tier == "asserted" and author not in ("operador", "grill"))
            or (tier == "llm_judged" and author != "racionalizador")):
        raise ValueError("arco author must match its asserted/llm_judged tier")
    ulid = _ulid()
    payload = {"ulid": ulid, "num": None, "operacao": operacao,
               "nome": nome, "tier": tier, "author": author}

    def _allocate_num():
        payload["num"] = _next_lens_num(read(log=log), operacao, "arc")

    return append_batch(
        [("arco.opened", f"arco:{ulid}", payload)], log=log, precondition=_allocate_num,
    )[0]


def _optional_canonical_rationale(rationale, dispatch_id, log):
    if rationale is not None:
        rationale = _lens_nonblank(rationale, "rationale")
    if dispatch_id is not None:
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if _is_canonical_log(log):
        rationale = _lens_nonblank(rationale, "rationale")
        dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    return rationale, dispatch_id


def close_arco(*, ref, valencia, julgamento, tier, rationale=None,
               dispatch_id=None, operacao=None, log=LOG):
    """Append an amendable verdict owned by the arc, not by any member activity."""
    _lens_choice(valencia, "valencia", _BEARING_VALENCES)
    julgamento = _lens_nonblank(julgamento, "julgamento")
    _lens_choice(tier, "tier", _LENS_TIERS)
    rationale, dispatch_id = _optional_canonical_rationale(rationale, dispatch_id, log)
    target = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao, kinds={"arco"})
    payload = {"ref": target["ulid"], "valencia": valencia,
               "julgamento": julgamento, "tier": tier,
               "rationale": rationale, "dispatch_id": dispatch_id}
    return append("arco.closed", f"arco:{target['ulid']}", payload, log=log)


def move_arco(*, ref, arco_novo, tier, author, rationale=None,
              dispatch_id=None, operacao=None, log=LOG):
    """Curatorially move an activity to another existing arc in the same operation."""
    rationale, dispatch_id = _activity_curatorial_fields(
        tier=tier, author=author, rationale=rationale, dispatch_id=dispatch_id, log=log)
    events = read(log=log)
    activity = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"atividade"})
    arc = _resolve_lens_ref(
        arco_novo, events, operacao=activity["operacao"], kinds={"arco"})
    if arc["operacao"] != activity["operacao"]:
        raise ValueError("activity and `arco_novo` must belong to the same operacao")
    payload = {"ref": activity["ulid"], "arco_novo": arc["ulid"],
               "rationale": rationale, "dispatch_id": dispatch_id,
               "tier": tier, "author": author}
    return append("arco.moved", f"atividade:{activity['ulid']}", payload, log=log)


def set_marco(*, operacao, ref, rationale, dispatch_id, author, nota=None, log=LOG):
    """Set the curated stable landmark for an operation; this never stores a frontier."""
    operacao = _lens_operacao(operacao)
    rationale = _lens_nonblank(rationale, "rationale")
    dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if author not in ("operador", "grill"):
        raise ValueError("`author` for marco.set must be operador or grill")
    if nota is not None:
        nota = _lens_nonblank(nota, "nota")
    target = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao,
        kinds={"atividade", "run", "arco", "fato"},
    )
    if target["operacao"] != operacao:
        raise ValueError("marco target must belong to `operacao`")
    payload = {"operacao": operacao, "ref": target["ulid"], "nota": nota,
               "rationale": rationale, "dispatch_id": dispatch_id, "author": author}
    return append("marco.set", f"operacao:{operacao}", payload, log=log)


def _wayfinder_curation(rationale, dispatch_id, author, *, tier="asserted"):
    rationale = _lens_nonblank(rationale, "rationale")
    dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    _lens_choice(tier, "tier", _LENS_TIERS)
    author = _lens_nonblank(author, "author")
    # Operator 2026-07-13: surface vocabulary is mentor (not grill). Accept both during rename.
    if ((tier == "asserted" and author not in ("operador", "grill", "mentor"))
            or (tier == "llm_judged" and author not in ("edge", "racionalizador"))):
        raise ValueError("wayfinder author must match its asserted/llm_judged tier")
    return rationale, dispatch_id, author


def _resolved_thread(thread, resolve_thread_fn):
    """Resolve a thread label to the persisted {uuid, display} at the pen's edge (A34).

    Only a label string resolves via the injected adapter (exactly one live candidate). A raw
    caller-supplied {uuid, display} is never trusted. Graphiti remains outside this module (A21).
    """
    if thread is None:
        return None
    if not isinstance(thread, str):
        raise ValueError("`thread` must be a label string resolved at the pen boundary")
    if not callable(resolve_thread_fn):
        raise ValueError("`thread` label needs a `resolve_thread_fn` to resolve to a uuid")
    raw_candidates = resolve_thread_fn(_lens_nonblank(thread, "thread"))
    if inspect.isawaitable(raw_candidates):
        close = getattr(raw_candidates, "close", None)
        if callable(close):
            close()
        raise ValueError("thread resolver must be synchronous and return a list")
    if not isinstance(raw_candidates, list):
        raise ValueError("thread resolver must return a list of candidates")
    candidates = raw_candidates
    if len(candidates) != 1:
        raise ValueError(
            f"`thread` label must resolve to exactly one live entity, got {len(candidates)}")
    resolved = candidates[0]
    if not isinstance(resolved, dict):
        raise ValueError("resolved `thread` must be {uuid, display}")
    return {"uuid": _lens_nonblank(resolved.get("uuid"), "thread.uuid"),
            "display": _lens_nonblank(resolved.get("display"), "thread.display")}


def open_map(*, operacao, titulo, rationale, dispatch_id, author, thread=None,
             resolve_thread_fn=None, tier="asserted", log=LOG):
    """Open an operation-scoped map; map identity is allocated under the eventlog flock."""
    operacao = _lens_operacao(operacao)
    titulo = _lens_nonblank(titulo, "titulo")
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier=tier)
    thread = _resolved_thread(thread, resolve_thread_fn)
    ulid = _ulid()
    payload = {"ulid": ulid, "num": None, "operacao": operacao, "titulo": titulo,
               "rationale": rationale, "thread": thread, "tier": tier,
               "author": author, "dispatch_id": dispatch_id}

    def _allocate_num():
        payload["num"] = _next_lens_num(read(log=log), operacao, "map")

    return append_batch(
        [("map.opened", f"map:{ulid}", payload)], log=log, precondition=_allocate_num,
    )[0]


def set_map_state(*, ref, estado, rationale, dispatch_id, author, operacao=None, log=LOG):
    """Set one map's asserted lifecycle state; ticket state remains untouched."""
    _lens_choice(estado, "estado", _MAP_STATES)
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    target = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao, kinds={"map"})
    payload = {"ref": target["ulid"], "estado": estado, "rationale": rationale,
               "author": author, "dispatch_id": dispatch_id}
    return append("map.state", f"map:{target['ulid']}", payload, log=log)


def _next_ticket_num(events, operacao):
    """Allocate monotonically across materialized tickets and move-held reservations.

    A ticket.open move owns its number from proposal time. Ratification duplicates that same
    embedded effect and decline leaves the proposal in history, so scanning every move state (and
    resolving a decline back to its proposal) makes the identity permanently non-reassignable.
    """
    highest = 0
    for entity in _lens_entities(events):
        if entity["kind"] != "ticket" or entity["operacao"] != operacao:
            continue
        match = re.fullmatch(r"tkt-(\d+)", entity["num"])
        if match:
            highest = max(highest, int(match.group(1)))
    map_operations = {
        key: entity["operacao"]
        for entity in _lens_entities(events) if entity["kind"] == "map"
        for key in (entity["ulid"], entity["full"])
    }
    proposals = {
        payload.get("ulid"): payload
        for event in events if isinstance(event, dict) and event.get("type") == "move.proposed"
        for payload in [event.get("payload") if isinstance(event.get("payload"), dict) else {}]
        if isinstance(payload.get("ulid"), str)
    }
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in (
                "move.proposed", "move.ratified", "move.declined"):
            continue
        move_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (event.get("type") == "move.declined"
                and not isinstance(move_payload.get("effect"), dict)):
            move_payload = proposals.get(move_payload.get("ref"), {})
        effect = move_payload.get("effect") if isinstance(move_payload, dict) else None
        if not isinstance(effect, dict) or effect.get("event_type") != "ticket.opened":
            continue
        ticket_payload = effect.get("payload") if isinstance(effect.get("payload"), dict) else {}
        num = ticket_payload.get("num")
        if map_operations.get(ticket_payload.get("map")) != operacao or not isinstance(num, str):
            continue
        match = re.fullmatch(r"tkt-(\d+)", num)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"tkt-{highest + 1:03d}"


def open_ticket(*, map, titulo, question, rationale, dispatch_id, author,
                blocked_by=None, inscricao=None, tier="asserted", legacy_ref=None,
                annotations=None, operacao=None, log=LOG):
    """Open one map-owned decision ticket with canonical dependency refs."""
    titulo = _lens_nonblank(titulo, "titulo")
    question = _lens_nonblank(question, "question")
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier=tier)
    events = read(log=log)
    parent = _resolve_lens_ref(map, events, operacao=operacao, kinds={"map"})
    if blocked_by is None:
        blocked_by = []
    if not isinstance(blocked_by, list):
        raise ValueError("`blocked_by` must be a list of ticket refs")
    blockers = []
    for ref in blocked_by:
        blocker = _resolve_lens_ref(
            ref, events, operacao=parent["operacao"], kinds={"ticket"})
        current = wayfinds_at(log=log)["tickets"].get(blocker["full"])
        if current is None or current["map"] != parent["ulid"]:
            raise ValueError("every blocked_by ticket must belong to the same map")
        if blocker["ulid"] not in blockers:
            blockers.append(blocker["ulid"])
    if inscricao is not None:
        inscricao = _lens_nonblank(inscricao, "inscricao")
        if inscricao not in hypotheses_at(log=log):
            raise ValueError("`inscricao` must reference an existing hypothesis.declared")
    if annotations is not None and not isinstance(annotations, dict):
        raise ValueError("`annotations` must be a dict")
    ulid = _ulid()
    payload = {"ulid": ulid, "num": None, "map": parent["ulid"], "titulo": titulo,
               "question": question, "rationale": rationale, "blocked_by": blockers,
               "inscricao": inscricao, "tier": tier, "author": author,
               "dispatch_id": dispatch_id, "legacy_ref": legacy_ref,
               "annotations": annotations}

    def _allocate_num():
        payload["num"] = _next_ticket_num(read(log=log), parent["operacao"])

    return append_batch(
        [("ticket.opened", f"ticket:{ulid}", payload)],
        log=log, precondition=_allocate_num,
    )[0]


def close_ticket(*, ref, resolucao, valencia, bears_on, rationale, dispatch_id,
                 author, tier="asserted", operacao=None, log=LOG):
    """Close/amend a ticket only with a non-empty valenced link to what resolved it."""
    resolucao = _lens_nonblank(resolucao, "resolucao")
    _lens_choice(valencia, "valencia", _BEARING_VALENCES)
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier=tier)
    if not isinstance(bears_on, list) or not bears_on:
        raise ValueError("ticket close `bears_on` must be a non-empty list")
    events = read(log=log)
    ticket = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"ticket"})
    current = wayfinds_at(log=log)["tickets"].get(ticket["full"])
    if current is None or current["estado"] == "declined":
        raise ValueError("cannot close a declined or nonexistent ticket; reopen it first")
    normalized_bearings = []
    for bearing in bears_on:
        if not isinstance(bearing, dict):
            raise ValueError("each ticket `bears_on` must be {alvo, valencia}")
        bearing_valence = _lens_choice(
            bearing.get("valencia"), "bears_on.valencia", _BEARING_VALENCES)
        target = _resolve_lens_ref(
            bearing.get("alvo"), events, operacao=ticket["operacao"],
            kinds={"atividade", "run", "arco", "fato", "claim", "hypothesis", "ticket"},
        )
        normalized_bearings.append({"alvo": target["ulid"], "valencia": bearing_valence})
    payload = {"ref": ticket["ulid"], "resolucao": resolucao, "valencia": valencia,
               "bears_on": normalized_bearings, "rationale": rationale, "tier": tier,
               "author": author, "dispatch_id": dispatch_id}
    return append("ticket.closed", f"ticket:{ticket['ulid']}", payload, log=log)


def decline_ticket(*, ref, reason, dispatch_id, author, rationale=None,
                   operacao=None, log=LOG):
    """Decline a ticket; a declined blocker explicitly unblocks its dependants."""
    reason = _lens_nonblank(reason, "reason")
    rationale = reason if rationale is None else rationale
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    ticket = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao, kinds={"ticket"})
    current = wayfinds_at(log=log)["tickets"].get(ticket["full"])
    if current is None or current["estado"] == "closed":
        raise ValueError("cannot decline a closed or nonexistent ticket")
    payload = {"ref": ticket["ulid"], "reason": reason, "rationale": rationale,
               "dispatch_id": dispatch_id, "author": author}
    return append("ticket.declined", f"ticket:{ticket['ulid']}", payload, log=log)


def reopen_ticket(*, ref, motivo, dispatch_id, author, evidencia=None,
                  rationale=None, operacao=None, log=LOG):
    """Explicitly reopen a closed/declined ticket; serialized state check rejects open."""
    motivo = _lens_nonblank(motivo, "motivo")
    rationale = motivo if rationale is None else rationale
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    ticket = _resolve_lens_ref(
        ref, read(log=log), operacao=operacao, kinds={"ticket"})
    payload = {"ref": ticket["ulid"], "motivo": motivo, "evidencia": evidencia,
               "rationale": rationale, "dispatch_id": dispatch_id, "author": author}

    def _must_be_terminal():
        current = wayfinds_at(log=log)["tickets"].get(ticket["full"])
        if current is None or current["estado"] == "open":
            raise ValueError("cannot reopen ticket: it is already open")

    return append_batch(
        [("ticket.reopened", f"ticket:{ticket['ulid']}", payload)],
        log=log, precondition=_must_be_terminal,
    )[0]


def _ticket_deps_have_cycle(tickets, target_ulid, desired):
    deps = {ticket["ulid"]: list(ticket.get("blocked_by", []))
            for ticket in tickets.values()}
    deps[target_ulid] = list(desired)
    visiting, done = set(), set()

    def visit(ulid):
        if ulid in visiting:
            return True
        if ulid in done:
            return False
        visiting.add(ulid)
        if any(blocker in deps and visit(blocker) for blocker in deps.get(ulid, [])):
            return True
        visiting.remove(ulid)
        done.add(ulid)
        return False

    return any(visit(ulid) for ulid in deps if ulid not in done)


def change_ticket_deps(*, ref, blocked_by, rationale, dispatch_id, author,
                       operacao=None, log=LOG):
    """Replace blocking edges atomically; a valid-API cycle is refused before append."""
    if not isinstance(blocked_by, list):
        raise ValueError("`blocked_by` must be a list of ticket refs")
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    events = read(log=log)
    ticket = _resolve_lens_ref(ref, events, operacao=operacao, kinds={"ticket"})
    folded = wayfinds_at(log=log)
    current = folded["tickets"].get(ticket["full"])
    if current is None:
        raise ValueError("ticket does not fold from its opening event")
    blockers = []
    for blocker_ref in blocked_by:
        blocker = _resolve_lens_ref(
            blocker_ref, events, operacao=ticket["operacao"], kinds={"ticket"})
        blocker_item = folded["tickets"].get(blocker["full"])
        if blocker_item is None or blocker_item["map"] != current["map"]:
            raise ValueError("every blocked_by ticket must belong to the same map")
        if blocker["ulid"] == ticket["ulid"]:
            raise ValueError("ticket dependency cycle: a ticket cannot block itself")
        if blocker["ulid"] not in blockers:
            blockers.append(blocker["ulid"])
    payload = {"ref": ticket["ulid"], "blocked_by": blockers,
               "rationale": rationale, "dispatch_id": dispatch_id, "author": author}

    def _acyclic_under_lock():
        current_fold = wayfinds_at(log=log)
        if _ticket_deps_have_cycle(current_fold["tickets"], ticket["ulid"], blockers):
            raise ValueError("ticket dependency cycle detected")

    return append_batch(
        [("ticket.deps_changed", f"ticket:{ticket['ulid']}", payload)],
        log=log, precondition=_acyclic_under_lock,
    )[0]


def fold_wayfinds(events):
    """Pure, fail-dark fold for map/ticket state and move audit history."""
    events = _events_with_embedded_move_effects(_operator_session_overlay(events))
    maps, tickets = {}, {}
    maps_by_ulid, tickets_by_ulid = {}, {}
    move_records, move_order = {}, []
    pins = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "map.opened":
            if not _foldable_map_open(payload):
                continue
            required = (payload.get("ulid"), payload.get("num"), payload.get("operacao"),
                        payload.get("titulo"), payload.get("rationale"),
                        payload.get("dispatch_id"), payload.get("author"))
            if (not all(isinstance(value, str) and value.strip() for value in required)
                    or payload.get("tier") not in _LENS_TIERS):
                continue
            ref = f"{payload['operacao']}/{payload['num']}"
            item = {**payload, "ref": ref, "estado": "ativado", "tickets": [],
                    "rationale_log": [{"event": "map.opened", "rationale": payload["rationale"],
                                       "seq": event.get("seq"), "ts": event.get("ts")}]}
            maps[ref] = item
            maps_by_ulid[payload["ulid"]] = item
        elif event_type == "map.state":
            item = maps_by_ulid.get(payload.get("ref"))
            if (item is None or payload.get("estado") not in _MAP_STATES
                    or payload.get("author") not in ("operador", "grill")
                    or not all(isinstance(payload.get(field), str) and payload[field].strip()
                               for field in ("rationale", "dispatch_id"))):
                continue
            item["estado"] = payload["estado"]
            item["rationale_log"].append({"event": event_type,
                                          "rationale": payload.get("rationale"),
                                          "seq": event.get("seq"), "ts": event.get("ts")})
        elif event_type == "ticket.opened":
            if not _foldable_ticket_open(payload):
                continue
            parent = maps_by_ulid.get(payload.get("map"))
            required = (payload.get("ulid"), payload.get("num"), payload.get("titulo"),
                        payload.get("question"), payload.get("rationale"),
                        payload.get("dispatch_id"), payload.get("author"))
            if (parent is None or not all(isinstance(value, str) and value.strip()
                                          for value in required)
                    or payload.get("tier") not in _LENS_TIERS
                    or not isinstance(payload.get("blocked_by", []), list)):
                continue
            ref = f"{parent['operacao']}/{payload['num']}"
            item = {**payload, "ref": ref, "operacao": parent["operacao"],
                    "estado": "open", "fechos": [], "fecho": None,
                    "declines": [], "reopens": []}
            tickets[ref] = item
            tickets_by_ulid[payload["ulid"]] = item
            parent["tickets"].append(ref)
        elif event_type == "ticket.closed":
            item = tickets_by_ulid.get(payload.get("ref"))
            if (item is None or item["estado"] == "declined"
                    or payload.get("valencia") not in _BEARING_VALENCES
                    or payload.get("tier") not in _LENS_TIERS
                    or not isinstance(payload.get("resolucao"), str)
                    or not isinstance(payload.get("bears_on"), list)
                    or not payload["bears_on"]
                    or not all(isinstance(payload.get(field), str) and payload[field].strip()
                               for field in ("rationale", "dispatch_id", "author"))):
                continue
            closure = {**payload,
                       "seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
                       "ts": event.get("ts")}
            item["fechos"].append(closure)
            item["fecho"] = max(
                item["fechos"],
                key=lambda candidate: (1 if candidate["tier"] == "asserted" else 0,
                                       candidate["seq"]),
            )
            item["estado"] = "closed"
        elif event_type == "ticket.declined":
            item = tickets_by_ulid.get(payload.get("ref"))
            if (item is None or item["estado"] == "closed"
                    or not isinstance(payload.get("reason"), str)
                    or not all(isinstance(payload.get(field), str) and payload[field].strip()
                               for field in ("rationale", "dispatch_id", "author"))):
                continue
            decline = {**payload, "seq": event.get("seq"), "ts": event.get("ts")}
            item["declines"].append(decline)
            item["estado"] = "declined"
        elif event_type == "ticket.reopened":
            item = tickets_by_ulid.get(payload.get("ref"))
            if (item is None or item["estado"] == "open"
                    or not isinstance(payload.get("motivo"), str)
                    or not all(isinstance(payload.get(field), str) and payload[field].strip()
                               for field in ("rationale", "dispatch_id", "author"))):
                continue
            reopening = {**payload, "seq": event.get("seq"), "ts": event.get("ts")}
            item["reopens"].append(reopening)
            item["estado"] = "open"
        elif event_type == "ticket.deps_changed":
            item = tickets_by_ulid.get(payload.get("ref"))
            blockers = payload.get("blocked_by")
            if (item is None or not isinstance(blockers, list)
                    or not all(isinstance(payload.get(field), str) and payload[field].strip()
                               for field in ("rationale", "dispatch_id", "author"))):
                continue
            item["blocked_by"] = list(blockers)
        elif event_type == "move.proposed":
            ulid = payload.get("ulid")
            if not isinstance(ulid, str):
                continue
            record = {**payload, "estado": "proposto", "seq": event.get("seq"),
                      "ts": event.get("ts"), "history": []}
            record["history"].append({"event": event_type, "seq": event.get("seq"),
                                      "ts": event.get("ts")})
            move_records[ulid] = record
            if ulid not in move_order:
                move_order.append(ulid)
        elif event_type == "move.ratified":
            record = move_records.get(payload.get("ref"))
            if record is None:
                continue
            record.update({"estado": "ratificado", "ratification": dict(payload)})
            record["history"].append({"event": event_type, "seq": event.get("seq"),
                                      "ts": event.get("ts")})
        elif event_type == "move.declined":
            record = move_records.get(payload.get("ref"))
            if record is None:
                continue
            record.update({"estado": "declinado", "decline": dict(payload)})
            record["history"].append({"event": event_type, "seq": event.get("seq"),
                                      "ts": event.get("ts")})
            if payload.get("pin") is True and isinstance(record.get("move_key"), str):
                pins.add(record["move_key"])
    moves = {
        "propostos": [move_records[ulid] for ulid in move_order
                       if move_records[ulid]["estado"] == "proposto"],
        "ratificados": [move_records[ulid] for ulid in move_order
                         if move_records[ulid]["estado"] == "ratificado"],
        "declinados": [move_records[ulid] for ulid in move_order
                        if move_records[ulid]["estado"] == "declinado"],
    }
    return {"maps": maps, "tickets": tickets, "moves": moves, "pins": pins}


def wayfinds_at(seq=None, ts=None, log=LOG):
    return fold_wayfinds(read(types=WAYFIND_TYPES, until_seq=seq, until_ts=ts, log=log))


def frontier_from_wayfinds(map_ref, wayfinds):
    """Pure frontier over an already-folded wayfinder snapshot; malformed branches fail dark."""
    maps = wayfinds.get("maps", {}) if isinstance(wayfinds, dict) else {}
    tickets = wayfinds.get("tickets", {}) if isinstance(wayfinds, dict) else {}
    current_map = maps.get(map_ref)
    if current_map is None:
        if isinstance(map_ref, str) and re.fullmatch(r"map-\d+", map_ref):
            raise AmbiguousRef(
                f"short ref {map_ref!r} requires an explicit operation bind; "
                f"use <operacao>/{map_ref}")
        matches = [item for item in maps.values()
                   if isinstance(item, dict) and item.get("ulid") == map_ref]
        if len(matches) != 1:
            raise ValueError("map ref does not resolve to exactly one existing grain of kind map")
        current_map = matches[0]
    if not isinstance(current_map, dict) or current_map.get("estado") != "ativado":
        return []
    by_ulid = {ticket.get("ulid"): ticket for ticket in tickets.values()
               if isinstance(ticket, dict) and isinstance(ticket.get("ulid"), str)}
    memo, visiting = {}, set()

    def layer(ticket):
        if not isinstance(ticket, dict) or not isinstance(ticket.get("ulid"), str):
            return None
        ulid = ticket["ulid"]
        if ulid in memo:
            return memo[ulid]
        if ulid in visiting:
            return None  # corrupt historical cycle: fail dark rather than recurse forever
        visiting.add(ulid)
        live_blocker_layers = []
        for blocker_ulid in ticket.get("blocked_by", []):
            blocker = by_ulid.get(blocker_ulid)
            if blocker is None or blocker.get("estado") in ("closed", "declined"):
                continue
            blocker_layer = layer(blocker)
            if blocker_layer is None:
                visiting.remove(ulid)
                return None
            live_blocker_layers.append(blocker_layer)
        visiting.remove(ulid)
        memo[ulid] = 0 if not live_blocker_layers else 1 + max(live_blocker_layers)
        return memo[ulid]

    grouped = {}
    map_tickets = current_map.get("tickets", [])
    if not isinstance(map_tickets, list):
        return []
    for ref in map_tickets:
        ticket = tickets.get(ref)
        if ticket is None or ticket.get("estado") != "open":
            continue
        ticket_layer = layer(ticket)
        if ticket_layer is not None:
            grouped.setdefault(ticket_layer, []).append(ref)
    return [grouped[index] for index in sorted(grouped)]


def frontier_of(map_ref, seq=None, ts=None, log=LOG):
    """Compute frontier layers from live dependency state; no frontier event exists."""
    folded = fold_wayfinds(read(
        types=WAYFIND_TYPES, until_seq=seq, until_ts=ts, log=log))
    return frontier_from_wayfinds(map_ref, folded)


class _MoveAlreadyExists(Exception):
    pass


def _ticket_open_intent_key(kind, alvo, effect, evidence_ulids):
    """Identity-free ticket.open intent used only to avoid spending a new reservation twice."""
    if kind != "ticket.open" or not isinstance(effect, dict):
        return None
    raw_payload = effect.get("payload")
    if not isinstance(raw_payload, dict):
        return None
    semantic_payload = dict(raw_payload)
    semantic_payload.pop("ulid", None)
    semantic_payload.pop("num", None)
    material = {
        "kind": kind,
        "alvo": alvo,
        "event_type": effect.get("event_type"),
        "payload": semantic_payload,
        "evidencia": sorted(evidence_ulids) if isinstance(evidence_ulids, list) else evidence_ulids,
    }
    return hashlib.sha256(json.dumps(
        material, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _move_target(kind, alvo, events, operacao):
    kinds = {
        "ticket.close": {"ticket"}, "ticket.reopen": {"ticket"},
        "atividade.close": {"atividade"}, "atividade.reopen": {"atividade"},
        "map.archive": {"map"}, "arco.move": {"atividade"},
        "contest": {"atividade", "ticket", "run", "arco", "hypothesis"},
        "falsificador_aconteceu": {"ticket"}, "ticket.open": {"map"},
    }[kind]
    return _resolve_lens_ref(alvo, events, operacao=operacao, kinds=kinds)


def _validated_ticket_open_proposal(payload, target, events):
    """Validate/canonicalize ticket semantics before its identity is allocated."""
    if payload.get("ulid") is not None or payload.get("num") is not None:
        raise ValueError("ticket.open proposal must leave effect ulid/num for flock allocation")
    if payload.get("map") not in (target["ulid"], target.get("full")):
        raise ValueError("ticket.open effect must belong to its map alvo")
    normalized = dict(payload)
    normalized.pop("ulid", None)
    normalized.pop("num", None)
    normalized["map"] = target["ulid"]
    normalized["titulo"] = _lens_nonblank(payload.get("titulo"), "effect.titulo")
    normalized["question"] = _lens_nonblank(payload.get("question"), "effect.question")
    rationale, dispatch_id, author = _wayfinder_curation(
        payload.get("rationale"), payload.get("dispatch_id"), payload.get("author"),
        tier=payload.get("tier"),
    )
    normalized.update({"rationale": rationale, "dispatch_id": dispatch_id,
                       "author": author, "tier": payload.get("tier")})
    blocked_by = payload.get("blocked_by", [])
    if not isinstance(blocked_by, list):
        raise ValueError("effect.blocked_by must be a list")
    folded = fold_wayfinds(events)
    blockers = []
    for ref in blocked_by:
        blocker = _resolve_lens_ref(
            ref, events, operacao=target["operacao"], kinds={"ticket"})
        current = folded["tickets"].get(blocker["full"])
        if current is None or current.get("map") != target["ulid"]:
            raise ValueError("every effect.blocked_by ticket must belong to the same map")
        if blocker["ulid"] not in blockers:
            blockers.append(blocker["ulid"])
    normalized["blocked_by"] = blockers
    inscricao = payload.get("inscricao")
    if inscricao is not None:
        inscricao = _resolve_lens_ref(
            inscricao, events, kinds={"hypothesis"})["ulid"]
    normalized["inscricao"] = inscricao
    annotations = payload.get("annotations")
    if annotations is not None and not isinstance(annotations, dict):
        raise ValueError("effect.annotations must be a dict or None")
    normalized["annotations"] = annotations
    return normalized


def _validated_move_effect(kind, effect, target, events, *, allow_unallocated_ticket=False):
    if not isinstance(effect, dict) or set(effect) != {"event_type", "subject", "payload"}:
        raise ValueError("`effect` must be exactly {event_type, subject, payload}")
    expected_type = _MOVE_EFFECT_TYPES[kind]
    if effect.get("event_type") != expected_type:
        raise ValueError(f"move kind {kind!r} requires effect.event_type={expected_type!r}")
    subject = (effect.get("subject") if expected_type == "ticket.opened"
               and allow_unallocated_ticket else
               _lens_nonblank(effect.get("subject"), "effect.subject"))
    if (expected_type == "ticket.opened" and allow_unallocated_ticket
            and subject is not None and not isinstance(subject, str)):
        raise ValueError("ticket.open proposal effect.subject must be a string or None")
    if not isinstance(effect.get("payload"), dict):
        raise ValueError("effect.payload must be a dict")
    try:
        payload = json.loads(json.dumps(effect["payload"], ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("effect.payload must be JSON-serializable") from exc

    target_ulid = target["ulid"]
    operation = target.get("operacao")
    if expected_type == "ticket.closed":
        if payload.get("ref") != target_ulid or subject != f"ticket:{target_ulid}":
            raise ValueError("ticket.close effect must address its canonical ticket alvo")
        payload["resolucao"] = _lens_nonblank(payload.get("resolucao"), "effect.resolucao")
        _lens_choice(payload.get("valencia"), "effect.valencia", _BEARING_VALENCES)
        _wayfinder_curation(payload.get("rationale"), payload.get("dispatch_id"),
                            payload.get("author"), tier=payload.get("tier"))
        bearings = payload.get("bears_on")
        if not isinstance(bearings, list) or not bearings:
            raise ValueError("effect ticket.closed needs non-empty `bears_on`")
        normalized = []
        for bearing in bearings:
            if not isinstance(bearing, dict):
                raise ValueError("effect bears_on items must be {alvo, valencia}")
            valence = _lens_choice(
                bearing.get("valencia"), "effect.bears_on.valencia", _BEARING_VALENCES)
            entity = _resolve_lens_ref(
                bearing.get("alvo"), events, operacao=operation,
                kinds={"atividade", "run", "arco", "fato", "claim", "hypothesis", "ticket"},
            )
            normalized.append({"alvo": entity["ulid"], "valencia": valence})
        payload["bears_on"] = normalized
    elif expected_type == "ticket.opened":
        if allow_unallocated_ticket:
            payload = _validated_ticket_open_proposal(payload, target, events)
            subject = None
        else:
            if not _foldable_ticket_open(payload) or subject != f"ticket:{payload.get('ulid')}":
                raise ValueError("ticket.open effect payload does not satisfy ticket.opened schema")
            if payload.get("map") != target_ulid:
                raise ValueError("ticket.open effect must belong to its map alvo")
    elif expected_type == "ticket.reopened":
        if payload.get("ref") != target_ulid or subject != f"ticket:{target_ulid}":
            raise ValueError("ticket.reopen effect must address its canonical ticket alvo")
        payload["motivo"] = _lens_nonblank(payload.get("motivo"), "effect.motivo")
        _wayfinder_curation(payload.get("rationale"), payload.get("dispatch_id"),
                            payload.get("author"), tier="asserted")
    elif expected_type == "atividade.closed":
        if payload.get("ref") != target_ulid or subject != f"atividade:{target_ulid}":
            raise ValueError("atividade.close effect must address its canonical atividade alvo")
        _lens_choice(payload.get("estado"), "effect.estado", _ACTIVITY_STATES)
        payload["julgamento"] = _lens_nonblank(payload.get("julgamento"), "effect.julgamento")
        payload["rationale"] = _lens_nonblank(payload.get("rationale"), "effect.rationale")
        payload["dispatch_id"] = _lens_nonblank(
            payload.get("dispatch_id"), "effect.dispatch_id")
        if payload["estado"] == "superada_por":
            successor = _resolve_lens_ref(payload.get("superada_por"), events,
                                          operacao=operation, kinds={"atividade"})
            payload["superada_por"] = successor["ulid"]
        elif payload.get("superada_por") is not None:
            raise ValueError("atividade.close effect superada_por only fits estado='superada_por'")
        _activity_curatorial_fields(tier=payload.get("tier"), author=payload.get("author"),
                                     rationale=payload.get("rationale"),
                                     dispatch_id=payload.get("dispatch_id"), log=Path("/tmp/move"))
    elif expected_type == "atividade.reopened":
        if payload.get("ref") != target_ulid or subject != f"atividade:{target_ulid}":
            raise ValueError("atividade.reopen effect must address its canonical atividade alvo")
        payload["motivo"] = _lens_nonblank(payload.get("motivo"), "effect.motivo")
        payload["rationale"] = _lens_nonblank(payload.get("rationale"), "effect.rationale")
        payload["dispatch_id"] = _lens_nonblank(
            payload.get("dispatch_id"), "effect.dispatch_id")
        _activity_curatorial_fields(tier=payload.get("tier"), author=payload.get("author"),
                                     rationale=payload.get("rationale"),
                                     dispatch_id=payload.get("dispatch_id"), log=Path("/tmp/move"))
    elif expected_type == "map.state":
        if (payload.get("ref") != target_ulid or subject != f"map:{target_ulid}"
                or payload.get("estado") != "arquivado"):
            raise ValueError("map.archive effect must be map.state estado='arquivado' for alvo")
        _wayfinder_curation(payload.get("rationale"), payload.get("dispatch_id"),
                            payload.get("author"), tier="asserted")
    elif expected_type == "arco.moved":
        if payload.get("ref") != target_ulid or subject != f"atividade:{target_ulid}":
            raise ValueError("arco.move effect must address its canonical atividade alvo")
        new_arc = _resolve_lens_ref(
            payload.get("arco_novo"), events, operacao=operation, kinds={"arco"})
        payload["arco_novo"] = new_arc["ulid"]
        payload["rationale"] = _lens_nonblank(payload.get("rationale"), "effect.rationale")
        payload["dispatch_id"] = _lens_nonblank(
            payload.get("dispatch_id"), "effect.dispatch_id")
        _activity_curatorial_fields(tier=payload.get("tier"), author=payload.get("author"),
                                     rationale=payload.get("rationale"),
                                     dispatch_id=payload.get("dispatch_id"), log=Path("/tmp/move"))
    elif expected_type == "contest.raised":
        if payload.get("alvo") != target_ulid:
            raise ValueError("contest effect payload.alvo must equal canonical move alvo")
        if subject != f"{target['kind']}:{target_ulid}":
            raise ValueError("contest effect subject must address the canonical move alvo")
        evidence = _resolve_lens_ref(payload.get("evidencia"), events, operacao=operation,
                                     kinds={"fato", "run", "atividade"})
        payload["evidencia"] = evidence["ulid"]
        payload["detalhe"] = _lens_nonblank(payload.get("detalhe"), "effect.detalhe")
        payload["author"] = _lens_nonblank(payload.get("author"), "effect.author")
    return {"event_type": expected_type, "subject": subject, "payload": payload}


def propose_move(*, kind, effect, expects, evidencia, rationale, basis_seq,
                 alvo=None, author="edge", operacao=None, log=LOG):
    """Film a typed move once; move_key CAS is authoritative across every later state."""
    if kind not in _MOVE_EFFECT_TYPES:
        raise ValueError(f"unknown move `kind` {kind!r}")
    if author != "edge":
        raise ValueError("move.proposed author must be 'edge'")
    rationale = _lens_nonblank(rationale, "rationale")
    if not isinstance(basis_seq, int) or isinstance(basis_seq, bool) or basis_seq < 0:
        raise ValueError("`basis_seq` must be a non-negative integer")
    if not isinstance(expects, dict):
        raise ValueError("`expects` must be a dict")
    if not isinstance(evidencia, list) or not evidencia:
        raise ValueError("`evidencia` must be a non-empty list of resolvable refs")
    events = read(log=log)
    if alvo is None and kind == "ticket.open" and isinstance(effect, dict):
        effect_payload = effect.get("payload")
        alvo = effect_payload.get("map") if isinstance(effect_payload, dict) else None
    if alvo is None:
        raise ValueError(f"move kind {kind!r} requires an explicit `alvo`")
    target = _move_target(kind, alvo, events, operacao)
    normalized_effect = _validated_move_effect(
        kind, effect, target, events, allow_unallocated_ticket=(kind == "ticket.open"))
    evidence_ulids = sorted({
        _resolve_lens_ref(ref, events, operacao=target.get("operacao"),
                          kinds={"atividade", "run", "fato"})["ulid"]
        for ref in evidencia
    })
    ulid = _ulid()
    payload = {"ulid": ulid, "kind": kind, "alvo": target["ulid"],
               "effect": normalized_effect, "expects": dict(expects),
               "evidencia": evidence_ulids, "rationale": rationale,
               "basis_seq": basis_seq, "move_key": None, "author": "edge"}

    def _set_move_key():
        key_material = {"kind": kind, "alvo": target["ulid"], "effect": payload["effect"],
                        "evidencia": evidence_ulids}
        payload["move_key"] = hashlib.sha256(json.dumps(
            key_material, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()

    if kind != "ticket.open":
        _set_move_key()

    def _move_key_absent():
        if kind == "ticket.open":
            # Identity allocation belongs to the same critical section that reserves the number.
            # A concurrent proposer/open_ticket therefore sees this proposal before choosing its
            # own number; the generated identity is part of move_key, never patched afterwards.
            current_events = read(log=log)
            current_target = _move_target(
                kind, target["ulid"], current_events, target.get("operacao"))
            incoming_intent = _ticket_open_intent_key(
                kind, current_target["ulid"], payload["effect"], evidence_ulids)
            if any(
                event.get("type") == "move.proposed"
                and isinstance(event.get("payload"), dict)
                and _ticket_open_intent_key(
                    event["payload"].get("kind"), event["payload"].get("alvo"),
                    event["payload"].get("effect"), event["payload"].get("evidencia"),
                ) == incoming_intent
                for event in current_events
            ):
                raise _MoveAlreadyExists(incoming_intent)
            ticket_payload = dict(payload["effect"]["payload"])
            ticket_payload["ulid"] = _ulid()
            ticket_payload["num"] = _next_ticket_num(
                current_events, current_target["operacao"])
            candidate = {"event_type": "ticket.opened",
                         "subject": f"ticket:{ticket_payload['ulid']}",
                         "payload": ticket_payload}
            payload["effect"] = _validated_move_effect(
                kind, candidate, current_target, current_events)
            _set_move_key()
        move_key = payload["move_key"]
        if any(isinstance(event.get("payload"), dict)
               and event["payload"].get("move_key") == move_key
               for event in read(types=["move.proposed"], log=log)):
            raise _MoveAlreadyExists(move_key)

    try:
        return append_batch(
            [("move.proposed", f"move:{ulid}", payload)],
            log=log, precondition=_move_key_absent,
        )[0]
    except _MoveAlreadyExists:
        return None


def _events_with_embedded_move_effects(events):
    """Recover a missing materialized effect from move.ratified without double-applying it."""
    events = list(events)
    materialized = {
        (event.get("seq"), event.get("type"), event.get("subject"),
         json.dumps(event.get("payload"), sort_keys=True, ensure_ascii=False))
        for event in events if isinstance(event, dict)
    }
    expanded = []
    for event in events:
        expanded.append(event)
        if not isinstance(event, dict) or event.get("type") != "move.ratified":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        effect = payload.get("effect")
        if not (isinstance(effect, dict)
                and set(effect) == {"event_type", "subject", "payload"}):
            continue
        identity = ((event.get("seq") + 1) if isinstance(event.get("seq"), int) else None,
                    effect["event_type"], effect["subject"],
                    json.dumps(effect["payload"], sort_keys=True, ensure_ascii=False))
        if identity in materialized:
            continue
        expanded.append({"seq": event.get("seq"), "ts": event.get("ts"),
                         "type": effect["event_type"], "subject": effect["subject"],
                         "payload": effect["payload"], "recovered_from_move": payload.get("ref")})
    return expanded


def _current_move_target(proposal, log):
    target_ulid = proposal.get("alvo")
    entity = next((entity for entity in _lens_entities(read(log=log))
                   if entity["ulid"] == target_ulid), None)
    if entity is None:
        return None
    if entity["kind"] == "ticket":
        return wayfinds_at(log=log)["tickets"].get(entity["full"])
    if entity["kind"] == "map":
        return wayfinds_at(log=log)["maps"].get(entity["full"])
    if entity["kind"] == "atividade":
        return atividades_at(log=log).get(entity["full"])
    if entity["kind"] == "run":
        return runs_at(log=log).get(entity["full"])
    if entity["kind"] == "arco":
        return arcos_at(log=log).get(entity["full"])
    return {"ulid": target_ulid}


def _bound_move_operation(proposal, operacao, log):
    events = read(log=log)
    target = _move_target(
        proposal.get("kind"), proposal.get("alvo"), events, None)
    actual = target.get("operacao")
    if operacao is not None:
        bound = _lens_operacao(operacao)
        if actual != bound:
            raise ValueError(
                f"move target belongs to operacao {actual!r}, not explicit bind {bound!r}")
    normalized = _validated_move_effect(
        proposal.get("kind"), proposal.get("effect"), target, events)
    if normalized != proposal.get("effect"):
        raise ValueError("move effect no longer matches its canonical operation-bound target")
    return actual, target


def ratify_move(*, ref, rationale, dispatch_id, author, operacao=None, log=LOG):
    """CAS-ratify a live move and materialize its exact embedded effect in one append batch."""
    ref = _lens_nonblank(ref, "ref")
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    proposed = next((move for move in wayfinds_at(log=log)["moves"]["propostos"]
                     if move.get("ulid") == ref), None)
    if proposed is None:
        raise ValueError(f"move {ref!r} is not in proposed state")
    operation, target_entity = _bound_move_operation(proposed, operacao, log)
    effect = json.loads(json.dumps(proposed["effect"], ensure_ascii=False))
    ratification_payload = {"ref": ref, "effect": effect, "rationale": rationale,
                            "dispatch_id": dispatch_id, "author": author,
                            "operacao": operation, "alvo": target_entity["ulid"]}
    ratification = ("move.ratified", f"move:{ref}", ratification_payload)
    materialized = (effect["event_type"], effect["subject"], effect["payload"])

    def _still_applicable():
        current = next((move for move in wayfinds_at(log=log)["moves"]["propostos"]
                        if move.get("ulid") == ref), None)
        if current is None:
            raise ValueError(f"move {ref!r} is no longer proposed (ratify/decline CAS)")
        _bound_move_operation(current, operacao, log)
        if current.get("basis_seq", -1) > _physical_len(log):
            raise ValueError("move basis_seq is ahead of the current ledger")
        target = _current_move_target(current, log)
        expects = current.get("expects") if isinstance(current.get("expects"), dict) else {}
        mismatches = {field: {"expected": expected,
                              "actual": target.get(field) if isinstance(target, dict) else None}
                      for field, expected in expects.items()
                      if not isinstance(target, dict) or target.get(field) != expected}
        if mismatches:
            raise ValueError(f"stale move {ref!r}: current target state mismatches {mismatches}")

    written = append_batch(
        [ratification, materialized], log=log, precondition=_still_applicable,
    )
    return written[0], written[1]


def decline_move(*, ref, reason, dispatch_id, author, pin=False, rationale=None,
                 operacao=None, log=LOG):
    """CAS-decline a live move; pin records its move_key in the fold, not merely its ULID."""
    ref = _lens_nonblank(ref, "ref")
    reason = _lens_nonblank(reason, "reason")
    if not isinstance(pin, bool):
        raise ValueError("`pin` must be a bool")
    rationale = reason if rationale is None else rationale
    rationale, dispatch_id, author = _wayfinder_curation(
        rationale, dispatch_id, author, tier="asserted")
    proposed = next((move for move in wayfinds_at(log=log)["moves"]["propostos"]
                     if move.get("ulid") == ref), None)
    if proposed is None:
        raise ValueError(f"move {ref!r} is not in proposed state")
    operation, target_entity = _bound_move_operation(proposed, operacao, log)
    payload = {"ref": ref, "reason": reason, "pin": pin, "rationale": rationale,
               "dispatch_id": dispatch_id, "author": author,
               "operacao": operation, "alvo": target_entity["ulid"]}

    def _still_proposed():
        current = next((move for move in wayfinds_at(log=log)["moves"]["propostos"]
                        if move.get("ulid") == ref), None)
        if current is None:
            raise ValueError(f"move {ref!r} is no longer proposed (ratify/decline CAS)")
        _bound_move_operation(current, operacao, log)

    return append_batch(
        [("move.declined", f"move:{ref}", payload)],
        log=log, precondition=_still_proposed,
    )[0]


def confirm_portfolio(*, rationale, dispatch_id, log=LOG):
    """Record the explicit curated no-op for one exact mentor dispatch."""
    rationale = _lens_nonblank(rationale, "rationale")
    dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    return append("portfolio.confirmed", "portfolio",
                  {"rationale": rationale, "dispatch_id": dispatch_id}, log=log)


def portfolio_diff(dispatch_id, log=LOG):
    """Return only gestures committed by one exact dispatch id, never a time-window guess."""
    dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    events = read(log=log)
    gestures = [event for event in events
                if isinstance(event.get("payload"), dict)
                and event["payload"].get("dispatch_id") == dispatch_id]
    entities = {entity["ulid"]: entity for entity in _lens_entities(events)}
    current_wayfinds = wayfinds_at(log=log)
    result = {"abertos": [], "fechados": [], "reabertos": [],
              "ativados": [], "pausados": [], "arquivados": [],
              "moves_ratificados": [], "frontier_antes": {}, "frontier_depois": {},
              "confirmed": []}
    affected_maps = set()

    def add_unique(field, value):
        if value is not None and value not in result[field]:
            result[field].append(value)

    for event in gestures:
        event_type = event.get("type")
        payload = event["payload"]
        entity = entities.get(payload.get("ref") or payload.get("ulid"))
        full_ref = entity.get("full") if entity else None
        if entity and entity.get("kind") == "ticket":
            ticket_item = current_wayfinds["tickets"].get(full_ref)
            parent = entities.get(ticket_item.get("map")) if ticket_item else None
            if parent:
                affected_maps.add(parent["full"])
        if event_type == "ticket.opened":
            add_unique("abertos", full_ref)
            parent = entities.get(payload.get("map"))
            if parent:
                affected_maps.add(parent["full"])
        elif event_type == "ticket.closed":
            add_unique("fechados", full_ref)
        elif event_type == "ticket.reopened":
            add_unique("reabertos", full_ref)
        elif event_type == "atividade.closed":
            add_unique("fechados", full_ref)
        elif event_type == "atividade.reopened":
            add_unique("reabertos", full_ref)
        elif event_type == "map.opened":
            add_unique("ativados", full_ref)
            if full_ref:
                affected_maps.add(full_ref)
        elif event_type == "map.state":
            field = {"ativado": "ativados", "pausado": "pausados",
                     "arquivado": "arquivados"}.get(payload.get("estado"))
            if field:
                add_unique(field, full_ref)
            if full_ref:
                affected_maps.add(full_ref)
        elif event_type == "move.ratified":
            add_unique("moves_ratificados", payload.get("ref"))
            effect = payload.get("effect")
            effect_payload = effect.get("payload") if isinstance(effect, dict) else None
            effect_entity = (entities.get(effect_payload.get("ref"))
                             if isinstance(effect_payload, dict) else None)
            if effect_entity and effect_entity.get("kind") == "ticket":
                ticket_item = current_wayfinds["tickets"].get(effect_entity["full"])
                parent = entities.get(ticket_item.get("map")) if ticket_item else None
                if parent:
                    affected_maps.add(parent["full"])
        elif event_type == "portfolio.confirmed":
            result["confirmed"].append({"seq": event.get("seq"),
                                        "rationale": payload.get("rationale")})
    if gestures and affected_maps:
        first_seq = min(event.get("seq", 0) for event in gestures)
        last_seq = max(event.get("seq", 0) for event in gestures)
        for map_ref in sorted(affected_maps):
            try:
                before = frontier_of(map_ref, seq=max(0, first_seq - 1), log=log)
            except ValueError:
                before = []
            try:
                after = frontier_of(map_ref, seq=last_seq, log=log)
            except ValueError:
                after = []
            result["frontier_antes"][map_ref] = before
            result["frontier_depois"][map_ref] = after
    return result


def hypothesize_claim(*, statement, origem_sessao, derivation_key, falsifier=None, log=LOG):
    """Record a bounded rationalizer claim; absent falsifier means salience, not a debt."""
    statement = _lens_nonblank(statement, "statement")
    origem_sessao = _lens_nonblank(origem_sessao, "origem_sessao")
    derivation_key = _lens_nonblank(derivation_key, "derivation_key")
    if falsifier is not None:
        falsifier = _validated_falsifier(falsifier)
    ulid = _ulid()
    payload = {"ulid": ulid, "statement": statement, "falsifier": falsifier,
               "origem_sessao": origem_sessao, "derivation_key": derivation_key,
               "tier": "llm_judged"}
    return append("claim.hypothesized", f"claim:{ulid}", payload, log=log)


def promote_claim(*, hypothesized, declared, log=LOG):
    """Link an existing rationalizer claim to the declared hypothesis that ratified it."""
    hypothesized = _lens_nonblank(hypothesized, "hypothesized")
    declared = _lens_nonblank(declared, "declared")
    claims = claims_at(log=log)
    if hypothesized not in claims["hypothesized"]:
        raise ValueError(f"no existing claim.hypothesized {hypothesized!r}")
    if declared not in claims["declared"]:
        raise ValueError(f"no existing hypothesis.declared {declared!r}")
    payload = {"hypothesized": hypothesized, "declared": declared}
    return append("claim.promoted", f"claim:{hypothesized}", payload, log=log)


def raise_contest(*, alvo, evidencia, detalhe, author, operacao=None, log=LOG):
    """Raise a contradiction backed by a real evidence grain; authority remains unchanged."""
    detalhe = _lens_nonblank(detalhe, "detalhe")
    author = _lens_nonblank(author, "author")
    events = read(log=log)
    target = _resolve_lens_ref(
        alvo, events, operacao=operacao,
        kinds={"atividade", "run", "arco", "ticket", "claim", "hypothesis"},
    )
    evidence = _resolve_lens_ref(
        evidencia, events, operacao=target.get("operacao"),
        kinds={"fato", "run", "atividade"},
    )
    if target["kind"] == "atividade":
        state = atividades_at(log=log).get(target["full"], {}).get("estado")
        if state in (None, "aberta", "reaberta"):
            raise ValueError("contest `alvo` activity must be closed/curated")
    elif target["kind"] == "run" and runs_at(log=log).get(target["full"], {}).get("fecho") is None:
        raise ValueError("contest `alvo` run must be closed/curated")
    elif target["kind"] == "arco" and arcos_at(log=log).get(target["full"], {}).get("fecho") is None:
        raise ValueError("contest `alvo` arco must be closed/curated")
    payload = {"alvo": target["ulid"], "evidencia": evidence["ulid"],
               "detalhe": detalhe, "author": author}
    return append("contest.raised", f"{target['kind']}:{target['ulid']}", payload, log=log)


def adjudicate_contest(*, alvo, veredito, rationale, dispatch_id, author,
                       sucessor=None, operacao=None, log=LOG):
    """Adjudicate an open contest; `mantido` clears visibility without rewriting history."""
    _lens_choice(veredito, "veredito", ("mantido", "corrigido"))
    rationale = _lens_nonblank(rationale, "rationale")
    dispatch_id = _lens_nonblank(dispatch_id, "dispatch_id")
    if author not in ("operador", "grill"):
        raise ValueError("contest adjudication author must be operador or grill")
    events = read(log=log)
    target = _resolve_lens_ref(
        alvo, events, operacao=operacao,
        kinds={"atividade", "run", "arco", "ticket", "claim", "hypothesis"},
    )
    def _contest_is_open():
        current_events = read(types=CONTEST_TYPES, log=log)
        raised = [event for event in current_events if event.get("type") == "contest.raised"
                  and isinstance(event.get("payload"), dict)
                  and event["payload"].get("alvo") == target["ulid"]]
        adjudicated = [event for event in current_events
                       if event.get("type") == "contest.adjudicated"
                       and isinstance(event.get("payload"), dict)
                       and event["payload"].get("alvo") == target["ulid"]]
        return bool(raised) and not (
            adjudicated and adjudicated[-1].get("seq", -1) > raised[-1].get("seq", -1))

    if not _contest_is_open():
        raise ValueError(f"target {target['full'] or target['ulid']!r} is not contested")
    if veredito == "corrigido" and sucessor is None:
        raise ValueError("veredito='corrigido' requires `sucessor`")
    if veredito == "mantido" and sucessor is not None:
        raise ValueError("veredito='mantido' must not carry `sucessor`")
    payload = {"alvo": target["ulid"], "veredito": veredito, "sucessor": None,
               "rationale": rationale, "dispatch_id": dispatch_id, "author": author}
    adjudication_tuple = (
        "contest.adjudicated", f"{target['kind']}:{target['ulid']}", payload,
    )
    if veredito == "mantido":
        def _still_open():
            if not _contest_is_open():
                raise ValueError("contest was already adjudicated by a concurrent writer")

        return append_batch([adjudication_tuple], log=log, precondition=_still_open)[0]

    if not isinstance(sucessor, dict):
        raise ValueError("`sucessor` must be a same-batch event descriptor {type, subject, payload}")
    successor_type = sucessor.get("type")
    successor_subject = sucessor.get("subject")
    successor_payload = sucessor.get("payload")
    if (target["kind"] != "atividade" or successor_type != "atividade.closed"
            or successor_subject != f"atividade:{target['ulid']}"
            or not isinstance(successor_payload, dict)):
        raise ValueError("corrected activity contest needs an atividade.closed successor descriptor")
    successor_payload = dict(successor_payload)
    if (successor_payload.get("ref") != target["ulid"]
            or successor_payload.get("tier") != "asserted"
            or successor_payload.get("author") not in ("operador", "grill")
            or successor_payload.get("estado") not in _ACTIVITY_STATES):
        raise ValueError("contest successor must be an asserted closure of the contested activity")
    successor_payload["julgamento"] = _lens_nonblank(
        successor_payload.get("julgamento"), "sucessor.julgamento")
    successor_payload["rationale"] = _lens_nonblank(
        successor_payload.get("rationale"), "sucessor.rationale")
    successor_payload["dispatch_id"] = _lens_nonblank(
        successor_payload.get("dispatch_id"), "sucessor.dispatch_id")
    if successor_payload["estado"] == "superada_por":
        _resolve_lens_ref(successor_payload.get("superada_por"), events,
                          operacao=target["operacao"], kinds={"atividade"})
    elif successor_payload.get("superada_por") is not None:
        raise ValueError("successor `superada_por` is only valid for estado='superada_por'")

    def _still_open_and_bind_successor():
        if not _contest_is_open():
            raise ValueError("contest was already adjudicated by a concurrent writer")
        payload["sucessor"] = _physical_len(log) + 1

    return append_batch(
        [(successor_type, successor_subject, successor_payload), adjudication_tuple],
        log=log, precondition=_still_open_and_bind_successor,
    )


def _foldable_hypothesized_claim(payload):
    if not (
        isinstance(payload.get("ulid"), str) and payload["ulid"]
        and isinstance(payload.get("statement"), str) and payload["statement"].strip()
        and isinstance(payload.get("origem_sessao"), str) and payload["origem_sessao"].strip()
        and isinstance(payload.get("derivation_key"), str) and payload["derivation_key"].strip()
        and payload.get("tier") == "llm_judged"
    ):
        return False
    falsifier = payload.get("falsifier")
    if falsifier is None:
        return True
    try:
        return _validated_falsifier(falsifier) == falsifier
    except ValueError:
        return False


def fold_claims(events):
    """Pure claim fold over one caller-owned event snapshot; malformed rows fail dark."""
    events = _events_with_embedded_move_effects(_operator_session_overlay(events))
    declared = fold_hypotheses([event for event in events
                                if event.get("type") in HYPOTHESIS_TYPES])
    for item in declared.values():
        item.update({"contested": False, "contests": [], "adjudications": []})
    hypothesized = {}
    promoted = {}
    contested = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "claim.hypothesized" and _foldable_hypothesized_claim(payload):
            item = dict(payload)
            item.update({"promoted_to": None, "contested": False,
                         "created_at": event.get("ts")})
            hypothesized[payload["ulid"]] = item
        elif event.get("type") == "claim.promoted":
            source, target = payload.get("hypothesized"), payload.get("declared")
            if source in hypothesized and target in declared:
                hypothesized[source]["promoted_to"] = target
                promoted[source] = target
        elif event.get("type") == "contest.raised":
            target = payload.get("alvo")
            item = declared.get(target) or hypothesized.get(target)
            if item is not None:
                item["contested"] = True
                item["contests"].append({**payload, "seq": event.get("seq"),
                                          "ts": event.get("ts")})
                if target not in contested:
                    contested.append(target)
        elif event.get("type") == "contest.adjudicated":
            target = payload.get("alvo")
            item = declared.get(target) or hypothesized.get(target)
            if item is not None and payload.get("veredito") in ("mantido", "corrigido"):
                item["contested"] = False
                item["adjudications"].append({**payload, "seq": event.get("seq"),
                                               "ts": event.get("ts")})
                if target in contested:
                    contested.remove(target)
    return {"declared": declared, "hypothesized": hypothesized,
            "promoted": promoted, "contested": contested}


def claims_at(seq=None, ts=None, log=LOG):
    """Fold declared and hypothesized claims, retaining promotions and contest visibility."""
    return fold_claims(read(
        types=CLAIM_TYPES + CONTEST_TYPES + [
            "move.ratified", "sessao.racionalizada", "sessao.excluded"],
        until_seq=seq, until_ts=ts, log=log))


def fold_presumptions(events):
    """Pure epistemic dependency graph over one event snapshot; performs zero I/O."""
    events = _operator_session_overlay(events)
    claims = fold_claims(events)
    session_operations = {}
    for event in events:
        if event.get("type") != "sessao.racionalizada":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        session = payload.get("sessao_id")
        operations = payload.get("operacoes")
        if (isinstance(session, str) and isinstance(operations, list)
                and all(isinstance(operation, str) and _OPERACAO_RE.fullmatch(operation)
                        for operation in operations)):
            session_operations[session] = sorted(set(operations))
    nodes = {}
    for ulid, claim in claims["declared"].items():
        if claim.get("falsifier") is not None:
            nodes[f"claim:{ulid}"] = {"kind": "claim", "ref": ulid,
                                       "eval": claim["falsifier"], "depends_on": [],
                                       "operacoes": []}
    for ulid, claim in claims["hypothesized"].items():
        if claim.get("falsifier") is not None:
            nodes[f"claim:{ulid}"] = {
                "kind": "claim", "ref": ulid, "eval": claim["falsifier"],
                "depends_on": [],
                "operacoes": list(session_operations.get(claim.get("origem_sessao"), [])),
            }

    facts_by_full = {}
    facts_by_run = {}
    direct_facts_by_activity = {}
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") != "fato.observed" or not _foldable_fact_observed(payload):
            continue
        full_ref = f"{payload['operacao']}/{payload['num']}"
        key = f"fato:{payload['ulid']}"
        facts_by_full[full_ref] = key
        if payload.get("medida") is not None:
            nodes[key] = {"kind": "fato", "ref": full_ref, "eval": payload["medida"],
                          "body": payload["body"], "depends_on": [],
                          "operacoes": [payload["operacao"]]}
        if isinstance(payload.get("run"), str):
            facts_by_run.setdefault(payload["run"], []).append(key)
        else:
            direct_facts_by_activity.setdefault(payload["atividade"], []).append(key)

    runs = fold_runs(events)
    run_key_by_full = {}
    for full_ref, run in runs.items():
        key = f"run:{run['ulid']}"
        run_key_by_full[full_ref] = key
        nodes[key] = {
            "kind": "run", "ref": full_ref, "eval": run["eval"],
            "resultado": run.get("resultado"),
            "bears_on": (run.get("fecho") or {}).get("bears_on", []),
            "operacoes": [run["operacao"]],
            "depends_on": list(dict.fromkeys(
                fact_key for fact_key in facts_by_run.get(run["ulid"], [])
                if fact_key in nodes
            )),
        }

    activities = fold_atividades(events)
    activity_key_by_ulid = {}
    activities_by_arc = {}
    for full_ref, activity in activities.items():
        key = f"atividade:{activity['ulid']}"
        activity_key_by_ulid[activity["ulid"]] = key
        dependencies = [run_key_by_full[run_ref] for run_ref in activity["runs"]
                        if run_ref in run_key_by_full]
        dependencies.extend(
            fact_key for fact_key in direct_facts_by_activity.get(activity["ulid"], [])
            if fact_key in nodes
        )
        nodes[key] = {
            "kind": "atividade", "ref": full_ref,
            "eval": activity.get("eval") or {"regua": activity["finalidade"]},
            "estado": activity["estado"],
            "operacoes": [activity["operacao"]],
            "depends_on": list(dict.fromkeys(dependencies)),
        }
        if isinstance(activity.get("arco"), str):
            activities_by_arc.setdefault(activity["arco"], []).append(key)
        for bearing in activity.get("bears_on", []):
            claim_node = nodes.get(f"claim:{bearing.get('alvo')}")
            if claim_node is not None:
                claim_node["operacoes"] = sorted(set(
                    claim_node.get("operacoes", []) + [activity["operacao"]]
                ))

    wayfinds = fold_wayfinds(events)
    for ticket in wayfinds["tickets"].values():
        claim_node = nodes.get(f"claim:{ticket.get('inscricao')}")
        if claim_node is not None:
            claim_node["operacoes"] = sorted(set(
                claim_node.get("operacoes", []) + [ticket["operacao"]]
            ))

    arcs = fold_arcos(events)
    arc_roots = []
    for full_ref, arc in arcs.items():
        key = f"arco:{arc['ulid']}"
        nodes[key] = {
            "kind": "arco", "ref": full_ref,
            "eval": ({"valencia": arc["valencia"], "julgamento": arc["julgamento"]}
                     if arc.get("fecho") is not None else None),
            "depends_on": list(dict.fromkeys(activities_by_arc.get(arc["ulid"], []))),
            "operacoes": [arc["operacao"]],
        }
        arc_roots.append(key)

    session_roots = []
    for event in events:
        if event.get("type") != "sessao.racionalizada":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        epistemic = payload.get("epistemico")
        presumptions = epistemic.get("presuncoes") if isinstance(epistemic, dict) else None
        if not isinstance(presumptions, list):
            continue
        session_identity = payload.get("rationalization_id") or payload.get("sessao_id") or event.get("seq")
        for index, presumption in enumerate(presumptions):
            if not isinstance(presumption, dict):
                continue
            text = presumption.get("texto")
            confirms, refutes = presumption.get("confirmaria"), presumption.get("refutaria")
            if not all(isinstance(value, str) and value.strip()
                       for value in (text, confirms, refutes)):
                continue
            key = f"sessao:{session_identity}:presuncao:{index}"
            dependency = presumption.get("depende_de")
            depends_on = []
            if isinstance(dependency, str):
                if dependency in run_key_by_full:
                    depends_on = [run_key_by_full[dependency]]
                elif dependency in facts_by_full:
                    depends_on = [facts_by_full[dependency]]
            nodes[key] = {
                "kind": "presuncao", "ref": key, "texto": text.strip(),
                "eval": {"confirmaria": confirms.strip(), "refutaria": refutes.strip()},
                "depends_on": depends_on,
                "operacoes": list(session_operations.get(payload.get("sessao_id"), [])),
            }
            session_roots.append(key)

    activity_roots = [key for ulid, key in activity_key_by_ulid.items()
                      if ulid not in {activity["ulid"] for activity in activities.values()
                                     if isinstance(activity.get("arco"), str)}]
    claim_roots = [key for key, node in nodes.items() if node["kind"] == "claim"]
    roots = list(dict.fromkeys(claim_roots + session_roots + arc_roots + activity_roots))
    return {"nodes": nodes, "roots": roots}


def presumptions_at(seq=None, ts=None, log=LOG):
    """Epistemic dependency graph. Organizational metadata is deliberately never inspected."""
    return fold_presumptions(read(until_seq=seq, until_ts=ts, log=log))


def _foldable_activity_open(payload):
    """Semantic read-side gate: malformed truth stays in the ledger but not in the projection."""
    ulid, num = payload.get("ulid"), payload.get("num")
    operation, purpose = payload.get("operacao"), payload.get("finalidade")
    tier, author = payload.get("tier"), payload.get("author")
    if not (isinstance(ulid, str) and ulid
            and isinstance(num, str) and re.fullmatch(r"atv-\d+", num)
            and isinstance(operation, str) and _OPERACAO_RE.fullmatch(operation)
            and isinstance(purpose, str) and purpose.strip()
            and tier in _LENS_TIERS and author in _ACTIVITY_AUTHORS):
        return False
    if ((tier == "asserted" and author not in ("operador", "grill"))
            or (tier == "llm_judged" and author != "racionalizador")):
        return False
    if tier == "llm_judged" and not (
            isinstance(payload.get("origem_sessao"), str) and payload["origem_sessao"].strip()
            and isinstance(payload.get("derivation_key"), str)
            and payload["derivation_key"].strip()):
        return False
    evaluation = payload.get("eval")
    if evaluation is not None and not (
            isinstance(evaluation, dict)
            and isinstance(evaluation.get("regua"), str) and evaluation["regua"].strip()):
        return False
    type_ref = payload.get("tipo_ref")
    return type_ref is None or (isinstance(type_ref, str) and _TIPO_REF_RE.fullmatch(type_ref))


def _foldable_map_open(payload):
    tier, author = payload.get("tier"), payload.get("author")
    if not (
        isinstance(payload.get("ulid"), str) and payload["ulid"]
        and isinstance(payload.get("num"), str) and re.fullmatch(r"map-\d+", payload["num"])
        and isinstance(payload.get("operacao"), str) and _OPERACAO_RE.fullmatch(payload["operacao"])
        and all(isinstance(payload.get(field), str) and payload[field].strip()
                for field in ("titulo", "rationale", "dispatch_id"))
        and tier in _LENS_TIERS and isinstance(author, str) and author.strip()
        and ((tier == "asserted" and author in ("operador", "grill"))
             or (tier == "llm_judged" and author in ("edge", "racionalizador")))
    ):
        return False
    thread = payload.get("thread")
    return thread is None or (
        isinstance(thread, dict)
        and all(isinstance(thread.get(field), str) and thread[field].strip()
                for field in ("uuid", "display"))
    )


def _foldable_ticket_open(payload):
    tier, author = payload.get("tier"), payload.get("author")
    return bool(
        isinstance(payload.get("ulid"), str) and payload["ulid"]
        and isinstance(payload.get("num"), str) and re.fullmatch(r"tkt-\d+", payload["num"])
        and isinstance(payload.get("map"), str) and payload["map"]
        and all(isinstance(payload.get(field), str) and payload[field].strip()
                for field in ("titulo", "question", "rationale", "dispatch_id"))
        and tier in _LENS_TIERS and isinstance(author, str) and author.strip()
        # mentor = surface vocabulary (operator 2026-07-13); grill kept for historical pens
        and ((tier == "asserted" and author in ("operador", "grill", "mentor"))
             or (tier == "llm_judged" and author in ("edge", "racionalizador")))
        and isinstance(payload.get("blocked_by", []), list)
        and all(isinstance(ref, str) and ref for ref in payload.get("blocked_by", []))
        and (payload.get("inscricao") is None or isinstance(payload.get("inscricao"), str))
        and (payload.get("annotations") is None or isinstance(payload.get("annotations"), dict))
    )


def _foldable_run_open(payload):
    required = (payload.get("ulid"), payload.get("num"), payload.get("operacao"))
    if not (all(isinstance(value, str) and value for value in required)
            and re.fullmatch(r"run-\d+", payload["num"])
            and _OPERACAO_RE.fullmatch(payload["operacao"])
            and payload.get("tier") in _LENS_TIERS
            and isinstance(payload.get("atividades"), list) and payload["atividades"]
            and all(isinstance(ref, str) and ref for ref in payload["atividades"])
            and isinstance(payload.get("config"), dict) and payload["config"]
            and (payload.get("leva") is None
                 or (isinstance(payload.get("leva"), str)
                     and payload["leva"].strip()))):
        return False
    evaluation = payload.get("eval")
    if not (isinstance(evaluation, dict)
            and isinstance(evaluation.get("metric"), str) and evaluation["metric"].strip()
            and isinstance(evaluation.get("predicao"), str) and evaluation["predicao"].strip()):
        return False
    normalized = {"metric": evaluation["metric"].strip(),
                  "predicao": evaluation["predicao"].strip()}
    expected_hash = hashlib.sha256(json.dumps(
        normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if payload.get("prediction_hash") != expected_hash:
        return False
    if payload["tier"] == "llm_judged" and not (
            isinstance(payload.get("derivation_key"), str)
            and payload["derivation_key"].strip()):
        return False
    return isinstance(payload.get("nao_mede", []), list)


def _foldable_arco_open(payload):
    tier, author = payload.get("tier"), payload.get("author")
    return bool(
        isinstance(payload.get("ulid"), str) and payload["ulid"]
        and isinstance(payload.get("num"), str) and re.fullmatch(r"arc-\d+", payload["num"])
        and isinstance(payload.get("operacao"), str) and _OPERACAO_RE.fullmatch(payload["operacao"])
        and isinstance(payload.get("nome"), str) and payload["nome"].strip()
        and tier in _LENS_TIERS and author in _ACTIVITY_AUTHORS
        and ((tier == "asserted" and author in ("operador", "grill"))
             or (tier == "llm_judged" and author == "racionalizador"))
    )


def _foldable_fact_observed(payload):
    if not (
        isinstance(payload.get("ulid"), str) and payload["ulid"]
        and isinstance(payload.get("num"), str) and re.fullmatch(r"fat-\d+", payload["num"])
        and isinstance(payload.get("operacao"), str) and _OPERACAO_RE.fullmatch(payload["operacao"])
        and isinstance(payload.get("atividade"), str) and payload["atividade"]
        and isinstance(payload.get("body"), str) and payload["body"].strip()
        and payload.get("tier") in _LENS_TIERS
        and (payload.get("run") is None or isinstance(payload.get("run"), str))
        and (payload.get("leva") is None
             or (isinstance(payload.get("leva"), str) and payload["leva"].strip()))
    ):
        return False
    measurement = payload.get("medida")
    return measurement is None or (
        isinstance(measurement, dict) and "valor" in measurement
        and isinstance(measurement.get("como"), str) and measurement["como"].strip()
    )


def _foldable_instrument_failure(payload):
    return all(
        isinstance(payload.get(field), str) and payload[field].strip()
        for field in ("instrumento", "leva", "detalhe")
    )


def _suspect_batches(events):
    return {
        event["payload"]["leva"]
        for event in events
        if isinstance(event, dict) and event.get("type") == "instrumento.falhou"
        and isinstance(event.get("payload"), dict)
        and _foldable_instrument_failure(event["payload"])
    }


def _current_activity_overlay(events):
    """Hide superseded LLM-derived activity rows unless an asserted gesture pinned the grain."""
    events = list(events)
    superseded = {
        payload["supersedes"]
        for event in events if isinstance(event, dict)
        for payload in [event.get("payload")]
        if event.get("type") == "sessao.racionalizada"
        and isinstance(payload, dict)
        and isinstance(payload.get("supersedes"), str)
        and payload["supersedes"]
    }
    if not superseded:
        return events
    derived_grains = {
        payload["ulid"]
        for event in events if isinstance(event, dict)
        for payload in [event.get("payload")]
        if event.get("type") == "atividade.opened"
        and isinstance(payload, dict)
        and payload.get("rationalization_id") in superseded
        and isinstance(payload.get("ulid"), str)
    }
    pinned = {
        payload["ref"]
        for event in events if isinstance(event, dict)
        for payload in [event.get("payload")]
        if event.get("type") in {
            "atividade.touched", "atividade.closed", "atividade.reopened",
            "atividade.bears_on",
        }
        and isinstance(payload, dict)
        and payload.get("tier") == "asserted"
        and payload.get("ref") in derived_grains
    }
    current = []
    for event in events:
        if not isinstance(event, dict):
            current.append(event)
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (event.get("type") == "sessao.racionalizada"
                and payload.get("rationalization_id") in superseded):
            continue
        if payload.get("rationalization_id") in superseded:
            grain = payload.get("ulid") if event.get("type") == "atividade.opened" \
                else payload.get("ref")
            if grain not in pinned:
                continue
        current.append(event)
    return current


def fold_atividades(events):
    """Pure, fail-dark activity fold; conversation-facing keys are full operation/num refs."""
    events = _current_activity_overlay(
        _events_with_embedded_move_effects(_operator_session_overlay(events)))
    activities = {}
    by_ulid = {}
    rationalizations = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "atividade.opened":
            if not _foldable_activity_open(payload):
                continue
            ulid, num = payload.get("ulid"), payload.get("num")
            operacao, finalidade = payload.get("operacao"), payload.get("finalidade")
            if not all(isinstance(value, str) and value for value in
                       (ulid, num, operacao, finalidade)):
                continue
            full_ref = f"{operacao}/{num}"
            item = {
                "ref": full_ref, "ulid": ulid, "num": num, "operacao": operacao,
                "finalidade": finalidade, "eval": payload.get("eval"),
                "arco": payload.get("arco"), "tipo_ref": payload.get("tipo_ref"),
                "estado": "aberta", "fechos": [], "fecho": None, "toques": [],
                "files": [], "enderecos": [], "novo": [], "bears_on": [], "runs": [],
                "fatos": [], "contests": [], "adjudications": [],
                "contested": False, "admissibilidade": None, "tier": payload.get("tier"),
                "sessoes_sem_toque": 0, "_opened_seq": event.get("seq"), "_state_events": [],
                "_arco_events": ([{"arco": payload.get("arco"), "tier": payload.get("tier"),
                                   "seq": event.get("seq") if isinstance(event.get("seq"), int)
                                   else -1}] if isinstance(payload.get("arco"), str) else []),
            }
            activities[full_ref] = item
            by_ulid[ulid] = item
        elif event_type == "atividade.touched":
            item = by_ulid.get(payload.get("ref"))
            sessao = payload.get("sessao")
            if item is None or not isinstance(sessao, str):
                continue
            touch = dict(payload)
            touch.update({"seq": event.get("seq"), "ts": event.get("ts")})
            item["toques"].append(touch)
            novo = payload.get("novo")
            if isinstance(novo, str) and novo:
                item["novo"].append(novo)
            paths = payload.get("files")
            if isinstance(paths, list):
                for path in paths:
                    if isinstance(path, str) and path not in item["files"]:
                        item["files"].append(path)
        elif event_type == "atividade.closed":
            item = by_ulid.get(payload.get("ref"))
            if (item is None or payload.get("estado") not in _ACTIVITY_STATES
                    or payload.get("tier") not in _LENS_TIERS):
                continue
            closure = dict(payload)
            closure.update({"seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
                            "ts": event.get("ts")})
            item["fechos"].append(closure)
            item["fecho"] = max(
                item["fechos"],
                key=lambda candidate: (
                    1 if candidate.get("tier") == "asserted" else 0,
                    candidate.get("seq") if isinstance(candidate.get("seq"), int) else -1,
                ),
            )
            item["_state_events"].append({"estado": closure["estado"],
                                          "tier": closure["tier"], "seq": closure["seq"]})
            item["estado"] = max(
                item["_state_events"],
                key=lambda candidate: (1 if candidate["tier"] == "asserted" else 0,
                                       candidate["seq"]),
            )["estado"]
        elif event_type == "atividade.reopened":
            item = by_ulid.get(payload.get("ref"))
            if (item is None or payload.get("tier") not in _LENS_TIERS
                    or not isinstance(payload.get("motivo"), str)):
                continue
            item["_state_events"].append({
                "estado": "reaberta", "tier": payload["tier"],
                "seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
            })
            item["estado"] = max(
                item["_state_events"],
                key=lambda candidate: (1 if candidate["tier"] == "asserted" else 0,
                                       candidate["seq"]),
            )["estado"]
        elif event_type == "atividade.bears_on":
            item = by_ulid.get(payload.get("ref"))
            if item is None or payload.get("valencia") not in _BEARING_VALENCES:
                continue
            bearing = dict(payload)
            bearing.update({"seq": event.get("seq"), "ts": event.get("ts")})
            item["bears_on"].append(bearing)
        elif event_type == "run.opened":
            if not _foldable_run_open(payload):
                continue
            ulid, num, operation = payload.get("ulid"), payload.get("num"), payload.get("operacao")
            parents = payload.get("atividades")
            if not (isinstance(ulid, str) and isinstance(num, str)
                    and isinstance(operation, str) and isinstance(parents, list)):
                continue
            run_ref = f"{operation}/{num}"
            for parent in parents:
                item = by_ulid.get(parent)
                if item is not None and run_ref not in item["runs"]:
                    item["runs"].append(run_ref)
        elif event_type == "fato.observed":
            if not _foldable_fact_observed(payload):
                continue
            item = by_ulid.get(payload.get("atividade"))
            ulid, num, operation = payload.get("ulid"), payload.get("num"), payload.get("operacao")
            if (item is None or not isinstance(ulid, str) or not isinstance(num, str)
                    or not isinstance(operation, str)):
                continue
            fact_ref = f"{operation}/{num}"
            if fact_ref not in item["fatos"]:
                item["fatos"].append(fact_ref)
        elif event_type == "arco.moved":
            item = by_ulid.get(payload.get("ref"))
            if (item is None or not isinstance(payload.get("arco_novo"), str)
                    or payload.get("tier") not in _LENS_TIERS):
                continue
            item["_arco_events"].append({
                "arco": payload["arco_novo"], "tier": payload["tier"],
                "seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
            })
            item["arco"] = max(
                item["_arco_events"],
                key=lambda candidate: (1 if candidate["tier"] == "asserted" else 0,
                                       candidate["seq"]),
            )["arco"]
        elif event_type == "contest.raised":
            item = by_ulid.get(payload.get("alvo"))
            if (item is None or not isinstance(payload.get("evidencia"), str)
                    or not isinstance(payload.get("detalhe"), str)):
                continue
            contest = dict(payload)
            contest.update({"seq": event.get("seq"), "ts": event.get("ts")})
            item["contests"].append(contest)
            item["contested"] = True
        elif event_type == "contest.adjudicated":
            item = by_ulid.get(payload.get("alvo"))
            if item is None or payload.get("veredito") not in ("mantido", "corrigido"):
                continue
            adjudication = dict(payload)
            adjudication.update({"seq": event.get("seq"), "ts": event.get("ts")})
            item["adjudications"].append(adjudication)
            item["contested"] = False
        elif event_type == "sessao.racionalizada":
            operations = payload.get("operacoes")
            session = payload.get("sessao_id")
            if (isinstance(operations, list) and isinstance(session, str)
                    and isinstance(event.get("seq"), int)):
                rationalizations.append({"seq": event["seq"], "ts": event.get("ts"),
                                         "sessao": session, "operacoes": operations})
            organizational = payload.get("organizacional")
            addresses = organizational.get("enderecos") if isinstance(organizational, dict) else None
            if isinstance(addresses, list):
                for raw_address in addresses:
                    if not isinstance(raw_address, dict):
                        continue
                    activity_ref, path = raw_address.get("atividade"), raw_address.get("path")
                    if isinstance(activity_ref, dict):
                        op, num = activity_ref.get("operacao"), activity_ref.get("num")
                        activity_ref = f"{op}/{num}" if isinstance(op, str) and isinstance(num, str) else None
                    item = (by_ulid.get(activity_ref) if isinstance(activity_ref, str) else None)
                    if item is None and isinstance(activity_ref, str):
                        item = activities.get(activity_ref)
                    if item is None or not (isinstance(path, str) and path.strip()):
                        continue
                    address = dict(raw_address)
                    address.update({"atividade": item["ulid"], "path": path.strip(),
                                    "stale": False, "seq": event.get("seq"),
                                    "ts": event.get("ts"), "sessao": session})
                    for previous in item["enderecos"]:
                        if previous.get("path") != address["path"]:
                            continue
                        hash_changed = (isinstance(previous.get("sha256"), str)
                                        and isinstance(address.get("sha256"), str)
                                        and previous["sha256"] != address["sha256"])
                        stat_changed = (previous.get("stat") is not None
                                        and address.get("stat") is not None
                                        and previous["stat"] != address["stat"])
                        if hash_changed or stat_changed:
                            previous["stale"] = True
                    item["enderecos"].append(address)
                    if address["path"] not in item["files"]:
                        item["files"].append(address["path"])
    session_ts = {row["sessao"]: row["ts"] for row in rationalizations}
    for item in activities.values():
        touched_sessions = {touch["sessao"] for touch in item["toques"]}
        last_touch_seq = max(
            (touch["seq"] for touch in item["toques"] if isinstance(touch.get("seq"), int)),
            default=item.pop("_opened_seq", -1),
        )
        item["sessoes_sem_toque"] = sum(
            1 for row in rationalizations
            if row["seq"] > last_touch_seq
            and item["operacao"] in row["operacoes"]
            and row["sessao"] not in touched_sessions
        )
        for touch in item["toques"]:
            touch["racionalizada_ts"] = session_ts.get(touch["sessao"])
            touch["sessao_racionalizada"] = {
                "ts": session_ts[touch["sessao"]]
            } if touch["sessao"] in session_ts else None
        item.pop("_state_events", None)
        item.pop("_arco_events", None)
    return activities


def atividades_at(seq=None, ts=None, log=LOG):
    """Fold activity events up to a cursor, preserving historical touches and closures."""
    types = ATIVIDADE_TYPES + RUN_TYPES + FATO_TYPES + ARCO_TYPES + CONTEST_TYPES + ["move.ratified"]
    return fold_atividades(read(types=types, until_seq=seq, until_ts=ts, log=log))


def fold_runs(events):
    """Pure run fold keyed by full operation/num refs; corrupt rows do not project."""
    events = _events_with_embedded_move_effects(events)
    suspect_batches = _suspect_batches(events)
    runs = {}
    by_ulid = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "run.opened":
            if not _foldable_run_open(payload):
                continue
            ref = f"{payload['operacao']}/{payload['num']}"
            item = dict(payload)
            item.update({"ref": ref, "primaria": payload["atividades"][0],
                         "fechos": [], "fecho": None, "resultado": None,
                         "admissibilidade": None})
            runs[ref] = item
            by_ulid[payload["ulid"]] = item
        elif event_type == "run.closed":
            item = by_ulid.get(payload.get("ref"))
            if (item is None or payload.get("tier") not in _LENS_TIERS
                    or not isinstance(payload.get("resultado"), str)):
                continue
            closure = dict(payload)
            closure.update({"seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
                            "ts": event.get("ts")})
            item["fechos"].append(closure)
            item["fecho"] = max(
                item["fechos"],
                key=lambda candidate: (1 if candidate.get("tier") == "asserted" else 0,
                                       candidate["seq"]),
            )
            item["resultado"] = item["fecho"]["resultado"]
    for item in runs.values():
        if item.get("leva") in suspect_batches:
            item["admissibilidade"] = "suspeita"
    return runs


def runs_at(seq=None, ts=None, log=LOG):
    """Fold run events up to a seq/UTC timestamp cursor."""
    return fold_runs(read(types=RUN_TYPES, until_seq=seq, until_ts=ts, log=log))


def fold_fatos(events):
    """Pure fact fold keyed by full operation/num refs, including batch admissibility."""
    suspect_batches = _suspect_batches(events)
    facts = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "fato.observed":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if not _foldable_fact_observed(payload):
            continue
        ref = f"{payload['operacao']}/{payload['num']}"
        item = dict(payload)
        item.update({
            "ref": ref,
            "admissibilidade": (
                "suspeita" if payload.get("leva") in suspect_batches else None
            ),
        })
        facts[ref] = item
    return facts


def fatos_at(seq=None, ts=None, log=LOG):
    """Fold fact events up to a seq/UTC timestamp cursor."""
    return fold_fatos(read(types=FATO_TYPES, until_seq=seq, until_ts=ts, log=log))


def fold_arcos(events):
    """Pure arc fold with an amendable, tier-precedent verdict owned by each arc."""
    events = _events_with_embedded_move_effects(events)
    arcs = {}
    by_ulid = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "arco.opened":
            if not _foldable_arco_open(payload):
                continue
            ref = f"{payload['operacao']}/{payload['num']}"
            item = dict(payload)
            item.update({"ref": ref, "fechos": [], "fecho": None,
                         "valencia": None, "julgamento": None})
            arcs[ref] = item
            by_ulid[payload["ulid"]] = item
        elif event_type == "arco.closed":
            item = by_ulid.get(payload.get("ref"))
            if (item is None or payload.get("tier") not in _LENS_TIERS
                    or payload.get("valencia") not in _BEARING_VALENCES):
                continue
            closure = dict(payload)
            closure.update({"seq": event.get("seq") if isinstance(event.get("seq"), int) else -1,
                            "ts": event.get("ts")})
            item["fechos"].append(closure)
            item["fecho"] = max(
                item["fechos"],
                key=lambda candidate: (1 if candidate["tier"] == "asserted" else 0,
                                       candidate["seq"]),
            )
            item["valencia"] = item["fecho"]["valencia"]
            item["julgamento"] = item["fecho"]["julgamento"]
    return arcs


def arcos_at(seq=None, ts=None, log=LOG):
    """Fold arc events up to a seq/UTC timestamp cursor."""
    return fold_arcos(read(types=ARCO_TYPES + ["move.ratified"],
                           until_seq=seq, until_ts=ts, log=log))


def fold_marcos(events):
    """Latest curated stable landmark per operation; malformed pointers fail dark."""
    entities = {entity["ulid"]: entity for entity in _lens_entities(events)}
    landmarks = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "marco.set":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        operation, target_ulid = payload.get("operacao"), payload.get("ref")
        target = entities.get(target_ulid)
        if (not isinstance(operation, str) or target is None
                or target.get("operacao") != operation):
            continue
        landmarks[operation] = {
            "operacao": operation, "ref": target["full"], "ulid": target_ulid,
            "nota": payload.get("nota"), "rationale": payload.get("rationale"),
            "dispatch_id": payload.get("dispatch_id"), "author": payload.get("author"),
            "seq": event.get("seq"), "ts": event.get("ts"),
        }
    return landmarks


def marco_of(operacao, seq=None, ts=None, log=LOG):
    """Return one operation's latest stable landmark, independently of computed frontier."""
    operation = _lens_operacao(operacao)
    return fold_marcos(read(until_seq=seq, until_ts=ts, log=log)).get(operation)


DOC_TYPES = ["doc.injected", "doc.retired", "canon.elected", "canon.retired"]
CANON_KINDS = ("md", "artefato", "experimento", "map")


def fold_docs(events):
    """Pure fold of md-to-mem events (issue #130) → {'live': [...], 'canon': [...]}. Two independent
    tiers over the SAME log, seq order (padrão objective_at/direction_at):

      - `doc.injected` abre um doc VIVO keyed by slug (body verbatim NO evento — replay/prune-safe);
        `doc.retired` o retira da janela sem apagar (o log preserva — I2). Body vive no evento;
        state/docs/<slug>.md é projeção.
      - `canon.elected` marca um objeto {kind: md|artefato|experimento, ref} como canônico;
        `canon.retired` o des-elege. Standing, não carregamento (I8): a janela lê o mark, a
        pesquisa decide o que sobe. NENHUM TTL — duração = canônico até canon.retired.

    Fail-dark sobre log corrompido: um payload não-dict simplesmente não folda (mesmo espírito de
    fold_direction). `slug`/`ref` ausentes = não-foldável."""
    live = {}   # slug -> doc item
    canon = {}  # (kind, ref) -> canon item
    for e in events:
        t = e.get("type")
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if t == "doc.injected":
            slug = p.get("slug")
            if not isinstance(slug, str):
                continue
            live[slug] = {"slug": slug, "body": p.get("body", ""), "threads": p.get("threads") or [],
                          "sha256": p.get("sha256"), "author": p.get("author"), "ts": e.get("ts")}
        elif t == "doc.retired":
            live.pop(p.get("slug"), None)
        elif t == "canon.elected":
            kind, ref = p.get("kind"), p.get("ref")
            if kind not in CANON_KINDS or not isinstance(ref, str):
                continue
            canon[(kind, ref)] = {"kind": kind, "ref": ref, "thread": p.get("thread"),
                                  "ts": e.get("ts")}
        elif t == "canon.retired":
            canon.pop((p.get("kind"), p.get("ref")), None)
    return {"live": list(live.values()), "canon": list(canon.values())}


def docs_at(seq=None, ts=None, log=LOG):
    """Fold md-to-mem events up to a cursor → {'live':[...], 'canon':[...]} (issue #130). Pure:
    replaying to a past cursor reconstructs that past — strategic versioning, as direction_at.
    Empty → {'live': [], 'canon': []}."""
    return fold_docs(read(types=DOC_TYPES, until_seq=seq, until_ts=ts, log=log))


SOURCE_TYPES = ["source.signal"]


def fold_source_yield(events):
    """Pure fold of `source.signal` events → **per-source (ref) yield** (ADR-0009): for each cited
    ref, {ref, kind, count, mean_similarity}. This is the leg the briefing's source-orientation reads
    and the grill consults (per-source yield → a hypothesis agenda item). Returns a dict keyed by ref
    (an empty dict is the sensible empty-case for a dict-returning fold)."""
    by_ref = {}  # ref -> {ref, kind, count, _sum}
    for e in events:
        p = e.get("payload", {}) or {}
        ref = p.get("ref")
        if ref is None:
            continue
        agg = by_ref.setdefault(ref, {"ref": ref, "kind": p.get("kind"), "count": 0, "_sum": 0.0})
        agg["count"] += 1
        agg["_sum"] += p.get("similarity", 0.0)
    return {ref: {"ref": ref, "kind": a["kind"], "count": a["count"],
                  "mean_similarity": a["_sum"] / a["count"]}
            for ref, a in by_ref.items()}


def source_yield_at(seq=None, ts=None, log=LOG):
    """Fold `source.signal` events up to a cursor → per-source yield, a dict keyed by ref (ADR-0009).
    Pure: replaying to a past cursor reconstructs that past yield — strategic versioning, as
    direction_at/corpus_at. Returns {} when there are no source signals yet."""
    return fold_source_yield(read(types=SOURCE_TYPES, until_seq=seq, until_ts=ts, log=log))


SOURCE_CURATED_TYPES = ["source.curated", "source.dropped"]
SOURCE_FEEDBACK_TYPES = SOURCE_TYPES + SOURCE_CURATED_TYPES


def integrate_artefato_source(slug, reviewer, note="", log=LOG):
    """B.3 (ticket B) — o ATO: um artefato publicado, quando INTEGRADO, vira uma source (o edge
    se aterra na própria obra). Writes são ACTS: este é um evento de integração HITL/autoridade
    (`review_approved`, authority=reviewer — reviewer≠asserter), NUNCA automático: exige o
    reviewer NOMEADO e recusa um slug que nunca publicou neste log. Zero tipo novo de nó — o
    fold (`integrated_sources_at`) só marca o slug como integrado; o pool/curadoria lê dali."""
    if not (isinstance(reviewer, str) and reviewer.strip()):
        raise ValueError(
            f"cannot integrate artefato {slug!r} as a source without a NAMED reviewer "
            "authority (B.3: HITL — review_approved{authority:reviewer}, nunca automático)")
    published = {e["payload"].get("slug")
                 for e in read(types=["artefato.published"], log=log)
                 if isinstance(e.get("payload"), dict)}
    if slug not in published:
        raise ValueError(
            f"cannot integrate {slug!r}: no artefato.published with that slug on this log "
            "(só a obra publicada vira source)")
    return append("artefato.integrated", f"artefato:{slug}",
                  {"slug": slug, "review_approved": True, "authority": "reviewer",
                   "reviewer": reviewer.strip(), "note": note}, log=log)


def fold_integrated_sources(events):
    """Pure fold de `artefato.integrated` → {slug: {reviewer, note, ts}} (o pool de obra-integrada
    que a curadoria/gather lê). Tolerante à casa: payload não-dict, slug vazio ou um evento sem
    review_approved=True é pulado, nunca crasha. Última integração ganha (re-integração é rara e
    idempotente no efeito)."""
    out = {}
    for e in events:
        if e.get("type") != "artefato.integrated":
            continue
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        if (isinstance(slug, str) and slug.strip()
                and p.get("review_approved") is True):
            out[slug] = {"reviewer": p.get("reviewer"), "note": p.get("note"),
                         "ts": e.get("ts")}
    return out


def integrated_sources_at(seq=None, ts=None, log=LOG):
    """O pool de artefatos-integrados-como-source até um cursor (replay puro, como corpus_at)."""
    return fold_integrated_sources(
        read(types=["artefato.integrated"], until_seq=seq, until_ts=ts, log=log))


# ---------------------------------------------------------------------------
# Ticket A — episteme nativo (ontologia-cortex-v2 §1-§3): a caneta da hipótese.
# thread=hipótese=artefato é CORRESPONDÊNCIA (3 nós, 2-hop), nunca identidade — a hipótese é
# o claim falsificável de 1ª classe; o :Artefato é o render que a suporta/refuta via bears_on.
# ---------------------------------------------------------------------------

HYPOTHESIS_TYPES = ["hypothesis.declared", "hypothesis.superseded"]
_FALSIFIER_DIRECTIONS = ("maior", "menor")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid():
    """A minimal ULID (O-2: the primary key): 48-bit ms timestamp + 80 random bits, Crockford
    base32, 26 chars, lexically time-sortable. Stdlib-only — no dependency for 6 lines."""
    n = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 31])
        n >>= 5
    return "".join(reversed(chars))


def _validated_falsifier(falsifier):
    """HIP-1 LOUD: the falsifier must be STRUCTURED and machine-comparable — a dict with a
    non-blank `metric`, a FINITE numeric `threshold` (bool is not a number), and `direction`
    ∈ {maior, menor}. Prose-only / missing / malformed RAISES; returns ONLY the three canonical
    keys (junk — e.g. a smuggled `verdict` — never persists; verdicts are never stored)."""
    if not isinstance(falsifier, dict):
        raise ValueError(
            "hypothesis falsifier must be STRUCTURED {metric, threshold, direction} — "
            "a prose-only falsifier is refused (HIP-1 LOUD)")
    metric, threshold, direction = (falsifier.get("metric"), falsifier.get("threshold"),
                                    falsifier.get("direction"))
    if not (isinstance(metric, str) and metric.strip()):
        raise ValueError("hypothesis falsifier needs a non-blank string `metric` (HIP-1)")
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)):
        raise ValueError("hypothesis falsifier needs a FINITE numeric `threshold` (HIP-1)")
    if direction not in _FALSIFIER_DIRECTIONS:
        raise ValueError(
            f"hypothesis falsifier `direction` must be one of {_FALSIFIER_DIRECTIONS} (HIP-1)")
    return {"metric": metric.strip(), "threshold": threshold, "direction": direction}


def declare_hypothesis(statement, falsifier, slug=None, author=None, log=LOG):
    """The hypothesis pen (HIP-1): append `hypothesis.declared` — the falsifiable claim as a
    first-class, IMMUTABLE, versioned entity (O-4: changing it = declare a NEW one +
    supersede_hypothesis, never an edit). ULID primary key (O-2); `content_hash` of the
    canonical JSON of statement+falsifier secondary (O-3 dedup). The structured falsifier is
    validated LOUD — prose-only never lands. `slug` is display-only, never a key."""
    if not (isinstance(statement, str) and statement.strip()):
        raise ValueError("cannot declare a hypothesis with an empty/non-string statement")
    statement = statement.strip()
    f = _validated_falsifier(falsifier)
    blob = json.dumps({"statement": statement, "falsifier": f},
                      sort_keys=True, ensure_ascii=False)
    ulid = _ulid()
    return append("hypothesis.declared", f"hypothesis:{ulid}",
                  {"ulid": ulid, "slug": slug, "statement": statement, "falsifier": f,
                   "content_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
                   "author": author}, log=log)


def supersede_hypothesis(old, new, log=LOG):
    """Version a hypothesis (O-4): append `hypothesis.superseded` linking old→new. Both ulids
    must have been DECLARED on this log (a link to a hypothesis that never existed is refused),
    and old ≠ new. The graph projects it as (new)-[:SUPERSEDES]->(old) — same label as the
    artefato lineage, new endpoint pair, no new edge type."""
    if old == new:
        raise ValueError(f"cannot supersede hypothesis {old!r} with itself")
    declared = {e["payload"].get("ulid")
                for e in read(types=["hypothesis.declared"], log=log)
                if isinstance(e.get("payload"), dict)}
    for u in (old, new):
        if u not in declared:
            raise ValueError(
                f"cannot supersede: no hypothesis.declared with ulid {u!r} on this log")
    return append("hypothesis.superseded", f"hypothesis:{old}",
                  {"old": old, "new": new}, log=log)


def fold_hypotheses(events):
    """Pure fold of `hypothesis.declared/superseded` → {ulid: hypothesis}. Each carries the
    declared fields + `superseded_by` (None while live). NO stored verdict/status anywhere —
    a hypothesis's standing is derived at read (with only lead bearings it can only ever be
    open/saturated_leads; ontologia §2b). Malformed payloads are skipped, never crash."""
    hyps = {}
    for e in events:
        t, p = e.get("type"), e.get("payload")
        if not isinstance(p, dict):
            continue
        if t == "hypothesis.declared":
            ulid = p.get("ulid")
            if isinstance(ulid, str) and ulid:
                hyps[ulid] = {"ulid": ulid, "slug": p.get("slug"),
                              "statement": p.get("statement"),
                              "falsifier": p.get("falsifier"),
                              "content_hash": p.get("content_hash"),
                              "author": p.get("author"), "created_at": e.get("ts"),
                              "superseded_by": None}
        elif t == "hypothesis.superseded" and p.get("old") in hyps:
            hyps[p["old"]]["superseded_by"] = p.get("new")
    return hyps


def hypotheses_at(seq=None, ts=None, log=LOG):
    """The declared hypotheses up to a cursor (pure replay, as corpus_at). {} when none."""
    return fold_hypotheses(read(types=HYPOTHESIS_TYPES, until_seq=seq, until_ts=ts, log=log))


# --- Native Experiments: curated-first scientific memory (#88/#107) --------------------------

EXPERIMENT_TYPES = ["experiment.declared", "experiment.curated"]
EXPERIMENT_TYPED_FIELDS = ("claim", "scope", "status", "caveat", "supports", "excludes", "next")
EXPERIMENT_KINDS = ("domain", "meta")
_EXPERIMENT_NUMBER_RE = re.compile(r"^exp([0-9]+)$")


def _validated_experiment_typed(typed):
    if not isinstance(typed, dict):
        raise ValueError("experiment canonical conclusion needs a typed dict")
    missing = [k for k in EXPERIMENT_TYPED_FIELDS if k not in typed]
    if missing:
        raise ValueError(f"experiment typed conclusion missing fields: {', '.join(missing)}")
    out = {}
    for k in ("claim", "scope", "status", "caveat", "next"):
        v = typed.get(k)
        if not (isinstance(v, str) and v.strip()):
            raise ValueError(f"experiment typed field {k!r} must be a non-blank string")
        out[k] = v.strip()
    for k in ("supports", "excludes"):
        v = typed.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError(f"experiment typed field {k!r} must be a list of non-blank strings")
        out[k] = [x.strip() for x in v]
    return out


def _validated_canonical_artifacts(canonical_artifacts):
    if not isinstance(canonical_artifacts, list) or not canonical_artifacts:
        raise ValueError("experiment curation needs at least one canonical audit artifact")
    out = []
    for a in canonical_artifacts:
        if not isinstance(a, dict):
            raise ValueError("experiment canonical artifacts must be dicts")
        ref, role = a.get("ref"), a.get("role")
        if not (isinstance(ref, str) and ref.strip()):
            raise ValueError("experiment canonical artifact needs a non-blank ref")
        if not (isinstance(role, str) and role.strip()):
            raise ValueError("experiment canonical artifact needs a non-blank role")
        item = {"ref": ref.strip(), "role": role.strip()}
        if isinstance(a.get("note"), str) and a["note"].strip():
            item["note"] = a["note"].strip()
        out.append(item)
    return out


def _normalized_experiment_id(experiment_id):
    if not (isinstance(experiment_id, str) and experiment_id.strip()):
        raise ValueError("experiment_id must be a canonical non-blank id like exp001")
    clean = experiment_id.strip()
    if not EXPERIMENT_ID_RE.fullmatch(clean):
        raise ValueError(
            f"experiment_id {experiment_id!r} is not canonical; use exp + digits, e.g. exp001")
    return clean


def next_experiment_id(log=LOG):
    """Return the next canonical experiment id (`expNNN`) visible in the log.

    Backward-compatible with historical ids such as `exp40`: the numeric suffix participates in
    the sequence, while newly allocated ids are zero-padded to at least three digits.
    """
    max_n = 0
    for e in read(types=EXPERIMENT_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        eid = p.get("experiment_id")
        if not isinstance(eid, str):
            continue
        m = _EXPERIMENT_NUMBER_RE.fullmatch(eid.strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"exp{max_n + 1:03d}"


def declare_experiment(title, *, experiment_id=None, kind="domain", hypothesis=None, scope=None, owner=None,
                       workspace=True,
                       decision_rule=None, arms=None, status="declared", by=None,
                       relates=None, log=LOG):
    """Declare a first-class Experiment and assign its stable canonical id (#107).

    This is the lightweight native pen: it creates the navigable Experiment object before the
    report exists. Finalization still happens through a report carrying `reports_on` and
    `experiment_curation`; declaration only names the object, records the decision-bearing
    uncertainty, and reserves the id.

    Numbering rule (#109): every decision-bearing Experiment consumes the global `expNNN`
    sequence, including meta-experiments about the Edge/reporting/eval process (`kind="meta"`).
    Arms, runs, report iterations and feedback passes do not consume global experiment numbers;
    record them under `arms`/future run events or as `relates` on the parent Experiment.
    """
    _require_body(title, "experiment.declared (title)")
    eid = _normalized_experiment_id(experiment_id) if experiment_id is not None else next_experiment_id(log)
    if kind not in EXPERIMENT_KINDS:
        raise ValueError(f"experiment.declared kind must be one of {EXPERIMENT_KINDS}")
    if arms is None:
        arms = []
    if not isinstance(arms, list):
        raise ValueError("experiment.declared arms must be a list")
    if relates is None:
        relates = []
    if not isinstance(relates, list) or not all(isinstance(x, dict) for x in relates):
        raise ValueError("experiment.declared relates must be a list of dicts")
    payload = {
        "experiment_id": eid,
        "kind": kind,
        "title": title.strip(),
        "hypothesis": hypothesis.strip() if isinstance(hypothesis, str) and hypothesis.strip() else None,
        "scope": scope.strip() if isinstance(scope, str) and scope.strip() else None,
        "owner": owner.strip() if isinstance(owner, str) and owner.strip() else None,
        "decision_rule": (decision_rule.strip()
                          if isinstance(decision_rule, str) and decision_rule.strip()
                          else decision_rule if isinstance(decision_rule, dict) else None),
        "arms": arms,
        "status": status.strip() if isinstance(status, str) and status.strip() else "declared",
        "by": by.strip() if isinstance(by, str) and by.strip() else None,
        "relates": relates,
    }

    def _unique_id():
        if eid in fold_experiments(read(types=EXPERIMENT_TYPES, log=log)):
            raise ValueError(f"experiment_id {eid!r} already exists")

    event = append_batch([("experiment.declared", f"experiment:{eid}", payload)],
                         log=log, precondition=_unique_id)[0]
    # Genotype disk workspace (experiments/<expNNN>-slug/) — phenotype root from agent.yaml.
    # Ledger remains source of truth; folder is the re-runnable analysis unit.
    # Only seed when writing the install's canonical log (hermetic tests use temp logs).
    if workspace and Path(log).resolve() == Path(LOG).resolve():
        try:
            import experiments_cfg
            experiments_cfg.ensure_experiment_workspace(
                eid,
                title=title.strip(),
                hypothesis=payload.get("hypothesis"),
            )
        except Exception:
            # Never fail the pen if the filesystem cannot be seeded (read-only CI, etc.).
            pass
    return event


def curate_experiment(experiment_id, *, prose, typed, canonical_artifacts, by, relates=None, log=LOG):
    """Append an explicit `experiment.curated` event.

    Native Experiments are self-memory, not external folders to dig: the read side returns a short
    curated interpretation first, with typed fields in the same atomic event, and only a compact set
    of canonical artifacts for audit. Automated sweep/recall may surface candidates, but promotion
    into this event is explicit curation (`by` is mandatory).
    """
    _require_body(experiment_id, "experiment.curated (experiment_id)")
    _require_body(by, "experiment.curated (by)")
    payload = normalize_experiment_curation(
        [experiment_id],
        {"prose": prose, "typed": typed, "canonical_artifacts": canonical_artifacts,
         "by": by, "relates": relates or []},
        by=by)[0]
    return append("experiment.curated", f"experiment:{experiment_id.strip()}", payload, log=log)


def fold_experiments(events):
    """Pure fold of Experiment declarations/curations → declared object + canonical conclusion.

    Latest curation is the current canonical conclusion for that experiment. Prior curations remain
    in `curation_chain`; contradictions are preserved as events/relations instead of overwritten
    inside one mutable summary.
    """
    experiments = {}
    for e in events:
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        eid = p.get("experiment_id")
        if not isinstance(eid, str) or not eid.strip():
            continue
        cur = experiments.setdefault(eid, {"experiment_id": eid, "curation_chain": []})
        if e.get("type") == "experiment.declared":
            cur.update({
                "title": p.get("title"),
                "kind": p.get("kind") if p.get("kind") in EXPERIMENT_KINDS else "domain",
                "hypothesis": p.get("hypothesis"),
                "scope": p.get("scope"),
                "owner": p.get("owner"),
                "decision_rule": p.get("decision_rule"),
                "arms": p.get("arms") or [],
                "status": p.get("status") or "declared",
                "declared_by": p.get("by"),
                "declared_ts": e.get("ts"),
                "declared_seq": e.get("seq"),
                "relates": p.get("relates") or cur.get("relates") or [],
            })
            cur.setdefault("canonical", {})
            cur.setdefault("canonical_artifacts", [])
            cur["ts"] = e.get("ts")
            cur["seq"] = e.get("seq")
        elif e.get("type") == "experiment.curated":
            item = {
                "seq": e.get("seq"),
                "ts": e.get("ts"),
                "by": p.get("by"),
                "canonical": p.get("canonical") or {},
                "canonical_artifacts": p.get("canonical_artifacts") or [],
                "relates": p.get("relates") or [],
            }
            cur["curation_chain"].append(item)
            cur["canonical"] = item["canonical"]
            cur["canonical_artifacts"] = item["canonical_artifacts"]
            cur["by"] = item["by"]
            cur["ts"] = item["ts"]
            cur["seq"] = item["seq"]
            cur["relates"] = item["relates"]
            typed = (item["canonical"].get("typed")
                     if isinstance(item.get("canonical"), dict) else None)
            if isinstance(typed, dict) and typed.get("status"):
                cur["status"] = typed["status"]
            else:
                cur["status"] = cur.get("status") or "curated"
    return experiments


def experiments_at(seq=None, ts=None, log=LOG):
    """Fold native Experiment curations up to a cursor. Empty → {}."""
    return fold_experiments(read(types=EXPERIMENT_TYPES, until_seq=seq, until_ts=ts, log=log))


def experiment_at(experiment_id, seq=None, ts=None, log=LOG):
    """Read one native Experiment by id/alias key from the curated-first fold. None when absent."""
    if not isinstance(experiment_id, str):
        return None
    return experiments_at(seq=seq, ts=ts, log=log).get(experiment_id.strip())


# --- §6 parceiro: a constelação social — PROMOTION, never minting. The extracted :Entity
# (graphiti already found "Julio") GAINS the parceiro mark; the graph node is never created here.

PARCEIRO_KINDS = ("empresa", "pesquisador", "equipe", "git-user")


def promote_parceiro(name, kind, *, by, domain=None, contact_ref=None, log=LOG):
    """§6 pen — promote an extracted Entity-person to `parceiro` (asserted, HITL: the promoting
    authority is NAMED, mirror of integrate_artefato_source). Refuses a blank name, an
    out-of-enum kind, or a missing authority. The projection MATCHes the existing :Entity and
    marks it — promotion, not minting: an Entity graphiti never extracted stays unmarked."""
    if not (isinstance(name, str) and name.strip()):
        raise ValueError("cannot promote a parceiro without a non-blank name")
    if kind not in PARCEIRO_KINDS:
        raise ValueError(f"parceiro kind must be one of {PARCEIRO_KINDS}, got {kind!r}")
    if not (isinstance(by, str) and by.strip()):
        raise ValueError(
            "cannot promote a parceiro without a NAMED promoting authority (§6: HITL — "
            "asserted-by-someone, nunca automático)")
    return append("parceiro.promoted", f"parceiro:{name.strip()}",
                  {"name": name.strip(), "kind": kind, "by": by.strip(), "domain": domain,
                   "contact_ref": contact_ref, "provenance_class": "asserted"}, log=log)


def fold_parceiros(events):
    """Pure fold of `parceiro.promoted` → {name: {kind, by, domain, contact_ref, ts}}. Last
    promotion wins (re-promotion updates the kind/domain). Malformed payloads are skipped."""
    out = {}
    for e in events:
        if e.get("type") != "parceiro.promoted":
            continue
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if isinstance(name, str) and name.strip():
            out[name] = {"name": name, "kind": p.get("kind"), "by": p.get("by"),
                         "domain": p.get("domain"), "contact_ref": p.get("contact_ref"),
                         "ts": e.get("ts")}
    return out


def parceiros_at(seq=None, ts=None, log=LOG):
    """The promoted parceiros up to a cursor (pure replay, as corpus_at). {} when none."""
    return fold_parceiros(read(types=["parceiro.promoted"], until_seq=seq, until_ts=ts, log=log))


def source_curated(source, opinion, kind=None, log=LOG):
    """Append a `source.curated` event (ADR-0011, source-feedback curated tier) — the grill-distilled
    mentee opinion about a source ("values X because Y"). A **separate** event the non-curated signal
    *prompts*, never a promotion (a measurement cannot become an opinion). Curated **outranks** the
    yield, is exempt from passive aging, retirable only by Voz (source_dropped). Latest wins per source.
    A blank source/opinion is refused LOUD — the opinion is reasoned by contract, never hollow."""
    _require_body(source, "source.curated (source)")
    _require_body(opinion, "source.curated (opinion)")
    return append("source.curated", f"source:{source}",
                  {"source": source, "opinion": opinion, "kind": kind}, log=log)


def source_dropped(source, reason="", log=LOG):
    """Append a `source.dropped` event — retire a curated source opinion (Voz only). The only way a
    curated source entry leaves (persist-until-dropped, mirroring direction.dropped)."""
    _require_body(source, "source.dropped (source)")
    return append("source.dropped", f"source:{source}", {"source": source, "reason": reason}, log=log)


def fold_source_feedback(events):
    """Pure two-tier fold of source-feedback events (ADR-0011), mirroring fold_direction (set over
    proposed). The **curated** tier folds `source.curated`/`source.dropped` per source — latest opinion
    wins, dropped removes it (Voz-only); it **outranks** the non-curated yield (no promotion — curated
    is a separate event the signal prompts). The **non-curated** tier is the mechanical per-ref yield
    (fold_source_yield over source.signal). Returns {"curated": [...], "non_curated": {ref: {...}}}."""
    curated = {}  # source -> {source, opinion, kind}
    for e in events:
        t, p = e.get("type"), e.get("payload", {}) or {}
        if t == "source.curated":
            src = p.get("source")
            if src is None:
                continue
            curated[src] = {"source": src, "opinion": p.get("opinion", ""), "kind": p.get("kind")}
        elif t == "source.dropped":
            curated.pop(p.get("source"), None)
    return {"curated": list(curated.values()),
            "non_curated": fold_source_yield([e for e in events if e.get("type") == "source.signal"])}


def source_feedback_at(seq=None, ts=None, log=LOG):
    """Fold source-feedback events up to a cursor → two tiers (ADR-0011): {"curated":[...],
    "non_curated":{ref:{...}}}, curated outranking. Pure: replaying to a past cursor reconstructs that
    past feedback — strategic versioning, as direction_at. Empty → {"curated":[], "non_curated":{}}."""
    return fold_source_feedback(read(types=SOURCE_FEEDBACK_TYPES, until_seq=seq, until_ts=ts, log=log))


# S1 (grounding iteration) — the event family (R2.3: persisted in the house style, new Tier-0
# types + pure folds). `grounding.manifest` = one recognized READ (the attempt row, E2b shape);
# `grounding.finding` = the dig's durable achado (E4: the topic file is a projection of it);
# `canary.result` = one instrument attestation per source×interface (R2.5); `grounding.floor_dark`
# = the close's floor could not see a transcript (E7: counted, never silent); `grounding.unmanifested`
# = the blind-leg tally for network-shaped calls no recognizer claimed (enxerto B2).
# `grounding.dark` = an operator/agent-DECLARED seca (a source swept, came back empty) — the honest
# negative-evidence declaration (aquisicao.declare_dark); it IS lastro, so it rides the family
# (readable), but it is NOT a manifest attempt, so it stays OUT of GROUNDING_FOLD_TYPES.
GROUNDING_TYPES = ["grounding.manifest", "grounding.finding", "canary.result",
                   "grounding.floor_dark", "grounding.floor", "grounding.unmanifested",
                   "grounding.dark"]
# fold_grounding consumes ONLY these two: manifests are the attempts, canary.result is what the
# two-factor dry projection (B1) joins. finding/floor_dark/unmanifested have their own consumers
# in later slices (S4-S7) — feeding them here would conflate attempts with tallies.
GROUNDING_FOLD_TYPES = ["grounding.manifest", "canary.result"]

# B1 two-factor TTL: a born-suspect dry read is projected `verificada` only by a canary pass for
# the SAME source×interface landing AT-OR-AFTER the read and within this window. 6h = 2× the 3h
# heartbeat: the canary runs at the very NEXT predispatch (design-emissao §2), so two beats of
# slack tolerate one skipped wake; a pass later than that attests a DIFFERENT instrument state
# (auth/quota/index drift on the hours scale — the measured failure modes of R2.5), so the read
# stays suspect (R2.4: seca sem canário = suspeita; a too-late canário is no canário).
GROUNDING_CANARY_TTL_S = 6 * 3600

# the dry labels that make a row seca-suspeita — excluded from learning (R4.2), counted by reason
_GROUNDING_SUSPECT_LABELS = ("suspect", "suspect:instrumento", "suspect:overspecified")
# attribution tiers excluded from learning (design-emissao §3: only mapped/declared feed the
# bandit — uncertain attribution is instrument bias exactly like seca-suspeita)
_GROUNDING_EXCLUDED_ATTRIBUTION = ("inferred", "unknown")


def _raw_ref_key(v):
    """A usable raw_ref = EXACTLY the E2b 4-tuple — (session_id, transcript_line_offset,
    tool_use_id, occurrence_index) — folded to a tuple so it can key the dedup. The raw_ref is
    the BRUTE occurrence: location, never interpretation, so a corrected recognizer never moves
    the key and `supersedes` always finds its target. Arity is part of the identity (codex S1
    gate D4): a 3-field ref is a DIFFERENT, incompatible key — folding it as valid would let two
    emitters of the same occurrence miss each other's dedup. The SHAPE is semantic, per field
    (codex round-4): session_id and tool_use_id non-empty str, transcript_line_offset and
    occurrence_index non-bool int — because True == 1 in Python, a bool in a numeric field would
    silently COLLAPSE two occurrences into one dedup key (["s", True, "t", 0] == ["s", 1, "t", 0])
    with corrupt never counted. Anything else is corrupt → None (fail-dark, the same tolerance
    as fold_direction's _key)."""
    def _iid(x):  # an identity int: non-bool int (True==1 must never key an occurrence)
        return isinstance(x, int) and not isinstance(x, bool)
    if (isinstance(v, (list, tuple)) and len(v) == 4
            and isinstance(v[0], str) and v[0]
            and _iid(v[1])
            and isinstance(v[2], str) and v[2]
            and _iid(v[3])):
        return tuple(v)
    return None


def _grounding_ts(v):
    """Parse an event ts for the canary-TTL join; a corrupt/missing ts → None (no join is ever
    fabricated from an unreadable clock — the row just stays suspect, fail-dark)."""
    try:
        return datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _event_seq(event):
    """A COMPARABLE seq for the MAX-direction orderings of the grounding fold — the supersede
    rank and the final aggregation sort. A corrupt/missing/non-numeric seq ranks 0 (codex S1
    round-3 B2: sorting on raw seqs TypeErrors the canonical fold when one row carries
    `seq: "bad"` beside a numeric one — fail-dark, never a raise).

    Direction rule, stated once (codex round-5): CORRUPT MUST LOSE UNDER BOTH DIRECTIONS. Rank-0
    loses under max() but would WIN under min() — so this helper is only safe where the best
    rank is the LARGEST. The canary join tie-breaks by min(delta_ts, seq); there a canary with a
    non-numeric seq is rejected as non-attesting (counted corrupt) instead of normalized, so a
    corrupt pass can never outrank a valid fail at equal timestamps and mint verificada."""
    seq = event.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, (int, float)):
        return 0
    return seq


def _supersede_rank(payload, event):
    """The E2b deterministic rank for competing interpretations of one raw_ref — the ORIGINAL
    row included (codex S1 gate D1): max (recognizer_rev, seq) wins, so a better recognizer
    outranks a later emission of a worse one, equal revs fall back to last-wins by seq, and a
    worse/corrupt reinterpretation NEVER defeats a healthier original (supersedes versions the
    interpretation, it is not an unconditional overwrite). A missing/non-numeric rev ranks -1
    (below any real one); seq comparability via _event_seq — deterministic fail-dark, never a raise."""
    rev = payload.get("recognizer_rev")
    if isinstance(rev, bool) or not isinstance(rev, (int, float)):
        rev = -1
    return (rev, _event_seq(event))


def _canary_for(row_event, source, interface, canaries):
    """The canary a born-suspect row joins (B1): same source×interface, landing at-or-after the
    read within GROUNDING_CANARY_TTL_S (INCLUSIVE at the boundary). Among joinable attestations
    the CLOSEST at-or-after wins — min (delta_ts, seq) — because the design's flow is dry-read →
    NEXT-predispatch canary (codex S1 gate D2): a later pass must never retro-verify a read whose
    NEAREST attestation failed (the recovery attests the instrument NOW, not what the read saw).
    None when nothing joins: an earlier canary proves nothing about what the read saw (the
    failure could have started in between), a later-than-TTL one attests a different instrument
    state, and a ROW without a named source×interface can never join at all (codex round-3 B3 +
    round-4: None dims must not meet a keyless canary's None dims and mint verificada for an
    unknown source, and a WHITESPACE-only name is as keyless as a missing one — the join key is
    the identity, absent identity = no join)."""
    if not (isinstance(source, str) and source.strip()
            and isinstance(interface, str) and interface.strip()):
        return None
    ts0 = _grounding_ts(row_event.get("ts"))
    if ts0 is None:
        return None
    joinable = []
    for c in canaries:
        if c["source"] != source or c["interface"] != interface or c["ts"] is None:
            continue
        try:
            delta = (c["ts"] - ts0).total_seconds()
        except TypeError:
            continue  # mixed aware/naive timestamps cannot be compared — no fabricated join
        if 0 <= delta <= GROUNDING_CANARY_TTL_S:
            joinable.append((delta, c["seq"], c))
    return min(joinable, key=lambda t: (t[0], t[1]))[2] if joinable else None


def _dry_label(row_event, payload, hits, source, interface, canaries):
    """The dry taxonomy of ONE row (B1 + R2.4). A row is a dry read when it was born marked
    `dry: suspect` OR measured 0 hits (hits None is UNKNOWN, never dry — instrument blindness
    does not fabricate a seca). `seca-verificada` is NEVER read off the row (design-emissao §2:
    it is a fold that joins suspect ↔ canary, keeping append-only intact): `verificada` needs
    BOTH factors — canary pass AND idiom_conforme True on the row; canary fail →
    `suspect:instrumento`; canary pass + idiom VIOLATED (`idiom_conforme is False`) →
    `suspect:overspecified` (the measured X case: 200+empty on an over-specified query is not
    health); an ABSENT/non-bool idiom flag attests NEITHER second-factor branch → stays bare
    `suspect` (codex round-3 B1: not-attested is not a violation — the same anti-coercion rule
    as the canary pass). `dry_semantics: never-dry` (Exa — the risk is confident filler, not
    dryness) → `nao-aplicavel`. Not dry → None."""
    if not (payload.get("dry") == "suspect" or hits == 0):
        return None
    if payload.get("dry_semantics") == "never-dry":
        return "nao-aplicavel"
    canary = _canary_for(row_event, source, interface, canaries)
    if canary is None:
        return "suspect"
    if not canary["passed"]:
        return "suspect:instrumento"
    if payload.get("idiom_conforme") is True:
        return "verificada"
    if payload.get("idiom_conforme") is False:
        return "suspect:overspecified"
    return "suspect"


def winning_manifest_rows(events):
    """The ONE dedup/supersede + canary reader (E2b) — the shared front half of `fold_grounding`
    and `grounding_yield` (the near-identical logic used to live in BOTH and must not drift).
    Pure, no I/O. → (rows, canaries, corrupt):

    `rows` = the WINNING (event, payload) manifest per BRUTE raw_ref, seq-sorted. FIRST emission
    wins per raw_ref (the log is append-only with no write-side dedupe — a cursor reset /
    retro-harvest re-emits, and the re-emission must be a no-op HERE, not prevented there). A row
    carrying `supersedes: <raw_ref>` REINTERPRETS that occurrence — the winner among the ORIGINAL
    and its reinterpretations is max (recognizer_rev, seq) (gate D1: a worse/corrupt recognizer
    never defeats a healthier original), so the raw history is never rewritten, the
    interpretation is versioned.

    `canaries` = the interpreted `canary.result` attestations, in log order.

    `corrupt` = the tally of rows that could not be interpreted — a corrupt manifest/canary is
    COUNTED, never raised and never silently dropped (fold_grounding surfaces it; the yield fold
    discards it — its excluded shape has no corrupt leg)."""
    corrupt = 0
    canaries = []   # interpreted canary.result attestations, in seq order
    plain = {}      # raw_ref -> (event, payload) of its FIRST emission
    supers = {}     # raw_ref -> [(event, payload)] reinterpretations targeting it
    for e in events:
        t = e.get("type")
        payload = e.get("payload")
        p = payload if isinstance(payload, dict) else None
        if t == "canary.result":
            ok = p.get("pass") if p is not None else None
            src = p.get("source") if p is not None else None
            iface = p.get("interface") if p is not None else None
            seq = e.get("seq")
            if ((ok is not True and ok is not False)
                    or not (isinstance(src, str) and src.strip()
                            and isinstance(iface, str) and iface.strip())
                    or isinstance(seq, bool) or not isinstance(seq, (int, float))):
                # codex S1 gate D3 + round-3 B3 + round-4 + round-5: only a REAL boolean from a
                # NAMED source×interface with an ORDERABLE seq attests — bool("false") is True
                # (a coerced pass could project verificada off a FAILED canary), a keyless or
                # whitespace-keyed canary could match a keyless row's None dims, and a
                # non-numeric seq cannot be ranked in the join's min() tie-break (normalizing it
                # to 0 would make corrupt WIN under min() what it loses under max() — see
                # _event_seq's direction rule). A non-attesting canary is counted corrupt
                # (visible degradation) and the rows it would have joined just stay suspect.
                corrupt += 1
                continue
            canaries.append({"source": src, "interface": iface, "passed": ok,
                             "ts": _grounding_ts(e.get("ts")), "seq": seq})
        elif t == "grounding.manifest":
            if p is None:
                corrupt += 1
                continue
            if "supersedes" in p:
                target = _raw_ref_key(p.get("supersedes"))
                if target is None:
                    # an unusable target can neither reinterpret nor be trusted as a fresh
                    # first emission (its raw_ref IS its target per E2b) — counted, not folded
                    corrupt += 1
                    continue
                supers.setdefault(target, []).append((e, p))
                continue
            ref = _raw_ref_key(p.get("raw_ref"))
            if ref is None:
                corrupt += 1
                continue
            plain.setdefault(ref, (e, p))  # first emission wins; re-harvests are no-ops
    rows = []
    for ref in set(plain) | set(supers):
        # the ORIGINAL row competes on the same (recognizer_rev, seq) rank as its
        # reinterpretations (codex S1 gate D1): a supersede with a worse/corrupt rev must NOT
        # defeat a healthier original — that would be the exact inversion E2b forbids
        # (supersedes versions the interpretation, it is not an unconditional overwrite).
        contenders = list(supers.get(ref, ()))
        if ref in plain:
            contenders.append(plain[ref])
        rows.append(max(contenders, key=lambda ep: _supersede_rank(ep[1], ep[0])))
    # _event_seq, not raw seq (codex round-3 B2): a corrupt `seq: "bad"` beside a numeric one
    # would TypeError this sort — the fold is fail-dark, never a raise
    return sorted(rows, key=lambda ep: _event_seq(ep[0])), canaries, corrupt


def fold_grounding(events):
    """Pure fold of `{grounding.manifest, canary.result}` events → the grounding attempts table
    (R2.3/R4.1: the DENOMINATOR the yield join consumes; the instrument-health strip the panel
    renders). No I/O, tolerant like fold_direction: a corrupt manifest is COUNTED (`corrupt`),
    never raised and never silently dropped.

    Identity (E2b): dedup/supersede + canary interpretation live in `winning_manifest_rows` (the
    ONE reader, shared with grounding_yield).

    Aggregation: one cell per (source, interface, lens, geometry, intent) — source×interface are
    DISTINCT entries (R2.2d), intent stratifies when declared (enxerto A2), `geometry: ambient`
    rides the same fold (R3.1/R3.2: wake health, never a gate). Per cell: `attempts`, `hits` (sum
    of KNOWN counts, None when none known — a `hits: None` row folds as `hits_unknown`, NEVER
    coerced to 0), and the `dry` taxonomy (B1, see _dry_label).

    Excluded-from-learning (R4.2): seca-suspeita and attribution inferred/unknown are counted in
    `excluded` BY REASON — excluded ≠ invisible; the rows still aggregate into their cells
    (instrument health reads every attempt) and the yield join (S7) drops them from the learning
    denominator, with this count keeping the estimator's bias magnitude inspectable."""
    rows, canaries, corrupt = winning_manifest_rows(events)
    cells = {}
    excluded = {"seca-suspeita": 0}
    excluded.update({f"attribution:{a}": 0 for a in _GROUNDING_EXCLUDED_ATTRIBUTION})
    for e, p in rows:  # already seq-sorted by winning_manifest_rows
        def _dim(k):  # a non-str dimension is corrupt-typed → folds under None (fail-dark)
            v = p.get(k)
            return v if isinstance(v, str) else None
        key = (_dim("source"), _dim("interface"), _dim("lens"), _dim("geometry"), _dim("intent"))
        cell = cells.setdefault(key, {"source": key[0], "interface": key[1], "lens": key[2],
                                      "geometry": key[3], "intent": key[4], "attempts": 0,
                                      "hits": None, "hits_unknown": 0, "dry": {}})
        cell["attempts"] += 1
        hits = p.get("hits")
        if isinstance(hits, bool) or not isinstance(hits, (int, float)):
            cell["hits_unknown"] += 1  # None (or corrupt) = unknown — NEVER coerced to 0
            hits = None
        else:
            cell["hits"] = (cell["hits"] or 0) + hits
        label = _dry_label(e, p, hits, key[0], key[1], canaries)
        if label is not None:
            cell["dry"][label] = cell["dry"].get(label, 0) + 1
            if label in _GROUNDING_SUSPECT_LABELS:
                excluded["seca-suspeita"] += 1
        if p.get("attribution") in _GROUNDING_EXCLUDED_ATTRIBUTION:
            excluded[f"attribution:{p['attribution']}"] += 1
    return {"cells": cells, "excluded": excluded, "corrupt": corrupt}


def grounding_at(seq=None, ts=None, log=LOG):
    """Fold `{grounding.manifest, canary.result}` events up to a cursor → the grounding attempts
    table (R2.3). Pure: replaying to a past cursor reconstructs that past interpretation —
    including the pre-supersede one (E2b: interpretation is versioned, the raw history is not) —
    strategic versioning, as direction_at/corpus_at. An empty log folds to the empty shape (a
    dict-returning fold, as source_yield_at)."""
    return fold_grounding(read(types=GROUNDING_FOLD_TYPES, until_seq=seq, until_ts=ts, log=log))


def _direction_ids(events):
    # shares fold_direction's payload/key tolerance (Slice 4 [high], round-4): a TRUTHY non-dict
    # payload (string/list) would AttributeError `.get`, and a non-string id is unhashable in this
    # set comprehension — so normalize the payload to a dict and keep only str ids (fail-dark).
    return {p.get("id") for e in events if e.get("type") in DIRECTION_TYPES
            for p in [e.get("payload") if isinstance(e.get("payload"), dict) else {}]
            if isinstance(p.get("id"), str)}


def consolidate_artefato_proposals(log=LOG):
    """Fan each `artefato.published` candidate into the non-curated `proposed` tier (ADR-0007: the
    sweep populates, the grill curates). Idempotent via the deterministic id `<slug>:<i>` — a
    candidate already in the log (proposed/set/dropped) is never re-added. Returns the count added."""
    evs = read(log=log)
    have = _direction_ids(evs)
    n = 0
    for e in evs:
        if e.get("type") != "artefato.published":
            continue
        p = e.get("payload") or {}
        slug = p.get("slug")
        for i, cand in enumerate(p.get("proposes") or []):
            iid = f"{slug}:{i}"
            if iid in have:
                continue
            # publish path accepts body|text (plan/report rites use either); hollow skipped, never crash wake
            body = (cand.get("body") if isinstance(cand, dict) else None) or (
                cand.get("text") if isinstance(cand, dict) else None) or ""
            if not (isinstance(body, str) and body.strip()):
                continue
            propose(iid, body, kind=cand.get("kind", "thread"),
                    from_artefato=slug, relates_to=cand.get("relates_to"), log=log)
            have.add(iid)
            n += 1
    return n


def _render_items(items):
    by_kind = {}
    for it in items:
        by_kind.setdefault(it.get("kind", "thread"), []).append(it)
    lines = []
    for kind in KIND_ORDER + [k for k in by_kind if k not in KIND_ORDER]:
        for it in by_kind.get(kind, []):
            prov = f" _(from {it['from_artefato']})_" if it.get("from_artefato") else ""
            lines.append(f"- **[{kind}]** {it.get('body', '')} `#{it['id']}`{prov}")
    return "\n".join(lines) if lines else "_none_"


def project_direction(seq=None, ts=None, log=LOG, out=DIRECTION):
    """Project the Direction standing page from the log — a fold output (ADR-0006/0007), never
    hand-edited (banner-marked). Renders BOTH tiers: `Set` (curated) and `Proposed` (non-curated).
    Projecting a past cursor writes that past plan."""
    d = direction_at(seq=seq, ts=ts, log=log) or {"set": [], "proposed": []}
    text = (f"<!-- generated by tools/eventlog.py from {LOG.name} — do not edit -->\n"
            f"# Direction\n\n## Set — curated (Voz)\n\n{_render_items(d.get('set', []))}\n\n"
            f"## Proposed — non-curated (grill achados)\n\n{_render_items(d.get('proposed', []))}\n")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text


def _render_corpus(items):
    if not items:
        return "_none yet_"
    lines = []
    for it in reversed(items):  # most-recent-first
        why = it.get("intent") or "_no intent recorded (C3 debt)_"
        lines.append(f"### {it['slug']}\n\n**why:** {why}\n")
        steers = [p.get("body") if isinstance(p, dict) else p for p in it.get("proposes", [])]
        steers = [s for s in steers if isinstance(s, str) and s.strip()]
        if steers:
            lines.append("proposes:\n" + "\n".join(f"- {s}" for s in steers) + "\n")
    return "\n".join(lines)


def project_corpus(seq=None, ts=None, log=LOG, out=CORPUS):
    """Project the corpus standing page from the log — a fold output (ADR-0006/0009), never hand-edited
    (banner-marked). Part of Memento's tattoo: a zero-memory agent reads it to know what it already did
    and **why**, so each Artefato's intent (the why) is inscribed per entry, most-recent-first, with its
    proposed steers. Projecting a past cursor writes that past corpus."""
    items = corpus_at(seq=seq, ts=ts, log=log)
    text = (f"<!-- generated by tools/eventlog.py from {LOG.name} — do not edit -->\n"
            f"# Corpus — the edge's own steps + their why\n\n{_render_corpus(items)}\n")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text


# --- Assemble pending queue (tkt-003 / S30.A2) — log is sole truth (ADR-0006) ---
# Per-item: assembly.pending opens a package_id; assembly.done|failed clears it.
# Graph is projection only — never authority for pending.


def _assembly_package_id(package_id):
    if not isinstance(package_id, str) or not package_id.strip():
        raise ValueError("assembly package_id must be a non-blank string")
    return package_id.strip()


def mark_assembly_pending(package_id, *, kind, ref=None, by=None, log=LOG):
    """Append assembly.pending — package enters the Assemble queue (log truth)."""
    package_id = _assembly_package_id(package_id)
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("assembly.pending kind must be a non-blank string")
    payload = {
        "package_id": package_id,
        "kind": kind.strip(),
        "ref": ref.strip() if isinstance(ref, str) and ref.strip() else None,
        "by": by.strip() if isinstance(by, str) and by.strip() else None,
    }
    return append("assembly.pending", f"assembly:{package_id}", payload, log=log)


def mark_assembly_done(package_id, *, by=None, log=LOG):
    """Append assembly.done — package leaves the open pending set for this id."""
    package_id = _assembly_package_id(package_id)
    payload = {
        "package_id": package_id,
        "by": by.strip() if isinstance(by, str) and by.strip() else None,
    }
    return append("assembly.done", f"assembly:{package_id}", payload, log=log)


def mark_assembly_failed(package_id, *, reason, by=None, log=LOG):
    """Append assembly.failed — package leaves open set; reason is durable for mentor/QA."""
    package_id = _assembly_package_id(package_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("assembly.failed reason must be a non-blank string")
    payload = {
        "package_id": package_id,
        "reason": reason.strip(),
        "by": by.strip() if isinstance(by, str) and by.strip() else None,
    }
    return append("assembly.failed", f"assembly:{package_id}", payload, log=log)


def assembly_pending_open(log=LOG):
    """Fold: open assembly packages = pending without a later done/failed for same package_id.

    Pure projection of the log — re-runnable, never invents state. Empty log → {}.
    """
    open_ = {}
    for event in read(log=log):
        if not isinstance(event, dict):
            continue
        t = event.get("type")
        p = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        pid = p.get("package_id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        pid = pid.strip()
        if t == "assembly.pending":
            open_[pid] = {
                "package_id": pid,
                "kind": p.get("kind"),
                "ref": p.get("ref"),
                "by": p.get("by"),
                "seq": event.get("seq"),
                "ts": event.get("ts"),
            }
        elif t in ("assembly.done", "assembly.failed"):
            open_.pop(pid, None)
    return open_
