# edge — Surface

What each concept exposes to the mentee. Companion to `CONTEXT.md` (what words mean) and
`docs/frontend.md` (how to implement — the canonical front-end doc). Built via
`/pocock-grill-ux-with-docs`.

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
- **vote**: 👍/👎 under a publication; a **toggle, capped at 1** per mentee — clicking the active
  button clears it, the two are mutually exclusive. Appends `voz.vote {slug, value: 1 | -1 | 0, ts}`
  (`0` = cleared); the current vote folds **latest-wins** (single-tenant), not a running sum.
  Frictionless, no reply owed (the retention signal). Always targets a publication.
- **view thread** (per-publication): comment+reply thread renders under each post — fold by
  `target_ref = slug`.
- **view chat** (standalone): one chronological timeline of all `voz.comment` / `voz.reply` /
  `voz.clarify`, any target, each labelled with its post context when it has one — the same events,
  unfiltered fold.
- **view reply**: the edge's `voz.reply` renders inline under the comment it answers, in both views.
- **view clarification** (v1): a parked `voz.clarify` renders inline under its original chat as the
  edge's open question, flagged *awaiting your answer* — the same inline pattern as a reply, in both
  views.
- **answer a clarification** (v1): the mentee answers a parked chat with a **distinct child event**
  `voz.clarify_answer {clarify_id, body, ts}` — **not** a `voz.comment`, so it is **never a new
  Directive** and never enters `open_comments()` / the eligible set (this is what stops an answer from
  re-opening the backlog). The composer is pre-linked from the inline question. The grill fold reads
  the link: a parked chat *with* a `voz.clarify_answer` is **ready for terminal resolution** at the
  next grill (which consumes the answer atomically when it appends `voz.resolved`); *without* one it
  stays awaiting-clarification. So a parked Directive is answerable on its own thread, never
  rediscovered by heuristic association. [adversarial-review iter10 #2, iter12 #1]

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
  captures the **start cursor** (max event seq) + the **actionable set** (open `comment_id`s ≤ the
  cursor that are *not* parked-without-answer — see the Event-schema invariant), then loads a
  **harm-ranked batch within a max chats/tokens cap** — the *loaded batch*. It
  **asks the residual only where ambiguous** (evidence-first), **closes each loaded chat at its
  close** — terminal `voz.resolved` (idempotent, one per `comment_id`) or, when it asked and got no
  answer, a non-terminal `voz.clarify` that keeps the chat **open** — and folds the standing-worthy
  ones into **Direction** (a `set` steer with `origin_comment_id`). *Asking* is non-exhaustive
  (ambiguous only); *closing* is **exhaustive over the loaded batch** — every loaded chat is
  terminally resolved or visibly parked, **none silently dropped**. Everything not
  loaded (eligible chats the cap excluded, plus post-cursor arrivals) **stays open as overflow** for
  the next grill — never silently dropped nor falsely closed — and the backlog **surfaces in the
  Briefing health strip**. So coverage is bounded *by construction* (no unbounded context load). The
  per-chat close is **atomic**: `voz.reply` + `direction.*` + `voz.resolved` land in one idempotent
  `append_batch` keyed by `comment_id` + `grill_run_id`, so a crash leaves a chat fully resolved or
  fully open — never a re-folded or lost steer; a `folded-to-direction` (or `retired-direction`) whose
  `direction_id` has no matching `direction.set` (or `direction.dropped`) is flagged. The append carries an append-time **version guard** under the eventlog
  lock — it fails unless **no `voz.resolved` *or* `voz.clarify` for that `comment_id` has appeared
  since the grill's start cursor** (`unchanged_since(comment_id, start_cursor)`), so **concurrent
  grills can't double-close** a chat whether the first close *resolved or parked* it (the stale batch
  is dropped) — robust to this install's parallel operator/heartbeat dispatches; a duplicate
  `voz.resolved` is a
  health-strip error. No pin — the grill already has the loaded batch in front of it.
  [adversarial-review iter3 #1, iter5 #1, iter6 #1, iter7 #1]
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
  `addressed`-vs-`answered` question: the grill close writes a **terminal**
  `voz.resolved {comment_id, outcome: replied | folded-to-direction | retired-direction | acknowledged, direction_id?}` —
  or, when it asked and captured no answer, a **non-terminal** `voz.clarify {comment_id, question}`
  that **keeps the chat open** (an autonomous grill may only park, never fabricate `acknowledged`).
  A Direction folded from a Directive carries `origin_comment_id`. `open_comments()` keys on the
  **absence of a terminal `voz.resolved`** (parked chats stay open), not on `voz.reply` presence; a
  Directive stays visible until terminally resolved. "Did my steer land?" is auditable end-to-end —
  acted-on, replied, acknowledged, or still *unsettled*. [adversarial-review iter1 #2, iter9 #1]

Gaps:
- Affordance for a targeted comment shown in the chat to link back to its publication — TBD.
- Notification when an answer lands (v1: mentee re-reads; phase 2: poller / push).
- Auth *mechanism* (session cookie vs reverse-proxy basic-auth, as session-deck does) — unbound; the
  *requirement* is fixed, the mechanism is a build choice.

## Event schema — the normative Voz/Direction contract

The authoritative event list; the prose above must not contradict it. All append-only; everything is
a fold, no parallel store, `group_id`-scoped per install.

**Voz events**
- `voz.comment {target_ref?, comment_id, body, ts}` — a mentee Directive (general chat if `target_ref`
  null). The *only* event that opens a chat.
- `voz.vote {slug, value: 1 | -1 | 0, ts}` — answer-less retention signal; always targets a
  publication. A **toggle capped at 1** per mentee: folds **latest-wins** (single-tenant), `0` clears.
- `voz.reply {comment_id, body, ts}` — the edge's inline answer; **presentation only**, not lifecycle.
- `voz.clarify {comment_id, clarify_id, question, grill_run_id, ts}` — the grill parks an unsettled
  loaded chat; **non-terminal** (the chat stays open).
- `voz.clarify_answer {clarify_id, body, ts}` — the mentee's answer to a clarify; a **child event**,
  never a `voz.comment`, so it never opens a chat.
- `voz.resolved {comment_id, outcome: replied | folded-to-direction | retired-direction | acknowledged, direction_id?, grill_run_id, ts}`
  — the grill's **terminal** outcome; one per `comment_id`, idempotent, under an append-time
  **version guard** (`unchanged_since(comment_id, start_cursor)` — no `voz.resolved`/`voz.clarify`
  since the grill's start cursor). `direction_id` references the **`direction.set`**
  (`folded-to-direction`, incl. a proposed→set ratification) or the **`direction.dropped`**
  (`retired-direction`); absent for `replied` / `acknowledged`.

**Direction events** (tier-disjoint provenance)
- `direction.set {id, title, body, expires_at?, supersedes?, origin_comment_id?, ts}` — curated tier
  (Voz-only). A `folded-to-direction` Directive emits **this**, carrying `origin_comment_id`.
- `direction.proposed {id, title, body, expires_at?, title_generated?, from_artefato?, relates_to?, ts}`
  — candidate tier (artefato / grill achados). **Never** carries `origin_comment_id`.
- `title` is **required** on a new write (≤ 80 chars, one line) — the handle a reader lists by
  (#632). A Directive whose plan carries no usable title **parks** the chat asking for one; it never
  raises inside the atomic append and never lands body-only. `title_generated: true` marks a handle
  derived from the body by `tools/direction_backfill.py`, never one somebody authored.
- `expires_at` (ISO date/datetime; date-only is inclusive of that day) is the steer's declared end.
  Past it, the item leaves both tiers of the fold and `eventlog.expired_directions` lists it.
- `direction.dropped {id, origin_comment_id?, ts}` — retire a steer. Dropping a **`set`** is
  **Voz-only** and carries `origin_comment_id` (appended atomically with its `voz.resolved` when
  Directive-driven); a **non-Voz** actor (grill / artefato) may only **propose** a retirement via
  `direction.proposed` (`relates_to` the target), never drop a `set` directly.

**Invariants**
- **`open_comments()`** = `voz.comment`s with no terminal `voz.resolved` (a parked `voz.clarify` chat
  is still open; `voz.clarify_answer` and `voz.reply` never affect openness).
- **Actionable set** (what a grill may load) = open comments that are **either** not awaiting
  clarification **or** parked *with* a linked `voz.clarify_answer`. A **parked chat without an answer
  is open but NOT actionable** — held only in the awaiting-clarification health count, never
  re-loaded, so it cannot consume the cap every grill and starve fresh directives.
- **Coverage** = every chat in a grill's loaded batch (drawn from the **actionable** set) reaches
  `voz.resolved` (terminal) or `voz.clarify` (parked); un-loaded actionable + post-cursor chats are
  overflow.
- **Atomic close** = a chat's close events land in one `append_batch` keyed by `comment_id` +
  `grill_run_id`, under the **version guard** `unchanged_since(comment_id, start_cursor)` — fails if
  any `voz.resolved`/`voz.clarify` for the chat appeared since the grill's start cursor, so a stale
  concurrent grill's batch drops whether the first close resolved *or* parked the chat (crash- and
  concurrency-safe; `still_open` alone is insufficient since a parked chat is still open).
- **Provenance** = `origin_comment_id` rides only Voz-owned curated events (`direction.set` and a
  `set`-targeting `direction.dropped`); never on `direction.proposed`. A `voz.resolved` with
  `outcome=folded-to-direction` has `direction_id` → a `direction.set`; `outcome=retired-direction` →
  a `direction.dropped`; **both events carry the same `origin_comment_id`**. The consistency check
  validates create/promote and retire **symmetrically**: any `direction_id` with no matching event,
  or any Direction mutation (`set`/`dropped`) folded from a Directive without an `origin_comment_id`,
  is a health-strip error.
- **Retirement** = a `set` is retired only by a **Voz `direction.dropped`** (carrying
  `origin_comment_id`); non-Voz actors propose retirement as `direction.proposed` (`relates_to`),
  never drop a `set`. Create, promote, and retire all preserve the tier-disjoint, Voz-owns-curated
  model. [adversarial-review iter14 #1]

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
  Directive count, the **Voz overflow/backlog** (eligible chats the last grill's cap left un-loaded,
  waiting for the next grill), the **awaiting-clarification count** (parked `voz.clarify` chats), and
  **resolution-consistency errors** (a duplicate `voz.resolved`, or a `folded-to-direction` /
  `retired-direction` whose `direction_id` has no matching `direction.set` / `direction.dropped`). The
  degraded-mode signal a composed briefing cannot give.
  [adversarial-review iter1 #6, iter6 #1, iter8 #1, iter9 #1]

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
- **Provenance is non-deferred for v1, and tier-disjoint** (iter2 #1, iter12 #2). A **Direct Voz
  `folded-to-direction` always emits `direction.set`** (Voz-grade → curated, never the dim `proposed`
  tier) carrying `origin_comment_id`; `voz.resolved` carries that steer's `direction_id`. The
  `proposed` tier is for **non-Voz candidates only** (artefato / grill achados) and carries
  `from_artefato` / `relates_to`, **never `origin_comment_id`** — so the provenance fields are
  **disjoint by tier** and a folded Directive can never land as a non-curated item with no promotion
  owner. `set()` takes `origin_comment_id`; `propose()` keeps `from_artefato` / `relates_to`. The
  surface renders the link **bidirectionally** (steer ⇄ originating comment). The audit promise and
  its schema land together — no half-state.

## Cortex graph — surf the agent's brain

Type: **projeção navegável** (a fold of the Cortex graph; ADR-0005/0006). Roles: Mentee
(reads + navigates + **searches/filters** the graph, and **corrects an Earmarked node** via the Voz
rail), edge (writes the graph via extraction + grill curation). **The mentee never edits the graph** —
the one write affordance is the Earmarked node-targeted Voz **correction** (a Voz comment, not a graph
mutation; the write surface stays the Voz rail). So the surface is **navigate + a gated correction
write**, not read-only.

Postura: a **futuristic graph interface** — a dark, force-directed canvas where the **whole Cortex**
renders at once as a constellation **centered on space-0** (the identity root: method + personality),
the luminous core every other node hangs off. The mentee pans, zooms, and clicks to *navigate the
agent's brain*. The territory is the **whole Cortex**, not the salient subgraph (clusters are *not*
graph nodes — `Community` = 0; they live as rendered wiki pages, so they do not appear as
neighborhoods in v1). **This is not Recall**: Recall is the *agent's* wake-act, where the edge connects
with its own brain (the space-0-rooted salient subgraph, auto-served at pre-dispatch). This is the
**mentee** freely **surfing** the same graph, on demand — with **search + filter** (shipped, Slice 6)
to find the way through it and a **gated correction** on an Earmarked node (shipped, Slice 6b) —
**one brain, two surfers** (#35, #28).

Operations:
- **surf** (v1): freely navigate the whole Cortex — pan / zoom / click a node to expand its
  neighborhood. The mentee drives the traversal (not the agent's auto-served subgraph). **This is
  the v1 surface.**
- **inspect node** (v1): click a node → its content; artifact retrieval = traverse to the reference
  node and fetch the blob (per CONTEXT.md, *Cortex*).
- **search** (shipped, Slice 6): find a node directly and jump to it, then surf from there. It is a
  **find-and-jump locator** — a deterministic substring match over the loaded payload's title / type /
  id / stable ref — **NOT semantic retrieval** (the banned-fetch posture the Cortex glossary bans
  stays explicit: no embedding/fetch, only locate-and-center over what is already loaded).
- **filter** (shipped, Slice 6): narrow the graph to navigate it better — by node **type** (the trust
  classes), **Earmarked-only**, or **recency** — recomputed purely from the one loaded payload (no
  re-query, no stale hidden state). Deterministic, client-side over the loaded fold.
- **correct an Earmarked node** (shipped, Slice 6b): an Earmarked (harm-bearing) node carries a
  **correction composer** — node-targeted Voz. `POST /cortex/<node_id>/comment` writes a `voz.comment`
  whose `target_ref` is the **node ref** (`node:<id>`), through the same canonical append + the Slice-1
  auth/CSRF/origin gate. **Fail-closed node-ref validation** (the ref must be a node present in the
  `group_id`-scoped payload **and** Earmarked — an inert or forged node ref rejects, no append),
  **idempotent nonce** (a double-submit/retry dedupes to one Directive), **same-origin** fetch. The
  drain folds it like any Directive (`direction.set` carrying `origin_comment_id`; the node
  `target_ref` is the provenance). This is the mentee's **only** write affordance on the Cortex — a Voz
  comment, **not** a graph mutation.

Decisions:
- **Same Cortex, two surfers.** v1 exposes the *same* graph — not a mentee-specific projection. The
  agent reads it via **Recall** (auto-served salient subgraph, at wake); the mentee reads it via
  **free surf** (the dashboard, on demand, the whole graph; with search + filter, Slice 6). One brain,
  two read-surfaces;
  a parallel mentee-graph would be a second store, the failure log-native physics deletes.
- **The mentee navigates + corrects, never edits the graph.** The mentee surfs, searches, filters,
  and **corrects an Earmarked node** (Slice 6b) — but the correction is a **Voz comment**, not a graph
  write. Only the edge writes the graph (extraction + grill curation). The mentee's write surface stays
  the Voz rail — two different surfaces on one substrate. So the surface is **not read-only**: it is
  read + navigate + a single gated correction affordance, all of which leave the graph itself
  edge-owned.
- **A JS island, never the app shell** (docs/frontend.md): a graph lib (Cytoscape / vis-network) loaded
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
- **"Whole graph" means the whole Cortex *for this install group* — `group_id`-scoped, fail-closed.**
  The server resolves the current install `group_id` and **fails dark if it is absent** (never a
  graph-wide `MATCH`); every node *and* both endpoints of every edge in the query are constrained to
  that `group_id`. This is **load-bearing on a shared neo4j**: the fleet co-locates installs in one
  instance keyed by `group_id` (roberto + petertosh share one), so an unscoped query would leak
  another install's brain into this dashboard — and it would render as a *successful* graph, not an
  obvious failure. Cross-install isolation is the `group_id`, enforced at the query, not assumed.
  [adversarial-review iter11 #1]
- **Earmarked overrides the dim — harm-surfacing beats trust-dimming.** Trust-dimming pushes
  low-trust nodes into the haze, which would **bury the Earmarked** (the harm-bearing subset the
  mentee most needs to correct) — backwards for a correction surface. So in v1 the **Earmarked is a
  first-class overlay**: a harm highlight, never dimmed, regardless of trust tier. Trust sets
  brightness for the *inert* mass; **harm overrides it** for the Earmarked. The overlay surfaces the
  harm frontier so it isn't buried; **correcting an Earmarked node is now shipped (Slice 6b) as
  node-targeted Voz** — a `target_ref` addressing the Earmarked node directly (`node:<id>`, beyond
  slugs), `POST /cortex/<node_id>/comment` through the Slice-1 auth/CSRF gate, fail-closed node-ref
  validation (present in the scoped payload **and** Earmarked), idempotent nonce. The correction is a
  **Voz comment that folds into a Directive** (`origin_comment_id` provenance), **not** a graph
  mutation — so the harm frontier is both surfaced **and** correctable without the mentee ever editing
  the graph. [adversarial-review iter1 #5, iter2 #4]

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
- **Filter taxonomy + UX** (the "navigate it better" set) — **shipped (Slice 6):** type / Earmarked /
  recency, client-side over the loaded payload. Further axes (cluster, Artefato/Direction) are
  candidates beyond the current set.
- **Earmarked corrective write-path** — **shipped (Slice 6b):** surfacing the Earmarked is v1
  (overlay), and the *write* path (node-targeted Voz, `target_ref` beyond slugs) is now closed — see
  the Operations + Earmarked decision above.

Next direction (R1, settled — the v-next, not yet built):
- **A 3D "navigate the brain" cloud replaces the 2D island.** The 2D Cytoscape constellation becomes a
  dark, luminous, **trust-weighted 3D force-directed cloud** (`3d-force-graph` = three.js + d3-force-3d,
  one self-hosted UMD bundle on the `/cortex` island only — the heavy lib never touches the read-mostly
  shell). Trust stays the sole size+brightness axis (space-0 brightest core → Episodic faintest haze);
  per-tier edges and the Earmarked red overlay survive the port. Camera = orbit + zoom + pan; **nodes
  are not draggable and graph mutation stays edge-owned, but the Slice-6b node-targeted Voz correction
  affordance survives the 3D port** (the surface stays navigate + the gated correction, never reverted
  to a read-only cloud). The cheap-on-resources constraint is amended **for this island specifically**
  to accept the bundle weight (`docs/frontend.md` R1 amendment); it stands everywhere else.
- **The 2D Cytoscape island is retained as the required WebGL fallback (M21), not deleted.** The render
  degrades on a strict hierarchy: **WebGL → 3D cloud, else the 2D Cytoscape island auto-renders, else a
  searchable list, else the honest message.** This is a release gate (a WebGL-incapable client still
  navigates the Cortex), distinct from fail-dark (M16, which is for *absent* graph data, not an
  unsupported renderer).
