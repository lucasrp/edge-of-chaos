# Phase 1 Shadow Observability

This document defines the first deployment slice for maximum visibility with minimum architectural commitment.

The rule for Phase 1 is strict:

- reuse existing emitters
- dual-write normalized facts into `state/events/log.jsonl`
- do not make the new stream authoritative yet
- do not add a new daemon, queue, or orchestration layer

This keeps room for radical architectural changes later while still producing real operational data now.

## Scope

Phase 1 captures facts from the current runtime across these surfaces:

1. dispatch cycle
2. pre/post skill execution evidence
3. primitive usage
4. workflow movement
5. claims and threads
6. signals
7. publication pipeline
8. health / operator interventions
9. fresh install / doctor verification

## Capability Map

### 1. Cycle

The runtime has two triggers:

- heartbeat
- direct operator dispatch

Both should converge on one cycle model:

- cycle starts
- a skill is dispatched
- skill-local steps happen
- publication/state work may happen
- cycle closes

### 2. Pre / Post Skill

The architecture already declares pre-skill and post-skill as part of the protocol, but today they are mostly enforced by prose and habit.

Phase 1 goal: make execution evidence visible, not authoritative.

### 3. Workflows

The runtime already has real workflow state transitions:

- recall
- use
- broken
- heal
- crystallize
- approve
- retire

Some of these already emit typed telemetry. Others still only exist in frontmatter or derived JSON.

### 4. Primitives

Primitives already log usage to `state/source-usage.jsonl` and, in some cases, `logs/events.jsonl` / SQLite telemetry.

Phase 1 goal: normalize these calls into the same shadow ledger.

### 5. Claims

Claims are mostly extracted from artifacts and frontmatter today. There is good semantic value here, but the runtime does not yet expose a full claim lifecycle event stream.

### 6. Signals

Signals are already first-class in practice:

- autonomy
- strategy
- reflection
- friction
- decision
- serendipity

They are currently written to `state/signals/*.md`.

### 7. Threads

Threads are durable memory objects and are updated during publication/state commit. Today, most of their lifecycle is visible only indirectly through markdown mutation and artifact frontmatter.

### 8. Publication Pipeline

The current pipeline already exposes strong boundaries:

- `consolidate-state`
- `blog-publish.sh`
- review/adversarial phases
- meta-report generation
- state audit
- git commit

### 9. Health / Survival

Health exists across:

- `health/current.json`
- `logs/pipeline-failures.jsonl`
- `logs/execution-ledger.jsonl`
- operator actions
- reflection / debugging artifacts

## Emitter Map

These are the lowest-friction emitters available now.

| Surface | Current emitter | Current sink | Phase 1 shadow action |
|---|---|---|---|
| generic typed telemetry | `tools/_shared/telemetry.py` | `logs/events.jsonl` | dual-write normalized envelope |
| execution attempts / pipeline probes | `tools/edge-ledger` | `logs/execution-ledger.jsonl` | dual-write normalized envelope |
| user/runtime events | `tools/edge-event` | `logs/events.jsonl` | dual-write normalized envelope |
| skill step tracking | `tools/edge-skill-step` | `logs/skill-steps.jsonl` | dual-write normalized envelope |
| typed signals | `tools/edge-signal` | `state/signals/*.md` | dual-write normalized envelope |
| primitive usage | `tools/primitives/_shared/usage_log.py` | `state/source-usage.jsonl` | dual-write normalized envelope |
| primitive lifecycle | `tools/edge-primitive-lifecycle` | `state/sources-manifest.yaml` + `state/events/log.jsonl` | canonical helper for missing/contract/materialize/probe facts |
| workflow transitions | `log_workflow_transition()` | `logs/events.jsonl` | already captured through shared telemetry |
| llm/router telemetry | `log_llm_call()` | `logs/events.jsonl` | already captured through shared telemetry |
| state commit artifact fact | `consolidate-state` Phase 5 inline Python | `logs/events.jsonl` | indirectly captured through `edge-event` legacy artifact event |
| render output facts | `tools/edge-render` | `logs/events.jsonl` + `state/events/log.jsonl` | dual-write `run_step` + `RenderProduced` |
| install materialization facts | `tools/edge-apply` | `logs/events.jsonl` + `state/events/log.jsonl` | dual-write `run_step` + `InstallApplied` |
| install verification checks | `tools/edge-doctor` | `logs/events.jsonl` + `state/events/log.jsonl` | dual-write `run_step` + `InstallCheckObserved` |

## Coverage Matrix

Legend:

- `done` = shadow dual-write added in Phase 1
- `partial` = observable, but not yet semantically complete
- `gap` = not yet emitted as a first-class fact

| Capability | Status | Notes |
|---|---|---|
| cycle start | done | emitted directly by `edge-dispatch open`; legacy `edge-event user_directive` still dual-writes during migration |
| cycle close | done | emitted directly by `edge-dispatch close` |
| skill dispatch | done | normalized from `edge-event skill_dispatched` |
| skill steps | done | normalized from `edge-skill-step` |
| primitive invocation | done | normalized from `usage_log.py` |
| primitive lifecycle | partial | helper now emits missing/contract/materialized/probe/manifest facts, but runtime still needs broader adoption at the command boundary |
| typed signals | done | normalized from `edge-signal` |
| generic telemetry events | done | normalized from `tools/_shared/telemetry.py` |
| workflow transitions | done | inherited from shared telemetry dual-write |
| llm/router calls | done | inherited from shared telemetry dual-write |
| execution attempts | done | normalized from `edge-ledger` |
| render output facts | done | `edge-render` now dual-writes rendered artifacts as `RenderProduced` |
| install materialization | done | `edge-apply` now emits `InstallApplied` across fresh-install writes |
| install verification checks | done | `edge-doctor` emits one fact per check as `InstallCheckObserved` |
| render/install drift projection | partial | `rollup-render-install-drift.py` + `edge-doctor` advisory readout now exist, but no gate consumes the projection yet |
| publication phase semantics | partial | current `edge-ledger` phase records are start-biased, not authoritative completion facts |
| artifact published | partial | strong legacy signal exists, but canonical publish fact still needs tightening |
| pre-skill executed | gap | currently prose-based; needs runtime evidence point |
| post-skill executed | gap | currently prose-based; needs runtime evidence point |
| claim lifecycle | gap | claims are visible in artifacts, not yet as lifecycle events |
| thread lifecycle | partial | thread mutation exists, but thread events remain indirect |
| operator actions | partial | separate logs exist, not yet normalized here |
| health transitions | partial | health exists in files/logs, not yet normalized as a single event stream |

## Why This Slice First

This slice maximizes data while minimizing new architecture.

It does not commit the project to the current runtime shape forever. It only makes the current runtime legible enough to decide what should survive in a rebuilt core.

That is the key distinction:

- radical architecture change is still available
- blind replacement is avoided

## What Phase 1 Does Not Do

Phase 1 does not:

- gate execution
- replace existing logs
- force a new command bus
- define the final event taxonomy
- claim that every current event has correct semantics

It only ensures that operational facts start landing in one normalized append-only stream.

## Expected Immediate Outputs

After rollout to `ed`, `gauss`, and `bobmarley`, we should quickly be able to answer:

- how many cycles start without a visible dispatch
- how many skill runs skip steps
- which primitives are actually used
- which signals are actually emitted
- how often publication work starts
- which execution attempts fail most often
- whether workflow activity is real or just documented

## Next Prioritization Pass

Once real data lands, the next slice should be chosen by observed pain, not intuition.

The most likely candidates are:

1. pre/post skill runtime evidence
2. publication phase completion semantics
3. claim/thread lifecycle events
4. health transition normalization
