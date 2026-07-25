# Plan — sliced execution of the richness/relevance fixes

From `docs/audit-richness.md` (D-A…D-F). TDD per CLAUDE.md §5. Work in the isolated worktree
(`/home/vboxuser/edge-richness`, branch `feat/conductor-richness`); real reports run **on ed**;
evidence = **recent edge work**; commit at the end. Each slice below is its own `/goal` in Goal 3,
gated by `/codex:review` looped until cosmetic, with — for output-affecting slices — a **real report
run + full-page screenshot I read and inject into the review focus** (codex can't see images).

Ordering principle: cheap+isolated first (clean diffs, fast gates), trustworthy gates before the deep
reconciliation, the visual post-pass last (it needs a good base report).

---

## Slice 0 — the real-report harness (prerequisite, on ed)
A reusable dispatch I run after each slice to SEE progress.
- `drafts/dispatch_recent_edge.py`: gather **recent edge work** as evidence (git log across branches +
  `state/direction.md` + recent `blog/entries/` + recent commits/ADRs), build an objective about the
  edge's current development, `excavate → run_conductor → publisher._render_page` → write HTML.
- Verify ed can run it: `agent.yaml` router + `secrets` + `_llm.make_client` present on ed (if not,
  fall back to the same model client roberto used). Confirm a baseline run renders before slicing.
- Screenshot: `google-chrome-stable --headless --print-to-pdf` → I read the PDF (full report) each round.
- **Not a code change** — infra for verification. No gate; it's the measuring instrument.

## Slice 1 — D-C: language-agnostic by STRUCTURE, not strings (REVISED by ed-research)
**Superseded approach (do NOT do):** my first cut hardcoded a `_LABELS` EN/PT map + a `_lang` detector
+ PT keyword markers in `close`. ed-research (G1 verified in code; G2 literature) shows that's the
anti-pattern: language detectors are unreliable on short text and per-language keyword lists never scale.
**Right design — "structure not strings":** the gate already satisfies moves by TYPED ARTIFACT, so make
the conductor lean on that and let the LLM write all human text in-language.
- **Verified ground truth (G1):** `close._check_rich_rite` satisfies *derivation* by a `derivation`
  BLOCK, *what-i-dont-know* by a `gap-table`/`gap-marker`/`gap-resolution` BLOCK, *external-frame* by
  `cites`/`bibliography` METADATA, *lineage* by `distills` METADATA — all language-agnostic. **Section
  titles are NEVER scanned.** So a conductor whose closing moves are BLOCKS + metadata needs ZERO
  keyword markers.
- **Do:** (a) emit the boundary as a **`gap-table` block** (not an English callout) — folds into Slice 3's
  gap consolidation; the derivation stays a `derivation` block; ensure `distills`/`cites` are set
  (already are in the envelope). (b) Scaffold/section titles are **content-derived or written in-language
  by the cognition** — never a code label map; sections are FREE (ADR-0012/0013), so an unlabeled or
  content-derived title is fine. (c) **REVERT** the `_LABELS` map, the `_lang` detector, and the
  `close.*_MARKERS` PT additions from my first cut.
- **TDD:** `tests/test_conductor_lang.py` — a PT report's spec contains **zero hardcoded English scaffold
  literals** AND **zero hardcoded Portuguese label literals from a code map** (assert no `_LABELS`-style
  constants drive titles); the rich-rite gate passes on the PT report **via block-type satisfaction with
  the marker lists emptied/ignored** (prove the moves clear with NO language markers present). An EN
  report is unaffected.
- **Gate:** `/codex:review` + a real PT report screenshot (titles in-language, gate green). Until cosmetic.

## Slice 2 — D-D + D-F: quantitative metrics gate + chart sizing (cheap, code+test)
- **D-D (`tools/blocks.py`, ITEM-LEVEL — block-level isn't enough):** today `metrics_grid_substantive`
  is a block boolean and render emits EVERY item, so a MIXED grid (1 real + 3 filler) leaks the filler.
  Fix at the item level: `normalize_block` for `metrics-grid` **filters `items`/`metrics`** to those
  whose `value` is **quantitative** (digit-bearing / quantified token: `42%`, `3x`, `30ms`), returns the
  block carrying only those items, and **drops the block if none remain**. **Tests:** (a) MIXED grid →
  filler items removed, real ones kept; (b) all-filler → block dropped; (c) all-quantitative → unchanged.
- **D-F (`tools/visual_recipes.py`):** default **landscape** `width`/`height` (e.g. 480×300) for
  `chart_bar`/line/scatter/slopegraph; `sparkline` keeps 120×30; dag/force untouched. **CAVEAT:**
  `_apply_facet` wraps a chart into a faceted spec that DROPS top-level width/height — so the sizing must
  be placed where facet preserves it (the inner view spec, or re-applied to the faceted wrapper).
  **Tests:** every chart recipe (line/bar/scatter/slopegraph) **AND a faceted variant** has explicit
  `width ≥ height`.
- **Grid layout:** ensure the metrics-grid CSS lays out N items with no lonely orphan (responsive, not
  3-fixed) — `tools/assets/base.css` if needed.
- **Gate:** `/codex:review` + a real report screenshot (no filler metric cards; if a chart appears it's
  landscape). Until cosmetic.

## Slice 3 — D-A + D-B: kill monotony at the SOURCE (plan-then-write), reconcile after (REVISED by ed-research)
**Root cause named by the literature (G5):** the monotony is **diversity-collapse under one fixed format
instruction** — every node gets the SAME type→format palette, so the format becomes the attractor — plus
**independent/parallel** fills that can't consolidate. So the primary fix is at the SOURCE (the outline/
fill), not only a post-hoc pass.
- **3a — content-driven per-node FORM CONTRACT (the source fix, plan-then-write):** `author_outline`
  stamps each deliver node with an explicit **`target_form`** (an allowed-block set) **derived
  deterministically from that finding's seed fields** — e.g. a numeric-dense `claim` → `metrics-grid`
  (NOT `chart` — see the visual invariant); a comparison/`contradiction` probe or "vs / before / after"
  claim → `comparison-table`/`diff-block`; a reasoning/`lineage` probe → `derivation`; a residual/boundary
  → `gap-table`; else prose. **EVERY block-bearing node gets a `target_form`, not just deliver nodes:**
  motivate / change-the-course / the synthetic + boundary scaffold default to **prose-only** (or an
  explicit set) — none include `chart`/`diagram`. **GLOBAL VISUAL INVARIANT:** `chart`/`diagram` are
  **never** in ANY node's `target_form`; the form gate (which drops any block outside its node's
  `target_form`, applied UNCONDITIONALLY to every block-bearing node) GUARANTEES no ungrounded
  chart/diagram reaches `close` — they exist only via the Slice 4 grounded post-pass.
  `_writer_prompt` then receives **ONLY that node's `target_form` guidance, not the full type→format
  palette** — the uniform instruction is the diversity-collapse attractor (G5). **Prompt guidance is not
  enough — ENFORCE it:** add a deterministic **post-fill form gate** — after `fill_node`/normalization and
  BEFORE reconciliation, every non-prose block whose `type` is OUTSIDE the node's `target_form` is
  **dropped** (prose is always allowed), so an LLM that ignores the guidance cannot smuggle a
  collapsed/unauthorized block through to `conciliate`. **Tests:** (i) nodes from differing findings carry
  **distinct `target_form`s** (the contract, tested PRE-generation); (ii) the **form gate** ACCEPTS an
  in-`target_form` block and DROPS a disallowed one — tested on REAL emitted blocks, post-generation;
  (iii) a **`chart`/`diagram` emitted in ANY node (deliver OR non-deliver) is DROPPED** by the form gate
  before reconciliation, and if one somehow survives, `add_visuals` rejects it (belt-and-braces);
  (iv) the per-section **ordered structural signature, computed AFTER the form gate,** diverges (below).
- **3b — deterministic reconciliation (after fills, before assemble):** a `reconcile(nodes, seed)` step:
  (i) **gap dedup** — collect every `gap-table`/`gap-marker` across nodes, dedup by normalized
  description with a **similarity threshold (~0.9, calibrate)**, emit ONE consolidated `gap-table` BLOCK
  (this also IS the language-agnostic boundary from Slice 1), strip per-node duplicates; (ii) consolidate
  claims repeated across sections. Deterministic — no LLM (multi-turn LLM revision is documented as
  unreliable, G5). **Test:** overlapping gaps → exactly one gap-table, unique rows.
- **3c — testable diversity GATE:** the per-section **structural signature is the ORDERED block-type
  sequence** (order PRESERVED — a set/binary vector would lose the rhythm that's the actual symptom);
  compute **Self-BLEU / Distinct-n** over those sequences (sourced metrics, G5). A test FAILS on the
  current all-identical output and PASSES once 3a varies the forms. (Thresholds calibrated against 2–3
  hand-judged reports — flagged unverified in the research.)
- **Escalation only:** if 3a+3b don't clear the diversity gate, a SCOPED LLM coherence pass over just the
  flagged over-templated sections (schema-validated I/O; trigger = signature-duplication ratio, not a
  screenshot) — never an open-ended "rewrite the report" (G5: that regime introduces errors).
- **Files:** `tools/conductor.py` (`author_outline`/`_writer_prompt` per-node objective; new
  `reconcile(...)` before `conciliate`; the consolidated gap-table replaces `_boundary_block`).
- **Gate:** `/codex:review` + a real report screenshot (visibly varied sections, gaps once). Until cosmetic.

## Slice 4 — D-E: the 2-spot visual post-pass (selector → subagents → splice)
Orchestrated at the **run layer** (I dispatch the agents; a subagent dispatch is a harness tool call the
conductor Python can't make — the #40 seam). **Slice 4 OWNS every `chart`/`diagram` block:** Slice 3a's
form gate guarantees `content` reaches here with NO pre-existing chart/diagram, and `add_visuals` asserts
that invariant before splicing — so every chart/diagram that ships has passed attribution + the quality
gate below. No ungrounded visual can reach `close`.
> **Sharpened by ed-research (G3+G4):** form follows the QUESTION; ground by attribution; verify the
> Vega `role-mark` data groups.
- **Selector agent:** reads the full assembled report + seed/context → targets **2 grounded spots**
  (section + intent). Route **chart** for quantitative magnitude/trend; **graph** (dag/force) ONLY for a
  **small, sparse** relational claim — cap nodes (≈≤12) and prefer tree/layered/DAG (a dense graph is a
  "hairball", a guaranteed loss — Ghoniem/Fekete); if the relation is dense, leave prose. Selection by
  the **data-ink test** (the visual must out-inform the prose it replaces). Ground-or-flag: a 2nd that
  can't be grounded → ship ONE + shortfall flag.
- **Per-spot subagent — GROUND BY ATTRIBUTION (Doc2Chart/ChartCitor pattern), then VERIFY:**
  1. **Extract an explicit intermediate artifact** from the cited spans — a **table** (chart) or an
     **edge-list of (source, relation, target) triples** (graph) — and attach a **provenance map: each
     datum/triple → the exact source span it came from**. **Reject any datum/triple not attributable**
     (this is the concrete anti-fabrication mechanism — hallucination in chart summaries is measured/real,
     so enforce, don't trust). The chart/graph is a pure function of that attributed artifact.
  2. **Verify a SPEC/DATA-level gate, NOT a naive SVG tag count** (Vega axes/legend/title are also
     `<rect>/<path>/<line>`): render to SVG and require a **`role-`tagged DATA-mark group** (role-mark of
     `rect/line/area/symbol/arc/...`, distinct from `role-axis`/`role-legend`/`role-title`) containing
     **≥ N real primitives**, backed by a **non-empty spec datasource**; chart must be **landscape**
     (`width ≥ height`). Graph: **≥2 nodes AND ≥1 valid edge** (`_validate_topology`) + the node cap.
     Iterate until it passes, else drop the spot.
- **Splice helper (`tools/visuals.py`):** `splice_visuals(spec, picks)` inserts verified blocks into
  `spec["sections"][i]["blocks"]`. Pure, tested. **Quality predicates** (`chart_substantive_svg`,
  `graph_topology_ok`) live here too, unit-tested incl. **false-positive cases** (axis-only/empty-data
  chart → fail; 1-node graph → fail; real chart/graph → pass).
- **Production seam — wired to the REAL shipping path, not just a wrapper.** Reality check: `run_conductor`
  has **no live caller**; the actual producers build an `artefato` dict and call `close.run_close(...,
  produce_fn=lambda: artefato, ...)` (`skills/report/SKILL.md`, the shared `skills/_shared/scaffold.md`
  step, `tools/close.py:run_close`). So the post-pass must operate on the assembled **`content` spec
  right before `close.run_close`**, producer-agnostically:
  - **`add_visuals(content, *, evidence, dispatch_fn=None, ...) -> (content, visual_flags)`** (new
    `tools/produce.py`): selector → per-spot subagents (via injected `dispatch_fn`) → `splice_visuals`.
    **`evidence` is REQUIRED — the original source/seed the report was built from (the raw evidence text
    + the seed `findings` with their `citation`s).** Attribution must resolve each datum/triple to a span
    in **`evidence`, NOT in `content`** — else a hallucinated report claim could be laundered into a
    "grounded" visual. A datum/triple with no `evidence` span is **rejected**. Returns the **content spec
    (ALWAYS a dict)** + a **`visual_flags` list** (`[]` on full success; `["shortfall: 1 grounded
    visual"]` when a 2nd couldn't be grounded). `dispatch_fn=None` ⇒ `(content unchanged, [])`.
  - **Wire it at the actual call sites with EXPLICIT unpacking** (content stays a dict —
    `artefato["content"]` is never a tuple): update `skills/report/SKILL.md` (+ shared scaffold) so the
    producer does `content, visual_flags = add_visuals(content, evidence=<source+seed>, dispatch_fn=…)`
    **before** `close.run_close`, sets `artefato["content"]=content`, **surfaces `visual_flags`** (log +
    non-proof-bound run metadata). `close.run_close` re-runs `check_genus` on the dict. The conductor
    wrapper (`produce_report`) + `dispatch_recent_edge.py` pass the conductor's input evidence + seed.
  - **Integration/contract test (BOTH cases, not just a helper unit test):** drive a producer **close
    path** with a fake `dispatch_fn`: (a) **two-visual success** → published `content` is a **dict** with
    2 visual blocks and `visual_flags == []`, and `close.run_close`'s genus pass saw the spliced dict;
    (b) **one-visual shortfall** → published `content` is a dict with 1 visual block and `visual_flags`
    is non-empty (the shortfall is observable in what the producer acted on); (c) `dispatch_fn=None` →
    content unspliced, `visual_flags == []`; (d) **attribution test** — a candidate datum present in the
    report `content` but ABSENT from `evidence` is **rejected** (no fabrication-laundering). This closes
    the seam blocker, the provenance hole, AND makes the degraded-but-valid case testable end-to-end.
- **Verification (the vision-gate):** I run the real report via `produce_report`, screenshot the full
  page, confirm the ≤2 visuals are relevant + render clean, and inject that read into `/codex:review`
  focus (codex reviews the splice/seam/predicate code; I review the rendered visuals).
- **TDD (deterministic parts):** `splice_visuals` inserts correctly; the SVG quality predicates
  (landscape, mark-count, topology) accept good specs and reject empty/portrait/1-node ones. The
  agent behavior is verified at runtime via the screenshot.
- **Gate:** `/codex:review` + screenshot. Until cosmetic.

---

## Ordering & dependency graph
`Slice 0 (harness)` → `1 (titles)` → `2 (metrics+chart)` → `3 (reconciliation)` → `4 (visual post-pass)`.
Run a real report on ed after each slice; the screenshot is the progress check. Slice 4 depends on a
good base from 1–3.

## Risks & mitigations
- **Reconciliation (3) is the deep one** — deterministic-first (gap dedup + block dedup); escalate to a
  single coherence LLM pass only if the screenshot still reads monotone. Don't over-build.
- **Selector/subagent fabrication (4)** — the hard quality gate (cite spans + SVG/topology check) +
  ground-or-flag is the guardrail; a spot that can't pass is dropped, not faked.
- **Global gate changes (Slice 2)** — the quantitative metrics rule and chart sizing affect all
  producers; run full `test_close*`/`test_genus*`/`test_render*`/`test_visual_coverage_substance` as
  regression each slice.
- **ed LLM client** — confirm in Slice 0; fall back to roberto's model client config if ed lacks it.
- **Parallel beat** — isolated worktree + own branch; commit only at the end.

## Success criterion (mirrors the audit)
A real report on recent-edge-work evidence, read from its screenshot: structurally varied; gaps deduped
(appear once); titles in the content language; metrics only where quantitative (code-gated + tested);
2 grounded visuals (chart-or-graph) passing the real quality gate, or 1 + a flagged shortfall; passes
`check_genus`.
