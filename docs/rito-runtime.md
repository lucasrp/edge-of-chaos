# The rito runtime — the experiment's rite as the genotype's production path

**Contract (operator):** the rite is the WHOLE causal execution, grounding-1 through
publication of the rendered page. We never score the output's appearance as a gate; we prove
EXECUTION. The approved renderer and its output hash are PINNED AS A STAGE of the rite —
pinning the pipeline, not scoring the artifact.

## Module map

| Module | Responsibility (deep, one seam each) |
|---|---|
| `tools/rito.py` | The rite runtime promoted from `drafts/old-edge-double-grounding-repro/run.py`: sequences stages 1–11, writes the sealed manifest (begin/finish/fail receipts with sha256), runs the deterministic gates (treatment scan, acceptance header, draft immutability), renders via the pinned renderer, terminates in publication. Also owns the DETECTOR `verify_rito` and its CLI. |
| `tools/render.py` | Gains `render_markdown_page(md, title)` + `RENDERER_ID = "exp072-neutral-markdown/v1"` — the approved renderer promoted verbatim from `generate_post_gate_grounding_arm.render_markdown`. |
| `tools/publisher.py` | Gains `publish_rito(slug, run_dir, *, intent, …)` — the rite's way out: recomputes the pinned render from the sealed markdown, REFUSES a hash mismatch, commits the atomic `artefato.published` event (spec format `edge-markdown/v1`, log is truth), writes the EXACT recomputed bytes temp+rename. `_render_page` gains the `edge-markdown/v1` branch so reprojection re-derives byte-identical pages. |

## The stages (canonical order, promoted from run.py)

1. `grounding1_dossier` (producer callable) → 2. `first_authorial_draft` (chat) →
3. `gap_critique` (review) → 4. `grounding2_targeted` (review) → 5. `provisional_rewrite`
(chat) → 6. `fact_audit` (review) → 7. `author_correction` (chat) → 8. `treatment_cleanup`
(chat, or deterministic copy when the scan is clean) → 9. `final_html` (runtime render, pinned)
→ 10. `final_review` (review, fail-closed ACCEPTANCE header) → 11. `publication` (publisher
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
