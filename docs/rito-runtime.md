# The rito runtime — the experiment's rite as the genotype's production path

**Contract (operator):** the rite is the WHOLE causal execution, grounding-1 through
publication of the rendered page. We never score the output's appearance as a gate; we prove
EXECUTION. The approved renderer and its output hash are PINNED AS A STAGE of the rite —
pinning the pipeline, not scoring the artifact.

## Module map

| Module | Responsibility (deep, one seam each) |
|---|---|
| `tools/rito.py` | The rite runtime promoted from `drafts/old-edge-double-grounding-repro/run.py`: sequences stages 1–11, writes the sealed manifest (begin/finish/fail receipts with sha256), runs the deterministic gates (treatment scan, acceptance header, draft immutability), renders via the pinned renderer, terminates in publication. Also owns the DETECTOR `verify_rito` and its CLI. |
| `tools/render.py` | Gains `render_markdown_page(md, title)` + `RENDERER_ID = "exp072-neutral-markdown/v2"` — the approved renderer promoted verbatim from `generate_post_gate_grounding_arm.render_markdown`. |
| `tools/publisher.py` | Gains `publish_rito(slug, run_dir, *, intent, …)` — the rite's way out: recomputes the pinned render from the sealed markdown, REFUSES a hash mismatch, commits the atomic `artefato.published` event (spec format `edge-markdown/v1`, log is truth), writes the EXACT recomputed bytes temp+rename. `_render_page` gains the `edge-markdown/v1` branch so reprojection re-derives byte-identical pages. |

## The stages (canonical order, promoted from run.py)

1. `grounding1_dossier` (producer callable) → 2. `first_authorial_draft` (chat) →
3. `gap_critique` (review) → 4. `grounding2_targeted` (review) → 5. `provisional_rewrite`
(chat) → 6. `fact_audit` (review) → 7. `author_correction` (chat) →
Feynman content loop (hard contract, two deterministic iterations -- a score does not skip a lastro, a low score does not extra-loop): `feynman_gate_1` (review route / LLM reviewer notes, 8 axes 0-5) -> `feynman_grounding_a` (review, fresh lastro aimed at the briefing) -> `feynman_rewrite_1` (chat) -> `feynman_gate_2` -> `feynman_grounding_b` -> `feynman_rewrite_2` ->
8. `treatment_cleanup`
(chat, or deterministic copy of rewrite 2 when the scan is clean) -> 9. `final_html` (runtime render, pinned)
-> close tooth `feynman_gate.review` (LLM reviewer; FAIL = StageFailure, no publish; not a loop controller) ->
10. `final_review` (review, fail-closed ACCEPTANCE header) → 11. `publication` (publisher
seam). A run that didn't publish didn't finish the rite. Stage 11 of the experiment
(`blind_reading_package`) is experiment apparatus, NOT a production stage — but the runtime
keeps `02_FIRST_AUTHORIAL_DRAFT.md` sealed and addressable in the run dir so a later blind
read is always possible.

## Seams (what is injected, what is owned)

- **Cognition is prose-owned.** The producer skill hands `grounding1_fn()` and per-stage
  `prompts[stage](outputs) -> str`. `rito.py` contains NO prompt content — only the
  deterministic gates (leak-scan regexes, acceptance header contract), which are gates,
  not cognition.
- **Transport is injected.** `complete_fn(route, prompt, max_tokens) -> str`; production
  wires the llm_routes completer, tests fake it. Routes per stage are FIXED in the stage
  table (chat=author, review=independent), promoted from the experiment.
- **Publication is inside the rite.** `publish_fn(markdown, manifest) -> receipt` defaults
  to `publisher.publish_rito`. The receipt (event id + page sha + manifest core hash) is
  sealed as stage 11.

## Binding

`manifest_core_hash` = canonical sha256 over {schema, rito_version, run_id, slug, stage
receipts 1–10}. The published event carries it plus `page_sha256` and `renderer_id`; the
publication receipt in the manifest carries the event id. So manifest ⇄ event ⇄ page bytes
are mutually bound and `verify_rito` can prove the triangle from disk + log alone.

## The detector

`verify_rito(run_dir, log=…, blog_dir=…)` → `{"pass": bool, "failures": [named codes]}`.
Proves: all 11 stages completed in causal order (timestamps monotonic, render BEFORE final
review), sealed receipts match disk bytes, LLM stages carry sealed prompts, recomputed
`render_markdown_page(sealed_08_markdown)` hash == sealed 09 receipt == published page bytes,
publication event present and bound, first draft addressable, acceptance PASS. It never
reads artifact QUALITY — execution only; the form check is a pipeline-identity hash, not a
score. CLI: `tools/edge-python tools/rito.py verify <run_dir> [--log …] [--blog-dir …]`.

Scope (codex gate 2): `verify_rito` is a CONSISTENCY verifier over the operator's own run
dir + event log — it proves the recorded execution is coherent and form-pinned, not that an
attacker who can write both could not fabricate it. File receipts are not tamper-proof
provenance; authority comes from running a REAL canary, never a fabricated fixture.

## Post-publish side-effects

A rito-published artefato must be a **first-class citizen of the graph/corpus** — the same as a
legacy-published one — so genus-wide adoption doesn't strand rito artefatos out of recall and the
graph. Both `publish` and `publish_rito` run the SAME post-commit sequence, extracted into one
shared private seam `publisher._post_publish_sideeffects` (called after the commit + page write):

1. **source-signal emission** (`_signal_cites`, ADR-0009) — one `source.signal` per cited snippet,
   scored `cosine(embed(snippet), embed(body))` when an `embed_fn` is injected (else 0.0). `body`
   is the text snippets are scored against: the rendered HTML for legacy, the **markdown body** for
   rito. Wrapped in a bare `try/except: pass`.
2. **graph projection** (`project_artefato`, #30) — the spine write (Artefato node + content
   embedding + SERVES/DISTILLS/PROPOSES/CITES/lineage edges). Default-resolved at call time; an
   explicit `project_fn=None` skips it; **default-skips a non-canonical log** (a test/dry-run must
   never write the install graph). Wrapped best-effort (`print` on failure).

**Failure semantics (identical to legacy):** the commit is the truth point (ADR-0006/0011); every
side-effect is BEST-EFFORT and NEVER aborts the publish — the page + atomic event already landed,
and the next beat re-emits/reprojects from the log. Neo4j unreachable in tests degrades inside
`project_artefato` (prints, never raises).

**Seam / coupling fixed:** `project_artefato` reads spec content only through `_spec_text(spec)`
(the embed + MENTIONS input). `_spec_text` was coupled to the legacy `sections`/`executive_summary`
tree and returned `''` for `edge-markdown/v1` — an **empty graph node**, unrecallable. Fixed by
adding a markdown branch to `_spec_text` (one place, feeds both embed and mentions) rather than
wrapping the markdown in a fake sections tree. Everything else in `project_artefato` is spec-shape
agnostic. `gate` is None for the rito path (no run_close verdict yet — see the OPEN decision below).

## What stays prose / open decisions

- Prompt bodies (the experiment's exact wording) live in the producer skills; `run.py`
  remains the archived reference.
- Author-thread continuity + environment sealing (codex CODEX_HOME/resume, route drift)
  were experiment reproducibility apparatus; the runtime records route + prompt/output
  receipts per stage and leaves continuity to the producer's `complete_fn` wiring.
  OPEN: promote continuity enforcement into the runtime?
- RESOLVED (operator, 2026-07-10, verbatim "basta"): the rite's own `final_review` (stage 10)
  REPLACES `close.run_close`'s double-blind reviewer gate on the rito path. Rationale: the
  blind-winning B was produced with only the rite's internal review; an extra stochastic gate
  is not the experiment ("o rito é tudo"). Anti-forgery is covered by the rito's own seal
  (per-stage sha256 receipts + `publish_rito`'s hash-refuse), not by reviewer proofs.
  Consequences: `publish_rito` takes NO run_close proof by design (pinned by
  `RitoFinalReviewReplacesDoubleBlind` in tests/test_rito_runtime.py); the projected `gate`
  stays None for rito artefatos — the gate badge is a legacy-close concept. Wake (ADR-0016)
  and intent-kernel (C3) gates are preserved. Legacy producers keep run_close until they
  migrate to the rito.

## Producer adoption (the pattern)

The report skill is the exemplar: build `grounding1_fn` + `prompts` from the skill's prose,
call `rito.run_rito(slug, run_dir=state/rito/<slug>, …, intent=…, dispatch_id=…)`. Other
producers adopt by supplying their own cognitive inputs — same runtime, same stages, same
detector ("o edge deve soar o mesmo across artefatos").

**Rolled out (genus-wide, 2026-07-10).** Every TEXT producer now exits through the rite. Only
the cognitive inputs vary; the stages, detector, and publication seam are identical:

| Producer | Artefato | Status | Cognitive inputs (what varies) |
|---|---|---|---|
| `report` | prose synthesis | rito (exemplar) | synthesis draft, calibrated contextualization |
| `research` | directed deep-dive | rito | derive-first Feynman dossier; derivation/gap-table carriers |
| `map` | connections diagram | rito | connections dossier; fenced mermaid/ASCII diagram + connection table (Markdown-native) |
| `plan` | next-steps flow | rito | situation/constraints dossier; fenced flow + ordered list/risk table |
| `discovery` | serendipity find | rito | the find + anchoring evidence; before/after + callout |
| `report-deep` / `research-deep` / `discovery-deep` | (alias) | rito (inherited) | same genus path as the base skill — not a different depth |
| `mentor` | insight artefato leg | rito | insight explanation; **only** the artefato-publication leg — the three-steers `grill_gate` close is untouched |
| `experiment` | (closes via `/report`) | rito (inherited) | an experiment finalizes by publishing a report, so it rides report's rite |
| `critique` | appraisal | inherits shared close | short skill; references "the close" only, carries no explicit exit snippet — moves when it grows one |

The `-deep` aliases and `experiment` are NOT wired individually: they delegate to a base
producer that is already on the rite, so wiring the base covers them.

## Interactive producers — the renderer conflict (RESOLVED: option (a), leave legacy)

**Operator decision, 2026-07-10, verbatim "deixa legado":** `prototype`/`lazer` stay on the legacy
close path (option (a) below). Rationale (ed): the rite was won by an experiment about dense GROUNDED
PROSE; forcing an interactive single-file artefato through the pinned Markdown renderer before an
experiment proves the rite improves a JS artefato would be changing the rite by conformance, not by
evidence — the exact move rejected twice. Interactive craft has its own canon; when there is appetite,
"does the 10-stage rite improve a single-file interactive?" becomes its own numbered experiment, and
its result decides between options (b) and (c). Until then, the two-path split is a DECLARED exception,
honest, not a drift. The analysis below is kept as the decision's grounding.



`prototype` (and `lazer`) produce an **interactive single-file HTML+JS page** whose artefato IS
the running page — the interaction carries the insight. These do **not** fit the rite as pinned,
and are deliberately left on the legacy close path. The conflict is precise:

1. **Stage 9 (`final_html`) is pinned to the neutral-MARKDOWN renderer.** `render.RENDERER_ID`
   (`exp072-neutral-markdown/v2`) renders a Markdown body into a self-contained neutral page;
   `publish_rito` byte-hash-enforces exactly that renderer's output. An interactive page is
   author-written JS+CSS in one file — there is no Markdown body to render, and forcing the JS
   *through* the markdown renderer would either strip the `<script>` (the exact `sanitize_raw_html`
   behavior the legacy prototype seam works AROUND with content-addressed publication) or produce
   bytes the pinned renderer never emits — a guaranteed hash mismatch at `publish_rito`.
2. **The rite's deterministic gates assume prose.** The treatment-scan regexes (the leak scan
   feeding `treatment_cleanup`) and the `ACCEPTANCE:` header contract are written against
   Markdown prose; run against JS source they either false-fire on code tokens or scan meaningless
   text — neither gates the thing that actually matters for an interactive page (does it RUN, does
   the interaction TEACH — a human render→ver→revisar gate, not a text scan).
3. **The publication seam differs.** Interactive pages publish content-addressed
   (`blog/entries/<slug>.proto.<sha12>.html`, immutable, `artefato.asset` event) via
   `publisher.publish_prototype_page`; the rite publishes a single canonical
   `blog/entries/<slug>.html` bound to `artefato.published`. These are different addressing and
   event contracts.

**Honest options for a future decision (NOT resolved here):**

- **(a) Leave them legacy** (current state). Two production paths coexist: the rite for prose
  artefatos, the content-addressed single-file seam for interactive ones. Cost: the genus does
  NOT sound the same for interactive artefatos; "prove the rite ran" does not apply to them.
- **(b) A second pinned form in the rite** — a `render.RENDERER_ID`-analog for single-file JS
  (identity-pin the bytes as-authored rather than render Markdown), with a stage-9 branch and a
  gate set fit for interactive content (the render→ver→revisar human gate as a sealed receipt
  instead of the prose leak-scan). This is a real redefinition of the rite for a second artefato
  family — deliberately NOT done here (the mission's law: do not invent a second renderer, do not
  redefine the rite unilaterally).
- **(c) Split the artefato** — publish the interactive page content-addressed (as today) and wrap
  it in a rito-published Markdown COMPANION entry that links it. The prototype skill already
  authors such a companion entry; routing only the companion through the rite would put the framing
  on the genus path while the page stays on its own seam. Cost: the page itself is still off-rite;
  the "artefato" the rite proves is the prose wrapper, not the interactive object.

Until the operator decides, `prototype`/`lazer` stay in `LEGACY_PRODUCERS` and keep the enforced
`close.run_close` exit (pinned by the legacy-snippet structure tests).
