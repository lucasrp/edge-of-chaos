# S7 — grounding boundary for drawn visuals (R2/R3) · local-verified

- **`visual_grounding.py`** — per-visual UNFORGEABLE attestation: `sign`/`verify`/`attest` over the block's
  canonical data, keyed by a PROCESS-PRIVATE secret. `verify` is blind-safe (secret + block, no evidence).
- **`close.ground_visuals`** — signs each chart/diagram/ascii-diagram whose data is `visuals.attributable`
  to the artefato's CITE snippets (the evidence spans); wired into run_close before every genus check.
- **`close._check_visual_grounding`** (in check_genus) — DEFAULT-DENY: chart/diagram/ascii-diagram MUST
  carry a valid attestation else `visual-grounding:ungrounded:<t>`; raw-html/svg/html/custom-html are
  BANNED authored-visual paths (`visual-grounding:banned-authored-visual:raw-html`). Structured palette
  blocks (table/metrics-grid/comparison) are OUT of scope (R0/visual-coverage, not free-data grounding).
- **`visuals.add_visuals`** — signs each `build_spot`-verified splice (conductor path).
- **`visuals.attributable`** — added the `ascii-diagram` branch (R3): every node/edge word token grounds
  per-token against the evidence, CAPABILITY-INDEPENDENT (runs with or without vl-convert).
- A directly-drawn ungrounded visual is rejected by the SAME check_genus the publisher runs; a fabricated
  datum/edge invalidates the HMAC.

## Verification
- `tests/test_visual_grounding.py` — 14 tests (attestation sign/verify/tamper/forge; ungrounded rejected;
  signed passes; raw-html/svg banned; structured blocks out of scope; cite-grounded signed clean; ascii
  grounded/ungrounded; capability-independent). Net-new blast radius vs HEAD: ZERO (publisher fixture
  pre-signed; the 18 pre-existing env/vl-convert failures unchanged; test_visuals' 9 are pre-existing
  vl-convert render-drift, not _grounding).

## Iteration 2 — ascii dropped + replay/transplant fixed (Codex S7 #1/#2 + operator decision)
- **ascii-diagram DROPPED** (operator decision): a free-form ascii relation can't be soundly grounded and
  carries no advantage over the renderable diagram/chart. `attributable` reverted (no ascii branch);
  ascii-diagram joins raw-html/svg in `_UNGROUNDABLE_AUTHORED_VISUAL_TYPES` → an authored ascii-diagram is
  rejected (`visual-grounding:ungroundable-authored-visual:ascii-diagram`). `_GROUNDABLE = {chart, diagram}`.
- **[high] replay/transplant fixed**: `ground_visuals` no longer skips already-signed blocks — it STRIPS any
  incoming `_grounding` and RE-GROUNDS from scratch against the artefato's OWN evidence (cite snippets +
  any findings), so a transplanted/replayed token whose data the current evidence doesn't support is left
  unsigned → flagged. Regression: a validly-signed chart transplanted into an unsupported artefato → flagged.
- 16 tests; net-new blast radius ZERO (publisher fixture migrated; baseline 18).

## Iteration 3 — structured-visual grounding: attempted, scoped to a documented follow-on (Codex S7 #1/#2)
- **[medium] #2 telemetry owed capability-aware (FIXED)**: `publisher._form_owes_visual` now returns owed
  only when `vl-convert` is present — a wheel-less map/plan with no renderable visual is NOT owed, matching
  the S6 'absent → not owed' contract (no adoption-denominator corruption).
- **[high] #1 structured data visuals**: I EXTENDED grounding to metrics-grid/comparison/comparison-table
  (generic per-token attribution) and measured it — it (a) cascades into the conductor's OWN
  `_genus_violations` (the conductor's writers emit these with no grounding seam → broadly flagged), and
  (b) is FRAGILE (token-matching authored values against paraphrased cite snippets false-fails legit data).
  DECISION (operator, with conviction): REVERTED — S7 grounds the DRAWN visuals (chart/diagram, via the
  add_visuals seam + cite/finding re-grounding) and bans raw-html/svg/ascii. Structured data visuals are
  governed by R0 (labels explained in prose) + R8 (prose numeric claims grounded via the runstore) +
  visual-coverage; a dedicated structured-visual attestation needs a conductor grounding seam for them +
  the richer explorer-evidence pipeline (P1), tracked as **R2-structured** (documented in close.py). This
  is the honest scope — a fragile, cascading guard is worse than the layered R0+R8 coverage already present.
- 16 tests; baseline 18 unchanged.
