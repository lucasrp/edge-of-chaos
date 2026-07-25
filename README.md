# edge

Genotype for the Edge mentor install (edge-next). Identity and phenotype live per install; this tree is subject-blind code plus optional living install state.

## Multi-CLI (Claude + Codex + Grok + Hermes)

Install provisions **every CLI harness present on the host**:

| Surface | Skills land in | Sessions filmed by assemble/sweep |
|---------|----------------|-------------------------------------|
| Claude | `~/.claude/skills/{ed,edge}-*` | `~/.claude/projects/…` (native) |
| Codex | `~/.codex/skills/{ed,edge}-*` | `~/.codex/sessions/` |
| Grok | `~/.grok/skills/{ed,edge}-*` | `~/.grok/sessions/` |
| Hermes | `~/.hermes/skills/{ed,edge}-*` | `~/.hermes/state.db` (SQLite — estimate hoje; filmagem completa é adaptador futuro) |

Detection = home directory exists (`detect_installed_surfaces`). Phenotype gets a `surfaces:` block enabling those harnesses. Assemble/quente/sweep **include every installed surface** (not Claude-only). Hermes (Nous Research) roda pela conta do próprio usuário (`hermes setup` define o modelo default — o edge nunca fixa modelo pra ele); adversarial via `--adversarial hermes` (rota `review_hermes`, transporte `hermes -z`).

On **ed** and **roberto** (all three CLIs present), a normal install fills all three pickers (`/ed-wake`, `@ed-wake`, …).

## First-run (no `agent.yaml` yet)

**Agentic path (recommended):** clone, open your CLI (Claude/Codex/Grok) in the repo and
ask for the guided install — the `onboard` skill (`skills/onboard/SKILL.md`; `/ed-onboard`
once provisioned) interviews you (name, home, secrets, backfill days **with a cost check**
— `edge-bootstrap estimate --days N`), runs every step below explaining as it goes,
brings up the Neo4j runtime (`edge-bootstrap runtime`), and flows straight into the first
mentor session before closing with `finish` + heartbeat + the local blog URL.

The manual road underneath: `agent.yaml` is the **output** of onboarding, not the seed. Order:

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

1. Bring up the local runtime: `tools/edge-python tools/edge-bootstrap runtime --home "$EDGE_HOME"` — pinned Neo4j 5.x in docker (container `edge-neo4j`, generated password → `secrets/neo4j.env`, idempotent). No docker → declared-dark (FTS covers zero-key).  
2. Run **wake / predispatch** (lookback = install `backfill_days`) — auto-stamps `state/onboarding-insumo.md` (wake package **without** Direction).  
3. Run **`/ed-mentor`** with that insumo — mentor creates objective/direction/leveling.  
4. Close install:

```bash
tools/edge-python tools/edge-bootstrap finish --home "$EDGE_HOME" \
  --mission "…" --voice "…"
# optional: --enable-heartbeat
```

5. Only then may autonomous beat/heartbeat be enabled (`--enable-heartbeat` = systemd user timer + linger). Artifacts read at **http://127.0.0.1:8766** (`blog-server`, loopback-only).

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
