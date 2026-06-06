"""eventlog — Tier-0 append-only event log, the source of truth (ADR-0006). Genotype tool.

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated. Nothing is
true unless it is an event here. The graph and the standing pages are projections of this log —
folds that replay deterministically, so a past cursor reconstructs that past state byte-faithfully
(strategic versioning). No event-store framework: append-only JSONL + pure-function folds.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "state" / "events" / "log.jsonl"
DIRECTION = REPO / "state" / "direction.md"


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
