"""recall — the memory-salient brief, the THIRD independent brief at pre-dispatch (ADR-0014).
Genotype tool.

Recall is a noun — the yield of recalling, exactly as Delta is the yield of updating: the salient
subgraph of the Cortex, rooted at space-0, handed to the agent as a brief PEER to the briefing
(assemble) and the delta — never fused with either (the subject boundary: delta reads the world,
recall reads the self). This supersedes the recall-push-inside-assemble placement (4428c64,
briefing §7): the briefing returns to its four parts; this module owns the leg.

The push seeds; navigation deepens (ADR-0011 reaffirmed): the brief is the mechanical salience
push — on-demand Cortex navigation stays the loop's own judgment (`skills/_shared/memory.md`).

**Dual graph entry (operator 2026-07-13):** wake still opens at **space-0** (structural push).
That is not the only door — any task may jump in via **common semantic search**
(`semantic_search` / `compose_semantic_brief`) over projected Artefato embeddings. Degrade
contract unchanged (CONTRACT C1): a dark graph/embedder yields an honest marker, never a crash.
"""
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _identity  # noqa: E402
import cortex  # noqa: E402

# The SALIENT slice — cap the artefatos in the brief so it does not grow with the whole corpus
# (Codex P2). A small, most-recent slice; recall MORE on demand.
RECALL_ARTEFATO_LIMIT = 8
RECALL_EXPERIMENT_LIMIT = 6
RECALL_ASSET_LIMIT = 8
RECALL_ATIVIDADE_LIMIT = 8
SEMANTIC_SEARCH_LIMIT = 8
SEMANTIC_EMBED_MODEL = "text-embedding-3-small"  # same model as publisher project_artefato
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
    "WHERE a.projection_complete = true AND coalesce(a.kind,'published') <> 'asset' "
    "RETURN a.slug AS slug, a.kernel AS kernel "
    "ORDER BY coalesce(a.projected_at,'') DESC, a.slug LIMIT $lim")
EXPERIMENTS_QUERY = (
    "MATCH (x:Experiment {group_id:$g}) "
    "WHERE x.projection_complete = true "
    "OPTIONAL MATCH (a:Artefato {group_id:$g})-[:REPORTS_ON]->(x) "
    "RETURN x.id AS id, x.title AS title, x.claim AS claim, x.status AS status, "
    "x.scope AS scope, coalesce(x.report_slug, x.canonical_report) AS report_slug, "
    "collect(DISTINCT a.slug) AS reports, "
    "coalesce(x.curated_at,x.declared_at,x.projected_at,'') AS sort_key "
    "ORDER BY sort_key DESC, id LIMIT $lim")
ASSETS_QUERY = (
    "MATCH (a:Artefato {group_id:$g}) "
    "WHERE a.kind='asset' AND a.projection_complete = true "
    "MATCH (p:Artefato {group_id:$g})-[:HAS_ASSET]->(a) "
    "RETURN a.slug AS slug, a.asset_kind AS kind, a.asset_role AS role, a.page AS page, "
    "a.skill AS skill, p.slug AS parent_slug "
    "ORDER BY coalesce(a.projected_at,'') DESC, a.slug LIMIT $lim")
# Employment spine from the projected graph (project_lentes), not the eventlog fold.
# Only open/reaberta — abandonada/cumprida stay out of the default agent push.
# Display ref prefers operacao/num (fold shape edge/atv-NNN) over raw atividade:ulid.
ATIVIDADES_QUERY = (
    "MATCH (a:Atividade {group_id:$g}) "
    "WHERE a.estado IN ['aberta', 'reaberta'] "
    "RETURN a.ref AS raw_ref, a.num AS num, a.operacao AS operacao, "
    "a.finalidade AS finalidade, a.estado AS estado, a.tier AS tier "
    "ORDER BY coalesce(a.num,'') DESC LIMIT $lim")
CLUSTERS_QUERY = (
    "MATCH (a:Artefato {group_id:$g})-[:DISTILLS]->(e:Entity {group_id:$g}) "
    "WHERE a.slug IN $slugs AND e.curated_cluster IS NOT NULL "
    "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
    "RETURN DISTINCT e.curated_cluster AS l ORDER BY l")
# The SURF query — the topology read a SELECT cannot do (Cortex-v1 brick-1, schema report
# `the-graph-you-filled-like-a-list`, move 2). From the seed Artefatos it walks ONLY the typed
# associative peer web — BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES|SUPPORTS|REFUTES|
# REPORTS_ON — direction-agnostic, bounded to *1..2 hops, and returns the reachable
# Artefatos/Sources/Experiments. SERVES (the degree-44
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
    # Ticket A (ontologia §2c): SUPPORTS|REFUTES join the associative walk (an artefato bearing on
    # a hypothesis IS associative signal); QUALIFIES/INCONCLUSIVE stay out (annotation weight).
    "MATCH p=(seed)-[:BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES|SUPPORTS|REFUTES|REPORTS_ON*1..2]-(n) "
    # A peer is keyed by its slug (Artefato), key (Source), or experiment_id/id (Experiment): use the
    # same coalesce for BOTH self-exclusion and returned ref, so surf → cortex_node drill-down resolves
    # every terminal type.
    "WHERE (n:Artefato OR n:Source OR n:Experiment) AND n.group_id=$g "
    "AND NOT coalesce(n.slug, n.key, n.experiment_id, n.id) IN $seeds "
    "AND all(x IN nodes(p) WHERE x.group_id=$g) "
    "RETURN DISTINCT coalesce(n.slug, n.key, n.experiment_id, n.id) AS slug, "
    "coalesce(n.kernel, n.claim, n.title) AS kernel, labels(n) AS labels, "
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
# Common semantic entry — complete Artefatos with content embedding (publisher project).
SEMANTIC_ARTEFATOS_QUERY = (
    "MATCH (a:Artefato {group_id:$g}) "
    "WHERE a.projection_complete = true AND a.embedding IS NOT NULL "
    "AND coalesce(a.kind,'published') <> 'asset' "
    "RETURN a.slug AS slug, a.kernel AS kernel, a.embedding AS embedding")

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
    ``{"codename","voice","objective","bets":[...],"artefatos":[...],"clusters":[...],
    "experiments":[...],"assets":[...],"atividades":[{"ref","num","finalidade","estado",...}]}``
    on success; **None** on a genuine degrade — no group, the neo4j driver absent, or the graph
    unreachable. NEVER raises (CONTRACT C1, ADR-0011: a transient outage darkens only this leg).
    ``atividades`` are open/reaberta nodes from the projected graph (employment spine) — cortex as
    graph for the agent, not only portfolio_at ledger. The recall cypher is the space-0 traversal
    from `skills/_shared/memory.md`."""
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
                        "bets": [], "artefatos": [], "clusters": [],
                        "experiments": [], "assets": [], "atividades": []}
            # salient Artefatos (MOST RECENT, capped) + the clusters they DISTILL — reached via
            # SERVES. The salience guards (complete-projections-only, recency order, the cap,
            # the retired-cluster filter) live in the module-level query constants above.
            arts = s.run(_q(ARTEFATOS_QUERY), g=group, lim=RECALL_ARTEFATO_LIMIT).data()
            slugs = [a["slug"] for a in arts]
            clusters = [r["l"] for r in s.run(_q(CLUSTERS_QUERY), g=group, slugs=slugs)]
            try:
                experiments = s.run(_q(EXPERIMENTS_QUERY), g=group,
                                    lim=RECALL_EXPERIMENT_LIMIT).data()
            except Exception:
                experiments = []
            try:
                assets = s.run(_q(ASSETS_QUERY), g=group, lim=RECALL_ASSET_LIMIT).data()
            except Exception:
                assets = []
            try:
                atividades = s.run(_q(ATIVIDADES_QUERY), g=group,
                                   lim=RECALL_ATIVIDADE_LIMIT).data()
            except Exception:
                atividades = []
            return {
                "codename": head["codename"], "voice": head["voice"],
                "objective": head["objective"], "bets": [b for b in head["bets"] if b],
                "artefatos": [{"slug": a["slug"], "kernel": a.get("kernel")} for a in arts],
                "clusters": clusters,
                "experiments": [{"id": e.get("id"), "title": e.get("title"),
                                 "claim": e.get("claim"), "status": e.get("status"),
                                 "scope": e.get("scope"), "report_slug": e.get("report_slug"),
                                 "reports": e.get("reports") or []}
                                for e in experiments if e.get("id")],
                "assets": [{"slug": a.get("slug"), "kind": a.get("kind"), "role": a.get("role"),
                            "page": a.get("page"), "skill": a.get("skill"),
                            "parent_slug": a.get("parent_slug")}
                           for a in assets if a.get("slug")],
                "atividades": [_atividade_row(a) for a in atividades],
            }
    except Exception:
        return None


def _atividade_row(row):
    """Normalize a projected Atividade row for the agentic brief."""
    num = row.get("num")
    operacao = row.get("operacao")
    if isinstance(operacao, str) and operacao.strip() and isinstance(num, str) and num.strip():
        ref = f"{operacao.strip()}/{num.strip()}"
    elif isinstance(num, str) and num.strip():
        ref = num.strip()
    else:
        raw = row.get("raw_ref")
        ref = raw.strip() if isinstance(raw, str) and raw.strip() else None
    return {
        "ref": ref,
        "num": num,
        "operacao": operacao,
        "finalidade": row.get("finalidade"),
        "estado": row.get("estado"),
        "tier": row.get("tier"),
    }

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
            # :Community yet simply matches nothing. ADDITIVE means a bridge-only failure (a
            # timeout, an old graph) darkens to "no siblings" — never discarding the direct rows
            # already in hand (codex #6). Dedupe by slug keeping the MIN hops: a peer reachable
            # both ways keeps its direct associative rank; a bridge-only sibling joins with its
            # honest hop count (4) and the community it crossed (`via`).
            try:
                bridge = s.run(_q(SURF_BRIDGE_QUERY), g=group, seeds=list(seeds)).data()
            except Exception:
                bridge = []
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
SEMANTIC_BANNER = ("<!-- generated by tools/recall.py — common semantic entry (not space-0); "
                   "query → ranked Artefatos by embedding cosine -->")


def _default_embed_fn(text):
    """Best-effort OpenAI embedder (same model as project_artefato). Raises on hard failure so
    callers can darken; never invents a vector.

    Loads the install's ``secrets/`` into the env (same seam as sweep/publisher) so a paid
    OpenAI key in ``secrets/openai.env`` is visible without requiring the caller to export it.
    The phenotype's embedding adapter (llm_routes.embed_fn — openai direto, openrouter,
    azure/base_url) wins when wired; the legacy OpenAI call is the fallback.
    """
    try:
        import llm_routes
        fn = llm_routes.embed_fn()
        if fn is not None:
            return fn(text)
    except Exception:
        pass  # adapter dark/malformed → estrada legada abaixo
    try:
        import _secrets
        _secrets.load_env(_identity._env_dir(_identity.AGENT_YAML))
    except Exception:
        pass  # env may already hold OPENAI_API_KEY; OpenAI() still fails loud if missing
    from openai import OpenAI
    return OpenAI().embeddings.create(
        model=SEMANTIC_EMBED_MODEL, input=text,
    ).data[0].embedding

def _read_semantic_corpus(group, uri=None, user=None, password=None):
    """Load (slug, kernel, embedding) rows for semantic_search. None on degrade."""
    if not group:
        return None
    try:
        with _session(group, uri, user, password) as s:
            if s is None:
                return None
            rows = s.run(_q(SEMANTIC_ARTEFATOS_QUERY), g=group).data()
            out = []
            for r in rows:
                emb = r.get("embedding")
                if not emb or not isinstance(emb, (list, tuple)):
                    continue
                slug = r.get("slug")
                if not isinstance(slug, str) or not slug.strip():
                    continue
                out.append({
                    "slug": slug.strip(),
                    "kernel": r.get("kernel"),
                    "embedding": list(emb),
                })
            return out
    except Exception:
        return None


def semantic_search(query, *, group=None, limit=SEMANTIC_SEARCH_LIMIT,
                    embed_fn=None, corpus=_AUTO, uri=None, user=None, password=None):
    """Common semantic graph entry: rank projected Artefatos by cosine(query, a.embedding).

    Dual entry with space-0 push — the agent (or skill) may start *here* with a free-text query
    instead of waking at Genesis and walking. Returns a list of
    ``{"slug","kernel","score"}`` (score in [0,1], best first) or **None** when dark
    (no query, no group, embedder failure, empty corpus). NEVER raises (CONTRACT C1).

    ``corpus`` is injectable for hermetic tests; live path reads Neo4j via SEMANTIC_ARTEFATOS_QUERY.
    """
    if not isinstance(query, str) or not query.strip():
        return None
    if limit is None or int(limit) < 1:
        return None
    limit = int(limit)
    try:
        g = group if group is not None else _identity.group()
    except Exception:
        return None
    if not g and corpus is _AUTO:
        return None
    if corpus is _AUTO:
        corpus = _read_semantic_corpus(g, uri=uri, user=user, password=password)
    if not corpus:
        return None
    embed = embed_fn or _default_embed_fn
    try:
        qv = embed(query.strip())
    except Exception:
        return None
    if not qv:
        return None
    ranked = []
    for row in corpus:
        emb = row.get("embedding")
        slug = row.get("slug")
        if not slug or not emb:
            continue
        try:
            score = float(cortex.cosine(qv, emb))
        except Exception:
            continue
        ranked.append({
            "slug": slug,
            "kernel": row.get("kernel"),
            "score": score,
        })
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r["score"], r["slug"]))
    return ranked[:limit]


def compose_semantic_brief(query, hits=_AUTO, *, group=None, limit=SEMANTIC_SEARCH_LIMIT,
                           embed_fn=None):
    """Render a short markdown brief for common semantic entry (peer to space-0 push, not a fuse).

    Pass ``hits`` explicitly for hermetic tests; leave unset to auto-run ``semantic_search``.
    Dark hits → honest marker **naming which leg failed** (corpus vs embedder), never a crash.
    """
    q = query.strip() if isinstance(query, str) else ""
    dark_reason = None
    if hits is _AUTO:
        if not q:
            hits, dark_reason = None, "empty query"
        else:
            try:
                g = group if group is not None else _identity.group()
            except Exception as e:
                g, dark_reason = None, f"group/identity: {type(e).__name__}: {e}"
            corpus = None
            if g and dark_reason is None:
                corpus = _read_semantic_corpus(g)
                if not corpus:
                    dark_reason = "empty corpus (no projection_complete Artefato with embedding)"
                    hits = None
            if dark_reason is None:
                try:
                    hits = semantic_search(
                        q, group=g, limit=limit, embed_fn=embed_fn, corpus=corpus)
                    if hits is None:
                        dark_reason = "embedder failed or ranked empty (check OpenAI quota/key)"
                except Exception as e:
                    hits, dark_reason = None, f"embedder: {type(e).__name__}: {e}"
            elif hits is _AUTO:
                hits = None
    if hits is None or hits is _AUTO:
        why = dark_reason or "no embedder, no corpus, or empty query"
        return (SEMANTIC_BANNER + "\n# Semantic search — common graph entry\n\n"
                f"_Query:_ {q or '_empty_'}\n\n"
                f"_Semantic leg DARK — {why}. Fall back to space-0 push "
                f"(`compose_recall_brief`) or structural cypher (`skills/_shared/memory.md`)._\n")
    lines = [
        SEMANTIC_BANNER,
        "# Semantic search — common graph entry",
        f"_Query:_ {q}",
        "_Not space-0: ranked by embedding cosine on projected Artefatos. Then surf/navigate "
        "from a hit slug if you need neighbors._",
        "",
        "## Hits",
    ]
    for h in hits:
        score = h.get("score")
        score_s = f"{score:.3f}" if isinstance(score, (int, float)) else "?"
        kernel = h.get("kernel") or "_no kernel_"
        lines.append(f"- **{h.get('slug')}** ({score_s}) — {kernel}")
    return "\n".join(lines) + "\n"


def enrich_recall_with_objective_semantic(recall_text, log=None, *, group=None,
                                          embed_fn=None, objective_fn=None):
    """Append dual-entry semantic brief seeded by the standing objective (employment wakes).

    Mechanical floor for "semantic as good as old edge" on wake — not an agentic affordance.
    Degrade-dark: always returns a string; never raises (CONTRACT C1).
    """
    base = recall_text if isinstance(recall_text, str) else ""
    try:
        if objective_fn is None:
            import cortex
            objective_fn = lambda: cortex.objective_at(log=log)  # noqa: E731
        obj = objective_fn() or {}
        body = (obj.get("body") if isinstance(obj, dict) else None) or ""
        body = body.strip() if isinstance(body, str) else ""
        if not body:
            return base + ("\n\n" + SEMANTIC_BANNER + "\n# Semantic search — common graph entry\n\n"
                           "_No standing objective body — semantic seed skipped._\n")
        # Seed with objective text (cap so embedders stay cheap).
        seed = body if len(body) <= 400 else body[:400].rsplit(" ", 1)[0]
        sem = compose_semantic_brief(seed, group=group, embed_fn=embed_fn)
        return base.rstrip() + "\n\n" + sem
    except Exception as e:  # noqa: BLE001
        return base.rstrip() + (
            f"\n\n{SEMANTIC_BANNER}\n# Semantic search — common graph entry\n\n"
            f"_Semantic enrich DARK ({type(e).__name__}: {e})._\n"
        )


def compose_mentee_persona_brief(root=None, *, max_perfil_chars=3500):
    """P1.5 — mentee persona from leveling-store (NOT the edge's Personality identity tattoo).

    Safe for wake/mentor recall: missing/blank perfil is declared empty, never silent.
    """
    root = Path(root) if root is not None else _identity.state_root() / "memory" / "leveling"
    parts = [
        "## Persona do mentee",
        "",
        "_Leveling-store (`memory/leveling/`) — who the **mentee** is. "
        "Distinct from briefing **Personality** (who the **edge** is)._ ",
        "",
    ]
    perfil = root / "perfil.md"
    if not perfil.exists() or not perfil.read_text(encoding="utf-8", errors="replace").strip():
        parts.append("_perfil vazio — leveling-store ainda não tem persona do mentorado._")
        return "\n".join(parts) + "\n"
    body = perfil.read_text(encoding="utf-8", errors="replace").strip()
    if len(body) > max_perfil_chars:
        body = body[:max_perfil_chars].rstrip() + "\n\n_…(perfil truncado)_"
    parts.append(body)
    mapa = root / "mapa.md"
    if mapa.exists():
        mapa_body = mapa.read_text(encoding="utf-8", errors="replace").strip()
        if mapa_body:
            # Short frontier: first non-empty content lines after title
            frontier = []
            for line in mapa_body.splitlines():
                if line.strip().startswith("#"):
                    continue
                if line.strip():
                    frontier.append(line.rstrip())
                if len(frontier) >= 8:
                    break
            if frontier:
                parts.extend(["", "### Fronteira (mapa)", ""] + frontier)
    return "\n".join(parts) + "\n"


def compose_recall_brief(subgraph=_AUTO, group=None, mentee_leveling_root=None):
    """Render the memory-salient brief as one markdown string — a standalone surface, PEER to the
    briefing and the delta (ADR-0014), never a section of either. `subgraph` left unset
    auto-fetches via recall_subgraph() for `group` (defaults to EDGE_GROUP / the install identity)
    and degrades to the dark-leg marker on outage; pass it explicitly to stay hermetic (tests).
    Begins at SPACE 0 (the :Genesis identity root), then objective → bets → salient artefatos →
    clusters. None → an honest dark marker; NEVER a crash (CONTRACT C1).

    Always appends **Persona do mentee** (leveling-store) — P1.5; not edge Personality.
    """
    persona = compose_mentee_persona_brief(root=mentee_leveling_root)
    if subgraph is _AUTO:
        g = group if group is not None else _identity.group()
        subgraph = recall_subgraph(g)
    if subgraph is None:
        return (BANNER + "\n# Recall — the memory-salient brief\n\n"
                "_Recall leg DARK (graph offline or no group) — the salient subgraph could not be "
                "pushed this wake. Orient from the briefing and the delta; recall on demand from "
                "your own graph (`skills/_shared/memory.md`) when the graph is reachable._\n\n"
                + persona)
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
    experiments = subgraph.get("experiments") or []
    if experiments:
        lines = []
        for e in experiments:
            title = e.get("title") or e.get("claim") or e.get("id")
            status = f" · {e.get('status')}" if e.get("status") else ""
            report = f" · report {e.get('report_slug')}" if e.get("report_slug") else ""
            lines.append(f"  - **{e.get('id')}** — {title}{status}{report}")
        parts.append("- **Native Experiments (scientific objects):**\n" + "\n".join(lines))
    else:
        parts.append("- **Native Experiments:** _none projected yet_")
    assets = subgraph.get("assets") or []
    if assets:
        lines = []
        for a in assets:
            parent = f" ← {a.get('parent_slug')}" if a.get("parent_slug") else ""
            kind = a.get("kind") or "asset"
            page = f" — {a.get('page')}" if a.get("page") else ""
            lines.append(f"  - **{a.get('slug')}** ({kind}){parent}{page}")
        parts.append("- **Generated Artefato assets (HTML/JS/data companions):**\n" + "\n".join(lines))
    else:
        parts.append("- **Generated Artefato assets:** _none projected yet_")
    # Graph employment spine (project_lentes Atividade nodes) — agentic cortex-as-graph.
    # Distinct from portfolio_at lanes: this is Neo4j, map-blind recall still carries it.
    atividades = subgraph.get("atividades") or []
    if atividades:
        lines = []
        for a in atividades:
            label = a.get("ref") or a.get("num") or "?"
            fin = a.get("finalidade") or "_sem finalidade_"
            estado = f" · {a.get('estado')}" if a.get("estado") else ""
            lines.append(f"  - **{label}** — {fin}{estado}")
        parts.append("- **Open Atividades (graph employment spine):**\n" + "\n".join(lines))
    else:
        parts.append("- **Open Atividades (graph employment spine):** _none open in graph_")
    parts.append("")
    parts.append(persona.rstrip())
    return "\n".join(parts) + "\n"

def _portfolio_text(item, key, lane):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"portfolio snapshot `{lane}` item `{key}` must be a non-blank string")
    return value


def _validate_portfolio_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("portfolio snapshot must be a dict")
    required_lanes = (
        "mapas_ativos", "atividades_perdidas", "contested", "agenda", "admissibilidade",
    )
    for lane in required_lanes:
        if lane not in snapshot:
            raise ValueError(f"portfolio snapshot missing `{lane}`")
        if not isinstance(snapshot[lane], list):
            raise ValueError(f"portfolio snapshot `{lane}` must be a list")
        if any(not isinstance(item, dict) for item in snapshot[lane]):
            raise ValueError(f"portfolio snapshot `{lane}` items must be dicts")

    for item in snapshot["mapas_ativos"]:
        _portfolio_text(item, "ref", "mapas_ativos")
        _portfolio_text(item, "titulo", "mapas_ativos")
        frontier = item.get("frontier")
        if (not isinstance(frontier, list)
                or any(not isinstance(layer, list) for layer in frontier)
                or any(not isinstance(ref, str) or not ref.strip()
                       for layer in frontier for ref in layer)):
            raise ValueError(
                "portfolio snapshot `mapas_ativos` item `frontier` must be a list of ref lists"
            )

    if "atividades" in snapshot:
        if not isinstance(snapshot["atividades"], list):
            raise ValueError("portfolio snapshot `atividades` must be a list")
        if any(not isinstance(item, dict) for item in snapshot["atividades"]):
            raise ValueError("portfolio snapshot `atividades` items must be dicts")
        for item in snapshot["atividades"]:
            _portfolio_text(item, "ref", "atividades")
            _portfolio_text(item, "finalidade", "atividades")

    for item in snapshot["atividades_perdidas"]:
        _portfolio_text(item, "ref", "atividades_perdidas")
        _portfolio_text(item, "finalidade", "atividades_perdidas")
        count = item.get("sessoes_sem_toque")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(
                "portfolio snapshot `atividades_perdidas` item `sessoes_sem_toque` "
                "must be a positive integer"
            )

    for item in snapshot["contested"]:
        _portfolio_text(item, "alvo", "contested")
        _portfolio_text(item, "detalhe", "contested")
        evidence = item.get("evidencia")
        if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
            raise ValueError(
                "portfolio snapshot `contested` item `evidencia` must be a non-blank string"
            )
        seq = item.get("seq")
        if seq is not None and (not isinstance(seq, int) or isinstance(seq, bool) or seq < 1):
            raise ValueError("portfolio snapshot `contested` item `seq` must be a positive integer")

    for item in snapshot["agenda"]:
        kind = item.get("tipo")
        if kind not in {"move", "pergunta"}:
            raise ValueError("portfolio snapshot `agenda` item `tipo` must be move or pergunta")
        _portfolio_text(item, "ref", "agenda")
        if kind == "move":
            _portfolio_text(item, "rationale", "agenda")
        else:
            text = item.get("texto")
            evaluation = item.get("eval")
            if ((not isinstance(text, str) or not text.strip())
                    and (not isinstance(evaluation, dict) or not evaluation)):
                raise ValueError(
                    "portfolio snapshot `agenda` pergunta needs non-blank `texto` or `eval`"
                )

    for item in snapshot["admissibilidade"]:
        kind = _portfolio_text(item, "tipo", "admissibilidade")
        if kind not in {"run", "fato"}:
            raise ValueError("portfolio snapshot `admissibilidade` item `tipo` must be run or fato")
        _portfolio_text(item, "ref", "admissibilidade")
        _portfolio_text(item, "leva", "admissibilidade")
        if item.get("admissibilidade") != "suspeita":
            raise ValueError(
                "portfolio snapshot `admissibilidade` item `admissibilidade` must be suspeita"
            )
        instrument = item.get("instrumento")
        if instrument is not None and (not isinstance(instrument, str) or not instrument.strip()):
            raise ValueError(
                "portfolio snapshot `admissibilidade` item `instrumento` "
                "must be a non-blank string"
            )


def compose_portfolio_recall_brief(subgraph=_AUTO, group=None, portfolio_fn=None,
                                   log=None, seq=None, ts=None):
    """Opt-in recall surface for the roles allowed to see the mentee's portfolio.

    ``compose_recall_brief`` remains the shared, map-blind default. Wake/mentor/recall callers
    cross this separate seam explicitly. ``group`` scopes only the Cortex leg; ``log``, ``seq``,
    and ``ts`` select the eventlog snapshot handed explicitly to ``portfolio_fn``.
    """
    if portfolio_fn is None:
        import portfolio
        portfolio_fn = portfolio.portfolio_at
    if log is None:
        import eventlog
        log = eventlog.LOG
    snapshot = portfolio_fn(log=log, seq=seq, ts=ts)
    _validate_portfolio_snapshot(snapshot)
    lines = ["# Portfolio — role-scoped orientation", "", "## Mapas ativos"]
    for active_map in snapshot.get("mapas_ativos", []):
        lines.append(f"- **{active_map.get('ref')}** — {active_map.get('titulo', '')}")
        for layer, tickets in enumerate(active_map.get("frontier", [])):
            lines.append(f"  - Layer {layer}: {', '.join(tickets)}")
    lines.extend(["", "## Atividades abertas"])
    open_refs = set()
    for activity in snapshot.get("atividades", []):
        ref = activity.get("ref")
        if isinstance(ref, str) and ref.strip():
            open_refs.add(ref)
        lines.append(
            f"- **{activity.get('ref')}** — {activity.get('finalidade', '')}"
        )
    lines.extend(["", "## Atividades perdidas"])
    # Exclusive of abertas: never dual-list the same ref under both sections.
    for activity in snapshot.get("atividades_perdidas", []):
        ref = activity.get("ref")
        if ref in open_refs:
            continue
        lines.append(
            f"- **{activity.get('ref')}** — {activity.get('finalidade', '')} "
            f"· {activity.get('sessoes_sem_toque')} sessões sem toque"
        )
    lines.extend(["", "## Contested — faixa reservada"])
    for item in snapshot.get("contested", []):
        evidence = f" · evidência {item['evidencia']}" if item.get("evidencia") else ""
        event_seq = f" · seq {item['seq']}" if item.get("seq") is not None else ""
        lines.append(f"- **{item['alvo']}** — {item['detalhe']}{evidence}{event_seq}")
    lines.extend(["", "## Agenda pull bounded"])
    for item in snapshot.get("agenda", []):
        kind = item.get("tipo")
        detail = (item.get("body") or item.get("rationale") or item.get("pergunta")
                  or item.get("texto")
                  or (f"eval {item['eval']}" if item.get("eval") else ""))
        locator = item.get("ref") or ""
        suffix = f" — {detail}" if detail else ""
        lines.append(f"- [{kind}] {locator}{suffix}")
    lines.extend(["", "## Admissibilidade suspeita"])
    for item in snapshot.get("admissibilidade", []):
        details = [f"leva {item.get('leva')}"]
        if item.get("instrumento"):
            details.append(f"instrumento {item['instrumento']}")
        details.append(str(item.get("admissibilidade")))
        lines.append(f"- [{item.get('tipo')}] **{item.get('ref')}** · " + " · ".join(details))
    return compose_recall_brief(subgraph=subgraph, group=group) + "\n" + "\n".join(lines) + "\n"
