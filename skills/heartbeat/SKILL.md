---
name: ed-heartbeat
description: "Autonomous heartbeat dispatcher. Router-only beat entrypoint for the internal skill loop."
user-invocable: true
---

# Heartbeat

The heartbeat is a router with one internal curation phase, not a worker.

Its job is to consume the prepared `beat_context`, choose one action skill,
dispatch it, and stop.
It must dispatch exactly one internal skill.

Direct `/ed-heartbeat` invocation is still a full beat.

## Launch Frame

### Direct Slash Re-entry

Assume the cycle is already open and routing fields are already prepared. Do not redo lifecycle work inside this skill.

If `/ed-heartbeat` is invoked directly without `EDGE_CYCLE_ID`, re-enter through the canonical wrapper and then stop:

```bash
if [ -z "${EDGE_CYCLE_ID:-}" ]; then
  EDGE_HEARTBEAT_FOREGROUND=1 ~/.local/bin/heartbeat.sh
fi
```

Do not call `edge-dispatch open` or `edge-close` from the direct slash process.
The direct invocation re-enters via `~/.local/bin/heartbeat.sh`; do not recreate the lifecycle by hand.

## Inputs

Use the prepared request fields:

- `request.dispatch_queue_summary`
- `request.heartbeat_routing`
- `request.beat_context`
- `request.self_healing`
- `request.beat_launch_context`
- `request.async_inbox`
- `request.health_snapshot`

`beat_launch_context` is the short-lived launch frame for the beat. Use it to compare operator pressure, edge-state pressure, and exploration budget.

`beat_context` is produced by internal heartbeat curation before dispatch. It is
ephemeral state, not an artifact. Treat its `what_is_broken`,
`what_matters_now`, `dispatch_recommendation`, and `injected_context` as the
compact interpretation that replaces the old heartbeat meta-skill round as
heartbeat dispatches.

Primitive self-healing has already run deterministically in preflight. If `request.self_healing.needs_llm` is non-empty, dispatch `autonomy` as the exceptional repair lane; autonomy must investigate/log the primitive failure without producing a publication artifact.

## Routing Order

Choose the next skill in this order:

1. `dispatch_queue_summary.head`: explicit queued work wins.
2. `request.self_healing.needs_llm`: unknown primitive failure dispatches `autonomy`.
3. `request.beat_context.dispatch_recommendation`: curation recommendation for this beat.
4. `heartbeat_routing.priority_hints`: runtime/inbox hints beat fairness.
5. `beat_launch_context.signal_from_operator_now`: reduce immediate operator pressure.
6. `beat_launch_context.signal_from_edge_state_now`: address the strongest internal state signal.
7. `heartbeat_routing.suggested_skill`: fall back to the action-skill rotation candidate.

If routing data is missing or stale, dispatch `discovery`.

## Skill Heuristics

- `autonomy`: exceptional primitive repair from self-healing or concrete substrate action requested by operator/runtime.
- `report`: clear synthesis for operator consumption.
- `research`: unresolved question, evidence gap, investigation before action.
- `discovery`: no dominant signal, open exploration.
- `planner`: sequencing, implementation plan, next concrete project step.

If multiple skills are plausible, choose the one that best reduces immediate operator pain, then the strongest edge-state signal, then the fairness candidate.

There is no meta/content round-robin. Do not dispatch deleted meta skills from
heartbeat. Curation is already done inside preflight and persisted only as
`state/beat-context.json` for the current beat.

## Dispatch

Router-only rule: the heartbeat dispatches the next skill and does not draft the final artifact.

Dispatch exactly once:

```bash
edge-dispatch dispatch --skill <skill>
```

After `edge-dispatch dispatch --skill <skill>` succeeds, stop doing inline work and stop doing substantive work as heartbeat.

## Invariants

- Dispatch exactly one internal skill.
- Do not draft artifacts.
- Do not perform the dispatched skill's analysis inline.
- Do not end the heartbeat without a dispatch.
