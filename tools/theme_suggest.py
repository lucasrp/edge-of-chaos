"""theme_suggest — Artefato theme proposals (Δ mente + install domain).

Policy (operator conversation 2026-07-24, genotype):

**Dual metric (order matters):**
1. **Δ mente / abertura / bom-para-mim** — primary. Passes only if the reader can
   truthfully say: *"eu não estava vendo X — e isso muda o jogo para mim"*
   (not merely *"agora sei o que testar no exp"*).
2. **Utilidade (código / produto / bet)** — secondary, optional.

**Install domain:** themes are *ranked for this edge_home* using mission + Direction
**set** (curated) so Δ mente lands in *that* operator's domain (legal/IR vs mentor/memory
vs product gate). Direction still does **not** seed ticket redigest — open bets are
denylist + domain profile only.

**Good theme**
- World mechanism / field tension / strategic bet the reader does not already know
- Apply at human altitude, bound to *this* install's mission
- Exp/bet only as *case*, never title-source

**Bad theme**
- Activity redigest / safe near current work / success = next arm

CLI::

    tools/edge-python tools/theme_suggest.py [--edge-home PATH] [-n 8] [--form research] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_REDIGEST = re.compile(
    r"(?:"
    r"\bexp\d{2,}\b"
    r"|\bg0\b"
    r"|\bplacar\b"
    r"|\bh\s*\*\b|\bhstar\b"
    r"|\bhard-?stops?\b"
    r"|\bdone-when\b"
    r"|\bthrash\b"
    r"|\bsitting-par\b"
    r"|\bopen-compare\b"
    r"|\bfase-flip\b"
    r"|\bcartao-g0\b"
    r"|\bgate-dogfood\b"
    r"|\barm_id\b"
    r"|\bdispatch_id\b"
    r"|\buser_requested\b"
    r"|\boutput\.html\b"
    r"|\barms?/\b"
    r"|\bpróximo ciclo\b|\bproximo ciclo\b"
    r"|\bo que se liga\b"
    r"|\bvol_mecanico\b"
    r")",
    re.IGNORECASE,
)

_CODE_ONLY_APPLY = re.compile(
    r"(?:"
    r"\b(tools/|skills/|tests/|state/|blog/entries)\b"
    r"|\b(git checkout|pull request|unit test|assert_)\b"
    r"|\b(próximo arm|proximo arm|next arm|open bet)\b"
    r"|\b(path inventory|file layout|ready\(\))\b"
    r")",
    re.IGNORECASE,
)

_WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

SHAPES = (
    "mechanism",
    "cost_truth",
    "field_pattern",
    "portable_method",
    "product_altitude",
    "strategic_bet",
    "operator_self",
)

_SEED_POOL: list[dict[str, str]] = [
    # --- strategic / mind-open (lista-B spirit, genotype-portable) ---
    {
        "shape": "strategic_bet",
        "form": "research",
        "title": "The end of 'search as product': navigation + explanation as the real unit",
        "unknown": "Why ranking-as-product is losing to systems that help the human *move and justify*, not only hit@k.",
        "world_hook": "Legal-tech and enterprise search positioning 2024–2026; public product notes on explainable retrieval.",
        "apply": "Whether the operator's identity is 'I build a ranker' or 'I build a navigator that a human can sign'.",
        "mind_open": "Reframes success away from leaderboard scores toward signed human trust.",
    },
    {
        "shape": "strategic_bet",
        "form": "research",
        "title": "Containment vs decomposition: two knowledge bets that look the same in demos",
        "unknown": "What you gain and lose by *containing* a graph of law/knowledge vs decomposing it into features.",
        "world_hook": "Knowledge-graph vs feature-store writeups; one survey on legal/IR graph approaches.",
        "apply": "A strategic choice about what 'knowing' means for the product — not a schema ticket.",
        "mind_open": "Makes visible that architecture is an epistemology bet, not neutral plumbing.",
    },
    {
        "shape": "field_pattern",
        "form": "research",
        "title": "When the mean is the wrong instrument: long-tail retrieval and model tournaments",
        "unknown": "How average metrics train the wrong intuition about rare, high-stakes queries.",
        "world_hook": "IR evaluation literature on long-tail / risk-sensitive metrics; public tournament postmortems.",
        "apply": "How the operator should *feel* about a 'winning' arm when the tail is where the user lives.",
        "mind_open": "Breaks the habit of trusting tournament averages as vision.",
    },
    {
        "shape": "field_pattern",
        "form": "research",
        "title": "LLM-as-judge as political technology: who defines 'won'",
        "unknown": "What reproducibility and power papers hide when a model grades another model.",
        "world_hook": "LLM-as-judge surveys + critique papers; one piece on inter-rater reliability failures.",
        "apply": "What 'ganhou no exp' actually authorizes in the operator's head — and what it must not.",
        "mind_open": "Separates score theater from judgment the human still owns.",
    },
    {
        "shape": "portable_method",
        "form": "report",
        "title": "Fact, narrative, and proof: what process/evidence theory still teaches index builders",
        "unknown": "Categories the legal process uses that schema fields flatten into 'text type'.",
        "world_hook": "Evidence-law / theory of proof primers; one IR paper on factuality vs narration.",
        "apply": "How the operator prioritizes what the system must never confuse — before the next channel.",
        "mind_open": "Restores a richer ontology than 'valorado vs narrado as enum'.",
    },
    {
        "shape": "product_altitude",
        "form": "research",
        "title": "Individualization vs recall: why a 'pocket' is not a fact store",
        "unknown": "Pocket/anchor as a different mental category from factual recall — product implication.",
        "world_hook": "Personalization vs retrieval literature; one design writeup on user-specific memory.",
        "apply": "What the operator is actually promising a user when they say 'the system knows your case'.",
        "mind_open": "Stops treating every memory problem as the same retrieval problem.",
    },
    {
        "shape": "product_altitude",
        "form": "discovery",
        "title": "Agent observability as trust design (not another exp dashboard)",
        "unknown": "What legitimate agent UX requires of the human who must sign the output.",
        "world_hook": "Agent UX / human-in-the-loop design notes; one critique of ops dashboards as false trust.",
        "apply": "Whether surfaces teach the operator *when to trust* or only *what ran*.",
        "mind_open": "Moves observability from ceremony to signature-ready trust.",
    },
    {
        "shape": "field_pattern",
        "form": "research",
        "title": "Staleness of memory in long-running agents: open problems, not store features",
        "unknown": "What the field still cannot guarantee about wrong-forget vs right-forget.",
        "world_hook": "Agent-memory benchmarks and open-problem notes (mem0/Zep/Letta class + papers).",
        "apply": "The operator's fear of *forgetting wrong* as a product risk — not a green ready() check.",
        "mind_open": "Names memory as existential risk for long systems, not a checkbox.",
    },
    {
        "shape": "portable_method",
        "form": "report",
        "title": "Preregistration and anti-HARKing outside the lab coat",
        "unknown": "How open science treats a wrong instrument without rewriting last week's scoreboard story.",
        "world_hook": "COS preregistration; Kerr HARKing; one methods note on sealed analysis plans.",
        "apply": "Culture of experiments the operator can live with without thrash-rewriting narrative.",
        "mind_open": "Separates learning from post-hoc story-fitting.",
    },
    {
        "shape": "operator_self",
        "form": "report",
        "title": "The operator as mentee of themselves: Johari and unknown-unknowns with an agent that echoes",
        "unknown": "What mentorship models imply when the 'product' mirrors your own work back at you.",
        "world_hook": "Johari window; unknown-unknown literature; one mentor-craft essay on feedback loops.",
        "apply": "When an Artefato is expanding the human vs recycling their board language.",
        "mind_open": "Makes redundancy feel like a *self* failure mode, not a content bug.",
    },
    {
        "shape": "cost_truth",
        "form": "report",
        "title": "Cognitive cost of multi-model multi-arm: attention tax, not token price",
        "unknown": "How many parallel eval reports a human can actually integrate before judgment collapses.",
        "world_hook": "Attention / cognitive load research; postmortems on multi-agent ops overload.",
        "apply": "How many parallel 'winners' the operator should tolerate before the board owns them.",
        "mind_open": "Reframes cost as human attention, not GPU bill.",
    },
    {
        "shape": "strategic_bet",
        "form": "discovery",
        "title": "What legal-tech marketing is lying about in 2026 (and where not to compete)",
        "unknown": "Positioning gaps between search, copilot, graph, and 'IA jurídica' claims vs delivered work.",
        "world_hook": "Public product pages + analyst notes + HN/X field talk; one honest failure writeup.",
        "apply": "Where the operator should *refuse* the market story instead of chasing feature parity.",
        "mind_open": "Anti-competitive clarity: knowing which game not to play.",
    },
    # --- mechanism / portable (still world-first; apply human-altitude) ---
    {
        "shape": "mechanism",
        "form": "research",
        "title": "How modern LLM prompt caching actually works (and when it silently dies)",
        "unknown": "Prefix hashing, routing affinity, TTL, and what breaks the hit — not marketing %.",
        "world_hook": "Provider docs + systems writeups on KV-cache reuse; compare at least two vendors.",
        "apply": "Whether long repeated briefs are buying cognition or burning money without the operator noticing.",
        "mind_open": "Turns 'more context' from virtue into a falsifiable systems claim.",
    },
    {
        "shape": "cost_truth",
        "form": "report",
        "title": "The real unit economics of 'one more grounding pass' in multi-review pipelines",
        "unknown": "Marginal cost vs marginal judgment quality when every pass is another full context.",
        "world_hook": "Public pricing + published agent-ops postmortems on review loops.",
        "apply": "Whether deeper rites buy the operator better judgment or only ceremony comfort.",
        "mind_open": "Lets the operator drop a pass without guilt when quality is flat.",
    },
    {
        "shape": "field_pattern",
        "form": "discovery",
        "title": "Why agent-memory products are flooding the stack (and what they actually store)",
        "unknown": "What mem0/Zep/Letta-class systems keep that a green health check never measures.",
        "world_hook": "HN/X Show-HN + product docs; one paper or deep post on memory stores for agents.",
        "apply": "The gap between 'install healthy' and 'knows years of me' as a lived product promise.",
        "mind_open": "Separates infrastructure green from relationship with the past.",
    },
    {
        "shape": "mechanism",
        "form": "research",
        "title": "GraphRAG and hierarchical memory: what the field solved that flat RAG cannot",
        "unknown": "Community summary + eviction as first-class, not optional polish.",
        "world_hook": "GraphRAG (Microsoft) + Zep (or peer) primary sources; one 2024–2026 survey.",
        "apply": "Whether the operator's knowledge stack has a consolidate story or only a write story.",
        "mind_open": "Makes hierarchy and eviction a design choice, not a backlog item.",
    },
    {
        "shape": "product_altitude",
        "form": "report",
        "title": "Eval theater vs eval that changes shipping: a diagnostic for AI product teams",
        "unknown": "When dashboards green while the product still fails the only user who matters.",
        "world_hook": "Eval-driven development posts; Goodhart; one failed-eval war story from the field.",
        "apply": "Which greens the operator is allowed to ignore without becoming reckless.",
        "mind_open": "Restores the right to distrust a green board.",
    },
    {
        "shape": "field_pattern",
        "form": "map",
        "title": "Multi-agent graphs vs loops: when topology is the product decision",
        "unknown": "The cases where adding agents is architecture, not headcount cosplay.",
        "world_hook": "Recent builder discourse (X/HN) + 1–2 reference systems with public graphs.",
        "apply": "When fan-out is a bet about the work, not a default of the toolkit.",
        "mind_open": "Topology becomes a conscious product lever.",
    },
    {
        "shape": "mechanism",
        "form": "research",
        "title": "Intermediate representations that survive the next session (nuggets, not transcripts)",
        "unknown": "Why raw session logs fail as memory and what a mid-layer claim looks like.",
        "world_hook": "Work on episodic→semantic compression; MemoryBank-style decay notes.",
        "apply": "What the operator needs to still believe next week without rereading the week.",
        "mind_open": "Shifts memory from 'keep everything' to 'keep what survives judgment'.",
    },
    {
        "shape": "portable_method",
        "form": "report",
        "title": "Blind first-draft acceptance: why the first sealed text is the real product",
        "unknown": "What changes when acceptance is reading, not checklisting post-amplifiers.",
        "world_hook": "Blind review culture in science/engineering; writing-process research on revision.",
        "apply": "Whether the operator is consuming prose or consuming proof-the-machine-ran.",
        "mind_open": "Returns reading as the acceptance act.",
    },
    {
        "shape": "cost_truth",
        "form": "report",
        "title": "Context stuffing vs retrieval: when more tokens make the mentor dumber",
        "unknown": "Empirics on lost-in-the-middle and when a smaller grounded set wins.",
        "world_hook": "Lost-in-the-middle paper + vendor guidance on long context failure modes.",
        "apply": "How much briefing the operator should tolerate before quality is theater.",
        "mind_open": "Less context can be the brave product choice.",
    },
    {
        "shape": "product_altitude",
        "form": "discovery",
        "title": "Operator altitude: what a PO-level AI collaborator must never sound like",
        "unknown": "Patterns that mark implementer-vocabulary capture in 'status' prose.",
        "world_hook": "Product-management writing craft; one case study of exec-vs-eng status mismatch.",
        "apply": "How Artefatos should talk so the operator stays a decider, not a path debugger.",
        "mind_open": "Protects the operator's altitude from eng-capture.",
    },
    {
        "shape": "field_pattern",
        "form": "research",
        "title": "Source-sufficiency judgments: evaluating evidence without checklist theater",
        "unknown": "How strong teams decide 'enough sources' vs decorative citation walls.",
        "world_hook": "Evidence synthesis methods (PRISMA-lite, source criticism) adapted to product research.",
        "apply": "When the operator can stop reading sources without guilt — and when they must not.",
        "mind_open": "Replaces citation count with judgment license.",
    },
    {
        "shape": "mechanism",
        "form": "report",
        "title": "Why 'green install' is not 'works for another human': identity and secrets as UX",
        "unknown": "The failure modes when defaults leak author identity into foreign installs.",
        "world_hook": "12-factor / secrets hygiene + multi-tenant agent writeups.",
        "apply": "What 'shipável for someone else' means as lived trust, not assert-in-CI.",
        "mind_open": "Shipável becomes a relationship claim, not a pipeline color.",
    },
    {
        "shape": "portable_method",
        "form": "map",
        "title": "Two subjects, two contexts: world-read vs self-read (and why fusion fails)",
        "unknown": "Contamination patterns when memory and world evidence share one window.",
        "world_hook": "Zep/GraphRAG failure writeups; context-engineering notes on mixed corpora.",
        "apply": "When the operator is learning the world vs re-reading themselves — and must not mix them.",
        "mind_open": "Makes fusion feel like contamination, not efficiency.",
    },
]

_FACET_SIGNALS: dict[str, tuple[str, ...]] = {
    "legal_ir": (
        "legal", "juríd", "jurid", "retrieval", "juris", "índice", "indice", "v10",
        "busca", "search", "ranking", "ranker", "processo", "prova", "valorado",
        "narrado", "pocket", "episteme", "instrução", "instrucao", "jurídico",
    ),
    "agent_memory": (
        "memory", "memória", "memoria", "cortex", "assemble", "recall", "knows-years",
        "staleness", "graphrag", "hierarchical", "nugget", "episodic", "semantic",
    ),
    "mentor": (
        "mentor", "mentee", "persona", "telos", "unknown-unknown", "altitude",
        "continuidade", "continuity", "shipável", "shipavel", "anti-pm", "operator",
    ),
    "product_gate": (
        "gate", "triagem", "closavo", "score", "prontidão", "prontidao", "user-novo",
        "placa", "superfície", "superficie", "qualifica",
    ),
    "eval_judge": (
        "judge", "placar", "eval", "tournament", "campeonato", "llm-as-judge",
        "variance", "variância", "variancia",
    ),
    "rite_agency": (
        "rito", "agency", "authorial", "feynman", "genus", "artefato", "report",
    ),
    "systems": (
        "caching", "context", "token", "multi-agent", "topology", "pipeline", "routing",
    ),
}

_TITLE_DOMAIN_HINTS: list[tuple[str, list[str]]] = [
    ("search as product", ["legal_ir"]),
    ("containment vs decomposition", ["legal_ir", "agent_memory"]),
    ("mean is the wrong", ["legal_ir", "eval_judge"]),
    ("llm-as-judge", ["eval_judge", "legal_ir"]),
    ("fact, narrative", ["legal_ir"]),
    ("individualization vs recall", ["legal_ir", "agent_memory"]),
    ("agent observability", ["mentor", "product_gate"]),
    ("staleness of memory", ["agent_memory", "mentor"]),
    ("preregistration", ["eval_judge", "mentor"]),
    ("mentee of themselves", ["mentor"]),
    ("cognitive cost of multi-model", ["eval_judge", "mentor"]),
    ("legal-tech marketing", ["legal_ir"]),
    ("prompt caching", ["systems"]),
    ("grounding pass", ["systems", "rite_agency"]),
    ("agent-memory products", ["agent_memory", "mentor"]),
    ("graphrag", ["agent_memory", "legal_ir"]),
    ("eval theater", ["eval_judge", "mentor"]),
    ("multi-agent graphs", ["systems"]),
    ("intermediate representations", ["agent_memory", "mentor"]),
    ("blind first-draft", ["rite_agency", "mentor"]),
    ("context stuffing", ["systems", "agent_memory"]),
    ("operator altitude", ["mentor"]),
    ("source-sufficiency", ["mentor"]),
    ("green install", ["mentor", "product_gate"]),
    ("two subjects, two contexts", ["agent_memory", "mentor"]),
]


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def is_activity_redigest(text: str) -> bool:
    return bool(_REDIGEST.search(text or ""))


def is_code_only_apply(apply: str) -> bool:
    return bool(_CODE_ONLY_APPLY.search(apply or ""))


def recent_entry_stems(blog_entries: Path, *, limit: int = 40) -> list[str]:
    root = Path(blog_entries)
    if not root.is_dir():
        return []
    files = sorted(
        (p for p in root.glob("*.html") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.stem for p in files[:limit]]


def _token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD.finditer(text or "")}


def overlaps_self_corpus(title: str, stems: list[str], *, min_shared: int = 3) -> bool:
    title_toks = _token_set(title)
    if len(title_toks) < min_shared:
        return False
    for stem in stems:
        stem_toks = _token_set(stem.replace("-", " "))
        if len(title_toks & stem_toks) >= min_shared:
            return True
    return False


def validate_card(card: dict[str, Any], *, stems: list[str] | None = None) -> list[str]:
    required = ("shape", "form", "title", "unknown", "world_hook", "apply")
    bad: list[str] = []
    for k in required:
        if not str(card.get(k) or "").strip():
            bad.append(f"missing:{k}")
    title = str(card.get("title") or "")
    blob = " ".join(str(card.get(k) or "") for k in required)
    if is_activity_redigest(blob):
        bad.append("activity-redigest")
    if stems is not None and overlaps_self_corpus(title, stems):
        bad.append("self-corpus-overlap")
    if card.get("shape") and card["shape"] not in SHAPES:
        bad.append("bad-shape")
    form = card.get("form") or ""
    if form not in ("report", "research", "map", "plan", "discovery", "prototype", "critique"):
        bad.append("bad-form")
    wh = _normalize(str(card.get("world_hook") or ""))
    if wh and not any(
        k in wh
        for k in (
            "paper", "arxiv", "hn", "field", "docs", "vendor", "post", "survey",
            "x/", "public", "literature", "product", "writeup", "benchmark",
            "essay", "primer", "note",
        )
    ):
        if "blog/entries" in wh or "direction" in wh or "open bet" in wh:
            bad.append("world-hook-internal")
    if is_code_only_apply(str(card.get("apply") or "")):
        bad.append("code-only-apply")
    if "mind_open" in card and not str(card.get("mind_open") or "").strip():
        bad.append("missing:mind_open")
    return bad


def _yaml_simple_load_identity(edge_home: Path) -> dict[str, str]:
    path = Path(edge_home) / "agent.yaml"
    out = {"name": "", "mission": "", "voice": "", "codename": ""}
    if not path.is_file():
        return out
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("#") or ":" not in s:
            continue
        key, _, val = s.partition(":")
        key = key.strip()
        if key not in out:
            continue
        val = val.strip().strip('"').strip("'")
        if val:
            out[key] = val
    return out


def _direction_set_text(edge_home: Path) -> str:
    path = Path(edge_home) / "state" / "direction.md"
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines: list[str] = []
    in_set = False
    for line in raw.splitlines():
        if line.startswith("## Set"):
            in_set = True
            continue
        if line.startswith("## ") and in_set:
            break
        if in_set and line.strip().startswith("-"):
            if is_activity_redigest(line):
                continue
            lines.append(line)
    return "\n".join(lines)


def load_install_context(edge_home: Path | None) -> dict[str, Any]:
    if edge_home is None:
        return {
            "name": "", "mission": "", "voice": "", "direction_set": "",
            "facets": set(), "domain_tokens": set(), "stems": [],
        }
    home = Path(edge_home)
    ident = _yaml_simple_load_identity(home)
    direction = _direction_set_text(home)
    blob = " ".join([
        ident.get("name") or "",
        ident.get("mission") or "",
        ident.get("voice") or "",
        direction,
    ]).lower()
    facets: set[str] = set()
    for facet, signals in _FACET_SIGNALS.items():
        if any(sig.lower() in blob for sig in signals):
            facets.add(facet)
    if not facets:
        facets.add("general")
    tokens = _token_set(blob)
    tokens -= {"the", "and", "for", "not", "with", "from", "that", "this", "are", "was", "que", "para", "com"}
    return {
        "name": ident.get("name") or "",
        "mission": ident.get("mission") or "",
        "voice": ident.get("voice") or "",
        "direction_set": direction,
        "facets": facets,
        "domain_tokens": tokens,
        "stems": recent_entry_stems(home / "blog" / "entries"),
    }


def seed_domains(card: dict[str, Any]) -> list[str]:
    if card.get("domains"):
        return list(card["domains"])  # type: ignore[return-value]
    title = (card.get("title") or "").lower()
    for hint, doms in _TITLE_DOMAIN_HINTS:
        if hint in title:
            return list(doms)
    return ["general"]


def domain_score(card: dict[str, Any], ctx: dict[str, Any]) -> float:
    facets = ctx.get("facets") or set()
    doms = set(seed_domains(card))
    facet_hit = len(doms & set(facets))
    blob = " ".join(str(card.get(k) or "") for k in ("title", "unknown", "mind_open", "world_hook"))
    overlap = len(_token_set(blob) & (ctx.get("domain_tokens") or set()))
    mo = 1.0 if str(card.get("mind_open") or "").strip() else 0.0
    general_floor = 0.15 if ("general" in doms or not facets or facets == {"general"}) else 0.0
    return mo * 2.0 + facet_hit * 3.0 + min(overlap, 8) * 0.35 + general_floor


def bind_apply_to_domain(card: dict[str, Any], ctx: dict[str, Any]) -> str:
    apply = str(card.get("apply") or "").strip()
    mission = (ctx.get("mission") or "").strip()
    name = (ctx.get("name") or "this install").strip()
    if not mission:
        return apply
    if "Δ mente must land" in apply or "mission:" in apply:
        return apply
    snip = mission[:160].rstrip().rstrip(".")
    if len(mission) > 160:
        snip += "…"
    bind = (
        f" Δ mente must land for **{name}** in its live domain — mission: {snip}. "
        "Exp/board may appear only as a case, never as the title-source."
    )
    base = apply.rstrip().rstrip(".")
    return base + "." + bind


def suggest_themes(
    *,
    edge_home: Path | None = None,
    n: int = 8,
    pool: list[dict[str, str]] | None = None,
    prefer_mind_open: bool = True,
    form: str | None = None,
    domain_rank: bool = True,
) -> list[dict[str, Any]]:
    """Return up to n theme cards (dual metric + install domain rank)."""
    ctx = load_install_context(edge_home)
    stems: list[str] = list(ctx.get("stems") or [])
    raw_pool = list(pool if pool is not None else _SEED_POOL)
    if form:
        filtered = [c for c in raw_pool if (c.get("form") or "") == form]
        raw_pool = filtered or raw_pool

    shape_priority = {
        "strategic_bet": 0,
        "operator_self": 1,
        "field_pattern": 2,
        "product_altitude": 3,
        "portable_method": 4,
        "cost_truth": 5,
        "mechanism": 6,
    }

    def _sort_key(c: dict[str, str]) -> tuple:
        has_mo = 0 if str(c.get("mind_open") or "").strip() else 1
        dscore = -domain_score(c, ctx) if domain_rank and edge_home is not None else 0.0
        sp = shape_priority.get(c.get("shape") or "", 9) if prefer_mind_open else 0
        return (has_mo, dscore, sp)

    raw_pool = sorted(raw_pool, key=_sort_key)
    out: list[dict[str, Any]] = []
    for raw in raw_pool:
        card = dict(raw)
        card["domains"] = seed_domains(card)
        card["slug_hint"] = re.sub(r"[^a-z0-9]+", "-", card["title"].lower()).strip("-")[:80]
        viol = validate_card(card, stems=stems)
        if viol:
            continue
        if edge_home is not None:
            card["apply"] = bind_apply_to_domain(card, ctx)
            if is_code_only_apply(card["apply"]):
                continue
        dscore = domain_score(card, ctx) if edge_home is not None else 0.0
        card["domain_score"] = round(dscore, 3)
        card["install_facets"] = sorted(ctx.get("facets") or [])
        card["policy"] = {
            "source": "world-seed-pool+install-domain-rank",
            "direction_role": "domain-profile+denylist",
            "not": "open-bet-continuation",
            "primary_metric": "mind-open-bom-para-mim",
            "secondary_metric": "code-product-utility-optional",
            "domain": "install-mission+direction-set",
            "dv": "reader can say: I wasn't seeing X — that changes the game for me (in this domain)",
        }
        out.append(card)
        if len(out) >= n:
            break
    return out


def format_markdown(cards: list[dict[str, Any]], *, ctx: dict[str, Any] | None = None) -> str:
    lines = [
        "# Theme candidates — Δ mente first, **install domain** ranked",
        "",
        "Primary: **abertura / bom-para-mim** (not activity redigest, not code-only close).",
        "Domain: mission + Direction *set* rank the world pool — they do **not** seed tickets.",
        "DV: *I wasn't seeing X — that changes the game for me* (in **this** domain).",
        "",
    ]
    if ctx:
        lines += [
            f"- **install:** `{ctx.get('name') or '?'}`",
            f"- **mission:** {(ctx.get('mission') or '')[:220]}",
            f"- **facets:** `{', '.join(sorted(ctx.get('facets') or []))}`",
            "",
        ]
    for i, c in enumerate(cards, 1):
        lines += [
            f"## {i}. {c['title']}",
            f"- **form:** `{c['form']}` · **shape:** `{c['shape']}` · **domain_score:** `{c.get('domain_score', '')}`",
            f"- **domains:** `{', '.join(c.get('domains') or [])}`",
            f"- **slug_hint:** `{c.get('slug_hint', '')}`",
            f"- **unknown (why new):** {c['unknown']}",
            f"- **world hook:** {c['world_hook']}",
            f"- **apply (altitude, not ticket):** {c['apply']}",
            f"- **mind_open (Δ mente):** {c.get('mind_open', '')}",
            "",
        ]
    if not cards:
        lines.append("_No themes passed the filter — widen pool or clear denylist collision._")
    return "\n".join(lines) + "\n"


def format_briefing_section(edge_home: Path, *, n: int = 6, form: str | None = None) -> str:
    cards = suggest_themes(edge_home=edge_home, n=n, form=form, prefer_mind_open=True, domain_rank=True)
    ctx = load_install_context(edge_home)
    return format_markdown(cards, ctx=ctx)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--edge-home", default=None, help="Install root (domain rank + denylist)")
    ap.add_argument("-n", type=int, default=8, help="Max themes (default 8)")
    ap.add_argument(
        "--form", default=None,
        choices=("report", "research", "map", "plan", "discovery", "prototype", "critique"),
        help="Filter seed form to match beat producer",
    )
    ap.add_argument("--json", action="store_true", help="Machine-readable cards")
    args = ap.parse_args(argv)
    edge_home = Path(args.edge_home).expanduser() if args.edge_home else Path(__file__).resolve().parent.parent
    cards = suggest_themes(edge_home=edge_home, n=args.n, form=args.form)
    ctx = load_install_context(edge_home)
    if args.json:
        print(json.dumps({
            "context": {
                "name": ctx.get("name"),
                "mission": ctx.get("mission"),
                "facets": sorted(ctx.get("facets") or []),
            },
            "themes": cards,
        }, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(cards, ctx=ctx), end="")
    need = max(1, min(args.n, 4))
    return 0 if len(cards) >= need else 1


if __name__ == "__main__":
    sys.exit(main())
