# Pre-dispatch is mechanically enforced at the close: no wake, no publish

The wake (pre-dispatch: sweep-to-currency + the three briefs, ADR-0008/0014) stops being a
prose-only contract. A mechanical **entry-driver** (`tools/predispatch.py`) runs the scaffolding —
sweep (fail-loud per ADR-0015), briefing, recall brief — and appends a **`dispatch.open` event**
to the log. The **close refuses to publish without a fresh `dispatch.open`**: the gate the
producer must exit through becomes the gate that proves it woke. Delta stays an agentic fan
(ADR-0001 — judgment, never mechanized) and never gates.

## Status

proposed (2026-06-10; Voz ratifies — "next steps" session). Pairs with ADR-0015 (the same
incident's other half). Extends ADR-0012 (the shared pipeline gains a mechanical pre-dispatch
stage), honors ADR-0008 (sweep triggers), ADR-0014 (three briefs), and the corpus thesis
*what-to-make-mechanical-the-scaffolding-not-the-cognition* (this is its third mechanization,
after project-in-publisher and recall-push).

## Context

- **Tonight's evidence (roberto, session 8166…421):** a standalone `/roberto-research` dispatch
  **read `pipeline.md` and `scaffold.md` — the files that define pre-dispatch — and skipped the
  entire fan.** Zero assemble/delta/recall subagents; the producer went straight to work from the
  operator's prompt. Meanwhile the **close — the one mechanically enforced stage — executed
  flawlessly** (genus check, blind reviews, atomic publish + kernel + signals) via its driver.
  The asymmetry is the lesson: the mechanized half of the lifecycle ran perfectly; the prose half
  was skipped by a model that had just read it.
- The two failures compounded silently: skipping the wake hid the broken sweep (ADR-0015's
  `-home-vboxuser` literal); the broken sweep would have made an executed wake look pointless
  ("nothing new"). Neither alone was visible.
- ADR-0008 already declares the sweep a trigger of "any standalone ed skill at entry"; the
  glossary's Dispatch entry says every dispatch observes the same effects. Both are prose. The
  close is code. Contracts survive where they are code.

## Considered options

- **Keep prose-only and prompt harder** (bold the mandate, repeat it in every SKILL.md).
  Rejected: tonight's model *read the contract first* and skipped it anyway. Prompt-strength is
  not enforcement; this exact failure recurs at the next long context.
- **Gate at entry** (refuse to run the producer until pre-dispatch lands — a wrapper that blocks
  the skill). Rejected: there is no mechanical hook at skill entry — skills are markdown read by
  a model; only tool calls are mechanical. An entry wrapper would be one more instruction to skip.
- **Chosen: stamp at entry, verify at exit.** The only door every producer must pass through
  mechanically is the close (it alone writes `artefato.published`). Make publish conditional on
  proof of wake: the entry-driver appends `dispatch.open`; `close.py` checks it. Skipping the
  wake now dead-ends at the moment of publish — visible, attributable, unskippable.

## Decision

- **`tools/predispatch.py`** — one idempotent command, run at every dispatch entry (beat or
  standalone): (1) sweep to currency (raises on a missing store, ADR-0015), (2) compose the
  briefing, (3) render the recall brief, (4) append **`dispatch.open`** to the Tier-0 log with
  the sweep yield in its payload (sessions digested, episodes appended — the read:write
  numerator the Direction wants instrumented rides along free).
- **`close.py` gates on the stamp**: publish requires a `dispatch.open` **newer than the last
  `artefato.published`** (one wake per publish — a stamp cannot be reused across dispatches).
  Absent or stale stamp → a strike that names the violation (`no-wake`), same vocabulary as the
  genus gates.
- **Delta is not stamped and not gated** — it remains the agentic, discretionary world-read
  (ADR-0001/0011). The mechanical floor is exactly the scaffolding: sweep + briefing + recall.
- The **operator wake** (`skills/wake`) runs the same entry-driver (it IS pre-dispatch) but needs
  no gate — it publishes nothing; its halt is the contract (CONTRACT C1).

## Consequences

- Every producer SKILL.md gains the same two-line entry snippet (run the driver, read the
  briefs); the skill prose *describes* the wake, the driver *performs* it — prose stops being the
  enforcement layer anywhere in the lifecycle.
- The `dispatch.open` payload gives the heartbeat the read-side metric (entities extracted per
  sweep) at zero extra cost — the read:write instrumentation steer starts here.
- A dispatch that legitimately cannot wake (graph down, store empty) still proceeds: sweep
  degrades honestly per contract, the stamp records the degrade — the gate proves the wake *ran*,
  not that the world cooperated.
- One-beat lag accepted: a stamp is per-dispatch; long operator sessions that publish twice need
  two wakes (re-running the driver is idempotent and cheap).
- Concurrent dispatches sharing one log (operator + heartbeat in parallel) can consume each
  other's stamp: A and B both stamp, A publishes, B's older stamp is now stale and B's publish
  refuses. Accepted: the race is rare, the refusal is loud and names the remedy, and re-running
  the driver recovers (idempotent). Per-dispatch stamp identity is the known hardening if the
  race ever becomes frequent.
- The skills now lag this ADR (build follows): `predispatch.py` + the `close.py` check + entry
  snippets in the producer SKILL.md set + provision re-render.
