# The beat fans into assemble, delta, and consolidate subagents; the loop carries only judgment

The beat's mechanical cognitions run as **fresh Agent-tool subagents inside the one beat dispatch**,
each in its own context, so the main loop holds only judgment. Four cognitions, not one:

1. **assemble** (consolidação prévia) — at open / `/load`, reads the edge's own prior consolidated
   state (handoffs, rolling digest, distilled pages) and hands up a **state digest**;
2. **delta** — at open, reads the **world** at its source keys and hands up a light **delta
   orientation** of what is new (agentic, per ADR-0001 — never a per-key primitive);
3. **the beat loop** (beat propriamente dito) — wakes already-assembled, does only the
   semantic/mentoring judgment, produces one Artefato, and emits a 3-line **intent kernel**;
4. **consolidate** (post) — at close, async, takes the intent kernel and archives the transcript,
   fans the session across the distilled pages, and writes the handoff.

assemble and delta are split because they read different things on different axes: assemble reads
the **wiki** (the edge's own knowledge, in full); delta reads the **world** (the inputs,
incrementally). Mixing them in one context reintroduces the decay this ADR exists to remove. Each
cognition stays faithful to one task without competing for the main context — the runtime/skills
split pushed down to the context level. No new `claude -p`: this is internal fan-out within the
single dispatch ADR-0003 mandates.

## Status

accepted

## Context

- The prior Edge mixed bookkeeping — reading state, distilling, writing handoffs — into the same
  context as the useful work; the operator names this as a major decay mode (cognition competing
  in one window). Old `blog/consolidate-state.sh` was a 1905-line monolith; `beat-context.json`
  mixed intent ("what_matters_now") into mechanical runtime state.
- ADR-0003 removed the Python **envelope** but left the single-shot `/ed-beat` skill reading,
  enriching, and consolidating **inline**, so all of that cognition shared the main window with the
  mentoring cognition.
- This is a different axis from 0003. 0003 shed deterministic **reliability** scaffolding (retry,
  dedup, launch-gate). This ADR sheds **context** cost. The subagents are agentic (Agent tool),
  **not** Python phases, and add **no** new `claude -p`.
- **Why delta is its own subagent, not part of assemble.** assemble reads the wiki in full; delta
  reads the world incrementally (CONTEXT.md: "the delta is over the world, never over the wiki").
  Different aperture, different failure mode, different cadence — so a clean context each, both
  feeding the loop. Delta stays agentic (ADR-0001): give it the key, it figures out what is new.
- The rebuild starts from ~95k LOC, **not** a blank slate. This separation is **decomposition** of
  that monolith (divide and conquer), not speculative robustness.

## Considered options

- **Everything inline in `/ed-beat` (0003 as written).** Simplest, one context. **Rejected as the
  default:** assembly + delta + consolidation material floods the working context — the observed
  prior-Edge decay — so the main loop reasons over a window half-full of bookkeeping.
- **Three cognitions (assemble incl. delta, loop, consolidate).** Cleaner, but assemble's context
  carries both the wiki (in full) and the world (incremental) — two apertures fighting in one
  window. **Rejected:** the very mixing, one level down.
- **Four cognitions: assemble, delta, loop, consolidate.** Each mechanical read/write gets a clean
  context; the loop inherits only briefs. **Chosen:** one faithful task per context, no extra
  `claude -p`, maximal decomposition.

## Decision

Three Agent-tool subagents around one judgment loop, inside the single beat dispatch:

- **assemble — blocking.** At beat-open (or on `/load`), a subagent reads the edge's prior
  consolidated state — handoffs, the rolling digest, the distilled pages — and returns a clean pack
  + a **state digest**. The loop **blocks** until it lands, then wakes holding only the result.
  `/load` is this same primitive, operator-triggered: it renders the digest to the human and widens
  the aperture from "what's active" to "full active state".
- **delta — blocking.** At beat-open, a subagent reads the **world** at its configured source keys
  (Mundo / Atividade / Voz — source-agnostic locators, from the Source-roadmap standing page) and
  returns a light **delta orientation**: what is new, enough to point the loop at fresh material.
  Agentic, never a per-key primitive. Empty when there are no keys or nothing new — the delta
  enriches a beat, it never gates one (CONTEXT.md: Delta is never a precondition).
- **the beat loop — judgment only.** Holding the state digest and the delta orientation (not the
  raw reads), it chooses one Worthwhile theme, produces one Artefato, self-reviews, and at close
  writes a 3-line **intent kernel** (what is open, the next bet — the pragmatic layer no cold reader
  recovers).
- **consolidate — async.** At beat-close, the loop fires a subagent with the intent kernel; it
  archives the transcript (raw, search-only), fans the session across the distilled pages, and
  writes the handoff. Fire-and-forget: the next beat needs it, ~3h away.
- **Briefs at each seam.** assemble→loop hands up a **state digest**; delta→loop hands up a **delta
  orientation**; loop→consolidate hands down the **intent kernel**. Every fresh context is cold to
  the others, so each seam carries one minimal, high-signal brief.
- **Mechanical / judgment split inside each subagent.** Each primitive is cheap mechanical work
  (enumerate surfaces · list source keys · archive the transcript) plus thin judgment (distil the
  pack · decide what's new · fan the pages + handoff). The mechanical half is where a deterministic
  Python core lands **if and when** it must be made reliable — not built speculatively day zero,
  and never a git per-key delta (ADR-0001).
- **One race, not yet a lock.** The consolidate(N)→assemble(N+1) seam is read-after-write; the
  heartbeat normally absorbs it. This is the one in-seam **guarantee**, so it follows 0003: the
  lock is **not** built day zero. assemble grows a completion check — silent when scheduled, a
  surfaced warning under `/load` — on the first observed early/manual beat that reads partial state.

## Consequences

- The main loop's context holds only mentoring judgment — faithful to one task; the maintainability
  win the rebuild is built for.
- Quality gates, when added, are the same pattern and benefit most from a fresh context (the agent
  that did the work does not grade it in the same window).
- Cost: more context boundaries means more intent-leak points. The per-seam brief is the mitigation,
  and the intent kernel is load-bearing — a fully-blind consolidate reintroduces the Zep failure
  (it loses pragmatic intent, distilling a vent as a decision).
- **Persistence-gated halves.** assemble's "read the distilled pages" and consolidate's "fan into
  the distilled pages" land fully when persistence (wiki clusters / standing pages — handoff #2)
  exists. Until then each does what it can against existing surfaces (digest, prior Artefatos,
  handoff) and marks the gated half. The seams are drawn now regardless — decomposition day zero.
- Consistent with 0003: no new `claude -p`, no Python envelope. If a primitive itself proves
  unneeded, collapse it back inline.
