# Beat dispatch: minimize `claude -p` — interactive in-session, autonomous single-shot

The beat runs **entirely inside Claude Code** ("tudo dentro do claude") — Claude Code *is* the
agent that reads the world and the wiki and produces the Artefato. There is no Python+LLM-API
pipeline doing the cognition. How that agent is launched depends on who triggered the beat, and
the launch is shaped to **minimize paid `claude -p` invocations** (Anthropic is moving `claude
-p` to extra-billed API).

## Status

accepted

## Context

The prior edge already ran cognition through `claude -p -` (`tools/edge-runner:93`), but wrapped
that one line in ~1400 lines of deterministic envelope: dispatch cycles, preflight duplicate
blocks, exploration packs, autonomy checkups, a heartbeat router, standdown detection, follow-on
handoffs, and an **artifact-supervisor retry loop** that re-invoked `claude -p` one-to-three more
times per beat until an `ArtifactPublished` event appeared. That envelope is the scaffolding
ADR-0001 dissolves and the legibility goal sheds (~95k → ~2-3k lines). Under per-invocation
billing, the retry loop is also the single most expensive construct in the runtime.

## Considered options

- **Keep the deterministic envelope (preflight, retry, launch-gate).** Reliable: guarantees a
  published artifact, blocks duplicates, never pays for an empty tick. **Rejected:** it multiplies
  `claude -p` cost (the retry loop alone re-invokes the paid backend), and it is the very
  scaffolding the rebuild exists to remove.
- **Single-shot, skill-owned beat.** One beat = one backend invocation; the reading, choosing,
  producing, and (later) consolidating live as prose in the `/ed-beat` skill, not as Python.
  **Chosen:** cheapest per beat, most legible, and aligned with agentic-first.

## Decision

- **Interactive / operator dispatch** runs `/ed-beat` in the **live session** already open — it
  never spawns `claude -p`. This is the preferred, already-paid-for path.
- **Autonomous dispatch** (cron, no human) is a **single-shot** `claude -p -` with
  `--dangerously-skip-permissions`, fed the minimal prompt "load `/ed-beat` and go." One beat,
  one invocation.
- **No envelope:** no dispatch cycle, no preflight tool, no exploration tool, and **no
  artifact-supervisor retry**.
- **No launch-gate:** the beat is never an empty tick — it works from the **wiki** alone when the
  delta is empty (the delta enriches a beat, it does not gate one), so there is nothing to gate.

## Consequences

- The surviving Python for the autonomous path is a thin launcher (`tools/edge-heartbeat`) that
  builds the one `claude -p -` command; everything else is the `/ed-beat` skill.
- We trade the deterministic guarantees (forced publication, duplicate block) for cost and
  legibility, trusting the skill to self-direct — consistent with ADR-0001's "start free, harden
  only if it decays."
- The known fallback, if autonomous beats loop or duplicate, is to reintroduce a *single* cheap
  rail (e.g. a launch-gate or a one-shot publication check) — selectively, never the full envelope.
