---
name: ed-planner
description: "Design concrete development cycles for new or existing projects. Turns a strategic target, idea, or problem into an executable proposal. Triggers on: planner, plan project, propose, proposta, ciclo de desenvolvimento."
user-invocable: true
---

# Planner — Development Cycle Design

Use this skill to turn a target into a concrete development cycle.

Planner does not execute the cycle. It designs the work so a human, team, or explicit implementation process can execute it with minimal ambiguity.

## Boundary

Do not manage lifecycle, publication, postflight, adversarial review, or generic artifact rites inside this skill.

Follow the shared source lookup protocol when the proposal depends on external tools, technical patterns, ecosystem examples, or implementation gotchas.

## When To Use

Use `ed-planner` when:

- heartbeat curation or the operator selected `plan`;
- a user asks for a proposal or development cycle;
- an idea from research/discovery needs an implementation shape;
- a project needs scope, deliverables, risks, and success criteria before execution;
- implementation would be premature because the work is not yet decomposed.

For missing understanding, use `ed-research`. For cross-project priority decisions, read `config/strategy.md` and current state directly. For a concrete implementation handoff, produce a clear `operator_action` rather than routing to an execution skill.

## Inputs

Use relevant context:

- target project or idea;
- current action queue;
- existing issues, proposals, reports, and prior executions;
- repository/project state when available;
- operator constraints;
- relevant external examples or implementation patterns.

Avoid duplicate proposals. If a similar proposal exists, build on it, merge it, or explain why this one is different.

## Proposal Types

### Existing Project Cycle

Use when the target project already exists.

The cycle should specify exactly what changes, where, in what order, and how success is checked.

### New Project Cycle

Use when the proposal creates a new project.

Do not create the repository or scaffold files from this skill. Define what should be created and make the approval/implementation handoff explicit.

### Repair Cycle

Use when the goal is to fix drift, broken runtime behavior, stale artifacts, or degraded execution.

Make the failure mode and regression test explicit.

### Measurement Cycle

Use when the idea is uncertain and should be tested before committing to implementation.

Define the measurement plan, success criteria, sample, expected cost, and handoff. Do not route to a separate experiment skill.

## Method

### 1. Define The Problem

State:

- what hurts or is missing;
- who or what is affected;
- why now;
- what changes if the cycle succeeds;
- what happens if it is deferred.

### 2. Inspect Existing Context

Check:

- similar proposals;
- related research/discovery artifacts;
- relevant repository state;
- open issues or known blockers;
- constraints from strategy or operator decisions.

### 3. Shape The Cycle

Define:

- in-scope work;
- explicit non-goals;
- deliverables;
- dependencies;
- execution order;
- files/modules/systems likely touched;
- tests or verification steps;
- rollback or stop conditions when relevant.

### 4. Show The Work

The proposal must make the future work visible.

Include concrete examples:

- before/after for behavior, UI, data, or file structure;
- input -> output examples for key pipeline pieces;
- example config, schema, command, API payload, or file content;
- mock success/failure result when useful.

The reader should be able to see what will change, not just read a description.

### 5. Estimate Cost And Risk

Estimate:

- engineering effort;
- API/runtime cost if relevant;
- operational risk;
- maintenance risk;
- uncertainty;
- dependencies on secrets, services, or human decisions.

Include mitigations for the important risks.

### 6. Produce Execution Handoff

End with an explicit handoff:

```text
Handoff
target: <project/system>
mode: operator_action | research | operator_decision
next_skill: ed-research | none
first_action: <concrete first step>
blockers: <if any>
```

## Proposal Quality

- A proposal must be executable, not merely plausible.
- Scope must be narrow enough for one cycle.
- Every deliverable needs verification.
- Every risk needs either mitigation or acceptance.
- Every dependency needs an owner or resolution path.
- The proposal must distinguish required work from optional polish.
- Do not create external repos, edit project files, or mutate production systems from this skill.
- If the proposal requires operator approval, make the decision explicit.

## Output Contract

Produce a proposal artifact suitable for the uniform report pipeline.

Recommended sections:

1. Problem
2. Proposed Cycle
3. Scope And Non-Goals
4. Deliverables
5. Before And After
6. Execution Plan
7. Verification
8. Cost And Risks
9. Handoff
10. References

Useful structures:

- numbered deliverable cards;
- before/after comparison;
- flow examples for key transformations;
- risk table;
- execution timeline;
- handoff block.

## Privacy Rule

For public communication, do not identify private organizations, owners, project names, or data that can trace the human operator.
