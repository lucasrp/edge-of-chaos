---
name: ed-sources
description: "Curate and improve source/signal patterns. Use when reviewing search quality, source usefulness, query patterns, source affordances, or edge-sources/edge-signals feedback."
user-invocable: true
---

# Sources — Source/Signal Curation

Use this skill to improve how the system finds external evidence and operational signals.

`ed-sources` is not the search runner. The CLI already does that:

```bash
edge-cap invoke sources.aggregate -- "topic" --intent <intent>
edge-cap invoke sources.aggregate -- "topic" --intent <intent> --feedback-json
edge-signals --help
edge-context --mode sources "topic" --intent <intent>
```

The skill owns the feedback loop around those tools: what worked, what failed, and which query patterns are worth keeping.

## Responsibility

Sources owns source/signal pattern curation.

It is responsible for:

- mining source/search/signal history for useful feedback;
- testing new source and query patterns;
- grading source/channel affordances;
- consolidating repeated source/signal behavior into topics or pre-skill context;
- archiving stale, duplicated, or low-use source patterns;
- keeping source guidance compact enough to stay useful.

## Boundary

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill.

Do not duplicate the source registry in this skill. `edge-sources`, `edge-signals`, `edge-context`, capability manifests, and primitive read models are the executable source of truth.

## Inputs

Use these in order:

- `state/source-affordance-digest.json`;
- recent source and signal events from `state/events.jsonl`;
- `edge-cap status --json --skill sources`;
- `edge-primitives status --json`;
- existing source/signal topics and notes from corpus search;
- recent reports or skill outputs that cite sources;
- failed or degraded `edge-sources`, `edge-signals`, or `edge-context` calls;
- operator feedback about source quality.

Use raw logs only to answer a specific curation question. Prefer digests and read models first.

## Feedback Model

Useful feedback is structured. For each search/signal episode, capture:

| Field | Meaning |
|---|---|
| Task intent | research, discovery, heartbeat, planner, report, etc. |
| Query pattern | exact query shape or source route tested |
| Source/channel | e.g. `source.hn`, `source.x`, `source.exa`, `signal.friction`, `search.corpus` |
| Affordance | novelty, confirmation, continuity, operational_signal, implementation_pattern, primary_source, counterexample |
| Usefulness | score 1-5 |
| Evidence | ODI/result URL, artifact, event id, or output snippet |
| Reason | why it helped, failed, or misled |
| Follow-up | keep, merge, archive, retest, or promote to topic/pre-skill context |

Record affordance judgments with:

```bash
edge-affordance evaluate <source_id> \
  --affordance <affordance> \
  --score <1-5> \
  --context "<task intent / situation>" \
  --query "<query or route>" \
  --reason "<short reason>"
```

If there is an ODI id from `edge-sources`, pass `--odi <id>`.

## Method

### 1. Read The Current Learning State

Inspect the affordance digest and recent source/signal events.

Answer:

- Which sources are reliably useful for which affordances?
- Which sources produce noise?
- Which intents have weak coverage?
- Which query patterns repeatedly work?
- Which source/signal calls fail or degrade?

### 2. Find Existing Source Patterns

Search for current source/signal patterns:

```bash
edge-cap invoke search.corpus -- "sources signals edge-sources edge-signals" --require-type topic --require-type memory -k 20
```

Classify each pattern:

- `keep`: still useful and distinct;
- `merge`: overlaps with another topic or note;
- `archive`: stale, unused, too broad, or contradicted by current tools;
- `retest`: promising but unproven;
- `replace`: superseded by a better route.

Keep the active source/signal pattern set short and specific.

### 3. Test Patterns

Test patterns against real questions, not toy prompts.

Use the CLI as the experimental harness:

```bash
edge-cap invoke sources.aggregate -- "<query>" --intent <intent> --feedback-json \
  --episode-id "sources-test:<slug>" \
  --pattern-id "<pattern-name>" \
  --pattern-note "<what is being tested>"
edge-context --mode sources "<query>" --intent <intent>
edge-signals --json
```

Test variants such as:

- specific source overrides vs routed default;
- narrow technical query vs broad problem query;
- primary-source-first vs community-discussion-first;
- corpus-first vs external-first;
- signal check before source search;
- second query derived from what failed in the first.

For each test, record what changed in the answer quality.

Use `--feedback-json` when curating. It returns the run id, episode id, selected route, source summaries, ODI ids, and a feedback contract for `edge-affordance`.
For corpus routing, it also includes `source_playbook.corpus` with citation-weighted query guidance, high-value entries, and decay notes from the observability rollup.

### 4. Grade Source/Signal Affordances

Use `edge-affordance evaluate` for every meaningful success or failure.

Score guidance:

- `5`: source/channel directly changed the answer or decision;
- `4`: useful and specific, with minor cleanup;
- `3`: acceptable context, not decisive;
- `2`: mostly noisy or indirect;
- `1`: failed, misleading, stale, or unavailable.

Grade atomic sources/channels, not wrappers. Prefer `source.hn`, `source.exa`, `source.github`, `signal.friction`, `search.corpus` over `edge-sources`.

When a corpus result directly informs an artifact, make sure the publishing
skill records it under `corpus_references` so future search ranking can learn
from actual use.

### 5. Curate The Pattern Set

Promote a pattern only when it is repeatable.

Before adding durable guidance:

- check active count;
- merge duplicates;
- archive stale guidance;
- ensure the new topic or pre-skill context has a clear trigger, failure mode, and evidence from tests.

Hard cap: keep only guidance that will affect future source routing.

### 6. Close With A Curation Report

Return:

```markdown
Sources Curation
Scope: <history window / patterns tested>

Affordance Updates:
- <source/channel> -> <affordance> -> <score> -> <reason>

Patterns Tested:
- <pattern> -> <result> -> <keep/archive/retest>

Pattern Curation:
- kept:
- merged:
- archived:
- promoted:

Failures / Blockers:
- <source/signal route> -> <exact error or degradation>

Next:
- <next test or pattern cleanup>
```

## Invariants

- The CLI runs searches; the skill curates learning from searches.
- Feedback must be structured enough to improve future routing.
- Grade atomic sources/channels, not only wrapper commands.
- Do not keep stale or duplicated source patterns.
- Do not promote a pattern without testing it.
- Archive old source guidance when it no longer produces useful work.
