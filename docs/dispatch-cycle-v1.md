# Dispatch Cycle V1

PR 1 introduces a shadow dispatch envelope so heartbeat-triggered and
operator-triggered work can share one runtime shape without making the new path
authoritative yet.

## Goal

Move the lifecycle boundary from prose and trigger-specific habits toward one
typed cycle:

1. `open`
2. `dispatch`
3. `close`

The trigger still matters, but only as request metadata.

## DispatchRequest

Persisted inside `state/current-dispatch.json`:

```json
{
  "trigger": "heartbeat",
  "skill": "research",
  "args": {
    "thread_id": "self-healing-pillars"
  },
  "policy": "autonomous",
  "routing_mode": "auto",
  "preflight_profile": "heartbeat_default",
  "postflight_profile": "standard",
  "opened_by": "ed"
}
```

Canonical trigger values:

- `heartbeat`
- `operator`

The CLI still accepts `user` as a legacy alias and normalizes it to
`operator`.

## DispatchCycleState

Also persisted in `state/current-dispatch.json`:

```json
{
  "active": true,
  "phase": "skill_dispatched",
  "skill_dispatched": true,
  "preflight_status": "pending",
  "skill_status": "running",
  "postflight_status": "pending",
  "close_status": null,
  "opened_at": "2026-04-20T19:30:00+00:00",
  "updated_at": "2026-04-20T19:31:12+00:00",
  "dispatched_at": "2026-04-20T19:31:12+00:00",
  "closed_at": null,
  "close_reason": null
}
```

`cycle_id` sits beside these blocks and is the correlation key for shadow
events.

## CLI

Examples:

```bash
edge-dispatch open --trigger heartbeat --policy autonomous --routing-mode auto
edge-dispatch dispatch --skill research
edge-dispatch close --status completed
```

```bash
edge-dispatch open --trigger operator --skill reflection --arg topic=enforcement
edge-dispatch dispatch --skill reflection
edge-dispatch close --status completed
```

Default profiles:

- heartbeat → `preflight_profile=heartbeat_default`
- operator → `preflight_profile=operator_default`
- all triggers → `postflight_profile=standard`

## Shadow Rollout

- `edge-runner` owns mechanical `edge-dispatch open` / `close` for heartbeat entrypoints
- `edge-dispatch open` emits `CycleStarted`
- `edge-dispatch dispatch` emits `SkillDispatched`
- `edge-dispatch close` emits `CycleClosed`
- heartbeat cycles still mirror `state/current-beat.json`
- `bin/heartbeat-dispatch-guard.sh` prefers `current-dispatch.json` and falls
  back to the legacy beat sentinel only when needed

This PR intentionally does not make dispatch authoritative yet. The point is to
dual-write a cycle model that can be observed and replayed before stronger
enforcement lands.
