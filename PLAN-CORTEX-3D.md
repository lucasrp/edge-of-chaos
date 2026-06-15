# Execution plan — the 3D "navigate the brain" Cortex

Turns `AUDIT-CORTEX-3D.md` (25 codex-approved must-haves) into **sequenced, independently-shippable
slices**. Each slice is a thin vertical (vendor / template / island JS / CSS + test), built via
`/pocock-tdd`, gated in execution by `/codex:review` (looped until increments are cosmetic). Gated
*as a plan* by `/codex:adversarial-review`.

**Operator decision R1 (settled, do not relitigate):** ship the **FULL 3D WebGL bundle**
(`3d-force-graph` UMD = three.js + d3-force-3d + camera + picking, one vendored min file) on `/cortex`,
**accepting its weight** island-only — no lazy-load / capability-gate *for resource saving*. The
`docs/frontend.md` cheap-on-resources line is amended **for the `/cortex` island specifically** (Slice 0),
its other surfaces untouched. **R1 does NOT remove the M21 fallback chain** — that chain
(WebGL→3D→2D Cytoscape→list→message) ships for *reach* (WebGL-incapable clients), a **release gate**
(M-GATE), not a perf optimization. It is baked into the render slice, never trailing.

**The invariant for this whole program (audit §"the change surface"):** the `/cortex` data API
(`cortex_fold`, `_cortex_live`, `_map_node`, `_node_href`), `_json_for_script`, `_cortex_dark` / fail-dark,
`group_id` scoping, and the `POST /cortex/<node_id>/comment` correction path stay **UNCHANGED**. The change
surface is exactly: the vendored 3D lib, `blog/static/cortex.js` (the island), the inspect panel, the new
inspect-panel + connects-to-pill Jinja macros in `components/ui.html`, `templates/pages/cortex.html`, and
the Cortex CSS in `style.css`. **No slice touches a server fold or the Cypher.** If any slice below appears
to need a `cortex_fold`/`_map_node` change, that is a STOP-and-flag — it is out of this front-end envelope.

**Test gate (EVERY slice):** `tools/edge-python tests/test_cortex.py` **and**
`tools/edge-python tests/test_cortex_correct.py` **and** `tools/edge-python tests/test_frontend_contract.py`
— keep all three green; add the affected surface's tests per slice. The pure island logic (`CortexFilters`
+ the new neighbor-index / traversal-order / webgl-probe helpers) is exported for **Node** and tested
headless, exactly as Slice 6 factored `search`/`visible`/`render`/`locate` (see
`test_cortex.py::CortexFilters*`). Slice 2 (the 3D render slice) runs the full dashboard suite.

**Browser gate (a RECURRING regression gate from Slice 2 onward — the M-GATE is browser behavior, not a
Flask response check).** The Python suites are Flask response assertions + headless Node `CortexFilters`
tests; they can pass with a **blank 3D canvas or a broken fallback rung** because WebGL render, camera
controls, the Cytoscape fallback, and the list fallback are **browser-only**. So a **Playwright/headless-
Chromium gate** (added in Slice 2) asserts (a) stub `webglSupported()`→true → a **non-blank** 3D canvas +
working orbit/zoom + space-0 centered; (b) stub WebGL→false → the **2D Cytoscape island** renders (non-blank,
navigable); (c) force Cytoscape render to fail → the **searchable list** DOM renders; (d) force the list to
fail → the **honest message**; (e) the 3D + cytoscape `<script>`s load **only** on `/cortex`. A 3D/fallback
rung that only "passes" a Flask 200 does **not** satisfy the M-GATE. **Because Slices 3–6 keep mutating the
SAME browser-only surface** (`cortex.js`, `cortex.html`, `style.css`, the renderer) — node selection, the
panel, camera fly-to, `?node=`, search, PREV/NEXT, the perf cap — **any slice from Slice 2 onward that
touches a renderer file MUST re-run the full fallback-ladder browser gate as a regression check** (the
recurring Flask+Node gate alone cannot catch a regressed canvas or a dead rung). A later slice that breaks a
WebGL-blocked client's fallback after the one-time gate passed is exactly the regression this recurring gate
prevents. (The operator captured the reference live via Playwright; the same harness proves our rungs render.
Run it backgrounded against a backgrounded server, never `blog/server.py` in the foreground — per the
anti-stall rule; `pkill` after.)

**Work only in `/home/vboxuser/edge-dashboard-wt`** (branch `feat/dashboard-blog-feedback`;
parallel-git hazard on `~/edge` — never touch it). **CONTRACT C1:** never commit `state/` mutations (the
`/ed-wake` predispatch stamps `dispatch.open`; reset the dirtied log before any commit — the committed
baseline carries zero `voz.*`). Commit per slice.

## Cross-cutting requirements (EVERY slice + EVERY gate)
1. **Gate against the documented decisions.** Every `/codex:review` (execution) and
   `/codex:adversarial-review` (design) runs with **all `docs/adr/*.md` + `CONTEXT.md` + `CONTRACT.md` +
   `SURFACE.md` + the canonical `docs/frontend.md`** in scope — flag any violation of a documented
   decision, glossary term, or contract (C1 read-only-on-the-world, ADR-0010 navigable-Cortex, ADR-0005/0006
   projections, the fail-dark + `group_id`-scoping surface decisions, the Slice-7 #37 no-CDN / Jinja /
   `/ux-catalog` contract). The work conforms to the docs, or the doc is updated first (with its own review —
   that is Slice 0).
2. **One design system — the Slice-7 #37 vocabulary, maintained.** Flask+Jinja scaffold
   (`blog/templates/base.html` + `partials/` + `components/ui.html` macros + `pages/cortex.html`),
   Tabler under the dark-token bridge, the `style.css` `:root` tokens as the palette source of truth, the
   self-hosted vendored JS, and `/ux-catalog` registration for every NEW component (the inspect panel, the
   CONNECTS-TO pill). **No one-off parallel styling system.** A new component *extends* the shared set and is
   registered on the catalog (`test_frontend_contract.py::test_ux_catalog_route_lists_tokens_and_macros`
   pins this).
3. **Security seams survive the lib swap (audit R5/M17/G5).** The 3D island consumes the SAME
   `_json_for_script` data block; the inspect panel is built with **DOM APIs + `esc()`** (the breakout
   defense), never `innerHTML`-from-payload; the source link stays `appendLink`'s internal-path-only guard;
   the correction composer stays the same-origin POST through the Slice-1 gate with the stable-then-advance
   nonce. **The 3D lib must never get a payload-derived `label` rendered as raw HTML** (3d-force-graph's
   `nodeLabel` accepts an HTML string → use a text-only accessor or a sprite/canvas label, not raw graph
   content). Codex checks this on every gate.

## Sequencing rationale
Dependencies first, tree green at each step: **doc-conformance gate** (Slice 0 — Phase-2 prerequisite per
audit Priority-0; the canonical docs must stop contradicting the shipped code before 3D builds on them) →
**vendor + capability seam** (Slice 1 — the lib on disk + the WebGL probe, no behavior change yet) → **the 3D
render WITH the M21 fallback chain in the same increment** (Slice 2, the M-GATE: no 3D ships without the
WebGL→3D→2D→list→message hierarchy) → **the enriched slide-in inspect panel** (Slice 3, the *additive*
surface) → **CONNECTS-TO neighbor traversal + `?node=` round-trip** (Slice 4, the navigation loop) →
**search-fly-to + PREV/NEXT** (Slice 5, reusing shipped pure logic) → **performance hardening to the measured
acceptance bound** (Slice 6, the last gate before the experience is "done"). Each slice leaves
`/cortex` working: Slice 1 still renders the 2D island; from Slice 2 on it renders 3D-or-fallback; panels and
traversal are additive on top of a navigable cloud.

---

## Slice 0 — Doc-conformance gate: bring the canonical docs to shipped reality + the 3D direction *(audit Priority-0 / G6 / M12 — PREREQUISITE, do FIRST)*
The canonical front-end doc and SURFACE.md still call Cortex **"read-only"** though node-targeted Voz
(Slice 6b), search + filter (Slice 6) shipped — Phase 2 cannot conform to "docs/adr + CONTEXT + CONTRACT +
SURFACE + the canonical front-end doc" while two of those contradict the code. **No 3D code in this slice** —
docs only, with its own review.
- **Build:**
  - `SURFACE.md` Cortex section (lines ~232–257, 296–322): retire the "read-only for the mentee" framing and
    the "search/filter = *future*" + "node-targeted Voz = *open bridge* / *explicit future*" framings.
    Document as **the current, gated Cortex contract**: find-and-jump **search** + **type/Earmarked/recency
    filter** (Slice 6, deterministic, NOT semantic retrieval — keep the banned-fetch posture explicit), and
    the **Earmarked node-targeted Voz correction** (Slice 6b: `POST /cortex/<node_id>/comment`, fail-closed
    node-ref validation, idempotent nonce, same-origin through the Slice-1 auth/CSRF gate, the
    `origin_comment_id` + node-`target_ref` provenance). Keep "the mentee never *edits the graph*" true (the
    write surface is still the Voz rail — the correction is a Voz comment, not a graph mutation), but stop
    calling the surface read-only. Add the **3D direction** as the stated v-next: a dark, luminous,
    trust-weighted 3D force-directed cloud replacing the 2D island, with the 2D Cytoscape island retained as
    the **required WebGL fallback** (not deleted).
  - `docs/frontend.md`: line ~96 (`Cortex (/cortex): a island do grafo (read-only surf da brain)`) → reflect
    the shipped search/filter + node-targeted Voz correction (a *gated write affordance*, not read-only).
    `§Hard constraint — cheap on resources` → record the **R1 amendment as a settled DIRECTION** (the
    v-next): the full 3D/WebGL bundle is accepted **on the `/cortex` island specifically** (the heavy lib
    never touches the read-mostly shell, M19); the constraint stands for every other surface. Frame the 3D
    cloud (replacing the 2D island, with the 2D Cytoscape island retained as the **WebGL fallback**) and the
    **M21 fallback chain** (WebGL→3D→2D Cytoscape→searchable list→honest message, distinct from fail-dark M16
    which is for *absent graph data*, not an unsupported renderer) as the **planned next direction**.
  - **DO NOT** add the vendored `3d-force-graph` to `§Supply chain` in this slice — that section lists the
    **assets actually on disk + served**, and the bundle is not vendored until Slice 1. Asserting it here
    would make the doc claim an asset (and an implied `/static/vendor/3d-force-graph.min.js` route) that does
    not yet exist — a doc-vs-code contradiction that breaks green-at-each-step and defeats this slice's whole
    purpose. The `§Supply chain` pinned-vendor entry is added **in Slice 1, with the file** (the doc and the
    asset land together).
- **Accept:** `grep -i "read-only"` over the Cortex section of both docs returns no framing that contradicts
  the shipped composer; both docs name node-targeted Voz + search/filter as current gated affordances; the
  R1 weight amendment is recorded as the scoped (`/cortex`-only) **direction**, and the 3D/M21 chain as the
  planned next; **`docs/frontend.md §Supply chain` still lists only the on-disk assets** (htmx, cytoscape,
  tabler — no `3d-force-graph` yet, since it is not vendored until Slice 1); the doc-conformance codex round
  on Slice 0 reports no remaining doc-vs-code contradiction in either direction.
- **Codex gate:** `/codex:adversarial-review` of the two doc diffs (its own review, per the audit) — conform
  to ADR-0010 (navigable Cortex), the Voz lifecycle (ADR-0017), CONTRACT C1, the no-fabrication posture.
- **Deps:** none. **Files:** `SURFACE.md`, `docs/frontend.md`.

## Slice 1 — Vendor `3d-force-graph` + the WebGL capability seam (no behavior change yet) *(audit M18 / G4; prereq for M-GATE)*
Put the lib on disk, pinned and self-hosted; add the WebGL-detection function the M-GATE branches on — but
do **not** wire 3D rendering yet, so the tree stays green rendering the existing 2D island.
- **Build:**
  - Vendor `3d-force-graph` (the UMD min bundle bundling three.js + d3-force-3d) into
    `blog/static/vendor/3d-force-graph.min.js`, **pinned** (record exact version + bundle size in the file
    header comment), served locally. **No `<script src="https://…">`** anywhere (M18 / Slice-7 #37). Extend
    `test_frontend_contract.py::test_vendor_files_on_disk` to assert the file exists and is served at
    `/static/vendor/3d-force-graph.min.js` with 200.
  - **Add the `§Supply chain` pinned-vendor entry to `docs/frontend.md` IN THIS SLICE, with the file** (the
    doc lists the asset now that it is on disk + served — the doc and the asset land together, closing the
    contradiction Slice 0 deliberately avoided): `vendor/3d-force-graph.min.js — <pinned version>` (island-
    only on `/cortex`), alongside the existing htmx / cytoscape / tabler entries.
  - Add a pure, exported `webglSupported()` to `cortex.js` (alongside `CortexFilters`) — a try/catch that
    asks for a `webgl`/`experimental-webgl` context on a throwaway `<canvas>` and returns a boolean; in Node
    (no `document`) it is callable but the DOM island guard still gates real use. Test it headless with a
    stubbed canvas factory (the same Node-export pattern as `CortexFilters`).
- **Accept:** the vendored bundle is on disk + served (200, correct content-type); the file header pins the
  version + KB; `webglSupported()` returns a boolean and is exported for Node; **no CDN `<script src>`** in
  any rendered page (`test_frontend_contract` grep); `/cortex` still renders the existing 2D island
  unchanged (Slice-1 introduces the asset + the probe, **not** the swap — the tree is green and shippable).
- **Codex gate:** `/codex:review` — supply-chain (no CDN, pinned), the probe is side-effect-free, no server
  fold touched.
- **Deps:** Slice 0. **Files:** `blog/static/vendor/3d-force-graph.min.js`, `blog/static/cortex.js`,
  `tests/test_frontend_contract.py`, `tests/test_cortex.py` (Node-export test for `webglSupported`).

## Slice 2 — The 3D cloud render WITH the M21 fallback chain AND the M22 performance floor in the SAME increment *(audit Group 1: M1–M6 + M16–M20 + M-GATE + M21 + the M22 floor; the M-GATE + M22 release gates)*
The defining slice. Replace the 2D-default render path with: **WebGL→the 3D cloud, else the 2D Cytoscape
island auto-renders, else a searchable list, else the honest message** — the strict hierarchy, **shipped in
one increment** (M-GATE: no 3D ships without the fallback; the regression it prevents — a blank/un-navigable
Cortex on a WebGL-blocked VM — is exactly what 3D-first would introduce). The inspect panel in this slice
stays the **current minimal floating panel** (kind + title + source link + Earmarked composer, unchanged
behavior) — the *enriched* panel is Slice 3, so this slice's surface is the cloud + the fallback, not the
panel rebuild.
- **Build (the renderer branch in `cortex.js`, behind `webglSupported()`):**
  - **M1** 3D force-directed render of the existing `{nodes, edges}` payload (consumed unchanged) — spheres,
    force-laid, thin edges, via `3d-force-graph`.
  - **M2** Camera: orbit (drag-to-rotate) + scroll-zoom + pan (Q7 settled); **read-only camera, nodes not
    draggable** (the 3D analog of `autoungrabify`). Match the reference's "drag to rotate · scroll to zoom."
  - **M3** Trust-weighted **luminosity** preserved: port the `TIER` map (space-0 brightest core → asserted
    bright → extracted dim → episodic faintest haze) to node color/opacity/size — trust stays the **sole**
    size+brightness axis (Q2 settled, no second centrality axis). Guard R4: keep luminosity readable *as
    trust* against 3D depth/occlusion (e.g. disable or bound fog so a distant bright node ≠ a faint low-trust
    node).
  - **M3b** Trust-weighted **edges** preserved: edge opacity/brightness follows the source node's tier
    (`TIER.edge`), so asserted spine edges (GROUNDS/ANCHORS/SERVES) read **stronger** than extracted/episodic
    (MENTIONS/RELATES_TO) — a documented semantic channel (ADR-0010 "trust legible per edge", SURFACE.md
    "bright solid asserted edges"), not styling. Uniform edges = a regression; acceptance ties to the
    existing per-tier `TIER.edge` values.
  - **M4** Earmarked **harm overlay** in 3D: the red-border / never-dimmed treatment survives the port (harm
    overrides the trust-dim, per SURFACE.md).
  - **M5** Center / orient on **space-0** on load (the 3D camera's initial target); a `?node=<ref>`
    deep-link instead centers + selects the located node (reuse `CortexFilters.locate`, unchanged).
  - **M6** **Labels** legible against the dark cloud: space-0 always labeled, plus the
    hovered/selected/search-hit node, scaled by trust tier (Q5 settled — not all-nodes-labeled). Text-only /
    sprite labels, **never raw-HTML from payload** (R5 / cross-cutting #3).
  - **M21 fallback chain (the M-GATE, in THIS increment):**
    1. WebGL available → the 3D cloud (default).
    2. WebGL **unavailable** → the **2D Cytoscape island auto-renders** — the existing, tested code +
       vendored `cytoscape.min.js`, **not deleted, not bypassed** (the single mandated fallback path).
    3. Cytoscape also fails to render (canvas/2D unavailable too) → an **accessible searchable node/edge
       list** with the source-drill links + node selection (tertiary).
    4. Even the list cannot render → the **honest fail-dark-style message** (the floor).
  - **M16** fail-**dark** unchanged: `cortex_fold → None → _cortex_dark()` still renders the honest dark page
    (no group / neo4j unreachable) — **the 3D lib is not loaded / no-ops when there is no payload** (the
    island guard already returns early without a `#cortex-data` block). Fail-dark (absent data) stays
    distinct from the M21 chain (unsupported renderer, data present).
  - **M17** `group_id` scoping + the `_json_for_script` XSS-safe embed unchanged; the 3D lib introduces **no
    `innerHTML`-from-payload** path (cross-cutting #3).
  - **M18 / M19** self-hosted (Slice 1) + loaded **only on `/cortex`** (the island, never the app shell —
    the heavy three.js bundle must not touch the read-mostly pages; today the `<script>` tags are emitted
    only by the `cortex()` route).
  - **M20** the render + fallback markup use the Slice-7 vocabulary (the `style.css` tokens, the existing
    `.cortex-page` full-canvas chrome, `pages/cortex.html`); no parallel styling.
  - **M22 PERFORMANCE FLOOR — PINNED NUMBERS, settled BEFORE the renderer becomes default, IN THIS SLICE
    (audit M22/R2):** the audit is explicit that performance + ceiling behavior must be settled **before the
    renderer ships** — and because each slice is independently shippable, Slice 2 landing a **live, unbounded**
    force tick at the real graph size IS the regression M22 names. The floor is **pinned with concrete numbers
    in this plan** (not "define a threshold after seeing results" — a post-hoc weak threshold would let a
    sluggish renderer pass), and Slice 2 **fails** if any are unmet:
    (i) **measure** the current `group_id`'s graph size at build time (`cortex_fold()` on the live install) +
    record it; baseline ~268 nodes / ~260 edges (`edge-next`, SURFACE.md), but it accretes — measure, don't
    assume.
    (ii) **Force-tick ceiling (PINNED):** the layout **freezes within ≤ 2.0 s wall-clock OR ≤ 300 ticks**,
    whichever first, then **stops** (the `cooldownTicks`/`cooldownTime` convergence condition is set, not
    left to run) — assert the sim is idle (no further ticks) after convergence. No unbounded live tick.
    (iii) **Interactive frame-rate floor (PINNED):** **≥ 30 FPS sustained over a 5 s measurement window**
    while orbiting, at the measured baseline size, in **headless Chromium (the Playwright gate's profile)** —
    the same fixed profile every run, so the number is comparable, not hardware-lottery. Slice 2 fails below 30.
    (iv) **Growth-stress ceiling (PINNED fixture):** a **synthetic fixture of ~1 000 nodes / ~1 000 edges
    (~4× the baseline)** must still **converge-and-freeze** (rung (ii)) and degrade via the cap — **never a
    runaway live tick** — even if it renders below 30 FPS (the cap, not the FPS floor, is what (iv) proves).
    This is the **hard floor**; Slice 6 is only *tuning beyond* it (the Episodic-collapse contingency lever +
    any finer thresholds). All of (i)–(iv) are client-side over the existing payload — **no `cortex_fold`
    change** (the 1 000-node fixture is a test-only synthetic payload, not a graph mutation).
  - **`cortex()` route change (template/island wiring only, NOT the fold):** emit BOTH vendored scripts
    (cytoscape for the fallback + 3d-force-graph) island-only, plus the existing `cortex-data` block and
    `cortex.js`; the searchable-list fallback (tier 3) is a server-rendered `<noscript>`-style block from the
    same payload (so it works even if JS is dead) OR a JS-built list from the payload — pick the cheaper, but
    it must be navigable (source links + selection) and reconcile the existing
    `test_cortex.py` assertions (`"cytoscape"` in body, `/static/cortex.js` in body) — extend, don't break
    them.
- **Accept (the happy path AND every fallback rung — the M-GATE is tested, not asserted):**
  (a) with WebGL → the 3D cloud renders the payload, space-0 centered, orbit+zoom+pan work, nodes
  non-draggable; trust luminosity + per-tier edges + the Earmarked red overlay are visually present and
  trace to `TIER`/`TIER.edge`/`earmarked`; space-0 + the selected node are labeled.
  (b) **WebGL forced unavailable (stub `webglSupported()`→false) → the 2D Cytoscape island auto-renders** and
  is navigable (the existing island behavior) — the single mandated fallback, **not a list, not a message**.
  (c) Cytoscape render forced to fail → the **searchable node/edge list** renders with source links + node
  selection.
  (d) list render forced to fail → the **honest message** (the floor).
  (e) `cortex_fold → None` → **fail-dark** page, **no 3D canvas error, no 500**, the 3D lib not active.
  (f) the `_json_for_script` block is unchanged and no payload value reaches `innerHTML`; a poisoned node
  `title` carrying `</script><script>` / `" onclick=` does not execute in 3D, the 2D fallback, or the list
  (port the existing breakout fixtures from `test_cortex.py`).
  (g) `?node=<stable-ref>` still centers+selects the originating node in 3D (R6 inbound path intact).
  (h) no CDN `<script src>`; the 3D + cytoscape scripts are emitted **only** by `/cortex` (grep another page
  → absent). `test_cortex.py` + `test_cortex_correct.py` + `test_frontend_contract.py` + the full dashboard
  suite green.
  **(i) the browser gate (the M-GATE proven in a real renderer, NOT just a Flask 200):** a new
  Playwright/headless-Chromium test asserts each rung renders — WebGL→true: a **non-blank** 3D canvas
  (pixel/canvas-nonempty check) + orbit/zoom respond + space-0 centered; WebGL→false (stubbed): the **2D
  Cytoscape island** renders non-blank + navigable; Cytoscape render forced to fail: the **searchable list**
  DOM renders; list forced to fail: the **honest message**; and the 3D + cytoscape `<script>`s load only on
  `/cortex`. The fallback ladder is **proven to render**, not merely asserted in prose — a blank 3D canvas or
  a dead rung **fails** this gate. Runs backgrounded against a backgrounded server (never `blog/server.py` in
  the foreground; `pkill` after), the same Playwright harness the operator used to capture the reference.
  **(j) the M22 floor — the PINNED numbers met before default 3D ships:** the force tick **freezes within
  ≤ 2.0 s / ≤ 300 ticks** then idles (assert no unbounded tick); the renderer sustains **≥ 30 FPS over a 5 s
  window** while orbiting at the **measured** baseline size in the headless-Chromium gate profile; the
  **~1 000-node / ~1 000-edge growth fixture** still converges-and-freezes + degrades via the cap (no runaway
  tick); the measured baseline size is recorded; **no `cortex_fold`/`_map_node` change** (the growth fixture
  is a test-only synthetic payload). Slice 2 **fails** if any pinned number is unmet.
- **Codex gate:** `/codex:review` — **challenge the M-GATE explicitly** (is the 2D fallback truly the
  auto-path, not a list? **does a real-browser test prove each rung renders non-blank, not just return 200?**)
  **AND the M22 floor** (are the PINNED numbers — ≤2s/≤300-tick freeze, ≥30 FPS over 5 s in the fixed headless
  profile, the ~1 000-node growth fixture converging — actually asserted and failing the slice if unmet,
  before default 3D ships, not a post-hoc weak threshold?), the security-seam survival (M17/R5), fail-dark vs
  M21 distinction (M16), island-only loading (M19), and
  conformance to ADR-0010 + `docs/frontend.md` + SURFACE.md.
- **Deps:** Slices 0, 1. **Files:** `blog/static/cortex.js`, `blog/templates/pages/cortex.html`,
  `blog/server.py` (the `cortex()` route's **script-tag / list-fallback wiring only** — the fold is
  untouched), `blog/static/style.css`, `tests/test_cortex.py`, `tests/test_frontend_contract.py`, and a new
  browser/Playwright test (e.g. `tests/test_cortex_render_browser.py`) for the M-GATE fallback ladder.

## Slice 3 — The enriched slide-in inspect panel (the additive surface) *(audit Group 2: M7, M8, M10, M10b, M12, M13; G5)*
Replace the minimal floating div with the structured side panel that slides in on node-select, carrying the
fields that already exist in `_map_node` or are derivable — **but NOT yet the CONNECTS-TO traversal nor the
`?node=` write** (those are Slice 4, so this slice ships a richer but still single-node panel and the tree
stays green). Reconcile G5: the panel **markup** becomes a registered `components/ui.html` macro +
`/ux-catalog` entry, while the panel is still **populated by the island via DOM APIs + `esc()`** (the
breakout defense is a security feature, not a rewrite-to-innerHTML).
- **Build:**
  - **M7** A side panel that **slides in** on node-select (replaces the current floating `.cortex-inspect`),
    built with the Slice-7 vocabulary — a new `inspect_panel` macro in `components/ui.html` (the static
    shell: regions for term/definition, SEEN-IN-THE-WILD, FULL DEFINITION, the composer slot). **The macro is
    rendered into `pages/cortex.html` as the empty shell** (so `/cortex` itself carries the macro's DOM
    regions — NOT a JS-only one-off the island builds from scratch, which would satisfy catalog registration
    while violating the Slice-7 shared-UX contract on the shipped surface), AND registered on `/ux-catalog`.
    The island then **fills the macro's empty regions by DOM API** on select, keeping `esc()` and the
    no-string-interpolation breakout defense. (The island no longer `createElement`s the whole panel; it
    populates the server-rendered macro shell.)
  - **M8** Term + **one-line definition**: `label` + `title` (`_node_title`, already shipped).
  - **M10** **FULL DEFINITION** prose = `content` (untruncated, already in `_map_node`) + the source
    drill-down as **READ MORE / abrir fonte →** (the existing `href`, via `appendLink`'s internal-path-only
    guard — unchanged).
  - **M10b** **SEEN IN THE WILD = the node's real `href` provenance** (settled, no new data, no fabrication):
    when a node has an `href`, surface it as the provenance/where-seen affordance; when it does not, **omit
    the block** (no dead link, no placeholder). **Never fabricate an evidence quote** — a curated
    evidence-quote field would be a `_map_node` server change, **out of scope**. The boxed editorial callout
    (N4) is deferred (no data source).
  - **M12** The **Earmarked correction composer** is preserved verbatim in behavior inside the new panel:
    same `POST /cortex/<node_id>/comment` through the Slice-1 gate, the stable-render-token-then-advance
    idempotent nonce, fail-closed node-ref validation, the same-origin fetch. A regression here breaks a
    shipped trust boundary — `test_cortex_correct.py` must stay green unchanged.
  - **M13** **Dismiss / close**: tap-background or a close affordance returns to the free-flight cloud (the
    existing tap-background dismiss survives).
- **Accept:** **the `/cortex` DOM itself contains the `inspect_panel` macro's shell regions** (assert the
  rendered page carries the macro markup, not just that `/ux-catalog` lists it — proving the shared macro is
  used on the shipped surface, not a JS-only one-off); selecting a node slides in the panel with term +
  one-line definition + the FULL DEFINITION prose + READ MORE; a node **with** `href` shows the
  SEEN-IN-THE-WILD provenance link, a node **without** `href` **omits** that block (no dead link, no
  fabricated quote); an Earmarked node still shows the working correction composer and `test_cortex_correct.py`
  passes unchanged; close/tap-background dismisses; the `inspect_panel` macro is also listed on `/ux-catalog`;
  the breakout fixtures (poisoned title/href) stay inert in the panel. Three core suites green + the recurring
  **browser fallback-ladder gate** (this slice touches `cortex.js` + `cortex.html` — re-run it as a
  regression check that the panel change broke no rung).
- **Codex gate:** `/codex:review` — the macro is **rendered into `/cortex`** (not just catalog-registered)
  (M20/G5), the DOM-API breakout defense and `esc()` survive (R5/M17), the correction composer is
  behaviorally unchanged (M12), no fabricated evidence field (M10b), no server fold touched; **re-run the
  browser M-GATE** (renderer touched).
- **Deps:** Slice 2 (the cloud + node selection exist). **Files:** `blog/static/cortex.js`,
  `blog/templates/components/ui.html`, `blog/templates/pages/cortex.html` (render the macro shell),
  `blog/templates/pages/ux_catalog.html`, `blog/static/style.css`, `tests/test_cortex.py`,
  `tests/test_cortex_correct.py`, the browser/Playwright test (re-run).

## Slice 4 — CONNECTS TO neighbor pills + `?node=` round-trip (the navigation loop) *(audit Group 2: M9, M11; G1, G3, R6)*
The core *navigation* verb of the experience — graph-as-hypertext: hop node→node. New **client** logic, **no
server change** (the edges are already in the payload).
- **Build:**
  - **M9** **CONNECTS TO — clickable neighbor pills.** Build a `nodeId → neighbors` index from `edges[]`
    once at load (G1, a new pure exported helper — `CortexFilters.neighborIndex(payload)` — tested headless
    under Node). Render the selected node's neighbors as pills (the `nav_pill`/a new `connects_to_pill`
    macro, registered on `/ux-catalog`, DOM-API-filled with `esc()`). **Clicking a pill flies the camera to
    that node** (the 3D analog of `cy.animate(center)`; a correct camera cut is acceptable v1, tweening is
    N3/nice-to-have), **re-renders the panel for the new node, and updates `?node=`.**
  - **M11** **URL `?node=` round-trips on selection.** Today `?node=` is read on load (deep-link, Slice 6b)
    but not written on in-graph selection. Selecting / flying to a node now writes the URL via
    `history.replaceState` (no history spam) or `pushState` (back/forward) — pick `replaceState` for
    selection + `pushState` only on an explicit pill-hop if back/forward through the traversal is wanted;
    the persisted target is the **stable `ref`** (not the volatile render id), matching what `locate()`
    resolves inbound. **R6:** the inbound `/chat` provenance link (`/cortex?node=<stable-ref>`) must still
    center+select — `locate()` is unchanged; only the outbound write is added.
- **Accept:** selecting a node shows its CONNECTS-TO neighbor pills derived from `edges[]` (verify the index
  against a fixture with known adjacency); clicking a pill flies the camera to that neighbor, re-renders the
  panel for it, and updates `?node=<stable-ref>` in the URL; reloading that URL re-centers+selects the same
  node (round-trip); the inbound `/chat` provenance deep-link still resolves (R6); `neighborIndex` is
  exported + tested headless; the pill macro is on `/ux-catalog`; pills are DOM-API-built (a poisoned
  neighbor label stays inert). Three suites green + the recurring **browser fallback-ladder gate** (this slice
  touches `cortex.js` — re-run it so the camera-fly/`?node=` change broke no rung).
- **Codex gate:** `/codex:review` — the neighbor index is correct + pure, the `?node=` write uses the stable
  ref (not the render id) and does not break the inbound `locate()` path (R6), no server fold touched (G1/G3
  are client-only), pills on the catalog (M20); **re-run the browser M-GATE** (renderer touched).
- **Deps:** Slice 3 (the panel renders the pills). **Files:** `blog/static/cortex.js`,
  `blog/templates/components/ui.html`, `blog/templates/pages/ux_catalog.html`, `blog/static/style.css`,
  `tests/test_cortex.py`.

## Slice 5 — Search-fly-to + PREV / NEXT traversal *(audit Group 3: M14, M15; Q8)*
"Find your way through the brain." M14 reuses shipped, tested pure logic (nearly free); M15 adds a stable
deterministic traversal order.
- **Build:**
  - **M14** **Search top-left (find-and-jump).** Reuse `CortexFilters.search`/`render` (deterministic
    label/type/id/ref match — **NOT** semantic retrieval, per SURFACE.md's banned-fetch posture; the pure
    logic + its tests port as-is). On hit, **fly the camera to the located node** (the 3D analog of today's
    `cy.animate(center)`), select it, open the panel. The existing controls markup
    (`#cortex-search`/status) + the controls `<aside>` are reused; only the on-hit *action* changes from
    `cy.animate` to a 3D camera move.
  - **M15** **PREV / NEXT traversal** (the reference's `← PREV / NEXT →`). Steps the selection + flies the
    camera along a **stable deterministic order over the currently-visible (filtered) set**, computed
    **client-side over explicit node fields** — a new exported pure helper
    `CortexFilters.traversalOrder(payload, state)` sorting by **`(trust-tier rank, label, normalized title,
    ref)`** with `ref` the final tie-breaker, **intersected with the active filter set** (so PREV/NEXT
    respects filters, consistent with `render()`'s no-resurrection rule). **NOT raw Neo4j "payload order"**
    (Q8 settled): `_cortex_live` runs the Cypher with **no `ORDER BY`** and serializes `.data()` directly, so
    row order is not stable across requests/versions/plans — the client-side sort over stable fields makes
    traversal repeatable **with no server change**. PREV/NEXT controls = a small pair of buttons in the
    existing controls `<aside>` (the Slice-7 vocabulary), wired to step the sorted index and fly the camera +
    open the panel.
- **Accept:** searching a label flies the camera to + selects + opens the panel for the located node, status
  shows the visible-match count, and a filtered-out node is **never** resurrected by search (the existing
  `render()` contract); PREV/NEXT step the selection in a **stable, repeatable** order that **survives a
  reload** (assert `traversalOrder` is deterministic over a fixture and ignores Neo4j row order), **respects
  the active filters** (a filtered-out node is skipped), wraps or stops cleanly at the ends, and flies the
  camera + opens the panel each step; `traversalOrder` is exported + tested headless. Three suites green + the
  recurring **browser fallback-ladder gate** (this slice touches `cortex.js` + `cortex.html` — re-run it so
  search/PREV-NEXT broke no rung).
- **Codex gate:** `/codex:review` — the traversal order is stable + filter-respecting + server-independent
  (Q8), search stays deterministic (no semantic retrieval), the on-hit camera move replaces `cy.animate`
  cleanly, no server fold touched; **re-run the browser M-GATE** (renderer touched).
- **Deps:** Slice 4 (selection + panel + camera-fly exist to drive). **Files:** `blog/static/cortex.js`,
  `blog/templates/pages/cortex.html` (the PREV/NEXT controls), `blog/static/style.css`,
  `tests/test_cortex.py`, the browser/Playwright test (re-run).

## Slice 6 — Performance tuning BEYOND the Slice-2 floor *(audit Group 4: M22 tuning; R1/R2)*
The hard M22 floor (measure + freeze-after-convergence + a concrete FPS threshold + a growth-stress ceiling)
**already shipped in Slice 2** — default 3D never went live without it. This slice is the *tuning beyond* that
floor: the contingency lever the audit/SURFACE.md name for when the haze is heavy or the graph has grown past
the Slice-2 measurement. R1 already accepted the bundle weight; this is about the **render density**, not the
bundle KB.
- **Build:**
  - **Re-measure** the current `group_id`'s graph size (it accretes every beat — the Slice-2 number may be
    stale); if it now misses the Slice-2 FPS threshold, engage the lever below.
  - **The Episodic-collapse lever (SURFACE.md's own suggestion):** collapse the ~91 `Episodic` nodes into
    their `MENTIONS` parent so the faint haze stops costing render budget — a **client-side render decision
    over the existing payload, no `cortex_fold` change.** Plus any finer level-of-detail / edge-bundling
    tuning beyond the Slice-2 cap.
- **Accept:** with the lever engaged the rendered density drops and the measured FPS recovers above the
  Slice-2 threshold at the re-measured (grown) size; the Episodic-collapse is a **client render decision**
  (the payload + `cortex_fold`/`_map_node` are **unchanged**); the Slice-2 floor (frozen tick, FPS threshold,
  growth-stress ceiling) **still holds** (re-run that acceptance). Three suites green + the renderer-touching
  recurring **browser fallback-ladder gate** (this slice touches `cortex.js`); the re-measured number +
  the engaged lever are recorded.
- **Codex gate:** `/codex:review` — the lever is genuinely client-side (no server fold), the Slice-2 floor is
  not regressed, conformance to SURFACE.md's stated lever; **re-run the browser M-GATE** (renderer touched).
- **Deps:** Slices 2–5 (the full renderer to tune). **Files:** `blog/static/cortex.js`,
  `tests/test_cortex.py`, the browser/Playwright test (re-run).

---

## Nice-to-haves (defer unless cheap / free-from-the-lib; revisit after the experience is proven)
- **N1** edge relationship-type label on hover · **N2** hover preview tooltip · **N3** camera-easing
  tween (take it if `3d-force-graph` gives it free) · **N4** the boxed editorial callout (no data source —
  deferred) · **N5** bloom / fog / DOF post-processing (costs WebGL budget; revisit only after M22 passes) ·
  **N6** minimap · **N7** the 2D island as a user-facing *preference* toggle (distinct from its MUST role as
  the WebGL fallback — never delete it) · **N8** tuned mobile touch controls (desktop-first per
  `docs/frontend.md`; touch must not *crash*, a tuned UX is out of scope).

## Definition of done (the program)
On `/cortex` the mentee **flies through the edge's mind**: a dark, luminous, trust-weighted 3D
force-directed cloud centered on space-0 (with per-tier edges + the Earmarked harm overlay), clicks a node
to slide in a structured inspect panel (term + definition + SEEN-IN-THE-WILD provenance + FULL DEFINITION +
the Earmarked correction composer), hops node→node via CONNECTS-TO pills with the camera flying + `?node=`
round-tripping, finds-and-jumps via search, and steps PREV/NEXT in a stable order — **and on any
WebGL-incapable client the same Cortex stays navigable** via the 2D Cytoscape fallback (→ list → honest
message). The `/cortex` data API, `cortex_fold`, fail-dark, `group_id` scoping, the `_json_for_script` embed,
and the Slice-6b correction path are **unchanged**; the design system, the no-CDN supply chain, and the
security seams are **maintained**.
