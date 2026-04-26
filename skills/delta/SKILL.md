---
name: ed-delta
description: "Internal prerequisite before substantive skill dispatch. Reconcile preflight state, raw operator chat, previous delta digest, and changed work surfaces so the next skill sees what changed, what stayed open, and what should be injected into its reasoning."
user-invocable: false
---

# Delta - Work Continuity Frame

Use this skill only as an internal prerequisite before a substantive skill (`ed-research`, `ed-strategy`, `ed-planner`, `ed-autonomy`, `ed-reflection`, `ed-report`, `ed-map`, or `ed-discovery`) begins its own work.

Its job is to answer: what changed since the last useful work frame, what is still open, and what must the next skill carry forward?

The delta pass runs inside the same backend invocation as the dispatched skill. Its explored text and `delta_frame` remain available to the main skill; do not treat it as a separate report that disappears after handoff.

## Inputs

Use `request.delta_prerequisite` as the contract. It contains:

- `previous_delta_digest`: curated `work`, `learning`, and `handoff` state from prior strategy/reflection runs.
- `raw_chat`: recent operator messages and source refs.
- `strategic_context`: beat launch context, operator pressure, claims, queue, and open gaps.
- `surfaces`: configured integrations, capabilities, previous baselines, and open work.
- `preflight`: health, workflow, primitives, and other runtime checks.
- `events`: recent edge runtime events.

Structured state is authoritative for what was persisted. Raw chat is authoritative for what the operator actually said. Reconcile the two before acting.

If `previous_delta_digest` is missing from runtime context, use `edge-delta show --json` as the fallback source. The CLI only reads persisted JSON; it does not call a model.

## Method

1. Load the previous digest.
2. Read raw chat and operator pressure for work that was discussed outside normal edge cycles.
3. Select relevant surfaces to probe: current request, high-priority open work, explicit operator pressure, and surfaces with stale or missing baselines.
4. Probe only as much as needed to establish whether a real delta exists.
5. Classify each checked surface as `delta`, `non_delta`, or `unverified`.
6. Curate open work: keep, create, merge, block, complete, or archive.
7. Produce `delta_frame` for the next skill. Strategy/reflection own persistence through `edge-delta update`.

## Delta Rules

Every real delta must include:

- `surface`: where it happened.
- `before`: previous known state.
- `after`: current observed state.
- `evidence`: file paths, event ids, command outputs, URLs, issue/PR refs, or chat provenance.
- `relevance`: why the next skill should care.
- `confidence`: `high`, `medium`, or `low`.

Do not call something a delta just because context exists. If a surface was checked and nothing relevant changed, put it in `non_deltas`. If it matters but was not checked, put it in `unverified`.

## Open Work Curation

The digest has three curated sections:

- `work`: open work, archived work, priority threads, and surface baselines. Strategy owns this.
- `learning`: recent failures, durable rules, protocol gaps, and skill patch candidates. Reflection owns this.
- `handoff`: short guidance to inject into the next skill. Strategy and reflection may both update this.

Open work may contain many entries, but it is not a passive backlog.

Use these statuses:

- `forming`: mentioned, not yet operational.
- `active`: currently driving work.
- `waiting`: blocked on operator or external event.
- `blocked`: cannot move until a dependency changes.
- `stale`: probably no longer active, needs archival or refresh.
- `done`: completed and ready to archive.
- `archived`: closed for continuity.

Archive stale work when no current request, issue, thread, artifact, or downstream action depends on it. Merge duplicates instead of carrying parallel entries. Keep only the items that can plausibly affect future dispatch.

## Output Contract

Return or carry forward this shape:

```json
{
  "delta_frame": {
    "deltas": [
      {
        "surface": "github:owner/repo#branch",
        "before": "previous known ref or state",
        "after": "current observed ref or state",
        "evidence": ["..."],
        "relevance": "why this affects the next skill",
        "confidence": "high"
      }
    ],
    "non_deltas": [],
    "unverified": [],
    "work_continuity": {
      "open_work_to_keep": [],
      "open_work_to_archive": [],
      "new_open_work": [],
      "inject_to_next_skill": []
    }
  },
  "digest_update_needed": false
}
```

`inject_to_next_skill` is the part that becomes high-priority guidance for the main skill. Keep the full `delta_frame` in working context so the dispatched skill can inspect the evidence behind that guidance.

## Boundaries

Do not do the main skill's job. Do not publish reports, make strategic decisions, or implement fixes unless the dispatch explicitly asks for `ed-delta` itself. Prefer read-only probes. If a probe fails, preserve the attempted evidence and mark the surface `unverified`.
