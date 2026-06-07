"""grill_writeback — land the grill's decisions directly on the graph. Genotype tool (ADR-0005).

The grill never edits a page; it marks the graph, and the page re-renders (tools/wiki_render.py).
Each decision is a node property the render respects — `curated_name` (rename/retire),
`merged_into` (canonical-identity), `curated_cluster` (split/attach), `archived` (orphan) — plus
the grilled mark (`grilled_at` + outcome), the Convergence cursor that makes the next Lint a delta.
One source of truth: render / Lint / Aging all read the node.

Env: EDGE_NEO4J_URI/USER/PASSWORD
"""
from datetime import datetime, timezone

import eventlog
import _identity

NEO4J = _identity.neo4j_conn()


def driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(NEO4J[0], auth=(NEO4J[1], NEO4J[2]))


def _set(drv, group, names, props):
    props = {**props, "grilled_at": datetime.now(timezone.utc).isoformat(), "tier": "curated"}
    with drv.session() as s:
        return s.run("MATCH (e:Entity {group_id:$g}) WHERE e.name IN $names SET e += $props "
                     "RETURN count(e) AS n", g=group, names=list(names), props=props).single()["n"]


def rename(drv, group, name, curated_name):
    """Retire a term to its live glossary name (idiom-conflict resolution)."""
    return _set(drv, group, [name], {"curated_name": curated_name, "outcome": "renamed"})


def merge(drv, group, names, canonical):
    """Fold canonical-identity duplicates under one canonical name."""
    _set(drv, group, [canonical], {"curated_name": canonical, "outcome": "canonical"})
    return _set(drv, group, [n for n in names if n != canonical],
                {"merged_into": canonical, "outcome": "merged"})


def cluster(drv, group, names, label):
    """Assign entities to a grill-curated cluster (split the blob / attach singletons)."""
    return _set(drv, group, names, {"curated_cluster": label, "outcome": "clustered"})


def archive(drv, group, names):
    """Archive orphans out of the read layer (non-lossy — the node stays)."""
    return _set(drv, group, names, {"archived": True, "outcome": "archived"})


def append_event(type, subject, payload, log=eventlog.LOG):
    """Persist a grill decision to the Tier-0 log (ADR-0006) — the durable truth, no graph needed.
    A grill that can't reach Neo4j still lands its `direction.set` / `grill.curated` event here;
    the graph and wiki catch up later by projection (the stranded-grill fix)."""
    return eventlog.append(type, subject, payload, log=log)
