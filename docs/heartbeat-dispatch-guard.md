# Heartbeat Dispatch Guard (#212)

Enforces the `/ed-heartbeat` invariant: **every beat dispatches exactly one skill before producing artifacts**. Implements L3 (executable hook) from the enforcement-ladder research (2026-04-09).

## Problem

`/ed-heartbeat` Step 2 is explicit: "ABSOLUTE RULE: The heartbeat ALWAYS dispatches a skill. There is no empty beat." Under strong operator signal ("do X now"), the agent can short-circuit Step 2 and produce artifacts (blog entries, reports) directly, bypassing `edge-consult` review, `edge-skill-step` telemetry, and `post-skill.md` procedures.

Reported in [issue #212](https://github.com/lucasrp/edge-of-chaos/issues/212).

## Solution

Three components:

1. **Sentinel file** (`$EDGE_ROOT/state/current-beat.json`) — written at Step 2 entry, flipped at skill dispatch, cleared at Step 3 end.
2. **PreToolUse hook** (`bin/heartbeat-dispatch-guard.sh`) — refuses `Write`/`Edit` into `~/edge/blog/entries/**` and `~/edge/reports/**` when the sentinel says active but no skill dispatched.
3. **SKILL.md lifecycle** — writes added at Step 2.0 (open), inside Dispatch (flip), Step 3e (close).

## Sentinel schema

```json
{
  "active": true,
  "started_at": "2026-04-16T22:30:00+00:00",
  "skill_dispatched": false,
  "skill": null
}
```

| Field | When written | Meaning |
|-------|--------------|---------|
| `active` | Step 2.0 → true; Step 3e → false | beat is in-flight |
| `started_at` | Step 2.0 | auto-expires sentinel after 1h (fail-open) |
| `skill_dispatched` | immediately before `edge-skill-step start` | unblocks artifact writes |
| `skill` | same time as dispatched flip | name of dispatched skill |

## Hook behavior

- Target paths: anything containing `/edge/blog/entries/` or `/edge/reports/`
- No sentinel file → allow (not in heartbeat)
- Sentinel `active=false` → allow (beat closed)
- Sentinel older than 1h → allow (fail-open; abandoned beat)
- Sentinel `skill_dispatched=true` → allow
- Otherwise → block (exit 2, message to stderr)

The hook is conservative on malformed input, unreadable sentinel, and unparseable JSON — all fail open. The narrow binary invariant (heartbeat active AND skill not dispatched AND writing guarded path) is the only block condition.

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
| Heartbeat abandoned mid-beat | Sentinel ages past 1h → allow on next write |
| Sentinel file corrupted | JSON parse fails → allow (fail open) |
| Hook script missing | Claude Code hook system passes through → no block |
| Skill writes artifact legitimately | Sentinel `skill_dispatched=true` → allow |
| Heartbeat tries to publish without dispatch | Block, message directs to run `edge-skill-step start` |

## Testing

1. Open sentinel manually:
   ```bash
   python3 -c "import json, datetime, pathlib; p=pathlib.Path.home()/'edge/state/current-beat.json'; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({'active':True,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'skill_dispatched':False,'skill':None}))"
   ```
2. Attempt a Write into `~/edge/blog/entries/test.md` via Claude Code — hook should block.
3. Flip sentinel:
   ```bash
   python3 -c "import json, pathlib; p=pathlib.Path.home()/'edge/state/current-beat.json'; s=json.loads(p.read_text()); s['skill_dispatched']=True; p.write_text(json.dumps(s))"
   ```
4. Retry Write — hook should allow.
5. Clear: set `active=false`.
