"""briefing — the deterministic composer of Memento's tattoo (ADR-0009). Genotype tool.

The agent has anterograde amnesia: it must orient **entirely** from the briefing and trust
nothing that isn't inscribed there (CONTEXT.md, the `**Briefing**` entry). So the load-bearing
lines — the curated Direction, what is open / the next bet, the source yield, what the agent
already did — are **deterministically inscribed from the log** (folds of `tools/eventlog.py`),
never left to an LLM to remember. Only the **Recap** (the corpus↔live-Atividade relation) is
synthesized fresh; `assemble` fills its slot. Tier-0 composes from the log alone — the graph
(Knowledge clusters) degrades where there is no runtime, never crashes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eventlog import (LOG, direction_at, corpus_at, artefatos_without_kernel,  # noqa: E402
                      source_yield_at)

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
    **floor**, with the per-source **yield** (ref · kind · count · mean sim, highest first) layered
    on as it accrues. The grill consults the yield; the roster keeps the section honest before any
    signal exists. Degrade, never crash."""
    floor = "\n".join(f"- **{r['name']}** ({r.get('kind')}) — {r.get('label', r['name'])}"
                      for r in (roster or []))
    parts = ["## 4. Source orientation", "**Declared roster** (the floor — what each source is for):",
             floor or "_no roster declared._"]
    yld = source_yield_at(seq=seq, ts=ts, log=log)
    if yld:
        rows = sorted(yld.values(), key=lambda r: r["mean_similarity"], reverse=True)
        lines = [f"- **{r['ref']}** ({r['kind']}) · {r['count']}× · mean sim {r['mean_similarity']:.2f}"
                 for r in rows]
        parts += ["**Source feedback** (how each source actually yielded):", "\n".join(lines)]
    return "\n\n".join(parts)


def _section_clusters(clusters):
    """Knowledge clusters (← graph, Tier-1). None → the Tier-0 degrade note (no graph runtime;
    knowledge = the swept log + Direction). Never crash on the missing graph."""
    if clusters is None:
        return ("## 5. Knowledge clusters\n\n"
                "_Tier-0: clusters unavailable — no graph runtime; "
                "knowledge = the swept log + Direction._")
    if not clusters:
        return "## 5. Knowledge clusters\n\n_none._"
    return "## 5. Knowledge clusters\n\n" + "\n".join(f"- {c}" for c in clusters)


def _section_recap(recap):
    """Recap (← corpus): the one synthesized-fresh part — the corpus↔live-Atividade relation.
    None → a slot marker the assemble LLM fills; otherwise inscribe the synthesized text."""
    body = recap or "_(Recap synthesized at compose-time — corpus × live Atividade)_"
    return f"## 6. Recap\n\n{body}"


BANNER = ("<!-- generated by tools/briefing.py — Memento's tattoo (ADR-0009); "
          "load-bearing lines inscribed from the log, only the Recap synthesized fresh -->")


def compose_briefing(log=LOG, recap=None, clusters=None, roster=None, seq=None, ts=None):
    """Render the briefing (Memento's tattoo) as one markdown string, from the log. Deterministic:
    sections in tattoo priority (load-bearing first). Cursor-aware (seq/ts) like the folds it reads.
    `roster` is the declared source floor (ADR-0011); defaults to source_roster() (reads agent.yaml)
    so the source section is never blank, while staying a pure composer when handed one explicitly."""
    if roster is None:
        roster = source_roster()
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
