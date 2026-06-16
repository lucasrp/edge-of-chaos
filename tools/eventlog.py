"""eventlog — Tier-0 append-only event log, the source of truth (ADR-0006). Genotype tool.

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated. Nothing is
true unless it is an event here. The graph and the standing pages are projections of this log —
folds that replay deterministically, so a past cursor reconstructs that past state byte-faithfully
(strategic versioning). No event-store framework: append-only JSONL + pure-function folds.
"""
import fcntl
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

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
            base = len(read(log=log))
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
    (until_seq: seq<=n; until_ts: ts<=t). The cursor is what makes replay reconstruct a past."""
    log = Path(log)
    if not log.exists():
        return []
    events = [json.loads(line) for line in log.read_text().splitlines() if line]
    if types is not None:
        events = [e for e in events if e["type"] in types]
    if until_seq is not None:
        events = [e for e in events if e["seq"] <= until_seq]
    if until_ts is not None:
        events = [e for e in events if e["ts"] <= until_ts]
    return events


DIRECTION_TYPES = ["direction.proposed", "direction.set", "direction.dropped"]
KIND_ORDER = ["phase", "priority", "constraint", "thread"]


def fold_direction(events):
    """Pure fold of direction.* events → addressable items in two tiers (ADR-0007).

    Per-id, in seq order: `direction.proposed` opens/updates a `proposed` item; `direction.set`
    opens/updates a `set` item and **outranks** proposed for the same id (curado > hipótese, a
    correção sempre ganha); `direction.dropped` removes the id (persist-until-dropped — nothing is
    lost by omission). Returns {"set": [...], "proposed": [...]} in insertion order.
    """
    items = {}  # id -> item (carries 'tier')
    for e in events:
        t, p = e.get("type"), e.get("payload", {}) or {}
        if t == "direction.proposed":
            iid = p.get("id")
            if iid is None:
                continue
            if items.get(iid, {}).get("tier") == "set":
                continue  # set outranks proposed
            items[iid] = {"id": iid, "body": p.get("body", ""), "kind": p.get("kind", "thread"),
                          "from_artefato": p.get("from_artefato"), "relates_to": p.get("relates_to"),
                          "tier": "proposed"}
        elif t == "direction.set":
            iid = p.get("id", "_plan")  # legacy {plan} blob folds to a single set item
            sup = p.get("supersedes")
            if sup and sup != iid:
                items.pop(sup, None)  # a set RETIRES the (different) id it supersedes — not just
                                      # same-id overwrite/dropped. Codex #28-review: supersedes was
                                      # stored but never honored, leaving the old steer active.
            items[iid] = {"id": iid, "body": p.get("body", p.get("plan", "")),
                          "kind": p.get("kind", "thread"), "supersedes": sup,
                          "tier": "set"}
        elif t == "direction.dropped":
            items.pop(p.get("id"), None)
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
    """Publish an Artefato — the producer-facing path. `intent` is REQUIRED (positional, no default):
    every real producer passes it and the close seam in publisher.py always does. The call publishes
    the `artefato.published` AND its `intent.kernel` in ONE indivisible write via
    `publish_artefato_atomic` — so the producer path pairs the kernel and **cannot** ship C3 debt
    (Codex re-review #2/round 2). An empty/missing intent raises before anything lands: there is NO
    kernel-less producer path. The Artefato **declares** candidate steers in `proposes`; it does NOT
    write Direction itself — the sweep consolidates them. Returns (published_event, kernel_event).

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


def publish_artefato_atomic(slug, intent, proposes=None, distills=None, cites=None,
                            spec=None, log=LOG, *, lineage=None, skill=None, require_wake=False):
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
    replays it as DIRECTED edges. No lineage folds to []."""
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")

    def _wake_gate():
        # ADR-0016, authoritative form (codex gate): evaluated UNDER append_batch's lock, so one
        # stamp admits exactly ONE publish — a concurrent caller that raced past an early
        # fast-fail check still loses here, with nothing written.
        if not wake_fresh(log=log):
            raise RuntimeError(
                f"no-wake: cannot publish {slug!r} — no dispatch.open newer than the last "
                "artefato.published on this log (ADR-0016: run tools/predispatch.py; "
                "one wake per publish)")

    published, kernel_ev = append_batch([
        ("artefato.published", f"artefato:{slug}",
         {"slug": slug, "proposes": proposes or [], "distills": distills or [],
          "cites": cites or [], "lineage": lineage or [], "spec": spec, "skill": skill}),
        ("intent.kernel", f"artefato:{slug}", {"slug": slug, "intent": intent}),
    ], log=log, precondition=_wake_gate if require_wake else None)
    return published, kernel_ev


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
    wake per publish; a stamp is consumed by the publish it precedes and cannot be reused."""
    evs = read(types=["dispatch.open", "artefato.published"], log=log)
    last_open = max((e["seq"] for e in evs if e["type"] == "dispatch.open"), default=None)
    last_pub = max((e["seq"] for e in evs if e["type"] == "artefato.published"), default=None)
    return last_open is not None and (last_pub is None or last_open > last_pub)


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


def source_curated(source, opinion, kind=None, log=LOG):
    """Append a `source.curated` event (ADR-0011, source-feedback curated tier) — the grill-distilled
    mentee opinion about a source ("values X because Y"). A **separate** event the non-curated signal
    *prompts*, never a promotion (a measurement cannot become an opinion). Curated **outranks** the
    yield, is exempt from passive aging, retirable only by Voz (source_dropped). Latest wins per source."""
    return append("source.curated", f"source:{source}",
                  {"source": source, "opinion": opinion, "kind": kind}, log=log)


def source_dropped(source, reason="", log=LOG):
    """Append a `source.dropped` event — retire a curated source opinion (Voz only). The only way a
    curated source entry leaves (persist-until-dropped, mirroring direction.dropped)."""
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


def _direction_ids(events):
    return {(e.get("payload") or {}).get("id") for e in events
            if e.get("type") in DIRECTION_TYPES} - {None}


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
            propose(iid, cand.get("body", ""), kind=cand.get("kind", "thread"),
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
        steers = [p.get("body", "") for p in it.get("proposes", [])]
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
