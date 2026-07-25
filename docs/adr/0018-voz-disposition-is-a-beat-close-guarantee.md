# Voz disposition is a beat-close guarantee (receipt now, semantics by the grill)

## Status

accepted — amends ADR-0017 (keeps its resolution model; adds the disposition rail and the
channel contract). Decided in-session with the operator (2026-07-01), after an /ed-research
pass (ports-and-adapters ingress, HITL feedback capture, transactional inbox, agent-memory
write-back, queueing/backpressure) and an adversarial Codex review of the draft design.

## Decision

The operator's requirement is **"toda Voz tem que ser respondida"**. ADR-0017 already gives
Directives a resolver (the grill, chat-level, terminal `voz.resolved`) but leaves a gap its own
Consequences name: *"latency up to one grill before a Directive is acknowledged."* This ADR
closes that gap with a **disposition rail** (`tools/voz.py`) — without reopening the FIFO-drain
resolution model 0017 superseded:

- **Pendency is a fold, never a stored cursor.** A Voz act (`voz.vote`, `voz.comment`) is
  *pending* while nothing closing references it. `fold_voz(events)` (pure, house `fold_*`
  pattern) derives it; completeness is auditable by replay, by construction.
- **Four disposition states**, recorded as `voz.disposition {of, state, reason?, ref?}`:
  `receipt_sent` / `semantic_answer_required` / `semantic_answered` / `dead_lettered`.
  The honesty invariant is **structural**: a `receipt_sent` on a comment is recorded but does
  NOT close it (only `semantic_answered(ref)` or `dead_lettered(reason)` do) — a cheap ack can
  never masquerade as an answer. `dead_lettered` without a reason fails loud.
- **Both rails close.** The fold honors ADR-0017's `voz.resolved {comment_id}` (any outcome)
  as a semantic terminal too — one comment, two closing vocabularies, zero divergence. The
  grill remains the resolver of Directive *chats*; the beat's close guarantees *receipt*.
- **Beat wiring:** every wake's briefing carries the bounded **Voz pendente** section
  (`voz.brief` — counts + top-N; this is 0017's "health strip", implemented). At beat close,
  `voz.close_cycle(answered={seq: ref})` disposes everything pending — votes get their receipt
  (closing them; a vote owes no reply, the receipt is bookkeeping + the retention effect),
  an unanswered comment gets a **one-time** receipt and stays pending, a comment the beat's
  artefato directly answered closes with its ref. Idempotent: re-run writes nothing.
  `voz.assert_all_received()` is the fail-loud gate (nothing ignored without even a receipt);
  its enforcement inside `close.run_close` plugs in when the conductor work settles.
- **No preemption** (0017 upheld): pending Voz is a strong guide at wake, theme-material when
  it aligns; the beat never jumps its rotation for it.

## The channel contract (for the adapters to come)

Voz is a **channel-agnostic subject**; a channel is an adapter, never a per-channel primitive
(ADR-0001 applied to ingress). Decided shape, validated against Slack's real semantics:

- **One canonical envelope** (`Signal`): `{seq, ts, channel, act, target, value|text,
  comment_id, required}` — the adapter translates native→canonical (an Anti-Corruption Layer:
  transport + schema + identity), the core interprets. The **adapter types the ACT**
  (vote/comment — structural, from the UI control used); the **core types the INTENT**
  (endorse/steer/contradict — semantic, from content).
- **Reply capability, not reply address**: captured at ingress as
  `{channel, address, expires_at, threading_mode, idempotency_key, fallback_policy}` —
  Slack `thread_ts`, WhatsApp 24h windows and closed sessions make a bare address a lie.
- **Native channel simplification**: delivery = a log write (`voz.reply` the dashboard
  renders) — local and atomic; the dual-write problem does not exist until the first
  external send.

## Considered and deferred (named triggers)

- **Outbox for egress** → with the first external order-bearing Medium (Slack/WhatsApp,
  0017's Phase 2); an external `chat.postMessage` cannot commit atomically with the log.
- **Two lanes (votes vs comments), aging/anti-starvation, priority tiers** → when the
  pending-queue depth is real (Little's Law says the collision comes; today's volume is ~0).
- **Channel registry with lifecycle** (`declared → live → draining → retired`; retiring a
  channel must drain-or-dead-letter its pending Voz and re-route replies via
  `fallback_policy`) → with the second channel. Runtime-*generated* adapters are allowed
  only through the normal gate (TDD + review), never improvised mid-beat — the adapter
  carries the delivery guarantees.
- **Vote → Cortex projection** (typed ENDORSES edge + MemoryBank-style weight `S+=1, t:=0`)
  → with the recall-rail story; today recall is recency-push and would not read the weight
  (a dead write). Until then a vote manifests as retention bookkeeping only; a steer
  manifests through the grill folding it into Direction (0017).

## Consequences

- The dashboard can render "recebido, na fila" the beat after any comment lands — the
  acknowledged-latency consequence of 0017 is closed cheaply, without touching its
  resolution model.
- "Toda Voz respondida" is now a *replayable audit*: fold the log; anything pending without
  even a receipt is a `VozUnreceived` failure, not an opinion.
- Two closing vocabularies coexist by design (`voz.resolved` from the grill,
  `voz.disposition` from the beat); `fold_voz` is the single place that reconciles them.
