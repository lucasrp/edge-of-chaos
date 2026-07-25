# S10 — adoption telemetry event (R6) · local-verified

**Slice:** R6 — emit a DURABLE adoption event AT publish (not a retrospective scan).
- `tools/publisher.py`: `publish(...)` gains an optional `visual_flags` param and, AFTER the atomic
  commit (non-fatal, like source signals), appends an `artefato.adoption` event with:
  `producer` (skill), `owed` (form owes a visual via `_form_owes_visual` from the descriptor OR content
  triggers `close.content_owes_visual`), `satisfied` (`close.has_substantive_visual`), `degraded` &
  `shortfall` (producer-supplied flags from add_visuals), `capability_state` (`render.diagram_available()`
  at publish). The report/dashboard reads this stream — `owed`/capability can't be reconstructed later.
- `tools/close.py`: added `content_owes_visual` (the quant trigger, standalone) + `has_substantive_visual`
  (a top-level metrics grid or a substantive visual block) — the owed/satisfied predicates, reusing the
  visual-coverage primitives.
- Emission is NON-FATAL: a telemetry append failure never corrupts/blocks the published page.

## Verification
- `tests/test_publisher.py::AdoptionTelemetryEventAtPublish` — 5 tests: prose-only report (owed/satisfied
  False), quant+metrics (owed/satisfied True), producer flags recorded, capability_state matches the
  backend, map form-owed by descriptor. test_publisher 65 OK; close_loop 71, storytelling 31, reviewers 37.
- Blast radius unchanged (18 pre-existing env/visual-coverage failures).

## Iteration 2 — exec-summary owed (Codex S10)
content_owes_visual scanned only _iter_blocks (which excludes top-level executive_summary), so a numeric-dense summary with no visual emitted owed=false → under-counted adoption. Fix: content_owes_visual now also scans executive_summary strings for numeric density. Regression: a numeric-dense summary owes (owed=True, satisfied=False). 6 adoption tests OK; blast radius 18.

## Iteration 3 — list-shaped flags (Codex S10)
visuals.add_visuals returns list[str] flags, not a dict; `_adoption_event` only read a dict → a real publish forwarding the list reported shortfall=false (false-healthy). Fix: `_normalize_visual_flags` accepts dict OR list[str], deriving shortfall from "shortfall"/"dropped spot" entries and degraded from a "degrad" marker. Regression passes the actual add_visuals list shape. 7 adoption tests OK; blast radius 18.

## Iteration 4 — atomic durability + metrics owed (Codex S10, 2 findings)
- **[medium] metrics owed**: a top-level metrics grid counted as `satisfied` but not `owed` (satisfied-but-
  not-owed corrupts the ratio). Fix: `content_owes_visual` now treats a substantive top-level metrics grid
  as owed → owed/satisfied agree. Regression: metrics-only artefato → owed=True, satisfied=True.
- **[medium] silently-lossy event**: the adoption append was post-commit + swallowed, and the published
  event didn't retain the inputs → a transient append failure lost the R6 record permanently. Fix: the
  adoption event now rides in the SAME atomic `append_batch` as the published+kernel events
  (`publish_artefato_atomic(..., adoption=...)`) — durable, no crash window. The COMPUTATION is wrapped
  non-fatally (a telemetry bug never blocks the page; only that rare case omits the record). The separate
  post-commit append is removed.
- test_publisher 68 OK (8 adoption tests); test_eventlog OK; blast radius 18.

## Iteration 5 — satisfied⟹owed at block level (Codex S10)
A section-level metrics-grid was satisfied but not owed. Fix: content_owes_visual returns True whenever has_substantive_visual(content) — so ANY present substantive visual (top-level OR block-level) is owed, making satisfied⟹owed hold everywhere (verified). Regression: section metrics-grid-only → owed+satisfied. 9 adoption tests OK; blast radius 18.

## Iteration 6 — telemetry never silently dropped (Codex S10)
If _adoption_event raised, adoption=None → no adoption event committed (silent under-count). Fix: _adoption_event is now SELF-DEFENSIVE (never raises; on compute error returns the payload with null fields + an `error` marker), and publish keeps a last-resort backstop that still emits a minimal error record — so EVERY publish commits an adoption event in the atomic batch, never blocking the page. Regression: forcing render.diagram_available to raise → publish still emits an adoption event carrying the error. 10 adoption tests OK; blast radius 18.

## Iteration 7 — eventlog boundary + no partial booleans (Codex S10, 2 findings)
- **[high] eventlog escape hatch**: publish_artefato_atomic now ALWAYS appends an artefato.adoption event
  in the batch — synthesizing a minimal `error:"no-adoption-supplied"` record when a caller passes none.
  So no path through the eventlog publish boundary (publisher, legacy publish_artefato wrapper, direct
  call) can commit a published artefato with zero adoption telemetry. The atomic batch is now THREE events
  (published + kernel + adoption); the 3 eventlog tests asserting the old 2-event shape updated to the R6
  invariant (incl. concurrent seqs 2n→3n). `_append_orphan_published_for_test` (test-only C3-debt) is the
  only intentional non-atomic path.
- **[medium] partial booleans**: `_adoption_event` now computes into LOCALS and commits to the payload
  only after EVERY probe succeeds — an errored record exposes NULL owed/satisfied/capability_state + the
  error marker, never half-computed countable booleans.
- Regressions: errored telemetry exposes null fields (no partial values); the eventlog boundary
  (legacy publish_artefato) emits a synthesized adoption event. test_publisher 71 OK, test_eventlog 90 OK;
  blast radius 18.

## Iteration 8 — boundary normalization + null-on-error (Codex S10, 2 findings)
- **[high] malformed payload accepted**: a partial/non-dict adoption dict ({} or {"owed":True}) passed
  through as-is. Fix: `eventlog._normalized_adoption` accepts a caller's dict ONLY when it carries every
  countable field (_ADOPTION_FIELDS); otherwise replaces it with an error-marked record (error
  "malformed-adoption" / "no-adoption-supplied") with all countable fields null. publish_artefato_atomic
  always normalizes → the boundary never commits unusable/false telemetry.
- **[medium] default-False on error**: errored/synthesized records defaulted degraded/shortfall to False
  (false-countable). Fix: ALL countable fields (owed/satisfied/degraded/shortfall/capability_state) are
  now NULL on any error/synthesized record (uncountable), real values only on full success.
- Regressions: malformed adoption dict → error-marked, all-null; forced telemetry failure → all countable
  fields null. test_publisher 72 OK, test_eventlog OK; blast radius 18.

## Iteration 9 — strict countable validation (Codex S10)
_normalized_adoption now accepts a caller dict as COUNTABLE only when error is falsy AND every countable field is a real bool; a record with a truthy error (message preserved), a missing/non-bool field, a non-dict, or None → error-marked, all countable fields null. So a full-shaped-but-errored payload (booleans + error) is normalized to all-null, never counted. Regression: errored countable payload → all-null + preserved message. 13 adoption tests OK; test_eventlog OK; blast radius 18.

## Iteration 10 — flag-type validation + producer anti-misattribution (Codex S10)
- _normalize_visual_flags now requires dict degraded/shortfall to be real bools (raises on non-bool like "false" — bool("false") was True), and raises on non-dict/list/None types → _adoption_event records an all-null error instead of false-countable telemetry. None → (False,False).
- _normalized_adoption now OVERWRITES producer from the boundary skill (was setdefault) → a caller cannot misattribute the producer.
Regressions: non-bool dict flags → all-null error; caller producer="map" with skill="report" → recorded producer="report". 15 adoption tests OK; blast radius 18.

## Iteration 11 — producer validity + list-only flags (Codex S10)
- _normalized_adoption: a countable record now requires a non-empty producer (skill); a full-bool payload with skill=None → all-null malformed-adoption (per-producer telemetry needs a real producer).
- _normalize_visual_flags: derived-flag path is now `list` ONLY (not tuple); a tuple/other type → raises → _adoption_event records all-null error.
Regressions: full-bool payload + skill=None → all-null malformed; tuple flags → all-null error. 17 adoption tests OK; blast radius 18.

## ✅ CODEX SHIP (iter-11, verdict: approve)
No material findings: no path commits countable adoption telemetry when the record is errored/partial/non-bool/producerless/misattributed; every other path is all-null error-marked. S10 COMPLETE — working tree only.
