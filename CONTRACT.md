# edge — Contract

Standing invariants the edge must **always** honor. These are the guarantees you check
behavior against — each clause is always-true or never-do.

This is not the glossary (`CONTEXT.md` = what words mean) and not the decision log
(`docs/adr/` = what we chose and why). A decision can be superseded; an invariant holds
across decisions. Add a clause only when it is a genuine invariant, and keep each to the
canonical one-line statement — ADRs reference a clause, they do not restate it. Keep this short.

## C1 — No external side effects

The edge reads, absorbs, and understands, and delivers knowledge **to read**. It does not act
in the world. The mentee's work — every source key (Mundo / Atividade / Voz) — is **read-only**;
the edge writes only to its own wiki and state. Acting in the world or mutating operator-owned
state requires explicit, scoped operator approval, never an autonomous beat decision.

_Origin: the old edge's founding contract (`~/edge/CONTEXT.md`) + rules-core #5. Bounds the
agentic-first beat of ADR-0001; affirmed under "everything agentic" by ADR-0002._

## C2 — Extraction is incremental, never full-store

Every dispatch re-extracts (zep/Graphiti) and re-projects **only the session delta since the cursor**,
never the whole transcript store. Construction is the lifecycle's dominant cost; per-dispatch work stays
proportional to what is new, not to store size. A full-store rebuild is a manual, explicit operation —
never an automatic dispatch effect.

_Origin: bounds the eager extraction of ADR-0008 (pull-at-open digestion) under the construction-cost
finding (recall confrontation, arXiv 2606.06448 — construction energy dominates the lifecycle)._

## C3 — Edge work carries its intent

Every dispatch that produces an Artefato emits an **`intent.kernel` event** at close — the *why* of the
work (what is open, the next bet). Edge work without a recorded intent is **incomplete**; the kernel is
mandatory metadata, not an optional breadcrumb. It is the durable *why* the **corpus** carries and the
briefing's **Recap** projects.

_Origin: Voz (2026-06-06) — "intent is relevant metadata to edge work; if it isn't mandatory, it should
be." Closes the kernel-home gap left by ADR-0008 dissolving consolidate; feeds the corpus/Recap (briefing)._
