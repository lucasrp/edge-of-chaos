# Primitive Generation Pipeline

Issue: #339

## Ontology

Edge capabilities should be described by three separate axes:

- `surface`: the system or domain being touched, such as `github`, `grafana`, `meta`, `google_drive`, or `slack`.
- `operation`: the relationship with that surface: `signals`, `search`, or `mutate`.
- `capability`: an atomic parameterizable action that implements one operation on one surface.

Examples:

- `github.signals.project_delta` observes current project movement.
- `github.search.repo` retrieves repository knowledge.
- `github.mutate.pr_comment` changes GitHub state by posting a comment.

Shared surface does not imply shared ontology. A GitHub delta, a GitHub code search, and a GitHub PR comment must remain separate capabilities because they have different safety, cost, retry, and routing semantics.

## Operation Classes

`signals` retrieve information about current real state or recent deltas. They are the primary language for heartbeat routing and gating. Health is a signal.

`search` retrieves broader knowledge from external or accumulated knowledge surfaces. `edge-search` and `edge-sources` remain the search lane.

`mutate` changes state. Mutating capabilities require stricter operator intent, clearer contracts, and safer probes than read-only capabilities.

## Human YAML Direction

Human-facing `agent.yaml` should remain natural language. It should describe surfaces and how each surface is used, not force operators to hand-author every primitive.

Example:

```yaml
surfaces:
  - key: github
    usage: Observe project movement, search repository knowledge, and change repository state only when explicitly needed.
  - key: grafana
    usage: Observe runtime state and inspect operational evidence.
  - key: meta
    usage: Observe campaign state and extract campaign signals before marketing decisions.
```

Render/apply/install turns that prose into candidate capabilities, probes, contracts, and warnings.

## Intermediate Representation

The install pipeline should materialize a reviewed intermediate representation before writing executable primitives:

```yaml
surface: meta
operation: signals
capability: meta.signals.campaign_snapshot
description: Read current campaign state and summarize delivery, spend, conversions, and event health.
inputs:
  account_id: required string
  campaign_filter: optional string
outputs:
  status: enum[ok,degraded,broken]
  observations: list
  evidence_refs: list
install_policy:
  materialize: eager
  probe_required: true
  credentials: meta.env
runtime_policy:
  safe_for_heartbeat: true
  mutates_state: false
  cache_ttl_seconds: 300
failure_policy:
  report_warning: true
  retry: next_apply
  fallback: use operator-visible degraded signal
```

## Generation Stages

1. Ingest prose from `agent.yaml`, operator pressure digests, docs, and explicit install notes.
2. Infer candidate surfaces and classify each requested use as `signals`, `search`, or `mutate`.
3. Derive atomic capabilities with one operation per capability.
4. Define contracts: inputs, outputs, side effects, credentials, expected evidence, and safety level.
5. Classify install behavior: eager materialization, lazy materialization, probe-only, or manual review required.
6. Generate probes and tests before treating the capability as healthy.
7. Materialize wrappers into `libexec` or static CLI registry entries.
8. Emit health and recovery metadata when materialization is absent, degraded, or broken.

## Validation And Testing

Every generated capability needs a probe contract. Read-only capabilities should be probeable during install/apply even if that makes install slower. Mutating capabilities should probe authentication and dry-run semantics without changing state.

Validation should cover:

- contract shape and parameter validation
- credential presence without leaking values
- provider reachability or a deterministic local substitute
- output schema validation
- telemetry emission
- degraded and missing-credential paths
- integration into `edge-search`, `edge-signals`, or a mutate-specific invoker

## Recovery Strategy

Broken substrate should be operator-visible, not buried in logs. Primitive/capability health should affect:

- install/apply output
- health snapshots
- heartbeat routing and gating
- reports after quality checks
- postflight summaries

Reports should include a `Primitive health warning` block when relevant, with:

- broken or degraded primitives/capabilities
- what they prevented
- fallbacks used
- likely failure class: missing credentials, degraded provider, missing materialization, broken probe, absent binding, or contract drift
- next recovery path

## Runtime Slice Implemented Now

This issue introduces two runtime pieces that make the ontology executable:

- `edge-signals`: collects state-oriented signals such as health, current dispatch, queue, workflow health, render/apply drift, primitive health, capability health, and recent failure events.
- `edge-context`: provides one UX entrypoint while preserving separate internal lanes for `signals` and `sources`.

The output intentionally keeps the lanes separate:

```json
{
  "query": "meta events",
  "signals": {"signals": []},
  "sources": {"results_by_source": {}},
  "summary": {}
}
```

This gives heartbeat and skills a simple context command without collapsing signals and search into the same category.
