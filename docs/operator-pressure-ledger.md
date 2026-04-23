# Operator Pressure Ledger and Session Digest (#333, #334)

This document records the current architecture decision for turning recent Claude sessions into a usable runtime feedback layer for Edge.

The goal is **not** to add another prose memory file. The goal is to create a feedback surface that tells the system what state the operator keeps trying to impose, with better provenance than the agent's own guesswork.

## Core idea

Recent sessions should produce an **operator pressure ledger**:

- what the operator keeps asking to change
- what keeps being corrected repeatedly
- what desired state changes are still open
- what has already been promoted into workflow / procedure / capability / policy
- what is still unresolved, superseded, ignored, or revoked

This becomes the highest-signal short-horizon memory layer in the system.

## Scope

This layer is consumed by **all skills**, not just meta skills.

No skill should start blind to repeated operator corrections or explicit recent direction.

Different skills may consume different render profiles later, but no skill opts out of the pressure layer.

## Three-layer architecture

Keep these concerns separate:

1. **Canonical pressure items**
   - small, structured, append-only records extracted from recent sessions
   - designed for diffing, status transitions, and provenance

2. **Digest render**
   - compact LLM-generated render derived from the canonical items
   - injected into preflight
   - optimized for current decision-making, not archival storage

3. **Periodic redigest snapshots**
   - consolidated, reviewable artifacts derived from the canonical items
   - segmented and indexed for retrieval
   - not the same thing as the hot preflight digest

Do not collapse these into one blob.

## Canonical item model

The storage unit is a small semantic item, not a markdown summary.

Each pressure item should capture at least:

- `id`
- `kind`
  - `directive`
  - `correction`
  - `question`
  - `tentative`
  - `failure`
  - `contradiction`
  - `resolution`
  - `outburst`
- `content`
- `target`
  - `workflow|procedure|capability|policy|skill|thread|research`
- `status`
  - `active|promoted|resolved|superseded|ignored|revoked|needs_review`
- `repeat_count`
- `created_at`
- `last_seen_at`
- `valid_until`
- `entities`
- `provenance`
- `supersedes`
- `promoted_to`

## Emotion policy

Emotion is metadata, not the main gate.

What matters most is `kind`.

- `kind=directive` can still promote even if the operator is frustrated
- `kind=outburst` should not promote
- `kind=open_question` or `kind=tentative` should route to threads / research / claims instead of workflow

In other words:

- `kind` does the main routing
- `emotion` refines confidence and review behavior

## Promotion policy

### Allowed to auto-promote

An item may auto-write a workflow / procedure / policy when it is clearly:

- from the operator
- explicit
- global in scope
- non-duplicative
- still active

This is intentionally more permissive than the current system in one sense and more constrained in another:

- more permissive because Edge can still write workflows on its own
- more constrained because the authority is now tied to **explicit operator direction**, not weak inference

### Not allowed to auto-promote

Cluster / pattern inference without explicit operator direction should **not** auto-write workflows in this pipeline.

For now, that path stays dormant:

- cluster and pattern detection may still generate `suggestions`
- but they do not directly create workflow files through the pressure-ledger route

This makes the new architecture safer than the current autonomous workflow promotion path.

## Routing policy

The pressure ledger should drive at least two channels:

1. **Promotion channel**
   - explicit operator directives and repeated corrections
   - may create workflow / procedure / policy

2. **Research / thread channel**
   - open questions
   - tentative ideas
   - uncertain directions
   - contradictions and unresolved failures

Examples:

- `directive` + global scope -> promotion candidate
- `correction` + repeated -> promotion candidate
- `question` + `uncertain` -> thread / research candidate
- `tentative` + `uncertain` -> discovery candidate

## Preflight use

Every skill preflight should inject a compact digest derived from recent pressure items.

That digest is **hot memory**:

- short-horizon
- bounded
- current
- operational

It should answer:

- what the operator wants changed right now
- what has been corrected repeatedly
- what remains unresolved
- what is currently blocked
- what recent direction should constrain this skill

The hot digest is not the retrieval artifact.

## Postflight use

Postflight should update the pressure layer, not just read it.

At minimum, postflight should:

- extract new candidate pressure items from the recent session delta
- update repeat counts and status transitions
- detect whether a repeated directive was crystallized or ignored
- record new promotion outcomes

This is where the system learns whether operator pressure is actually changing the substrate.

## Retrieval and indexing

Do **not** index the incremental hot digest.

Instead:

- keep the incremental digest operational only
- periodically generate a full redigest snapshot
- index only those periodic snapshots

Even then, do not index them as monolithic thematic documents.

They should be segmented semantically by:

- entities
- decisions
- repeated failures
- unresolved questions
- contradictions
- status
- recency

This gives Edge episodic / operational retrieval instead of just another prose blob in the corpus.

## Consumers

This layer should have direct runtime consumers:

1. **all skill preflights**
2. **workflow / procedure / policy promotion logic**
3. **threads / research candidate routing**
4. **health / learning metrics**

It should not exist as passive documentation only.

## Health and learning implications

The pressure ledger is also the best place to measure whether the system is learning from the operator.

Useful metrics include:

- repeated guidance still active
- promotion latency
- revoked promotions
- unresolved repeated failures
- enforcement gaps
  - operator repeated themselves even though a workflow already existed

This separates:

- failure to crystallize
from
- failure to enforce

## Rollout order

Implement in this order:

1. canonical pressure item store
2. compact preflight digest render
3. postflight extraction and status transitions
4. periodic redigest snapshots for retrieval
5. promotion / suggestion routing

Do not start with auto-promotion from weak clustering.

## Summary decision

The pressure-ledger architecture replaces vague workflow inference with a safer contract:

- explicit operator direction may still auto-create workflow
- non-explicit inference does not
- all skills consume the resulting digest
- postflight keeps the ledger current
- retrieval uses periodic structured redigests, not the hot digest

This turns recent sessions into a canonical runtime feedback surface instead of an unstructured memory summary.
