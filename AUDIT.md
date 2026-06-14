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

### B. The direct-side round-trip is broken — you direct, but nothing answers
- **The grill drain loop** — ed does not actually reply. The operator's "oi" in `/chat` sat **open**;
  the reply was **hand-appended**. Nothing reads `open_comments()` and generates `voz.reply` /
  `voz.resolved`. The return path *renders* but is not *generated*. **Not built.** → directing the edge
  is a dead letter without a manual close. This is the single biggest break in "living" the dashboard:
  the interaction loop does not close on its own.

### C. The documentation itself is not surfaced — you read markdown, not live docs
- **Glossary** (`CONTEXT.md`) — the domain language (Cortex, Recall, Earmarked, Directive, Steer…) is
  not navigable in the dashboard. To "live the documentation," the glossary must be a surface.
- **ADRs / comms model** — the decisions (ADR-0017, the Medium/Voz/Directive/Vote model) are not
  surfaced. The mentee reads them as files.
- **Cortex nodes don't link to their source** — you see the brain, but clicking an `Artefato` /
  `Direction` / `Source` node does not drill into the artefato page, the Direction entry, or the doc it
  represents. The graph is an island disconnected from the read surfaces.

### D. The Cortex graph's deferred half — you can see the brain but can't navigate it well
- **Search** (find-and-jump) — deferred in `SURFACE.md`.
- **Filter** (by node type / recency / Earmarked) — deferred.
- **Earmarked corrective write-path** (correct a harm-bearing node via Voz; `target_ref` beyond slugs)
  — deferred. The overlay is read-only awareness only.

### E. The code lags the hardened plan — slice-2 vs the 17-round design
- **Voz lifecycle:** the code keys open/answered on `voz.reply`-absence; the hardened plan is
  `voz.resolved` / `voz.clarify` + the actionable-set + atomic close + the concurrency version-guard.
  Not built.
- **Auth / CSRF / target-validation / body-limit** on writes — designed (the "private authed surface"),
  currently **assumed, not enforced**.
- **Fleet front-end contract (#37)** — Jinja/Tabler/`/ux-catalog`; today the HTML is hand-rolled
  f-strings.

## Priority for *living the documentation* (highest leverage first)
1. **(B) the grill drain loop** — directing must round-trip, or the dashboard is read-only with a dead
   comment box. This is the heart of "living."
2. **(A) Briefing + Direction** — see the self-state and the steers; close the Voz→Direction loop
   visibly.
3. **(C) surface the docs + link Cortex nodes to their source** — the literal "live the documentation":
   glossary/ADRs as surfaces, and the graph wired into the read surfaces.
4. **(D) Cortex search / filter** — navigate the brain, not just stare at it.
5. **(E) lifecycle / auth / contract hardening** — robustness; lower priority for *experiencing* it,
   required before exposing it beyond localhost.

## Open question for the review
Is "living the documentation" satisfied by surfacing **the edge's runtime state** (Cortex, Artefatos,
Direction, Briefing, Voz round-trip), or does it also require surfacing **the design documents
themselves** (CONTEXT.md glossary, the ADRs, SURFACE.md) as first-class navigable pages? This audit
assumes **both** — section C — but the weighting between them is the operator's call.
