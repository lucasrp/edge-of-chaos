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
**valor_derivado** (a fold over the explicit outcome event `voz.resolved`, *not* over `voz.reply`
presence — see iter1 #2). Roles: Mentee (write + read), edge (replies only).

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
- **The grill resolves a loaded batch of chats; no pin, no per-Directive FIFO.** At start the grill
  captures the **start cursor** (max event seq) + the **eligible set** (open `comment_id`s as of that
  cursor), then loads a **harm-ranked batch within a max chats/tokens cap** — the *loaded batch*. It
  **asks the residual only where ambiguous** (evidence-first), **resolves exactly the loaded batch at
  its close** (`voz.resolved`, idempotent, one per `comment_id`), and folds the standing-worthy ones
  into **Direction** (a `set` steer with `origin_comment_id`). *Asking* is non-exhaustive (ambiguous
  only); *solving* is **exhaustive over the loaded batch** — no loaded chat survives. Everything not
  loaded (eligible chats the cap excluded, plus post-cursor arrivals) **stays open as overflow** for
  the next grill — never silently dropped nor falsely closed — and the backlog **surfaces in the
  Briefing health strip**. So coverage is bounded *by construction* (no unbounded context load). No
  pin — the grill already has the loaded batch in front of it. [adversarial-review iter3 #1, iter5 #1, iter6 #1]
- **Writes are authenticated, validated, bounded (hard v1 requirement).** The "private authed
  surface" is *enforced, not assumed*: every `voz.*` write route sits behind dashboard auth, with
  CSRF/origin protection, a body-size limit, and `target_ref` validation (reject votes/comments for
  slugs absent from the published fold). Rationale: `voz.*` are high-priority inputs the grill must
  resolve and votes drive retention — an unauthenticated write is **log poisoning**, not a comment.
  [adversarial-review iter1 #1]
- **Writes go through the canonical `eventlog` append, never a hand-rolled one.** Seq assignment +
  append use `tools/eventlog`'s locked primitive with an idempotency key (dedupe double-clicks /
  retries) — not scan-for-max-seq-then-append (a race that forges duplicate seqs in the source of
  truth). [adversarial-review iter1 #3]
- **A Directive's outcome is recorded, not inferred from reply-absence.** Resolves the long-open
  `addressed`-vs-`answered` question: the grill close writes an explicit
  `voz.resolved {comment_id, outcome: replied | folded-to-direction | acknowledged, direction_id?}`,
  and a Direction folded from a Directive carries `origin_comment_id`. `open_comments()` keys on the
  **outcome event, not on `voz.reply` presence**; a Directive stays visible until its outcome is on
  the log. "Did my steer land?" becomes auditable end-to-end. [adversarial-review iter1 #2]

Gaps:
- Affordance for a targeted comment shown in the chat to link back to its publication — TBD.
- Notification when an answer lands (v1: mentee re-reads; phase 2: poller / push).
- Auth *mechanism* (session cookie vs reverse-proxy basic-auth, as session-deck does) — unbound; the
  *requirement* is fixed, the mechanism is a build choice.

## Read-side surfaces — one coherent set

The mentee's window is **one navigation**, each surface a fold/projection of the log + graph (no
parallel store): **Briefing** (self-state landing) → **Direction** (steers, drill-down) → **Blog**
(Artefatos, the work feed) → **Cortex graph** (explore the brain). The **Voz rail** is the write-side,
threaded across them. Decided this session: the **briefing subsumes a separate "state" page**, and
**Direction is a drill-down off the briefing** — not three overlapping pages. Built today: Blog +
Voz rail. To build: Briefing, Direction, Cortex graph.

## Briefing — the self-state landing

Type: **projeção** (reuses `tools/briefing.py::compose_briefing` — the *same* text the edge wakes to).
Roles: Mentee (read). The mentee sees the agent's literal wake-state: curated Direction, open bets,
corpus head, knowledge clusters, source orientation.

Operations:
- **view briefing** (v1): render the composed wake-briefing. No new fold — calls `compose_briefing`.
- **read-model health strip** (v1): a compact objective-state band above the briefing — last
  dispatch, last assemble/grill, log cursor, extraction/sweep errors, graph reachability, open
  Directive count, and the **Voz overflow/backlog** (eligible chats the last grill's cap left
  un-loaded, waiting for the next grill). The degraded-mode signal a composed briefing cannot give.
  [adversarial-review iter1 #6, iter6 #1]

Decisions:
- **Subsumes the *composed* state, not the *health* of the folds.** The briefing is the human-readable
  self-state — but a composed briefing can read plausible while the folds beneath it are stale or
  failing (observed at a real wake: the sweep degraded to `swept_sessions: 0` on a context-window
  overflow, yet the briefing composed clean). So the landing carries a thin **read-model health
  strip** (above); there is still no separate *raw-state* page. [adversarial-review iter1 #6]
- **Reuses the wake artifact.** What the mentee reads is exactly what the edge wakes to — no
  mentee-specific recomposition, no drift.

## Direction — the steers (drill-down)

Type: **projeção** (fold of `direction.*` → two tiers, via `eventlog.direction_at`). Roles: Mentee
(read), edge (writes via grill/Voz). A focused drill-down off the **Briefing**, distinct from the
**Cortex graph** (status-scanning your steers ≠ exploring a constellation).

Operations:
- **view Direction** (v1): the two tiers — **set** (curated, Voz-only — the active steers) and
  **proposed** (candidates awaiting the grill). Curated prominent, proposed dimmer (same trust-
  language as the Cortex graph).

Decisions:
- **Dedicated surface, not subsumed by the graph.** The affordance differs: Direction answers "what
  is the edge steering toward, did my steer land?" — a scannable list, not graph exploration.
- **Provenance is non-deferred for v1** (adversarial-review iter2 #1 — it was contradictorily both
  *required* by the Voz-rail outcome decision and *deferred* here). The event model gains:
  `direction.set` / `direction.proposed` carry `origin_comment_id` when folded from a Directive, and
  `voz.resolved` carries `direction_id` for the `folded-to-direction` outcome; `propose()` / `set()`
  take the new param. The surface renders the link **bidirectionally** (steer ⇄ originating comment).
  The audit promise and its schema land together — no half-state.

## Cortex graph — surf the agent's brain

Type: **projeção navegável** (a read-only fold of the Cortex graph; ADR-0005/0006). Roles: Mentee
(read + navigate only), edge (writes the graph via extraction + grill curation — the mentee never
edits it; the write surface stays the Voz rail).

Postura: a **futuristic graph interface** — a dark, force-directed canvas where the **whole Cortex**
renders at once as a constellation **centered on space-0** (the identity root: method + personality),
the luminous core every other node hangs off. The mentee pans, zooms, and clicks to *navigate the
agent's brain*. The territory is the **whole Cortex**, not the salient subgraph (clusters are *not*
graph nodes — `Community` = 0; they live as rendered wiki pages, so they do not appear as
neighborhoods in v1). **This is not Recall**: Recall is the *agent's* wake-act, where the edge connects
with its own brain (the space-0-rooted salient subgraph, auto-served at pre-dispatch). This is the
**mentee** freely **surfing** the same graph, read-only, on demand (search is a later affordance) —
**one brain, two surfers** (#35, #28).

Operations:
- **surf** (v1): freely navigate the whole Cortex — pan / zoom / click a node to expand its
  neighborhood. The mentee drives the traversal (not the agent's auto-served subgraph). **This is
  the v1 surface.**
- **inspect node** (v1): click a node → its content; artifact retrieval = traverse to the reference
  node and fetch the blob (per CONTEXT.md, *Cortex*).
- **search** (future): find a node directly and jump to it, then surf from there. Deferred — surf is
  the v1 act. Open when built: **find-and-jump locator** vs **semantic retrieval** (the latter
  reintroduces the fetch posture the Cortex glossary bans).
- **filter** (future): narrow the graph to navigate it better — by node type (Mundo / Atividade /
  Self, cluster, Artefato, Direction), recency, or salience/earmarked. Deferred; v1 ships the
  unfiltered navigable graph.

Decisions:
- **Same Cortex, two surfers.** v1 exposes the *same* graph — not a mentee-specific projection. The
  agent reads it via **Recall** (auto-served salient subgraph, at wake); the mentee reads it via
  **free surf** (the dashboard, on demand, the whole graph; search a later affordance). One brain,
  two read-surfaces;
  a parallel mentee-graph would be a second store, the failure log-native physics deletes.
- **Read-only for the mentee.** The mentee navigates; only the edge writes the graph. The mentee's
  write surface stays the Voz rail — two different surfaces on one substrate.
- **A JS island, never the app shell** (FRONTEND.md): a graph lib (Cytoscape / vis-network) loaded
  *only* on this view; the rest of the dashboard stays server-rendered htmx. Honors the hard
  "cheap on resources" constraint — the heavy lib never touches the read-mostly pages.
- **Whole graph, centered on space-0 — then simplify.** v1 renders the *entire* Cortex at once,
  space-0 as the gravitational core — *not* a spine-first skeleton that expands on demand. The
  legibility work is **subtractive** (declutter the hairball: visual hierarchy, trust-dimming,
  layout) — never **additive** (withhold then reveal). Rationale (operator, this session): seeing
  the whole brain is the point; simplify the view, don't hide it.
- **Trust-weighted brightness is the primary simplification axis.** Render everything, but weight
  opacity/brightness by trust + role: **space-0** brightest → asserted spine (`Objective`,
  `Direction`, `Artefato`) bright, solid edges → extracted `Entity` / `Source` dim → `Episodic`
  faintest (background haze). The curated mind pops, the hypothesis cloud recedes — subtractive
  legibility via *opacity*, not removal (honors whole-then-simplify), and glossary-mandated
  ("trust is legible per edge"). Doubles as the futuristic aesthetic: a glowing core on a faint
  nebula. Chosen over recency or importance/Earmarked as the *primary* axis.
- **Live fold per request, client-side navigation.** On page load the server runs one Cypher query
  for the whole graph and ships a JSON payload to the island once; pan / zoom / click is client-side,
  no re-query. Always fresh, server authoritative, no snapshot store. The render payload is *not* the
  forbidden "parallel client store" (that failure mode is *persistent* divergent state; a per-load
  payload can't diverge). Revisit only if scale makes the query or payload hurt — then pagination /
  snapshot, measured, not pre-optimized.
- **Earmarked overrides the dim — harm-surfacing beats trust-dimming.** Trust-dimming pushes
  low-trust nodes into the haze, which would **bury the Earmarked** (the harm-bearing subset the
  mentee most needs to correct) — backwards for a correction surface. So in v1 the **Earmarked is a
  first-class overlay**: a harm highlight, never dimmed, regardless of trust tier. Trust sets
  brightness for the *inert* mass; **harm overrides it** for the Earmarked. **The v1 overlay is
  read-only awareness** — it surfaces the harm frontier so it isn't buried, consistent with the
  Cortex graph being read-only for the mentee; correcting an Earmarked item still goes through the
  existing Voz rail (on the relevant publication / via the grill). **Node-targeted Voz** (a
  `target_ref` addressing an Earmarked node directly, beyond slugs) is an explicit *future*
  increment — so v1 does not ship a correction surface it cannot structurally back.
  [adversarial-review iter1 #5, iter2 #4]

Node/edge vocabulary (live, group `edge-next` — the real shape, not #28-speculative):
- **Asserted spine (the curated Self, ~55 nodes, *faithful*):** `Genesis` (space-0, 1), `Objective`
  (1), `Direction` (41), `Artefato` (12); edges `GROUNDS` / `ANCHORS` / `SERVES` / `PROPOSES` /
  `DISTILLS` / `CITES`.
- **Extracted layer (Graphiti, *hypothesis*, the bulk ~163 nodes):** `Entity` (72), `Episodic` (91,
  = *Atividade*), `Source` (50, = *Mundo*); edges `MENTIONS` (196), `RELATES_TO` (64).
- `Community` / `Saga` = 0 (not materialized).

Gaps:
- **Secondary simplification levers** (primary = trust-weighted brightness, decided): if the faint
  `Episodic` haze is still too heavy at ~268 nodes, collapse Episodics into their `MENTIONS` parent;
  edge bundling; level-of-detail on zoom. Try opacity first, measure before adding. Candidates.
- **Filter taxonomy + UX** (the "navigate it better" set) — deferred to a future increment.
- **Earmarked corrective write-path** — surfacing the Earmarked is now v1 (overlay, decided above);
  the *write* path (Voz targeting an Earmarked node, `target_ref` beyond slugs) is the open bridge.
