---
name: ed-heartbeat
description: "Autonomous heartbeat dispatcher. Router-only beat entrypoint for the internal skill loop."
user-invocable: true
---

# Heartbeat

The heartbeat is a router, not a worker.

Its job is to choose the next internal skill and dispatch it quickly.

## Direct Slash Re-entry

If `EDGE_CYCLE_ID` is empty, this slash command was invoked directly inside
Claude instead of through `edge-runner`. Do not open a cycle manually in that
case. Re-enter through the canonical wrapper so the parent runner owns
preflight, dispatch, follow-on skill execution, postflight, and foreground
output:

```bash
if [ -z "${EDGE_CYCLE_ID:-}" ]; then
  EDGE_HEARTBEAT_FOREGROUND=1 ~/.local/bin/heartbeat.sh
fi
```

After that command returns, stop. Do not call `edge-dispatch open`,
`edge-dispatch dispatch`, or `edge-close` from the direct slash process.

## What The Runtime Already Did

By the time this skill starts, the runtime already handled the mechanical layer:

- opened the cycle
- ran preflight
- captured health, inbox, claims, workflows, capabilities, corpus coverage, and queue state
- computed `operator_pressure_digest`
- computed `beat_launch_context`
- prepared `heartbeat_routing`
- blocked inline artifact publication before dispatch

Do not redo those steps manually inside the heartbeat.

## What This Skill Must Do

1. Read the runtime context already injected into the request.
2. Choose exactly one internal skill.
3. Dispatch it immediately.
4. Stop.

The dispatched skill owns:

- search rounds
- Feynman / first-principles / adversarial checkpoints
- synthesis
- artifact drafting
- publication
- postflight

## Inputs To Trust

Use these runtime fields as authoritative:

- `request.async_inbox`
- `request.heartbeat_routing`
- `request.dispatch_queue_summary`
- `request.beat_launch_context`
- `request.health_snapshot`
- `request.workflow_status`

`beat_launch_context` is the best short-lived launch frame for this beat. It already composes:

- recent operator signal
- current edge-state signal
- the exploration budget

## Routing Policy

Choose the next skill in this order:

1. `dispatch_queue_summary.head`
If there is an explicit queued skill, dispatch it.

2. `heartbeat_routing.priority_hints`
If inbox or runtime hints are present, dispatch the best-fitting internal skill for that pressure.

3. `beat_launch_context.signal_from_operator_now`
If operator pressure is dominant right now, choose the skill that best reduces it.

4. `beat_launch_context.signal_from_edge_state_now`
If the edge state is the stronger signal, choose the skill that best responds to it.

5. `heartbeat_routing.suggested_skill`
If nothing outranks fairness, dispatch the round-robin candidate.

## Default Skill Heuristics

Use simple defaults:

- `reflection`
  - operator correction
  - confusion
  - contradictory state
  - diagnosis

- `autonomy`
  - operational change
  - substrate adjustment
  - doing the next concrete move

- `report`
  - synthesizing a situation clearly for operator consumption

- `research`
  - unresolved question
  - evidence gap
  - investigation needed before action

- `map`
  - landscape / structure / taxonomy / comparison

- `discovery`
  - no strong signal dominates
  - exploration is appropriate

- `strategy`
  - sequencing, prioritization, or medium-horizon direction

If multiple skills are plausible, prefer:

1. the one that reduces immediate operator pain
2. then the one that addresses the strongest edge-state signal
3. then the fairness candidate

## Dispatch

Dispatch exactly once:

```bash
edge-dispatch dispatch --skill <skill>
```

After dispatch succeeds, stop doing substantive work as heartbeat.

## Invariants

- The heartbeat is a router, not a worker.
- It must dispatch exactly one internal skill.
- It must not do substantive work inline after dispatch.

## Failure Rule

If no better candidate exists and routing data is somehow missing or stale:

- dispatch `discovery`

The heartbeat must not end without dispatching one internal skill.

## Direct Invocation

Direct `/ed-heartbeat` invocation is still a full beat.

It is not a preview and not a planning-only mode.

The heartbeat still must run through the normal lifecycle. Direct slash
invocation re-enters via `~/.local/bin/heartbeat.sh`; it does not manually
manage the lifecycle.

## Router-only rule:

The heartbeat does not draft the final artifact.

After `edge-dispatch dispatch --skill <skill>` succeeds, stop doing inline work as heartbeat.
