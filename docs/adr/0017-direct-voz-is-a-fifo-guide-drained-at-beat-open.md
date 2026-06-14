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
one with a mentee comment the edge has not yet replied to (the `open_comments()` fold = comments
with no `voz.reply`). Every open chat is **earmarked**, so the **grill loads them all into context**
at once. From that full context the grill:

- **asks the residual only where ambiguous** — evidence-first, **non-exhaustive**: it questions the
  mentee only on the chats the loaded context cannot settle;
- **marks every open chat solved at its close** — **exhaustive** (coverage): no open chat survives a
  grill, so nothing rots in a queue;
- **folds the standing-worthy ones into Direction** — a chat that moves strategy becomes a `set`
  steer; the rest are simply answered and closed.

So *earmark = full context*; **asking is non-exhaustive (ambiguous only), solving is exhaustive (all
marked solved)**. There is **no pin** — the grill already has every open chat in front of it — and
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

- **Latency up to one grill** before a Directive is acknowledged. The deferred deterministic poller
  is the documented path to close this gap when it is needed.
- **Resolution is by chat, not by message.** The grill does not drain a queue oldest-first; it loads
  every open chat and closes all of them in one pass. Coverage is the invariant — no open chat
  outlives a grill.
- **The answer travels back out through the Medium** — for the Voz rail that path is the dashboard
  rendering the `voz.reply` event; no separate outbound send. A Directive can only ride a **two-way**
  Medium precisely because a one-way pipe cannot carry the answer back.
- **"The moment does not jump the queue" (Beat) still holds for the *world*** (delta / hot events).
  Mentee Directives do not preempt the beat either — they wait for the grill, which is where every
  promotion happens (ADR-0012-compatible: the beat stays a pure round-robin scheduler; resolution is
  the grill's, not a beat rule).
- **Open / solved is a fold over the log**, not a mutable flag — `open_comments()` derives from the
  absence of a `voz.reply`, consistent with the event-sourced model (ADR-0005/0006). No parallel
  store.

## Considered and deferred

- **Real-time deterministic poller** (every few minutes; interrupt on an open higher-tier Voz chat):
  the ideal for true back-and-forth latency. Deferred for simplicity.
- **A per-Directive FIFO drain at beat-open**, with separate **addressed** (acted-on) vs **answered**
  (replied) states: the earlier design. **Superseded** — the grill resolves whole chats from full
  context (coverage at its close), which removes the queue, the FIFO rule, the pin, and the
  two-state bookkeeping. Whether "solved" should still distinguish *acted-on* from *replied* is an
  **open question** (see below).
- **Harm-ranked drain** instead of FIFO: moot under chat-resolution — the grill already prioritises
  by harm potential when *asking*, and solves exhaustively regardless.

## Open question

Does **"solved"** collapse the earlier **addressed** (the edge acted on the Directive) vs
**answered** (the edge replied through the Medium) distinction, or should both still be tracked?
CONTEXT.md and this ADR use **solved** provisionally (a chat closed at the grill — answered, and
folded into Direction where standing-worthy). Not yet resolved by the operator.
