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

## Runtime Boundary

Use the runtime-injected pre-skill context as the starting point.

Do not manage lifecycle, publication, postflight, adversarial review, or generic artifact rites inside this skill. The runtime owns those mechanics.

Follow the shared source lookup protocol when external evidence, current information, examples, papers, repositories, or public discussion are relevant.

## Method

### 1. Define Scope

Before researching or writing, answer:

- What is the central question?
- What decision or understanding should the report enable?
- What is the minimum evidence needed for the report to be useful?
- What would be out of scope or misleading to imply?

If user-invoked, the request provides the scope. If self-invoked, state why the report is being generated.

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
- comparison blocks for before/after or option trade-offs;
- flow examples for input -> output transformations;
- diagrams for architecture, process, dependencies, or feedback loops;
- timelines for sequence;
- charts for numeric comparison.

If the reader would need to draw something on paper to understand it, include a visualization.

## Output Contract

Produce a report artifact suitable for the uniform report pipeline.

The artifact should include:

- title and subtitle;
- concise executive summary;
- sections with narrative flow;
- at least one structured element when useful: table, comparison, diagram, timeline, flow example, or chart;
- references for external or non-obvious claims;
- explicit risks and unknowns;
- next steps.

## Privacy

Reports may contain confidential project details. Public versions must be sanitized before publication.
