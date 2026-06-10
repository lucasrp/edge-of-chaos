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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _identity  # noqa: E402

# The SALIENT slice — cap the artefatos in the brief so it does not grow with the whole corpus
# (Codex P2). A small, most-recent slice; recall MORE on demand.
RECALL_ARTEFATO_LIMIT = 8

_AUTO = object()


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
    uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = password or os.environ.get("EDGE_NEO4J_PASSWORD") or _identity.neo4j_password()
    try:
        from neo4j import GraphDatabase
    except Exception:
        return None
    try:
        drv = GraphDatabase.driver(uri, auth=(user, password))
    except Exception:
        return None
    try:
        with drv.session() as s:
            # space-0 → objective → bets (active ANCHORS only) — the spine head
            head = s.run(
                "MATCH (gen:Genesis {group_id:$g}) "
                "OPTIONAL MATCH (gen)-[:GROUNDS]->(o:Objective {group_id:$g}) "
                "OPTIONAL MATCH (o)-[:ANCHORS]->(d:Direction {group_id:$g}) "
                "RETURN gen.codename AS codename, gen.voice AS voice, o.body AS objective, "
                "collect(DISTINCT d.body) AS bets", g=group).single()
            if head is None:
                return {"codename": None, "voice": None, "objective": None,
                        "bets": [], "artefatos": [], "clusters": []}
            # salient Artefatos (MOST RECENT, capped) + the clusters they DISTILL — reached via
            # SERVES. Push ONLY COMPLETE projections (Codex P2): `projection_complete = true` so a
            # half-projected node (an outage mid-rebuild — stale kernel / missing DISTILLS) is NOT
            # surfaced as reliable memory; recovery replays it, and the next brief picks it up once
            # complete. Order by `projected_at` (recency) DESC and LIMIT to the salient slice, so
            # the brief does NOT grow with the whole corpus. Legacy nodes sort last (coalesce to '').
            arts = s.run(
                "MATCH (a:Artefato {group_id:$g})-[:SERVES]->(:Objective {group_id:$g}) "
                "WHERE a.projection_complete = true "
                "RETURN a.slug AS slug, a.kernel AS kernel "
                "ORDER BY coalesce(a.projected_at,'') DESC, a.slug LIMIT $lim",
                g=group, lim=RECALL_ARTEFATO_LIMIT).data()
            # clusters derived from the SAME salient slice (Codex P2): only the clusters the pushed
            # artefatos distill, not every Artefato in the group — so the recall stays salient and
            # does not grow with the whole corpus. ACTIVE clusters only (Codex P2): mirror
            # graph_clusters/the projection resolver — a stale DISTILLS edge to a later-archived/
            # merged cluster must NOT surface a retired cluster in the brief.
            slugs = [a["slug"] for a in arts]
            clusters = [r["l"] for r in s.run(
                "MATCH (a:Artefato {group_id:$g})-[:DISTILLS]->(e:Entity {group_id:$g}) "
                "WHERE a.slug IN $slugs AND e.curated_cluster IS NOT NULL "
                "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
                "RETURN DISTINCT e.curated_cluster AS l ORDER BY l", g=group, slugs=slugs)]
            return {
                "codename": head["codename"], "voice": head["voice"],
                "objective": head["objective"], "bets": [b for b in head["bets"] if b],
                "artefatos": [{"slug": a["slug"], "kernel": a.get("kernel")} for a in arts],
                "clusters": clusters,
            }
    except Exception:
        return None
    finally:
        try:
            drv.close()
        except Exception:
            pass


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
        g = group if group is not None else (os.environ.get("EDGE_GROUP") or _identity.group())
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
