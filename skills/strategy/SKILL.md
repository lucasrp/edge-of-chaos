---
name: ed-strategy
description: "Strategic planning across all projects. Analyze state, curate claims and threads, choose action modes, and route next work. Triggers on: strategy, estrategia, planeje, plan ahead, big picture, quadro geral."
user-invocable: true
---

# Strategy — Active Strategic Curation

Use this skill to look across projects, threads, claims, and signals, then decide what should happen next.

Strategy is not passive recommendation. It makes decisions over the agent-owned substrate: classify work, curate stale knowledge, route next skills, and produce an action queue.

It does not execute project work directly.

## Runtime Boundary

Use the runtime-injected pre-skill context as the starting point.

Do not manage lifecycle, publication, postflight, adversarial review, or generic artifact rites inside this skill. The runtime owns those mechanics.

Follow the shared source lookup protocol when external trends, platform changes, ecosystem shifts, or strategic examples are relevant.

## The Job

Produce a strategic action artifact that answers:

- What should move now?
- What is blocked?
- What needs research, planning, or execution?
- Which threads should stay active, be merged, be parked, or be archived?
- Which claims are still useful, disputed, stale, or dead?
- Which stale claims should be archived because no work is derived from them?
- What should be routed to another skill next?
- What decisions belong to the operator?

## Inputs

Use relevant internal state:

- runtime context;
- project status and repositories;
- issues, boards, proposals, and threads;
- claims and their supporting artifacts;
- recent reports and decisions;
- operational signals such as friction, autonomy, decision, reflection, and serendipity;
- prior strategy artifacts.

Use external sources only when the strategy depends on current ecosystem information or outside examples.

## Action Modes

Every project, thread, or meaningful claim cluster should receive one of these modes:

- `advance`: move it forward now.
- `unblock`: remove a concrete blocker.
- `research`: evidence or understanding is missing.
- `plan`: turn it into a proposal or implementation cycle.
- `operator_action`: enough is known; hand off for implementation or human decision.
- `reflect`: update memory, correct drift, or process feedback.
- `merge`: combine duplicates or overlapping threads/claims.
- `park`: keep it, but do not spend work now.
- `archive`: remove from active attention.
- `operator_decision`: requires human choice before progress.

Each active mode needs a next skill or next action.

## Thread Curation

For each active or resurfacing thread, decide:

- keep active;
- merge with another thread;
- route to `ed-research`, `ed-planner`, `ed-reflection`, `ed-map`, or `operator_action`;
- park with a concrete reactivation condition;
- archive because it no longer produces useful work.

A thread should not remain active only because it exists. If it has no current objective, no next action, and no useful pressure on a project, archive it.

## Claim Curation

Claims are working knowledge, not a museum.

Classify old, stale, weak, duplicated, or unsupported claims explicitly:

- `keep`: still useful and connected to live work.
- `refresh`: still important, but source/evidence may be stale.
- `dispute`: contradicted or no longer trusted.
- `merge`: duplicate or near-duplicate of a stronger claim.
- `promote`: should become workflow, proposal, issue, or thread.
- `archive`: stale or inactive with no derived work.

Archive a claim when all are true:

- it is old or marked stale;
- no active thread, proposal, issue, workflow, or project action depends on it;
- it is not needed as evidence for a current decision;
- refreshing it would not unblock concrete work.

Do not keep stale claims around as passive context. If no work is derived from them, archive them.

If a stale claim still matters, do not archive it silently. Route it to `refresh` or `research` and state what decision depends on it.

## Method

### 1. Establish The Big Picture

Start with the current state of the ecosystem:

- active projects;
- blocked projects;
- recently changed priorities;
- operator pressure;
- runtime pressure;
- stale or overloaded knowledge surfaces.

### 2. Analyze Projects

For every relevant project, evaluate:

| Dimension | Question |
|---|---|
| Momentum | Is it active, dormant, blocked, or complete? |
| Next milestone | What is the next concrete milestone? |
| Blockers | What prevents progress? |
| Risk | What degrades if ignored? |
| Dependencies | What does it need from other projects? |
| Action mode | advance, unblock, research, plan, operator_action, park, archive, or operator_decision? |

### 3. Curate Threads And Claims

Review threads and claim clusters as part of strategy, not as a separate housekeeping task.

For each item, decide:

- current status;
- whether it is still strategically useful;
- what work is derived from it;
- whether it should be archived, merged, refreshed, promoted, or routed.

### 4. Map Dependencies

Identify:

- direct dependencies;
- shared infrastructure;
- reusable work;
- conflicts between priorities;
- synergies where one effort advances multiple projects.

Use a diagram or table when the graph is non-trivial.

### 5. Produce The Action Queue

End with an explicit queue:

```text
Strategic Actions
1. <target> -> <action_mode> -> next: <skill/action> -> reason: <why>
2. <target> -> <action_mode> -> next: <skill/action> -> reason: <why>
```

The queue should be short enough to act on.

## Quality Criteria

- Strategy must be grounded in actual project, thread, and claim state.
- Every active item needs an action mode.
- Every `advance`, `unblock`, `research`, `plan`, `operator_action`, or `reflect` item needs a next skill or concrete action.
- Every `park` item needs a reactivation condition.
- Every `archive` decision needs a short reason.
- Stale claims without derived work should be archived, not carried forward.
- Priority means something else is not first; state the trade-off.
- Do not turn strategy into implementation.
- Do not edit operator-owned direction or priority files directly from this skill.
- Make stale assumptions visible.
- Compare against prior strategy when available.

## Output Contract

Produce a strategy artifact suitable for the uniform report pipeline.

Recommended sections:

1. Big Picture
2. Project Action Modes
3. Thread Curation
4. Claim Curation
5. Dependencies And Conflicts
6. Strategic Action Queue
7. Operator Decisions
8. Risks
9. References

Useful structures:

- project cards with action-mode badges;
- thread table;
- claim curation table;
- dependency diagram;
- action queue;
- risk table.
