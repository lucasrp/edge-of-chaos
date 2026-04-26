---
name: ed-reflection
description: "Operational self-review and feedback loop. Diagnose repeated failures, process operator feedback, update stale guidance, and route concrete corrections. Triggers on: reflection, reflect, reflexao, review sessions, process feedback, self-review."
user-invocable: true
---

# Reflection — Operational Learning

Use this skill when the system needs to learn from its own behavior.

Reflection is not a report, research pass, or planning cycle. It diagnoses recurring friction, turns operator feedback into operating changes, and decides what must be fixed, routed, archived, or monitored.

## Responsibility

Reflection owns the operational learning loop.

It is responsible for making sure repeated mistakes, operator corrections, stale rules, and contradictory state become one of:

- a concrete fix inside the agent substrate;
- a durable rule in the right skill, workflow, memory, or shared protocol;
- an archived rule or claim that should stop influencing behavior;
- a routed task for the skill or operator that can actually resolve it;
- a monitored condition with clear evidence needed before action.

A reflection run is incomplete if it only describes a problem and leaves no ownership trail. The report is just the closing record; the responsibility is to change future behavior or explicitly route the change.

Reflection does not own product implementation, project delivery, or broad refactors. It owns the decision that an operational lesson exists and the placement of that lesson in the system.

## Boundary

Do not manage lifecycle, publication, postflight acknowledgement, or generic artifact rites inside this skill.

When editing protected state or shared protocols, follow the shared state protocol. Make the intended change explicit before editing, keep the change focused, and report what changed.

Use the shared source lookup protocol only when the reflection depends on current external practice, tool behavior, ecosystem changes, or outside examples. Most reflection should come from internal evidence.

## Modes

| Mode | When | Output |
|---|---|---|
| `heartbeat-normal` | Routine heartbeat asks for self-review | Up to 3 actionable observations |
| `heartbeat-escalated` | Anomaly, repeated failure, user frustration, or contradictory state | Root-cause diagnosis plus one concrete correction or route |
| `manual` | Operator explicitly asks for reflection | Deeper review of recent behavior, feedback, stale rules, and next corrections |

If mode is not provided, infer it from the request and runtime context. Prefer the smallest mode that can answer the problem.

## Inputs

Use internal evidence before speculation:

- runtime request and async inbox snapshot;
- operator feedback, especially explicit "always", "never", "from now on", or "make sure" directives;
- health, workflow, and capability status;
- operational signals such as friction, reflection, cost, serendipity, and decision;
- recent dispatches, ledger summaries, retry/failure patterns, and state lint;
- git signals, changed files, and fix chains;
- debugging notes, reflection log, workflows, and skill-step summaries;
- relevant transcripts only when an anomaly requires message-level evidence.

Do not read entire histories by habit. Sample only the evidence needed to answer the current reflection question.

## Core Questions

Answer these in order:

- What happened or keeps happening?
- What evidence proves it?
- Is it a real pattern, a one-off, or stale state?
- What rule, workflow, skill, memory, or routing decision should change?
- What should be archived because it no longer drives work?
- What needs operator decision instead of agent action?

## Finding Types

Classify every meaningful finding as one of:

- `fix_now`: small, clear correction inside reflection's scope.
- `route`: send to another skill or tool because reflection should not do the work.
- `codify`: add or revise durable guidance, workflow, debugging entry, or shared protocol.
- `archive`: remove stale guidance, claim, workflow, or thread from active attention.
- `monitor`: not enough evidence yet; define what would make it actionable.
- `operator_decision`: the next step requires human judgment.

Do not leave a finding as commentary only. Each finding needs a next action or a reason it is being monitored.

## Method

### 1. Establish The Trigger

State why reflection is running:

- operator feedback;
- heartbeat routing;
- anomaly or repeated failure;
- stale or contradictory state;
- manual review request.

### 2. Gather Evidence

Collect the smallest evidence set that can prove or disprove the trigger.

For normal heartbeat mode, use ready summaries and keep the review short.

For escalated or manual mode, inspect deeper sources only when they answer a specific question. Transcript reading should be targeted to the failing run, not broad browsing.

### 3. Diagnose

For each issue, identify:

| Field | Meaning |
|---|---|
| Evidence | concrete signal, file, run, user feedback, or diff |
| Pattern | repeated behavior or contradiction |
| Cause | likely root cause, or explicit unknown |
| Impact | what gets worse if ignored |
| Action | fix_now, route, codify, archive, monitor, or operator_decision |

Prefer one strong diagnosis over many weak observations.

### 4. Process Feedback

Operator feedback has priority over generic introspection.

If the feedback is a durable operating rule, convert it into the right durable surface:

- shared protocol for cross-skill rules;
- a specific skill when the rule belongs only there;
- workflow when it is repeatable procedure;
- debugging note when it prevents recurring failure;
- strategy or planner route when it implies project-level work.

Do not manually acknowledge or consume async inbox messages. Runtime postflight owns acknowledgement after completion evidence exists.

### 5. Curate Stale Guidance

Reflection should remove drag, not only add rules.

Archive or retire guidance when it is obsolete, contradicted by current decisions, duplicated by a stronger source, or no active work depends on it.

If old guidance still matters but is untrusted, mark it for refresh or route it to research. Do not keep stale guidance active as passive context.

### 6. Apply Focused Corrections

Reflection may make focused edits when the correction is clear and inside its scope:

- update a skill or shared protocol;
- add or revise a debugging rule;
- update memory with consolidated operating knowledge;
- mark stale guidance archived;
- create a route or action item for another skill.

Do not perform unrelated project implementation. If the correction requires product/code work, route it.

### 7. Close With Action

End with a concise operational report:

```markdown
Reflection Mode: <heartbeat-normal | heartbeat-escalated | manual>
Trigger: <why this ran>
Evidence Checked: <short list>

Findings:
- <finding> -> <action type> -> <next action>

Changes Made:
- <file or state surface>: <what changed>

Routed / Monitoring:
- <item>: <next skill/action or monitoring condition>
```

If no issue is found, say so directly and name the residual risk or next signal to watch.

## Escalation Triggers

Escalate from normal to escalated when any of these is true:

- the same failure repeats;
- user feedback indicates frustration or correction;
- runtime state contradicts itself;
- a protected workflow, skill, or memory rule is stale and causing errors;
- retry, cost, or failure signals show avoidable waste;
- an operator directive must become durable guidance.

## Invariants

- Internal evidence beats vibe.
- Operator feedback outranks autonomous curiosity.
- Reflection changes operating behavior or routes the work; it does not merely summarize.
- Stale rules are liabilities. Archive them when no current work depends on them.
- Keep the output short enough to guide the next cycle.
