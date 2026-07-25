# Audit — Cortex 3D Graph Navigation (the must-have feature set)

The operator's goal: transform `/cortex` from a flat **2D Cytoscape** constellation into a **3D
force-directed "navigate the brain"** experience — modeled on Matt Pocock's *AI Coding Dictionary*
(`/tmp/aicd-4.png` the cloud, `/tmp/aicd-2.png` the node-selected panel), but in the edge's **dark,
luminous, trust-weighted identity** rather than the reference's light-minimal. This realizes the
operator's founding brief: *"interface futurista de grafo, navegar pelo cérebro do agente."*

This is **Phase 1 (AUDIT)**: which features we **must** have to achieve the experience — traced to the
target interaction and to what Cortex already provides. It is **not** the implementation plan (Phase 2)
and prescribes no code. Gated by `/codex:adversarial-review`; done when the remaining increments are
purely cosmetic.

References (not duplicated here): `docs/frontend.md` (the front-end contract — server-rendered, islands,
cheap-on-resources, self-hosted no-CDN), `CONTEXT.md` (glossary: Cortex / space-0 / Earmarked / trust),
`CONTRACT.md` (C1 read-only-on-the-world, C4 secrets), `docs/adr/0010` (navigate-the-Cortex),
`docs/adr/0005-0006` (the graph/pages are projections of the log), `SURFACE.md` (the hardened Cortex
surface), `blog/server.py` (`/cortex`, `cortex_fold`, `_map_node`, `_node_href`), `blog/static/cortex.js`
(the current 2D island), `blog/templates/pages/cortex.html`, `blog/static/style.css` (the dark tokens).

## What the target experience IS (the bar)

A first-person flight through the edge's mind. Concretely, from the screenshots + the handoff:

1. **The cloud** — a 3D force-directed graph: spheres sized by importance, floating in space, thin
   edges, small-caps labels. *"Drag to rotate · Scroll to zoom."* The camera moves; you fly through it.
2. **Click a node → a side panel slides in** carrying: term + one-line definition; **SEEN IN THE WILD**
   (real-usage evidence/quote); a highlighted in-context callout; **CONNECTS TO** clickable neighbor
   pills (selecting one flies the camera there, updates the panel, updates the URL `?node=`); **FULL
   DEFINITION** prose with READ MORE; **← PREV / NEXT →** traversal; **search** top-left.
3. **The edge's twist (operator decision 2):** DARK space, not light. Node luminosity = trust-weighted
   brightness (space-0 brightest → Episodic faintest — *already* the Cortex design in `cortex.js`'s
   `TIER` map). The Earmarked harm overlay (red border) survives into 3D.

## What Cortex already provides server-side (the mapping — most exists)

The handoff is right: **the data layer is done; only the front-end island + the inspect panel change.**
Confirmed by reading the code:

| Target-interaction need | Already shipped (where) |
|---|---|
| Node size = importance | trust tier → brightness/size in `cortex.js` `TIER`; tier from `_TRUST_BY_LABEL` (`_map_node`) |
| Term + definition line | `_map_node` ships `title` (`_node_title`) + full `content` (`_node_content`, untruncated) |
| **CONNECTS TO** neighbors | `cortex_fold` ships the full `edges[]` (every `(a)-[r]->(b)` in the group); neighbors are derivable client-side from the one payload — no new query |
| **SEEN IN THE WILD** / source | `_node_href` → the real source surface (`/e/<slug>`, `/direction`, `/docs/source-roadmap`, `/wiki/<cluster>`); rendered today as `abrir fonte →` (Slice 6) |
| Search (find-and-jump) | `CortexFilters.search`/`render` + the controls (Slice 6), deterministic over the loaded payload |
| `?node=` deep-link / centering | `cy.ready` + `CortexFilters.locate(payload, ref)` already center+select on a stable-ref deep-link (Slice 6b) |
| Filter (type / Earmarked / recency) | `CortexFilters.visible` + `_cortex_controls` (Slice 6) |
| Earmarked correction write-path | `POST /cortex/<node_id>/comment`, the inspect-panel composer (Slice 6b), fail-closed node-ref validation |
| Dark / luminous identity | `style.css` dark tokens + `TIER` brightness; `.cortex-page` full-canvas chrome |
| fail-dark / group scoping | `cortex_fold` → `_cortex_dark()`; `group_id`-scoped query; never graph-wide |
| XSS-safe payload embed | `_json_for_script` (escapes `<>&` + U+2028/9) — the 3D island inherits this seam unchanged |

**The invariant for this program:** the `/cortex` data API, `cortex_fold`, `_map_node`, fail-dark,
`group_id` scoping, `_json_for_script`, and the correction path stay **unchanged**. The change surface is
`blog/static/cortex.js` (2D Cytoscape → 3D force-graph), the inspect panel (enrich it), the vendored lib,
`templates/pages/cortex.html`, and the Cortex CSS. **If a "must-have" below requires touching
`cortex_fold`/`_map_node`, that is a flag the audit raises explicitly — it should be additive and rare.**

---

## MUST-HAVE feature set (grouped) — core to the 3D "navigate the brain" experience

### Group 1 — The 3D cloud (the spatial substrate)
- **M1. 3D force-directed render of the whole-Cortex payload.** Spheres in space, force-laid, thin
  edges. The single defining feature; everything else hangs off it. Consumes the existing `{nodes,
  edges}` from `cortex_fold` unchanged.
- **M2. Camera navigation — drag-to-rotate (orbit), scroll-to-zoom, pan.** The "fly through it" verb.
  The reference labels these explicitly. Read-only camera, not node-dragging (matches today's
  `autoungrabify`).
- **M3. Trust-weighted luminosity preserved in 3D (the dark identity).** space-0 brightest core →
  asserted bright → extracted dim → Episodic faintest haze, by the existing `TIER` map. Node size =
  trust tier (already the design). This is the operator's *whole reason* for dark-not-light; it is a
  must, not a finish.
- **M3b. Trust-weighted EDGES preserved in 3D (not just nodes).** Edge brightness/opacity follows the
  source node's trust tier — asserted edges (GROUNDS/ANCHORS/SERVES, the curated spine) render visually
  **stronger** than extracted/episodic edges (MENTIONS/RELATES_TO, the hypothesis haze). This is a
  documented semantic channel, not styling: `cortex.js`'s `TIER.edge` already encodes it, SURFACE.md names
  trust-weighted brightness (incl. *"bright solid asserted edges"*) the *primary* simplification axis, and
  ADR-0010 states *"trust is legible per edge."* A 3D port with **uniform edges** silently drops the
  curated-vs-hypothesis distinction — a regression. Acceptance ties to the existing `TIER.edge` behavior.
- **M4. Earmarked harm overlay in 3D.** The red-border (harm-overrides-dim) treatment survives the port.
  Harm awareness is a Cortex semantic, not decoration — losing it in 3D is a regression.
- **M5. Center / orient on space-0 on load.** The gravitational core the mentee orients from (today
  `cy.ready` centers space-0). In 3D this is the initial camera target.
- **M6. Node labels legible against the dark cloud.** Small-caps-style labels (reference), at minimum on
  space-0 + the hovered/selected/search-hit node (today: space-0 always; title on select/hit). Label
  density is a tuning question (see Q7), but *some* legible labeling is must-have.

### Group 2 — The inspect panel (click a node → it slides in)
This is the biggest *additive* surface. Today's panel is a minimal floating div (kind + title + `abrir
fonte →` + the Earmarked composer). The target panel is a structured side panel. Each field below maps
to data that already exists in `_map_node` or is derivable from the payload.
- **M7. Side panel that slides in on node-select** (replaces the current floating `.cortex-inspect`),
  carrying the structured fields below. Built with the **Slice-7 shared UX vocabulary** (Jinja
  `components/ui.html` macros, `style.css` dark tokens, Tabler under the dark bridge) — not a parallel
  styling system, and not interpolated-string HTML (keep the DOM-API / `esc()` breakout defenses already
  in `cortex.js`).
- **M8. Term + one-line definition.** `label` + `title` (`_node_title`) — already shipped.
- **M9. CONNECTS TO — clickable neighbor pills.** Derive a node's neighbors from `edges[]` (already in
  the payload), render as pills; **clicking a pill flies the camera to that node, re-renders the panel,
  and updates `?node=`.** This is the core *navigation* loop of the experience (graph-as-hypertext). The
  neighbor derivation is new *client* logic but needs **no server change** — the edges are already there.
- **M10. FULL DEFINITION prose + the source drill-down.** `content` (untruncated, already shipped in
  `_map_node`) as the prose body; the existing `href` as **READ MORE / abrir fonte →** (Slice 6 drill).
  Preserves the "graph stops being an island" wiring.
- **M10b. SEEN IN THE WILD = the node's real provenance/source (settled — no new data, no fabrication).**
  The reference's "SEEN IN THE WILD" evidence block maps onto the node's **existing `href` provenance** —
  the real surface the node came from (`/e/<slug>` blog entry, `/direction`, `/docs/source-roadmap`,
  `/wiki/<cluster>`), rendered as the evidence/where-this-is-seen affordance. **Acceptance:** when a node
  has an `href`, the panel surfaces it as the SEEN-IN-THE-WILD provenance link; when it does not, the block
  is omitted (no dead link, no placeholder). The audit **settles** this (it does not leave it open): we map
  onto existing provenance and **never fabricate an evidence quote**. A *distinct curated evidence-quote
  field* would be a `cortex_fold`/`_map_node` server change — **out of scope** for this front-end-only
  program (if the operator ever wants it, it is a separate data slice, flagged in G2, not a blocker here).
  The reference's *boxed in-context callout* (a second editorial field) has no Cortex data source → N4
  (deferred), distinct from this provenance block.
- **M11. URL `?node=` round-trips on selection.** Today `?node=` is read on load (deep-link) but not
  *written* on in-graph selection. Must-have: selecting/flying to a node updates the URL (back/forward,
  shareable, provenance link target). Pure client-side `history.replaceState`/`pushState`; the existing
  `locate(payload, ref)` already resolves the inbound direction.
- **M12. Earmarked correction composer preserved.** The Slice-6b node-targeted Voz write-path
  (fail-closed validation, idempotent nonce, same-origin POST through the Slice-1 gate) must continue to
  work from the new panel, unchanged in behavior. A regression here breaks a shipped trust boundary.
  **Doc-vs-reality flag (must resolve before Phase 2):** `SURFACE.md` (lines 301–304, 321–322) still
  describes Cortex as *"read-only for the mentee"* and node-targeted Voz as an *"explicit future"* / *"open
  bridge"* — but the code (`POST /cortex/<node_id>/comment` in `blog/server.py`, the correction composer
  in `cortex.js`) shows it **shipped in Slice 6b**. The audit treats it as shipped+mandatory because the
  *code* is authoritative on what exists; **both `SURFACE.md` AND `docs/frontend.md` must be updated to
  make Slice-6b node-targeted Voz part of the current Cortex contract** (fail-closed validation,
  idempotency, auth/CSRF, provenance) — `docs/frontend.md:96` *also* still calls `/cortex` *"a island do
  grafo (read-only surf da brain)"*, and it is the *canonical* front-end doc this audit treats as
  authoritative. Updating only SURFACE.md leaves the canonical front-end contract still reading "read-only,"
  so Phase 2 inherits conflicting authority — "preserve the composer (audit/code)" vs "Cortex is read-only
  (front-end doc)". This doc update (with its own review) is a Phase-2 prerequisite, not an afterthought.
- **M13. Dismiss / close the panel** (tap background or close affordance) — returns to the free-flight
  cloud. Today: tap-background dismisses.

### Group 3 — Search & traversal (find your way through the brain)
- **M14. Search top-left (find-and-jump).** Reuse `CortexFilters.search`/`render` (deterministic
  label/type/id/ref match — NOT semantic retrieval, per SURFACE.md's banned-fetch posture). On hit, **fly
  the camera to the located node** (the 3D analog of today's `cy.animate(center)`), select it, open the
  panel. The pure logic is already factored + tested under Node — it ports as-is.
- **M15. PREV / NEXT traversal.** The reference's `← PREV / NEXT →`. Steps the selection + flies the camera
  along a **stable deterministic order over the currently-visible (filtered) set**, computed **client-side
  over explicit node fields** — sort by `(trust-tier rank, label, normalized title, ref)` with `ref` as the
  final tie-breaker — intersected with the active filter set (so PREV/NEXT respects filters, consistent with
  the no-resurrection rule in `render()`). **NOT "payload order":** `_cortex_live()` runs the Cortex Cypher
  with **no `ORDER BY` and serializes `s.run(...).data()` directly**, so Neo4j row order is *not* guaranteed
  stable across requests/versions/query-plans — relying on it would make traversal silently reorder on
  reload. The client-side sort over stable fields fixes the order **without any server change** (front-end-
  only mandate honored). (Ordering is settled, not open — Q8.)

### Group 4 — The non-negotiable invariants (must survive the port; failing any is a regression)
- **M16. fail-dark when the graph is dark.** `cortex_fold → None → _cortex_dark()` must still render the
  honest dark page (no group / neo4j unreachable) — **never a 3D canvas error, never a 500.** The 3D lib
  must not be loaded or must no-op when there is no payload.
- **M17. `group_id` scoping + XSS-safe embed unchanged.** The 3D island consumes the same
  `_json_for_script` data block; cross-install isolation and the script-context breakout defense are
  untouched. The 3D lib must not introduce its own `innerHTML`-from-payload path that bypasses `esc()`.
- **M18. Self-hosted, no-CDN 3D lib (decision 3 / Slice 7 #37).** The chosen lib (+ its three.js
  dependency) is **vendored into `blog/static/vendor/`**, pinned, served locally. **No `<script
  src="https://…">`.** This is a hard supply-chain invariant, not a preference.
- **M19. Loaded ONLY on `/cortex` (a JS island, never the app shell).** The heavy 3D/WebGL lib must not
  touch the read-mostly pages — honors `docs/frontend.md`'s cheap-on-resources constraint. Today
  Cytoscape is island-scoped; three.js (heavier) must be too.
- **M20. The Slice-7 shared design system is maintained.** Flask+Jinja scaffold (`base.html`,
  `partials/`, `components/ui.html` macros, `pages/cortex.html`), Tabler under the dark-token bridge, the
  `:root` tokens as the palette source of truth, the `/ux-catalog` registration for any new component
  (e.g. the inspect panel, the CONNECTS-TO pill). **No one-off parallel styling.**
- **M-GATE. The WebGL-fallback chain (M21) is a release gate, not a later slice.** No 3D Cortex increment
  ships until the strict fallback hierarchy — WebGL → 3D, else 2D Cytoscape auto-render, else searchable
  list, else honest message — is **implemented and tested**. M21 lives in Group 5 below for grouping, but
  its *sequencing weight is here*: it cannot be deferred behind the 3D happy path, because the regression
  it prevents (a blank/un-navigable Cortex on a WebGL-blocked VM/browser) is exactly what shipping 3D-first
  would introduce. Treat M21 as an invariant of every 3D increment, on a par with M16 (fail-dark).

### Group 5 — Degradation & reach (must-have *as a decision*, even if the decision is "minimal")
These are must-have to *make a defensible call on*, because shipping 3D without answering them silently
drops users. The audit's position is stated; the operator confirms.
- **M21. WebGL-unavailable fallback MUST stay navigable (not just honest).** 3D force-graphs need WebGL.
  When WebGL is absent/blocked (hardened browsers, some VMs, GPU-blocklisted contexts), the page must
  degrade to a **still-navigable Cortex** — **not a blank canvas and not a bare message.** A message-only
  fallback would leave a host where the graph *data is present* but the Cortex recall surface is
  functionally gone — a **regression from today's working Cytoscape island** and a violation of ADR-0010's
  *navigable-Cortex* contract (fail-dark is for *absent graph data*, M16 — not for an unsupported renderer
  when a tested non-WebGL renderer already exists). **The fallback is a strict hierarchy, not a choice:**
  1. **WebGL available → the 3D cloud** (the default experience).
  2. **WebGL unavailable → the 2D Cytoscape island auto-renders** — *required*, not optional. The code +
     vendored Cytoscape already exist and are tested; this is the single mandated fallback path (option (c)
     of Q3). Phase 2 must **not** delete or bypass the 2D renderer.
  3. **Cytoscape also fails to render (canvas/2D unavailable too) → an accessible, searchable node/edge
     list** with the source-drill links + node selection — a tertiary last resort, never the *primary*
     WebGL fallback.
  4. **Even the list cannot render → the honest fail-dark-style message** (the floor).
  A WebGL capability check (G4) selects between 1 and 2 on load. The list and message are strictly *below*
  the required 2D-graph fallback — a list-only WebGL fallback does **not** satisfy M21.
- **M22. Performance bound at the live graph size — against the documented baseline.** A force-directed
  3D sim is O(N·E) per tick. `SURFACE.md` (lines 309–318) records the real shape for this install
  (`edge-next`): **~268 nodes / ~260 edges** — the asserted spine (~55: Genesis 1, Objective 1, Direction
  41, Artefato 12) + the extracted bulk (~163: Entity 72, Episodic 91, Source 50), with edges MENTIONS
  196 + RELATES_TO 64 dominating. Must-have: (a) **measure the current `group_id` at implementation time**
  (the graph grows), and (b) define a concrete **acceptance threshold** — an interactive frame rate at
  ~268/260 — plus an explicit **ceiling behavior** (freeze layout after convergence / cap ticks / cap
  rendered nodes / SURFACE.md's own suggestion: collapse the ~91 Episodics into their MENTIONS parent if
  the haze is too heavy) — **before the 3D renderer ships.** The number is no longer "unknown" (R2 below
  updated): ~268/260 is light for three.js *if* the sim is frozen after convergence; the risk is an
  unbounded live tick on a graph that keeps growing. **Gating, not a finish** (see Risk R1/R2).

---

## NICE-TO-HAVE (real to the reference, but not core to the experience; defer unless cheap)
- **N1. Edge labels / relationship-type on edges.** The reference shows mostly unlabeled edges; we have
  `edge.type`. Surfacing it on hover is enrichment, not core.
- **N2. Hover preview** (label/tooltip on hover before click). Polish; click→panel is the must.
- **N3. Animated camera easing / fly-to tweening.** A smooth tween reads better than a jump, but a
  correct cut is acceptable v1. (Borderline — if the lib gives it free, take it.)
- **N4. The highlighted "in-context callout"** (the boxed quote in `/tmp/aicd-2.png`). Nice editorial
  flourish; only real if the node *has* such a callout field — **we do not have a distinct callout vs
  evidence field today** (see Gap G2). Without a data source it is fabricated content — defer.
- **N5. Depth-of-field / bloom / fog post-processing** for the "luminous in space" look. Pure cosmetic;
  costs WebGL budget (M22). Defer; revisit only after performance is proven.
- **N6. Minimap / overview.** Helpful in a big cloud; not in the reference; defer.
- **N7. Keeping the 2D Cytoscape island as a user-facing PREFERENCE toggle.** Only the *preference*
  toggle is nice-to-have. **2D-as-the-WebGL-fallback-renderer is now a MUST (M21)** — the cheapest way to
  meet the navigable-fallback requirement, since the code + vendored Cytoscape already exist and are
  tested. So do **not** delete the 2D island; keeping it *visible as a deliberate user choice* (vs only as
  the automatic fallback) is the nice-to-have. See Q3.
- **N8. Mobile-tuned controls** (touch orbit/pinch). `docs/frontend.md` is explicitly desktop-first
  ("mobile é um Medium diferente"). Touch should not *break*, but a tuned mobile UX is out of scope. See
  Q6.

---

## GAPS — where the target wants data/behavior we don't cleanly have

- **G1. "CONNECTS TO" needs client-side neighbor derivation.** The data (edges) exists, but today's
  island never computes per-node adjacency — it renders the whole graph and selects one node. The panel's
  neighbor pills + the click-to-fly traversal are **new client logic** (build a `nodeId → neighbors`
  index from `edges[]` once at load). No server change; flagged so Phase 2 sizes it.
- **G2. "SEEN IN THE WILD" / "in-context callout" are reference editorial fields with no 1:1 Cortex data
  field — SETTLED, not open.** `_map_node` ships `title` (display blurb) + `content` (full claim) + `href`
  (source). The reference's *evidence quote* ("SEEN IN THE WILD") and the *boxed callout* are editorial
  fields the AI Coding Dictionary authored per term; the Cortex node does **not** carry a separate curated
  evidence quote. **The audit settles this (M10b), it does not leave it open:** "SEEN IN THE WILD" maps to
  the node's **existing `href` provenance** (honest, no new data, no fabrication); the boxed callout → N4
  (deferred, no data). A *distinct curated evidence-quote field* is explicitly **out of scope** here — it
  would be a `cortex_fold`/`_map_node` server change outside the front-end-only envelope; if the operator
  ever wants it, it is a separate future *data* slice, **not** an open call gating this audit.
- **G3. URL `?node=` is read-only today.** Deep-link-in works (Slice 6b); selection-out does not write
  the URL. M11 closes this — small but real (back/forward + shareable-node provenance depend on it).
- **G4. No WebGL capability gate anywhere in the codebase.** M21 needs a new detection seam; nothing
  today checks for it (Cytoscape is canvas/SVG, not WebGL — so this is a *new* failure mode the 3D port
  introduces). Flagged as a port-introduced regression risk.
- **G6. SURFACE.md *and* docs/frontend.md lag the shipped Cortex (doc-conformance blocker).** Both still
  frame Cortex as read-only-for-the-mentee: SURFACE.md with search/filter/node-Voz as "future" (all three
  **shipped** — Slice 6 search + filter, Slice 6b node-targeted Voz), and `docs/frontend.md:96` with
  `/cortex` as a *"read-only surf da brain."* The audit's must-haves are correct against the *code*, but
  Phase 2 cannot conform to "docs/adr + CONTEXT + CONTRACT + SURFACE + the canonical front-end doc" while
  **both** docs contradict the code. **Update both first** (each with its own review) to reflect the
  shipped surface — node-targeted Voz documented as a current, gated Cortex affordance — then build 3D on
  top. This is the one doc-conformance blocker the audit surfaces (see M12's flag for the node-Voz
  specifics).
- **G5. The inspect panel is a hand-built floating div, not a Jinja component.** To satisfy M20 (shared
  UX), the enriched panel should become a registered `components/ui.html` macro + `/ux-catalog` entry —
  today it is constructed entirely in `cortex.js` via DOM APIs. Phase 2 must reconcile "island builds the
  panel in JS" with "the design system is Jinja macros." (The DOM-API construction is a *security*
  feature — the breakout defense — so the reconciliation is structure/markup, not a rewrite to
  innerHTML.) Flagged.

---

## RISKS — what could sink the experience or violate a contract

- **R1. (HIGH) Bundle weight vs the cheap-on-resources constraint.** `docs/frontend.md` is explicit and
  *hard*: no heavy client; htmx ~48 KB, Cytoscape ~365 KB loaded only on `/cortex`. A 3D stack
  (`3d-force-graph` + three.js) is **substantially heavier** (three.js alone is ~600 KB+ minified; the
  full `3d-force-graph` UMD bundle is larger). This is the single biggest tension with the documented
  front-end contract. **The lib choice must be weighed by weight, not just features** (see Q1), and the
  "island-only, never the app shell" rule (M19) is what keeps it inside the contract — the heavy lib
  never taxes the read-mostly pages. Phase 2 must record the chosen bundle size and justify it against the
  constraint, or the constraint is amended (with its own review). **This is the gating risk.**
- **R2. (MED) Performance at live graph size (M22).** The baseline is **documented, not unknown**:
  `SURFACE.md` records ~268 nodes / ~260 edges for `edge-next`. That size is *light* for three.js with a
  frozen post-convergence layout — so the real risk is not the static render but (a) an **unbounded live
  force tick** that never freezes, and (b) **graph growth** (the Cortex accretes nodes every beat — today's
  268 is not a ceiling). Mitigation must be a *must* in Phase 2: freeze-after-convergence + a node/edge cap
  or Episodic-collapse (SURFACE.md's own lever) with the threshold measured against the *current*
  `group_id` at build time. Downgraded from HIGH → MED now that the size is concrete and modest; it stays a
  gate because of growth, not current size.
- **R3. (MED) WebGL/dark-VM reality (M21/G4).** The fleet runs on VMs; software WebGL or a blocklisted
  GPU is plausible. Without M21, those hosts get a blank cloud — strictly worse than today. The fail-dark
  honesty contract (M16) must extend to WebGL-absent.
- **R4. (MED) Losing the trust legibility in 3D.** In 2D, opacity + size + color encode the trust tier
  cleanly. In 3D, depth/occlusion/perspective can *fight* the brightness encoding (a faint distant node
  vs a faint low-trust node look alike). The luminosity encoding (M3) must remain *readable as trust*, not
  just "pretty in space" — else the Cortex's core semantic (asserted vs extracted vs episodic) is lost.
  This is a design risk specific to the dark-3D choice.
- **R5. (MED) Security-seam erosion on the lib swap.** The current island is hardened: `_json_for_script`
  embed, `esc()` on panel content, DOM-API (not attribute-string) link/composer construction, the
  same-origin POST gate. A 3D lib that wants `innerHTML`/HTML labels, or a node `label` rendered as raw
  HTML, **reopens the XSS/breakout vector** the Cortex closed (titles derive from graph content). M17 +
  G5 must be enforced through the swap; codex must check it.
- **R6. (LOW) `?node=` provenance link contract (Slice 6b).** The `/chat` provenance link
  (`/cortex?node=<stable-ref>`) must still resolve in 3D (center+select the originating node). `locate()`
  already handles the inbound resolution; M11 must not break the *inbound* path while adding the
  *outbound* URL write.
- **R7. (LOW) CONTRACT C1 during this audit.** The `/ed-wake` predispatch stamped `dispatch.open` into
  `state/events/log.jsonl` (expected, ADR-0016). This audit phase produces no Artefato and must **not**
  commit `state/` (CONTRACT C1 / the committed-log-clean guard) — reset the dirtied log before any commit.

---

## OPEN CALLS vs SETTLED DEFAULTS

### The ONE open operator call (gates Phase 2)
- **Q1 — 3D lib choice + weight.** `3d-force-graph` (batteries-included: force sim + three.js + camera +
  picking, one UMD bundle, easiest port) vs raw **three.js + `d3-force-3d`** (compose it; smaller if
  tree-shaken, but no build step here so likely shipped whole) vs a lighter WebGL graph lib. Given the
  *no-build-step* reality (we vendor a UMD/min file, no bundler), the practical choice trades convenience
  vs total KB. **What bundle weight is acceptable against the `docs/frontend.md` cheap-on-resources
  constraint, and is the constraint amended for the `/cortex` island specifically?** (Audit lean:
  `3d-force-graph` for the lowest implementation risk, *if* its weight is acceptable island-only; record
  the number.) **This is the only decision the operator must make** — it can put the program in tension
  with a documented front-end contract. Everything below is **settled by the audit** (a confident default,
  implementable without operator input); listed so Phase 2 inherits the decision, not the question.

### Settled defaults (NOT open calls — implementation notes Phase 2 follows)
- **Q2 — Dark adaptation [SETTLED].** Trust tier stays the **sole** size+brightness axis (it is the
  shipped semantic; a second centrality/degree axis would need a `cortex_fold` change — out of scope).
  No second size axis.
- **Q3 — 2D toggle vs replacement [SETTLED].** 3D default; **2D Cytoscape is the required automatic WebGL
  fallback** (M21/M-GATE), never deleted. Exposing it *also* as a user preference toggle is nice-to-have
  (N7), not required. Option (a) "delete 2D" is ruled out.
- **Q4 — "SEEN IN THE WILD" / callout [SETTLED].** Mapped onto the node's real `href`/source provenance
  (M10b); boxed callout deferred (N4); no fabricated quote field. A curated evidence-quote field is an
  out-of-scope future *data* slice.
- **Q5 — Label density [SETTLED].** Today's posture + hover: space-0 always labeled, plus the
  hovered/selected/search-hit node; labels scaled by trust tier so the bright spine reads and the haze
  stays quiet. Not all-nodes-labeled (cloud clutter).
- **Q6 — Mobile [SETTLED].** Desktop-first per `docs/frontend.md` ("mobile é um Medium diferente"): touch
  must not *crash*, but a tuned mobile UX is out of scope.
- **Q7 — Camera model [SETTLED].** Orbit-around-center + zoom + pan — matches the reference's literal
  "drag to rotate · scroll to zoom" and avoids free-fly disorientation.
- **Q8 — PREV/NEXT ordering [SETTLED].** A **client-side stable sort over explicit fields** —
  `(trust-tier rank, label, normalized title, ref)`, `ref` as the final tie-breaker — over the
  currently-visible (filtered) set. **Not raw Neo4j "payload order":** the Cortex fold has no `ORDER BY`, so
  row order is not guaranteed stable; the client sort makes traversal repeatable with no server change.

---

## Priority for achieving the experience (highest leverage first)

0. **Pre-Phase-2 doc-conformance gate (G6 / M12) — do this FIRST, before any 3D work.** Update **and
   review** both `SURFACE.md` and `docs/frontend.md` so node-targeted Voz (Slice 6b) and search/filter
   (Slice 6) are documented as the *current, gated* Cortex contract — both docs still call Cortex
   "read-only," which contradicts the shipped composer M12 must preserve. Phase 2 cannot conform to its own
   doc-conformance mandate while the canonical docs contradict the code, so this gate precedes Group 1.
1. **Group 1 (M1–M6) + the invariants (M16–M20, M-GATE) + the WebGL-fallback chain (M21)** — the 3D cloud
   itself, in the dark trust-weighted identity, island-scoped, self-hosted, fail-dark, secure, **with the
   2D-Cytoscape-auto-fallback shipped in the SAME increment** (M-GATE: no 3D ships without it). Nothing is
   "navigate the brain" without this, and shipping it without the invariants *or the fallback* is a
   regression. **The lib choice (Q1/R1) + performance (M22/R2) gate this group — settle them first.**
2. **Group 2 (M7–M13)** — the enriched slide-in inspect panel with CONNECTS-TO traversal. The
   *navigation* half of the experience (the reference's whole point is hopping node→node). Depends on the
   cloud existing and on the shared-UX reconciliation (G5).
3. **Group 3 (M14–M15)** — search-fly-to + PREV/NEXT. Reuses shipped pure logic (M14 nearly free);
   completes "find your way through the brain."
4. **M22 (performance bound)** — measured against the documented baseline before the renderer ships. (M21,
   the WebGL fallback, is *not* deferred to here — it ships **with** Group 1 per M-GATE; only the
   performance-acceptance work is sequenced as explicit hardening, and R1/R2 must be answered before Group
   1 ships, not after.)
5. **Nice-to-haves (N1–N8)** — only if cheap or free-from-the-lib; revisit after the experience is proven.

## The single open call the operator hasn't made
**After the Priority-0 doc-conformance gate (G6/M12) is resolved**, the one remaining *operator* call is
**the lib + its weight (Q1/R1) against the hard cheap-on-resources constraint.** Everything else is either
already-shipped data, a port of existing pure logic, or a confirmable lean. The bundle weight is the one
decision that can put this program *in tension with a documented front-end contract* — so it is the first
thing Phase 2 must record (after closing the doc gate) and codex must check conformance on. (The G6/M12
doc updates are a prerequisite *task*, not an open operator question — the docs are stale-vs-code, so the
direction is settled; only the wording needs review.)
