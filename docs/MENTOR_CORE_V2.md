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
  - refresh the LLM-maintained digest of Claude chat deltas;
  - load state and delta source manifest, including operator pressure and async operator chat when present;
  - continuity/context/search review twice;
  - fresh broad search after reviewer search suggestions;
  - adversarial review twice;
  - Feynman review;
  - rich report;
  - report utility classification;
  - thread update.

`heartbeat` is not a beat kind. It is a router that selects a real beat kind
and then hands off to the same common rite.

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

Model defaults are non-secret phenotype defaults in `.env.defaults`, not Python
constants. Instance-specific overrides belong in `.env` or `keys/*.env`.

## Context And Search Reviews

The old system tried to enforce prose with primitives, capabilities, and many
deterministic checks. v2 keeps the execution guarantee but removes the ontology.

The runtime always assembles a context pack with two source manifests:

- `delta_source_manifest`: workspaces, Claude sessions, chat digest, threads,
  reports, events, operator pressure, async chat, first steps, seed threads, interests;
- `search_source_manifest`: Exa, Hacker News, X, GitHub, configured status, and
  credential availability without exposing secrets.

Every reviewer sees both manifests. Reviewers are responsible for judging
whether the loader and the search attempts were adequate, suggesting search
terms, and naming missing sources. The runtime does not convert that judgment
into pass/fail branching; it feeds the suggestions into the next straight-line
search/delivery step.

## Straight-Line Rite

## Method Enforcement

v2 avoids primitives as a domain ontology, but it still enforces the beat rite.
The simple split is deterministic orchestration plus LLM judgment.

The deterministic part is the `Rite Gate`. Before a cycle can close, the ledger
must show the required events in order:

```text
CycleOpened -> ChatDigestRefreshed -> StateLoaded -> DeliveryCompleted(context-pack) ->
ContinuitySearchReviewed -> BroadSearchCompleted ->
DeliveryCompleted(evidence-pack-v1) ->
ContinuitySearchReviewed -> BroadSearchCompleted ->
DeliveryCompleted(evidence-pack-v2) ->
ReportDrafted -> DeliveryCompleted(draft-v1) ->
AdversarialSearchReviewed -> BroadSearchCompleted ->
ReportRevised -> DeliveryCompleted(draft-v2) ->
AdversarialReviewed -> ReportRevised -> DeliveryCompleted(draft-v3) ->
FeynmanReviewed -> FinalReportPrepared -> ReportWritten ->
ReportUtilityClassified -> ThreadUpdated -> DigestRebuilt -> BlogBuilt ->
RiteVerified -> CycleClosed
```

This is intentionally small. It proves the runtime followed the method without
recreating primitives, capabilities, claims, or a large deterministic ontology.

The LLM part judges whether the content actually honored the method. Its
judgment is carried into the next delivery, not turned into a control-flow
branch. If the primary LLM provider is unavailable or returns an invalid
response, runtime LLM calls fall back to the local `claude` CLI.

## State

The authoritative write side is append-only:

```text
state/events.jsonl
```

Threads, digests, and blog indexes are read models or applied projections:

```text
state/chat-digest.md
state/operator-pressure.md
state/async-chat.jsonl
state/threads/
state/digests/
state/report-utility.jsonl
reports/
blog/entries/
```

Reports are the rich deliverable. Threads are compact continuity. Report utility
classification is a lightweight projection for future curation of generated
content.

`state/chat-digest.md` is the compact genotypic projection of Claude chats. A
digest LLM reads the previous digest and only new session deltas, ignores
runtime/reviewer boilerplate, and writes a fresh summary of operator direction,
domain vocabulary, open threads, decisions, mistakes to avoid, and the recent
delta. Beats consume this digest instead of raw chat logs.

## Blog

The blog remains, but it is not a dashboard. It is a static archive of rich
reports plus a minimal async operator chat lane. The runtime reads that chat
lane into the next beat and acknowledges what it consumed, but richer
dashboard/runtime-control surfaces stay out of v2 core.

## Removed From Core

- primitives and primitive lifecycle;
- capabilities, signals, claims, operator-pressure ontologies;
- voice and branding;
- rich dashboard;
- self-healing genotype;
- autonomous mutation of the mentee workspace.
