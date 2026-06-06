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
NEO4J = (os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687"),
         os.environ.get("EDGE_NEO4J_USER", "neo4j"),
         os.environ.get("EDGE_NEO4J_PASSWORD", "edgepassword123"))


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
    main(sys.argv[1] if len(sys.argv) > 1 else "edge-next")
