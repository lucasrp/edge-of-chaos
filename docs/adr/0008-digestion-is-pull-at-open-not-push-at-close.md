# Digestion is a pull-at-open, store-keyed sweep run by every dispatch; consolidate is absorbed

The edge digests sessions by **one idempotent, cursor-guarded sweep over the transcript store**, run at
the **open of any dispatch** (`/ed-beat` is just a shell — a manual `/ed-report` runs the same effect),
**not** by a beat-close `consolidate` subagent. Digestion moves from **push-at-close to pull-at-open**,
covering **all** sessions — including dispatch-less, skill-less chats. This **amends ADR-0004**: the
`consolidate` cognition is absorbed into the sweep + the grill.

## Status

proposed (2026-06-06; Voz ratifies)

## Context

- ADR-0004 made `consolidate` (beat-close, async) the writer of the handoff/digestion. Two runtime gaps:
  - **Coverage.** Only beats consolidate. `assemble` runs only inside `/ed-beat` (the heartbeat launches
    it via `claude -p`; the live session runs it in-place). So operator sessions — and sessions that run
    **no ed skill at all** — are never digested; their content leaks in only via live grilling. There are
    **zero hooks** wired (`~/.claude/settings*.json`). Voz: *"nem toda sessão tem dispatch… posso
    conversar sem disparar o agente… nem ed-report."*
  - **Fidelity vs coverage.** A cold `consolidate` distils a vent as a decision (the Zep failure,
    ADR-0004:98). The load-bearing **intent kernel** mitigates it for beats — but there is no kernel for a
    session no loop ever lived.
- The **handoff** is already defined (Idiom) as *"a session distilled to its decisions; the clean episode
  fed to the graph."* The concept is right; the **producer and coverage** are the bug.
- **`/ed-beat` is just a shell** (Voz): the lifecycle must not be privileged to it — a manual `/ed-report`
  dispatch must observe the same effects.

## Considered options

- **Keep `consolidate` at beat-close (ADR-0004 as written).** Rejected: leaves non-beat and no-skill
  sessions undigested.
- **A SessionStart hook as the sole trigger.** Prompt and dispatch-independent, but **net-new hook infra**
  (none today; the install layer already shows hooks drift badly here). Deferred as an optional *second*
  trigger, not the mechanism.
- **A pull-at-open, idempotent, store-keyed sweep triggered by any dispatch.** Chosen: complete coverage
  with zero new infra, robust to dirty exits, and faithful (mechanical, judgment deferred).

## Decision

- **One sweep, idempotent and cursor-guarded.** Over the transcript store
  (`~/.claude/projects/-home-vboxuser/*.jsonl`, operator-present sessions). It appends raw `episode` /
  `voz` events to the log (ADR-0006) and advances a per-session cursor. Re-running digests only new
  content — so multiple triggers are safe.
- **Keyed on the store, not on any skill.** A session that ran no ed skill is still digested at the next
  trigger; the store is the truth of "what happened," not the skills invoked.
- **The sweep runs the full pipeline to currency — only curation defers.** It is not timid: append raw →
  distil episodes → run **zep/Graphiti extraction** (incremental, on the delta) → **re-project** the wiki
  and Direction. So the **non-curated (hypothesis / `proposed`) tier is current at every dispatch entry**,
  ambiguous and `contested` items included (flagged, not hidden). What defers to the **grill** is **only
  curation**: promotion (hypothesis→curated, `proposed`→`set`) and cleanup of the ambiguous.
- **The Zep-failure guard is the tier boundary, not timidity.** "Never distil a vent as a decision" means
  extraction only ever writes the **non-curated** tier — never asserts a vent as a *curated* decision. A
  vent is allowed to *exist* as a flagged hypothesis; only the grill (the human) promotes it. This populates
  the abundant cheap tier eagerly (CONTEXT.md: "the edge works naturally with hypotheses") and reserves the
  mentee's scarce attention for curation. **Re-projection is part of the sweep** (sweep → re-fold/extract →
  digest), so a freshly-swept episode is in the rendered page the dispatch reads, not only in the log.
- **Triggers are pluggable** (idempotency makes stacking safe): the **heartbeat dispatch**, **any
  standalone ed skill at entry**, and `/load`. A SessionStart hook is an optional later trigger if
  heartbeat-independence is wanted — not built day zero.
- **The lifecycle belongs to the dispatch, not to `/ed-beat`.** A manual `/ed-report` dispatch observes
  the same effects (digest at entry, persist at close) as the heartbeat beat; they differ only in the
  cognition wrapped (a full judgment loop vs a single Artefato).
- **`consolidate` is absorbed.** Its three jobs redistribute: *archive raw* → the pull-at-open sweep;
  *fan/curate the pages* → the **grill** (Hypothesis consolidation, ADR-0007); *write the handoff* →
  **gone** (durable delta = the swept log; strategy = **Direction**). The only close-time act is the thin
  **intent-kernel breadcrumb**, written by whoever lived the session (a loop, or live grilling); a
  no-skill chat leaves none and the sweep captures its raw. ADR-0004 goes **four cognitions → three**
  (assemble[+sweep], delta, loop); the `consolidate→assemble` race (ADR-0004:88) dies with it.

## Consequences

- **Complete coverage.** Every session — beat, operator chat, no-skill, or crashed — is digested at the
  next trigger; the cursor guarantees no loss, only bounded delay (≤ ~3h via the heartbeat).
- **Robust to dirty exits.** Pull-at-open does not depend on a clean close; a crash never runs a close hook.
- **Fidelity preserved by the tier boundary.** Extraction populates only the non-curated tier; the curated
  tier and Direction `set` change only by the grill (the human). So the Zep failure cannot recur — a vent
  can land as a flagged hypothesis, never as a curated decision.
- **The non-curated tier is always current.** Every dispatch — including a manual `/ed-report` — starts
  against an up-to-date hypothesis tier and re-projected pages, not a stale snapshot. Completeness *and*
  extraction are synchronous; only curation is eventual.
- The async-close machinery and its one race are **gone** — a net simplification.
- **Cost: extraction runs at every dispatch** — the construction-heavy path the recall confrontation flagged
  (arXiv 2606.06448: construction energy dominates the lifecycle). Bounded by running extraction
  **incrementally on the delta** (Graphiti is built for streaming updates), never a full rebuild — so
  per-dispatch cost stays proportional to what is new, not to store size. The sweep must also be genuinely
  idempotent (per-session cursor discipline). Build: a sweep primitive over `sessions.py` that runs
  episodes → extraction → re-projection and advances the cursor, wired to the dispatch entrypoints;
  supersede `consolidate/SKILL.md`.
- **Supersedes** ADR-0004's `consolidate` cognition and its one-race clause; **consistent** with ADR-0006
  (the sweep is the log's writer), ADR-0007 (the grill consolidates strategy), and ADR-0001 (agentic,
  source-agnostic, no per-key primitive).
