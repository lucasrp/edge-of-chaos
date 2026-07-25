# A straddling concept resolves by one rule: cohesive logic gets an owner and an interface; a mere sequence dissolves

## Context

The 9-module refactor repeatedly hit concepts that live across two or more modules —
grounding-floor (Aquisição↔Julgamento), Assemble (Plataforma↔Aquisição↔Cortex), wiki_render
(Provisão↔Cortex), the Voz rail (Publicação↔Curadoria↔Aquisição), Conductor (Produção↔Julgamento),
Rich-rite/Depth (Produção↔Julgamento), and eventlog's query surface (Plataforma↔Cortex). Each is a
decision about where the logic lives, and left ad-hoc they re-create the leaks the refactor is meant
to remove.

## Decision

A straddling concept is resolved by **one test: does it have cohesive logic of its own?**

- **Yes → one owner module + a narrow interface.** The other modules *call* the interface; they never
  re-implement it. (e.g. grounding-floor is owned by Aquisição; Julgamento calls `grounding.floor()`.)
- **No — it is only a *sequence* of other modules' acts → it dissolves.** The logic returns to the
  modules it spanned; a thin sequencer coordinates. (e.g. Assemble — see ADR-0020.)

## Consequences

- No module contains another module's logic; every straddle becomes owner+interface or dissolution.
- This is the standing test for every future straddle, not a one-off resolution.
- First application on record: ADR-0008 (Consolidate dissolved). The seam-owner assignments and the
  9-module map live in `CONTEXT.md`.
