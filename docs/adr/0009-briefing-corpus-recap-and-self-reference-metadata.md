# The briefing is corpus + Recap; edge work carries mandatory intent and a two-tier, mechanical source-feedback

The edge presents a **briefing** to orient the agent at every dispatch — **three projections**: Knowledge
clusters (← graph), Direction (← log), and a new **Recap** (← corpus). The **corpus** is the edge's *own*
created content (a fold of `artefato.published`); the **Recap** projects it, synthesized **fresh** against
the mentee's current Atividade. Edge work carries **mandatory intent** (CONTRACT C3) plus a minimal
metadata schema, and **source feedback** is a **two-tier** (mechanical hypothesis → grill-curated)
relevance signal over **Mundo and Atividade**. Grounded in a 4-source 2026 survey.

## Status

proposed (2026-06-06; Voz ratifies)

## Context

- The sweep (ADR-0008) digests the mentee's **Atividade** but **excludes autonomous beats** — so the edge
  had **no leg reading its own work**: no self-reference for continuity, and no way to relate what it did to
  what the mentee is doing. (Voz: "the next leg is summarizing the agent activity.")
- "State digest" (the `assemble` hand-up) was a mechanical, unnamed brief; `briefing.md` / exp-009 were the
  lineage. Voz reframed it: the **briefing** is the collection presented to orient the agent, in parts.
- The **intent kernel** lost its durable home when ADR-0008 dissolved consolidate — and autonomous-beat
  transcripts are excluded from the sweep, so the *why* could vanish entirely.
- **Research (4 sources, 2026; X · HN · arXiv · exa):** intent is the **most-neglected yet highest-value**
  field (STITCH arXiv:2601.10702 uses an intent tuple as the *primary* retrieval index; Sayou's SAMB
  benchmark: decision-reasoning recall **67% structured vs 18.5% embeddings**). Source-feedback is best done
  **mechanically** (AgentOS `RetrievalFeedbackSignal` detects used-vs-ignored post-hoc; MemQ arXiv:2605.08374
  propagates outcome credit through the provenance DAG). **Artifact→human-outcome credit is unbuilt** across
  all systems surveyed.

## Considered options

- **Keep "State digest" / a flat dump.** Rejected: no structure, no self-reference, no corpus.
- **Corpus grown from beat logs/blog outside the log.** Rejected: a second source of truth vs ADR-0006 —
  the corpus is a **fold of the log's `artefato.published`**, a new lens, not a new store.
- **Source-feedback by agent self-rating.** Rejected: cognitive burden **and** unreliable (the field's
  lesson). The agent must carry no scoring load.
- **Source-feedback purely mechanical (overlap).** Partial — a noisy proxy; adopted **as the hypothesis tier
  only**, refined by outcome credit and curated by the grill.

## Decision

- **Briefing** — the orientation presented at **every dispatch** (and `/load`): three **projections** —
  Knowledge clusters (← graph) · Direction (← log) · **Recap** (← corpus). Composed by `assemble`;
  **supersedes "State digest"**. The handoff (intent-kernel breadcrumb) is one pragmatic input, not the briefing.
- **Corpus** — the edge's own created content; a **fold of `artefato.published`** events. Per-install (own
  group), the **reflexive** complement to Mundo/Atividade/Voz; autonomous beats land here, not in the sweep.
- **Recap** — a **projection of the corpus**: the agent's recent steps + their *why*, correlated **fresh at
  compose-time** to the mentee's current Atividade. Not a stored link (orientation must be current; the
  stored `cites`/`distills` are provenance, not the relation).
- **Mandatory intent (C3)** — every dispatch that produces an Artefato emits an **`intent.kernel` event** at
  close: the *why* the corpus carries and the Recap projects. Closes the kernel-home gap left by ADR-0008.
- **Artefato metadata schema** (the consensus core, four fields):
  `{ intent, cites:[{ref, kind: mundo|atividade, relevant}], distills:[cluster:…], proposes:[{body, kind, relates_to?}] }`.
  **`impact` is derived** from `proposes` at compose-time, **not stored** (the field has not solved
  outcome-credit; keep minimal).
- **Source feedback — two-tier** (the edge's universal hypothesis→curated shape; **one curation act** — the
  grill — now governs Knowledge, Direction, **and** Sources):
  - **hypothesis (mechanical, no agent/mentee load):** intrinsic citation (the agent names sources as part of
    writing a cited Artefato) + **outcome credit** (Voz ratification of a `proposes` / engagement, propagated
    back through `cites`, MemQ-style) + retrieval-use detection (`RetrievalFeedbackSignal`). Never self-rating.
  - **curated (grill + Voz):** the grill distills the mentee's **reasoned** source opinion ("values X in
    reports because Y"), **re-ranks the Source roadmap with curated authority**, exempt from passive aging,
    retirable only by Voz.
  - Spans **Mundo and Atividade** — *"this commit was relevant to this report."*

## Consequences

- The edge gains a **reflexive leg** (corpus) and self-reference for continuity; the briefing **relates the
  edge's work to the mentee's live work** — the mentoring payload, not just a state dump.
- **Intent becomes durable and load-bearing** (C3) — ahead of the shipped field, where intent is the
  most-neglected field.
- Source value is learned **mechanically + outcome-grounded** (zero cognitive burden), and the mentee's
  reasoned preference is **curated** — closing the **artifact→human-outcome** loop the 2026 survey found
  **unbuilt**.
- **Consistent** with ADR-0006 (all briefing parts are projections/folds of the log), ADR-0007 (two-tier,
  grill-curated — now generalized to a third object), and ADR-0008 (the sweep; `intent.kernel` closes its gap).
- Cost: a corpus fold + a Recap synthesis at compose-time (one LLM call in `assemble`); a new `intent.kernel`
  event type; the source-feedback outcome-credit wiring. Build is a follow-up (new issue), extending the
  spine after #9/#13/#15/#16/#14: `intent.kernel` emission → corpus fold (`corpus_at` + `state/corpus.md`) →
  Recap composition in `assemble` → source-feedback credit (citation + outcome) + the grill's curated tier.
- Open: the mechanical hypothesis tier's overlap heuristic is a proxy; the **outcome-credit** path is the
  trustworthy signal, but depends on `proposes` ratification / engagement actually happening (sparse early).
