# edge — Surface

What each concept exposes to the mentee. Companion to `CONTEXT.md` (what words mean) and
`FRONTEND.md` (how to implement). Built via `/pocock-grill-ux-with-docs`.

## Directives

- **Tipo**: Personal operational dashboard — single-tenant, self-hosted. The mentee's private
  window onto their edge: read its work (Artefatos, Direction, state) and direct it (Voz). Not a SaaS.
- **Audiência**: The **Mentee** — one trusted, technical/semi-technical person (PM-builder). Single
  role, private authed surface; no anonymous or multi-user access.
- **Postura**: Dense, operational, low-ceremony. Information-rich projections of the event log and
  graph; the edge's voice — direct, technical, skeptical. No marketing chrome.
- **Dispositivo**: Desktop-first (read-and-direct at a keyboard). Mobile / on-the-go reach is a
  *different Medium* (Telegram, phase 2), not the dashboard's responsibility.
- **Multi-tenant**: No. One install = one mentee = one tenant (isolated by `group_id`). No
  per-tenant navigation, isolation, or branding.

_Derived from CONTEXT.md (Mentee, Install) and ADR-0017's v1 scope; not separately confirmed._

## Voz rail — comments, votes, chat

Type: **evento** (immutable `voz.*` log events; the rail is append-only). Addressed/answered is
**valor_derivado** (a fold). Roles: Mentee (write + read), edge (replies only).

Operations:
- **comment** (create a Directive): comment box under a publication *and* in the standalone chat;
  appends `voz.comment {target_ref?, comment_id, body, ts}`. Owes an edge reply → the answer queue.
- **vote**: 👍/👎 under a publication; appends `voz.vote {slug, value:±1, ts}`. Frictionless, no
  reply owed (the retention signal). Always targets a publication.
- **view thread** (per-publication): comment+reply thread renders under each post — fold by
  `target_ref = slug`.
- **view chat** (standalone): one chronological timeline of all `voz.comment` / `voz.reply`, any
  target, each labelled with its post context when it has one — the same events, unfiltered fold.
- **view reply**: the edge's `voz.reply` renders inline under the comment it answers, in both views.

Decisions:
- Per-publication comments and the standalone chat are **NOT two mediums** — they are two
  **projections of one `voz.*` stream**, keyed by an optional `target_ref` (per-publication =
  filter by slug; chat = unfiltered timeline). One write path, one answer queue, two views. Reason:
  the mentee's "they are not so different" is literally true log-native, and it avoids a parallel
  store — the #1 dashboard failure.
- A standalone-chat message is a comment with `target_ref = null` — a general Directive, still owes
  a reply.
- Votes require a target (you vote *on* something); comments may be targeted or general.
- **The grill resolves whole chats; no pin, no per-Directive FIFO.** Every *open* mentee↔edge chat
  is **earmarked**, so the grill loads **all** of them into context. It **asks the residual only
  where ambiguous** (evidence-first), **marks every open chat solved at its close** (coverage), and
  folds the standing-worthy ones into **Direction** (a `set` steer). So earmark = full context;
  *asking* is non-exhaustive (ambiguous only), *solving* is exhaustive (all marked solved). No pin —
  the grill already has every open chat in front of it.

Gaps:
- Affordance for a targeted comment shown in the chat to link back to its publication — TBD.
- Notification when an answer lands (v1: mentee re-reads; phase 2: poller / push).

## Cortex graph — surf the agent's brain

Type: **projeção navegável** (a read-only fold of the Cortex graph; ADR-0005/0006). Roles: Mentee
(read + navigate only), edge (writes the graph via extraction + grill curation — the mentee never
edits it; the write surface stays the Voz rail).

Postura: a **futuristic graph interface** — a dark, force-directed canvas where the Cortex renders
as a constellation: **space-0** (the identity root: method + personality) as the luminous core,
knowledge clusters as neighborhoods, and Artefatos / Direction / the Mundo·Atividade·**Self**
relations as nodes, edges as synapses. The mentee pans, zooms, and clicks to *navigate the agent's
brain* — expanding a node's neighborhood on click. The territory is the **whole Cortex**, not the
salient subgraph. **This is not Recall**: Recall is the *agent's* wake-act, where the edge connects
with its own brain (the space-0-rooted salient subgraph, auto-served at pre-dispatch). This is the
**mentee** freely **searching and surfing** the same graph, read-only, on demand — **one brain, two
surfers** (#35, #28).

Operations:
- **surf** (v1): freely navigate the whole Cortex — pan / zoom / click a node to expand its
  neighborhood. The mentee drives the traversal (not the agent's auto-served subgraph).
- **search** (v1): find a node directly and jump to it — the mentee's own entry into the graph,
  distinct from the briefing-seeded entry the *agent* gets at wake.
- **inspect node** (v1): click a node → its content; artifact retrieval = traverse to the reference
  node and fetch the blob (per CONTEXT.md, *Cortex*).
- **filter** (future): the mentee composes filters to navigate it better — by node type
  (Mundo / Atividade / Self, cluster, Artefato, Direction), recency, or salience/earmarked. Deferred;
  v1 ships the unfiltered navigable graph.

Decisions:
- **Same Cortex, two surfers.** v1 exposes the *same* graph — not a mentee-specific projection. The
  agent reads it via **Recall** (auto-served salient subgraph, at wake); the mentee reads it via
  **free search + surf** (the dashboard, on demand, the whole graph). One brain, two read-surfaces;
  a parallel mentee-graph would be a second store, the failure log-native physics deletes.
- **Read-only for the mentee.** The mentee navigates; only the edge writes the graph. The mentee's
  write surface stays the Voz rail — two different surfaces on one substrate.
- **A JS island, never the app shell** (FRONTEND.md): a graph lib (Cytoscape / vis-network) loaded
  *only* on this view; the rest of the dashboard stays server-rendered htmx. Honors the hard
  "cheap on resources" constraint — the heavy lib never touches the read-mostly pages.

Gaps:
- **Filter taxonomy + UX** (the "navigate it better" set) — deferred to a future increment, not
  specced. The axes above are candidates, not decided.
- **Initial viewport**: where free surf lands first — whole-graph overview vs space-0 as natural
  center vs blank-until-search. TBD (not recall-seeded — that salient entry is the *agent's*, not
  the mentee's).
- **Node/edge vocabulary** actually rendered (which Cortex node types + relations surface, and their
  visual encoding) — TBD; depends on #28's espinha + embed landing.
- **Live vs snapshot**: does the view re-fold per request (log-native) or read a graph snapshot for
  pan/zoom performance? TBD — bears on the "cheap" constraint at graph scale.
