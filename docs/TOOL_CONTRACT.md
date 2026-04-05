# Tool Contract — JSON-over-stdout for Agent Primitives

> Canonical contract for CLI primitives in `tools/primitives/`. Applies to
> any executable that an agent (LLM running under Claude Code or similar)
> invokes via `Bash()` and parses the output from.

Part of issue #94 — primitives catalog + `sources:` field in agent.yaml.

## TL;DR

| Aspect | Rule |
|---|---|
| **Exit codes** | 0 = success, 1 = error, 2 = misuse (bad args) |
| **Stdout** | Single JSON object OR NDJSON (one JSON per line) for streaming |
| **Stderr** | Human-readable text only. NEVER JSON. |
| **Errors** | Both channels: `{ok:false,error,code}` in stdout + human text in stderr |
| **Binaries** | Write to path, return path in JSON. Base64 inline only if < 1 MB |
| **Progress** | NDJSON events in stdout when piped; stderr human text if TTY |
| **Logging** | Call `_shared/usage_log.log_invocation()` on entry and exit |

## Rationale

There is no IETF RFC for "CLI tool contract when invoked by an LLM agent".
Best practice emerges from convergence across LSP (Language Server Protocol),
MCP (Model Context Protocol), `jq`, `gh`, and Unix tradition. This document
codifies the convergence for the edge-of-chaos primitives catalog.

See also: research report
`reports/2026-04-05-research-tool-catalog-design.html` section 2.4.

## Exit codes

- **0** — success. Stdout contains a valid JSON response.
- **1** — runtime error. The tool tried to do its job but failed (network
  timeout, API error, missing env var, parse failure). Stdout still contains
  a valid JSON error object (`{"ok": false, "error": "...", "code": N}`);
  stderr contains a human-readable explanation.
- **2** — misuse. The tool was called with bad arguments (missing required
  flag, invalid enum value). Stderr contains the usage error; stdout may
  contain JSON error object but is not required.

Do NOT use other exit codes unless you have a specific reason. Consumers
check `exit == 0` for success, everything else for error.

## Stdout format

### Single JSON (simple/fast operations)

Preferred for tools that complete quickly (< few seconds) and return one
coherent result.

```json
{"ok": true, "query": "Q-curvature", "count": 12, "results": [...]}
```

- Single line if possible, or pretty-printed if size justifies it.
- Must be a single JSON value (object preferred).
- No trailing newline characters inside the JSON string.

### NDJSON (streaming operations)

For tools that emit progress, multiple results, or take minutes. One valid
JSON object per line. Each line is parseable independently.

```
{"type": "start", "total": 1000}
{"type": "progress", "current": 250, "percent": 25}
{"type": "progress", "current": 500, "percent": 50}
{"type": "result", "data": {"id": "2503.12345", "title": "..."}}
{"type": "end", "ok": true, "count": 500, "duration_ms": 12345}
```

- Each line is a complete JSON object.
- `type` field is REQUIRED on every event.
- Suggested types: `start`, `progress`, `result`, `warn`, `error`, `end`.
- Final `end` event is REQUIRED — signals normal completion.

## Stderr format

- **Human-readable text only.** Never JSON.
- Used for: errors, warnings, debug traces, progress when TTY is interactive.
- LLM agents typically parse stdout for structured data and show stderr to
  the human operator during debugging.

```
Error: EXA_API_KEY not set in environment
Warning: rate limited, retrying in 2s...
```

## Error handling

Errors go to BOTH channels:

**Stdout (JSON, for LLM):**
```json
{"ok": false, "error": "unauthorized", "code": 401}
```

**Stderr (text, for operator debugging):**
```
Error: invalid API key for semantic scholar (HTTP 401)
```

**Exit code:** 1 (runtime) or 2 (misuse).

Rationale: LLMs parse stdout structured data and can reason about error
codes. Humans debugging via `| tee stderr.log` see the friendly text.
Both audiences served, no conflict.

## Binary outputs

Tools that produce binary artifacts (PDFs, images, archives):

**Preferred: write to path, return path in JSON.**
```json
{"ok": true, "pdf_path": "/tmp/gauss-cache/2503.12345.pdf", "size_bytes": 847123}
```

**Discouraged: base64 inline.**
Only if the binary is < 1 MB and the caller explicitly expects inline
content. Large base64 payloads bloat context and break streaming.

## Progress events

For operations > few seconds, emit NDJSON progress events to stdout. Only
emit to stdout when output is piped (not a TTY). Detect via `isatty()`:

```python
if sys.stdout.isatty():
    # Human running interactively — show spinner on stderr
    print("Fetching...", file=sys.stderr, flush=True)
else:
    # Piped to another tool or captured by agent — emit NDJSON
    print(json.dumps({"type": "progress", "current": 250}), flush=True)
```

## jq-friendliness

Structure output so common `jq` queries work without contortion:

**Good:**
```json
{"results": [{"id": 1}, {"id": 2}]}
```

Works with `jq '.results[]'` and `jq '.results | length'`.

**Bad:**
```json
{"1": {"title": "..."}, "2": {"title": "..."}}
```

Object-keyed collections break generic iteration.

**Also good (top-level array):**
```json
[{"id": 1}, {"id": 2}]
```

Works with `jq '.[]'`.

## Invocation logging

Every primitive MUST call `_shared/usage_log.log_invocation()` on entry
and on exit (success or failure). This appends to
`$EDGE_HOME/state/source-usage.jsonl` and is the raw material for diversity
analysis, discovery tracking, and evidence-based issue filing.

```python
from usage_log import log_invocation

def main():
    start_ts = time.time()
    log_invocation("arxiv", "start", input_summary=f"query={args.query!r}")
    try:
        result = do_work()
        log_invocation(
            "arxiv", "end",
            duration_ms=int((time.time() - start_ts) * 1000),
            ok=True,
            result_count=len(result),
        )
    except Exception as exc:
        log_invocation(
            "arxiv", "end",
            duration_ms=int((time.time() - start_ts) * 1000),
            ok=False,
            error=str(exc),
        )
        raise
```

## Versioning

Each primitive's `meta.yaml` declares a `version:` field (semver).

- **Never break signatures** — adding optional fields is fine, removing or
  renaming is not.
- **Breaking change** = new major version = new primitive file
  (e.g., `arxiv` → `arxiv-v2`), old version kept for backward compat.
- **Additive change** = bump minor, same file.
- **Bugfix** = bump patch, same file.

Silent schema breakage is the #1 production failure mode for agent tool
ecosystems — version discipline prevents it.

## Anti-patterns

- **JSON on stderr.** Always keep stderr as human text.
- **Mixed output.** Don't interleave progress and results on stdout unless
  using NDJSON with `type` discrimination.
- **Swallowing errors.** Always emit error JSON on stdout, error text on
  stderr, AND exit 1. All three.
- **Base64 bombs.** Don't embed multi-MB binaries in JSON responses.
- **Breaking signatures in place.** Bump major version and ship new file.
- **Logging to stdout.** Logging goes via `log_invocation()` → jsonl file,
  not stdout, not stderr.

## See also

- `tools/primitives/README.md` — catalog layout and how to add a primitive
- `tools/primitives/_shared/usage_log.py` — logging helper
- `tools/primitives/arxiv/impl` — reference implementation (read-only)
- `tools/primitives/overleaf/impl` — reference implementation (bidirectional, stub)
- Research report: `reports/2026-04-05-research-tool-catalog-design.html`
