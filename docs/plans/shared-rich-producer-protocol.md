# Implementation Plan — A Shared Rich Producer Protocol (every artefato form, present *and future*)

## Goal (success criteria)

Every producer skill — the five today (`report`, `research`, `map`, `plan`, `discovery`) and **any added
later** — inherits **one shared presentation protocol** that guarantees **rich output**, where richness is
**declared, not coded**:

- **Common, enforced for all (the protocol):** the full block palette, a type→format discipline, and a
  **generic floor-evaluator** that reads each producer's *declared presentation obligations* and enforces
  them — plus the rich block vocabulary (diagram now, chart later).
- **Per-producer, content-relative (the form):** a small **descriptor** that DECLARES the form's
  obligations (required blocks/counts/structure). The cognitive moves stay owned by the content-relative
  genus gate, never by the descriptor.

**Done when:** (a) a NEW producer with a **nontrivial declared floor** (e.g. "≥2 illustrations" or "framed
steps + a dependency diagram") publishes a rich artefato through the close with **zero edits** to
`skills/_shared/*`, `tools/close.py`, `tools/render.py` — proving richness is declaration, not
re-implementation; and (b) each existing non-prose producer renders richly by default (`map`
multi-illustration, `plan` framed steps + dependency diagram, `discovery` contextualized bite).

Out of scope (separate efforts): the fan-out-vs-classic question (`multi-writer-rich-ui.md`); the chart
renderer's heavy deps (`vl-convert`); the reactive dashboard.

All work is red-green-refactor (`/pocock-tdd`, CLAUDE.md §5). Each phase names its failing test first.

## The principle — two orthogonal axes, and the floor is DECLARED

The regression to fix is a conflation: "lean form" was allowed to mean "poor presentation." Form and
presentation are orthogonal, and crucially **the presentation floor is itself part of the per-producer
declaration** — so the shared close can enforce it generically without knowing any producer by name.

| Axis | Who owns it | Enforced where |
|---|---|---|
| The **rich rite / genus moves** (derivation · what-I-don't-know · external-frame · lineage) | the shared genus gate — **unconditional, content-relative** (ADR-0013) | close, **always**, for every developed Artefato |
| Presentation vocabulary + the **generic floor-evaluator** | the shared protocol | shared scaffold + close |
| The form's **declared PRESENTATION obligations** (required blocks/counts/structure) — **additive only** | the producer's descriptor | close, evaluating the declaration ON TOP of the genus floor |

**Invariant (ADR-0013, hard):** the descriptor can only ADD presentation obligations. It can **never**
subtract from, narrow, or opt a producer out of the rich rite — the cognitive-move floor is decided by the
*content* (content-relatively), not by the producer's declaration. Rich presentation is additive to deep
cognition, never a substitute for it.

**Extensibility test (the load-bearing acceptance, Phase 4):** a new producer declares its floor from the
shared **predicate vocabulary**; the close evaluates it with no new branches. If satisfying a new producer's
floor needs a code change to scaffold/close/render, the seam has failed.

## What already exists — build ON it (ADR-0012/0013)

`skills/_shared/scaffold.md` ("the loop structure is the same for every producer; only the slot-fill
differs"), `skills/_shared/pipeline.md` + `tools/close.py` (one content-relative genus gate), `tools/render.py`
(one palette). The protocol **lifts the PRESENTATION floor into the shared layer as a generic evaluator, and
makes each form's presentation floor a declaration the evaluator reads** — not new machinery beside the old.
The **rich rite stays exactly where ADR-0013 put it**: the unconditional, content-relative genus gate
(`close._check_rich_rite`), applied to every developed Artefato regardless of producer. The protocol **adds**
presentation; it does **not** touch the genus.

## Phase 0 — The descriptor + the predicate vocabulary + the generic floor-evaluator (the seam)

This is the whole extensibility seam; everything else reads it.

- **Descriptor shape (minimal, ENFORCEABLE, and ADDITIVE-only):**
  `{ name,
     richness: { require: [ {predicate, args}, ... ] } }`   # ADDITIONAL form-specific PRESENTATION obligations
  No `owed_moves` field — the cognitive-move rich rite is NOT a per-producer declaration; it is the
  unconditional, content-relative genus gate (see "What already exists"). The type→format writer-hint surfaces
  the blocks named in `richness` first — one field drives steering and presentation enforcement (no separate
  `favored_blocks`, YAGNI).
- **Predicate vocabulary (a small, stable, shared set — PRESENTATION predicates only):**
  `min_blocks_of(types,n)`, `any_of([predicate,...])` (capability degradation), `has_structure(id)`
  (e.g. `framed_steps`), `contextual_framing`. **The rich rite is never expressible as a predicate and cannot
  be weakened by any descriptor** — it stays the unconditional, content-relative genus gate. Adding a producer
  reuses these; only a genuinely new *kind* of presentation obligation grows the vocabulary (rare, deliberate,
  shared — never per-producer).
- **The generic floor-evaluator (in `tools/close.py`):** reads `descriptor.richness.require`, evaluates each
  predicate by its stable ID against the artefato's blocks. **No per-producer branch exists anywhere.**
- **Capability-aware from the start (folds in pass-1 finding #2):** the evaluator separates two failure
  classes — **writer-unsatisfiable** (the form COULD be satisfied but the draft fell short → bounce through
  `improve_fn`) vs **environment-unsatisfiable** (a required capability, e.g. Graphviz `dot`, is absent with
  no `any_of` fallback → mark unsatisfied for an environmental reason and **do NOT retry generation**, surface
  a capability error). `any_of` lets a floor degrade (`any_of([diagram, ascii-diagram, comparison-table])`)
  so an optional renderer's absence never makes a floor impossible.
- **No-regression rollout (folds in pass-2 finding #2):** in the SAME phase, give all **five existing
  producers** a descriptor (initially a permissive floor that matches today's output), so that the moment
  "missing descriptor → fatal" goes live, **every shipping producer already has one** — there is no
  intermediate state where a live producer cannot close. Floors are *tightened* later (Phase 3); Phase 0 only
  guarantees coverage + the evaluator.
- **Test first (`tests/test_floor_evaluator.py`):** a synthetic descriptor with a **nontrivial** floor
  (`min_blocks_of([diagram,ascii-diagram],2)` + `has_structure(framed_steps)`) is evaluated correctly with
  **zero per-producer code**; an unknown producer with no descriptor fails **loud** (never defaults to
  report's floor); **every existing producer still closes/publishes** under the new descriptor-lookup path
  (the regression guard); an `any_of` floor passes via fallback when `dot` is absent; an
  environment-unsatisfiable floor is marked unsatisfied **without** burning `improve_fn` rounds.

## Phase 1 — Type→format rule in the shared scaffold (lifts all five now)

- **Change:** add the content-shape→block rule to the **shared** writer instruction in
  `skills/_shared/scaffold.md`, surfacing the blocks named in the producer's `richness.require` first while
  keeping the full palette reachable: 3+ values→`metrics-grid`; comparison→`comparison-table`;
  reasoning→`derivation`; boundary→`gap-table`; relation/flow→`diagram` (or `ascii-diagram` fallback);
  evidence→`evidence`.
- **Test first (`tests/test_type_to_format_shared.py`):** for each descriptor, a writer handed shaped fixture
  content emits the matching canonical block (asserted via the render normalizer), not `paragraph`, and leads
  with its declared blocks.

## Phase 2 — The `diagram` block (the shared rich-illustration enabler) — a SAFE renderer contract

Built BEFORE existing producers declare diagram-dependent floors. Because `diagram` becomes a shared default
block carrying **writer-controlled content**, it is a renderer *and a trust boundary* — both are specified
here (folds in pass-2 finding #1).

- **Single input grammar — DOT only.** The block schema accepts **DOT** (what Graphviz `dot` actually parses);
  the writer emits DOT, not "Mermaid-ish" text. Mermaid, if ever wanted, is a **separate** capability/renderer,
  never silently conflated. The normalizer **validates the DOT grammar** and rejects invalid input with a clear
  error (not a writer-failure misclassification, not a crash).
- **Sanitized SVG boundary.** The `dot -Tsvg` output is **allowlist-sanitized before inlining**: strip
  `<script>`, all `on*` event attributes, `<foreignObject>`, and any external/`xlink:href`/`href`/`<image>`
  references — the inlined SVG must be inert and non-network-capable.
- **Capability-gated:** register in `VISUAL_BLOCK_TYPES` and the Phase-0 capability registry (block → required
  binary). If `dot` is absent the normalizer rejects the block (never a placeholder) and `any_of` floors fall
  back to `ascii-diagram`/`comparison-table`.
- **Test first (`tests/test_diagram_block.py`):** valid DOT renders to inline SVG; **invalid DOT** is rejected
  with a grammar error (not a silent pass, not a crash); **hostile labels/URLs** (a node label containing
  `<script>`, an `xlink:href` to an external URL, a `javascript:` link) produce **sanitized, inert** SVG with
  no script/event/external-ref surviving; with `dot` absent the normalizer rejects the block and the registry
  reports it unavailable; `visual-coverage` counts `diagram` as a visual.

## Phase 3 — Tighten the five existing producers' floors + re-aim them onto the protocol

The descriptors already exist (Phase 0, permissive). Here each `richness.require` is **ratcheted up** from the
permissive placeholder to the form's real floor, and per-skill presentation logic the protocol now owns is
deleted (surgical).

- Tighten each existing descriptor's `richness.require` to encode its form's real **presentation** floor —
  `map`: `min_blocks_of([diagram,ascii-diagram],2)`; `plan`: `has_structure(framed_steps)` +
  `any_of([min_blocks_of([diagram],1), min_blocks_of([ascii-diagram],1)])`; `discovery`:
  `contextual_framing`. `report`/`research` declare **no** presentation floor here — their depth is already
  the genus rich rite, which applies to all forms unconditionally. Delete per-skill presentation logic the
  protocol now owns (surgical — only what's replaced).
- **Test first (`tests/test_producers_rich_default.py`):** a dry produce of each producer, through the close,
  clears its declared presentation floor by default, with **no producer-local presentation code**;
  capability-degraded environments (no `dot`) still pass via fallback.
- **Genus-floor regression test (`tests/test_descriptor_cannot_opt_out_of_rich_rite.py`)** (per pass-3): a
  producer (e.g. `map`) whose CONTENT is developed prose (≥ the rich-rite trigger) but is missing a move —
  no `what-i-dont-know`, say — **still FAILS close**, even when its declared presentation floor (2 diagrams)
  is fully satisfied. The descriptor adds; it never buys a way out of the genus.

## Phase 4 — Prove extensibility: a NEW producer is a declaration only (the goal's acceptance)

- **Change:** add one throwaway producer (e.g. `critique`) by writing ONLY its descriptor — with a
  **nontrivial, novel floor** declared from the predicate vocabulary (not just a favored-block hint) — plus a
  3-line skill that fills the scaffold slots. Touch **nothing** in `skills/_shared/*`, `tools/close.py`,
  `tools/render.py`.
- **Test first (`tests/test_new_producer_is_declarative.py`):** the new producer produces and publishes a
  rich artefato that **clears its declared floor**, with **zero diffs** to the shared files (asserted by a
  git-diff check in the test scope). If any shared file must change, the seam is wrong — this is the
  protocol's falsifiable proof.

## Sequencing rationale

```
Phase 0 ─ seam: descriptor + predicate vocabulary + capability-aware evaluator
          + descriptors for ALL FIVE existing producers (permissive) + no-regression guard
Phase 1 ─ type→format in the shared scaffold (lifts all five now)
Phase 2 ─ diagram block: DOT-only grammar + sanitized-SVG boundary, capability-gated  ← before diagram floors
Phase 3 ─ tighten the five existing producers' floors + re-aim
Phase 4 ─ prove a NEW producer with a nontrivial declared floor works edit-free   ← blocking acceptance
```

Principle: **the seam and its evaluator first (with capability/failure handling built in), then the enabler,
then declare the known producers, then prove the seam holds for an unknown future producer.** Richness is a
declaration the shared evaluator enforces; adding a producer is declaration, never re-implementation.

## Risks & open questions

- **R1 — the predicate vocabulary is too small (a real new producer needs a new predicate).** Then the
  vocabulary grows — that is the ONE deliberate, shared extension point, and it is acceptable as long as it is
  rare and shared (not per-producer). *Open:* the right starting predicate set; Phase 4 pressure-tests it.
- **R2 — over-abstraction (YAGNI).** Mitigation: every descriptor field and predicate is read by an actual
  gate; if Phase 4 passes with fewer, cut them. (`altitude` was dropped from the descriptor — it belongs to
  the deferred two-altitude work, not here.)
- **R3 — a declared floor false-fails a lean form** (the procrustean trap, ADR-0012/0013). Mitigation: a form
  owes only the PRESENTATION blocks its descriptor declares, plus whatever the content-relative genus gate
  independently triggers; the Phase-0/3 tests assert a bite is never failed for presentation blocks it does
  not declare, nor for cognitive moves its content does not trigger.
- **R4 — the `diagram` block is a writer-controlled trust boundary.** Inlining `dot`-generated SVG admits
  hostile labels/links. Mitigation: DOT-only validated grammar + allowlist SVG sanitization (Phase 2), with
  hostile-input tests; the inlined SVG must be inert and non-network-capable.

## Non-goals

- The fan-out-vs-classic question; the chart renderer's heavy deps; the reactive dashboard.
- No change to the content-relative *genus principle* — the protocol parameterizes the floor per declaration;
  it never makes the floor procrustean.
