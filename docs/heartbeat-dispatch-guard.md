# Heartbeat Dispatch Guard (#212)

Enforces the `/ed-heartbeat` invariant: **every beat dispatches exactly one skill before producing artifacts**. Implements L3 (executable hook) from the enforcement-ladder research (2026-04-09).

## Problem

`/ed-heartbeat` Step 2 is explicit: "ABSOLUTE RULE: The heartbeat ALWAYS dispatches a skill. There is no empty beat." Under strong operator signal ("do X now"), the agent can short-circuit Step 2 and produce artifacts (blog entries, reports) directly, bypassing `edge-consult` review, `edge-skill-step` telemetry, and the canonical `postflight.yaml` / `edge-postflight` path.

Reported in [issue #212](https://github.com/lucasrp/edge-of-chaos/issues/212).

## Solution

Three components:

1. **Dispatch-cycle file** (`$EDGE_ROOT/state/current-dispatch.json`) — opened by the heartbeat entrypoint, updated at skill dispatch, closed after the skill exits.
2. **Legacy mirror** (`$EDGE_ROOT/state/current-beat.json`) — still written for heartbeat cycles during rollout so older checks keep working.
3. **PreToolUse hook** (`bin/heartbeat-dispatch-guard.sh`) — refuses `Write`/`Edit` into `~/edge/blog/entries/**` and `~/edge/reports/**` when an active heartbeat cycle has not dispatched a skill yet.
4. **Heartbeat skill body** — still performs `edge-dispatch dispatch` when the real work skill is chosen, but no longer opens/closes the cycle itself.

## Dispatch-cycle schema

```json
{
  "cycle_id": "cycle-20260420T193000Z-a1b2c3",
  "request": {
    "trigger": "heartbeat",
    "skill": null,
    "args": {},
    "policy": "autonomous",
    "routing_mode": "auto",
    "preflight_profile": "heartbeat_default",
    "postflight_profile": "standard"
  },
  "state": {
    "active": true,
    "phase": "opened",
    "skill_dispatched": false,
    "opened_at": "2026-04-20T19:30:00+00:00",
    "updated_at": "2026-04-20T19:30:00+00:00"
  }
}
```

| Field | When written | Meaning |
|-------|--------------|---------|
| `request.trigger` | heartbeat entrypoint / operator entrypoint | whether the cycle came from heartbeat or operator |
| `request.skill` | open or dispatch | requested/dispatched skill |
| `state.active` | entrypoint open → true; entrypoint close → false | cycle is in-flight |
| `state.opened_at` | entrypoint open | auto-expires heartbeat protection after 1h (fail-open) |
| `state.skill_dispatched` | immediately before `edge-skill-step start` | unblocks artifact writes |

## Hook behavior

- Target paths: anything containing `/edge/blog/entries/` or `/edge/reports/`
- No state file → allow (not in heartbeat)
- Active operator dispatch cycle → allow
- Heartbeat cycle `active=false` → allow (beat closed)
- Heartbeat cycle older than 1h → allow (fail-open; abandoned beat)
- Heartbeat cycle `skill_dispatched=true` → allow
- Otherwise → block (exit 2, message to stderr)

The hook prefers `current-dispatch.json` when present. It only falls back to the
legacy beat sentinel when no active dispatch-cycle state is available. Malformed
input, unreadable state, and unparseable JSON all fail open. The narrow binary
invariant (heartbeat active AND skill not dispatched AND writing guarded path) is
the only block condition.

## Wire-up

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/edge/bin/heartbeat-dispatch-guard.sh"
          }
        ]
      }
    ]
  }
}
```

## Why L3 is appropriate here

The enforcement-ladder research (`blog/entries/2026-04-09-research-enforcement-mechanisms-agent-compliance.md`) argues:

> L3 hooks are appropriate for **binary invariants only**. For non-binary judgments (quality, relevance, style), hooks Goodhart.

"Heartbeat active AND no skill dispatched AND writing artifact path" is a pure binary predicate — no ambiguity, no quality dimension. Ideal L3 target.

## Interaction with Step 2.95

Step 2.95 (prose-level post-hoc check) is **not removed**. It remains as a mechanical double-check that reads `skill-steps.jsonl` after work is done. The hook is the early L3 gate; Step 2.95 is the late L1/L2 audit. Defense in depth.

If the hook ever fires, Step 2.95 would also flag the same beat — but the hook prevents the bad artifact from ever being written, while Step 2.95 only observes that it was.

## Failure modes

| Scenario | Outcome |
|----------|---------|
| Operator-driven edit (not in a heartbeat) | No sentinel → allow |
| `/ed-execute` direct work | No sentinel → allow |
| Heartbeat abandoned mid-beat | State ages past 1h → allow on next write |
| State file corrupted | JSON parse fails → allow (fail open) |
| Hook script missing | Claude Code hook system passes through → no block |
| Skill writes artifact legitimately | Dispatch state `skill_dispatched=true` → allow |
| Heartbeat tries to publish without dispatch | Block, message directs to run `edge-dispatch dispatch` then `edge-skill-step start` |

## Testing

1. Open a heartbeat cycle:
   ```bash
   edge-runner skill --skill /ed-heartbeat --dispatch-trigger heartbeat --dispatch-policy autonomous --dispatch-routing-mode auto --dispatch-preflight-profile heartbeat_default --dispatch-postflight-profile standard --dispatch-force
   ```
2. Attempt a Write into `~/edge/blog/entries/test.md` via Claude Code before the skill dispatches — hook should block.
3. Mark the skill as dispatched:
   ```bash
   edge-dispatch dispatch --skill research
   ```
4. Retry Write — hook should allow.
