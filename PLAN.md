# Execution plan — building toward "fully living the documentation"

Turns `AUDIT.md` into **sequenced, independently-shippable slices**. Each slice is a thin vertical
(route + fold + render + test), built via `/pocock-tdd`, and gated in execution by `/codex:review`
(looped until increments are cosmetic). Gated *as a plan* by `/codex:adversarial-review`.

**Already shipped:** blog index + entries, Voz rail (comment/vote-toggle/chat/reply-render), Cortex
graph (`/cortex`). **Test gate (every slice):** `tools/edge-python tests/test_blog.py` **and**
`tools/edge-python tests/test_cortex.py` (the Cortex graph is shipped) — keep **both** green; add the
affected surface's tests per slice; **Slice 7 runs the full dashboard suite.**
**Work only in `~/edge-dashboard-wt`** (parallel-git hazard on `~/edge`). Commit per slice.

## Sequencing rationale
The audit's priority B→A→C→D→E, refined by dependency: the **trust boundary precedes the live loop**
(can't generate replies to spoofable input), and **reads before the docs-graph wiring** (a Cortex node
can only link to a Direction/Briefing surface that exists). Each slice ships a working increment.

---

## Slice 1 — Voz write trust boundary *(audit B, prerequisite)*
Make `voz.*` writes safe before anything generates from them.
- **Build:** a single-tenant auth gate on **every log-mutating route** — the mentee writes
  (`POST /e/<slug>/comment|vote`, `/chat/comment`) **and the Slice-2 drain (`POST /grill/drain`) if it
  is an HTTP route** (otherwise make the drain a **local-only tool** with no public endpoint). Session
  cookie *or* reverse-proxy header (mechanism is a build choice); CSRF/origin check; `target_ref`
  validation (reject slugs absent from the published fold); body-size limit; appends through the
  **canonical `tools/eventlog` append** (locked, idempotency key), not the hand-rolled `_append`.
- **Accept:** an unauthenticated/cross-origin call to **ANY log-mutating route** (the writes **and** the
  drain, if HTTP) → **rejected with no append** (test each); oversized / invalid-slug → rejected; a
  valid write still appends one event; `test_blog.py` + `test_cortex.py` green + new auth tests.
- **Deps:** none. **Test seam:** an env flag to set/skip the auth principal in tests.

## Slice 2 — `voz.resolved` lifecycle + the grill drain loop *(audit B, the round-trip)*
Directing answers back, on its own — no hand-appended replies.
- **Build:** the terminal-or-parked outcome model (`voz.resolved {outcome}` / `voz.clarify`) per the
  hardened `SURFACE.md`; `open_comments()` keys on absence of a terminal `voz.resolved` (not
  `voz.reply`). A **drain** (`POST /grill/drain` behind the Slice-1 gate, and/or a local-only tool) that
  captures `start_cursor` + the **actionable set**, loads a deterministic **capped batch** (max chats /
  tokens; the **overflow stays open and visible** — never an oversized prompt), generates a `voz.reply`
  per loaded comment via the edge LLM, and — when a comment is a
  **standing Directive** — atomically appends `direction.set` + `voz.resolved {outcome:
  folded-to-direction, origin_comment_id, direction_id}` (the write-side of the Voz→Direction loop;
  surfaced in Slice 4). One **idempotent `append_batch`** keyed by `comment_id`+`grill_run_id` under a
  version guard.
- **Accept (live verticals + failure modes, NOT just the happy path):**
  (a) post a comment → drain → a `voz.reply` generates, renders inline, the comment leaves
  `open_comments()` (the "oi" dead-letter is gone);
  (b) a **standing Directive** → drain → `direction.set` + `voz.resolved{folded-to-direction,
  origin_comment_id, direction_id}` land **atomically** (verified end-to-end in Slice 4);
  (c) the drain loads only the **actionable set** — a parked `voz.clarify` with no answer is **not**
  re-loaded; a `voz.clarify_answer` re-enters it and terminally resolves;
  (d) a **stale/concurrent drain must NOT produce a second terminal outcome** (test the version guard);
  a crash mid-close leaves a chat fully resolved-or-open, never half;
  (e) a duplicate / orphan `voz.resolved` surfaces as a consistency error;
  (f) with **more actionable comments than the cap**, the drain processes only the capped batch and the
  **overflow stays open + visible** (not silently dropped, not stuffed into one oversized prompt);
  (g) the drain route (if HTTP) **rejects unauthenticated / cross-origin calls with no append** (per Slice 1).
- **Deps:** Slice 1 (writes must be trusted before they're auto-resolved).

## Slice 3 — Briefing surface + read-model health strip *(audit A)*
The self-state landing: where the edge is right now.
- **Build:** `GET /briefing` rendering `tools/briefing.py::compose_briefing` (the exact wake text) +
  a compact **health strip** (last dispatch, log cursor, extraction/sweep errors, graph reachability,
  open-Directive count, Voz backlog) — the degraded-mode signal.
- **Accept:** `/briefing` renders the composed self-state + the health strip; fails dark (not blank) if
  a fold is degraded. **Deps:** none (reuses `compose_briefing`).

## Slice 4 — Direction surface *(audit A)*
See the steers; close the Voz→Direction loop visibly.
- **Build:** `GET /direction` folding `direction.*` → the two tiers (`set` curated / `proposed`
  candidate), curated prominent / proposed dimmer; render the `origin_comment_id` provenance link
  (steer ⇄ originating comment) where present. Drill-down from the Briefing.
- **Accept (live, not seeded):** post a **real** standing Directive in `/chat` → run the drain →
  `/direction` shows the **new** `set` steer **linked back to its originating comment**
  (`origin_comment_id`), with `voz.resolved{folded-to-direction}` on the log. Both tiers render
  (curated prominent, proposed dimmer). "Did my steer land?" is answerable end-to-end for a NEW
  directive — not from seeded data. **Deps:** Slices 2 (the write-side fold) + 3 (drill-down off
  Briefing).

## Slice 5a — Design-doc surfaces *(audit C)*
The literal "live the documentation," part 1.
- **Build:** navigable pages for the glossary (`CONTEXT.md`), the ADRs (`docs/adr/*`), and the standing
  pages **Idiom** + **Source roadmap / source-feedback** — rendered from the source files (markdown →
  HTML), one index + per-doc view, in the dark theme.
- **Accept (all four types, not just glossary+ADRs):** glossary terms (`CONTEXT.md`), the ADRs
  (`docs/adr/*`), the **Idiom** page, AND the **Source roadmap / source-feedback** page each list +
  render in-dashboard; none forces the mentee back to a file path. **Deps:** none.

## Slice 5b — Emergent-knowledge surfaces + Cortex wiring *(audit C)*
Part 2: the wiki and the graph→source bridge.
- **Build:** a **wiki/Knowledge-cluster** index + cluster-thread drill-down (from
  `state/wiki/index.html` + `cluster-*.html`), served **through an allowlist sanitizer or a sandboxed /
  no-scripts boundary** — the wiki HTML is **edge-generated and source-derived**, so it must **not**
  execute same-origin in the authed dashboard (an injected `<script>`/handler could read state and fire
  authenticated log-mutating POSTs, defeating the Slice-1 gate). **Link Cortex nodes to their source** —
  clicking an `Artefato`/`Direction`/`Source` node in `/cortex` drills into its blog entry / Direction
  surface / source doc.
- **Accept:** the wiki/Knowledge-cluster index + a cluster-thread page render in-dashboard; **clusters
  are reachable from `/briefing` AND from an Artefato's `distills`** (not just a standalone route); a
  Cortex `Artefato`/`Direction`/`Source` node click navigates to its real surface (blog entry /
  Direction / source doc); a **malicious cluster page** (a `<script>`, an `onerror=` handler, a
  `javascript:` URL) renders **inert** — scripts/handlers stripped or sandboxed, **cannot perform an
  authenticated append** (test it). **Deps:** Slices 3–5a (the targets the graph + distills link into
  must exist).

## Slice 6 — Cortex search + filter *(audit D)*
Navigate the brain, not just stare at it.
- **Build:** find-and-jump **search** (deterministic label/type match → center the node) and **filter**
  (by node type / Earmarked / recency) over the loaded graph payload — client-side on the island.
- **Accept:** searching a node label centers it; filtering by type hides/shows classes. **Deps:** the
  `/cortex` island (built).

## Slice 7 — Fleet front-end contract #37 *(audit E)*
Presentation cleanup; do last, before any non-localhost exposure.
- **Build:** convert the hand-rolled f-string HTML to Flask+Jinja (`base`/`components`/`partials`/
  `pages`) + Tabler/Bootstrap 5 + a `/ux-catalog`, keeping every test marker green.
- **Accept:** all surfaces render via templates; 12+ tests green; `/ux-catalog` lists the macros.
  **Deps:** all prior slices (convert once, after the surfaces exist).

---

## Definition of done (the program)
The mentee can, in the dashboard: read the edge's **work** (Artefatos), **mind** (Cortex, wired to
sources), **steer** (Direction), **self-state** (Briefing+health), and the **documentation** (glossary,
ADRs, Idiom, Source roadmap, Knowledge clusters) — and **direct** it (Voz) with a real, trusted,
self-closing round-trip. That is "fully living the documentation."
