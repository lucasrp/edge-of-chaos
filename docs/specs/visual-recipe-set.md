# Spec — The Visual Recipe Set (the edge's closed Vega vocabulary)

**Status:** draft (spec-before-code). Backs the `chart` and `diagram` blocks of the shared rich producer
protocol (`docs/plans/shared-rich-producer-protocol.md`). Corrects the chart-vocabulary research's
diagram pick (graphviz/`dot`, which broke the no-root install property) by unifying the whole visual
family on **`vl-convert`** — one pure-pip wheel, no system binary, no root, no container.

## Principle

The writer **never emits Vega.** The edge owns a small, closed set of vetted **recipes** (Vega/Vega-Lite
spec templates). A block's payload is the edge's **own tiny schema** — data + light config. `render.py`
expands that into the chosen recipe, `vl-convert` renders it to SVG, the existing sanitizer inlines it.
Vega is an implementation detail *behind* the block, invisible to the writer and to the stored spec —
exactly the closed-vocabulary discipline of the 25-block palette and the protocol's predicate set.

**Store the schema, never the SVG.** The block persists the edge schema (data + config). The same payload
renders static now (`vl-convert`) and drillable later (`vega-embed`) — the edge owns the upgrade.

## The two block types

| Block | Backend | Discriminator | Why this backend |
|---|---|---|---|
| `chart` | Vega-Lite | `chart:` (recipe) | terser grammar; the data-chart family |
| `diagram` | full Vega | `layout:` (recipe) | only Vega exposes graph-layout transforms |

Both are **capability-gated** on `vl-convert` (a pip wheel, so present by default; the gate is defense —
absent → block disabled, never a placeholder). Both **fail closed** on a malformed payload (a genus
violation, never a crash).

## The recipe catalog (closed — 7 recipes)

### Charts (Vega-Lite)

| Recipe | Content shape it serves | Edge schema (what the writer emits) |
|---|---|---|
| `line` | change over time / a sequence | `{type:"chart", chart:"line", data:[{x, y, series?}], x_label?, y_label?, title?}` |
| `sparkline` | inline trend dataword (brief altitude) | `{type:"chart", chart:"sparkline", data:[y, y, …]}` |
| `bar` | magnitude / ranking across categories | `{type:"chart", chart:"bar", data:[{label, value}], horizontal?, title?}` |
| `scatter` | relationship between two quantities | `{type:"chart", chart:"scatter", data:[{x, y, label?}], x_label?, y_label?}` |
| `slopegraph` | before/after across many items (Tufte) | `{type:"chart", chart:"slopegraph", data:[{item, before, after}], before_label?, after_label?}` |

**`facet` is a modifier, not a recipe** — any chart accepts an optional `facet: "<field>"` that turns it
into Tufte **small multiples** (Vega-Lite `facet`). Composition over a separate recipe.

### Diagrams (the graph-layout family)

| Recipe | Content shape it serves | Edge schema (what the writer emits) |
|---|---|---|
| `dag` | hierarchy **and** dependency graph (step-flow, multi-parent DAG) | `{type:"diagram", layout:"dag", nodes:[{id, label}], edges:[{source, target, label?}], orientation?, title?}` |
| `force` | connection map (cycles, non-directional, fan-out) | `{type:"diagram", layout:"force", nodes:[{id, label}], edges:[{source, target, label?}], title?}` |

The writer emits **topology** (`nodes` + directed `edges`), never coordinates.

- **`dag` is the workhorse** and fixes the pass-1 gap: a single `parent` field can only encode a tree, but
  a plan step can depend on *several* predecessors. So `dag` is **edges-based** and the **layered layout is
  computed in pure Python** (Sugiyama-lite, prototype-validated): longest-path topological rank
  (rank = max(predecessor ranks)+1, roots at 0; cycles broken by dropping back-edges, never a hang), then a
  **deterministic median/barycenter ordering pass** within ranks to reduce crossings (~4 sweeps — pass-2
  flagged that first-appearance ordering crosses even at 4 nodes; the barycenter pass cut the 12-node plan
  from 2 crossings to 1 and is a no-op on trees), then fixed x/y from rank+order. Vega only **draws** —
  `symbol` nodes, `text` labels, `rule` edges with `symbol` arrowheads trimmed to the node radius — **no Vega
  layout transform**. A strict hierarchy is a DAG with single parents, so `dag` subsumes the old `tree`
  recipe. **Readability fixtures** pin small multi-parent DAGs (rank correctness + crossing count) as
  regression tests; crossings are reduced, not provably zero (acceptable and measured for ~5–15 nodes).
- **`force`** uses Vega's `force` transform for genuinely non-directional connection maps.

## The Vega surface — the auditable allowlist (nothing outside this ships)

The whole system uses only these primitives. Anything else is out of vocabulary by construction; this is
what makes the SVG output predictable and the sanitizer reliable.

- **Vega-Lite marks:** `line`, `point`, `bar`, `rule`, `area`.
- **Vega-Lite encodings:** `x`, `y`, `color`, `size`, `detail`, `facet`, `tooltip`.
- **Vega-Lite transforms:** `fold` (slopegraph), `window`/`aggregate`/`bin` (optional, sparkline/summaries).
- **Vega marks (diagrams):** `symbol`, `text`, `path`, `line`, `group`.
- **Vega transforms (diagrams):** `force`, `linkpath` — used **only** by the `force` recipe. The `dag`
  recipe computes its layout in pure Python and uses **no** Vega transform (drawing marks only). `stratify`/
  `tree`/`treelinks` are deliberately NOT in the vocabulary — the executability gap pass-1 flagged is gone.
- **Excluded entirely:** projections/geoshape, arbitrary signals, image marks, external data loaders,
  expression-driven URLs — none appear in any recipe.

## Rendering pipeline

```
writer → edge block schema (data + config)
       → validate against the recipe schema (fail closed on malformed)
       → render.py expands to the recipe's Vega/Vega-Lite template (writer never sees this)
       → vl-convert → SVG  (pure-Python, no root)
       → sanitize (existing allowlist boundary: no script/event/foreignObject/external-href/image)
       → inline as <div class="chart|diagram">…</div>
stored: the EDGE SCHEMA, never the SVG  (→ vega-embed for the reactive dashboard later)
```

## Validation (fail closed — carries the /codex-review lessons)

Each recipe declares its required fields; the normalizer validates the block against its recipe before
rendering. Malformed input (missing data, non-list `data`, non-string labels, empty topology) → a genus
violation with a clear reason, **never** a crash and **never** a chart/diagram that renders blank but
still satisfies a presentation floor. A `chart`/`diagram` block counts toward a producer's richness floor
only if it **actually renders** (the renderable-not-just-present rule already enforced for `diagram`).

## Versioning (replay stability — ADR-0006/0010)

Every `chart`/`diagram` block carries a `v` (schema version, integer) identifying the recipe-template
semantics it was authored against. The guarantee is **semantic**, not byte-level — and that is the correct
scope: per ADR-0006 the page is a *re-rendered projection of the log*, so the SVG is regenerated, never
stored as truth. Byte-identical SVG across `vl-convert`/Vega/font/sanitizer upgrades is an explicit
**non-goal** (chasing it would mean pinning the whole toolchain forever — brittle, and against the
projection model). What IS guaranteed:

- `render.py` keeps the template for each `(recipe, v)` it ships; a payload renders under **its own** `v`,
  never silently reinterpreted by a newer template's *semantics*.
- A recipe change that alters the **meaning** of a payload is a **new** `v` (old `v` template retained); a
  pure visual/toolchain change keeps `v` — the chart still faithfully depicts the same data.
- The validator tightens only for **new** `v`; an old payload that passed at its `v` still passes.
- A lightweight **provenance stamp** (`rendered_with`: vl-convert + recipe versions) is recorded per render
  for diagnosis — provenance, not a byte-identity promise.
- **Test:** a corpus of `v=1` payloads still renders to a **valid, faithful** chart (right marks, right
  data, no error) after a `v=2` recipe **and** after a `vl-convert` upgrade — semantic stability, not bytes.

This also makes the later `vega-embed` reactive upgrade safe: it consumes the same versioned schema.

## Growth policy

The recipe set is closed and grows **deliberately** — a new recipe is a vetted, shared addition (like the
protocol's predicate vocabulary), never an per-artefato escape into raw Vega. The bar to add one: a
content shape the existing seven genuinely cannot carry.

## Non-goals

- No raw-Vega passthrough block (that would reopen the open-grammar surface this spec closes).
- No interactivity in the static render (reactivity is a later, still-vetted layer on the same schema).
- `ascii-diagram` remains only as a dependency-absent safety net, never the intended output.
