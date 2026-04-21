# Primitives

Primitives are standalone CLI executables that talk to ONE external source.
They are NOT pre-built. They are created on demand by the agent when it
first needs them.

## How primitives are born

1. Operator declares `sources:` in agent.yaml with `{name, description}`
2. Agent tries to use a source during work → exit 127 (not found)
3. Runtime state carries the declared source in `state/sources-manifest.yaml`;
   agent reads the description there (WHAT) + `docs/TOOL_CONTRACT.md` (HOW)
4. Agent writes contract (meta.yaml) + implementation + tests it
5. Saves to `<edge_home>/libexec/<codename>/<name>`, registers in manifest
6. Autonomy deepens the primitive later with evidence from usage log

Use `tools/edge-primitive-lifecycle` for the contract/manifest/probe steps so
the lifecycle is observable in telemetry and no longer lives only in prose.

Use `tools/edge-primitives status --json` for the canonical read model:
declared sources, manifest state, local files, probe status, and recent usage.

See `docs/TOOL_CONTRACT.md` for the full contract specification.

## Where primitives live

```
<edge_home>/libexec/<codename>/
├── arxiv                    executable (created by agent)
├── arxiv.meta.yaml          contract (created by agent)
├── semscholar
├── semscholar.meta.yaml
└── ...
```

## Shared helpers

`tools/primitives/_shared/usage_log.py` — invocation logging helper.
Every primitive should import and call `log_invocation()` at entry and exit.
Logs to `<edge_home>/state/source-usage.jsonl`.

## Edge-native tools are NOT primitives

`edge-consult`, `edge-signal`, `edge-search`, `review-gate`, etc. are
framework infrastructure in `tools/edge-*`. Always available to every
agent. Never declared in `sources:`. Operator doesn't know about them.
