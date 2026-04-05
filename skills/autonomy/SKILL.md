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
   - `sources:` (yaml) vs `state/sources-manifest.yaml` → what's declared but not materialized?
   - `state/source-usage.jsonl` → what works? what's wasted? diversity?
   - `state/signals/` → friction, serendipity, strategy shifts?
   - `state/proposals.json` → active proposals: strengthen, remove stale, or add new

2. **Propose** (max 3 active, max 1 new per beat):
   - Each proposal: what, why, evidence, cost
   - Adversarial review before adding (edge-consult)
   - Proposal that survives 3+ revisions with growing evidence = strong signal
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

**Bootstrap** (first heartbeats, during first_steps):
- Create rough primitive as side-effect of the work
- Follow `docs/TOOL_CONTRACT.md` — contract + impl + test + register
- Blog entry (light): "created X, minimal, functional"
- No pool overhead — demand comes from the work itself

**Steady-state** (after bootstrap):
- Autonomy detects the gap in its evaluate phase
- Proposes materialization via the pool
- Creates with full discipline: contract, impl, test, adversarial, blog+report

**Deepening** (ongoing):
- Autonomy reviews existing primitives with usage evidence
- Proposes improvements: rate limiting, caching, slimmer output, new operations
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

## When to run

- Heartbeat meta rotation (every ~9 beats, alongside reflection/strategy)
- After gaining new access (new key, new host, new data)
- When friction signals accumulate

---

## Anti-gaming

- Max 1 new proposal per execution
- Adversarial before adding
- If operator rejects >70% of proposals, autonomy is miscalibrated — recalibrate
- Consolidar pipeline (blog + report + claims) for every action — no silent changes
