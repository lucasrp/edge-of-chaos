---
name: ed-heartbeat
description: "Autonomous heartbeat dispatcher. Router-only beat entrypoint for the internal skill loop."
user-invocable: true
---

# Heartbeat

The heartbeat is a router, not a worker.

Its only job is to choose one internal skill, dispatch it, and stop.

## Launch Frame

Assume the cycle is already open and routing fields are already prepared. Do not redo lifecycle work inside this skill.

If `/ed-heartbeat` is invoked directly without `EDGE_CYCLE_ID`, re-enter through the canonical wrapper and then stop:

```bash
if [ -z "${EDGE_CYCLE_ID:-}" ]; then
  EDGE_HEARTBEAT_FOREGROUND=1 ~/.local/bin/heartbeat.sh
fi
```

Do not call `edge-dispatch open` or `edge-close` from the direct slash process.

## Inputs

Use the prepared request fields:

- `request.dispatch_queue_summary`
- `request.heartbeat_routing`
- `request.beat_launch_context`
- `request.async_inbox`
- `request.health_snapshot`
- `request.workflow_status`

`beat_launch_context` is the short-lived launch frame for the beat. Use it to compare operator pressure, edge-state pressure, and exploration budget.

## Routing Order

Choose the next skill in this order:

1. `dispatch_queue_summary.head`: explicit queued work wins.
2. `heartbeat_routing.priority_hints`: runtime/inbox hints beat fairness.
3. `beat_launch_context.signal_from_operator_now`: reduce immediate operator pressure.
4. `beat_launch_context.signal_from_edge_state_now`: address the strongest internal state signal.
5. `heartbeat_routing.suggested_skill`: fall back to the round-robin candidate.

If routing data is missing or stale, dispatch `discovery`.

## Skill Heuristics

- `reflection`: correction, confusion, contradictory state, diagnosis.
- `autonomy`: operational change, substrate adjustment, concrete internal action.
- `report`: clear synthesis for operator consumption.
- `research`: unresolved question, evidence gap, investigation before action.
- `map`: landscape, structure, taxonomy, comparison.
- `discovery`: no dominant signal, open exploration.
- `strategy`: sequencing, prioritization, medium-horizon direction.

If multiple skills are plausible, choose the one that best reduces immediate operator pain, then the strongest edge-state signal, then the fairness candidate.

## Dispatch

Dispatch exactly once:

```bash
edge-dispatch dispatch --skill <skill>
```

After dispatch succeeds, stop doing substantive work as heartbeat.

## Invariants

- Dispatch exactly one internal skill.
- Do not draft artifacts.
- Do not perform the dispatched skill's analysis inline.
- Do not end the heartbeat without a dispatch.
