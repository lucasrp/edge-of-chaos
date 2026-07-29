# The wiki is a re-rendered projection of the graph, never edited

The wiki's durable pages — Knowledge clusters, entity pages, the index — are a **materialized
projection of the graph** (Zep/Graphiti). The graph is the single mutable source of truth; a
page is a view. Every change to the wiki is a change to the **graph** (the grill writes curated
facts, invalidates, directs clusters), followed by **re-rendering** the affected pages. Pages
are never edited in place.

## Status

accepted

## Context

- We adopted Zep/Graphiti as the knowledge substrate (exp-002/003): a bi-temporal entity/fact
  graph, seeded from distilled **handoffs** (raw transcripts contaminate it). Graphiti's
  `episode → entity → community` **is** the Karpathy tiering (`raw → entity-page → cluster`), so
  a separate page-structuring engine is redundant — the structure comes from the graph.
- The glossary's `llm-wiki` is **pages** (Knowledge clusters + Standing pages). How the graph and
  the pages relate was the open question.
- If pages were hand-authored/edited, they would drift from the graph (two sources of truth), and
  correction-propagation, staleness, and bidirectional curation would each need manual bookkeeping.

## Considered options

- **Hand-authored/edited cluster pages, graph as a search index beneath.** Rejected:
  two-sources-of-truth drift; a correction must be hunted across pages; provenance is lost.
- **Pages as a re-rendered projection of the graph.** Chosen: one source of truth; the page is a
  build artifact (a view), so correction-propagation/staleness/curation derive for free.

## Decision

- **Projection.** The wiki (clusters, entity pages, index) is a materialized view of the graph.
  The graph is the only mutable source of truth.
- **Re-render, never edit.** A change to the wiki is a change to the graph, then a re-render of
  the affected pages. No in-place page edits.
- **Incremental.** Re-render only the **blast radius** of a change (the corrected node's
  community + neighborhood), not the whole wiki.
- **Hybrid render.** Structural projection (entity pages, index, fact lists) is **mechanical /
  template** — no LLM. The cluster/thread **synthesis prose** is agentic but delegated to a cheap
  router (`render` = `gpt-5.4-mini`), **not** the edge's scarce cognition. The judgment lives
  **upstream** — in the graph + Idiom, produced by the edge's Opus-level cognition; the render
  only **expresses** it. The render prompt carries the **Idiom** (frame in the mentee's terms) +
  the cluster's current-valid facts + the prior page (continuity).
- **Bounding.** The render projects only **current-valid / hot / relevant** facts, so the
  read-in-full wiki stays bounded while the raw/graph grows unbounded — the access semantics of
  handoff #4, now a mechanical consequence of the render rather than a rule.
- **Uniform.** Standing pages (Idiom, Direction) are projections too — of curated **Voz** facts —
  so nothing in the wiki is hand-edited.

## Consequences

- Correction-propagation, staleness archiving, and bidirectional (add **and** retire) curation
  "just work" — one source of truth, the view always derived.
- A cheap render makes **liberal** re-render affordable ("without economizing"), which is exactly
  what page-as-projection needs to stay drift-free. The two choices reinforce each other:
  disposable projections tolerate a cheap, occasionally imperfect renderer; a cheap renderer
  affords constant re-render.
- **Cost gradient:** Opus (judgment — theme, grill, orientation, spawn/merge by harm potential) →
  `gpt-5.4-mini` (synthesis render) → template (structure) → `gpt-5.4-mini`/Graphiti (extraction).
  Scarce cognition touches only the irreducible.
- Cluster curation (spawn/attach/merge) operates on the **graph**, gated by harm potential; pages
  follow. This **reverses handoff #4's** assumption that clusters might be hand-curated markdown.
- Consistent with ADR-0001 (agentic), ADR-0003 (the `render` router adds **no** `claude -p` — it
  is an API call), and ADR-0004 (the render is where consolidate/grill graph-writes become
  readable pages; it ungates consolidate's *persistence-gated* cluster write).
