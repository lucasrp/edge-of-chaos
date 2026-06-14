# Direct Voz is a strong guide the grill resolves, not a real-time interrupt

## Status

accepted

A two-way **Medium** can carry a **Directive** (the direct tier of **Voz**) addressed to the edge.
We deliberately do **not** build the ideal — a non-LLM deterministic poller that checks the
order-bearing Medium every few minutes and interrupts. For now (simplicity first): the **Voz rail**
is one append-only `voz.*` event stream, and a **Directive** is a **strong guide, not a real-time
order** — epistemically Voz-grade, operationally non-preempting. It is **resolved by the grill**,
not by jumping the beat queue.

The unit of resolution is the **chat** (a mentee↔edge exchange on the rail — a comment and the
replies under it), not the individual message and not a global FIFO position. An **open chat** is
one whose mentee comment has **no `voz.resolved` outcome yet** (the `open_comments()` fold = comments
lacking a `voz.resolved`; `voz.reply` is **presentation only** — the inline answer the dashboard
renders — never the lifecycle state). Resolution is **bounded by a loaded batch**, not a close-all. At its start the grill captures the
**start cursor** (max event seq) and the **actionable set** — the open `comment_id`s ≤ that cursor
that are **not parked-without-answer** (a parked `voz.clarify` chat re-enters the actionable set only
once its `voz.clarify_answer` lands; until then it lives in the awaiting-clarification health count
and is **never re-loaded**, so it can't consume the cap every grill and starve fresh directives).
It then loads a **deterministic harm-ranked batch** of the actionable set **within a max (chats /
tokens) cap** — the *loaded batch*. From that loaded context the grill:

- **asks the residual only where ambiguous** — evidence-first, **non-exhaustive**: it questions the
  mentee only on the loaded chats the context cannot settle;
- **closes each loaded chat to a terminal *or* a parked state** — **coverage over the loaded batch**:
  at close every loaded comment reaches exactly one of — **terminally resolved** (`voz.resolved`,
  idempotent, one per `comment_id`) **or parked awaiting-clarification** (`voz.clarify {comment_id,
  clarify_id, question, grill_run_id}`) when the grill had to ask but captured no answer. A **parked chat stays
  open** (non-terminal — `open_comments()` still lists it, flagged *awaiting-clarification*) and is
  terminally resolved only once a later grill captures the answer; an **autonomous / non-interactive
  grill may only park, never fabricate** a terminal `acknowledged` for an unanswered ambiguous chat
  (else unsettled high-priority Voz would silently vanish). So **no loaded chat is silently dropped**:
  each is terminal or visibly parked. Everything *not* loaded — eligible comments the cap excluded,
  plus any comment arriving after the start cursor — **stays open as overflow** for the next grill.
  The overflow, backlog, and awaiting-clarification counts **surface in the Briefing read-model-health
  strip**. This bounds the grill against the same context-window overflow seen at a real wake (the
  digestion sweep), by construction; [adversarial-review iter9 #1]
- **folds the standing-worthy ones into Direction** — a loaded chat that moves strategy becomes a
  `set` steer (carrying `origin_comment_id`); the rest are answered and closed.
- **the close is atomic per loaded chat** — a chat's close events (`voz.reply`, `direction.*` steer
  with `origin_comment_id` / `direction_id`, and its terminal `voz.resolved` **or** non-terminal
  `voz.clarify`) land in **one idempotent `append_batch`** keyed by `comment_id` + `grill_run_id`. A crash mid-close leaves a chat **fully resolved or fully
  open, never half** — no `direction.set`-without-`voz.resolved` (which would re-fold the steer next
  grill) and no `voz.resolved`-without-Direction (a lost steer / broken audit link); a retry replays
  the identical planned batch. A `folded-to-direction` whose `direction_id` has no matching Direction
  event is **flagged in the fold / health strip** (consistency check). The batch also carries an
  append-time **precondition `still_open(comment_id)`** checked under the eventlog lock — so two
  concurrent grills (distinct `grill_run_id`s, e.g. a manual `/ed-grill` racing a heartbeat dispatch,
  the parallel-dispatch reality this install already lives with) that loaded the same comment
  **cannot both close it**: the second's precondition fails and its batch is dropped (the chat was
  already resolved). Duplicate / conflicting `voz.resolved` for one `comment_id` is a **fold /
  health-strip error**, never a silent overwrite. [adversarial-review iter7 #1, iter8 #1]

So *earmark = eligible-set context*; **asking is non-exhaustive (ambiguous only), solving is exhaustive
over the loaded batch (every loaded chat resolved; overflow carried forward)**. There is **no pin** —
the grill already has the loaded batch in front of it — and
**no per-Directive FIFO / beat-drain**: the beat does not jump its round-robin for a Directive. The
edge's answer is a `voz.reply` event the **dashboard renders inline** ("agent responds next beat") —
no external outbound send is required (the dashboard projecting the log *is* the return path).

A Directive's frictionless, answer-less sibling is a **Vote** (`voz.vote {slug, value: ±1}`): the
retention signal, owing no reply, always targeting a publication.

## Scope (v1)

v1 ships **two native Mediums**:

- **Claude Code — native, low-tier.** Conversational but order-less *to edge*: its content is
  **gathered Voz (context only)**, never a Directive. The mentee's sessions are long and full of
  directives aimed at the *coding agent*; edge **must never read them as orders to itself** (it
  corrupts everything) and **owes no reply** (Claude Code already answered). Claude Code is
  **uniformly** low-tier — edge never extracts a Directive from it, even from a session that was in
  fact addressed to edge: per-turn classification is the risky guess we refuse (CONTRACT C5).
  Configured natively, outside the install YAMLs.
- **The dashboard's Voz rail — native, two-way, order-bearing to edge.** The dashboard's *first
  use* (edge-next), resurrecting the legacy async chat but **log-native**: one `voz.*` stream keyed
  by an optional `target_ref` (the artefato slug), surfaced as two projections of the *same* events
  — **per-publication comments** (fold by slug) and a **standalone chat** (unfiltered timeline). A
  mentee comment is a **Directive**, and edge's answer (`voz.reply`) is an event the dashboard
  renders — **no external outbound send required**. Trust is the dashboard's own (the mentee's
  private, authed surface — a single trusted author), so order-bearing-to-edge is safe without
  per-message authentication.

**Phase 2:** external order-bearing Mediums (Telegram / Slack, declared in the install config, each
needing real outbound send), the every-few-minutes deterministic poller, and topology beyond
private 1:1 (human-hub fan-in, shared room).

## Consequences

- **Latency up to one grill** before a Directive is acknowledged — **more under sustained backlog**,
  where overflow waits for a later grill (the backlog count surfaces in the Briefing health strip).
  The deferred deterministic poller is the documented path to close this gap when it is needed.
- **Resolution is by chat, not by message.** The grill does not drain a queue oldest-first; it loads
  a **harm-ranked batch** of the start-cursor eligible set within a max chats/tokens cap and brings
  each chat in that **loaded batch** to a **terminal-or-parked** outcome in one pass. Coverage is the
  invariant — **every loaded chat is terminally resolved (`voz.resolved`) or parked
  (`voz.clarify`)**; a **parked chat stays open** (awaiting clarification) and **may outlive the
  grill** until its linked answer is captured and a terminal `voz.resolved` is appended. Eligible
  chats the cap excluded, and any arriving after the start cursor, stay open as overflow for a later
  grill (all visible in the Briefing health strip).
- **The answer travels back out through the Medium** — for the Voz rail that path is the dashboard
  rendering the `voz.reply` event; no separate outbound send. A Directive can only ride a **two-way**
  Medium precisely because a one-way pipe cannot carry the answer back.
- **"The moment does not jump the queue" (Beat) still holds for the *world*** (delta / hot events).
  Mentee Directives do not preempt the beat either — they wait for the grill, which is where every
  promotion happens (ADR-0012-compatible: the beat stays a pure round-robin scheduler; resolution is
  the grill's, not a beat rule).
- **Open / solved is a fold over the log**, not a mutable flag — `open_comments()` derives from the
  absence of a **`voz.resolved`** (not `voz.reply`, which is presentation only), consistent with the
  event-sourced model (ADR-0005/0006). No parallel store.

## Considered and deferred

- **Real-time deterministic poller** (every few minutes; interrupt on an open higher-tier Voz chat):
  the ideal for true back-and-forth latency. Deferred for simplicity.
- **A per-Directive FIFO drain at beat-open**, with separate **addressed** (acted-on) vs **answered**
  (replied) states: the earlier design. **Superseded** — the grill resolves whole chats from full
  context (coverage at its close), which removes the queue, the FIFO rule, the pin, and the
  two-state bookkeeping. Whether "solved" should still distinguish *acted-on* from *replied* is an
  **open question** (see below).
- **Harm-ranked drain** instead of FIFO: **adopted for batch selection** — when the eligible set
  exceeds the cap, the loaded batch is chosen harm-ranked (FIFO would resolve trivia while a high-harm
  Directive overflows). Within a loaded batch the grill solves exhaustively; FIFO ordering is moot.

## Resolution — the outcome is recorded, not inferred (adversarial-review iter1 #2)

The earlier **open question** — does "solved" collapse **addressed** (edge acted on it) vs
**answered** (edge replied)? — is resolved by *recording the outcome explicitly* rather than
inferring "solved" from reply-absence. An adversarial review surfaced the failure mode: a Directive
could get a reply, drop out of `open_comments()`, and leave **no audit trail** of whether it changed
Direction or was merely acknowledged.

So the grill close writes an explicit **terminal**
`voz.resolved {comment_id, outcome: replied | folded-to-direction | acknowledged, direction_id?}` —
or, when it had to ask and captured no answer, the **non-terminal** `voz.clarify {comment_id,
clarify_id, question, grill_run_id}` that **keeps the chat open** (an autonomous grill may only park,
never fabricate `acknowledged`). The `voz.clarify` **renders inline** on its chat as the edge's
question; the mentee answers with a **distinct child event** `voz.clarify_answer {clarify_id, body,
ts}` (**not** a `voz.comment`, so it never becomes a new Directive or enters `open_comments()`), and a
later grill — seeing that linked answer — appends the terminal `voz.resolved`, consuming the answer
atomically. A Direction folded from a Directive
carries `origin_comment_id`. `open_comments()` keys on the **absence of a terminal `voz.resolved`** (a
parked `voz.clarify` chat is still open), not on `voz.reply`; a Directive stays visible until
terminally resolved. This
**distinguishes** acted-on (`folded-to-direction`, carrying `direction_id`) from merely
replied/acknowledged, and both from *unsettled* (parked) — first-class and auditable, with no mutable
flag (it stays a fold over `voz.resolved` / `voz.clarify`). Still no real-time poller (deferred).
