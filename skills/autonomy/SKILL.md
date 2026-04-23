---
name: ed-autonomy
description: "Evaluate, propose, act. Reads actual runtime state, proposes changes to the agent's phenotype (primitives, workflows, policies, config projections), and materializes primitives on demand. Meta-skill — heartbeat triggers based on gaps, patterns, or waste detected in usage data."
user-invocable: true
---

# Autonomy — Evaluate, Propose, Act

Autonomy is the self-evolution skill.

Its job is not to rediscover raw state by hand. Its job is to read the current
read models, decide what is missing or wasteful, and act within scope.

It still produces a full-rite artifact every dispatch. Follow
`_shared/report-template.md` like every other `/ed-*` skill.

---

## The Job

1. **Evaluate** the current phenotype from read models
2. **Propose** at most one new change per beat
3. **Act** automatically when the scope is local and reversible
4. **Document** what changed, what remains missing, and what should wait

---

## Primary Inputs

### 1. Primitive status is the canonical source

Use:

```bash
edge-cap status --json --skill autonomy
```

This is the main scoreboard for capability coverage. It already joins:

- static CLI wrappers from `config/capabilities.yaml`
- runtime-declared and materialized primitives
- recent capability probes/invocations

When you need primitive-specific details, drill down with:

```bash
edge-primitives status --json
```

That primitive read model already joins:

- `state/sources-manifest.yaml`
- local meta/binary files
- recent usage
- recent probe history

Do not manually diff raw files when the read model already explains the state.

Important statuses:

- `active`
- `probed`
- `degraded`
- `broken`

Use `manifest_status` and `problems` for the distinction between a merely
declared source and a contract-written source that still is not activated.

### 2. Proposal pool

Read:

- `state/proposals.json`

Use it to strengthen, revise, or remove existing proposals before creating a
new one.

### 3. Operational signals

Read the relevant signals and current context:

- `~/edge/briefing.md`
- `state/signals/`
- recent artifacts when a proposal depends on concrete prior evidence

Prefer the digested state first. Read raw files only when you need details.

---

## Decision Policy

### Proposal limits

- max 3 active proposals total
- max 1 new proposal in this run
- proposals need: what, why, evidence, cost

### Approval rules

| Action | Approval |
|---|---|
| Create or improve local primitive | Auto |
| Add or remove source | Auto |
| Propose workflow | Auto |
| Modify activation procedure (`pre-skill.md`) | Human |
| Modify activation context (`pre-skill.md`) | Human |
| External action | Human |

Autonomy should spend most beats pruning, deepening, or materializing, not
opening new fronts.

---

## Primitive Lifecycle

When autonomy works on primitives, use the lifecycle commands, not hand-edits.

### Contract

```bash
edge-primitive-lifecycle contract <name> --description "..."
```

Use this when a source is declared but not yet specified well enough to build.

### Materialize

Write the executable, then register it:

```bash
edge-primitive-lifecycle materialize <name>
```

### Probe

Validate the primitive explicitly:

```bash
edge-primitive-lifecycle probe <name> -- <probe command>
```

### Readback

After any lifecycle mutation, read the status again:

```bash
edge-cap status --json --skill autonomy
```

That readback is the canonical proof of the new state.

---

## What to Look For

Strong autonomy candidates:

- `degraded` primitives with real usage pressure
- `active` primitives never probed
- `broken` or `degraded` primitives affecting current work
- workflows repeatedly rediscovered in artifacts
- stale proposals that no longer have evidence

Weak candidates:

- optional declared sources with no demand
- cosmetic rewrites without operational payoff
- speculative additions with no evidence trail

---

## Bootstrap vs Steady State

### Bootstrap

Early in a new instance, autonomy may materialize rough primitives quickly to
reduce friction. Keep them small, local, and functional.

### Steady state

Later, autonomy should mostly:

- harden frequently used primitives
- probe what exists
- remove drift
- consolidate repeated operator patterns into workflows

---

## Anti-Gaming

- More agency does not mean more surface area every beat.
- A removed proposal is often healthier than a forced one.
- Repeated operator rejection means calibration is off.
- Primitive work without evidence from `edge-cap status --json` or
  recent usage is weak.

---

## Hard Rules

- Do not hand-edit `state/sources-manifest.yaml` when lifecycle commands exist.
- Do not infer primitive health from one file when the read model exists.
- Do not create more than one new proposal in a run.
- Do not escalate to human approval for things that are explicitly auto-local.
- Do not skip the full artifact rite when autonomy makes a real change.
