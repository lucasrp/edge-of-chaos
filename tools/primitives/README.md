# Primitives Catalog

Catalog of external source primitives. Each primitive is a standalone CLI executable that talks to ONE external service (arxiv, semscholar, overleaf, etc) and follows the JSON-over-stdout contract defined in `docs/TOOL_CONTRACT.md`.

## Layout

```
tools/primitives/
├── README.md              (this file)
├── _shared/
│   └── usage_log.py       helper: append to state/source-usage.jsonl
├── <name>/
│   ├── meta.yaml          contract (schema, annotations, needs)
│   └── impl               executable (Python/Shell/Go), must be chmod +x
└── ...
```

## meta.yaml contract

```yaml
name: <name>                      # must match directory name
description: "Short human-readable purpose"
mode: read | write | bidirectional
needs: []                         # required env vars (empty = public)
input_schema: {}                  # JSON Schema for CLI args
output_schema: {}                 # JSON Schema for stdout JSON
annotations:                      # mirrors MCP tool annotations
  read_only_hint: bool
  idempotent_hint: bool
  destructive_hint: bool
version: "X.Y.Z"                  # semver; never break signature
```

## impl contract (JSON-over-stdout)

See `docs/TOOL_CONTRACT.md` for the full spec. Summary:

- **Exit 0**: success (JSON in stdout)
- **Exit 1**: error (`{ok: false, error, code}` in stdout + human text in stderr)
- **Exit 2**: misuse (bad args)
- **Stdout**: single JSON object for simple responses, NDJSON (one JSON per line) for streaming
- **Stderr**: human-readable text only, never JSON
- **Binaries**: write to path, return path in JSON (not base64)
- **Logging**: call `_shared/usage_log.log_invocation()` at entry and exit

## How the catalog is used

1. Operator declares `sources: [arxiv, semscholar, overleaf]` in agent.yaml
2. `edge-render` validates each name resolves against this catalog
3. `edge-materialize-primitives` copies `<name>/impl` to `<edge_home>/libexec/<codename>/<name>` and emits `<name>.meta.yaml` alongside
4. Agent invokes primitives via bash: `~/gauss/libexec/gauss/arxiv --query "Q-curvature"`
5. Each invocation is logged to `<edge_home>/state/source-usage.jsonl`

## Adding a new primitive

1. Create `tools/primitives/<name>/meta.yaml` with the full contract
2. Create `tools/primitives/<name>/impl` as executable (chmod +x)
3. Primitive must call `_shared/usage_log.log_invocation()` at entry and exit
4. Test manually: `./tools/primitives/<name>/impl --query "test" | jq .`
5. Bump version in meta.yaml on any signature change (semver)

## Edge-native tools are NOT primitives

Tools like `edge-consult`, `edge-signal`, `edge-search`, `review-gate`, `edge-render`, `edge-apply` are framework infrastructure. They live in `tools/edge-*` and are always available to every agent. They should NOT be declared in `sources:` — the operator doesn't know about them.
