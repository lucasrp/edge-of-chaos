# Event-Sourced Enforcement Migration (#248)

This document defines how the event-sourced enforcement substrate proposed in [issue #248](https://github.com/lucasrp/edge-of-chaos/issues/248) coexists with the current state-oriented system and how the legacy enforcement ladder is retired without a big-bang rewrite.

The first concrete rollout slice is documented in [docs/phase1-shadow-observability.md](./phase1-shadow-observability.md).

## Problem

`edge-of-chaos` currently mixes three different authority layers:

1. Prose rules in `SKILL.md` and `memory/`
2. State inspection and point hooks (`write-guard`, `edge-doctor`, review gates, heartbeat verifiers)
3. Materialized state on disk (`blog/entries/`, `reports/`, `state/`, rendered config)

This creates four recurring failure classes:

- New write primitives bypass old chokepoints
- Intent and materialized state drift silently
- Telemetry is fragmented across logs, signals, frontmatter, and ad hoc files
- Fixes accumulate as local patches instead of simplifying the substrate

The current system still contains real capability and operational knowledge. The rewrite target is the enforcement substrate, not the whole agent.

## Decision

Adopt event sourcing incrementally.

The current pipeline remains the executor at first. The new ledger and projections begin as observers, then become advisory gates, then soft blockers, and only later become the authoritative command boundary for protected writes.

This is a migration, not a replacement PR.

## Migration Modes

### 1. Observe-only

Legacy behavior remains authoritative.

- `consolidate-state`, `blog-publish.sh`, `edge-apply`, `edge-event`, `edge-signal`, `edge-skill-step`, and existing hooks keep running unchanged.
- The only new behavior is dual-write into a unified append-only ledger.
- No new block conditions are introduced.

Use this mode to prove that the event model is expressive enough before moving authority.

### 2. Advisory

Projections become visible, but not enforceable.

- `dispatch-completeness` reports missing dispatch / missing closure
- `pipeline-state` reports incomplete phases and blocked artifacts
- `render-install-drift` reports divergence between rendered intent and installed state

Legacy success/failure semantics still win. Projection output is compared against current behavior to find mismatches.

### 3. Soft-gate

Selected legacy checks consult projections before declaring success.

Examples:

- dispatch-cycle close consults `dispatch-completeness`
- Pipeline completion consults `pipeline-state`
- `edge-doctor` incorporates `render-install-drift`

At this stage, the old code paths still execute the work. The new substrate only decides whether the cycle is considered complete.

### 4. Command-owned

Protected writes move behind the new command boundary.

- Artifact writes become command-validated instead of primitive-specific hook-validated
- Projections become the source of truth for cycle completeness
- Legacy hooks are either removed or reduced to thin shims that call the new validator

This is the point where the old enforcement ladder can be retired.

## Authority Shift

The migration deliberately separates execution from authority.

| Stage | Executes work | Decides completion |
|-------|----------------|--------------------|
| Observe-only | legacy pipeline | legacy pipeline |
| Advisory | legacy pipeline | legacy pipeline |
| Soft-gate | legacy pipeline | legacy + projection read |
| Command-owned | command bus + legacy adapters | event substrate |

This avoids the common failure mode where a new substrate is made authoritative before it has enough operational coverage.

## Starting Point

Do not start with a command bus.
Do not start by rewriting skills.
Do not start by replacing `consolidate-state`.

Start with the ledger.

The highest-leverage first move is to unify the telemetry that already exists in scattered form. The codebase is already telling us this:

- `edge-skill-step` already emits structured step records
- `edge-event` already emits lifecycle facts
- `consolidate-state` already knows phase boundaries
- dispatch and publish bugs are visible in logs, but not expressed as one replayable stream

## Step 1: Unified Ledger

Create one append-only file:

`state/events/log.jsonl`

### Requirements

- JSONL, one event per line
- append-only
- atomic writer with lock
- monotonic chain field (`prev_hash`) so tampering is detectable
- tolerant readers: replay should skip malformed trailing lines and surface them as corruption warnings

### Event Envelope

See [memory/events.md](/home/vboxuser/work/edge-of-chaos-pr248/memory/events.md) for the initial schema.

### Dual-write Sources

Step 1 should add dual-write from:

- `edge-event`
- `edge-signal`
- `edge-skill-step`
- `consolidate-state`
- `blog-publish.sh`

Fresh-install tooling can join after the dispatch loop is stable:

- `edge-render`
- `edge-apply`
- `edge-doctor`

These emit `RenderProduced`, `InstallApplied`, and `InstallCheckObserved` facts so install drift can be compared against runtime prose later.

## First Projections

### `dispatch-completeness`

Purpose:

- detect cycle starts with no `SkillDispatched`
- detect dispatch cycles that never close
- support the eventual replacement of prose-only lifecycle invariants

This is the best first enforcement target because it is binary, frequent, and already the source of repeated incidents.

A dispatch cycle may be triggered by:

- heartbeat
- direct operator invocation

The process is the same after the trigger. The trigger source changes, but the cycle semantics do not.

### `pipeline-state`

Purpose:

- reconstruct phase progression for each artifact
- distinguish `blocked`, `partial`, and `complete`
- replace ad hoc reasoning from `pipeline-failures.jsonl`, daily logs, and meta-reports

This is the second target because current failures in `ed`, `gauss`, and `roberto` are dominated by pipeline completion ambiguity, especially around Phase 1.

Current implementation path:

- `tools/rollup-pipeline-state.py` builds `state/projections/pipeline-state.json`
- `edge-replay pipeline-state` exposes the projection from the canonical ledger
- `ArtifactPublished` without matching `PhaseCompleted` is surfaced as `orphaned_publish` until pipeline phase emission is complete
- `consolidate-state` emits `PhaseCompleted` for every completed/failed/degraded phase, including a terminal `phase=pipeline`
- `edge-doctor` and `edge-postflight` now read `pipeline-state` in advisory/soft-gate mode

### `render-install-drift`

Purpose:

- compare rendered intent and installed materialized state
- replace bespoke checks in `edge-doctor`
- explain drift instead of merely detecting symptoms

Current implementation path:

- `tools/rollup-render-install-drift.py` builds `state/render-install-drift.json`
- `edge-doctor` reads that projection in advisory mode

This remains advisory. It makes drift legible before any install-time gate exists.

## Rollout Plan

### Phase A: Shadow Mode

Run for at least 7 dispatch cycles on `ed`, `gauss`, and `roberto`.

The sample should include both heartbeat-triggered cycles and direct user-triggered cycles when available.

Success criteria:

- every dispatch cycle emits replayable ledger events
- replay can reconstruct dispatch and pipeline state
- projections surface the already-known incidents without introducing many false positives

The goal is not perfection. The goal is proving that the new substrate observes the real cycle accurately enough to own it later.

### Phase B: Advisory Readouts

Expose projection results in:

- cycle reports, including heartbeat reports
- meta-reports
- `edge-doctor` / state audit output

Keep legacy behavior authoritative. Any mismatch between projection output and legacy success should be treated as a migration bug to study.

### Phase C: Soft Gates

Turn on narrow projection reads in the highest-value binary checkpoints:

- dispatch-cycle close
- pipeline completion summary
- postflight projection refresh

Do not yet block arbitrary writes. The purpose here is to force the cycle semantics, not to redesign every command path at once.

### Phase D: Protected Command Boundary

Introduce `edge-cmd` or equivalent command-owned write path for protected artifacts.

Only after this is stable should the following legacy pieces start disappearing:

- prose-only "ABSOLUTE RULE" enforcement that duplicates binary invariants
- primitive-specific write hooks
- state-only audits that can now be replayed from events

Current implementation path:

- `tools/edge-cmd validate-write` validates protected artifact writes and emits `ArtifactWriteAuthorized` / `ArtifactWriteRejected`
- `hooks/write-guard.sh` delegates protected write decisions to `edge-cmd`
- `bin/heartbeat-dispatch-guard.sh` delegates heartbeat dispatch enforcement to `edge-cmd` while retaining its legacy fallback when the command boundary is unavailable
- `tools/audit-cqrs-migration.py` audits the migration surface and reports remaining shim/fallback residue

## Legacy Retirement Order

Retire old mechanisms from most redundant to most dangerous:

1. Prose rules that merely restate binary invariants
2. Ad hoc verification steps whose logic now lives in projections
3. Specialized lifecycle hooks that inspect one primitive or one path
4. Path-specific write guards
5. Direct protected writes outside the command boundary

Do not invert this order. Removing write protections before the command boundary exists only widens the hole.

## Non-Goals

- Rewriting the whole agent from scratch
- Replacing `genotype/phenotype/epigenetics`
- Removing adversarial review as a quality gate
- Moving everything into one daemon
- Declaring the event log authoritative before replay and projections have proven themselves

## Why This Is Better Than A Full Rewrite

A full rewrite of the whole agent would mix two questions that should stay separate:

1. Is the enforcement substrate wrong?
2. Are the skills, tools, and operational routines still useful?

The answer to (1) is increasingly "yes". The answer to (2) is clearly not "no" because the fleet still produces useful work, especially on `gauss`.

The correct move is to preserve working capability while replacing the part that keeps generating enforcement debt.

## First PR After This Spec

The first implementation PR should be deliberately small:

1. add the unified ledger writer
2. dual-write from `edge-event`, `edge-signal`, and `edge-skill-step`
3. add `tools/edge-replay --tail`
4. document the event envelope

That PR should not introduce new block conditions yet.

## Acceptance For The Migration Start

- `state/events/log.jsonl` exists and is append-only
- at least three current telemetry producers dual-write into it
- `edge-replay --tail` can follow the new ledger live
- the 7-cycle shadow run on `ed`, `gauss`, and `roberto` is completed
- projection output can explain known dispatch and pipeline incidents better than today's scattered logs
