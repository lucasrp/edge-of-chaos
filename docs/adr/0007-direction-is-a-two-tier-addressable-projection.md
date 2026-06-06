# Direction is a two-tier addressable projection: grill-`proposed` and Voz-`set` threads, folded from the log

The **Direction** standing page holds two tiers — `proposed` (the grill's strategic achados,
hypothesis) and `set` (Voz-ratified, curated) — as **addressable items** with an explicit
propose/set/drop lifecycle, **both rendered**, folded from the event log (ADR-0006). Artefatos
**declare** candidate steers; the **grill** consolidates them into `proposed`. This refines ADR-0006's
single `direction.set` blob and the CONTEXT.md `Direction` term.

## Status

proposed (2026-06-06; Voz ratifies)

## Context

- ADR-0006 declared `direction.set` events folded to a page, but only **one tier** (Voz) and
  **last-write-wins on a single `{plan}` blob** (`eventlog.py:direction_at`/`project_direction`).
- The grill's second, load-bearing output is **orientation** — the strategic read, the next bet, the
  decision not yet made (`grill/SKILL.md`). Today it dies in the transient handoff: the edge persists
  **facts** (clusters/curated) but not **strategy**. Voz named the gap: *"estamos montando os fatos mas
  não estamos montando isso ainda."*
- A wholesale blob re-introduces **evaporation-by-omission** — a thread survives only if the grill
  re-states it every consolidation; miss it once and it is silently gone. That is the exact failure the
  change exists to remove, reproduced one layer up.
- Artefatos **exist to move or confirm Direction** (the house "decision not yet made" section), but they
  are **read-only on state** (CONTRACT C1) — they cannot write Direction.

## Considered options

- **Single-tier, Voz-only Direction; grill achados live elsewhere.** Rejected: fragments one concept
  into two homes; strategy stays homeless.
- **Two tiers as wholesale-rewritten blobs (`proposed` blob + `set` blob).** Simpler, matches the
  current tool. Rejected: evaporation-by-omission returns — the property we are trying to kill.
- **Two tiers as addressable items with explicit lifecycle.** Chosen: a thread persists until
  deliberately dropped; promotion and provenance are first-class.
- **Artefato writes `direction.proposed` directly.** Rejected: two consolidators, and it skips the
  harm-potential funnel — every report's open question would auto-become a steer.

## Decision

- **Two tiers, mirroring hypothesis/curated.** `proposed` (grill, hypothesis) and `set` (Voz, curated).
  `curado > hipótese`: `set` outranks `proposed`. "A correção sempre ganha" — `set` is always Voz-originated.
- **Addressable items.** Each thread has a stable `id` and an optional `kind ∈ {phase, priority,
  constraint, thread}`. Events (asserted per ADR-0006 — direct Cypher, no LLM, replayable):
  - `direction.proposed {id, body, kind, from_artefato?, relates_to?}`
  - `direction.set {id, body, supersedes?}`
  - `direction.dropped {id, reason}`
- **Persist-until-dropped.** A thread survives until an explicit `direction.dropped`. Never lost by
  omission — the anti-evaporation property, the whole point.
- **Fold/replay per id.** Last event per `id` wins; `set` outranks `proposed` for the same `id`;
  `dropped` removes it. `direction_at(t)` folds to the as-of-then page (both tiers). **Strategic
  versioning = replay.**
- **The page renders both tiers** — a `Set` section (ratified) and a `Proposed` section (open threads).
- **Artefato → Direction.** An Artefato declares candidate steers in its own `artefato.published`
  event: `proposes: [{body, kind, relates_to?}]` — open a fresh thread, or confirm/challenge an existing
  one. It **never writes Direction itself.** The **digestion sweep** (ADR-0008) auto-writes each candidate
  into the **non-curated `proposed` tier** — eagerly, even when ambiguous — so the tier is current at every
  dispatch entry. The candidate is **optional** — a knowledge-only Artefato proposes nothing and only
  deepens a cluster.
- **Who writes which tier.** The **`proposed` tier is populated permissively** — by the sweep (artefato
  candidates) and by the grill's live orientation; ambiguity is allowed to *exist* there, flagged. The
  **`set` tier is the grill's alone**: on in-session Voz ratification it promotes `proposed → set` (the
  same promotion it runs on knowledge). The grill's **harm-potential funnel applies to curation, not
  entry**: it promotes the high-harm and drops/merges the noise — *"don't drain the hypothesis tier;
  consolidate what carries harm potential."*
- **Obsoletes `eventlog.py`'s last-write-wins `{plan}` blob.** `direction_at`/`project_direction` rework
  to a per-id fold and a two-tier render.

## Consequences

- The grill's strategic achados become **durable, replayable, versioned** — the gap closed.
- Strategy **leaves the transient handoff** and lives in Direction (a fold); killing the handoff no
  longer loses the steer (see ADR-0008).
- **Provenance is explicit** (`from_artefato`): a steer traces to the Artefato that proposed it, even
  after that blob is pruned.
- Cost: `id` management and a richer event taxonomy than ADR-0006 sketched — kept to append-only JSONL +
  per-id pure-function fold, no framework ("shed scaffolding toward a legible core").
- Build (tracer-bullet, ADR-0006 — Direction projection first): rework `eventlog.py` to the per-id fold;
  render the `Proposed` tier; add `proposes` to `artefato.published` and to `grill_lint`'s agenda.
- Consistent with ADR-0005 (render unchanged — it now projects a two-tier page) and ADR-0006 (asserted
  edges fold from the log; versioning survives because the edge was declared, not inferred).
