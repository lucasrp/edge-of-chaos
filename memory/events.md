# Event Envelope

This file defines the initial event envelope for the event-sourced enforcement substrate proposed in [issue #248](https://github.com/lucasrp/edge-of-chaos/issues/248).

The goal of the first version is not to model everything. It is to capture enough of the cycle to replay skill dispatch, pipeline phases, and later render/install drift.

## Envelope

Every event in `state/events/log.jsonl` uses this outer structure:

```json
{
  "ts": "2026-04-19T14:23:52.779405+00:00",
  "type": "PhaseCompleted",
  "actor": "consolidate-state",
  "cycle_id": "cycle-2026-04-19T14:03:39Z",
  "artifact": "blog/entries/2026-04-19-planner-event-log-poc-dispatch-queue.md",
  "payload": {
    "phase": "1",
    "ok": false,
    "reason": "blog_publish_nonzero"
  },
  "prev_hash": "sha256:..."
}
```

## Field Semantics

| Field | Required | Meaning |
|-------|----------|---------|
| `ts` | yes | event creation timestamp in ISO-8601 with offset |
| `type` | yes | typed fact name |
| `actor` | yes | tool / script / hook / skill that emitted the event |
| `cycle_id` | no | correlation id for one dispatch cycle, whether heartbeat-triggered or operator-triggered |
| `artifact` | no | canonical artifact path or logical target |
| `payload` | yes | event-specific fields |
| `prev_hash` | yes | hash of the previous ledger line |

## Rules

- `ts` is the canonical timestamp field. Do not introduce `timestamp` in new ledger events.
- `type` names are facts, not commands.
- `actor` identifies the emitter, not the human explanation.
- `payload` may evolve, but outer envelope names must stay stable.
- readers must ignore unknown payload keys.
- during the initial shadow rollout, `prev_hash` is best-effort per emitter process; full cross-process chaining is not required yet.

## Initial Event Set

Step 1 now tracks six event types.

### `CycleStarted`

```json
{
  "type": "CycleStarted",
  "payload": {
    "skill_rotation_slot": "planner",
    "trigger": "heartbeat",
    "thread_id": "self-healing-pillars",
    "primary_thread_id": "self-healing-pillars"
  }
}
```

Emitted when a dispatch cycle starts and obtains a `cycle_id`.

Allowed trigger values in V1:

- `heartbeat`
- `operator`

Legacy normalization may still surface `user` while older `edge-event user_directive`
emitters are being migrated.

### `SkillDispatched`

```json
{
  "type": "SkillDispatched",
  "payload": {
    "skill": "planner",
    "dispatch_mode": "normal",
    "thread_id": "self-healing-pillars",
    "primary_thread_id": "self-healing-pillars"
  }
}
```

Emitted exactly when a skill is actually dispatched, not when prose says it should be.

### `CycleClosed`

```json
{
  "type": "CycleClosed",
  "payload": {
    "trigger": "operator",
    "skill": "reflection",
    "thread_id": "self-healing-pillars",
    "primary_thread_id": "self-healing-pillars",
    "close_status": "completed",
    "reason": ""
  }
}
```

Emitted when the dispatch cycle is explicitly closed, regardless of whether the
trigger came from heartbeat or operator intent.

### `PhaseCompleted`

```json
{
  "type": "PhaseCompleted",
  "artifact": "blog/entries/2026-04-19-example.md",
  "payload": {
    "pipeline": "consolidate-state",
    "phase": "1",
    "ok": false,
    "reason": "blog_publish_nonzero"
  }
}
```

Represents the outcome of one pipeline phase. This is enough to build the first `pipeline-state` projection.

### `ArtifactPublished`

```json
{
  "type": "ArtifactPublished",
  "artifact": "blog/entries/2026-04-19-example.md",
  "payload": {
    "hash": "sha256:...",
    "source_skill": "planner"
  }
}
```

Represents the canonical publish fact for an artifact.

### `ClaimObserved`

```json
{
  "type": "ClaimObserved",
  "artifact": "blog/entries/2026-04-21-example.md",
  "payload": {
    "claim_id": "claim-abcd1234",
    "text": "Critical case still lacks a closure argument",
    "kind": "gap",
    "threads": ["boundedness-classification"]
  }
}
```

Represents one claim explicitly observed from a published artifact.

### `ThreadTouched`

```json
{
  "type": "ThreadTouched",
  "artifact": "blog/entries/2026-04-21-example.md",
  "payload": {
    "thread_id": "boundedness-classification",
    "reason": "artifact_published"
  }
}
```

Represents one continuity surface touched by a beat or artifact.

### `ClaimLinkedToThread`

```json
{
  "type": "ClaimLinkedToThread",
  "artifact": "blog/entries/2026-04-21-example.md",
  "payload": {
    "claim_id": "claim-abcd1234",
    "text": "Critical case still lacks a closure argument",
    "thread_id": "boundedness-classification",
    "kind": "gap"
  }
}
```

Represents the explicit edge from one claim to one thread.

### `ClaimsValidationObserved`

```json
{
  "type": "ClaimsValidationObserved",
  "artifact": "blog/entries/2026-04-21-example.md",
  "payload": {
    "slug": "2026-04-21-example",
    "judge_status": "uncertain",
    "heuristic_status": "accepted"
  }
}
```

Represents the shadow validation result for continuity claim extraction.

### `InstallApplied`

```json
{
  "type": "InstallApplied",
  "artifact": "~/.claude/skills/ed-planner/SKILL.md",
  "payload": {
    "hash": "sha256:...",
    "source_template": "skills/planner/SKILL.md"
  }
}
```

Required later for render/install drift, but defined now so the envelope does not drift again during rollout.

### `InstallRemoved`

```json
{
  "type": "InstallRemoved",
  "artifact": "~/edge/.avatar-gen.py",
  "payload": {
    "source_template": "generated:avatar-openai-script",
    "kind": "file",
    "reason": "temporary-avatar-cleanup"
  }
}
```

Represents an install-time artifact cleanup so drift projections can distinguish
durable state from intentional temporary files.

### `RenderProduced`

```json
{
  "type": "RenderProduced",
  "artifact": "config/CLAUDE.md",
  "payload": {
    "hash": "sha256:...",
    "source_template": "config/CLAUDE.md.tpl",
    "residual_count": 0
  }
}
```

Represents one rendered artifact produced by `edge-render`.

### `InstallCheckObserved`

```json
{
  "type": "InstallCheckObserved",
  "artifact": "~/ed/config/branding.yaml",
  "payload": {
    "check_id": "file:branding-yaml",
    "status": "ok",
    "severity": "ok",
    "detail": "branding.yaml: /home/vboxuser/ed/config/branding.yaml"
  }
}
```

Represents one `edge-doctor` verification fact during fresh install or post-install validation.

### `PrimitiveMissingObserved`

```json
{
  "type": "PrimitiveMissingObserved",
  "payload": {
    "source": "overleaf",
    "operation": "search",
    "exit_code": 127,
    "detail": "primitive 'overleaf' returned exit 127"
  }
}
```

Represents the runtime moment where a declared primitive was needed but not yet materialized.

### `PrimitiveOperationMissingObserved`

```json
{
  "type": "PrimitiveOperationMissingObserved",
  "payload": {
    "source": "overleaf",
    "operation": "write",
    "exit_code": 77,
    "detail": "write operation not implemented yet"
  }
}
```

Represents a partial primitive that exists, but still lacks the requested operation.

### `PrimitiveContractWritten`

```json
{
  "type": "PrimitiveContractWritten",
  "artifact": "~/ed/libexec/ed/overleaf.meta.yaml",
  "payload": {
    "source": "overleaf",
    "status": "contract-only",
    "hash": "sha256:..."
  }
}
```

Represents the contract-writing step before implementation.

### `PrimitiveMaterialized`

```json
{
  "type": "PrimitiveMaterialized",
  "artifact": "~/ed/libexec/ed/overleaf",
  "payload": {
    "source": "overleaf",
    "hash": "sha256:..."
  }
}
```

Represents the executable becoming real and runnable.

### `PrimitiveProbeCompleted`

```json
{
  "type": "PrimitiveProbeCompleted",
  "payload": {
    "source": "overleaf",
    "command": ["~/ed/libexec/ed/overleaf", "--query", "test"],
    "exit_code": 0,
    "ok": true
  }
}
```

Represents the validation probe after contract or materialization.

### `PrimitiveManifestUpdated`

```json
{
  "type": "PrimitiveManifestUpdated",
  "artifact": "~/ed/state/sources-manifest.yaml",
  "payload": {
    "source": "overleaf",
    "status": "active"
  }
}
```

Represents the mutation of `state/sources-manifest.yaml`, which is the durable lifecycle index for materialized primitives.

### `WorkflowRecommended`

```json
{
  "type": "WorkflowRecommended",
  "payload": {
    "slug": "sources-research-consult-report",
    "title": "Sources → Research → Consult → Report",
    "source": "search_sidecar",
    "score": 0.87,
    "query": "claim continuity graph"
  }
}
```

Represents a workflow recommendation emitted by runtime preflight before the skill starts.

### `WorkflowUsedObserved`

```json
{
  "type": "WorkflowUsedObserved",
  "artifact": "blog/entries/2026-04-23-example.md",
  "payload": {
    "slug": "sources-research-consult-report",
    "mode": "used"
  }
}
```

Represents a workflow explicitly cited as having worked in a published artifact.

### `WorkflowBrokenObserved`

```json
{
  "type": "WorkflowBrokenObserved",
  "artifact": "blog/entries/2026-04-23-example.md",
  "payload": {
    "slug": "stale-playwright-validation",
    "mode": "broken"
  }
}
```

Represents a workflow explicitly cited as broken/outdated in a published artifact.

### `WorkflowIgnoredObserved`

```json
{
  "type": "WorkflowIgnoredObserved",
  "payload": {
    "slug": "sources-research-consult-report",
    "reason": "recommended_not_cited"
  }
}
```

Represents a workflow recommendation that the cycle ignored instead of citing as used or broken.

### `PrimitiveBypassObserved`

```json
{
  "type": "PrimitiveBypassObserved",
  "payload": {
    "source": "arxiv",
    "capability": "source.arxiv",
    "reason": "primitive_used_without_capability_wrapper",
    "primitive_invocations": 2,
    "capability_invocations": 0
  }
}
```

Represents substrate discipline drift: a primitive was invoked directly when a capability wrapper existed.

### `ProviderProbeCompleted`

```json
{
  "type": "ProviderProbeCompleted",
  "payload": {
    "provider": "openai",
    "ok": true,
    "status": "ok",
    "http_status": "200",
    "probe": "check-quality"
  }
}
```

Represents a concrete provider/API availability probe executed by the runtime.

### `HealthComponentObserved`

```json
{
  "type": "HealthComponentObserved",
  "payload": {
    "name": "runtime_flow",
    "status": "degraded",
    "detail": "started=12 closed=10 dispatched=8"
  }
}
```

Represents one health component/check result written into `health/raw/*.json`.

### `HealthSnapshotComputed`

```json
{
  "type": "HealthSnapshotComputed",
  "payload": {
    "status": "degraded",
    "score": 72,
    "hard_fail": false,
    "dimensions": {
      "runtime_flow": {"status": "degraded", "score": 58},
      "continuity": {"status": "degraded", "score": 54}
    }
  }
}
```

Represents the final health v2 snapshot after all component checks and event-backed dimensions have been rolled up.

## Projection Inputs

The first projections depend on this subset:

- `dispatch-completeness` reads `CycleStarted`, `SkillDispatched`, and `CycleClosed`
- `pipeline-state` reads `PhaseCompleted` and `ArtifactPublished`
- `render-install-drift` reads `RenderProduced`, `InstallApplied`, `InstallRemoved`, and `InstallCheckObserved`

## Compatibility Rule

Existing logs may still use:

- `timestamp`
- ad hoc `event_id`
- free-form summaries
- event files split by date

These can coexist during migration, but dual-write adapters must normalize them into the envelope above when writing to `state/events/log.jsonl`.

## Rejected For V1

The following are explicitly out of scope for the first envelope version:

- modeling every signal as its own top-level event type
- embedding full artifact content in the ledger
- command objects in the same file as facts
- daemon-only ownership of the writer

The first version is for replayable cycle integrity, not complete operational history.
