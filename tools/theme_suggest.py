"""theme_suggest — Artefato theme proposals (old edge-of-chaos shape + dual metric).

Policy (operator conversation 2026-07-24, genotype):

**Dual metric (order matters):**
1. **Δ mente / abertura / bom-para-mim** — primary. Passes only if the reader can
   truthfully say: *“eu não estava vendo X — e isso muda o jogo para mim”*
   (not merely *“agora sei o que testar no exp”*).
2. **Utilidade (código / produto / bet)** — secondary, optional. Never required as the
   close of a research/report theme. Good for handoff instruments; bad as the *default*
   objective of genus research.

**Good theme**
- Something the reader **does not already know**: world mechanism, field tension,
  strategic bet/anti-bet, portable method, or operator-self unknown.
- World hook with external lastro (paper / field / public docs).
- Apply at **human altitude** first (identity, priority, time, power, trust, fear of ship)
  or product altitude — never a path inventory / open-bet continuation.

**Bad theme**
- Redigest of own activity: open-bet continuation, thrash-guard, sitting card, exp-as-title.
- “Safe near current work” that only remaps what is already in blog/Direction.
- Success = next arm / next cycle / “o que se liga”.

**Direction** open bets deny thrash; they do **not** monopolize theme generation.
Recent self-corpus + ticket-ish stems are a *denylist*, never the primary seed pool.

Offline by default (no network). Optional later: live Mundo probes can extend the pool
without changing the shape contract.

CLI::

    tools/edge-python tools/theme_suggest.py [--edge-home PATH] [-n 8] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Ticket / self-pipeline vocabulary — genotype-agnostic markers of activity-redigest.
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

# Apply lines that only point at code/paths — utility-only, fails dual metric primary.
_CODE_ONLY_APPLY = re.compile(
    r"(?:"
    r"\b(tools/|skills/|tests/|state/|blog/entries)\b"
    r"|\b(git checkout|pull request|unit test|assert_)\b"
    r"|\b(próximo arm|proximo arm|next arm|open bet)\b"
    r"|\b(path inventory|file layout|ready\(\))\b"
    r")",
    re.IGNORECASE,
)

# Tokenize for overlap against recent published stems.
_WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

# Content-class shapes (not form skill).
SHAPES = (
    "mechanism",        # how a real subsystem works
    "cost_truth",       # numbers that reframe a decision (token OR attention)
    "field_pattern",    # what the world is doing now
    "portable_method",  # scientific / eng method that travels
    "product_altitude", # product problem without code inventory
    "strategic_bet",    # market/field bet or anti-bet; vision-level
    "operator_self",    # mentee/unknown-unknowns about the human running the agent
)

# Seed pool: world-first + strategic + operator-self.
# Application lines stay install-generic and prefer **human altitude** over code paths.
# Exp/bet may appear only as *case* inside apply — never as title source.
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


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def is_activity_redigest(text: str) -> bool:
    """True if the title/body smells like ticket/activity redigest (not world-new)."""
    return bool(_REDIGEST.search(text or ""))


def is_code_only_apply(apply: str) -> bool:
    """True if apply is utility-to-code only — fails primary Δ mente bar."""
    return bool(_CODE_ONLY_APPLY.search(apply or ""))


def recent_entry_stems(blog_entries: Path, *, limit: int = 40) -> list[str]:
    """Recent published HTML stems under blog/entries (mtime desc)."""
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
    """True if title shares too many tokens with a recent self-published stem."""
    title_toks = _token_set(title)
    if len(title_toks) < min_shared:
        return False
    for stem in stems:
        stem_toks = _token_set(stem.replace("-", " "))
        if len(title_toks & stem_toks) >= min_shared:
            return True
    return False


def validate_card(card: dict[str, Any], *, stems: list[str] | None = None) -> list[str]:
    """Structural + policy checks for one theme card. Returns violation codes."""
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
    # World-first: world_hook must not be only internal state
    wh = _normalize(str(card.get("world_hook") or ""))
    if wh and not any(
        k in wh
        for k in (
            "paper",
            "arxiv",
            "hn",
            "field",
            "docs",
            "vendor",
            "post",
            "survey",
            "x/",
            "public",
            "literature",
            "product",
            "writeup",
            "benchmark",
            "essay",
            "primer",
            "note",
        )
    ):
        if "blog/entries" in wh or "direction" in wh or "open bet" in wh:
            bad.append("world-hook-internal")
    # Dual metric: apply must not be code/path-only utility
    if is_code_only_apply(str(card.get("apply") or "")):
        bad.append("code-only-apply")
    # Prefer explicit mind_open; if present must be non-empty when key exists
    if "mind_open" in card and not str(card.get("mind_open") or "").strip():
        bad.append("missing:mind_open")
    return bad


def suggest_themes(
    *,
    edge_home: Path | None = None,
    n: int = 8,
    pool: list[dict[str, str]] | None = None,
    prefer_mind_open: bool = True,
) -> list[dict[str, Any]]:
    """Return up to n theme cards that pass the dual-metric policy filter.

    Reads local blog/entries only to *exclude* self-redigest — never as theme seeds.
    When prefer_mind_open, cards with mind_open and strategic/operator shapes sort first.
    """
    stems: list[str] = []
    if edge_home is not None:
        stems = recent_entry_stems(Path(edge_home) / "blog" / "entries")

    raw_pool = list(pool if pool is not None else _SEED_POOL)
    if prefer_mind_open:
        priority = {
            "strategic_bet": 0,
            "operator_self": 1,
            "field_pattern": 2,
            "product_altitude": 3,
            "portable_method": 4,
            "cost_truth": 5,
            "mechanism": 6,
        }

        def _key(c: dict[str, str]) -> tuple[int, int]:
            has_mo = 0 if str(c.get("mind_open") or "").strip() else 1
            return (has_mo, priority.get(c.get("shape") or "", 9))

        raw_pool = sorted(raw_pool, key=_key)

    out: list[dict[str, Any]] = []
    for raw in raw_pool:
        card = dict(raw)
        card["slug_hint"] = re.sub(r"[^a-z0-9]+", "-", card["title"].lower()).strip("-")[:80]
        viol = validate_card(card, stems=stems)
        if viol:
            continue
        card["policy"] = {
            "source": "world-seed-pool",
            "direction_role": "denylist-only",
            "not": "open-bet-continuation",
            "primary_metric": "mind-open-bom-para-mim",
            "secondary_metric": "code-product-utility-optional",
            "dv": "reader can say: I wasn't seeing X — that changes the game for me",
        }
        out.append(card)
        if len(out) >= n:
            break
    return out


def format_markdown(cards: list[dict[str, Any]]) -> str:
    """Human-readable smoke output."""
    lines = [
        "# Theme smoke — dual metric (Δ mente first, utility optional)",
        "",
        "Primary: **abertura / bom-para-mim** — not activity redigest, not code-only close.",
        "Direction open bets are **denylist only**. Self-corpus stems filter overlap; they do not seed.",
        "Each card: unknown + world hook + human-altitude apply + mind_open.",
        "",
    ]
    for i, c in enumerate(cards, 1):
        lines += [
            f"## {i}. {c['title']}",
            f"- **form:** `{c['form']}` · **shape:** `{c['shape']}`",
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--edge-home",
        default=None,
        help="Install root (default: parent of tools/). Used only to denylist recent entries.",
    )
    ap.add_argument("-n", type=int, default=8, help="Max themes (default 8)")
    ap.add_argument("--json", action="store_true", help="Machine-readable cards")
    args = ap.parse_args(argv)

    edge_home = Path(args.edge_home).expanduser() if args.edge_home else Path(__file__).resolve().parent.parent
    cards = suggest_themes(edge_home=edge_home, n=args.n)
    if args.json:
        print(json.dumps(cards, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(cards), end="")
    # Smoke exit: must produce at least half of requested (or all if n small)
    need = max(1, min(args.n, 4))
    return 0 if len(cards) >= need else 1


if __name__ == "__main__":
    sys.exit(main())
