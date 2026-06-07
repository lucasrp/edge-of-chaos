"""briefing — the deterministic composer of Memento's tattoo (ADR-0009). Genotype tool.

The agent has anterograde amnesia: it must orient **entirely** from the briefing and trust
nothing that isn't inscribed there (CONTEXT.md, the `**Briefing**` entry). So the load-bearing
lines — the curated Direction, what is open / the next bet, the source yield, what the agent
already did — are **deterministically inscribed from the log** (folds of `tools/eventlog.py`),
never left to an LLM to remember. Only the **Recap** (the corpus↔live-Atividade relation) is
synthesized fresh; `assemble` fills its slot. The **Facts leg** (Knowledge clusters) navigates the
graph (ADR-0011: graph mandatory, Cortex guaranteed); a real outage degrades only that leg to the
Tier-0 note — the log-fold legs still compose, the beat never crashes.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eventlog import (LOG, direction_at, corpus_at, artefatos_without_kernel,  # noqa: E402
                      source_feedback_at)

REPO = Path(__file__).resolve().parent.parent
AGENT_YAML = REPO / "agent.yaml"

KIND_ORDER = ["phase", "priority", "constraint", "thread"]

# The native source the edge always reads — the mentee's Claude sessions (the transcript store the
# sweep digests). Not declared in agent.yaml because it is intrinsic to the runtime; a constant floor
# entry so the roster is never blank even on a stock agent.yaml (ADR-0011, Source roadmap floor).
NATIVE_SOURCE = {"name": "claude-sessions", "kind": "native",
                 "label": "the mentee's Claude sessions (native transcript store)"}


def source_roster(agent_yaml=AGENT_YAML):
    """The declared source roster (← Source roadmap, ADR-0011) — the never-blank floor of the
    briefing's source orientation. Reads agent.yaml `sources:` (each authored → curated by
    definition) and prepends the native Claude-sessions source. Per-entry `label` is the fallback
    chain description→via→bare name (no schema migration forced). Pure-ish: only reads agent.yaml,
    so compose_briefing stays a pure composer when handed a roster explicitly."""
    import yaml
    roster = [dict(NATIVE_SOURCE)]
    p = Path(agent_yaml)
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        for s in data.get("sources") or []:
            name = s.get("name", "")
            label = s.get("description") or s.get("via") or name
            roster.append({"name": name, "kind": s.get("kind"), "label": label})
    return roster


def graph_clusters(group=None, uri=None, user=None, password=None):
    """The Facts leg (ADR-0011): read this group's grill-curated **Knowledge clusters** from the
    Cortex — the same projection wiki_render reads — and return them **in full** for the briefing.

    There is **no Cortex recall/navigation interface yet** (ADR-0010 is proposed, unbuilt), so the
    briefing carries the whole curated knowledge inline rather than letting the agent retrieve it:
    a list of ``{"label", "entities": [{"name", "facts": [...]}]}`` (clusters alpha-ordered, entities
    alpha-ordered, current-valid facts deduped, contested flagged). **[]** when the graph is reachable
    but holds no curated cluster yet; **None** on a genuine degrade — no group declared (EDGE_GROUP —
    the genotype carries no identity default), the neo4j driver absent (Tier-0 minimal host), or the
    graph unreachable. Never raises — a transient outage darkens only this leg (ADR-0011)."""
    if not group:
        return None
    uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
    user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = password or os.environ.get("EDGE_NEO4J_PASSWORD")  # no literal default (#21/C4)
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
            labels = [r["l"] for r in s.run(
                "MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
                "RETURN DISTINCT e.curated_cluster AS l ORDER BY l", g=group)]
            out = []
            for label in labels:
                ents = s.run(
                    "MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster=$l "
                    "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
                    "RETURN coalesce(e.curated_name,e.name) AS d, e.name AS n ORDER BY d",
                    g=group, l=label).data()
                entities = []
                for e in ents:
                    facts = []
                    for r in s.run(
                        "MATCH (x:Entity {name:$n})-[rel:RELATES_TO]-() WHERE rel.invalid_at IS NULL "
                        "RETURN rel.fact AS f, coalesce(rel.contested,false) AS c", n=e["n"]).data():
                        f = r.get("f")
                        if not f:
                            continue
                        f = ("⚠ contested — " + f) if r.get("c") else f
                        if f not in facts:
                            facts.append(f)
                    entities.append({"name": e["d"], "facts": facts})
                out.append({"label": label, "entities": entities})
    except Exception:
        return None
    finally:
        try:
            drv.close()
        except Exception:
            pass
    return out


def _render_direction_items(items):
    by_kind = {}
    for it in items:
        by_kind.setdefault(it.get("kind", "thread"), []).append(it)
    lines = []
    for kind in KIND_ORDER + [k for k in by_kind if k not in KIND_ORDER]:
        for it in by_kind.get(kind, []):
            lines.append(f"- **[{kind}]** {it.get('body', '')}")
    return "\n".join(lines) if lines else "_none_"


def _section_direction(log, seq, ts):
    d = direction_at(seq=seq, ts=ts, log=log)
    if d is None:
        return "## 1. Direction\n\n_no direction set yet._"
    return ("## 1. Direction\n\n"
            "**Set — curated (Voz, highest authority):**\n\n"
            f"{_render_direction_items(d.get('set', []))}\n\n"
            "**Proposed — non-curated (grill achados):**\n\n"
            f"{_render_direction_items(d.get('proposed', []))}")


def _section_continuity(corpus):
    """The literal tattoo: what the cold agent was mid-doing — the *why* of the most-recent
    kernels, most-recent-first. Empty corpus (or no recorded why yet) → an honest empty marker."""
    whys = [c["intent"] for c in reversed(corpus) if c.get("intent")]
    body = "\n".join(f"- {w}" for w in whys[:2]) if whys else "_nothing open recorded yet._"
    return f"## 2. What is open / the next bet\n\n{body}"


def _section_corpus(corpus, debt):
    """What I already did: recent slugs + their why, most-recent-first, so the agent builds rather
    than repeats. Kernel-less Artefatos are surfaced as C3 debt (show the gap, don't hide it)."""
    if not corpus:
        body = "_no corpus yet._"
    else:
        lines = []
        for it in reversed(corpus):
            why = it.get("intent") or "_no intent recorded (C3 debt)_"
            lines.append(f"- **{it['slug']}** — {why}")
        body = "\n".join(lines)
    if debt:
        body += "\n\n**C3 debt** (Artefatos with no recorded intent): " + ", ".join(debt)
    return f"## 3. Corpus — what I already did\n\n{body}"


def _section_sources(log, seq, ts, roster):
    """Source orientation (ADR-0011): the declared **roster** (← Source roadmap) as the never-blank
    **floor**, then the two-tier source feedback — the **curated** stratum (← source.curated, the
    grill-distilled mentee opinion) ABOVE the non-curated **yield** (ref · kind · count · mean sim,
    highest first), mirroring _section_direction (set over proposed). The grill consults the yield;
    the roster + curated keep the section honest before/after signal accrues. Degrade, never crash."""
    floor = "\n".join(f"- **{r['name']}** ({r.get('kind')}) — {r.get('label', r['name'])}"
                      for r in (roster or []))
    parts = ["## 4. Source orientation", "**Declared roster** (the floor — what each source is for):",
             floor or "_no roster declared._"]
    fb = source_feedback_at(seq=seq, ts=ts, log=log)
    if fb["curated"]:
        cur = "\n".join(f"- **{c['source']}** — {c['opinion']}" for c in fb["curated"])
        parts += ["**Curated — mentee opinion (Voz-grounded, highest authority):**", cur]
    yld = fb["non_curated"]
    if yld:
        rows = sorted(yld.values(), key=lambda r: r["mean_similarity"], reverse=True)
        lines = [f"- **{r['ref']}** ({r['kind']}) · {r['count']}× · mean sim {r['mean_similarity']:.2f}"
                 for r in rows]
        parts += ["**Source feedback — non-curated (how each source actually yielded):**", "\n".join(lines)]
    return "\n\n".join(parts)


def _section_clusters(clusters):
    """Knowledge clusters (← graph, the Facts leg of ADR-0011). Four states:
    None → degrade note (graph offline OR no EDGE_GROUP — the leg darkens, knowledge = log + Direction);
    [] → graph reachable but no curated cluster yet (distinct from an outage);
    [{label, entities:[{name, facts}]}] → the **full** clusters inline (no Cortex recall interface yet,
    so the briefing carries the whole curated knowledge — entities + current-valid facts);
    [str, ...] → bare labels as bullets (explicit/pure-composer callers). Never crash on the graph."""
    if clusters is None:
        return ("## 5. Knowledge clusters\n\n"
                "_Tier-0: clusters unavailable — graph offline or no EDGE_GROUP set; "
                "knowledge = the swept log + Direction._")
    if not clusters:
        return "## 5. Knowledge clusters\n\n_graph reachable — no curated clusters yet._"
    if isinstance(clusters[0], dict):
        # Full-read: the whole cluster inline (stopgap until a Cortex recall interface exists).
        parts = ["## 5. Knowledge clusters",
                 "_Full read — no Cortex recall interface yet; the whole curated graph is inline._"]
        for c in clusters:
            ents = c.get("entities") or []
            lines = [f"### {c.get('label')} ({len(ents)})"]
            for e in ents:
                facts = e.get("facts") or []
                lines.append(f"- **{e.get('name')}** — " + "; ".join(facts) if facts
                             else f"- **{e.get('name')}**")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
    return "## 5. Knowledge clusters\n\n" + "\n".join(f"- {c}" for c in clusters)


def _section_recap(recap):
    """Recap (← corpus): the one synthesized-fresh part — the corpus↔live-Atividade relation.
    None → a slot marker the assemble LLM fills; otherwise inscribe the synthesized text."""
    body = recap or "_(Recap synthesized at compose-time — corpus × live Atividade)_"
    return f"## 6. Recap\n\n{body}"


BANNER = ("<!-- generated by tools/briefing.py — Memento's tattoo (ADR-0009); "
          "load-bearing lines inscribed from the log, only the Recap synthesized fresh -->")


_AUTO = object()  # sentinel: "fetch clusters for me" vs an explicit None ("I have none — Tier-0")


def compose_briefing(log=LOG, recap=None, clusters=_AUTO, roster=None, seq=None, ts=None, group=None):
    """Render the briefing (Memento's tattoo) as one markdown string, from the log. Deterministic:
    sections in tattoo priority (load-bearing first). Cursor-aware (seq/ts) like the folds it reads.
    `roster` is the declared source floor (ADR-0011); defaults to source_roster() (reads agent.yaml)
    so the source section is never blank. `clusters` is the Facts leg: left unset, it navigates the
    Cortex for `group` (defaults to EDGE_GROUP) via graph_clusters() and degrades to None on outage;
    pass it explicitly (None or a list) to keep compose_briefing a pure composer (tests, Tier-0)."""
    if roster is None:
        roster = source_roster()
    if clusters is _AUTO:
        clusters = graph_clusters(group if group is not None else os.environ.get("EDGE_GROUP"))
    corpus = corpus_at(seq=seq, ts=ts, log=log)
    parts = [
        BANNER + "\n# Briefing — orient entirely from here",
        _section_direction(log, seq, ts),
        _section_continuity(corpus),
        _section_corpus(corpus, artefatos_without_kernel(log=log)),
        _section_sources(log, seq, ts, roster),
        _section_clusters(clusters),
        _section_recap(recap),
    ]
    return "\n\n".join(parts) + "\n"
