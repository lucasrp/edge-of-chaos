---
name: ed-strategy
description: "Domain-first strategic planning from operator direction, real project progress, blockers, and next deliverables. Triggers on: strategy, estrategia, planeje, plan ahead, big picture, quadro geral."
user-invocable: true
---

# Strategy — Domain Strategy

Use this skill to turn the operator's real priorities into a short strategic plan for the next work cycles.

Strategy is about the operator's domain work: projects, deployed services, repositories, customer or research objectives, deliverables, blockers, and decisions. Internal edge-of-chaos substrate only matters when it changes what should happen in the domain.

It does not execute project work directly.

Prime rule: at least 70% of the artifact must be about domain work. Substrate curation is capped at 30%, and should be omitted entirely when it does not affect domain priorities.

## Boundary

Do not manage lifecycle, publication, postflight, adversarial review, or generic artifact rites inside this skill.

Follow the shared source lookup protocol when external trends, platform changes, ecosystem shifts, or strategic examples are relevant.

## The Job

Produce a strategic action artifact that answers:

- What does `config/strategy.md` say the operator is trying to achieve now?
- Which real projects or deliverables moved since the last strategy pass?
- What is blocked, stale, or unclear in the operator's work?
- Which milestone should be next for each priority project?
- What needs research, planning, execution, or an operator decision?
- What decisions belong to the operator?
- Which internal substrate issues, if any, materially block the above?

## Inputs

Start with operator direction:

- `config/strategy.md`;
- explicit operator messages in the current session;
- active GitHub issues, PRs, repositories, deployed services, dashboards, data assets, and project notes;
- recent reports and decisions that changed the domain plan.

Then use relevant internal state only as support:

- current session context;
- proposals, threads, topics, and open gaps;
- operational signals such as friction, decision, and runtime health;
- prior strategy artifacts and delta digest.

Use external sources only when the strategy depends on current ecosystem information or outside examples.

## Action Modes

Every real project or meaningful deliverable should receive one of these modes:

- `advance`: move it forward now.
- `unblock`: remove a concrete blocker.
- `research`: evidence or understanding is missing.
- `plan`: turn it into a proposal or implementation cycle.
- `operator_action`: enough is known; hand off for implementation or human decision.
- `park`: keep it, but do not spend work now.
- `archive`: remove from active attention.
- `operator_decision`: requires human choice before progress.

Each active mode needs a next skill or next action.

## Substrate Triage

Substrate triage is a brief final section, not the main body.

Include internal thread/topic/open-gap/runtime notes only when one of these is true:

- it blocks a domain milestone;
- it risks misleading future work;
- it should change the next dispatch;
- the operator explicitly asked for substrate cleanup.

Do not produce an edge-of-chaos status dashboard. If the artifact reads mostly like a claims, threads, or health report, it failed.

When substrate must be touched, prefer routing a small concrete fix instead of expanding the strategy artifact.

## Method

### 1. Anchor In Operator Direction

Read `config/strategy.md` first. Extract:

- current phase;
- top priorities;
- explicit non-goals;
- project constraints;
- decisions waiting on the operator.

Quote or paraphrase the relevant parts before interpreting anything else.

### 2. Establish The Domain Picture

Summarize the current state of the operator's work:

- active projects;
- blocked projects;
- deployed services or repos that matter;
- recently changed priorities;
- recent decisions;
- measurable progress or lack of progress.

### 3. Analyze Projects

For every relevant project, evaluate:

| Dimension | Question |
|---|---|
| Momentum | Is it active, dormant, blocked, or complete? |
| Next milestone | What is the next concrete milestone? |
| Blockers | What prevents progress? |
| Risk | What degrades if ignored? |
| Dependencies | What does it need from other projects? |
| Action mode | advance, unblock, research, plan, operator_action, park, archive, or operator_decision? |

### 4. Map Dependencies

Identify:

- direct dependencies;
- shared infrastructure;
- reusable work;
- conflicts between priorities;
- synergies where one effort advances multiple projects.

Use a diagram or table when the graph is non-trivial.

### 5. Add Brief Substrate Notes

Only after the domain strategy is clear, include a compact substrate note:

- runtime or publication blockers that can derail project work;
- stale topics/open gaps that materially affect a project;
- recommended route for the next skill.

If there is no material substrate issue, write one sentence saying so.

### 6. Produce The Action Queue

End with an explicit domain action queue:

```text
Strategic Actions
1. <target> -> <action_mode> -> next: <skill/action> -> reason: <why>
2. <target> -> <action_mode> -> next: <skill/action> -> reason: <why>
```

The queue should be short enough to act on.

### 7. Curate The Delta Digest

Every strategy run must update the curated delta digest, even if the update is an explicit no-op.

Strategy owns the digest `work` section:

- `open_work`: active work that should affect future dispatch.
- `archived_work_recent`: stale or completed work removed from active attention.
- `priority_threads`: threads that should bias the next dispatch.
- `surface_baselines`: checked work surfaces and their latest known refs.

Strategy may also update `handoff.inject_to_next_skill`, `handoff.watch_next`, and `handoff.unverified_but_important` when the next skill needs short guidance.

Persist with:

```bash
edge-delta update --skill strategy --payload-file <json>
```

If nothing should change:

```bash
edge-delta update --skill strategy --no-op --summary "<reason>"
```

The payload shape is:

```json
{
  "summary": "short strategic continuity summary",
  "work": {
    "open_work": [],
    "archived_work_recent": [],
    "priority_threads": [],
    "surface_baselines": {}
  },
  "handoff": {
    "inject_to_next_skill": [],
    "watch_next": [],
    "unverified_but_important": []
  }
}
```

## Quality Criteria

- Strategy must be grounded in `config/strategy.md` and actual project state.
- At least 70% of the artifact must discuss domain work, not internal substrate.
- Every active project or deliverable needs an action mode.
- Every `advance`, `unblock`, `research`, `plan`, or `operator_action` item needs a next skill or concrete action.
- Every `park` item needs a reactivation condition.
- Every `archive` decision needs a short reason.
- Substrate notes must be brief and tied to project impact.
- Priority means something else is not first; state the trade-off.
- Do not turn strategy into implementation.
- Do not edit operator-owned direction or priority files directly from this skill.
- Do not finish without `edge-delta update` or an explicit `edge-delta update --no-op`.
- Make stale assumptions visible.
- Compare against prior strategy when available.

## Output Contract

Produce a strategy artifact suitable for the uniform report pipeline.

Recommended sections:

1. Operator Direction
2. Domain Progress
3. Next Milestones
4. Blockers And Dependencies
5. Recommendations
6. Strategic Action Queue
7. Substrate Notes
8. Operator Decisions
9. Delta Digest Update
10. Risks
11. References

Useful structures:

- project cards with action-mode badges;
- dependency diagram;
- action queue;
- risk table.
