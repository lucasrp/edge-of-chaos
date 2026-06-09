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
                      source_feedback_at, objective_at, report_at)
import _identity  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
AGENT_YAML = REPO / "agent.yaml"
MEMORY = REPO / "memory"
STATE = REPO / "state"

KIND_ORDER = ["phase", "priority", "constraint", "thread"]

# recall-push (#30): the SALIENT slice — cap the artefatos pushed into the briefing so it does not
# grow with the whole corpus (Codex P2). A small, most-recent slice; recall MORE on demand.
RECALL_ARTEFATO_LIMIT = 8

# The identity fields the genotype CANNOT compose without — a thin agent.yaml that omits any of
# these is a lobotomy (ADR-0009), not a valid install. The personality `.tpl` substitutes them.
REQUIRED_IDENTITY = ["name", "mission", "voice"]


class BriefingIdentityError(Exception):
    """Fail-closed signal: a genotype-identity input the briefing REQUIRES is missing/thin (thin
    agent.yaml identity, absent doctrine, blank idiom, or no declared source roster). Raised instead
    of silently blanking a load-bearing identity section, so `_validate`/`edge-apply` can catch it
    and a lobotomized edge never reaches HEALTHY (briefing-lifecycle gate, issue #26)."""

# The native source the edge always reads — the mentee's Claude sessions (the transcript store the
# sweep digests). Not declared in agent.yaml because it is intrinsic to the runtime; a constant floor
# entry so the roster is never blank even on a stock agent.yaml (ADR-0011, Source roadmap floor).
NATIVE_SOURCE = {"name": "claude-sessions", "kind": "native",
                 "label": "the mentee's Claude sessions (native transcript store)"}


def source_roster(agent_yaml=AGENT_YAML):
    """The declared source roster (← Source roadmap, ADR-0011) — the source orientation's floor.
    FAIL-CLOSED (gate root-cause #2): requires agent.yaml to exist and carry a non-empty `sources:`
    list whose every entry has name + kind + description, each a non-empty STRING (a blank/
    whitespace/non-string field is a thin roster, not a real one); the native Claude-sessions source
    is prepended as an ADDITIVE floor, never a SUBSTITUTE for the declared roster (so a missing/
    malformed source list cannot masquerade as a non-empty section). Per-entry `label` is the
    (stripped) description. Pure-ish: only reads agent.yaml, so compose_briefing
    stays a pure composer when handed a roster explicitly."""
    import yaml
    p = Path(agent_yaml)
    if not p.exists():
        raise BriefingIdentityError(f"agent.yaml absent ({p}) — no declared source roster to inject")
    data = yaml.safe_load(p.read_text()) or {}
    sources = data.get("sources")
    if not sources:
        raise BriefingIdentityError("agent.yaml declares no sources — the source roster is empty "
                                    "(the native floor is additive, never the whole roster)")
    if not isinstance(sources, list):
        raise BriefingIdentityError(
            f"agent.yaml `sources` is not a list ({type(sources).__name__}) — the source roster must "
            "be a list of mappings (name + kind + description), not a string/mapping")
    roster = [dict(NATIVE_SOURCE)]
    for s in sources:
        if not isinstance(s, dict):
            raise BriefingIdentityError(
                f"malformed source entry {s!r} — each declared source must be a mapping with "
                "name + kind + description")
        name, kind, desc = s.get("name"), s.get("kind"), s.get("description")
        for field, val in (("name", name), ("kind", kind), ("description", desc)):
            if not isinstance(val, str) or not val.strip():
                raise BriefingIdentityError(
                    f"malformed source entry {s!r} — `{field}` must be a non-empty string "
                    "(name + kind + description); a blank/whitespace/non-string field is a thin roster")
        roster.append({"name": name.strip(), "kind": kind.strip(), "label": desc.strip()})
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
    password = password or os.environ.get("EDGE_NEO4J_PASSWORD") or _identity.neo4j_password()  # env → install secret (#21/C4)
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


def recall_subgraph(group=None, uri=None, user=None, password=None):
    """Recall-push (#30): read the SALIENT SUBGRAPH of the edge's own memory — space-0 (the
    :Genesis identity root) → the Objective → the active Directions (bets) → the salient Artefatos
    (most recent, slug+kernel) → the clusters they DISTILL — and return it so `compose_briefing`
    can PUSH it into the briefing. The producer then wakes with its own memory already in front of
    it (recall-push), rather than depending on remembering to recall (the dormant g.search() tale).

    Mirrors `graph_clusters` exactly: returns a dict
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
            # SERVES. Order by `projected_at` (the recency signal) DESC and LIMIT to the salient
            # slice, so the briefing does NOT grow with the whole corpus (#30, Codex P2). Legacy
            # nodes with no projected_at sort last (coalesce to '').
            arts = s.run(
                "MATCH (a:Artefato {group_id:$g})-[:SERVES]->(:Objective {group_id:$g}) "
                "RETURN a.slug AS slug, a.kernel AS kernel "
                "ORDER BY coalesce(a.projected_at,'') DESC, a.slug LIMIT $lim",
                g=group, lim=RECALL_ARTEFATO_LIMIT).data()
            # clusters derived from the SAME salient slice (Codex P2): only the clusters the pushed
            # artefatos distill, not every Artefato in the group — so the recall stays salient and
            # does not grow with the whole corpus.
            slugs = [a["slug"] for a in arts]
            clusters = [r["l"] for r in s.run(
                "MATCH (a:Artefato {group_id:$g})-[:DISTILLS]->(e:Entity {group_id:$g}) "
                "WHERE a.slug IN $slugs AND e.curated_cluster IS NOT NULL "
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


def _render_direction_items(items):
    by_kind = {}
    for it in items:
        by_kind.setdefault(it.get("kind", "thread"), []).append(it)
    lines = []
    for kind in KIND_ORDER + [k for k in by_kind if k not in KIND_ORDER]:
        for it in by_kind.get(kind, []):
            lines.append(f"- **[{kind}]** {it.get('body', '')}")
    return "\n".join(lines) if lines else "_none_"


def _section_objective(log, seq, ts):
    """The spine (ADR-0006/0007): the mentee's **confirmed objective** — the anchor everything below
    is measured against, so it sits ABOVE Direction. Inscribed from the log fold (objective_at), a
    saved-as-confirmed-hypothesis prior the next grill re-tests. No objective set yet → an honest
    marker (the briefing still composes on a fresh log)."""
    obj = objective_at(seq=seq, ts=ts, log=log)
    if obj is None:
        return "## Objective — the anchor\n\n_no confirmed objective yet._"
    body = obj.get("body", "")
    rationale = obj.get("rationale")
    why = f"\n\n_why:_ {rationale}" if rationale else ""
    return f"## Objective — the anchor\n\n{body}{why}"


def _section_direction(log, seq, ts):
    d = direction_at(seq=seq, ts=ts, log=log)
    if d is None:
        return "## 1. Direction\n\n_no direction set yet._"
    return ("## 1. Direction\n\n"
            "**Set — curated (Voz, highest authority):**\n\n"
            f"{_render_direction_items(d.get('set', []))}\n\n"
            "**Proposed — non-curated (grill achados):**\n\n"
            f"{_render_direction_items(d.get('proposed', []))}")


def _section_report(log, seq, ts):
    """The direcionamento — the rolling steer injected every wake (ADR-0006/0007). Direction's
    proposed/set bullets are the skeleton; this report is the flesh actually read: objective + the
    steer + the live insight, re-derived from the data each grill. Only the LATEST shows (the present
    steer; the lineage is the grill's to read). Inscribed from the log fold (report_at). No report
    yet → an honest marker (additive — Direction still renders above)."""
    r = report_at(seq=seq, ts=ts, log=log)
    latest = r.get("latest")
    if latest is None:
        return "## Direcionamento — the rolling steer\n\n_no direcionamento report yet._"
    return f"## Direcionamento — the rolling steer\n\n{latest.get('body', '')}"


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
                "_Tier-0: clusters unavailable — the graph leg is DARK, which is NOT the same as "
                "'no clusters yet'. Before narrating 'graph offline', CHECK: (1) did this process load "
                "the install secrets (`_secrets.load_env(secrets/)`)? a `claude -p` dispatch must, or "
                "EDGE_NEO4J_PASSWORD is absent and the leg darkens though neo4j is up; (2) is EDGE_GROUP "
                "/ agent.yaml graph_group set? `edge-apply --validate` is the ground truth for "
                "reachability. If both hold, the graph is reachable and this is a load gap, not an "
                "outage — do not report 'offline'. Knowledge this beat = the swept log + Direction._")
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


def _section_recall(subgraph):
    """Recall-push (#30) — the salient subgraph of the edge's OWN memory, PUSHED into the briefing
    so the producer wakes with it in front (not depending on remembering to recall). ADDITIVE: a
    new section, the rest of the briefing unchanged. Begins at SPACE 0 (the :Genesis identity root),
    then objective → bets → salient artefatos → clusters. None → a dark-leg marker (graph offline /
    no group); the briefing still composes (never fatal). Recall MORE on demand via
    skills/_shared/memory.md (semantic + structural traversal beyond this pushed slice)."""
    if subgraph is None:
        return ("## 7. Recall — your own memory (pushed)\n\n"
                "_Recall leg DARK (graph offline or no group) — the salient subgraph could not be "
                "pushed this wake. You still hold the full briefing above; recall MORE on demand "
                "from your own graph (`skills/_shared/memory.md`) when the graph is reachable._")
    parts = ["## 7. Recall — your own memory (pushed)",
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
    return "\n".join(parts)


BANNER = ("<!-- generated by tools/briefing.py — Memento's tattoo (ADR-0009); "
          "load-bearing lines inscribed from the log, only the Recap synthesized fresh -->")


def _render_tpl(text, agent_yaml=AGENT_YAML):
    """Substitute {{var}} from agent.yaml identity fields (same convention as templates/).
    FAIL-CLOSED (gate root-cause #1): a referenced identity field (name/mission/voice) that is
    absent or blank in agent.yaml raises BriefingIdentityError rather than silently substituting
    empty — a thin identity must fail loud, never blank the personality tattoo."""
    import re
    import yaml
    cfg = {}
    p = Path(agent_yaml)
    if p.exists():
        cfg = yaml.safe_load(p.read_text()) or {}
    cfg.setdefault("codename", cfg.get("name", ""))
    refs = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", text))
    missing = [k for k in REQUIRED_IDENTITY if k in refs and not str(cfg.get(k, "")).strip()]
    if missing:
        raise BriefingIdentityError(
            f"agent.yaml identity is thin — {', '.join(missing)} blank/absent; the personality "
            "tattoo would silently blank. Fill the identity (ADR-0009).")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}",
                  lambda m: str(cfg.get(m.group(1), m.group(0))), text)


def _read_doc(name, memory=MEMORY, agent_yaml=AGENT_YAML):
    """Read a memory doctrine doc — rendered `.md` preferred, else render the `.md.tpl`. '' if absent.
    The `.tpl` render is fail-closed on thin identity (via _render_tpl)."""
    md, tpl = Path(memory) / f"{name}.md", Path(memory) / f"{name}.md.tpl"
    if md.exists():
        return md.read_text().strip()
    if tpl.exists():
        return _render_tpl(tpl.read_text(), agent_yaml=agent_yaml).strip()
    return ""


def _section_tattoos(memory=MEMORY, agent_yaml=AGENT_YAML):
    """The **immutable** head of the briefing — the *initial tattoos*: who the edge is (**personality**)
    and how it thinks (**method**), the Feynman doctrine. Loaded ONLY here, at the edge's wake (via the
    briefing) — never the global `CLAUDE.md` system prompt (that would change Claude, not the edge). Read
    from `memory/` as the **current** doctrine (not cursor-versioned — the tattoos are foundational, not
    historical). FAIL-CLOSED (gate root-cause #1): BOTH personality and method must render non-empty,
    or it raises BriefingIdentityError — an absent/blank tattoo is a lobotomy, never a silent marker."""
    personality = _read_doc("personality", memory=memory, agent_yaml=agent_yaml)
    method = _read_doc("method", memory=memory, agent_yaml=agent_yaml)
    missing = [n for n, v in (("personality", personality), ("method", method)) if not v]
    if missing:
        raise BriefingIdentityError(
            f"doctrine absent/blank — {', '.join(missing)} not inscribed in {memory}; "
            "the initial tattoos are REQUIRED at every stage (ADR-0009).")
    return "\n\n".join([
        "## Initial tattoos (immutable) — who I am, how I think",
        "_The permanent tattoos: loaded every wake, unchanged by the log. Operate from these "
        "before reading the state below._",
        "### Personality\n\n" + personality,
        "### Method\n\n" + method,
    ])


def _section_idiom(agent_yaml=AGENT_YAML, state_dir=STATE):
    """The Idiom / glossary (← the mentee's terms, ADR-0005). The glossaries are NOT genotype — they
    are a per-install CONSEQUENCE of `agent.yaml` `ground_truth.documents` (the mentee's projects'
    CONTEXT.md, the authored canon / Voz ground-truth). This reads that declared list (paths, `~`
    expanded), reads each EXISTING non-empty file, and INJECTS its content as the glossary FLOOR — so
    the amnesiac beat speaks the mentee's language. The edge's own curated `state/idiom.md` (grilling-
    accreted, expected-empty on a fresh install) is LAYERED on top when present, never the floor.

    Fail-closed distinguishes a config-gap from a genotype lobotomy:
      • ground_truth declared but ALL documents absent/empty → BriefingIdentityError (a declared-but-
        missing canon is a real config failure);
      • some present, some missing → inject the present ones + note the missing (never silently drop);
      • ground_truth NOT declared at all → an honest "no ground_truth declared" marker (an agent.yaml
        CONFIG gap, NOT a lobotomy — does NOT raise, distinct from the fail-closed tattoos)."""
    import yaml
    p = Path(agent_yaml)
    data = yaml.safe_load(p.read_text()) if p.exists() else None
    gt = (data or {}).get("ground_truth") if isinstance(data, dict) else None
    documents = (gt or {}).get("documents") if isinstance(gt, dict) else None

    if not documents:
        # An agent.yaml CONFIG gap — honest marker, not a raise (distinct from the lobotomy tattoos).
        return ("## Idiom — the mentee's terms\n\n"
                "_no ground_truth declared in agent.yaml — the glossary floor "
                "(`ground_truth.documents`) is unconfigured; this is an agent.yaml CONFIG gap, not a "
                "genotype lobotomy. No mentee glossary is injected this wake._")

    blocks, missing = [], []
    for raw in documents:
        path = Path(os.path.expanduser(str(raw)))
        content = path.read_text().strip() if path.exists() else ""
        if content:
            blocks.append(f"### {raw}\n\n{content}")
        else:
            missing.append(str(raw))

    if not blocks:
        raise BriefingIdentityError(
            f"ground_truth declared but ALL documents absent/empty ({', '.join(missing)}) — a "
            "declared-but-missing canon is a real config failure; the glossary floor is REQUIRED "
            "when ground_truth is declared (ADR-0005).")

    parts = ["## Idiom — the mentee's terms",
             "_Glossary floor — the ground_truth.documents (the mentee's projects' authored canon)._"]
    parts += blocks
    if missing:
        parts.append("_Missing ground_truth document(s) (declared but absent/empty): "
                     + ", ".join(missing) + "._")

    idiom = Path(state_dir) / "idiom.md"
    layer = idiom.read_text().strip() if idiom.exists() else ""
    if layer:
        parts.append("### Curated Idiom (edge-accreted)\n\n" + layer)
    return "\n\n".join(parts)


_AUTO = object()  # sentinel: "fetch clusters for me" vs an explicit None ("I have none — Tier-0")


def compose_briefing(log=LOG, recap=None, clusters=_AUTO, roster=None, seq=None, ts=None, group=None,
                     agent_yaml=AGENT_YAML, memory=MEMORY, subgraph=_AUTO):
    """Render the briefing (Memento's tattoo) as one markdown string, from the log. Deterministic:
    sections in tattoo priority (load-bearing first). Cursor-aware (seq/ts) like the folds it reads.
    The genotype-identity head (Personality, Method, Idiom, the declared Source roster) is
    FAIL-CLOSED: a thin agent.yaml, absent doctrine, blank idiom, or no declared sources raises
    BriefingIdentityError (briefing-lifecycle gate) — never a silent blank. `roster` defaults to
    source_roster() (reads agent.yaml); pass it explicitly (e.g. []) to keep compose_briefing a
    pure composer (tests, Tier-0). `clusters` is the Facts leg: left unset, it navigates the Cortex
    for `group` (defaults to EDGE_GROUP) via graph_clusters() and degrades to None on outage.
    `subgraph` is the recall-push leg (#30): left unset, it auto-fetches the salient subgraph via
    recall_subgraph() (ONLY when `clusters` was also auto — a caller that pinned clusters keeps the
    briefing hermetic and passes subgraph explicitly when wanted) and degrades to None on outage.
    The recall-push section is ADDITIVE — the full briefing above is unchanged."""
    if roster is None:
        roster = source_roster(agent_yaml=agent_yaml)
    clusters_was_auto = clusters is _AUTO
    # resolve the group LAZILY — only when an auto-fetch actually needs it (Codex P3): a caller that
    # pinned BOTH clusters and subgraph (Tier-0 / custom-agent tests) must stay hermetic and not
    # trigger a default identity lookup that could read the wrong install or fail.
    def _group():
        return group if group is not None else (os.environ.get("EDGE_GROUP") or _identity.group())
    if clusters is _AUTO:
        clusters = graph_clusters(_group())
    if subgraph is _AUTO:
        # recall-push (#30): auto-fetch the salient subgraph ONLY when the caller did not opt out
        # of graph fetches (clusters is _AUTO). A caller that pinned clusters (tests, Tier-0) keeps
        # the briefing hermetic — they pass subgraph explicitly when they want it.
        subgraph = recall_subgraph(_group()) if clusters_was_auto else None
    corpus = corpus_at(seq=seq, ts=ts, log=log)
    parts = [
        BANNER + "\n# Briefing — orient entirely from here",
        _section_tattoos(memory=memory, agent_yaml=agent_yaml),
        _section_idiom(agent_yaml=agent_yaml, state_dir=Path(memory).parent / "state"),
        _section_objective(log, seq, ts),
        _section_direction(log, seq, ts),
        _section_report(log, seq, ts),
        _section_continuity(corpus),
        _section_corpus(corpus, artefatos_without_kernel(log=log)),
        _section_sources(log, seq, ts, roster),
        _section_clusters(clusters),
        _section_recap(recap),
        _section_recall(subgraph),
    ]
    return "\n\n".join(parts) + "\n"
