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
