# Mentor Core v2

## Product Thesis

`edge-of-chaos` is not a generic autonomous agent framework. It is a private
mentoring runtime.

Its job is to stay updated with the mentee's real work, choose beats that are
adherent to that work, search richly, apply methodological rigor, use other LLMs
as reviewers, and produce rich reports that build on previous reports.

If those six things work, the product works.

## Genotype

These are fixed and cannot be configured away:

- Edge is a private mentor for a mentee.
- Every opinion starts from context absorption and delta.
- Threads carry continuity across reports.
- Feynman principles govern reasoning: derive, simplify, expose gaps.
- Skills are consultive by default and do not mutate mentee workspaces.
- Every beat runs the minimum rite:
  - broad search;
  - adversarial review;
  - general review;
  - Feynman review;
  - rich report.

## Phenotype

`agent.yaml` stays rich. It declares:

- mentee identity;
- workspaces;
- domains and interests;
- first steps;
- source providers;
- routines and context seeds;
- paths, cadence, and integrations.

It does not decide whether Edge is a mentor. That belongs to the genotype.

## Context Readiness

The old system tried to enforce prose with primitives, capabilities, and many
deterministic checks. v2 keeps the execution guarantee but removes the ontology.

The runtime always assembles a delta/preskill packet, then runs one LLM-shaped
gate: `Context Readiness Review`.

That review answers two qualitative questions:

1. continuity: does this continue an existing thread, reopen an old one, cross
   threads, or justify a new thread?
2. sufficiency: is the loaded context enough for a mentor to advise without
   becoming generic?

The runtime allows at most two attempts. If the second review fails, the beat
must report the limitation instead of pretending confidence.

## State

The authoritative write side is append-only:

```text
state/events.jsonl
```

Threads, digests, and blog indexes are read models or applied projections:

```text
state/threads/
state/digests/
reports/
blog/entries/
```

Reports are the rich deliverable. Threads are compact continuity.

## Blog

The blog remains, but it is not a dashboard. It is a static archive of rich
reports. Dashboard behavior, chat, interventions, metrics, and runtime controls
are out of v2 core.

## Removed From Core

- primitives and primitive lifecycle;
- capabilities, signals, claims, operator-pressure ontologies;
- voice and branding;
- rich dashboard;
- self-healing genotype;
- autonomous mutation of the mentee workspace.
