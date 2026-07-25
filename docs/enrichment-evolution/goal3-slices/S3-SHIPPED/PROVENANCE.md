# S3 — internal-evidence tier (R8) · local-verified snapshot

**Slice:** S3 (R8 internal-evidence cite: content-addressed runstore ref grounds an internal numeric
claim without an external snippet; never counts toward rich-rite:external-frame).
**State:** local-verified, pre-codex re-gate. Working tree only — no commits, nothing to main/fleet.

## What this iteration closed (Codex S3 #5, two [high])
1. **ref ↔ attested address binding** (`tools/close.py` `_check_cites`): the public `ref` must equal
   `runstore:<address>` for the SAME address that is attested. A missing / non-runstore / divergent
   ref now fails even when the hidden `internal_evidence.address` resolves — the displayed citation can
   no longer dereference a different run than the one verified.
2. **CSS-hidden visible-text** (`_visible_text` / `_VisibleTextParser`): the claim corpus is rendered
   via `render.spec_to_html` and only reader-DISPLAYED text is kept; `display:none` /
   `visibility:hidden` / `aria-hidden` subtrees are dropped. A claim hidden inside a CSS-hidden
   raw-html span no longer satisfies the in-content binding.

## Verification
- `tests/test_internal_evidence_cite.py` — 18 tests OK (added: hidden-raw-html ×2 styles; ref-bind ×4 refs)
- `tests/test_close_loop.py` 68 · `tests/test_runstore.py` 11 · `tests/test_envconf.py` 5 — all OK

## Iteration 2 (Codex S3 #6, one [high])
- **boolean `hidden` attribute** (`_VisibleTextParser` / new `_attrs_mark_hidden` helper): the HTML
  `hidden` boolean attribute is browser-default `display:none` but was not detected — `<span hidden>…</span>`
  survived rendering and its text was still collected. Centralized all hidden mechanisms in
  `_attrs_mark_hidden` (boolean `hidden`, `aria-hidden=true`, inline display:none/visibility:hidden);
  fail-toward-hidden on any `hidden` presence regardless of value. Regression extended to 6 span variants
  incl. `<span hidden>`, `<span hidden="">`, and a nested `<div hidden><p>…</p></div>` subtree.

## Iteration 3 — DECISIVE class-kill (Codex S3 #7, the reader-invisible-claim root, 3rd flag)
Codex flagged reader-invisible claim text a THIRD time (now opacity:0/font-size:0/clip/offscreen/
`<template>`/closed `<details>`). Blocklisting CSS hide-tricks is an unbounded arms race, so per the
operator cadence rule (re-flagged root twice → decisive architectural change, not more heuristics) the
fix moves to the SOURCE:
- **`_strip_raw_html`**: raw-html (and its aliases html/custom-html/svg, resolved via
  `render.canonical_block`) is the SOLE author-controlled-markup vector — verified: `render_block` is
  dispatched only from `render_section`, no renderer recurses into arbitrary nested block lists, and no
  trusted renderer emits any hiding tag/style. It is now stripped from the claim corpus recursively
  before rendering. The grounding claim must live in TRUSTED rendered prose (which by construction
  carries no hide-styling) — closing the ENTIRE open-ended CSS/HTML hide class in one move.
- `_VisibleTextParser` (hidden-subtree drop) retained as defense-in-depth for trusted renderers.
- Regression: 11-variant raw-html matrix (incl. opacity:0, font-size:0, <template>, closed <details>,
  and even a fully-VISIBLE raw-html claim) all fail to bind; aliases excluded; trusted prose still binds.
- **Operator-decision note:** the grounding claim sentence MUST appear in trusted authored prose, never
  only in a raw-html block. This is intended contract (reinforces R0 explain-not-label), not a regression.

## Iteration 4 — close the 2nd hide vector (Codex S3 #7 continued)
Codex correctly refuted my premise: TRUSTED renderers DO carry author style — `render_paragraph`
(and `render_list`) pass `b["style"]` through `safe_style`, whose `_CSS_DECL` permits opacity:0 /
font-size:0 / position:absolute;left:-9999px / display:none / color-hiding. So a claim in a styled
trusted paragraph was reader-invisible yet bound.
- **`_attrs_mark_hidden` widened**: ANY non-empty inline `style` now drops the element's subtree from
  the claim corpus (we cannot prove author CSS keeps text visible → fail-closed), alongside the boolean
  `hidden` attr and aria-hidden=true. Kills the open-ended CSS class without enumerating declarations.
  Removed the now-unused `_HIDDEN_STYLE` regex (orphaned by this change).
- Regression: claim in a paragraph styled opacity:0 / font-size:0 / offscreen / color:#fff / display:none
  / visibility:hidden all fail; plain unstyled prose still binds.
- **Contract (operator-decision):** a grounding claim must live in UNSTYLED trusted prose. raw-html and
  styled blocks are excluded from the grounding corpus. Visual richness is unaffected — only what may
  *carry a numeric grounding claim* is constrained, which reinforces R0 (explain-in-prose, not label).

## Iteration 5 — PROSE-ONLY corpus (Codex S3 #7, corpus root)
Codex raised the deeper root: even with raw-html + styled text excluded, the corpus still included ALL
trusted blocks, so a claim shown only in a TABLE CELL / HEADING / CHART LABEL / LIST item bound without
any prose explanation — the exact visual-substitutes-prose failure mode this whole effort exists to kill
(R0: explain-not-label).
- **`_prose_blocks` + prose allowlist** (`_PROSE_BLOCK_TYPES = {"paragraph"}`): the grounding corpus is
  now built ONLY from prose blocks found anywhere in the spec (explicit `type` resolving to paragraph;
  non-block data dicts and every non-prose/visual/tabular block excluded). This SUBSUMES the raw-html
  strip (raw-html isn't prose), so `_strip_raw_html` was removed as orphaned.
- `_visible_text` now renders only the collected prose, then still drops hidden/styled subtrees
  (`_attrs_mark_hidden`) → a claim must appear in UNSTYLED PROSE.
- Regression: claim only in subsection(heading)/table/chart/list/metrics-grid all fail; unstyled prose
  still binds; styled prose still fails; raw-html (all variants + aliases) still fail.
- **Contract (operator-decision, final):** an internal numeric claim grounds ONLY when it is explained in
  unstyled prose. Tables/charts/headings/labels remain free for visual richness — they simply cannot be
  the SOLE home of a grounded number. This is the storytelling floor, enforced at the gate.

## Iteration 6 — topology-faithful corpus (Codex S3 #7, nested-metadata)
Real bug in iter-5's `_prose_blocks`: it recursed into ALL values of non-prose dicts, so a
paragraph-shaped dict `{"type":"paragraph","text":claim}` buried in a chart/table/list METADATA field
(never rendered by render_section) was collected and re-rendered as prose → claim bound while
reader-invisible. The corpus had diverged from what the page actually renders (ADR-0013 violation).
- **`_prose_blocks` now delegates to `_iter_blocks`** — the existing helper that walks the EXACT render
  topology (`sections[].blocks` / `additional_sections[].blocks`) — and keeps only top-level blocks whose
  canonical type is paragraph. No recursion into block payload fields. Collection wrapped fail-closed.
- Regression: a valid table/chart/list carrying a nested paragraph-shaped dict in a payload field, with
  no visible prose claim → fails. All prior regressions still green (23 tests).

## Iteration 7 — span-binding + exec-summary corpus (Codex S3 #7: fragment + exec-summary)
Two more real findings:
- **[high] fragment-binding**: `claim in content_text` let a producer cite a SUB-FRAGMENT of a larger,
  possibly NEGATED sentence ("the run did NOT score AUC 85.0" grounded by fragment "score AUC 85.0").
  Fix: the claim must now equal a FULL reader-visible prose SPAN — a whole sentence or whole prose unit,
  boundary-aligned (`_claim_spans` + `_norm_span` + `_SENTENCE_SPLIT`), not an arbitrary substring.
  Sentence split is decimal-safe (splits only on terminal punct + whitespace); normalization collapses
  whitespace and strips trailing terminal punctuation. `_check_cites` now takes `claim_spans` (set), not
  a flat `content_text`.
- **[medium] exec-summary omitted**: render renders top-level `executive_summary` as prose and rich-rite
  counts it as prose, but `_iter_blocks` omitted it → corpus ≠ rendered output. Fix: `_visible_prose_units`
  now includes each executive_summary item, rendered + parsed per-unit (no cross-unit span fusion).
- Architecture: corpus is built per-PROSE-UNIT (`_visible_prose_units` → `_render_visible`), so sentence
  spans never fuse across paragraphs/summary items. `_visible_text` removed (replaced).
- Tests reworked so the grounding claim is a standalone sentence; +3 regressions (negated-fragment,
  exec-summary-binds, full-sentence-among-prose). 25 tests green; close_loop/runstore/envconf green.
- **Residual (documented, operator-decision):** span-binding closes FRAGMENT selection; a fully-quoted
  but semantically NEGATED sentence cited as grounded is a truthfulness question for the blind reviewer /
  human, not a deterministic gate concern.

## Iteration 8 — whole-unit binding + implicit paragraphs (Codex S3 #7: split-fabrication + implicit)
- **[high] sentence-split fabrication**: `_SENTENCE_SPLIT` split on any terminal punct, so `e.g.` / `i.e.`
  / `No.` / ellipses fabricated false sentence boundaries → a fragment after `e.g.` became a bindable
  span, reopening fragment-selection. An abbreviation-aware tokenizer is itself unbounded, so the decisive
  fix drops sentence-splitting: a claim must equal a WHOLE prose UNIT (full paragraph / summary item).
  `_SENTENCE_SPLIT` removed; `_claim_spans` is now one normalized entry per unit. A grounded number must
  be EXPLAINED in its own prose unit.
- **[medium] implicit paragraphs**: `_prose_blocks` required an explicit string `type`, but render_block
  defaults a typeless block to paragraph — so `{"text": "..."}` rendered as visible prose yet was excluded
  from the corpus. Fix: since `_iter_blocks` yields only real block slots, `canonical_block` now speaks for
  the renderer — a typeless block is admitted as an implicit paragraph; a non-string type → None → excluded.
- Regressions: abbreviation/ellipsis fragment cannot bind; implicit-paragraph claim binds like explicit.
  27 tests green; close_loop/runstore/envconf green.

## Iteration 9 — callout corpus + numeric ≥1000 + provenance residual (Codex S3 #7, 3 findings)
- **[medium] callout corpus mismatch**: rich-rite counts `callout` as prose (`PROSE_BLOCK_TYPES =
  {paragraph, callout}`) but internal-evidence used a private `{paragraph}` set. Fix: internal-evidence
  now reuses the SHARED `PROSE_BLOCK_TYPES`, so the two prose definitions can never diverge. (render_callout's
  `style` field is a VARIANT→CSS-class, not an inline style — not a hide vector; its text is visible.)
  Private `_PROSE_BLOCK_TYPES` removed.
- **[medium] numeric ≥1000**: `_NUM_TOKEN` capped the integer part at 1–3 leading digits, so plain
  `1000`/`12345`/`-5000`/`10000` were never recognized → valid metrics failed binding. Fix: integer part
  is now grouped-run OR plain `\d+` (grouped tried first so comma numbers never split); all S3 #2/#3
  boundary protections preserved (verified across a 16-case matrix).
- **[high] runstore provenance → ACCEPTED RESIDUAL (operator decision, documented as R8-prov)**: content-
  addressing gives integrity + claim↔value↔address↔prose binding, NOT runner-authentication. Closing it
  needs harness-signing/job-provenance infra absent from the architecture; fabricating one's own
  measurement is an ADR-0013 blind-reviewer/human concern, not a deterministic-gate guarantee. Documented
  in requirements R8 ("Limite de proveniência") and tracked as future R8-prov, out of S3 scope.
- Regressions: callout binds; large ungrouped values bind. 29 tests green; close_loop/runstore/envconf green.

## Iteration 10 — <br> fusion + comma-prefix boundary (Codex S3 #7, 2 findings)
- **[high] <br> digit fusion**: render_text safelists producer `<br>`, but the visible-text parser added
  no separator → `1000<br>0` fused to a reader-invisible `10000` that a cite could ground. Fix:
  `_VisibleTextParser` now emits a space separator for `<br>` and block-level tags (`_BREAK_TAGS`); inline
  formatting (strong/em/code/…) deliberately does NOT separate, so `8<strong>5</strong>` stays `85`.
- **[medium] comma-prefix**: the new ungrouped `\d+` alt could match the PREFIX of a malformed comma run
  (`1000,000`→`1000`, `1,0000`→`1`). Fix: trailing `(?!,\d)` rejects a run that is a comma-number prefix;
  sentence commas (`85, then`) still bind; valid multi-group numbers (`1,234,567`) still bind.
- Regressions: <br>-split digits don't fuse; malformed comma prefixes don't bind. 31 tests green;
  close_loop/runstore/envconf green.

## ✅ CODEX SHIP (iter-10, verdict: approve)
No material findings in the deterministic path: visible-prose corpus, ref/address binding, whole-unit claim matching, standalone numeric-token checks, runstore content-address integrity all hold. Only residual = documented R8-prov (out of scope). S3 COMPLETE — working tree only, no commit.
