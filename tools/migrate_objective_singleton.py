#!/usr/bin/env python3
"""#633 — make the spine :Objective of a group a SINGLETON again, RELINKING every edge it carries.

The write path (tools/publisher.py) is fixed forward-only: it can no longer mint or stamp a second
Objective, and the per-`operacao` hub is now labelled :Operacao. This is the one-shot repair for
graphs that ALREADY duplicated — the fleet's `petertosh` carried 6 :Objective with one identical
body, which is what `tools/group_health.py` reports as `N Objectives vivos`.

Two damages, two repairs:

  * COLLAPSE — extra spine copies (`ref IS NULL`, i.e. never an operation hub). Every relationship
    they carry is re-created on the survivor, THEN the copy is DETACH DELETEd. Deleting 5 nodes
    without relinking would trade duplication for orphanhood: an Artefato whose only SERVES pointed
    at a copy would stop being reachable from space-0.

  * RELABEL — the `operacao:<name>` hubs `publisher.project_lentes` used to mint as :Objective.
    These nodes are LEGITIMATE (MARCO_OF hangs off them) and are NEVER deleted, only relabelled to
    :Operacao. The spine fan they wrongly collected (incoming SERVES from :Artefato, incoming
    GROUNDS from :Genesis, outgoing ANCHORS to :Direction) is moved to the survivor and the stamped
    `body`/`spine` properties are cleared. When a sweep already ran on the fixed code, an :Operacao
    twin exists for that ref — the hub's remaining edges are relinked onto the twin instead.

DRY-RUN IS THE DEFAULT. `--apply` additionally requires `--yes`. Nothing is written otherwise.

    tools/edge-python tools/migrate_objective_singleton.py --group petertosh
    tools/edge-python tools/migrate_objective_singleton.py --group petertosh --apply --yes

The unicity key is publisher.OBJECTIVE_SINGLETON_KEY — `("group_id",)` today, `("group_id",
"agent")` once #578 (corpus N×N) lands. Pass `--agent` when that key is in force.
"""
import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import publisher  # noqa: E402

# Relationship types are interpolated into Cypher (they cannot be parameterised). Only names that
# came back from `type(r)` on this very graph AND match this shape are ever spliced in.
_REL_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The edges the spine fan wrongly hung on an operation hub — the only ones moved off it.
_FAN = (("SERVES", "in", "Artefato"), ("GROUNDS", "in", "Genesis"), ("ANCHORS", "out", "Direction"))


def _rel_type(name):
    if not isinstance(name, str) or not _REL_TYPE.match(name):
        raise ValueError(f"refusing to splice an unexpected relationship type: {name!r}")
    return name


def _edges_of(s, node_ids):
    """Every relationship touching these nodes: (owner, kind, outgoing, other, props)."""
    if not node_ids:
        return []
    rows = s.run(
        "MATCH (o) WHERE elementId(o) IN $ids "
        "MATCH (o)-[r]-(x) "
        "RETURN elementId(o) AS owner, type(r) AS kind, startNode(r) = o AS outgoing, "
        "elementId(x) AS other, properties(r) AS props", ids=list(node_ids))
    return [dict(r) for r in rows]


def _fan_edges_of(s, node_ids):
    """Only the spine-fan edges on these nodes — what the old bare MERGE wrongly attached."""
    if not node_ids:
        return []
    edges = []
    for kind, direction, label in _FAN:
        arrow = (f"(o)-[r:{kind}]->(x:{label})" if direction == "out"
                 else f"(x:{label})-[r:{kind}]->(o)")
        rows = s.run(f"MATCH (o) WHERE elementId(o) IN $ids MATCH {arrow} "
                     "RETURN elementId(o) AS owner, type(r) AS kind, "
                     f"{'true' if direction == 'out' else 'false'} AS outgoing, "
                     "elementId(x) AS other, properties(r) AS props", ids=list(node_ids))
        edges.extend(dict(r) for r in rows)
    return edges


def _relink(s, target, edges):
    """Re-create `edges` on `target`. MERGE, so an edge the target already has is reused."""
    for e in edges:
        if e["other"] == target:
            continue  # would become a self-loop on the target
        kind = _rel_type(e["kind"])
        pattern = f"(a)-[r:{kind}]->(b)" if e["outgoing"] else f"(b)-[r:{kind}]->(a)"
        s.run("MATCH (a) WHERE elementId(a) = $target "
              "MATCH (b) WHERE elementId(b) = $other "
              f"MERGE {pattern} SET r += $props",
              target=target, other=e["other"], props=e["props"] or {})


def _hubs(s, key):
    """`:Objective` nodes that are really per-`operacao` MARCO_OF hubs (pre-rename)."""
    where = " AND ".join(f"o.{field} = ${field}" for field in key)
    rows = s.run(f"MATCH (o:Objective) WHERE {where} AND o.ref IS NOT NULL "
                 "RETURN elementId(o) AS id, o.ref AS ref, o.body AS body ORDER BY o.ref", **key)
    return [dict(r) for r in rows]


def _twin_of(s, key, ref):
    """An already-relabelled :Operacao with this ref (a sweep ran before the migration)."""
    where = " AND ".join(f"n.{field} = ${field}" for field in key)
    rec = s.run(f"MATCH (n:`{publisher.OPERACAO_LABEL}`) WHERE {where} AND n.ref = $ref "
                "RETURN elementId(n) AS id", ref=ref, **key).single()
    return rec["id"] if rec else None


def plan(s, group_id, agent=None):
    """READ-ONLY. What the migration WOULD do, as a dict — the dry-run print and apply share it."""
    key = publisher.spine_objective_key(group_id, agent)
    spine = publisher.spine_objectives(s, group_id, agent)
    hubs = _hubs(s, key)
    for hub in hubs:
        hub["twin"] = _twin_of(s, key, hub["ref"])
    survivor = spine[0] if spine else None
    dead = spine[1:]
    body = survivor["body"] if survivor else None
    ambiguous = None
    if survivor is None and hubs:
        # every "objective" in this group was an operation hub — no spine node was ever created.
        # Rebuild it from the stamped text, but only when the graph agrees on ONE text.
        bodies = collections.Counter(h["body"] for h in hubs if h["body"])
        if len(bodies) > 1:
            ambiguous = sorted(bodies)
        elif bodies:
            body = next(iter(bodies))
    return {"key": key, "survivor": survivor, "dead": dead, "hubs": hubs,
            "body": body, "ambiguous": ambiguous,
            "collapse_edges": _edges_of(s, [d["id"] for d in dead]),
            "fan_edges": _fan_edges_of(s, [h["id"] for h in hubs])}


def render(p, group_id):
    out = [f"group: {group_id}   key: {p['key']}"]
    if p["ambiguous"]:
        out.append("REFUSING: no spine :Objective survives and the operation hubs carry "
                   f"{len(p['ambiguous'])} DIFFERENT bodies — pick the north by hand first.")
        return "\n".join(out)
    live = 1 if (p["survivor"] or p["body"]) else 0
    now = (1 + len(p["dead"]) if p["survivor"] else 0) + len(p["hubs"])
    out.append(f":Objective in this group now: {now}   (of which operation hubs: {len(p['hubs'])})")
    if p["survivor"]:
        out.append(f"  survivor (oldest): {p['survivor']['id']} — body kept as-is")
    elif p["body"]:
        out.append("  survivor: NONE — will MERGE the spine node from the stamped body "
                   f"({p['body'][:60]!r})")
    for d in p["dead"]:
        out.append(f"  collapse: {d['id']} → survivor (relink every edge, then DETACH DELETE)")
    for h in p["hubs"]:
        how = (f"merge into existing :{publisher.OPERACAO_LABEL} {h['twin']}" if h["twin"]
               else f"relabel :Objective → :{publisher.OPERACAO_LABEL}")
        out.append(f"  hub {h['ref']}: {how}; clear the stamped body/spine")
    out.append(f"  relink: {len(p['collapse_edges'])} edge(s) off the collapsed copies, "
               f"{len(p['fan_edges'])} spine-fan edge(s) off the hubs")
    out.append(f"after: {live} :Objective, {len(p['hubs'])} :{publisher.OPERACAO_LABEL} intact")
    return "\n".join(out)


def apply(s, group_id, agent=None):
    """DESTRUCTIVE. Runs the plan. Callers gate this behind --apply --yes."""
    p = plan(s, group_id, agent)
    if p["ambiguous"]:
        raise SystemExit("refusing: the operation hubs carry different bodies — resolve by hand")

    survivor = p["survivor"]["id"] if p["survivor"] else None
    if survivor is None and p["body"]:
        props = ", ".join(f"{field}:${field}" for field in p["key"])
        survivor = s.run(f"MERGE (o:Objective {{{props}, spine:true}}) SET o.body = $body "
                         "RETURN elementId(o) AS id", body=p["body"], **p["key"]).single()["id"]
    elif survivor is not None:
        s.run("MATCH (o) WHERE elementId(o) = $id SET o.spine = true", id=survivor)

    # 1. the extra spine copies: relink everything they carry, then delete.
    if survivor is not None:
        _relink(s, survivor, p["collapse_edges"])
    dead_ids = [d["id"] for d in p["dead"]]
    if dead_ids:
        s.run("MATCH (o) WHERE elementId(o) IN $ids DETACH DELETE o", ids=dead_ids)

    # 2. the operation hubs: move the spine fan to the survivor, drop the stamp, relabel.
    hub_ids = [h["id"] for h in p["hubs"]]
    if hub_ids:
        if survivor is not None:
            _relink(s, survivor, p["fan_edges"])
        for kind, direction, label in _FAN:
            arrow = (f"(o)-[r:{kind}]->(:{label})" if direction == "out"
                     else f"(:{label})-[r:{kind}]->(o)")
            s.run(f"MATCH (o) WHERE elementId(o) IN $ids MATCH {arrow} DELETE r", ids=hub_ids)
        s.run("MATCH (o) WHERE elementId(o) IN $ids REMOVE o.body, o.spine", ids=hub_ids)
        for hub in p["hubs"]:
            if hub["twin"]:
                _relink(s, hub["twin"], _edges_of(s, [hub["id"]]))
                s.run("MATCH (o) WHERE elementId(o) = $id DETACH DELETE o", id=hub["id"])
            else:
                s.run("MATCH (o) WHERE elementId(o) = $id "
                      f"REMOVE o:Objective SET o:`{publisher.OPERACAO_LABEL}`", id=hub["id"])
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--group", help="group_id to repair (default: this install's identity)")
    ap.add_argument("--agent", default=None,
                    help="agent, when OBJECTIVE_SINGLETON_KEY includes it (#578)")
    ap.add_argument("--apply", action="store_true", help="WRITE the plan (also needs --yes)")
    ap.add_argument("--yes", action="store_true", help="confirm the destructive apply")
    args = ap.parse_args(argv)

    import _identity
    from neo4j import GraphDatabase
    group = args.group or _identity.require_group()
    uri, user, pw = _identity.neo4j_conn()
    drv = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        with drv.session() as s:
            print(render(plan(s, group, args.agent), group))
            if not args.apply:
                print("\n-- dry-run (nothing written). Re-run with --apply --yes to write. --")
                return 0
            if not args.yes:
                print("\nrefusing --apply without --yes: this DELETES and RELABELS nodes.",
                      file=sys.stderr)
                return 2
            apply(s, group, args.agent)
            print("\n-- applied --")
            print(render(plan(s, group, args.agent), group))
    finally:
        drv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
