# Audit — what to fix so conductor reports are genuinely good (rich AND relevant)

The v2 conductor artefato (fatores theme) proved the visual-richness fix works on real content, but a
full read of the rendered PDF exposed quality limits. This audit root-causes each against the code
(line-anchors from `tools/conductor.py`, `tools/visual_recipes.py`, `tools/render.py`,
`tools/excavate.py`) and states WHAT must be done. It is the audit, not the plan.

**Operator decisions baked in:** go DEEP (cross-node reconciliation is in-bounds); run real reports
**on ed** (deploy here); evidence = **recent edge work** (not the rendered HTML — that caused the
meta-reference); isolated worktree, commit at the end; visuals via a holistic post-pass — **target 2**,
but every visual must be **grounded** (cites real source spans/relations, distinct intent, passes a real
quality gate): a chart where a genuine series exists, else a graph; if a 2nd cannot be grounded without
fabricating, the post-pass ships ONE and **flags** the shortfall. **Grounding beats count** — there is
no fabricate-to-hit-2; 2 is the expectation for rich content, not a hard requirement (see D-E).

---

## The six defects

### D-A — Structural monotony (every section is the same template)
Every section renders the identical rhythm: paragraph → comparison-table → metrics-grid → derivation →
gap-table. Root cause: nodes are filled **independently** and concatenated **raw**.
- `run_conductor` (`conductor.py:~948`) loops `for node in nodes: fill_node(...)` — each node filled,
  gated, discharged in isolation; no post-fill reconciliation.
- `assemble` (`:~630`) and `conciliate` (`:~791`) concatenate `node["blocks"]` as-is — no merge, no
  structure variation, no seam-smoothing.
- The module docstring (`:11–14`) names the missing layer explicitly: the "coherence /
  enrichment-relocation" and "living-outline split/merge" of **slices 2–3, NOT in slice 1**.

**Must do:** add a cross-node **reconciliation post-pass** (the slice-2 layer) that runs AFTER all nodes
are filled and BEFORE assembly — varies section structure to the content (not a fixed template),
relocates/merges overlapping material, and smooths seams. This is the deep one.

### D-B — Repeated gap-tables (same open questions recur every section)
The same 3–4 gaps reappear as a gap-table in nearly every section. Root cause: each node emits its OWN
gap-table (the `_TYPE_FORMAT_RULE`, `conductor.py:~298`), and nothing dedups across nodes.
`_boundary_block` (`:~729–737`) is a single hardcoded generic callout that never collects or dedups the
per-node gaps.

**Must do:** **collect + dedup gaps across all nodes** into ONE consolidated gap surface (a single
deduplicated gap-table / boundary), and stop each node from independently re-emitting the same gaps.
Part of the D-A reconciliation pass.

### D-C — Hardcoded English titles amid Portuguese content
15+ English literals render regardless of the content/seed language:
- `assemble`: "Why this holds" (`:643`), "Open questions" (`:661`), "What I don't know" (`:662`) + the
  English derivation/boundary text (`:648`, `:658`).
- `conciliate`: "Why this holds" (`:795`), "Open questions" (`:799`), "Synthesis" (`:814`) + English
  text (`:797`, `:817`).
- `_digest_derivation`: "The through-line" (`:725`).
- `_boundary_block`: "What I don't know" + "What remains uncertain…" (`:735–737`).
- `_section_title` fallback map: `{"Why this matters","The finding","What this changes"}` (`:617`).

**Must do:** the appended scaffold sections/blocks must carry titles/text in the **content's language**
(derive from objective/seed language, or parameterize) — zero hardcoded English in produced artefatos.

### D-D — Forced / filler metrics + orphan card
Metrics-grids are emitted mechanically: non-metric labels used as metric cards ("pré-CSS", "célula"),
and a 3-cards-per-row grid leaves a dangling orphan 4th card. Root: the type→format rule reached for a
metrics-grid by shape without a real numeric payload.

**Must do (code-level, not just prompt):** tighten metrics-grid normalization/gating — a metric card
counts only when its `value` is genuinely **quantitative** (digit-bearing / a quantified token like
`42%`, `3x`, `30ms`), not merely any nonblank string. Today `blocks.metrics_grid_substantive` accepts
ANY nonblank `value`+`label` and `render.BLOCK_SCHEMAS["metrics-grid"]` has no required field — so
"pré-CSS"/"célula" survive as "metrics". Add the quantitative-value check + a test that a
non-quantitative card is rejected; otherwise the content uses prose/list. Lay out N items without a
lonely orphan (responsive grid, not 3-fixed). **Prompt calibration alone does NOT fix this.**

### D-E — Visual relevance: the 2-spot visual post-pass (chart-or-graph)
Per-node writers can't see the whole; their visuals (when any) are local. The right design is a
holistic **post-pass** after assembly:
1. **Selector** (one agent) reads the **full assembled report + the seed/context** → targets **2 spots**
   (section + intent). For each spot it decides: **chart** iff a genuine quantitative SERIES exists in
   the material, else **graph** (`diagram` dag/force) over the relational structure of that content
   (concept dependencies, factor hierarchy, argument flow). **HARD CONTRACT (the falsifiable part):**
   every visual must be **grounded** — it cites the source spans/relations it is built from and has a
   **distinct** visual intent (no two visuals re-encoding the same structure); it **never fabricates**
   data or topology to hit the count. 2 is the *target* because a rich artefato genuinely carries that
   much relational structure (operator decision); but if the selector cannot ground a 2nd visual
   without inventing, it emits ONE and **flags the shortfall** (a signal the content was too thin) —
   **grounding always beats count.**
2. **Per-spot subagent** (one per spot) **re-extracts** the exact data (for a chart) or nodes/edges (for
   a graph) from the report text + context — because excavate findings are **narrative strings only**
   (`excavate.py:34–37,77–94`: `claim/citation/bears_on/probe`, no data/series/topology). It builds the
   `chart`/`diagram` block spec and verifies it with a **real quality check, NOT just `*_renderable`**:
   `render.chart_renderable`/`diagram_renderable` (`render.py:544–572`) only prove vl-convert *accepts*
   the spec — they do NOT inspect dimensions, marks, or topology. The verification layer must
   additionally render the SVG/screenshot and assert it is **landscape & non-trivial** (for a chart:
   width ≥ height AND a minimum visible-mark count, not an empty frame) and, for a **graph**, carries
   **real topology** (≥2 nodes AND ≥1 valid source→target edge — a 1-node "graph" is decorative). The
   subagent iterates until the visual passes; a spot that cannot is dropped (point 1's ground-or-flag).
3. **Splice** the 2 verified blocks into the assembled spec at the chosen sections (post-pass over
   `deep_spec["sections"][i]["blocks"]`; orchestrated at the run/skill layer, since a subagent dispatch
   is a harness tool call the conductor's Python cannot make — same seam #40 uses).

**Must do:** build this selector→subagent→splice post-pass; charts data-triggered, graphs as the usual
**grounded** fallback (never a node/edge-less decorative one), target 2 but **ground-or-flag**, every
visual passing the real quality gate (charts landscape + non-trivial marks; graphs ≥2 nodes + ≥1 edge)
before splicing.

### D-F — Chart sizing defect (backstop for D-E)
Only `chart_sparkline` sets width/height (`visual_recipes.py:131–132`); `chart_bar`/line/scatter/
slopegraph set none → Vega-Lite auto-layout produces tall/narrow portraits (the 288×405 2-bar mess).
DAG self-sizes (`:433–434`) and force is 400×400 (`:574`) — **graphs already render well**.

**Must do:** set sensible default `width`/`height` for the chart recipes (in `_vl_base` or per-recipe,
overridable) so a chart, when the post-pass emits one, renders landscape/readable.

---

## Out of scope (named)
- New block TYPES (the palette suffices).
- The full LLM review stack of slices 2–3 (feynman-per-node / whole-doc adversarial) beyond the
  reconciliation needed for D-A/D-B.
- Changing EDGE_CONDUCTOR's dark-by-default / passthrough behavior.

## Execution constraints (for Goal 3)
- Real reports run **on ed** ("deploy here"); evidence = **recent edge work** (gathered from the edge's
  own recent activity — git/state/recent artefatos/delta), NOT a rendered artefato (kills the
  meta-reference).
- Each slice gated by `/codex:review`, looped until only-cosmetic. **Codex cannot view images**, so the
  screenshot review is a vision-gate: I render the real report, view the **full-page** screenshot, write
  the visual assessment, and **inject it into the `/codex:review` focus** each iteration (code review +
  my visual read together).
- Isolated worktree on ed; commit at the end.

## Success criterion (what the downstream goals must achieve)
A re-run on recent-edge-work evidence yields a report that, verified by viewing the rendered screenshot:
1. is **structurally varied** — sections do not all follow one template;
2. has **deduped gaps** — no gap-table repeated across sections;
3. has **all titles/text in the content language** — zero hardcoded English literals;
4. emits a **metrics-grid only where the values are genuinely quantitative** (digit-bearing), laid out
   with no orphan card — **code-gated**, with a test that a non-quantitative card is rejected;
5. carries **2 grounded visuals (the target in rich content)** — a chart where a genuine series exists,
   else a graph — each citing its source spans, distinct in intent, and passing the real quality check
   (charts landscape + non-trivial marks; graphs ≥2 nodes + ≥1 edge); a 2nd is emitted only if
   groundable without fabrication, else ONE ships and the shortfall is flagged;
6. **passes `check_genus`** (no violations).
