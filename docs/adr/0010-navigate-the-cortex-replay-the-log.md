# Navigate the Cortex, replay the log — the graph is the edge's navigable mind

The Tier-0 log is the source of truth but **un-navigable by design** (append-only; replayed for time and
versioning). The **Cortex** — the whole knowledge graph — is the edge's **navigable mind**: during a beat
the edge *navigates* it (extracted clusters + the asserted Direction / curated / corpus / artifact-refs /
source-signals — one connected surface), following edges on demand. This **refines ADR-0006** by naming the
read architecture: **navigate the Cortex, replay the log.** Navigation is the recall that **scales past
full-read**; the asserted/extracted axis keeps trust legible; the Cortex is a **declared recall capability**
(used like github/exa — for querying its own knowledge, never re-ingested).

## Status

proposed (2026-06-06; Voz ratifies)

## Context

- The log (the "registro") is **hard to navigate** — it is for replay/audit/versioning, not traversal. The
  edge needs a surface it can *move through* during a beat ("what connects to X", multi-hop recall).
- The graph is already queried (`assemble` reads clusters, `grill_lint` runs Cypher) but **declared nowhere**
  and used narrowly — there was no name for "the navigable knowledge the edge thinks in."
- The recall confrontation (`blog/entries/the-recall-confrontation-…`) showed **full-read breaks past a token
  budget** — the edge needs a recall mode that scales.
- ADR-0006 already declared *"everything projects into the graph — the connection substrate; standing pages
  have edges too"* — the navigable-whole-graph was half-declared, unnamed.
- Voz: *"the source of truth is hard to navigate… with all knowledge in a graph the edge could navigate
  seamlessly during beats… why not give him the whole graph"* + *"we should have a name for that, like the
  brain"* → **Cortex** (the obvious `Mente`/`Mens` was rejected — it collides with `Mentee`).

## Considered options

- **Read rendered wiki pages / files in full (status quo).** Breaks at scale (full-read budget); fragmented
  across files; the log itself is un-navigable.
- **Make the graph a delta/intake source.** Rejected — re-reading its own extractions is the self-reference
  loop (the "100% self-referential graph" the project escaped); the log feeds the graph, not vice versa.
- **Name the *act* (a `Recall` term).** Rejected — the Idiom names **subjects, not mechanics** (it *avoids*
  "ingest"/"coleta"). The navigable knowledge is a **thing**; "recall" stays a lowercase verb.
- **Name the *thing* (the navigable graph) and navigate it as the recall surface.** Chosen → **Cortex**.

## Decision

- **Navigate the Cortex, replay the log.** The **Cortex** (the whole graph) is the navigable mind the edge
  thinks *in* during a beat; the **log** is the source of truth, **replayed** (never navigated) for time and
  versioning. Two jobs, two layers — both earn their keep.
- **The whole graph is the surface.** Everything projects in (ADR-0006): extracted clusters **and** the
  asserted edges (Direction, curated, **corpus**, artifact reference nodes, `source.signal` yields). Artifact
  retrieval = traverse to the reference node, fetch the blob.
- **Navigation is the recall that scales.** The **briefing** seeds entry points (a small oriented full-read);
  deep recall follows edges **on demand** — no full-read token wall. *(Three layers: log = record · Cortex =
  mind · wiki/briefing = renders.)*
- **Trust is legible per edge** (ADR-0006 asserted/extracted): **asserted** edges fold from the log →
  faithful; **extracted** (Graphiti) → hypothesis. The edge navigates both, marked.
- **Declared recall capability.** The Cortex is declared (`agent.yaml` / Source roadmap) with a locator
  (`EDGE_NEO4J_URI` + per-install `EDGE_GROUP`), used uniformly like github/exa — but for **recall**
  (querying own knowledge), **never intake**: never deltized, never re-ingested (the self-reference guard).
- **Glossary:** new term **Cortex**; `llm-wiki` refined (full-read when small, navigate the Cortex beyond);
  no `Recall` term (the verb stays lowercase).

## Consequences

- One **navigable knowledge surface** instead of N rendered files + an un-navigable log; the edge gets an
  anatomy of nouns — **corpus** (body), **Cortex** (mind), the **log** (record), Mundo/Atividade/Voz (senses).
- **Recall scales past the full-read budget** (the recall-confrontation's boundary) — navigation, not full-load.
- The **log/Cortex division of labor is explicit**: truth/time (replay) vs navigation/recall — neither redundant.
- Cost: **navigation discipline** — good entry points (the briefing) + **bounded traversal** (follow relevant
  edges, do not load all nodes); the recall capability must be **declared per install** (uri + group).
- Consistent with ADR-0006 (extends it), ADR-0009 (the briefing seeds entry points; corpus / source-signals
  are nodes in the Cortex), and the self-reference guard (recall, not intake).
- Open: traversal budget during navigation (how many hops/nodes to pull per recall) is unspecified — a tuning
  question for the build; on a graph-less host the Cortex is absent and the edge runs Tier-0 (log + folds).
