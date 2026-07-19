# edge

Genotype for the Edge mentor install (edge-next). Identity and phenotype live per install; this tree is subject-blind code plus optional living install state.

## First-run (no `agent.yaml` yet)

`agent.yaml` is the **output** of onboarding, not the seed. Order:

1. **Deliver secrets** into a folder the install will read  
2. **Bootstrap** (name, lookback days, adversarials, optional embeddings)  
3. **Assemble + wake** over that history (structures the mentor insumo)  
4. **Mentor** (Direction / objective born here)  
5. Phenotype written → heartbeat may be enabled  

### Secrets folder (required)

Create a secrets directory under the install home (default) or point `EDGE_SECRETS_DIR`:

```text
$EDGE_HOME/secrets/
  openai.env      # e.g. OPENAI_API_KEY=…
  xai.env
  neo4j.env       # EDGE_NEO4J_PASSWORD=… when using graph
  exa.env
  github.env
  …
```

- Format: one `VAR=value` per line (optional `export ` prefix).  
- **Bootstrap, assemble, wake, and onboarding read this folder.** The installer does **not** download or invent keys.  
- Do not commit secrets (`secrets/` is gitignored).  
- Logs and insumo packages record **key names only**, never values.

### Bootstrap knobs

| Knob | Required | Example |
|------|----------|---------|
| Install home | yes | `--home ~/my-edge` or `EDGE_HOME` |
| Agent name | yes | `--name ed` or `EDGE_AGENT_NAME` |
| Assemble lookback (days) | yes | `--backfill-days 30` or `EDGE_ASSEMBLE_BACKFILL_DAYS` |
| Adversarials | no | `--adversarial codex --adversarial grok` — if none available, **the primary model does the adversarial** |
| Embeddings key | no | if `OPENAI_API_KEY` (or configured embedding secret) is in `secrets/`, embedding route is wired; otherwise declared-dark |

```bash
# after placing secrets under $EDGE_HOME/secrets/
export EDGE_HOME=~/my-edge
tools/edge-python tools/edge-bootstrap \
  --home "$EDGE_HOME" \
  --name ed \
  --backfill-days 30
# optional: --adversarial codex --adversarial grok
```

Heartbeat stays **off** until onboarding completes.

### After bootstrap

1. Run **wake** (assemble inside the lookback window) — produces `state/onboarding-insumo.md` (wake package **without** Direction).  
2. Run **`/ed-mentor`** with that insumo — mentor creates objective/direction and emits `agent.yaml`.  
3. Only then may autonomous beat/heartbeat be enabled.

Full contract: [`docs/specs/onboarding-first-run.md`](docs/specs/onboarding-first-run.md).

## Legacy install (phenotype already exists)

```bash
tools/edge-python tools/edge-apply --yaml agent.yaml --home ~/edge
# optional runtime: --provision-runtime
```

## Layout (install home)

| Path | Role |
|------|------|
| `secrets/` | Operator-delivered keys (read by onboarding) |
| `state/bootstrap.json` | Pre-phenotype install knobs |
| `state/onboarding-insumo.md` | Mentor insumo after first wake |
| `agent.yaml` | Phenotype (written at end of onboarding) |
| `skills/`, `blog/`, `memory/` | Install tree |

## Contract pointers

- Identity / secrets: CONTRACT C4 — genotype declares where secrets live, not how they arrive.  
- Issue context: edge-next#136 (first-run); this README implements the stronger “yaml = output” path.
