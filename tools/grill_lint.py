"""grill_lint — Lint over the wiki graph; seeds the grill agenda. Genotype tool (CONTEXT: Lint).

Mechanical detection of curation debt: retired terms (entity names the glossary moved to `_Avoid_`
— a conflict with the Idiom), canonical-identity duplicates, the blob (over-large community),
orphans (degree 0). Ranked by harm potential → the grill agenda. **A delta**: it skips entities
already carrying the grilled mark (`grilled_at`) — the agenda is only the un-converged frontier.
Lint detects and escalates; the rule or the mentee resolves (never by judgment in code).

Usage:  python grill_lint.py [group_id]
Env:    EDGE_NEO4J_URI/USER/PASSWORD
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity
NEO4J = _identity.neo4j_conn()


def normalize(name: str) -> str:
    """Fold surface variants to one key: lowercase, separators→space, collapse spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[/\-_,.]", " ", name.lower())).strip()


def duplicate_groups(names):
    """Group names that collapse to the same normalized key (size > 1) — dedup candidates."""
    by_key = defaultdict(list)
    for n in names:
        by_key[normalize(n)].append(n)
    return [g for g in by_key.values() if len(g) > 1]


def avoid_terms(context_text: str):
    """The terms the glossary has retired — everything after an `_Avoid_:` line."""
    terms = set()
    for line in context_text.splitlines():
        m = re.match(r"\s*_Avoid_:\s*(.+)", line)
        if m:
            for t in re.split(r"[,;]", m.group(1)):
                t = re.sub(r"\(.*?\)", "", t).strip().lower()
                if t:
                    terms.add(t)
    return terms


def retired(names, avoid):
    """Entity names the glossary has moved to `_Avoid_` — a conflict with the Idiom."""
    norm_avoid = {normalize(a) for a in avoid}
    return [n for n in names if normalize(n) in norm_avoid]


# Contradiction rule (slice 3, ADR-0011): a curated=valued source is "contradicted" when its accruing
# yield has gone cold — accumulated evidence (count >= MIN) at a low mean similarity (< COLD). Minimal,
# documented, testable: the standing opinion says "relevant" but the data says "no longer landing". We
# require MIN cites so a single weak hit can't fire a confront (the confront needs accrued data).
SOURCE_COLD_SIM = 0.30   # below this mean similarity, the source is no longer landing
SOURCE_MIN_CITES = 2     # need at least this many cites before the cold reading is trustworthy


def _curated_ref(ref, curated_sources):
    """The curated source name governing a yield ref, or None. Curated is keyed by source name (e.g.
    'github'); the yield is keyed by ref (e.g. 'github:abc') — match on exact name or the `src:` prefix."""
    for s in curated_sources:
        if ref == s or ref.split(":")[0] == s:
            return s
    return None


def source_yield_agenda(yield_by_ref, curated=None):
    """Per-source yield (eventlog.source_yield_at output) → grill agenda items, as a **DELTA** over the
    curated frontier (ADR-0011). The grill consults the mechanical non-curated tier — "source X yielded
    N cites, mean sim 0.YZ — relevant?" — but **skips sources that already carry a curated opinion**
    (the converged frontier; pass `curated` = fold_source_feedback's curated tier). The exception is the
    two-way Convergence: a curated source whose accruing yield CONTRADICTS the standing opinion
    (gone cold: count >= SOURCE_MIN_CITES at mean sim < SOURCE_COLD_SIM) **re-surfaces as `contested`**
    for the mentee to retire or reaffirm. Pure (no driver): the signal is never used alone."""
    curated_sources = {c["source"] for c in (curated or [])}
    agenda = []
    for y in yield_by_ref.values():
        gov = _curated_ref(y["ref"], curated_sources)
        if gov is not None:
            if y["count"] >= SOURCE_MIN_CITES and y["mean_similarity"] < SOURCE_COLD_SIM:
                agenda.append(("HIGH", "source-contested",
                               f"Curated source '{gov}' is contradicted by the data: "
                               f"'{y['ref']}' yielded {y['count']} cite(s) at mean sim "
                               f"{y['mean_similarity']:.2f} (< {SOURCE_COLD_SIM:.2f} — gone cold).",
                               "Retire it (source.dropped) or reaffirm the curated opinion?"))
            continue  # curated + consistent → omitted from the delta
        agenda.append(("LOW", "source-yield",
                       f"Source '{y['ref']}' ({y.get('kind')}) yielded {y['count']} cite(s), "
                       f"mean sim {y['mean_similarity']:.2f}.",
                       "Is this source relevant to your reports? (curate: values it because…)"))
    return agenda


def detect(driver, group):
    """Assemble the ranked grill agenda over the un-grilled frontier (harm: high → low)."""
    def q(c, **kw):
        with driver.session() as s:
            return [r.data() for r in s.run(c, **kw)]

    names = [r["name"] for r in q("MATCH (e:Entity {group_id:$g}) WHERE e.grilled_at IS NULL "
                                  "RETURN e.name AS name", g=group)]
    ctx = REPO / "CONTEXT.md"
    avoid = avoid_terms(ctx.read_text()) if ctx.exists() else set()

    agenda = []
    for n in retired(names, avoid):
        agenda.append(("HIGH", "idiom-conflict", f"'{n}' is retired in the glossary (_Avoid_).",
                       "Confirm the live term it should become."))
    for grp in duplicate_groups(names):
        agenda.append(("MED", "duplicate", f"{grp} are one concept under different surfaces.",
                       "Merge into one canonical entity? Which name is canonical?"))
    for r in q("MATCH (c:Community {group_id:$g})-[:HAS_MEMBER]->(e) WHERE e.grilled_at IS NULL "
               "WITH c, count(e) AS n WHERE n>=10 RETURN c.uuid AS c, n", g=group):
        agenda.append(("MED", "split-blob", f"One community holds {r['n']} un-grilled entities — it conflates themes.",
                       "Split into named clusters?"))
    orph = q("MATCH (e:Entity {group_id:$g}) WHERE NOT (e)-[:RELATES_TO]-() AND e.grilled_at IS NULL "
             "RETURN e.name AS name", g=group)
    if orph:
        agenda.append(("LOW", "orphan", f"{len(orph)} entities have no facts: {[o['name'] for o in orph][:8]}.",
                       "Prune (archive) or attach?"))
    # Direction `proposed` tier — the grill curates it (promote/drop/merge), ADR-0007/#14.
    try:
        sys.path.insert(0, str(REPO / "tools"))
        import eventlog
        for it in (eventlog.direction_at() or {}).get("proposed", []):
            src = f" (from {it['from_artefato']})" if it.get("from_artefato") else ""
            agenda.append(("HIGH", "direction-proposed",
                           f"Proposed direction '{it.get('body', '')}'{src} is uncurated.",
                           "Promote to set (ratify), drop, or merge?"))
    except Exception:
        pass
    # Source-feedback — a DELTA over the curated frontier (ADR-0011): the non-curated yield seeds
    # agenda items, but curated sources are omitted unless the data contradicts them (→ contested).
    try:
        sys.path.insert(0, str(REPO / "tools"))
        import eventlog
        fb = eventlog.source_feedback_at()
        agenda.extend(source_yield_agenda(fb["non_curated"], curated=fb["curated"]))
    except Exception:
        pass
    return sorted(agenda, key=lambda a: {"HIGH": 0, "MED": 1, "LOW": 2}[a[0]])


def main(group):
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(NEO4J[0], auth=(NEO4J[1], NEO4J[2]))
    agenda = detect(drv, group)
    drv.close()
    print(f"=== GRILL AGENDA — {len(agenda)} items (group={group}) ===\n")
    for i, (harm, kind, belief, ask) in enumerate(agenda, 1):
        print(f"{i}. [{harm} · {kind}] {belief}\n   → {ask}\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else _identity.require_group())
