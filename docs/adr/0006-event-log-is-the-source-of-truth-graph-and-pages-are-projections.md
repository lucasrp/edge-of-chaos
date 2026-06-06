# The source of truth is an append-only event log; the graph and pages are projections of it

The single source of truth is an **append-only, immutable event log** (raw, deterministic). The
Graphiti graph is **not** the source of truth — it is a *projection* of the log's distilled
episodes. The standing pages (Idiom, Source-roadmap, Direction) and the strategic plan's version
history are **folds** over the log. This **refines ADR-0005**: it keeps "everything is a projection,
nothing hand-edited," but moves the **root** from a mutable LLM-lossy graph to an immutable log.

## Status

proposed (2026-06-06; Voz ratifies)

## Context

- ADR-0005 made the **graph** "the single mutable source of truth" (0005 §Decision) and declared
  standing pages "projections too… nothing hand-edited" (0005 line 48). Two problems surfaced at runtime:
  - **The standing pages are not projections.** `idiom.md` / `source-roadmap.md` are hand-edited
    markdown that `wiki_render.py:42` *reads as a source*; nothing renders them from the graph. 0005:48
    is aspirational — the split-brain (markdown vs graph) the grill keeps hitting.
  - **A mutable, LLM-lossy graph cannot be a versioning root.** Graphiti's entity/relation extraction
    is non-deterministic; you cannot replay it to a faithful past state. "Versioning of strategic
    planning" (the mentee's ask) needs deterministic replay — which a *mutable* store, by definition,
    cannot give. "Single **mutable** source of truth" is an oxymoron for an auditable plan.
- 0005 already says the graph is **seeded from distilled handoffs** — "raw transcripts contaminate it"
  (0005:16). So the raw layer is *already* conceptually outside the graph; it just has no home.
  `consolidate` archives the transcript "raw, search-only" (consolidate/SKILL.md:23) — the would-be log,
  today only a cold blob, not an event stream. The handoff still flags a "full raw store" as persistence-gated.
- Artefatos are **transient/prunable** by glossary (CONTEXT.md) — they must not be event-sourced as blobs.

## Considered options

- **Graph as the store, pages/versioning on top (ADR-0005 as written).** Rejected: the root is mutable
  and lossy → no faithful replay; standing pages drift as hand-edited markdown (the observed split-brain).
- **Append-only event log as the root; graph and pages as projections.** Chosen: the log is immutable
  and deterministic, so replay/versioning is faithful; the graph becomes a rebuildable read-model; the
  standing pages and Direction-history become folds — one truth, everything derived.

## Decision

- **Tier 0 — the log is truth.** An append-only, immutable event stream (`state/events/*.jsonl`, one JSON
  event per line, never mutated). Events: distilled `episode`s, `voz.correction`s, `direction.set`s,
  `grill.curated` marks, etc. Deterministic; replayable; human-legible. No event-store DB — JSONL is enough.
- **Tier 1 — the graph is a projection.** Graphiti ingests the log's distilled episodes → entities /
  communities (the existing 0005 pipeline, now fed *from* the log, not treated as the store). Lossy,
  rebuildable, queryable — droppable and reconstructable from the log.
- **The axis is asserted vs extracted, NOT in-graph vs out.** Everything projects into the graph — the
  connection substrate; standing pages have edges too (Idiom term→cluster, Direction→what it directs). What
  differs is HOW an edge is written:
  - **Asserted (deterministic, replayable):** the edge is **declared in the event** (e.g.
    `direction.set {relates_to:[...]}`) and written to the graph by **direct Cypher, no LLM** — exactly what
    `grill_writeback.py` already does. Standing pages, Direction, curated grill marks. It lives in the graph
    **and** stays faithful, because the edge was declared, not inferred — so versioning survives.
  - **Extracted (lossy):** Graphiti's **LLM extraction** (`episode → entity → community`) pulls
    entities/relations from prose. Knowledge clusters. Approximate by design.
  Versioning works because the asserted edges **fold from the log**, not because anything bypasses the graph.
- A grill **appends an event** (carrying its asserted edges); the matching projection re-derives. This makes
  0005:48 finally true (rooted at the log) and dissolves the standing-page/graph split-brain.
- **Artefatos live in three places, each holding the right thing:** the **blob** (prose HTML) in the
  blob/file store (`blog/entries/…`), transient/prunable; an **`artefato.published` event** in the log
  (`{slug, distills:[cluster:…], cites:[source:…]}`) — the durable record; and a **reference node + asserted
  edges** in the graph (the artifact hung off the clusters it distills / sources it cites — CONTEXT.md's
  "Artefatos hang off the cluster", made real). Prune the blob → keep the event + distillation + connections.
- **Versioning = replay.** `direction_at(t)` folds `direction.*` events up to `t` → the plan as-of-then.
  Strategic history is faithful because the log is raw and deterministic.
- **Tier 2 — wiki HTML projects the graph** (unchanged from 0005). **Artefatos** are blobs in a blob
  store, **referenced** from the graph, transient/prunable — never event-sourced as blobs.
- **The grill always persists to the log.** A grill that cannot reach Neo4j still appends its events
  (the durable truth); the graph/wiki catch up via projection. Fixes the stranded-grill gap.

## Consequences

- **Corrects 0005's root, keeps its spirit.** "Everything is a projection, nothing hand-edited" stays;
  "the graph is the single mutable source of truth" is **superseded** — the graph is a *projection*.
- The split-brain (markdown standing pages vs graph) goes away: both become folds over one log.
- Graphiti is now disposable — a cache. Loss of the graph is recoverable; loss of the log is not (so the
  log gets the durability budget).
- **Migration is incremental** (tracer-bullet first): build the log + the **Direction** projection to
  prove faithful versioning; migrate Idiom/Source-roadmap/clusters to projections after. Until migrated,
  hand-edited markdown remains an explicit *stand-in* (like `chat-digest.md` today).
- Cost: a fold/projection layer and an event taxonomy to maintain. Kept minimal — append-only JSONL +
  pure-function folds, no framework (consistent with "shed scaffolding toward a legible core").
- Consistent with ADR-0001 (agentic, no per-source primitive), ADR-0004 (consolidate's archive *is* the
  log's writer), and ADR-0005 (render unchanged — it now projects a graph that is itself a projection).
