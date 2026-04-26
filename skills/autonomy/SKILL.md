---
name: ed-autonomy
description: "Evaluate and improve the agent-owned operational substrate: capabilities, primitives, source/signal workflows, and local reversible automation. It does not create skill proposals or do product implementation."
user-invocable: true
---

# Autonomy — Operational Substrate

Use this skill when the agent should improve its own ability to work.

Autonomy is not strategy, reflection, or project execution. It evaluates the current capability substrate, finds missing or wasteful operational affordances, and attempts every substrate improvement it can reach.

## Responsibility

Autonomy owns the agent-owned operational substrate.

It is responsible for:

- capability and primitive coverage;
- source and signal workflows;
- local wrappers and probes;
- operational affordance learning;
- reducing repeated tool/search/signal friction;
- attempting substrate changes until they succeed or hit a concrete error.

A run is incomplete if it only observes missing capability and leaves no decision. Each finding must become one of:

- `act`: make local, reversible substrate improvements;
- `probe`: validate an existing primitive or capability;
- `workflow`: update or route a repeatable agent-owned workflow;
- `blocked`: tried, but a command, credential, permission, dependency, verification, or runtime error prevented completion;
- `route`: send product, strategy, planning, or reflection work to the right skill.

Autonomy does not own project delivery, product code, broad refactors, or skill creation.

It still reports every run. The difference is that the report is an operational accountability record, not a separate publication ritual. If autonomy acts, the report must make the action auditable: decision, evidence, changed surface, verification readback, residual risk, and next route.

## Runtime Boundary

Use the runtime-injected pre-skill context as the starting point.

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill. The runtime owns those mechanics.

When editing protected state or shared protocols, follow the shared state protocol. Prefer lifecycle tools and read models over hand-editing raw state.

Use the shared source lookup protocol only when a substrate decision depends on current external tool behavior, ecosystem practice, or comparable implementations.

## Primary Inputs

Use read models first:

```bash
edge-cap status --json --skill autonomy
edge-primitives status --json
```

These are the canonical sources for capability and primitive state. They combine configuration, materialized primitives, probe results, and recent usage.

Also inspect when relevant:

- `state/source-affordance-digest.json`;
- runtime capability and workflow status;
- operational signals such as autonomy, friction, cost, reflection, and serendipity;
- recent failed or repeated tool/search/signal paths;
- local workflow and primitive usage evidence.

Read raw manifests or logs only when the read model cannot answer the question.

## Decision Policy

Autonomy should sweep the whole substrate and try all substrate work it can reach in the current run. It should not stop after one primitive, and it should not skip a candidate just because it looks weak, speculative, or low priority.

The default is attempt. The only valid reason for not completing substrate work is that the attempt hit a real blocker: missing command, missing credential, permission failure, dependency failure, failing probe, verification mismatch, destructive-only path, or other concrete runtime error.

Limits:

- no skill proposals;
- no general proposal entries;
- no product implementation;
- every mutation needs intended effect and readback;
- batch actions must isolate failures so one broken item does not prevent independent attempts.

## Candidate Discovery

Treat all substrate candidates as attemptable unless they are outside autonomy's ownership.

Candidate examples:

- broken or degraded primitives blocking current work;
- active primitives that have never been probed;
- repeated manual search/signal/tool pattern that can become a local workflow;
- source/channel affordance repeatedly confirmed by actual use;
- local wrapper that removes recurring operational friction;
- stale primitive or workflow that is confusing routing or wasting effort.

Weak demand is not a reason to skip. If a candidate can be attempted cheaply inside the agent-owned substrate, try it. If the attempt fails, record the exact failure and continue.

## Primitive Lifecycle

Use lifecycle commands when they exist.

Contract:

```bash
edge-primitive-lifecycle contract <name> --description "..."
```

Materialize:

```bash
edge-primitive-lifecycle materialize <name>
```

Probe:

```bash
edge-primitive-lifecycle probe <name> -- <probe command>
```

Read back after mutation:

```bash
edge-cap status --json --skill autonomy
```

The readback is the proof. Do not infer success from the file edit alone.

## Method

### 1. Read The Substrate

Start from capability and primitive read models. Identify degraded, broken, unprobed, unused, duplicated, or high-friction items.

### 2. Build The Attempt Queue

For each candidate, define:

- what will be attempted;
- which command/file/tool is involved;
- how success will be verified;
- what error would block completion.

Do not discard candidates for low priority. Ordering is allowed; skipping before trying is not.

### 3. Attempt The Queue

Attempt every substrate action found in the sweep:

- probe existing capability;
- materialize or improve local primitives;
- update local source/signal workflows;
- remove or archive stale substrate items;
- route the issue elsewhere.

If an action requires a missing credential, missing dependency, unavailable network route, unavailable command, irreversible external mutation, or destructive-only path, attempt the smallest probe/setup/read-only version first. If that fails or proves impossible, record it as `blocked` with the exact error.

### 4. Apply Batch And Read Back

Before changing files, state the batch: what will be attempted and how each item will be verified.

After each mutation, run the relevant probe or status readback. If one item fails, handle that item without invalidating the whole batch: revert your own incomplete local mutation when appropriate, or mark that substrate item blocked/degraded with the exact error and continue with independent attempts.

### 5. Close With Decision

Return a concise operational report:

```markdown
Autonomy Sweep: <scope>
Actions Completed:
- <target> -> <action> -> <readback>

Blocked After Attempt:
- <target> -> <attempted action> -> <exact error/blocker>

Routed:
- <target> -> <skill/action>

Residual Risk: <what may still be wrong>
Next: <remaining work or next sweep focus>
```

## Routing

- repeated mistake or stale operating rule -> `ed-reflection`;
- stale claims, project sequencing, or action queue -> `ed-strategy`;
- external-practice question after local attempt fails -> `ed-research`;
- product or implementation plan -> `ed-planner`;
- internal relationships between capabilities, workflows, and projects -> `ed-map`;
- current state summary -> status/context tool.

## Invariants

- Read models before raw files.
- Sweep the whole substrate and attempt every reachable substrate improvement.
- Do not skip because priority, demand, or evidence seems weak.
- Only mark work not done after a concrete failed attempt or hard blocker.
- Do not create skill proposals.
- Verification readback is part of the action, not optional.
