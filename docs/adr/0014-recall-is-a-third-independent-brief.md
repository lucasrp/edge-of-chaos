# Recall is a third independent brief at pre-dispatch — fanned beside assemble and delta, never fused with either

The **recall-push** (the salient subgraph of the Cortex, rooted at space-0) leaves the assemble
briefing and becomes a **third independent brief**, produced by its own subagent fanned at
pre-dispatch alongside **assemble** (curated self-state) and **delta** (world-new). Three views,
three subjects, three faithful agents (ADR-0004). The wake — and every dispatch's pre-dispatch —
fans **three briefs**.

## Status

proposed (2026-06-10; Voz ratifies, glossary grill). Amends ADR-0009 (briefing composition: the
recall leg leaves the briefing and becomes a peer brief) and the recall-push placement inside
assemble (`feat(assemble): recall-push`, 4428c64). Honors ADR-0004 (one task per subagent),
ADR-0011 (navigation is judgment in the loop — reaffirmed; only the *push* is fanned), ADR-0012
(pre-dispatch widens from `assemble + delta` to `assemble + delta + recall`).

## Considered options

- **Fuse recall with delta in one shared-context subagent.** Rejected on the subject boundary —
  the glossary's strongest line: delta is *over the world, never over the wiki*; recall is
  *navigation of own knowledge, never re-ingested*. One context holding both is where the
  self-reference guard fails in practice: the edge's own recalled Artefato sits beside fresh world
  signal with only model discipline keeping one from being read as the other (the Zep-failure
  shape, transplanted to sources). The two reads also need different judgment (novelty-worth-
  surfacing vs salience-to-now) and different tools (source keys vs graph traversal).
- **Keep the recall-push inside assemble** (the status quo, 4428c64). Rejected on context budget
  and fidelity: assemble's brief is already the fattest surface in the system (~60k tokens), and
  ADR-0011 already ruled that assemble is mechanical while Cortex work is its own thing. The push
  was placed there as a compromise; a dedicated agent can navigate deep (traversal + semantic
  search over past Artefatos) and return only the salient subgraph.
- **Chosen: independent recall subagent.** Parallelism is real — recall reads the durable graph
  (space-0, Direction anchors, curated clusters, published Artefatos) and does not need the
  sweep's seconds-fresh output: what the sweep just extracted is non-curated, exactly the tier
  that is not yet salience-bearing. Cost: one-beat staleness on brand-new extractions —
  acceptable by construction.

## Decision

- **Recall** becomes a noun — the yield of recalling (the act stays a lowercase verb), symmetric
  to **Delta** (the yield of updating). The brief it yields is the **memory-salient view**: the
  salient subgraph of the Cortex, rooted at space-0.
- **Pre-dispatch fans three briefs**: assemble (curated self-state) · delta (world-new) · recall
  (memory-salient). All three are read-only subagents; the loop blocks on assemble, the delta
  never gates (ADR-0011), recall degrades to briefing-only waking on a graph outage.
- **The push seeds; navigation deepens.** The recall brief is the *push* (mechanical salience,
  fanable). On-demand Cortex navigation remains the loop's own judgment in its own window
  (ADR-0011's line, reaffirmed — it was never assemble's, and it is not the recall agent's either).

## Consequences

- The skills now lag the decision (a build follows, not in this ADR): `skills/wake` ("fan the two
  briefs" → three), `skills/_shared/pipeline.md` (pre-dispatch = assemble + delta + recall),
  `skills/assemble` + `tools/briefing.py` (the recall leg moves out), a new `skills/recall`
  subagent.
- The briefing (ADR-0009) returns to its four parts; the salient subgraph is no longer §7 of the
  briefing but a peer brief beside it.
- If the Cortex grows to where the salience traversal wants its own cadence or budget, the
  independent agent is already the right seam — that future tuning needs no further architecture.
