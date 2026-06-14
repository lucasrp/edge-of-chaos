# Audit — what's missing to *fully live the documentation*

The operator's goal: **a dashboard that fully allows living the documentation** — experiencing the
edge's state, work, decisions, and mind *interactively through the dashboard*, not by reading markdown
files. This audit is the gap between that and what exists. Gated by `/codex:adversarial-review`; it is
done when the remaining increments are cosmetic.

References (not duplicated here): `SURFACE.md` (the hardened surface design), `CONTEXT.md` (glossary),
`docs/adr/0017-*` (comms model), `blog/server.py` (the implementation).

## What "living the documentation" means (the bar)
The dashboard must let the mentee **read the edge's mind, work, steer, and self-state — and direct it
with a real round-trip**:
- read its **work** (Artefatos), its **mind** (Cortex), its **steer** (Direction), its **self-state**
  (Briefing), and the **documentation itself** (glossary, ADRs, comms model) — as live, navigable
  surfaces, not static files;
- **direct** it (Voz) and get an **answer back** — the loop must close, not dead-letter.

## What is built (live on `:8780`)
- **Blog index + entries** — Artefatos as a fold of `artefato.published` + `intent.kernel`; dark theme. ✅
- **Voz rail** — comment, **vote (toggle, cap 1)**, standalone `/chat`, replies rendered inline. ✅
- **Cortex graph** (`/cortex`) — whole-Cortex fold, Cytoscape island, **centered on space-0**,
  **trust-weighted brightness**, **Earmarked overlay**, **`group_id`-scoped & fail-dark**. ✅ (just built)

## The gaps — grouped by what blocks "living the documentation"

### A. The read-side is incomplete — you can't see the whole self-state
- **Briefing** — no self-state landing. `SURFACE.md` designs it (reuses `compose_briefing` — the exact
  text the edge wakes to) + a **read-model health strip** (last dispatch, cursor, extraction errors,
  graph reachability, open-Directive count, Voz backlog). **Not built.** Without it there is no "here
  is where the edge is right now."
- **Direction** — no view of the steers (the `set` / `proposed` two tiers). The mentee can *direct*
  (Voz) but cannot *see* the resulting Direction. **Not built.** → the Voz→Direction loop is invisible:
  "did my steer land?" is unanswerable in the UI.

### B. The direct-side round-trip is broken — and its trust boundary is missing (they ship together)
> A live Voz loop on an **unauthenticated** log resolves spoofed Directives and poisoned votes while
> *looking* like it's living correctly. The drain loop and the write-trust boundary are **one slice**,
> not loop-now-secure-later.
- **The grill drain loop** — ed does not actually reply. The operator's "oi" in `/chat` sat **open**;
  the reply was **hand-appended**. Nothing reads `open_comments()` and generates `voz.reply` /
  `voz.resolved`. The return path *renders* but is not *generated*. **Not built.** → directing the edge
  is a dead letter without a manual close. The single biggest break in "living" the dashboard.
- **Authenticated, validated, bounded writes — a HARD v1 prerequisite, not late robustness.**
  `SURFACE.md` makes dashboard auth + CSRF/origin + `target_ref` validation + a body-size limit + the
  canonical `eventlog` append a hard v1 requirement, because every `voz.*` write appends to the
  **authoritative log**. The grill loop **must not** ship before this. **Not built.**
- **The `voz.resolved` / `voz.clarify` lifecycle** — the drain loop's outcome model per the hardened
  plan (terminal-or-parked, actionable-set, atomic close, concurrency version-guard). The code today
  keys on `voz.reply`-absence; the drain loop is built **on** this lifecycle. **Not built.**

### C. The documentation itself is not surfaced — you read markdown, not live docs
- **Glossary** (`CONTEXT.md`) — the domain language (Cortex, Recall, Earmarked, Directive, Steer…) is
  not navigable in the dashboard. To "live the documentation," the glossary must be a surface.
- **ADRs / comms model** — the decisions (ADR-0017, the Medium/Voz/Directive/Vote model) are not
  surfaced. The mentee reads them as files.
- **Cortex nodes don't link to their source** — you see the brain, but clicking an `Artefato` /
  `Direction` / `Source` node does not drill into the artefato page, the Direction entry, or the doc it
  represents. The graph is an island disconnected from the read surfaces.
- **Standing pages — Idiom and Source roadmap.** Beyond Direction (section A), `CONTEXT.md` defines
  first-class standing pages: the **Idiom** (the mentee-language surface the edge frames in) and the
  **Source roadmap** + source-feedback (what sources the edge reads, and how each actually yielded).
  Neither is surfaced. To "live the docs" the mentee must be able to inspect **what the edge reads** and
  **the language it speaks** — embedded in the Briefing or as drill-downs. **Not built.**

### D. The Cortex graph's deferred half — you can see the brain but can't navigate it well
- **Search** (find-and-jump) — deferred in `SURFACE.md`.
- **Filter** (by node type / recency / Earmarked) — deferred.
- **Earmarked corrective write-path** (correct a harm-bearing node via Voz; `target_ref` beyond slugs)
  — deferred. The overlay is read-only awareness only.

### E. Presentation-contract cleanup — lower priority for *experiencing*
- **Fleet front-end contract (#37)** — Jinja/Tabler/`/ux-catalog`; today the HTML is hand-rolled
  f-strings. Maintainability/consistency, not experience-blocking. (The Voz lifecycle + write-auth that
  were filed here are now **prerequisites in B** — they gate the live Voz loop, not late cleanup.)

## Priority for *living the documentation* (highest leverage first)
1. **(B) the direct-side round-trip + its trust boundary, as ONE slice** — auth + validated/bounded
   writes + the `voz.resolved` lifecycle + the grill drain loop, shipped **together**. Directing must
   round-trip AND must not resolve spoofed/poisoned input. The heart of "living," and unsafe without the
   boundary.
2. **(A) Briefing + Direction** — see the self-state and the steers; close the Voz→Direction loop
   visibly.
3. **(C) surface the docs (glossary, ADRs, Idiom, Source roadmap) + link Cortex nodes to their source**
   — the literal "live the documentation": the design docs as navigable surfaces, the graph wired into
   the read surfaces.
4. **(D) Cortex search / filter** — navigate the brain, not just stare at it.
5. **(E) front-end contract (#37)** — presentation cleanup; required before exposing beyond localhost.

## Open question for the review
Is "living the documentation" satisfied by surfacing **the edge's runtime state** (Cortex, Artefatos,
Direction, Briefing, Voz round-trip), or does it also require surfacing **the design documents
themselves** (CONTEXT.md glossary, the ADRs, SURFACE.md) as first-class navigable pages? This audit
assumes **both** — section C — but the weighting between them is the operator's call.
