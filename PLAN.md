# Execution plan — building toward "fully living the documentation"

Turns `AUDIT.md` into **sequenced, independently-shippable slices**. Each slice is a thin vertical
(route + fold + render + test), built via `/pocock-tdd`, and gated in execution by `/codex:review`
(looped until increments are cosmetic). Gated *as a plan* by `/codex:adversarial-review`.

**Already shipped:** blog index + entries, Voz rail (comment/vote-toggle/chat/reply-render), Cortex
graph (`/cortex`). **Test runner:** `tools/edge-python tests/test_blog.py` (keep green every slice).
**Work only in `~/edge-dashboard-wt`** (parallel-git hazard on `~/edge`). Commit per slice.

## Sequencing rationale
The audit's priority B→A→C→D→E, refined by dependency: the **trust boundary precedes the live loop**
(can't generate replies to spoofable input), and **reads before the docs-graph wiring** (a Cortex node
can only link to a Direction/Briefing surface that exists). Each slice ships a working increment.

---

## Slice 1 — Voz write trust boundary *(audit B, prerequisite)*
Make `voz.*` writes safe before anything generates from them.
- **Build:** a single-tenant auth gate on every write route (`POST /e/<slug>/comment|vote`,
  `/chat/comment`) — session cookie *or* reverse-proxy header (mechanism is a build choice); CSRF/origin
  check; `target_ref` validation (reject slugs absent from the published fold); body-size limit; route
  appends through the **canonical `tools/eventlog` append** (locked, idempotency key), not the
  hand-rolled `_append`.
- **Accept:** unauthenticated/cross-origin write → rejected (test); oversized/invalid-slug → rejected;
  a valid write still appends one event; existing 12 tests green + new auth tests.
- **Deps:** none. **Test seam:** an env flag to set/skip the auth principal in tests.

## Slice 2 — `voz.resolved` lifecycle + the grill drain loop *(audit B, the round-trip)*
Directing answers back, on its own — no hand-appended replies.
- **Build:** introduce the terminal-or-parked outcome model (`voz.resolved {outcome}` / `voz.clarify`)
  per the hardened `SURFACE.md`; `open_comments()` keys on absence of a terminal `voz.resolved` (not
  `voz.reply`). A **drain** mechanism (endpoint `POST /grill/drain` and/or a runnable tool) that loads
  the actionable open comments, generates a `voz.reply` per comment via the edge LLM, writes
  `voz.resolved`, atomically through the canonical append. v1 = a "grill-lite" answerer; folding
  standing comments into Direction is the Slice-4 hook.
- **Accept:** post a comment → run the drain → a `voz.reply` is generated and renders inline, and the
  comment leaves `open_comments()`; the "oi" dead-letter is gone (a real round-trip).
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
- **Accept:** `/direction` shows both tiers; a steer folded from a Directive links back to its comment.
  **Deps:** Slice 3 (drill-down off Briefing); the provenance link is best-effort on existing data.

## Slice 5a — Design-doc surfaces *(audit C)*
The literal "live the documentation," part 1.
- **Build:** navigable pages for the glossary (`CONTEXT.md`), the ADRs (`docs/adr/*`), and the standing
  pages **Idiom** + **Source roadmap / source-feedback** — rendered from the source files (markdown →
  HTML), one index + per-doc view, in the dark theme.
- **Accept:** `/docs` (or per-type routes) lists and renders each; the glossary terms and ADRs are
  readable in-dashboard, not as files. **Deps:** none.

## Slice 5b — Emergent-knowledge surfaces + Cortex wiring *(audit C)*
Part 2: the wiki and the graph→source bridge.
- **Build:** a **wiki/Knowledge-cluster** index + cluster-thread drill-down (from
  `state/wiki/index.html` + `cluster-*.html`); **link Cortex nodes to their source** — clicking an
  `Artefato`/`Direction`/`Source` node in `/cortex` drills into its blog entry / Direction surface /
  source doc.
- **Accept:** the wiki index + a cluster page render in-dashboard; a Cortex node click navigates to the
  real surface. **Deps:** Slices 3–5a (the targets the graph links into must exist).

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
