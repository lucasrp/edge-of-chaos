# Assemble dissolves into acquire-then-project; the entry sequencer commits the cursor last

## Context

ADR-0008 dissolved Consolidate into the pull-at-open sweep. The sweep (Assemble) itself still
straddled three modules: it reads the transcript store (Aquisição), extracts and re-projects into the
graph and Direction (Cortex), and is the blocking dispatch entry (Plataforma). By ADR-0019 it is a
*sequence*, not cohesive logic of its own — so it dissolves.

## Decision

Assemble dissolves. Its parts return to their home modules:

- the cursor-guard / transcript read → **`Aquisição.sweep()`**
- the extraction → projection (graph + Direction) → **`Cortex.project()`**
- **Plataforma** owns a thin entry sequencer: at wake, blocking, `sweep()` → `project()`.

**Atomicity invariant: the sequencer commits the cursor only after *both* steps succeed.** A crash
between acquire and project leaves the cursor un-advanced, so the next wake re-reads the same sessions.
This gives all-or-nothing without a fat "Assemble module" — the transaction boundary is the
cursor-commit, owned by the sequencer, not a monolith.

## Consequences

- There is no "Assemble module"; the logic lives in the two modules it spanned.
- Cursor-commits-last is the guarantee against a half-digested state (acquired-but-not-projected =
  silently-lost sessions the cursor would hide).
- Extends ADR-0008; is the second application of ADR-0019's dissolution branch.
