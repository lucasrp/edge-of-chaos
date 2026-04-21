# Dashboard Threads Console (#283)

This document defines the product direction for the dashboard's threads screen.
It is not a wireframe and it is not a frontend-stack proposal. The goal is to
make threads legible and operable as the system's unit of continuous work.

## Problem

The current dashboard shows threads, but it still behaves more like a registry
than a control surface.

The operator can see that threads exist, and can sometimes nudge status, but
the screen does not yet answer the operational questions that matter:

- which threads need attention now
- why each thread is in its current state
- what the next step is
- what evidence shows the thread is moving
- what intervention is pending or already applied

That makes the operator work from scattered files, thread detail pages, reports,
and implicit beat history instead of from one continuity surface.

## Product Goal

Turn the threads screen into a **thread triage console**.

The screen should help the operator do four things quickly:

1. identify which threads require attention now
2. understand why a thread is healthy, stalled, blocked, or overdue
3. act on a thread without dropping into raw files
4. verify whether a later beat actually moved the thread forward

## Core UX Direction

### 1. Attention first, inventory second

The default view should prioritize operational risk, not alphabetical or
creation-order browsing.

The screen should answer "what needs attention?" before "what threads exist?"

### 2. Thread as continuity unit

A thread is not just a metadata file. It is the canonical container for:

- objective
- next step
- evidence
- related claims
- related artifacts
- recent beats that touched it
- operator interventions

The screen should reflect that.

### 3. State must be explained, not only labeled

A status badge alone is not enough.

If a thread is `blocked`, `waiting`, `overdue`, or `healthy`, the UI must make
the reason visible.

### 4. Actions must be local and auditable

The operator should be able to act from the screen, but the screen must also
make clear whether an action:

- changed the thread immediately
- was queued for the next dispatch
- was already applied downstream

### 5. Disclosure by depth

The main list should optimize for fast scanning.

The selected-thread detail should optimize for continuity, history, and linked
evidence.

The operator should not need to open multiple files to understand what is going
on with one thread.

## Operator Questions The Screen Must Answer

Within a few seconds, the operator should be able to answer:

- which threads are due now
- which threads are blocked
- which threads are waiting on something external
- which active threads lack a next step
- which active threads lack recent evidence
- which threads are actually advancing
- which threads are closure-ready
- which interventions are still pending
- which beat or skill touched a thread last

## Required Capabilities

### 1. Operational segmentation

The screen must separate at least these categories:

- `needs attention`
- `in progress`
- `waiting`
- `proposed`
- `dormant`
- `done`

The main list order should prefer urgency over neutrality:

1. overdue / resurface due
2. blocked
3. active with no next step
4. active with no recent evidence
5. active healthy
6. proposed
7. dormant / done

### 2. Thread card contract

Every thread card must show enough information to support a triage decision.

Minimum fields:

- title
- id
- status
- type
- owner
- goal
- next step
- done when
- updated
- resurface
- entries count
- reports count
- claims summary
- last evidence summary
- last beat or skill that touched the thread

### 3. Health flags

Threads must expose explicit health signals, not implicit interpretation.

Minimum flags:

- `blocked`
- `waiting_on`
- `overdue`
- `no_next_step`
- `no_recent_evidence`
- `closure_ready`
- `false_positive_overdue` when an overdue state is not actually actionable

### 4. Evidence visibility

The operator must be able to see whether a thread is moving because of actual
work, not because a timestamp changed.

The screen must expose:

- latest linked artifact
- latest report
- latest note if available
- claims summary (`verified`, `open`, `disputed`, `stale` as available)
- timestamp and summary of the latest beat touching the thread

### 5. Beat history

Threads need first-class continuity history.

Each thread should expose a beat/cycle timeline showing, at minimum:

- timestamp
- cycle id
- trigger
- skill
- one-line summary
- artifacts produced
- outcome

This can be condensed in the main list, but it must exist in the thread detail
surface.

### 6. Intervention visibility

The screen must distinguish:

- current thread state
- pending operator intent
- already applied intervention
- downstream effect on later beats or artifacts

### 7. Local actions

The operator should be able to act directly on a thread from the screen.

Minimum actions:

- `worked`
- `snooze`
- `activate`
- `block`
- `unblock`
- `mark waiting`
- `mark dormant`
- `mark done`
- `enqueue dispatch`
- `update next step`

### 8. Drilldown

Selecting a thread should open a detail surface with:

- thread objective and done-when condition
- current state and reason
- linked entries
- linked reports
- linked notes
- linked claims
- beat history
- intervention history

## Acceptance Criteria

- the operator can identify threads requiring immediate attention within a few
  seconds of opening the screen
- every active or overdue thread shows a readable reason for its current state
- every active thread either has a visible `next step` or a visible
  `no_next_step` problem state
- blocked or waiting threads show what they are blocked on
- every thread shows when it was last touched and by which beat or skill
- the operator can act on a thread without leaving the screen
- the UI makes it explicit whether an action is queued or already applied
- the screen makes it possible to distinguish advancing threads from aging
  threads
- proposed and candidate threads are visually and operationally distinct from
  active work
- the detail surface is sufficient to understand one thread's continuity
  without opening several raw files

## Non-Goals

- this is not a general task manager replacing the rest of the dashboard
- this is not a proposal to render full thread markdown in the main list
- this is not a frontend rewrite proposal
- this is not a requirement to expose the full event log inline on every card
- this is not an instruction to optimize the screen for catalog browsing over
  operational decision-making

## Suggested Delivery Slices

1. enrich the read model with thread health, latest evidence, and thread-level
   beat history
2. ship an attention-first threads screen with operational lanes and explicit
   health flags
3. add thread-level actions plus queued/applied intervention visibility
4. add full thread continuity detail with linked artifacts, claims, and beat
   history
