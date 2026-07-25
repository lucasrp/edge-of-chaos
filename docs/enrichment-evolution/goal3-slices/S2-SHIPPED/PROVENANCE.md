# S2 — R0 storytelling floor (DOMINANT) · local-verified snapshot

**Slice:** S2 (R0): EXPLAIN, don't label — the dominant requirement (the user's core ask: "same
information as the book, visually rich, without trading content for visuals"). Working tree only.

## The ADR-0013 split (deterministic structure vs semantic judgment)
- **DETERMINISTIC (in `close.check_genus`): R0-II(d)** — `_check_storytelling_floor`: a SECTION carrying a
  visual/labeled STRUCTURE (VISUAL_BLOCK_TYPES + data tables, keyed by TYPE so it is robust to renderer-
  shape drift) but NO accompanying non-visual prose unit (paragraph/callout with real text) is flagged
  `r0:visual-without-prose`. This is the operator's exact regression — a diagram/list of phase siglas with
  no prose explaining them. Content-relative (no visual → no owe) and genus-relative (a non-narrative map
  is never failed for lacking a prose ARC, only for a visual with no explanation at all).
- **SEMANTIC (blind reviewer, ADR-0013): R0-I adequacy + R0-III claim-preservation** — folded into the
  `narrative_depth` dimension: every term/acronym/label a visual or heading introduces must be EXPANDED in
  prose at first use; enriching must not drop a claim the artefato's OWN source carried (paraphrase/split/
  merge ok; surface-mention-that-drops-the-claim or a retained contradiction fails); source-relative,
  property-not-section. (Keys unchanged → reviewer-dimension tests stay green.)

## Deferred (documented, not silently skipped)
- **R0-III typed-claim MECHANIZATION** (claim-id + source-span + normalized entities, deterministic
  paraphrase/split/merge matcher) and **R0-II narrative-metric CALIBRATION from the book `eeb696e`** (S2a:
  freeze prose/concept ratio, transition coverage, K-through-line) are the book-MIGRATION slice's targets,
  not the generic gate (the plan: not cabling a fixed claim-set into the generic close.check_genus, else a
  map/plan on other material false-fails). The semantic enforcement above carries R0-I/III now; full
  deterministic mechanization is follow-on. This is the plan's flagged subjective-risk area, handled by
  routing semantics to the reviewer rather than a brittle deterministic NLI.

## Verification
- `tests/test_storytelling_floor.py` — 8 tests OK (visual-without-prose fails; visual+prose passes;
  callout counts; pure-prose owes nothing; map+prose passes / map-without-prose fails; heading-only fails;
  additional_sections checked).
- close suite 71, reviewers, adr_close, internal_evidence 31, runstore 11, envconf 5 — all OK.
- One correct fixture fix: `test_new_producer_is_declarative` (a critique with a comparison-table now
  carries a paragraph — R0-conformant). Net new breakage vs HEAD: ZERO (the 18 env/pre-existing failures
  are unchanged).

## Iteration 2 — visible-prose owe + top-level metrics (Codex S2, 2 findings)
- **[high] hidden prose satisfied the owe**: `has_prose` read raw authored fields (`_block_text`), so a
  paragraph styled display:none/opacity:0 counted as the explanation while the reader saw only the chart.
  Fix: `has_prose` now reuses the S3 reader-visible machinery — `_render_visible(render.render_block(b))`
  — so a CSS-hidden prose block renders to no text and does NOT clear the owe.
- **[medium] top-level metrics bypass**: `content.metrics` is a visual the renderer emits OUTSIDE any
  section, so `_sections` missed it. Fix: a substantive top-level metrics grid now owes reader-visible
  prose SOMEWHERE in the artefato (exec-summary item or a section paragraph/callout), else flagged.
- Regressions: CSS-hidden prose (4 styles) next to a chart still fails; top-level metrics without prose
  fails; with section prose or exec-summary prose passes. 12 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 3 — list bypass + benign-styled prose (Codex S2, 2 findings)
- **[high] label-only `list` bypass**: a bare list of phase siglas wasn't in the owing set → a list-only
  section passed. Fix: `_R0_LABELED_BLOCK_TYPES` now includes `list` (aliases bullet-list/ordered-list/
  bullets resolve via `_type`); a list-only section owes prose, a list+paragraph passes.
- **[medium] benign-styled visible prose treated as hidden**: reusing S3's all-style-drop made a legit
  `color:#111` paragraph not count → false-fail. Fix: R0-specific `_r0_prose_visible` + `_R0_HIDING_STYLE`
  — counts benignly-styled VISIBLE prose, drops only genuine hiders (display:none/visibility:hidden/
  opacity:0/font-size:0/offscreen). Opposite fail-direction from S3 (a missed exotic hider degrades to a
  narrative_depth reviewer catch, never a false PASS). Top-level metrics path uses `_r0_any_visible_prose`
  with the same predicate.
- Regressions: list-only fails (3 aliases); list+prose passes; benign-styled prose (4 styles) passes;
  CSS-hidden prose (4 styles) still fails. 15 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 4 — card-family owe + zero-variant hiders (Codex S2, 2 findings)
- **[high] card-style structures bypassed**: card/numbered-card/risk-table/code-block/template-block are
  reader-facing labeled structures but weren't in the owing set. Added them to `_R0_LABELED_BLOCK_TYPES`
  (now: visual palette + data tables + list + card/numbered-card/risk-table/code-block/template-block).
  Prose/explanation-by-nature blocks (paragraph, callout, derivation, gap-*, glossary, bibliography,
  subsection) are deliberately excluded — they ARE the explanation.
- **[medium] zero-variant CSS hiders**: opacity:00 / font-size:00px / opacity:.0 parse as 0 (hidden) but
  the regex matched only single "0". Added `_CSS_ZERO` = (0+(\.0+)? | \.0+), covering 0/00/0.0/.0/0.00,
  still excluding 0.5/5.
- Regressions: card/numbered-card/risk-table/code-block-only sections fail; card+prose passes; zero-variant
  styled prose (5 forms) hidden→fails. 18 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 5 — real _block_text bug + scale hider (Codex S2, 2 findings)
- **[high] _block_text flattened `style` as prose**: `_block_text` includes the `style` string, so an
  empty `{"type":"paragraph","style":"color:#111"}` (no body) falsely cleared has_prose. Fix:
  `_r0_prose_visible` now reads the canonical `text` field the renderer actually displays (via
  render.canonical_block), not `_block_text` — an empty styled block can no longer pose as prose.
- **[medium] scale:0 / transform:scale(0)** collapse text visually; added to `_R0_HIDING_STYLE`.
  Documented: the hider denylist is BEST-EFFORT for the plausible hiders; the narrative_depth blind
  reviewer is the backstop for exotic CSS-collapse (a miss → reviewer catch, never a security hole).
- Regressions: empty styled paragraph/callout next to a chart → fails; scale:0 / scale:0.0 /
  transform:scale(0) prose → fails. 19 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 6 — markup-only prose + scale decimal boundary (Codex S2, 2 findings)
- **[high] markup-only body**: a paragraph text of "<br>" (or other markup-only) has truthy .strip() but
  renders no visible explanation. Fix: `_r0_prose_visible` now requires `_render_visible(render.render_text
  (text))` to yield non-whitespace — markup-only bodies render nothing and don't satisfy the owe.
  (render_text emits no style attrs, so this strips only tags/break-separators, never benign styling.)
- **[medium] scale:0.5 false-fail**: the scale hider matched the leading "0" of "0.5" (word boundary
  before the dot). Fix: scale property requires a value terminator `(?=[\s;,]|$)`; transform scale(...)
  requires the zero to be followed by `,`/`)`. So scale:0.5 / transform:scale(0.5) / opacity:0.5 pass;
  scale:0 / scale:0 0 / transform:scale(0) / transform:scale(0,0) still fail. `\b` before `scale` avoids
  matching inside `grayscale`.
- Regressions: markup-only ("<br>") prose fails; non-zero scale/opacity/font-size visible prose passes.
  20 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 7 — exec-summary rendered-visible consistency (Codex S2 #3)
The markup-only gap also lived in the top-level-metrics path: `_r0_any_visible_prose` validated
executive_summary items with raw `.strip()`, so `executive_summary: ["<br>"]` cleared the metrics owe.
Fix: the summary path now shares the SAME rendered-visible predicate as the block path
(`_render_visible(render.render_text(s)).strip()`). Regression: top-level metrics + markup-only summary
fails. 21 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 8 — font-size zero-unit class (Codex S2 #3)
font-size:0<unit> (0vw/0vh/0ch/0rem) is the SAME font-size:0 hider with a different unit (safe_style
permits any alphabetic unit) → it bypassed the px/pt/em/rem/% allowlist. Fix: the font-size hider now
accepts zero + ANY unit (`[a-z%]*`), closing the whole unit class while still rejecting non-zero
(0.5rem). Regressions added for 0vw/0vh/0ch/0rem on the section path and the metrics path. 22 tests OK;
blast radius unchanged (18 pre-existing).

## Iteration 9 — percent-zero generalized (Codex S2 #3)
opacity:0% / scale:0% / font-size:0% / transform:scale(0%) are the SAME zero-value mechanism with a percent. Decisive generalization: a shared `_ZERO_VAL` = CSS-zero + optional unit/percent applied uniformly to opacity/font-size/scale (and transform:scale). Verified hide set {0,00,0.0,.0,0px,0vw,0ch,0rem,0%,00%,scale(0%)} all matched; visible set {0.5, 50%, 1.0, 14px, 0.5rem, color} all pass. 22 tests OK; blast radius unchanged.

## Iteration 10 — renderer-consistent style check (Codex S2 #3, the decisive alignment)
Codex's key insight: the floor checked the RAW author style, but render_paragraph emits
`safe_style(style)` which DROPS any paren-bearing declaration. So (a) transform:scale(0)/clip:rect(…)
were false-FAILED (renderer strips them → text visible) and (b) the `font:0px serif` shorthand was a real
bypass (kept by safe_style, sets zero size). Decisive fix:
- `_r0_prose_visible` now runs the hider check against `render.safe_style(style)` — EXACTLY what the
  renderer emits — and only for PARAGRAPH blocks (a callout's `style` is a variant/class, never CSS, so a
  callout is never hidden by it). This removes the whole paren-function false-fail class and aligns the
  predicate with renderer output.
- Added the `font:` shorthand zero-size branch; removed the transform:scale / clip branches (dead against
  sanitized style — parens are stripped).
- Tests: transform:scale(0)/scale(0.5) now PASS (visible, stripped); font:0px/0%/bold-0px serif FAIL
  (hidden); callout with CSS-looking style passes (variant). 23 tests OK; blast radius unchanged (18).

## Iteration 11 — transparent text + DOCUMENTED denylist boundary (Codex S2 #3)
Added the well-known color-transparency hiders (kept by safe_style, no parens): color:transparent,
zero-alpha hex (#0000 / #00000000), -webkit-text-fill-color:transparent. Opaque colors (#000000/#fff/
named) correctly stay visible.
**Operator decision (documented boundary, per the re-flagged-root cadence rule):** the deterministic R0
denylist now covers the enumerated KNOWN single-declaration text-hiders — display:none, visibility:hidden,
opacity:<zero>, font-size:<zero>, font: shorthand zero, scale:<zero>, offscreen (negative indent/left/top),
transparent/zero-alpha color — checked against the SANITIZED style render emits (paren-function hiders are
already stripped by safe_style). A deterministic gate cannot soundly enumerate ALL of CSS; per ADR-0013
the narrative_depth BLIND REVIEWER is the authoritative backstop for both explanation ADEQUACY and any
novel/multi-declaration CSS-collapse (contrast hiding, width:0+overflow, clip-path). A denylist miss
degrades to a reviewer catch, never a security hole. 25 tests OK; blast radius unchanged (18).

## Iteration 12 — declaration parser (Codex S2 #3, ends the substring-unsoundness)
Flat-substring regex on CSS was unsound: `color` matched inside `background-color:transparent` (false-fail)
and missed colored zero-alpha hex (#fff0/#ffffff00). Decisive fix: `_style_hides_text` now PARSES the
sanitized style declaration-by-declaration with EXACT property names. Hiders: display:none, visibility:
hidden, opacity/font-size zero (any unit/%), scale with a zero axis, font: shorthand zero size,
color/-webkit-text-fill-color transparent or zero-alpha hex (#RGBA / #RRGGBBAA), offscreen negative
indent/left/top. Verified: background-color/border-color:transparent and opaque colors PASS;
color:#fff0/#ffffff00/transparent FAIL; transform:scale(0) PASS (safe_style strips parens). 25 tests OK;
blast radius unchanged (18). [boundary note from iter-11 stands: novel/multi-declaration collapse = the
documented narrative_depth reviewer backstop, ADR-0013.]

## Iteration 13 — font bare-zero + offset precision (Codex S2 #3)
- **[high] font:0/0 serif bare-zero size**: unitless 0 is a valid length, so the shorthand size "0" hides
  but my unit requirement missed it. Fix: strip the /line-height component, then any css-zero size token
  (bare 0 / 0px / 0%) hides; family/keywords are never css-zero. font:14px/0 serif (line-height 0) stays
  visible.
- **[medium] left/top:-Npx false-fail**: an offset alone doesn't hide (needs position:absolute) → removed
  left/top from the single-declaration denylist (the offscreen idiom is multi-declaration → reviewer
  backstop). text-indent now requires a LARGE negative (>=100, the off-screen text-replacement idiom);
  text-indent:-1px stays visible.
- Verified: font:0/0, font:0, font:0px, italic-bold-0px shorthand + text-indent:-9999/-100 FAIL;
  font:14px/0, text-indent:-1px/-2px, left/top:-Npx, opaque colors PASS. 25 tests OK; blast radius 18.

## Iteration 14 — visibility:collapse (Codex S2 #3)
visibility:collapse is a sibling hiding value on the same `visibility` property → added to the branch ({hidden, collapse}). Regression added. 25 tests OK; blast radius 18.

## Iteration 15 — signed-zero (Codex S2 #3)
scale:-0 / scale:1 -0 / opacity:-0 — CSS signed zero is still zero. _CSS_ZERO_VAL now accepts an optional leading "-" (signed zero is never a visible value for any property, so this is safe; -5/-0.5 still visible). The zero-value class is now complete across sign / unit / percent / leading-zeros. 25 tests OK; blast radius 18.

## Iteration 16 — signed-zero hardening + refuted false-positive (Codex S2 #3)
Codex flagged opacity:+0 / font-size:+0px / scale:+0 as bypasses, on the premise that safe_style keeps
plus-signed values. VERIFIED FALSE: render.safe_style's value charset has no `+`, so it DROPS every
`+`-signed declaration → an `opacity:+0` paragraph renders with default opacity → text reader-VISIBLE →
correctly counts as prose. No bypass on the real pipeline (the predicate checks safe_style output).
Hardened anyway (defense-in-depth, harmless — signed zero is never visible): `_CSS_ZERO_VAL` now accepts
`[+-]?`, so both -0 and +0 are caught at the parser level should a future safe_style ever keep them.
Regressions: +signed style renders VISIBLE on the full pipeline (safe_style strips it → passes); signed
zero (-0/+0) is hidden at the parser level. 27 tests OK; blast radius 18.

## Iteration 17 — ALLOWLIST: decisive end of the hider arms race (Codex S2 #3)
content-visibility:hidden and zoom:0 (kept by safe_style) were the latest single-declaration bypasses.
Per the cadence rule (the "single-declaration hider" root re-flagged many rounds), inverted the model:
`_style_hides_text` is now ALLOWLIST-based — prose counts only if EVERY sanitized declaration uses a
property in `_R0_SAFE_PROSE_PROPS` with a non-hiding value; hide-capable props keep their value checks;
ANY unknown/exotic property (content-visibility, zoom, future-X) fails CLOSED. This permanently closes the
bypass class — an unknown property can never produce a false PASS. Fail-closed is the right direction for
R0; benign-but-exotic styling just means the author writes plainer prose (reviewer backstops adequacy).
Verified: content-visibility:hidden / zoom:0 / some-future-prop FAIL; all common benign + opaque + offset
+ non-zero styles PASS. 28 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 18 — unit-aware text-indent (Codex S2 #3)
text-indent:-50em / -99% / -7rem hide (off-screen) but my px-only >=100 threshold missed them. Fix:
`_text_indent_hides` converts the magnitude to real px via a unit table (em/rem≈16, etc.; %/vw/… treated
relatively, >=50 hides), so a small px/em hanging-indent nudge (-1px/-20px/-1.5em/-10%) stays visible
while a far off-screen indent (-50em≈800px / -99% / -9999px) hides. Satisfies BOTH the earlier
-1px-visible requirement AND the -50em-hides requirement. 28 tests OK; blast radius 18.

## Iteration 19 — display allowlist + visible-glyph + max-height typo (Codex S2 #3, 3 findings)
- **[high] display non-painting modes**: display:table-column / table-column-group don't paint text but
  passed (only `none` was rejected). Fix: `display` is now a POSITIVE visible-value allowlist
  (`_VISIBLE_DISPLAY`); any non-painting value hides.
- **[high] zero-width-only prose**: ​/‌/‍/﻿ survive str.strip() and render_text but show
  nothing. Fix: `_has_visible_glyph` requires a painting glyph (Unicode L/N/P/S/M), excluding whitespace
  (Z*) and zero-width/format/control (C*); applied to both block and exec-summary prose paths.
- **[medium] allowlist typo**: the layout set repeated `max-width` instead of `max-height`, false-failing
  visible `max-height:10rem` prose. Fixed.
- Regressions: non-painting display + zero-width-only prose FAIL; display:block/flex/max-height:10rem PASS.
  30 tests OK; blast radius unchanged (18 pre-existing).

## Iteration 20 — variation selectors / default-ignorable glyphs (Codex S2 #3)
U+FE0F/FE0E (Mn, default-ignorable) rendered nothing alone but counted as marks. Fix: _has_visible_glyph now requires a BASE painting category (L/N/P/S — drops marks M), and excludes default-ignorable letters (Hangul fillers, CGJ). Verified: variation selectors/CGJ/Hangul-filler FAIL; real text/emoji/accented/numbers PASS. 32 tests OK; blast radius 18.

## Iteration 21 — float-parse numeric values (Codex S2 #3, ends the zero-form arms race)
opacity:0e0 / font-size:0e0px / scale:0e0 / text-indent:-1e3px (CSS exponent notation) bypassed the
literal-form regex. Decisive fix: numeric values are now PARSED AS FLOAT (`_num_unit` → float(magnitude),
unit) — so any zero form (0/.0/0px/0%/0e0/-0) is caught by `==0.0` and off-screen text-indent by the real
magnitude (sign/decimal/exponent-aware), not chased literal-by-literal. Verified: 0e0 forms hide; nonzero
exponents (1e0=1, 1e1px=10px, -9e1px=-90px<100) stay visible. 33 tests OK; blast radius 18.

## Iteration 22 — Braille blank U+2800 (Codex S2 #3)
U+2800 BRAILLE PATTERN BLANK (category So) renders empty but counted as a symbol glyph. Added to _DEFAULT_IGNORABLE. Braille-blank-only prose now FAILS; real text passes. 33 tests OK; blast radius 18.

## ✅ CODEX SHIP (iter-22, verdict: approve)
No material findings: no single-declaration false-PASS, no common-visible-prose false-FAIL, no structural bypass. Remaining risk = the DOCUMENTED multi-declaration/contrast-collapse class delegated to the narrative_depth blind reviewer (ADR-0013). S2 COMPLETE — working tree only.

## Summary of S2 R0 deliverable
DETERMINISTIC (close.check_genus): R0-II(d) `_check_storytelling_floor` — a section (or top-level metrics) with a visual/labeled structure (visual palette + data tables + list + card/numbered-card/risk-table/code-block/template-block) owes a reader-visible prose unit. Visibility = visible-glyph + allowlist-of-safe-properties + float-parsed non-hiding values, checked against the SANITIZED style render emits. SEMANTIC (narrative_depth dimension): R0-I definition adequacy + R0-III source-claim preservation. DEFERRED (documented): R0-III typed-claim mechanization + R0-II book-metric calibration = the book-migration slice.
