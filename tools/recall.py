"""recall — the memory-salient brief, the THIRD independent brief at pre-dispatch (ADR-0014).
Genotype tool.

Recall is a noun — the yield of recalling, exactly as Delta is the yield of updating: the salient
subgraph of the Cortex, rooted at space-0, handed to the agent as a brief PEER to the briefing
(assemble) and the delta — never fused with either (the subject boundary: delta reads the world,
recall reads the self). This supersedes the recall-push-inside-assemble placement (4428c64,
briefing §7): the briefing returns to its four parts; this module owns the leg.

The push seeds; navigation deepens (ADR-0011 reaffirmed): the brief is the mechanical salience
push — on-demand Cortex navigation stays the loop's own judgment (`skills/_shared/memory.md`).
Degrade contract unchanged (CONTRACT C1): a dark graph yields an honest marker, never a crash.
"""
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _identity  # noqa: E402

# The SALIENT slice — cap the artefatos in the brief so it does not grow with the whole corpus
# (Codex P2). A small, most-recent slice; recall MORE on demand.
RECALL_ARTEFATO_LIMIT = 8

# The recall cyphers as module constants — the runtime artifacts the salience guards live in
# (cap, recency order, complete-projections-only, retired-cluster filter), testable as
# interfaces rather than by grepping function source (review: a comment satisfied the old
# substring assertions while the live query regressed).
SPINE_QUERY = (
    "MATCH (gen:Genesis {group_id:$g}) "
    "OPTIONAL MATCH (gen)-[:GROUNDS]->(o:Objective {group_id:$g}) "
    "OPTIONAL MATCH (o)-[:ANCHORS]->(d:Direction {group_id:$g}) "
    "RETURN gen.codename AS codename, gen.voice AS voice, o.body AS objective, "
    "collect(DISTINCT d.body) AS bets")
ARTEFATOS_QUERY = (
    "MATCH (a:Artefato {group_id:$g})-[:SERVES]->(:Objective {group_id:$g}) "
    "WHERE a.projection_complete = true "
    "RETURN a.slug AS slug, a.kernel AS kernel "
    "ORDER BY coalesce(a.projected_at,'') DESC, a.slug LIMIT $lim")
CLUSTERS_QUERY = (
    "MATCH (a:Artefato {group_id:$g})-[:DISTILLS]->(e:Entity {group_id:$g}) "
    "WHERE a.slug IN $slugs AND e.curated_cluster IS NOT NULL "
    "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
    "RETURN DISTINCT e.curated_cluster AS l ORDER BY l")

# The SURF query — the topology read a SELECT cannot do (Cortex-v1 brick-1, schema report
# `the-graph-you-filled-like-a-list`, move 2). From the seed Artefatos it walks ONLY the typed
# associative peer web — BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES — direction-agnostic,
# bounded to *1..2 hops, and returns the reachable Artefatos/Sources. SERVES (the degree-44
# classification hub that "reaches everything and therefore discriminates nothing") is excluded
# STRUCTURALLY, by omission from the allowlist — it is never a pass-through hop. No ranking weight
# in v1: ORDER BY hops, slug only (the 1/|P| hub-damping rank from the report is OUT of brick-1).
# The seam (research `cosine-nominates-the-author-disposes`, R1): this OFFERS candidate priors the
# producer authors typed lineage FROM — the wiring into authoring context is the L6 doc, not code.
# PATH-WIDE group scoping (R7b / GitHub #41): the variable-length *1..2 walk constrains EVERY node
# on the path — `all(x IN nodes(p) WHERE x.group_id=$g)` — not only `seed` and the terminal `n`.
# On the SHARED neo4j (roberto/petertosh, one graph split by group_id) a FOREIGN intermediate bridge
# node could otherwise route which same-group peers surface — a cross-install topology leak that
# LOOKS scoped (rows are same-group) while the traversal itself was contaminated. With every path
# node pinned to $g, an off-group bridge is off-path, so it can neither surface nor route.
SURF_QUERY = (
    "MATCH (seed:Artefato {group_id:$g}) WHERE seed.slug IN $seeds "
    "MATCH p=(seed)-[:BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES*1..2]-(n) "
    # A peer is keyed by its slug (Artefato) OR its key (Source — Sources carry `key`, not `slug`,
    # codex final [P2]): use coalesce(n.slug, n.key) for BOTH the self-exclusion and the returned ref,
    # so a cited Source surfaces with a non-null slug and the surf → cortex_node drill-down resolves it
    # — without coalesce, `NOT n.slug IN $seeds` is null for a Source and the node returns a null slug.
    "WHERE (n:Artefato OR n:Source) AND n.group_id=$g "
    "AND NOT coalesce(n.slug, n.key) IN $seeds "
    "AND all(x IN nodes(p) WHERE x.group_id=$g) "
    "RETURN DISTINCT coalesce(n.slug, n.key) AS slug, n.kernel AS kernel, labels(n) AS labels, "
    "min(length(p)) AS hops "
    "ORDER BY hops, slug")

# The Entity/Community BRIDGE (ticket D, 02-D — "pra tudo se misturar"): sibling artefatos of the
# same knowledge cluster, reached seed-MENTIONS->Entity<-HAS_MEMBER-Community-HAS_MEMBER->Entity
# <-MENTIONS-sibling. A SISTER query to SURF_QUERY, deliberately NOT a widened allowlist: the
# associative walk stays EXACTLY the five typed relations (the set-equality test pins it), and the
# bridge is an EXPLICIT fixed shape — never a *1..4 walk that would blow past the hub discipline.
# hops is the REAL path length (4), so direct associative peers always outrank bridge siblings in
# the merged ORDER BY; `via` names the crossed community/ies (the navigability the mistura buys).
# Path-wide group scoping verbatim from SURF_QUERY (R7b/#41): a foreign Entity/Community can
# neither surface nor route.
SURF_BRIDGE_QUERY = (
    "MATCH (seed:Artefato {group_id:$g}) WHERE seed.slug IN $seeds "
    "MATCH p=(seed)-[:MENTIONS]->(:Entity)<-[:HAS_MEMBER]-(c:Community)"
    "-[:HAS_MEMBER]->(:Entity)<-[:MENTIONS]-(n:Artefato) "
    "WHERE n.group_id=$g AND NOT n.slug IN $seeds "
    "AND all(x IN nodes(p) WHERE x.group_id=$g) "
    "RETURN n.slug AS slug, n.kernel AS kernel, labels(n) AS labels, "
    "min(length(p)) AS hops, collect(DISTINCT c.name) AS via "
    "ORDER BY hops, slug")

_AUTO = object()

# N1/R3 — the bounded-latency budget (seconds). Every cortex_* read rides a driver opened with these
# timeouts, so a slow/absent graph DARKENS within the budget instead of blocking the standing server
# (Mem0 async-default; CONTRACT C1: name the dark leg, never block the beat). The dark marker IS the
# timeout's value. EDGE_CORTEX_TIMEOUT (seconds) tunes it per host; a small default keeps the beat live.
def _timeout_s():
    try:
        return float(os.environ.get("EDGE_CORTEX_TIMEOUT", "5"))
    except (TypeError, ValueError):
        return 5.0


def _driver_kwargs():
    """Connection timeouts for a fail-dark driver (N1/R3): bound BOTH the TCP connect and the pool
    acquisition so neither can hang the standing read door."""
    t = _timeout_s()
    return {"connection_timeout": t, "connection_acquisition_timeout": t}


def _q(text):
    """Wrap a cypher string in a neo4j.Query carrying the SERVER-SIDE execution timeout (N1/R3): the
    connection timeout bounds the CONNECT, this bounds the QUERY itself — an already-connected slow
    query darkens within the budget instead of hanging the standing server. Falls back to the bare
    string if the neo4j Query type is unavailable (the caller's outer guard still darkens)."""
    try:
        from neo4j import Query
        return Query(text, timeout=_timeout_s())
    except Exception:
        return text


@contextmanager
def _session(group, uri=None, user=None, password=None):
    """The ONE guarded connection seam (R7): open driver → yield a live neo4j session → always close.
    recall_subgraph, surf_subgraph, AND the cortex MCP all read the same self-graph; each used to
    re-implement this open/resolve/fail-dark/close boilerplate. Extracted here so the scaffolding
    lives in one place (a real three-call-site de-dup, not a speculative abstraction).

    This is the RUNTIME connection seam, POST-identity — its only failure mode is fail-DARK (C1,
    ADR-0011): YIELDS the session on success; YIELDS None on every genuine runtime degrade — the
    neo4j driver absent, the graph unreachable/unverifiable, or a guarded credential resolution that
    raised on a misconfigured install. NEVER raises (a transient outage darkens only this leg); the
    driver is closed in `finally` regardless. Callers branch on `s is None` for the dark marker.

    The fail-LOUD identity boundary (F6/N6, ADR-0015) does NOT live here — it is the caller's
    startup responsibility: the cortex MCP resolves `_identity.require_group()` ONCE at startup and
    refuses to serve an unidentified install BEFORE any tool runs (an unidentified install must not
    even reach this seam). recall_subgraph/surf_subgraph are the runtime-degrade callers whose
    documented contract is "None on no group" (compose_recall_brief/predispatch depend on a dark
    recall leg at wake, never a crash); they pass a falsy group here only as already-resolved, so the
    falsy-group → None branch is the runtime degrade, not the identity wall. Keeping the two failure
    classes at their correct layers is exactly ADR-0015's distinction (absent identity ≠ graph
    outage): the wall is loud at the server's startup seam, dark at this per-query connection."""
    if not group:
        yield None
        return
    try:
        uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
        user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
        password = password or os.environ.get("EDGE_NEO4J_PASSWORD") or _identity.neo4j_password()
    except Exception:
        yield None
        return
    try:
        from neo4j import GraphDatabase
    except Exception:
        yield None
        return
    drv = None
    try:
        drv = GraphDatabase.driver(uri, auth=(user, password), **_driver_kwargs())
        drv.verify_connectivity()   # the driver is LAZY — an unreachable graph fails HERE, not on
                                    # open; verify so a dark graph yields None (the dark leg), not a
                                    # live-looking session that explodes on the first s.run().
    except Exception:
        if drv is not None:
            try:
                drv.close()
            except Exception:
                pass
        yield None
        return
    try:
        with drv.session() as s:
            yield s
    finally:
        # Close the driver no matter what. An exception thrown back IN from the caller's body (a
        # mid-query outage) propagates out of the `with` — the callers each wrap the whole block in
        # `try/except: return None`, so it darkens their leg there. We must NOT swallow-and-re-yield
        # here (a generator may yield only once) — close, then let it propagate to the caller's guard.
        try:
            drv.close()
        except Exception:
            pass


def recall_subgraph(group=None, uri=None, user=None, password=None):
    """Read the SALIENT SUBGRAPH of the edge's own memory — space-0 (the :Genesis identity root)
    → the Objective → the active Directions (bets) → the salient Artefatos (most recent,
    slug+kernel) → the clusters they DISTILL — for `compose_recall_brief` to render. The agent
    then wakes with its own memory already in front of it (the push), rather than depending on
    remembering to recall (the dormant g.search() tale).

    Returns a dict
    ``{"codename","voice","objective","bets":[...],"artefatos":[{"slug","kernel"}],"clusters":[...]}``
    on success; **None** on a genuine degrade — no group, the neo4j driver absent, or the graph
    unreachable. NEVER raises (CONTRACT C1, ADR-0011: a transient outage darkens only this leg).
    The recall cypher is the space-0 traversal from `skills/_shared/memory.md`."""
    if not group:
        return None
    try:
        with _session(group, uri, user, password) as s:
            if s is None:
                return None
            # space-0 → objective → bets (active ANCHORS only) — the spine head
            head = s.run(_q(SPINE_QUERY), g=group).single()
            if head is None:
                return {"codename": None, "voice": None, "objective": None,
                        "bets": [], "artefatos": [], "clusters": []}
            # salient Artefatos (MOST RECENT, capped) + the clusters they DISTILL — reached via
            # SERVES. The salience guards (complete-projections-only, recency order, the cap,
            # the retired-cluster filter) live in the module-level query constants above.
            arts = s.run(_q(ARTEFATOS_QUERY), g=group, lim=RECALL_ARTEFATO_LIMIT).data()
            slugs = [a["slug"] for a in arts]
            clusters = [r["l"] for r in s.run(_q(CLUSTERS_QUERY), g=group, slugs=slugs)]
            return {
                "codename": head["codename"], "voice": head["voice"],
                "objective": head["objective"], "bets": [b for b in head["bets"] if b],
                "artefatos": [{"slug": a["slug"], "kernel": a.get("kernel")} for a in arts],
                "clusters": clusters,
            }
    except Exception:
        return None


def surf_subgraph(seeds, group=None, uri=None, user=None, password=None):
    """SURF the associative peer web from `seeds` — the multi-hop topology read a SELECT cannot do
    (Cortex-v1 brick-1). From the seed Artefato slugs it walks ONLY the typed associative edges
    (BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES, *1..2 hops, direction-agnostic) and returns
    the reachable peers as a list of ``{"slug","kernel","labels","hops"}`` dicts, ordered by hops
    then slug. SERVES (the degree-44 hub) is excluded STRUCTURALLY by omission — D-hangs-off-the-hub
    is never surfed.

    The seam (research R1): this also OFFERS candidate priors for the producer to author typed
    lineage FROM — the wiring into authoring context is the L6 doc, not this function.

    Returns the peer list on success; **None** on a genuine degrade — no seeds, no group, the neo4j
    driver absent, or the graph unreachable. NEVER raises (CONTRACT C1, ADR-0011): this reuses
    `recall_subgraph`'s degrade scaffolding verbatim — a transient outage darkens only this leg."""
    if not seeds:
        return None
    # Identity resolution is GUARDED (CONTRACT C1, review FIX-2): `_identity.group()` can raise on a
    # misconfigured install — that must darken this leg, never propagate. The connection scaffolding
    # (driver open / password resolve / fail-dark / close) is the shared `_session` helper (R7).
    try:
        group = group or _identity.group()
        if not group:
            return None
        with _session(group, uri, user, password) as s:
            if s is None:
                return None
            rows = s.run(_q(SURF_QUERY), g=group, seeds=list(seeds)).data()
            # the Entity/Community bridge (ticket D) — same session, additive; a graph with no
            # :Community yet simply matches nothing. Dedupe by slug keeping the MIN hops: a peer
            # reachable both ways keeps its direct associative rank; a bridge-only sibling joins
            # with its honest hop count (4) and the community it crossed (`via`).
            bridge = s.run(_q(SURF_BRIDGE_QUERY), g=group, seeds=list(seeds)).data()
            out = {}
            for r in rows + bridge:
                peer = {"slug": r["slug"], "kernel": r.get("kernel"),
                        "labels": r.get("labels"), "hops": r["hops"]}
                if r.get("via"):
                    peer["via"] = r["via"]
                prev = out.get(r["slug"])
                if prev is None or peer["hops"] < prev["hops"]:
                    out[r["slug"]] = {**(prev or {}), **peer}
                elif prev is not None and "via" in peer and "via" not in prev:
                    prev["via"] = peer["via"]   # keep the direct rank, still name the cluster
            return sorted(out.values(), key=lambda r: (r["hops"], r["slug"]))
    except Exception:
        return None


BANNER = ("<!-- generated by tools/recall.py — the memory-salient brief (ADR-0014); "
          "the push seeds, navigation deepens -->")


def compose_recall_brief(subgraph=_AUTO, group=None):
    """Render the memory-salient brief as one markdown string — a standalone surface, PEER to the
    briefing and the delta (ADR-0014), never a section of either. `subgraph` left unset
    auto-fetches via recall_subgraph() for `group` (defaults to EDGE_GROUP / the install identity)
    and degrades to the dark-leg marker on outage; pass it explicitly to stay hermetic (tests).
    Begins at SPACE 0 (the :Genesis identity root), then objective → bets → salient artefatos →
    clusters. None → an honest dark marker; NEVER a crash (CONTRACT C1)."""
    if subgraph is _AUTO:
        g = group if group is not None else _identity.group()
        subgraph = recall_subgraph(g)
    if subgraph is None:
        return (BANNER + "\n# Recall — the memory-salient brief\n\n"
                "_Recall leg DARK (graph offline or no group) — the salient subgraph could not be "
                "pushed this wake. Orient from the briefing and the delta; recall on demand from "
                "your own graph (`skills/_shared/memory.md`) when the graph is reachable._\n")
    parts = [BANNER + "\n# Recall — the memory-salient brief",
             "_Begin at **space 0** (your :Genesis identity — method + personality). This salient "
             "subgraph is PUSHED so you wake holding your own memory; recall MORE on demand "
             "(`skills/_shared/memory.md`: structural traversal + semantic search of past Artefatos)._"]
    cn, voice = subgraph.get("codename"), subgraph.get("voice")
    if cn or voice:
        parts.append(f"- **space-0 (identity):** {cn or '_codename_'}" + (f" — {voice}" if voice else ""))
    obj = subgraph.get("objective")
    parts.append(f"- **Objective (the hub):** {obj}" if obj else "- **Objective (the hub):** _none projected yet_")
    bets = subgraph.get("bets") or []
    parts.append("- **Active bets (Directions):** " + ("; ".join(bets) if bets else "_none anchored_"))
    arts = subgraph.get("artefatos") or []
    if arts:
        lines = "\n".join(f"  - **{a['slug']}** — {a.get('kernel') or '_no kernel_'}" for a in arts)
        parts.append("- **Salient Artefatos (build on, don't repeat):**\n" + lines)
    else:
        parts.append("- **Salient Artefatos:** _none projected yet_")
    clusters = subgraph.get("clusters") or []
    parts.append("- **Distilled clusters:** " + ("; ".join(clusters) if clusters else "_none yet_"))
    return "\n".join(parts) + "\n"
