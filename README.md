# edge of chaos

**A mentor that keeps one state and one direction across every CLI you use.**

Not another chat that forgets. Edge consolidates what you are doing — across Claude, Codex, Grok, Hermes, and the rest — and steers with a single Direction instead of a pile of disconnected threads.

People already run it. The core works. This repo is the **genotype**: subject-blind code you install; identity and secrets stay on your machine.

```text
one memory  ·  one direction  ·  real mentor, not assistant cosplay
```

| | |
|--|--|
| **Repo** | [github.com/lucasrp/edge-of-chaos](https://github.com/lucasrp/edge-of-chaos) |
| **Language (docs & defaults)** | **en-US** |
| **Operator language** | Optional per install (`agent.yaml` `language:`) — phenotype, not genotype |

---

## Daily use — two commands

The whole daily surface is two skills, on whichever CLI you're in:

```text
> /edge-wake     # switch the mentor on — it reads every CLI surface and renders
                 # where you actually are; unfinished work goes back on the table
> /edge-mentor   # reflect and calibrate — sharpen direction, place the bets,
                 # get pushed back when your behavior drifts from your goal
```

`/edge-wake` to activate. `/edge-mentor` to reflect and calibrate. Everything else (reports, research, maps) hangs off those two.

---

## What you get

- **Multi-CLI continuity** — skills and session film on every harness present on the host (Claude / Codex / Grok / Hermes).
- **Wake → mentor → produce → close** — a rite, not a single prompt: orient, sharpen, ship artifacts with gates.
- **Graph + log** — long-term memory when Neo4j is up; zero-key path still works (FTS / declared-dark).
- **Your install is yours** — `agent.yaml`, secrets, and state are **outputs** of onboarding, never committed as “the” product identity.

---

## Multi-CLI (Claude + Codex + Grok + Hermes)

Install provisions **every CLI harness present on the host**:

| Surface | Skills land in | Sessions filmed by assemble/sweep |
|---------|----------------|-------------------------------------|
| Claude | `~/.claude/skills/{ed,edge}-*` | `~/.claude/projects/…` (native) |
| Codex | `~/.codex/skills/{ed,edge}-*` | `~/.codex/sessions/` |
| Grok | `~/.grok/skills/{ed,edge}-*` | `~/.grok/sessions/` |
| Hermes | `~/.hermes/skills/{ed,edge}-*` | `~/.hermes/state.db` (SQLite — estimate today; full film adapter later) |

Detection = home directory exists (`detect_installed_surfaces`). Phenotype gets a `surfaces:` block for those harnesses. Assemble / quente / sweep **include every installed surface** (not Claude-only). Hermes runs under the user’s own account (`hermes setup` picks the model — edge never pins it); adversarial via `--adversarial hermes` (`review_hermes`, transport `hermes -z`).

On hosts with several CLIs installed, a normal install fills each picker (`/ed-wake`, `@ed-wake`, …).

---

## First-run (no `agent.yaml` yet)

**Agentic path (recommended):** clone, open your CLI in the repo, and ask for the guided install — the `onboard` skill (`skills/onboard/SKILL.md`; `/ed-onboard` once provisioned) interviews you (name, home, secrets, backfill days **with a cost check** — `edge-bootstrap estimate --days N`), runs every step below while explaining, brings up Neo4j (`edge-bootstrap runtime`), and flows into the first mentor session before `finish` + optional heartbeat + local blog URL.

The manual path underneath: `agent.yaml` is the **output** of onboarding, not the seed.

1. **Deliver secrets** into a folder the install will read  
2. **Bootstrap** (name, lookback days, adversarials, optional embeddings)  
3. **Assemble + wake** over that history (builds the mentor package)  
4. **Mentor** (Direction / objective are born here)  
5. Phenotype written → heartbeat may be enabled  

### Defaults (en-US)

| Knob | Default |
|------|---------|
| Docs & README | English (en-US) |
| New phenotype `language:` | `en` (see `tools/onboarding.py` emit) |
| Operator voice in session | Follows install `language` / mentee preference |

### Secrets folder (required)

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
- **Bootstrap, assemble, wake, and onboarding read this folder.** The installer does **not** invent keys.  
- Do not commit secrets (`secrets/` is gitignored).  
- Logs record **key names only**, never values.

### Bootstrap knobs

| Knob | Required | Example |
|------|----------|---------|
| Install home | yes | `--home ~/my-edge` or `EDGE_HOME` |
| Agent name | yes | `--name ed` or `EDGE_AGENT_NAME` |
| Assemble lookback (days) | yes | `--backfill-days 30` or `EDGE_ASSEMBLE_BACKFILL_DAYS` |
| Adversarials | no | `--adversarial codex --adversarial grok` — if none, **the primary model does adversarial** |
| Embeddings key | no | if embedding secret is present, route is wired; else declared-dark |

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

1. Runtime: `tools/edge-python tools/edge-bootstrap runtime --home "$EDGE_HOME"` — pinned Neo4j 5.x in Docker (`edge-neo4j`, password → `secrets/neo4j.env`). No Docker → declared-dark (FTS covers zero-key).  
2. **Wake / predispatch** (lookback = install `backfill_days`) — stamps `state/onboarding-insumo.md` (wake package **without** Direction).  
3. **`/ed-mentor`** with that package — objective / direction / leveling.  
4. Close install:

```bash
tools/edge-python tools/edge-bootstrap finish --home "$EDGE_HOME" \
  --mission "…" --voice "…"
# optional: --enable-heartbeat
```

5. Only then enable autonomous beat/heartbeat (`--enable-heartbeat` = systemd user timer + linger). Artifacts: **http://127.0.0.1:8766** (`blog-server`, loopback-only).

Full contract: [`docs/specs/onboarding-first-run.md`](docs/specs/onboarding-first-run.md).

---

## Legacy install (phenotype already exists)

```bash
tools/edge-python tools/edge-apply --yaml agent.yaml --home ~/edge
# optional: --provision-runtime
```

---

## Layout (install home)

| Path | Role |
|------|------|
| `secrets/` | Operator-delivered keys |
| `state/bootstrap.json` | Pre-phenotype install knobs |
| `state/onboarding-insumo.md` | Mentor package after first wake |
| `agent.yaml` | Phenotype (written at end of onboarding) |
| `skills/`, `blog/`, `memory/` | Install tree |

---

## Documentation

| Doc | Role |
|-----|------|
| [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md) | Fresh-clone guard for agent harnesses |
| [`CONTRACT.md`](CONTRACT.md) | Product contract |
| [`CONTEXT.md`](CONTEXT.md) | Domain map (internal self-model) |
| [`docs/`](docs/) | Specs, ADRs, runtime notes — **English is the house default**; older paths may still mix languages while we migrate |

---

## Contract pointers

- Identity / secrets: CONTRACT C4 — genotype declares where secrets live, not how they arrive.  
- Issue context: first-run path where **yaml = output** of onboarding.
- Public face: ship the core that already works; polish backlog does not block the face.

---

## License / status

Open genotype. Installs carry their own identity. Contributions and issues welcome in **English** on this repo.
