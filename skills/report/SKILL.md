---
name: ed-report
description: "Generate a structured HTML report on any topic. Use when you need to deeply understand something, analyze a question, or produce a deliverable for the user. Dual-purpose: user invokes for deliverables, edge_of_chaos self-invokes to think through problems. Triggers on: report, gerar report, analise, analyze, explique em detalhe, explain in detail."
user-invocable: true
---

# Report — Thinking By Producing

Use this skill when the work needs more than a short answer: a structured analysis, a decision memo, a synthesis of evidence, or a durable explanation.

A report is both thinking and communication. The structure should force clarity that running text would not.

## When To Use

Use `ed-report` when:

- the user asks for a report or detailed analysis;
- the agent needs to understand something before acting;
- a complex topic needs decomposition;
- a decision needs evidence, comparisons, risks, and next steps;
- reasoning should become a durable artifact.

If the answer fits cleanly in a few paragraphs, do not inflate it into a report.

## Boundary

Do not manage lifecycle, publication, postflight, adversarial review, or generic artifact rites inside this skill.
Do not call `edge-consult` or `review-gate` manually as part of the normal report path.
Draft the YAML and staging entry, then let `consolidate-state` own the adversarial,
Feynman, review-gate, publication, meta-report, and post-state phases. If
`consolidate-state` blocks on feedback, address that feedback and rerun the
pipeline; do not create a separate pre-publication review loop inside this skill.

Publishing is not optional once `/ed-report` has chosen a topic. Files staged in
`/tmp` are drafts, not the report artifact. Do not close by asking the operator
whether to publish, by recommending a future `consolidate-state` run, or by
handing off because earlier drafts are blocked. Prior blocked drafts are evidence
for the report and may justify a tighter scope, but they do not authorize a
staging-only exit. The skill is complete only after `consolidate-state` succeeds
and the generated HTML report, blog entry, and meta-report have been verified; if
that cannot be achieved, surface the concrete failing command and reason instead
of reporting success.

Follow the shared source lookup protocol when external evidence, current information, examples, papers, repositories, or public discussion are relevant.

## Method

### 1. Define Scope

Before researching or writing, answer:

- What is the central question?
- What decision or understanding should the report enable?
- What is the minimum evidence needed for the report to be useful?
- What would be out of scope or misleading to imply?

If user-invoked, the request provides the scope. If self-invoked, state why the report is being generated.

### Bare Invocation / Missing Scope

A bare `/ed-report` dispatch is already authorization to choose a useful
report target. Do not end the skill by asking the operator what topic to use
when runtime context contains enough signal to proceed.

If no explicit topic, question, or args are present:

1. Inspect the injected runtime frame: `delta_prerequisite`,
   `beat_launch_context`, `operator_pressure_digest`, `health_snapshot`,
   `claims_summary`, `exploration_pack`, recent pipeline failures, and current
   git/runtime drift.
2. Select the highest-leverage report target that would reduce operator
   uncertainty or make the next engineering action clear.
3. State the inferred target and why it was selected.
4. Produce the report artifact.

Ask the operator for a topic only when the runtime frame contains no reasonable
candidate and any inferred report would be misleading. That should be rare.

### 2. Gather Evidence

Use the right sources for the topic:

- internal context and project files;
- previous notes and reports;
- source lookup for external evidence and current context;
- primary docs, papers, repos, or public discussions where relevant.

Prefer primary sources and concrete examples. Record source identifiers clearly enough that the reader can inspect them later.

### 3. Derive Before Summarizing

Use first-principles reasoning before pasting conclusions from sources.

If reasoning stalls, mark the gap explicitly. A good report shows where understanding came from, what changed during investigation, and what remains uncertain.

### 4. Structure The Report

Choose sections that tell a story:

1. Context
2. Central Question
3. Evidence
4. Analysis
5. Alternatives Or Comparisons
6. Recommendation Or Synthesis
7. Risks And Unknowns
8. Next Steps
9. References

Adapt titles to the topic, but preserve the arc: context -> evidence -> analysis -> decision.

## Report Quality

- Sections should build on each other; order matters.
- Tables beat prose when 3+ comparable items exist.
- Comparisons beat paragraphs when alternatives have trade-offs.
- Callouts should mark insights, risks, caveats, or decisions the reader should not miss.
- Claims should be traceable to sources, files, or explicit reasoning.
- Uncertainty should be visible, not hidden.
- Recommendations should be concrete enough to execute or test.

## Visuals

Use visual structure when it makes the report easier to reason about.

Prefer:

- tables for exact reference;
- `bar-chart` blocks for 3+ comparable values, risks, options, costs, or scores;
- `line-chart` blocks for trends, sequences, or before/during/after movement;
- comparison blocks for before/after or option trade-offs;
- flow examples for input -> output transformations;
- diagrams for architecture, process, dependencies, or feedback loops;
- timelines for sequence;
- charts for numeric comparison.

If the reader would need to draw something on paper to understand it, include a visualization.
When a report has more than one analytical comparison or operational trade-off,
use more than one visualization instead of forcing the whole argument into prose.

## Output Contract

Produce a report artifact suitable for the uniform report pipeline.

The artifact should include:

- title and subtitle;
- concise executive summary;
- sections with narrative flow;
- at least one structured element when useful: table, comparison, diagram, timeline, flow example, or chart;
- SVG/table chart pairs for routine numerical comparisons;
- references for external or non-obvious claims;
- explicit risks and unknowns;
- next steps.

## Privacy

Reports may contain confidential project details. Public versions must be sanitized before publication.
