# S7 (R2/R3 grounding boundary) + S6 (R1 capability floor) — ✅ CODEX SHIP (verdict: approve)

The last and hardest slices of the triple-`/goal` enrichment build: make every owed visual carry sound,
unforgeable grounding, and make the presentation floor capability-honest — WITHOUT letting a fabricated
number hide in a visual where the reader and the reviewers can't see it. R0-for-values went **11 adversarial
codex rounds** to a clean SHIP ("no material findings").

## What shipped

**S7 — drawn-visual grounding boundary (R2/R3).** A reader-visible DRAWN visual (chart/diagram) must carry a
valid HMAC grounding attestation (`visual_grounding.sign/verify`, process-private secret), minted only when
its data is attributable to the evidence. `raw-html`/`svg`/`html`/`custom-html`/`ascii-diagram` are BANNED as
ungroundable authored visuals. Replay/transplant-proof: `close.ground_visuals` STRIPS any incoming
attestation and re-grounds against THIS artefato's cites+findings before signing. A directly-drawn ungrounded
visual is rejected by the SAME `close.check_genus` the publisher runs.

**S6 — capability-conditional presentation floor (R1).** A chart/diagram floor degrades to `env-unsat`
(not a violation) when vl-convert is absent; `_block_counts` counts only RENDERABLE blocks; the floor is
R0-SUBORDINATE (suppressed while R0 storytelling fails). `ascii-diagram` dropped from the floor types
(operator decision — renderable recipes supersede it).

**R0-for-values — the structured-visual fabrication close (the 11-round core).** A numeric magnitude shown
in a BARE DATA CELL must ALSO appear in the reader-visible EXPLANATORY corpus — a number can never live only
inside a visual where R0 (labels) and R8 (prose-only) never reach it. The model is a COMPLETENESS argument,
not a leaky allowlist: every reader-visible numeric magnitude is in exactly one bucket —
1. **value-checked** — a data-cell block's value/cell/row/AND visible label/title/badge/header
   (metrics-grid/comparison/comparison-table/table+aliases/risk-table + the top-level executive `metrics`);
2. **in the RENDER-TRUTH corpus** — the actual reader-visible text the renderer emits for every other block
   (denylist, not allowlist: callout/derivation/gap-marker/card/list/next-steps/concept/quote/… all count) +
   headings + executive_summary, with hidden text dropped and data values SUBTRACTED so a cell can't
   self-satisfy;
3. **exempt code** — code-body literals (field-specific: the code field is blanked, the visible label still
   counts);
4. **HMAC-grounded** chart/diagram data.

A dedicated generous magnitude grammar `_MAGNITUDE_RE` (distinct from S3's untouched `_NUM_TOKEN`) recognizes
every rendered numeric form on BOTH sides: plain/negative/`+99`/thousands/decimal/`.75`/`1e3`/unit-suffixed
(`300ms`), compared as floats so any equivalent prose form matches.

## The 11 codex rounds (R0-for-values)

1. Initial close: section-level data visuals + the top-level metrics dashboard, folded into R0.
2. **#1 [high] numeric-form coverage** — `_NUM_TOKEN` missed `+99`/`.75`/`1e3`. Fix: `_MAGNITUDE_RE` applied
   symmetrically to visual and prose.
3. **#2 [high] plain `table` cells skipped** — extended the checked set to `DATA_TABLE_TYPES`.
4. **#3 [high] `risk-table`/`next-steps` escaped the type-allowlist** — flipped from a leaky allowlist to a
   completeness partition (data-cell vs sentence-corpus vs code vs grounded).
5. **#4 [high] numeric CHROME (a comparison side `title` "AUC 99")** — value-check reader-visible
   labels/titles/badges/headers of data blocks.
6. **#5 [high] `name`/`id`/`input_label`/`output_label` wrongly non-visible** — audited every
   `_NONVISIBLE_KEYS` member against render.py; the corpus credits all genuinely-visible fields.
7. **#6 [high] unrendered-metadata laundering** (`description:'99'` on a grid, `hidden_note` on a paragraph)
   — corpus rebuilt from RENDER-TRUTH (render the block, keep only reader-visible text); data values
   subtracted so no self-satisfy.
8. **#7 [high]×2** — executive_summary scanned raw (Markdown-URL `href` numbers) → render-truth; and
   safe_style-permitted CSS hiders (content-visibility/zoom/offscreen) → fail-closed corpus hiding.
9. **#8 [high]×2** — `height:0;overflow:hidden` clip combo + numeric headings (section/exec titles) in no
   bucket → clip-to-zero check + headings into the corpus.
10. **#9 [high] safe-listed spacing/line metrics** (`line-height:0;overflow:hidden`, negative
    letter/word-spacing) → explicit value checks.
11. **#10 [high] author `overflow` made the corpus WEAKER than R0** (`width:1px;overflow:hidden`, non-zero) →
    removed the overflow-expanded allowlist entirely. The corpus now uses the **identical** `_style_hides_text`
    + `_R0_SAFE_PROSE_PROPS` as the R0 storytelling floor — provably no weaker than R0 by construction.

## ✅ CODEX SHIP (round 11, verdict: approve)
> "I could not find a defensible parity break in the targeted diff. The R0-for-values rendered-style corpus
> now uses `_style_hides_text(render.safe_style(style))` with the same `_R0_SAFE_PROSE_PROPS` path as the R0
> prose floor, so overflow/overflow-x/overflow-y fail closed rather than being credited. No material findings."

## Verification
- Dedicated suites green: test_visual_grounding (44), test_floor_subordination (2), test_floor_evaluator
  (20), test_conductor_visual (12), test_publisher (77), test_storytelling_floor (31),
  test_internal_evidence_cite (31), test_genus (55), test_new_producer_is_declarative (8).
- Full-suite blast radius **17 failing files = a STRICT SUBSET of HEAD's 20**; the diff additionally FIXES 3
  (conductor_circuit_breaker, internal_evidence_cite, storytelling_floor) and introduces **0 net-new**. All
  17 are pre-existing env-dependent (neo4j / no vl-convert / live-runtime surfaces).

## Documented residual (honest, parallel to the accepted R8-prov)
Per-datum PROVENANCE grounding of a structured value to a SPECIFIC cite span — once forced into the corpus a
value is reviewable by the blind reviewer + cite/R8 layer, but it is not HMAC-bound to a cite the way a drawn
chart's data is. Closing it soundly needs the conductor structured-visual grounding seam + the P1
explorer-evidence pipeline. AND: any CSS hiding vector `_style_hides_text` doesn't catch (e.g. color==background
matching) is a PRE-EXISTING property of the shared R0 detector affecting the R0 floor itself — not introduced
here; hardening it would benefit both.

**With S7+S6 approved, all of goal-3's slices S1–S10 are codex-approved (S5 deferred-documented).**
