---
name: ed-autonomy
description: "Evaluate, propose, act. Reads declared vs actual state, proposes changes to the agent's phenotype (sources, workflows, routines, config), and materializes primitives on demand. Meta-skill — heartbeat triggers based on gaps, patterns, or waste detected in usage data."
user-invocable: true
---

# Autonomy — Evaluate, Propose, Act

The agent's self-evolution mechanism. Reads declared state vs actual state,
proposes changes, acts on what's approved. Produces blog + report like
every skill — plus operational changes (primitives, workflows, config).

**Principle:** more agency = more quality. But agency without initiative
is just a bigger toolbox. The value is in seeing what nobody asked for.

---

## The Job

1. **Evaluate** — read, don't discover. Everything is declarative now:
   - `state/dispatch-queue.json` → pending requests from other meta-skills (read FIRST)
   - `state/telemetry-digest.json` → quantitative operational facts (fail rates, cost, anomalies)
   - `sources:` (yaml) vs `state/sources-manifest.yaml` → what's declared but not materialized?
   - `state/source-usage.jsonl` → what works? what's wasted? diversity?
   - `state/signals/` → friction, serendipity, strategy shifts?
   - `state/proposals.json` → shared backlog: proposals from strategy, reflection, and autonomy

   **Smoke test active primitives** (every autonomy beat):
   For each primitive with `status: active` in `sources-manifest.yaml`,
   run it with a minimal probe query and verify exit 0. Log results.
   If a primitive that was active now fails (exit 1, timeout, auth error),
   mark as `status: broken` in the manifest and add to the remediation
   list for this beat. This catches: expired API keys, changed endpoints,
   broken dependencies — before they silently degrade a content beat.

   **Read dispatch queue first:**
   ```bash
   python3 -c "
   import json, os
   f = os.path.expanduser('~/edge/state/dispatch-queue.json')
   if os.path.exists(f):
       queue = json.load(open(f))
       mine = [q for q in queue if q.get('skill') == 'autonomy']
       if mine:
           for item in mine:
               print(f'DISPATCH from {item.get(\"source\",\"?\")}: {item.get(\"reason\",\"\")}')
           remaining = [q for q in queue if q.get('skill') != 'autonomy']
           with open(f, 'w') as fh:
               json.dump(remaining, fh, indent=2)
       else:
           print('No pending dispatches.')
   else:
       print('No dispatch queue.')
   " 2>/dev/null
   
   # Telemetry digest
   cat ~/edge/state/telemetry-digest.json 2>/dev/null || echo "(no telemetry digest)"
   ```
   
   Dispatches from reflection ("edge-x broken, can't fix") and strategy ("source X is priority") inform which proposals to act on first. Telemetry provides quantitative evidence.

2. **Curate and EXECUTE proposals** — autonomy is the curator of `state/proposals.json` AND the executor:

   ```bash
   cat ~/edge/state/proposals.json 2>/dev/null || echo "[]"
   ```

   **Curation rules:**
   - Proposal with evidence from 2+ distinct skills → **strong**, execute NOW
   - Proposal with evidence from 1 skill for 3+ beats → **mature**, execute NOW
   - Proposal without new evidence in 5 beats → **stale**, remove with note
   - Max 3 active proposals — if a 4th arrives, the weakest exits
   
   **Execution rules — be aggressive:**
   - **Execute everything auto-approved that fits in the beat.** Do not defer to the next beat what can be done now. A primitive that takes 10 minutes should be materialized immediately, not proposed and left for 27 hours.
   - If 3 primitives are auto-approved and each takes 10 minutes, **do all 3**. The limit is the beat's time budget, not an arbitrary "max 1" rule.
   - The cycle is **evaluate → curate → execute → verify** in a SINGLE beat. Proposing without executing when execution is auto-approved and feasible is a failure mode, not caution.
   - Adversarial review (edge-consult) before adding genuinely new, unvalidated proposals. But acting on existing proposals with strong evidence does NOT need another round of review.
   
   Strategy and reflection add proposals and evidence. Autonomy prioritizes, executes, and removes stale ones. See `~/.claude/skills/_shared/proposals-protocol.md`.
   
   - Proposal the agent removes = self-correction (positive)

3. **Act** — approval depends on scope:

   | Action | Approval | Why |
   |---|---|---|
   | Create/improve primitive (local, reversible) | Auto | Internal tooling |
   | Propose workflow (internal method) | Auto | Doesn't affect external state |
   | Add/remove source | Auto | Reversible, blog documents |
   | Add/remove routine (knowledge) | Auto | Knowledge, not execution |
   | Modify pre_skill_procedure | **Human** | Changes every future beat |
   | Modify pre_skill_context | **Human** | Changes agent knowledge every session |
   | External action (publish, send, create account) | **Human** | Leaves the agent |

---

## Materialization — Creating primitives on demand

When the agent tries to use a source and the primitive doesn't exist
(exit 127) or an operation isn't built yet (exit 77):

**The rule: if the key exists and the contract is documented, materialize NOW.**
Do not propose what you can build. A stub primitive with a working API key
is a bug, not a proposal. Fix it in the same beat you discover it.

**Bootstrap** (first heartbeats):
- Create rough primitives as side-effect of the work
- Follow `docs/TOOL_CONTRACT.md` — contract + impl + test + register
- Blog entry (light): "created X, minimal, functional"
- Multiple primitives per beat is expected — batch them

**Steady-state** (after bootstrap):
- Autonomy detects gaps in evaluate phase and **executes immediately**
- If auto-approved and key is available → build, test, register, log
- Full discipline: contract, impl, test, adversarial, blog+report
- If 5 primitives need building and the beat has time → build 5

**Deepening** (ongoing):
- Autonomy reviews existing primitives with usage evidence
- Improves: rate limiting, caching, slimmer output, new operations
- Full adversarial + consolidar pipeline

---

## Workflows — Learning from usage

When the usage log shows a repeated pattern (e.g., "arxiv with math.AP
filter + date sort works 4x better"), autonomy can propose a workflow:

- Workflow = learned method, auto-approved (internal, no external side effect)
- Published via blog entry with tag `workflow`, enters reinforcement loop
- Can later be promoted to routine if the operator wants it every beat

Removal works the same way: if a workflow never gets used after N beats,
autonomy proposes removal. Blog documents why.

---

## State files

- `state/proposals.json` — pool of active proposals
- `state/sources-manifest.yaml` — materialized primitives (name, status, created)
- `state/source-usage.jsonl` — invocation log (source, query, ok/fail, duration)
- `docs/TOOL_CONTRACT.md` — contract for creating primitives

---

## Post-execution: Dispatch to other meta-skills

After acting, queue dispatches for what autonomy cannot resolve alone:

- **Created a new primitive** → queue for reflection (to validate in next beat)
- **Source not worth the cost** → queue for strategy (to reprioritize)
- **Proposal executed** → update `proposals.json` status to `done`

---

## When to run

- Heartbeat meta rotation (every ~9 beats, alongside reflection/strategy)
- After gaining new access (new key, new host, new data)
- When friction signals accumulate
- When dispatch queue has items addressed to autonomy

---

## Anti-gaming

- Adversarial review before adding genuinely new proposals (not before executing existing ones)
- If operator rejects >70% of proposals, autonomy is miscalibrated — recalibrate
- Consolidar pipeline (blog + report + claims) for every action — no silent changes
- The failure mode to guard against is **proposing without executing**, not executing too much. Volume of proposals is waste. Volume of shipped primitives is progress.
