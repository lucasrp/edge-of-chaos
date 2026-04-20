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
    "trigger": "heartbeat"
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
    "dispatch_mode": "normal"
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

## Projection Inputs

The first projections depend on this subset:

- `dispatch-completeness` reads `CycleStarted`, `SkillDispatched`, and `CycleClosed`
- `pipeline-state` reads `PhaseCompleted` and `ArtifactPublished`
- `render-install-drift` reads `RenderProduced`, `InstallApplied`, and `InstallCheckObserved`

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
