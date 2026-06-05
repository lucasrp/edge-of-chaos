# The lifecycle splits into assemble and consolidate subagents; the beat loop carries only judgment

The beat's mechanical phases — assembling prior state at the open, consolidating the session at
the close — run as **fresh Agent-tool subagents inside the one beat dispatch**, each in its own
context. The main loop never holds that mechanics: it wakes already-assembled, does only the
semantic/mentoring judgment, and hands consolidation down to a subagent on the way out. `/load`
is the same assemble primitive, triggered by the operator. Each cognition stays faithful to one
task without competing for the main context — it is the runtime/skills split pushed down to the
context level.

## Status

accepted

## Context

- The prior Edge mixed bookkeeping — reading state, distilling, writing handoffs — into the same
  context as the useful work; the operator names this as a major decay mode (cognition competing
  in one window).
- ADR-0003 removed the Python **envelope** but left the single-shot `/ed-beat` skill reading and
  consolidating **inline**, so the assembly/consolidation cognition still shares the main window
  with the mentoring cognition.
- This is a different axis from 0003. 0003 shed deterministic **reliability** scaffolding (retry,
  dedup, launch-gate). This ADR sheds **context** cost. The subagents here are agentic (Agent
  tool), **not** Python phases, and add **no** new `claude -p` invocation — they are internal
  fan-out within the single dispatch 0003 mandates.
- The rebuild starts from ~95k LOC, **not** a blank slate. Separating assemble/consolidate is
  **decomposition of that monolith** (divide and conquer), not speculative robustness. 0003's
  *start free, harden on decay* governs reliability **machinery** (retries, gates, locks) — a
  different category that does not argue against drawing boundaries. The only part of this ADR
  that inherits 0003's caution is the in-seam **guarantee** (the lock below), not the separation.

## Considered options

- **Everything inline in `/ed-beat` (0003 as written).** Simplest, one context. **Rejected as the
  default:** assembly + consolidation material floods the working context — the observed
  prior-Edge decay — so the main loop reasons over a window half-full of bookkeeping.
- **Mechanics in fresh subagents within the one dispatch.** Assemble and consolidate each get a
  clean context; the main loop inherits only results. **Chosen:** clean cognition per task, no
  extra `claude -p`, and "separate everything" is the maintainability the rebuild exists for.

## Decision

Two symmetric primitives, both Agent-tool subagents inside the single beat dispatch:

- **Assemble — blocking.** At beat-open (or on `/load`), a subagent reads prior handoffs, the
  delta, and the distilled pages, and returns a clean pack + a state digest. The main loop
  **blocks** until it lands, then wakes holding only the result — the blocking is the mechanism
  that delivers the fresh context. `/load` is this same primitive, operator-triggered: it renders
  the digest to the human and widens the aperture from "delta" to "full active state".
- **Consolidate — async.** At beat-close, the main loop writes a 3-line **intent kernel** (what is
  open, the next bet — the pragmatic layer no cold reader recovers) and fires a subagent that
  archives the transcript (raw, search-only), fans the session across the distilled pages, and
  writes the handoff. Fire-and-forget: the next beat needs it, ~3h away.
- **Briefs at each seam.** assemble→loop hands *up* a state digest; loop→consolidate hands *down*
  the intent kernel. Every fresh context is cold to the others, so each seam carries one minimal,
  high-signal brief.
- **One race, not yet a lock.** The consolidate(N)→assemble(N+1) seam is read-after-write; the
  heartbeat normally absorbs it. This is the one in-seam **guarantee**, so it follows 0003: the
  lock is **not** built day zero. The race is noted, and assemble grows a completion check —
  silent when scheduled, a surfaced warning under `/load` — on the first observed early/manual
  beat that reads partial state. The separation ships now; this guarantee waits for decay.
- **Decomposition.** Each primitive is cheap code (mechanical: compute delta / archive transcript)
  plus a thin subagent (judgment: assemble pack+digest / fan pages + handoff), keeping the agentic
  surface small.

## Consequences

- The main loop's context holds only mentoring judgment — faithful to one task; the
  maintainability win the rebuild is built for.
- Quality gates, when added, are the same pattern and benefit most from a fresh context (the agent
  that did the work does not grade it in the same window).
- Cost: more context boundaries means more intent-leak points. The per-seam brief is the
  mitigation, and the intent kernel is load-bearing — a fully-blind consolidate reintroduces the
  Zep failure (it loses pragmatic intent, distilling a vent as a decision).
- Consistent with 0003: no new `claude -p`, no Python envelope. The separation is **decomposition**
  of the 95k monolith, taken day zero — it is not the reliability structure 0003 defers. Only the
  in-seam **guarantees** (the lock) follow 0003's "start free, harden only if it decays". If a
  primitive itself proves unneeded, collapse it back inline.
