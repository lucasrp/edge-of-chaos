---
name: ed-discovery
description: "Discover useful tools, concepts, or mental models that apply to real work problems. Like a well-read friend giving you a practical insight. Triggers on: discovery, discover, explore new, new tool, bizu, descoberta."
user-invocable: true
---

# Discovery — Practical Insight

Use this skill for open-ended exploration that should bring back something useful: a tool, concept, mental model, pattern from another industry, cultural idea, historical analogy, or emerging technique.

Unlike `ed-research`, the target does not need to be known in advance. The value is finding something the agent/operator would not naturally search for, then making its practical relevance clear.

## Arguments

- No argument: explore freely and bring back something useful.
- With direction: explore in that direction while keeping room for adjacent discoveries.

## Runtime Boundary

Use the runtime-injected pre-skill context as the starting point.

Do not manage lifecycle, publication, postflight, or generic artifact rites inside this skill. The runtime owns those mechanics.

## What Counts As A Discovery

A good discovery has practical application, not just novelty.

Examples:

- Tool: "prompt tuning by hand can become an optimization loop with DSPy."
- Concept: "Andon cord maps to fail-fast pipeline interruption."
- Industry pattern: "aviation checklists clarify handoff risk in agent workflows."
- Cultural concept: "genchi genbutsu means go see the real system, not the proxy."

Not enough: "this is interesting." The discovery must answer: what changes because we know this?

## Method

### 1. Choose A Starting Direction

Start from one of:

- current work friction;
- a vague operator signal;
- a surprising thread in prior research;
- a nearby field;
- a tool ecosystem;
- an analogy from another discipline;
- pure curiosity when no stronger signal exists.

### 2. Explore Broadly

Search across sources appropriate to the direction:

- tool ecosystems and repositories;
- HN, technical blogs, docs, papers, and public discussions;
- other industries such as manufacturing, aviation, medicine, education, operations;
- history, philosophy, language, and cultural concepts.

The source itself can be the discovery if it reveals a reusable idea.

### 3. Understand The Discovery

For tools, capture:

- what it does;
- how it works;
- how to get started;
- cost and operating constraints;
- limitations and failure modes.

For concepts or patterns, capture:

- original context;
- core mechanism;
- why it mattered there;
- where the analogy does and does not transfer.

### 4. Contextualize To Work

This is the central requirement.

Explain concretely:

- which project or workflow it affects;
- what current friction it addresses;
- how things work now;
- how they would work with the discovery;
- what first practical step would test it;
- what risk would make the analogy fail.

## Quality Criteria

- The application to work must be specific enough to act on.
- Include a before/after comparison for the main application.
- Explain the concept plainly before using it as advice.
- Distinguish useful analogy from overreach.
- Prefer one strong discovery over a list of loosely related curiosities.
- Keep sources traceable.

## Output Contract

Produce a discovery artifact suitable for the uniform report pipeline.

Recommended sections:

1. The Problem Or Friction
2. The Discovery
3. Original Context
4. Application To Work
5. Before And After
6. Getting Started
7. Risks And Limits
8. References

## Privacy Rule

For external posts or public communication, do not identify private organizations, owners, project names, or data that can trace the human operator.
