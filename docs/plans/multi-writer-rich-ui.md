# Implementation Plan — Multi-Writer Rich-UI Report Producer

## Goal (success criteria)

Re-home report production onto **fanned Claude subagent writers** (the "book" method), each authoring
with the **full rich block palette**, with structure **enforced** — *if and only if* fan-out is proven
to beat the cheaper single-pass path on an **evidence-safe** pipeline. **Done when:** either (a) the
fan-out producer clears its head-to-head gate and a live producer (`skills/report`, `skills/research`)
fans N writers emitting **schema-valid, evidence-preserving** rich block-specs, gated for
**content-relative visual density**, passing the enforced close (`close.run_close`) reproducibly; **or**
(b) the gate fails and the **single-pass classic stays the default** — but, either way, the evidence-safety
fix ships, because it is a trust invariant independent of the fan-out decision.

Out of scope: reviving the gpt-5.4 conductor; the reactive/drillable dashboard (the final phase only
**preserves** the chart spec so a later effort can hydrate it).

All development is red-green-refactor (`/pocock-tdd`, CLAUDE.md §5). Each phase names its failing test first.

## The two load-bearing risks (these drive the ordering)

1. **Evidence preservation is broken, and it is a trust invariant — not presentation polish.** The palette
   has no verbatim-quote/evidence block, and the conductor's discharge gate was loosened to accept
   **paraphrase for all discharge**, conflating *claims* (paraphrase-OK) with *evidence* (must stay
   verbatim). ed's mission is intended-behavior-vs-runtime-evidence; paraphrased evidence is a corrupted
   runtime signal. → **Phase 0, before everything**, because every later decision (including the fan-out
   gate) is only valid on an evidence-safe pipeline. A blind reviewer must never be allowed to prefer a
   fluent-but-evidentially-corrupted arm.
2. **The fan-out premise may be unjustified.** The single-pass classic just produced a rich-AND-deep
   artefato (~4.8k words, 5.0/5.0 reviewers) at a fraction of fan-out's ~7x/25x cost — the recall spine
   flags this across four Artefatos as the unresolved bet. The operator has **decided on multiple writers**,
   but a decision is not evidence. → **Phase 1 ends in a blocking head-to-head gate**, run *after* evidence
   is safe, so the comparison measures evidence-preserving output.

Schema drift (the reason `drafts/assemble_book.py:norm()` exists) is real but **secondary** — a quality
tax, not a correctness or trust failure. It is handled in Phase 2.

## Phase 0 — Evidence-safety preflight (prerequisite for everything, including the gate)

Ship the trust invariant first. It applies to **both** arms (classic and fan-out) and is **independent of
the fan-out decision** — a later gate failure never un-ships it.

- **Change:** add a `quote`/`evidence` block to `render.py` + `BLOCK_SCHEMAS` carrying **mandatory source
  anchoring** — `quote_text` (verbatim) + `source_ref` (source_id/message_id) + `anchor` (byte-offset range
  **or** content hash of the source span). Preservation is not enough: **authenticity must be provable.**
  **Split the discharge rule** in `tools/conductor.py` and the producer path: paraphrase discharges a
  *claim*; an *evidence* item discharges **only** by a verbatim quote whose `quote_text` is verified to
  **equal the referenced source span** (by hash/offset lookup against the cited source) before
  normalize/close/render.
- **Test first (`tests/test_evidence_survives.py`):** (a) a known client-message string appears
  **byte-for-byte** after writer → `validate_and_normalize` → assemble → `close.run_close` → render, on
  **both** classic and fan-out paths; (b) the gate **rejects** a paraphrased evidence item; (c) the gate
  **rejects a fabricated quote** (text that matches no span in the cited source); (d) rejects a **wrong/
  nonexistent `source_ref`**; (e) rejects an **altered span** (anchor/hash mismatch); (f) accepts only a
  verbatim quote with a correct anchor.
- **Verify:** no pipeline can displace, paraphrase, **or fabricate** evidence — every evidence block is
  provably copied from its cited source. This is the precondition the Phase-1 gate measures against.

## Phase 1 — Producer + execution contract + the FAN-OUT EVIDENCE GATE

Build the producer to a real engineering contract, then **gate fan-out adoption on proving it earns its
cost — measured on the now-evidence-safe pipeline.**

- **Execution contract (`tools/producer_fanout.py`):** per-node IDs; deterministic section ordering
  independent of arrival order; per-writer deadline; retry + **idempotency** (a retried writer cannot
  duplicate a section); **partial-failure policy** (one writer fails → degrade or abort, never silently
  drop a node); cancellation; **publish-gating** (assemble is all-or-nothing before `run_close` — no partial
  publish).
- **Test first — failure injection (`tests/test_producer_fanout.py`):** stub writers AND inject timeout, a
  failed writer, a duplicate retry result, a missing outline node, and out-of-order completion; assert the
  contract holds (ordered, deduped, no partial publish, reasoned degradation). Happy-path assembly +
  `close.run_close` genus-clean is the baseline case, not the only case.
- **EXIT GATE (blocking) — blind fan-out vs classic head-to-head, made falsifiable:** a one-outline
  comparison can bless fan-out on noise — so **pre-register** before running: (i) a small **representative
  outline corpus** (e.g. a research deep-dive, a status report, a comparison, a short bite — spanning the
  report shapes); (ii) **repeated trials** per arm×outline (deterministic seeds where possible) to handle
  reviewer-score and cost variance; (iii) **explicit fail-closed thresholds** fixed *before* the run —
  fan-out ships only if, aggregated across the suite, mean quality ≥ classic mean AND cost ≤ K× classic AND
  p95 latency ≤ M× classic AND failure rate ≤ F% (K, M, F named at pre-registration, not chosen post-hoc);
  (iv) **failure aggregation** — a writer failure that aborts a report counts against fan-out's failure rate.
  Record per arm: reviewer pass rate, quality, cost (tokens/$), latency, retry/failure count.
- **STOP semantics (narrow):** **fail-closed** — fan-out is adopted only if it clears **all** thresholds
  **across the suite**; otherwise a gate failure stops **fan-out adoption only**, and the classic path —
  already made evidence-safe in Phase 0 — stays the default and is fully shippable. Publish the deciding
  numbers. Phases 2–6 (the rich-UI build) run only if fan-out passes.

## Phase 2 — `norm()` → a validating contract (schema discipline)

- **Change:** lift `norm()` into `tools/normalize.py` as `validate_and_normalize(block) -> (block, action)`,
  `action ∈ {ok, normalized, repair_requested, dropped_with_reason}`, validating against `render.py`
  `BLOCK_SCHEMAS` + `_BLOCK_TYPE_ALIASES`. Unambiguous mismatch → deterministic normalize; ambiguous/unknown
  → bounce to the writer (cap 2 repairs) → then drop **with a logged reason**. **Never a silent drop.**
- **Test first (`tests/test_block_normalize.py`):** drifted inputs (nested table wrapper, `body`→`text`,
  `columns`→`headers`, callout `style`→`variant`, stray `DIGEST`) → each maps to a render-valid block or
  `repair_requested`; a coverage counter asserts **zero silent drops**.
- **Metric:** emit `drift_rate = repaired_blocks / emitted_blocks` per run (feeds the Phase-6 go/no-go).

## Phase 3 — type→format rule over the **existing, rendering** palette

- **Change (rule):** the writer prompt carries the content-shape→block rule over the palette **that already
  renders** (3+ values→`metrics-grid`; comparison→`comparison-table`; before/after→`diff-block`; reasoning→
  `derivation`; boundary→`gap-table`; evidence→`quote`). **`chart`/`diagram` are deliberately NOT taught
  here** — they enter the writer prompt and `VISUAL_BLOCK_TYPES` only **atomically with their renderer**
  (Phase 6), so no block can satisfy visual-coverage or ship live before it actually renders.
- **No proxy-calibration risk:** the density gate (`_check_visual_coverage`) is **content-relative**, not
  threshold-tuned to a fixed block set — adding new visual types in Phase 6 does **not** recalibrate it, so
  there is no need to register chart/diagram early. (Resolves the pass-1 "don't calibrate on proxies" and the
  pass-3 "don't ship placeholder visuals" findings together.)
- **Test first (`tests/test_type_to_format.py`):** writer handed shaped fixtures emits the matching canonical
  block-type (asserted via `validate_and_normalize`), not `paragraph`.

## Phase 4 — the density gate (flip the shape-gate to a density floor)

- **Change:** invert `tools/conductor.py` `_synthetic_shape_violations` (penalize-structure → require
  content-relative visual density) by reusing `close.py` `_check_visual_coverage`; a too-prose-y section is
  **bounced** through the close's `improve_fn`/`IMPROVE_ROUNDS`, not hard-failed. Because Phase 3 already
  registered the real visual types, the gate ships calibrated on the final surface.
- **Test first (`tests/test_density_gate.py`):** a prose-wall section fails; a content-relatively-dense one
  passes; the bounce re-produces within `IMPROVE_ROUNDS` rather than raising.

## Phase 5 — wire live (existing rendering palette only)

- Route `skills/report` and `skills/research` through `tools/producer_fanout.py`; the enforced close is
  unchanged. Live reports use the 25-block palette + the evidence block — **every block type in the live
  surface renders.** No `chart`/`diagram` yet (they arrive in Phase 6). **Verify:** a real `/ed-report` run
  fans writers, preserves evidence, and publishes via `run_close`. (Reachable only if Phase 1's gate passed.)

## Phase 6 — the chart/diagram **block + renderer, landed atomically** (new deps)

Everything for chart/diagram ships **in one atomic step** so the live surface can never hold an unrendered
visual: schema registration, `VISUAL_BLOCK_TYPES` entry, writer-prompt teaching, and the renderer all land
together, behind a **dependency smoke test** — if `vl-convert`/`dot` are absent the block type stays
**disabled** (writers cannot emit it; it never counts toward visual-coverage).

- **`chart`:** payload = Vega-Lite spec; render via **vl-convert** (`pip install vl-convert-python`, pure
  Python, no browser/Node) → static SVG. **STORE THE SPEC, NEVER THE SVG.**
- **`diagram`:** Mermaid vocabulary; render browser-free via **D2** or **Graphviz** (system binary), not
  mermaid-cli's headless Chromium.
- **Gate:** add the data-ink sub-gates (density / data-ink / scale→small-multiples) to the Phase-4 gate.
- **Go/no-go:** if `drift_rate` (Phase 2 metric) rises sharply once the richer grammar is enabled, hold and
  add a stricter spec-validator before exposing charts to writers.
- **Test first (`tests/test_chart_block.py`):** a Vega-Lite spec block renders to inline static SVG; the
  **stored** block contains the spec, not `<svg>`; with deps **absent**, the block type is disabled and a
  writer attempt to emit it is rejected by `validate_and_normalize` (never a placeholder in a live report).
- **Dependency note:** neither `vl-convert` nor `dot`/`d2` is installed today (verified) — the reason
  chart/diagram are last AND gated on a smoke test, never shipping a placeholder.

## Sequencing rationale

```
Phase 0 ─ evidence-safety + AUTHENTICITY preflight (trust invariant)  ← ships for BOTH arms; gate-independent
Phase 1 ─ producer + execution contract + FALSIFIABLE FAN-OUT GATE    ← blocking, fail-closed; stops fan-out only
Phase 2 ─ validating normalize (schema discipline)
Phase 3 ─ type→format rule over the EXISTING rendering palette
Phase 4 ─ density gate (flip shape-gate; content-relative, no recalibration)
Phase 5 ─ wire live (existing rendering palette only — no placeholders)
Phase 6 ─ chart/diagram block + renderer, landed ATOMICALLY (new deps) ← smoke-test-gated; drift_rate go/no-go
```

Ordering principle: **trust (evidence) → justify (fan-out gate) → discipline (schema) → presentation
(gate) → ship → heavy deps.** The evidence invariant is fixed before any measurement; the fan-out premise
is then tested on a trustworthy pipeline; nothing downstream can regress trust.

## Risks & open questions

- **R1 — drift worsens with the richer grammar.** Mitigation: Phase 2's validating contract; measurement:
  `drift_rate`; control point: Phase 6 go/no-go. *Open:* the acceptable `drift_rate` threshold.
- **R2 — the data-ink gate may not stop chartjunk** (a property check, not perceptual). Untested until
  Phase 6; may need a stricter machine check.
- **R3 — fan-out justification** is now Phase 1's blocking gate, run on the evidence-safe pipeline. A gate
  failure stops fan-out adoption but leaves the classic path evidence-safe and shippable. This is the one
  place the plan's premise is allowed to be wrong.

## Non-goals

- No reactive/drillable dashboard (Phase 6 renders static; it only **preserves** the spec).
- No gpt-5.4 conductor revival; its deterministic pieces are lifted, its `complete_fn` dropped.
- No change to the close's review/proof/publish machinery — the producer feeds the existing gate.
