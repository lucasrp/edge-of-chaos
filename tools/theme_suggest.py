"""theme_suggest — smoke-oriented Artefato theme proposals (old edge-of-chaos shape).

Policy (operator conversation 2026-07-24, genotype):
- A good theme is something the reader **does not already know** that is **useful** —
  world mechanism / field pattern / portable idea — then applied at high altitude to live work.
- A bad theme is a **redigest of own activity**: open-bet continuation, thrash-guard,
  sitting card, path inventory, "where the files are".
- **Direction open bets deny thrash; they do not monopolize theme generation.**
  This module treats recent self-corpus + ticket-ish stems as a *denylist*, never as the
  primary seed pool.

Offline by default (no network). Optional later: live Mundo probes (exa/hn/arxiv) can
extend the pool without changing the shape contract.

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
    r")",
    re.IGNORECASE,
)

# Tokenize for overlap against recent published stems.
_WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

# Old edge-of-chaos *shape* families (content class, not form skill).
SHAPES = (
    "mechanism",       # how a real subsystem works
    "cost_truth",      # numbers that reframe a decision
    "field_pattern",   # what the world is doing now
    "portable_method", # scientific / eng method that travels
    "product_altitude",# mentee product problem without code inventory
)

# Seed pool: world-first themes in the *spirit* of old HTML reports (caching, eval,
# autonomy, nuggets, genotype…). Application lines stay install-generic (the local edge
# as product/mentor system) — never a named open bet.
_SEED_POOL: list[dict[str, str]] = [
    {
        "shape": "mechanism",
        "form": "research",
        "title": "How modern LLM prompt caching actually works (and when it silently dies)",
        "unknown": "Prefix hashing, routing affinity, TTL, and what breaks the hit — not marketing %.",
        "world_hook": "Provider docs + systems writeups on KV-cache reuse; compare at least two vendors.",
        "apply": "Where the edge's long briefs and repeated wakes burn money or latency for no cognitive gain.",
    },
    {
        "shape": "cost_truth",
        "form": "report",
        "title": "The real unit economics of 'one more grounding pass' in multi-review pipelines",
        "unknown": "Marginal cost vs marginal judgment quality when every pass is another full context.",
        "world_hook": "Public pricing + published agent-ops postmortems on review loops.",
        "apply": "Whether the edge's rite depth is buying judgment or buying ceremony for the operator.",
    },
    {
        "shape": "field_pattern",
        "form": "discovery",
        "title": "Why agent-memory products are flooding the stack (and what they actually store)",
        "unknown": "What mem0/Zep/Letta-class systems keep that a green ready() check never measures.",
        "world_hook": "HN/X Show-HN + product docs; one paper or deep post on memory stores for agents.",
        "apply": "The gap between 'cortex healthy' and 'knows-years' as a product experience.",
    },
    {
        "shape": "portable_method",
        "form": "report",
        "title": "Preregistration without the lab coat: observation-phase rules for AI artifacts",
        "unknown": "How COS-style sealed plans stop post-hoc story-fitting when the 'experiment' is prose.",
        "world_hook": "COS preregistration materials; Kerr HARKing; one short methods note.",
        "apply": "How the operator should accept or reject an Artefato without reopening protocol thrash.",
    },
    {
        "shape": "mechanism",
        "form": "research",
        "title": "GraphRAG and hierarchical memory: what the field solved that flat RAG cannot",
        "unknown": "Community summary + eviction as first-class, not optional polish.",
        "world_hook": "GraphRAG (Microsoft) + Zep (or peer) primary sources; one 2024–2026 survey.",
        "apply": "Whether assemble→cortex is a write rail without a matching consolidate rail.",
    },
    {
        "shape": "product_altitude",
        "form": "report",
        "title": "Eval theater vs eval that changes shipping: a diagnostic for AI product teams",
        "unknown": "When dashboards green while the product still fails the only user who matters.",
        "world_hook": "Eval-driven development posts; Goodhart; one failed-eval war story from the field.",
        "apply": "Which edge greens (ready, mineração, publish) pretend-to-prove consumption or mentor quality.",
    },
    {
        "shape": "field_pattern",
        "form": "map",
        "title": "Multi-agent graphs vs loops: when topology is the product decision",
        "unknown": "The cases where adding agents is architecture, not headcount cosplay.",
        "world_hook": "Recent builder discourse (X/HN) + 1–2 reference systems with public graphs.",
        "apply": "Fan-out in producers (explorers, adversarials) as a topology choice, not a default.",
    },
    {
        "shape": "mechanism",
        "form": "research",
        "title": "Intermediate representations that survive the next session (nuggets, not transcripts)",
        "unknown": "Why raw session logs fail as memory and what a mid-layer claim looks like.",
        "world_hook": "Work on episodic→semantic compression; MemoryBank-style decay notes.",
        "apply": "What should survive between wakes besides Direction bullets and blog HTML.",
    },
    {
        "shape": "portable_method",
        "form": "report",
        "title": "Blind first-draft acceptance: why the first sealed text is the real product",
        "unknown": "What changes when acceptance is reading, not checklisting post-amplifiers.",
        "world_hook": "Blind review culture in science/engineering; writing-process research on revision.",
        "apply": "Rite stages as servants of a readable first draft, not as proof the machine ran.",
    },
    {
        "shape": "cost_truth",
        "form": "report",
        "title": "Context stuffing vs retrieval: when more tokens make the mentor dumber",
        "unknown": "Empirics on lost-in-the-middle and when a smaller grounded set wins.",
        "world_hook": "Lost-in-the-middle paper + vendor guidance on long context failure modes.",
        "apply": "Briefing/recall payload size as a product decision for mentor quality.",
    },
    {
        "shape": "product_altitude",
        "form": "discovery",
        "title": "Operator altitude: what a PO-level AI collaborator must never sound like",
        "unknown": "Patterns that mark implementer-vocabulary capture in 'status' prose.",
        "world_hook": "Product-management writing craft; one case study of exec-vs-eng status mismatch.",
        "apply": "How Artefatos should talk so the operator reads them without becoming a path debugger.",
    },
    {
        "shape": "field_pattern",
        "form": "research",
        "title": "Source-sufficiency judgments: evaluating evidence without checklist theater",
        "unknown": "How strong teams decide 'enough sources' vs decorative citation walls.",
        "world_hook": "Evidence synthesis methods (PRISMA-lite, source criticism) adapted to product research.",
        "apply": "Grounding manifests that license claims vs grounding that only fills a form.",
    },
    {
        "shape": "mechanism",
        "form": "report",
        "title": "Why 'green install' is not 'works for another human': identity and secrets as UX",
        "unknown": "The failure modes when genotype defaults leak author identity into foreign installs.",
        "world_hook": "12-factor / secrets hygiene + multi-tenant agent writeups.",
        "apply": "Shipável as someone else rising with yaml+keys — measured, not asserted.",
    },
    {
        "shape": "portable_method",
        "form": "map",
        "title": "Two subjects, two contexts: world-read vs self-read (and why fusion fails)",
        "unknown": "Contamination patterns when memory and world evidence share one window.",
        "world_hook": "Zep/GraphRAG failure writeups; context-engineering notes on mixed corpora.",
        "apply": "Delta vs recall as a product boundary the operator should feel, not only ADR text.",
    },
]


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def is_activity_redigest(text: str) -> bool:
    """True if the title/body smells like ticket/activity redigest (not world-new)."""
    return bool(_REDIGEST.search(text or ""))


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
        k in wh for k in ("paper", "arxiv", "hn", "field", "docs", "vendor", "post", "survey", "x/", "public")
    ):
        # soft structural: still require non-empty; smoke prefers external language
        if "blog/entries" in wh or "direction" in wh or "open bet" in wh:
            bad.append("world-hook-internal")
    return bad


def suggest_themes(
    *,
    edge_home: Path | None = None,
    n: int = 8,
    pool: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return up to n theme cards that pass the old-edge policy filter.

    Reads local blog/entries only to *exclude* self-redigest — never as theme seeds.
    """
    stems: list[str] = []
    if edge_home is not None:
        stems = recent_entry_stems(Path(edge_home) / "blog" / "entries")

    out: list[dict[str, Any]] = []
    for raw in pool if pool is not None else _SEED_POOL:
        card = dict(raw)
        card["slug_hint"] = re.sub(r"[^a-z0-9]+", "-", card["title"].lower()).strip("-")[:80]
        viol = validate_card(card, stems=stems)
        if viol:
            continue
        card["policy"] = {
            "source": "world-seed-pool",
            "direction_role": "denylist-only",
            "not": "open-bet-continuation",
        }
        out.append(card)
        if len(out) >= n:
            break
    return out


def format_markdown(cards: list[dict[str, Any]]) -> str:
    """Human-readable smoke output."""
    lines = [
        "# Theme smoke — old-edge shape (world-new, not activity redigest)",
        "",
        "Direction open bets are **not** the seed. Recent self-corpus is a **denylist**.",
        "Each card: something the reader likely does not know + a world hook + high-altitude apply.",
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
