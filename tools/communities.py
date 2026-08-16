"""communities — Modulo 2 (Cortex): automatic consolidation + navigation of knowledge clusters.

The organ that ended the empty-clusters era (experiment 2026-07-05, aceite 4/4): the graph's
extracted entities consolidate into Community nodes WITHOUT a human in the flow path — label
propagation (small-N-appropriate; graphiti 0.29.1's native build_communities deadlocks on this
install, registered) + twin-merge + one LLM summary per community + last_touched recency.
Curadoria humana fica onde erro machuca (harm-bearing), nunca como porteiro da vazao.

READ navigation is exposed through the Modulo-2 door (cortex.communities/community/locate —
late-binding, ADR-0019); the WRITE side (consolidate) is called by sweep/heartbeat directly,
mirroring the eventlog split (writes direct, reads through the door). The READ adapters are
lazy imports that degrade DARK (None), the same contract as briefing.graph_clusters; the WRITE
one does NOT — `consolidate` raises ConsolidationFailed, because a write that could not happen
is a failure and not an empty result (#635). This module imports bare (no top-level
neo4j/urllib) so bare-python callers can hold the door.
"""
import json
import os
import time
import uuid as uuidlib
from collections import Counter, defaultdict

_AUTO = object()   # "resolva pelo seam" — DISTINTO de None/"" , que significam "sem grupo"


class ConsolidationFailed(RuntimeError):
    """`consolidate()` NÃO conseguiu agrupar — distinto de `[]` ("não havia o que agrupar").

    O dente da #635. `consolidate()` devolvia None em três situações que são coisas diferentes
    — sem grupo, sem driver, e grafo inalcançável/erro no meio — e o chamador (`sweep`) fazia
    `len(written or [])` e imprimia "0 clusters" para TODAS. Um grafo que não pôde ser
    consolidado lia-se, no terminal do operador, idêntico a um grafo que ainda não tem o que
    consolidar. Foi essa indistinção que fez o apagão (identidade lida em tempo de import,
    corrigido no PR #603) passar por ESCASSEZ durante meses: a frota inteira imprimia
    "0 clusters" e ninguém viu falha nenhuma.

    Ausência de resultado só é sucesso quando o órgão RODOU. Falha em rodar é falha, e falha
    tem que ser alta.

    O vocabulário é o de `group_health.verdicts` (#638), não um terceiro inventado:
      · `dark` — NÃO PUDE rodar (sem identidade de grupo, sem Bolt). Nada foi medido, o que é
        MUITO diferente de "tudo bem": lá o `main` já sai 2 nesse caso.
      · `fail` — rodei contra o grafo e quebrei no meio.
    `.severity` é essa palavra, `.reason` é a máquina (`no-group` · `graph-unreachable` ·
    `graph-error`), `.detail` é o humano. Nenhuma das três é `[]`."""

    SEVERITIES = {"no-group": "dark", "graph-unreachable": "dark", "graph-error": "fail"}

    def __init__(self, reason, detail=""):
        self.reason = reason
        self.severity = self.SEVERITIES.get(reason, "fail")
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _resolve_group(group):
    """O grupo efetivo. `_AUTO` (o default) resolve pelo seam; None ou "" são uma INSTRUÇÃO
    explícita do chamador — sem grupo — e continuam sem grupo.

    Antes o default era None e o corpo fazia `group or _group()`, o que apaga a diferença: um
    None explícito virava "resolva um pra mim" e a chamada caía no grafo do install. Era
    invisível enquanto a identidade vinha só de EDGE_GROUP (quase sempre ausente em teste);
    passou a morder quando a resolução ganhou o agent.yaml."""
    return _group() if group is _AUTO else group


def _group():
    """O grupo, resolvido pelo seam único (ADR-0015) e SOB DEMANDA.

    Era uma constante de módulo lendo a variável de ambiente do grupo direto, no topo do arquivo:
    um segundo seam E um cache de identidade em tempo de import — o mesmo par que
    test_sweep_has_no_import_time_identity_cache já proíbe no sweep. Cache de identidade no import
    guarda a identidade de quem importou, não a do install que vai ser consultado."""
    import _identity
    return _identity.group()


# --- pure core (bare python; the internal seam the tests hold) ---

def label_propagation(node_ids, edges):
    """Deterministic label propagation: each node adopts the most frequent neighbour label,
    min-label tiebreak, sorted visit order — reproducible run-to-run (the Leiden small-N
    pathology is why this algorithm, not that one). Returns {node_id: label}."""
    nbr = defaultdict(set)
    for a, b in edges:
        nbr[a].add(b)
        nbr[b].add(a)
    label = {n: n for n in node_ids}
    order = sorted(label)
    for _ in range(30):
        changed = 0
        for u in order:
            if not nbr[u]:
                continue
            cnt = Counter(label[v] for v in nbr[u] if v in label)
            if not cnt:
                continue
            top = max(cnt.values())
            best = min(l for l, c in cnt.items() if c == top)
            if best != label[u]:
                label[u] = best
                changed += 1
        if not changed:
            break
    return label


def cluster(node_ids, edges, min_size=3):
    """Label-prop → groups of >= min_size (dust is dropped, DECLARED by the caller's count).
    Groups sorted by size desc then member order — deterministic."""
    label = label_propagation(node_ids, edges)
    groups = defaultdict(list)
    for n in sorted(node_ids):
        groups[label[n]].append(n)
    kept = [g for g in groups.values() if len(g) >= min_size]
    return sorted(kept, key=lambda g: (-len(g), g))


def merge_pass(groups, edges, min_cross=2):
    """Twin fix (user-feedback #3): two groups joined by >= min_cross cross-edges are one theme
    split by propagation — merge them. Edges are canonicalized (min,max) BEFORE counting: an
    undirected Cypher MATCH returns each edge twice, and one real edge must never trip
    min_cross=2 (codex [high]). Iterates to fixpoint; deterministic order."""
    groups = [sorted(g) for g in groups]
    canon = {(min(a, b), max(a, b)) for a, b in edges}
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                gi, gj = set(groups[i]), set(groups[j])
                cross = sum(1 for a, b in canon
                            if (a in gi and b in gj) or (a in gj and b in gi))
                if cross >= min_cross:
                    groups[i] = sorted(gi | gj)
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    return sorted(groups, key=lambda g: (-len(g), g))


def last_touched(member_dates):
    """Recency fold (user-feedback #2 — a navegacao pelo tempo): a community's last_touched is
    the MAX of its members' last-mention dates (ISO strings compare lexically); None-safe."""
    dates = [d for d in member_dates.values() if d]
    return max(dates) if dates else None


# --- adapters (lazy; degrade DARK = None, never raise — briefing.graph_clusters contract) ---

def _driver(uri=None, user=None, password=None):
    uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = password or os.environ.get("EDGE_NEO4J_PASSWORD")
    if not password:
        try:
            import _identity
            password = _identity.neo4j_password()
        except Exception:
            return None
    try:
        from neo4j import GraphDatabase
        return GraphDatabase.driver(uri, auth=(user, password))
    except Exception:
        return None


def communities(group=_AUTO, **kw):
    """The briefing §5 leg: [{uuid, name, summary, size, last_touched}] recency-desc.
    [] = graph reachable, no communities yet; None = dark."""
    group = _resolve_group(group)
    if not group:
        return None
    drv = _driver(**kw)
    if drv is None:
        return None
    try:
        with drv.session() as s:
            rows = s.run(
                "MATCH (c:Community {group_id:$g}) "
                "OPTIONAL MATCH (c)-[:HAS_MEMBER]->(e {group_id:$g}) "
                "OPTIONAL MATCH (ep:Episodic {group_id:$g})-[:MENTIONS]->(e) "
                "WITH c, count(DISTINCT e) AS size, "
                "max(coalesce(ep.valid_at, ep.created_at)) AS lt "
                "RETURN c.uuid AS uuid, c.name AS name, c.summary AS summary, size, "
                "toString(lt) AS last_touched ORDER BY lt DESC", g=group).data()
        return rows
    except Exception:
        return None


def community(ref, group=_AUTO, **kw):
    """One cluster in full: members (with last_mentioned) + provenance (source sessions via
    MENTIONS, artefatos via DISTILLS). ref = uuid or name. None = dark/not found."""
    group = _resolve_group(group)
    if not group:
        return None
    drv = _driver(**kw)
    if drv is None:
        return None
    try:
        with drv.session() as s:
            head = s.run(
                "MATCH (c:Community {group_id:$g}) WHERE c.uuid=$r OR c.name=$r "
                "RETURN c.uuid AS uuid, c.name AS name, c.summary AS summary LIMIT 1",
                g=group, r=ref).single()
            if not head:
                return None
            members = s.run(
                "MATCH (c:Community {uuid:$u})-[:HAS_MEMBER]->(e {group_id:$g}) "
                "OPTIONAL MATCH (ep:Episodic {group_id:$g})-[:MENTIONS]->(e) "
                "WITH e, max(coalesce(ep.valid_at, ep.created_at)) AS lm "
                "RETURN e.name AS name, coalesce(e.summary,'') AS summary, "
                "toString(lm) AS last_mentioned ORDER BY lm DESC",
                u=head["uuid"], g=group).data()
            sessions = s.run(
                "MATCH (c:Community {uuid:$u})-[:HAS_MEMBER]->(e {group_id:$g})"
                "<-[:MENTIONS]-(ep:Episodic {group_id:$g}) "
                "RETURN DISTINCT ep.name AS id, "
                "toString(max(coalesce(ep.valid_at, ep.created_at))) AS at "
                "ORDER BY at DESC LIMIT 12", u=head["uuid"], g=group).data()
            artefatos = [r["slug"] for r in s.run(
                "MATCH (c:Community {uuid:$u})-[:HAS_MEMBER]->(e {group_id:$g})"
                "<-[:DISTILLS]-(a:Artefato) "
                "RETURN DISTINCT coalesce(a.slug, a.name) AS slug",
                u=head["uuid"], g=group).data() if r["slug"]]
        return dict(head) | {"members": members, "sessions": sessions, "artefatos": artefatos}
    except Exception:
        return None


def locate(names, group=_AUTO, **kw):
    """JULGAR positioning: for each entity name, which community holds it (member), neighbours
    it (edge — RELATES_TO into a community), or none. None = dark."""
    group = _resolve_group(group)
    if not group:
        return None
    if not names:
        return {}
    drv = _driver(**kw)
    if drv is None:
        return None
    out = {}
    try:
        with drv.session() as s:
            for n in names:
                row = s.run(
                    "MATCH (e:Entity {group_id:$g, name:$n})<-[:HAS_MEMBER]-"
                    "(c:Community {group_id:$g}) "
                    "RETURN c.name AS c LIMIT 1", g=group, n=n).single()
                if row:
                    out[n] = {"community": row["c"], "relation": "member"}
                    continue
                row = s.run(
                    "MATCH (e:Entity {group_id:$g, name:$n})-[:RELATES_TO]-(x {group_id:$g})"
                    "<-[:HAS_MEMBER]-(c:Community {group_id:$g}) RETURN c.name AS c LIMIT 1",
                    g=group, n=n).single()
                out[n] = ({"community": row["c"], "relation": "neighbor"} if row
                          else {"community": None, "relation": "none"})
        return out
    except Exception:
        return None


def _default_summarize(members_text):
    """One-shot name+summary pelo modelo de chat do host (gpt-5.6-luna neste install); injected in tests. Raises on transport error —
    consolidate catches and degrades."""
    import urllib.request
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps({"model": "gpt-5.6-luna", "max_completion_tokens": 300, "messages": [{
            "role": "user",
            "content": "Estas entidades formam um cluster de conhecimento das sessões de "
                       "trabalho de um operador. Dê um NOME curto (3-6 palavras, PT-BR) e um "
                       "SUMÁRIO de 2-3 frases. Formato: NOME: ... | SUMÁRIO: ...\n\n"
                       + members_text}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return body["choices"][0]["message"]["content"].strip()


def consolidate(group=_AUTO, summarize_fn=None, min_size=3, min_cross=2, **kw):
    """The offline consolidation sweep (WRITE side — called by heartbeat/sweep, NOT the door):
    entities+RELATES_TO → cluster() → merge_pass() → summarize each → wipe-rebuild Community/
    HAS_MEMBER (their own lifecycle; the log stays the truth, ADR-0006).

    Returns the list of {name, size} written — `[]` means the sweep RAN and there was nothing to
    group (no entities, or every candidate was dust). It NEVER returns None: a consolidation that
    could not run raises `ConsolidationFailed`, because the read side's dark contract (None) is
    wrong for a WRITE — a write that did not happen is not "no data", it is a failure, and it
    must reach the operator as one. Dust count is logged, never silent."""
    group = _resolve_group(group)
    if not group:
        raise ConsolidationFailed(
            "no-group", "sem identidade de grupo (EDGE_GROUP ou agent.yaml name/codename) — "
            "nada foi lido nem escrito no grafo")
    drv = _driver(**kw)
    if drv is None:
        raise ConsolidationFailed(
            "graph-unreachable", f"sem driver Neo4j para o grupo {group!r} "
            "(bolt fora, ou senha ausente em EDGE_NEO4J_PASSWORD / _identity)")
    summarize_fn = summarize_fn or _default_summarize
    try:
        with drv.session() as s:
            # ed: no edge-owned schema on :Community. graphiti already indexes Community(uuid)
            # and Community(group_id); a CREATE CONSTRAINT on Community(uuid) is rejected by
            # Neo4j (Schema.IndexAlreadyExists — a constraint's backing index duplicates the
            # existing one, name-independent), and the outer except swallowed it → silent
            # "0 clusters" on every host graphiti touched first. uuids are uuid4 (unique by
            # construction) and consolidate wipe-rebuilds each run, so no constraint is needed.
            # codex [medium]: uuid é load-bearing — nulos ficam fora do clustering
            ents = s.run("MATCH (n:Entity {group_id:$g}) WHERE n.uuid IS NOT NULL "
                         "RETURN n.uuid AS u, n.name AS name, "
                         "coalesce(n.summary,'') AS summ", g=group).data()
            rels = s.run("MATCH (a:Entity {group_id:$g})-[:RELATES_TO]-(b:Entity {group_id:$g}) "
                         "WHERE a.uuid IS NOT NULL AND b.uuid IS NOT NULL "
                         "RETURN a.uuid AS a, b.uuid AS b", g=group).data()
        ids = [e["u"] for e in ents]
        by_id = {e["u"]: e for e in ents}
        edges = [(r["a"], r["b"]) for r in rels]
        groups = merge_pass(cluster(ids, edges, min_size=min_size), edges, min_cross=min_cross)
        print(f"communities: {len(ents)} entities -> {len(groups)} clusters "
              f"(+{len(ids) - sum(len(g) for g in groups)} poeira fora)")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        written = []
        # sumários FORA da transação (LLM é lento; tx segura só as escritas)
        payloads = []
        for g in groups:
            members = "\n".join(f"- {by_id[u]['name']}: {by_id[u]['summ'][:150]}"
                                for u in g[:25])
            try:
                out = summarize_fn(members)
            except Exception as e:
                print(f"communities: summarize degraded ({type(e).__name__}) — cluster sem sumário")
                out = f"NOME: cluster de {len(g)} entidades | SUMÁRIO: (sumário indisponível)"
            name = out.split("|")[0].replace("NOME:", "").strip()[:80]
            summ = out.split("SUMÁRIO:")[-1].strip() if "SUMÁRIO:" in out else out
            payloads.append((str(uuidlib.uuid4()), name, summ, g))

        def _rebuild(tx):
            # codex [high]: wipe+rebuild numa transação só — falha no meio = rollback, o
            # conjunto velho sobrevive. ponytail: single-writer (heartbeat); se surgir
            # escritor concorrente, o degrau seguinte é run-id swap.
            tx.run("MATCH (c:Community {group_id:$g}) DETACH DELETE c", g=group)
            for cu, name, summ, g in payloads:
                tx.run("CREATE (c:Community {uuid:$u, name:$n, summary:$s, group_id:$gr, "
                       "created_at:$t})", u=cu, n=name, s=summ, gr=group, t=now)
                for u in g:
                    tx.run("MATCH (c:Community {uuid:$cu}),"
                           "(n:Entity {uuid:$eu, group_id:$gr}) "
                           "CREATE (c)-[:HAS_MEMBER]->(n)", cu=cu, eu=u, gr=group)

        with drv.session() as s:
            s.execute_write(_rebuild)
        return [{"name": n, "size": len(g)} for _, n, _, g in payloads]
    except Exception as e:
        # ed: never swallow silently — a swallowed consolidate reads identically to an empty
        # graph ("0 clusters"), which hid the schema-name collision above for weeks. The
        # traceback stays (it is the only diagnosis of a mid-write failure) and the failure now
        # PROPAGATES: the caller decides how loud, and `edge-python -c "...consolidate()"`
        # exits non-zero instead of printing a reassuring None.
        import traceback; traceback.print_exc()
        raise ConsolidationFailed("graph-error", f"{type(e).__name__}: {e}") from e
