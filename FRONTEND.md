# edge — Frontend

How the dashboard front-end is built. Companion to `SURFACE.md` (what to expose) and `CONTEXT.md`
(what words mean). UX decisions are challenged against these constraints.

## Stack

- **Server-rendered HTML on Flask.** Every page is a **projection of the event log** (ADR-0005/0006):
  the server folds the log (and graph) into HTML at request time — no parallel client store, no
  build step. Slice 1 (branch `feat/dashboard-blog-feedback`) already does this: the index folds
  `artefato.published` + `intent.kernel`.
- **htmx for interactivity, not a SPA.** Posting a comment/vote, seeing answered/voted state,
  rendering replies — fragment swaps + polling (or SSE). Progressive enhancement over
  server-rendered HTML; the server stays authoritative.
- **JS islands only where a view is inherently interactive.** The future graph navigator
  (pan / zoom / click nodes) is a small graph library (e.g. Cytoscape or vis-network) embedded in a
  server-rendered page — an *island*, never an app shell.

## Hard constraint — cheap on resources

No heavy client framework. **A React/SPA bundle — the 1–3 GB `node_modules`, the multi-MB ship — is
out**; an OSS install must not pay that to read its own edge. Footprint stays: Python + Flask + a
stylesheet + htmx (~14 KB) + one graph lib loaded *only* on the graph view. Rich interface, light
shoes.

## Why (the trade-off)

A SPA buys richer client interactivity at the cost of a build pipeline, a parallel client-state
model (the #1 dashboard failure log-native physics exists to delete), and a heavy install. For a
single-user, read-mostly operational dashboard whose pages are log projections, htmx + islands give
the richness — including graph navigation — without any of that cost. The ceiling: if one view ever
needs live-collab or heavy local state, *that view* becomes an island; the app shell never does.
