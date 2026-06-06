"""eventlog — Tier-0 append-only event log, the source of truth (ADR-0006). Genotype tool.

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated. Nothing is
true unless it is an event here. The graph and the standing pages are projections of this log —
folds that replay deterministically, so a past cursor reconstructs that past state byte-faithfully
(strategic versioning). No event-store framework: append-only JSONL + pure-function folds.
"""
import json
import math
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
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    seq = len(read(log=log)) + 1
    ev = {"seq": seq, "ts": datetime.now(timezone.utc).isoformat(),
          "type": type, "subject": subject, "payload": payload}
    with log.open("a") as fh:
        fh.write(json.dumps(ev) + "\n")
    return ev


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
            items[iid] = {"id": iid, "body": p.get("body", p.get("plan", "")),
                          "kind": p.get("kind", "thread"), "supersedes": p.get("supersedes"),
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


def propose(id, body, kind="thread", from_artefato=None, relates_to=None, log=LOG):
    """Append a `direction.proposed` item (the non-curated tier — grill achados / artefato candidates)."""
    return append("direction.proposed", "direction",
                  {"id": id, "body": body, "kind": kind,
                   "from_artefato": from_artefato, "relates_to": relates_to}, log=log)


def set_direction(id, body, kind="thread", supersedes=None, log=LOG):
    """Append a `direction.set` item (the curated tier — Voz only; promotes/supersedes a proposed id)."""
    return append("direction.set", "direction",
                  {"id": id, "body": body, "kind": kind, "supersedes": supersedes}, log=log)


def drop(id, reason="", log=LOG):
    """Append a `direction.dropped` event — retire a thread (the only way an item leaves)."""
    return append("direction.dropped", "direction", {"id": id, "reason": reason}, log=log)


def publish_artefato(slug, proposes=None, distills=None, cites=None, log=LOG):
    """Append an `artefato.published` event (ADR-0006/0007). The Artefato **declares** candidate
    steers in `proposes`; it does NOT write Direction itself — the sweep consolidates them."""
    return append("artefato.published", f"artefato:{slug}",
                  {"slug": slug, "proposes": proposes or [], "distills": distills or [],
                   "cites": cites or []}, log=log)


def kernel(slug, intent, log=LOG):
    """Append an `intent.kernel` event (CONTRACT C3) — the durable *why* of a dispatch's Artefato:
    what is open, the next bet. Mandatory at close; the corpus folds it alongside artefato.published
    (paired by slug), and the briefing's Recap projects it. The kernel and a cold transcript can
    disagree on intent; the kernel wins."""
    return append("intent.kernel", f"artefato:{slug}", {"slug": slug, "intent": intent}, log=log)


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
    kerneled = {(e.get("payload") or {}).get("slug") for e in evs if e["type"] == "intent.kernel"}
    published = [(e.get("payload") or {}).get("slug") for e in evs if e["type"] == "artefato.published"]
    return [s for s in published if s not in kerneled]


CORPUS_TYPES = ["artefato.published", "intent.kernel"]


def fold_corpus(events):
    """Pure fold of `{artefato.published, intent.kernel}` events → the corpus (ADR-0009): the edge's
    own published steps, each paired with its *why*. In one pass, seq order: an `artefato.published`
    opens a corpus item keyed by slug (carrying its proposes/distills/cites and published ts); an
    `intent.kernel` writes the `intent` onto its slug's item. An Artefato with no kernel folds with
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
                           "ts": e.get("ts")}
        elif t == "intent.kernel" and slug in items:
            items[slug]["intent"] = p.get("intent")
    return list(items.values())


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
