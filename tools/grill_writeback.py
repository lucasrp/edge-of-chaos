"""grill_writeback — land the grill's decisions directly on the graph. Genotype tool (ADR-0005).

The grill never edits a page; it marks the graph, and the page re-renders (tools/wiki_render.py).
Each decision is a node property the render respects — `curated_name` (rename/retire),
`merged_into` (canonical-identity), `curated_cluster` (split/attach), `archived` (orphan) — plus
the grilled mark (`grilled_at` + outcome), the Convergence cursor that makes the next Lint a delta.
One source of truth: render / Lint / Aging all read the node.

Env: EDGE_NEO4J_URI/USER/PASSWORD
"""
from datetime import datetime, timezone
from pathlib import Path

import eventlog
import _identity

REPO = Path(__file__).resolve().parent.parent

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


# The persona files the grill writes back (grill-design.md; roberto ~/leveling prototype).
# perfil/mapa/curriculo are CURRENT-STATE (overwrite: who he is, the map, the curriculum);
# diario is APPEND-ONLY (the ordinal record — entries accrete, never wall-clock-windowed).
LEVELING_KINDS = ("perfil", "mapa", "curriculo", "diario")


def leveling(kind, content, root=None, log=eventlog.LOG):
    """Persona writeback (custo-de-reconstrução→0): append a `grill.leveling` event to the Tier-0
    log (ADR-0006 — the durable, replayable truth, locked+fsynced by eventlog), then render
    memory/leveling/{kind}.md (the readable projection the next grill opens with). Unknown kind or
    blank content is refused LOUD — a hollow persona file is worse than none (the same never-hollow
    rule the gate feeders follow). Returns the path written."""
    if kind not in LEVELING_KINDS:
        raise ValueError(f"leveling kind must be one of {LEVELING_KINDS}, got {kind!r}")
    if not (isinstance(content, str) and content.strip()):
        raise ValueError(f"refusing a blank leveling {kind} — a hollow persona file is worse than none")
    eventlog.append("grill.leveling", f"leveling:{kind}",
                    {"kind": kind, "content": content.strip()}, log=log)
    root = Path(root) if root else REPO / "memory" / "leveling"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{kind}.md"
    content = content.strip() + "\n"
    if kind == "diario":
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"\n---\n\n## {stamp}\n\n{content}" if path.exists() else f"## {stamp}\n\n{content}"
        with path.open("a") as f:
            f.write(entry)
    else:
        path.write_text(content)
    return path


def elect_canon(kind, ref, thread=None, log=eventlog.LOG):
    """Elege um objeto durável a CANÔNICO (issue #130 pontos 11/17) — açúcar sobre append_event. O
    rail é GERAL: kind ∈ {md, artefato, experimento}. Eleger = promover a índice da thread em que o
    objeto já está pendurado; a superfície é a curadoria de thread que o grill já faz (NENHUM comando
    'canon' novo pro operador). NUNCA emitido pelo inject — só pelo grill.

    Sem TTL: canônico ATÉ retire_canon; a longevidade emerge só de atos do grill (ponto 10). Kind
    desconhecido recusa loud (mesma regra never-hollow do resto do writeback)."""
    if kind not in eventlog.CANON_KINDS:
        raise ValueError(f"canon kind deve ser um de {eventlog.CANON_KINDS}, recebeu {kind!r}")
    return append_event("canon.elected", f"canon:{kind}:{ref}",
                        {"kind": kind, "ref": ref, "thread": thread}, log=log)


def retire_canon(kind, ref, reason=None, log=eventlog.LOG):
    """Des-elege um canônico (issue #130 ponto 9) — volta ao ordinal comum, SEM apagar (o log
    preserva; decay por escassez segue valendo). Açúcar sobre append_event."""
    if kind not in eventlog.CANON_KINDS:
        raise ValueError(f"canon kind deve ser um de {eventlog.CANON_KINDS}, recebeu {kind!r}")
    return append_event("canon.retired", f"canon:{kind}:{ref}",
                        {"kind": kind, "ref": ref, "reason": reason}, log=log)


def append_event(type, subject, payload, log=eventlog.LOG):
    """Persist a grill decision to the Tier-0 log (ADR-0006) — the durable truth, no graph needed.
    A grill that can't reach Neo4j still lands its `direction.set` / `grill.curated` event here;
    the graph and wiki catch up later by projection (the stranded-grill fix)."""
    return eventlog.append(type, subject, payload, log=log)
