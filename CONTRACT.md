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
