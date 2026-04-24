---
name: ed-autonomy
description: "Evaluate, workflow, act. Reads actual runtime state, improves primitives and agent-owned search/signal workflows, and materializes primitives on demand. It does not create skill proposals."
user-invocable: true
---

# Autonomy — Evaluate, Workflow, Act

Autonomy is the self-evolution skill.

Its job is not to rediscover raw state by hand. Its job is to read the current
read models, decide what is missing or wasteful, and act within scope.

It still produces a full-rite artifact every dispatch. Follow
`_shared/report-template.md` like every other `/ed-*` skill.

---

## The Job

1. **Evaluate** the current phenotype from read models
2. **Improve workflows** for agent-owned search/signal behavior
3. **Act** automatically when the scope is local and reversible
4. **Document** what changed, what remains missing, and what should wait for human directive

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

### 2. Source affordance digest

Read:

- `state/source-affordance-digest.json`

Use it to decide which atomic sources/channels work for which affordances
(`novelty`, `confirmation`, `continuity`, `operational_signal`, etc.).
The unit of learning is the source/channel, not the wrapper.

### 3. Operational signals

Read the relevant signals and current context:

- `~/edge/briefing.md`
- `state/signals/`
- recent artifacts when a workflow decision depends on concrete prior evidence

Prefer the digested state first. Read raw files only when you need details.

---

## Decision Policy

### Workflow limits

- no skill proposals
- no new `state/proposals.json` entries from autonomy
- max 1 workflow change or primitive materialization per run
- workflow changes need: what, why, evidence, cost

### Approval rules

| Action | Approval |
|---|---|
| Create or improve local primitive | Auto |
| Add or remove source | Auto |
| Record source/channel affordance grade | Auto |
| Update agent-owned search/signal workflow | Auto |
| Propose or create a new skill | Not allowed |
| Create a general proposal | Human |
| Modify runtime protocol procedure (`preflight.yaml`) | Human |
| Modify runtime protocol context (`preflight.yaml`) | Human |
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
- source/channel affordances repeatedly confirmed by ODIs
- search/signal workflows repeatedly rediscovered in artifacts

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
- consolidate repeated search/signal patterns into workflows

---

## Anti-Gaming

- More agency does not mean more surface area every beat.
- Repeated operator rejection means calibration is off.
- Primitive work without evidence from `edge-cap status --json` or
  recent usage is weak.
- Do not convert uncertainty into a skill proposal. Convert repeated search or
  signal evidence into workflow learning, or leave it for human directive.

---

## Hard Rules

- Do not hand-edit `state/sources-manifest.yaml` when lifecycle commands exist.
- Do not infer primitive health from one file when the read model exists.
- Do not create skill proposals.
- Do not create new `state/proposals.json` entries.
- Do not escalate to human approval for things that are explicitly auto-local.
- Do not skip the full artifact rite when autonomy makes a real change.
