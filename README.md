# edge-of-chaos — Autonomous AI Agent Framework

Framework for deploying autonomous AI agents based on Claude Code. Each agent has its own identity, dashboard, skills, and heartbeat cycle.

## Quick Start (5 min)

```bash
# 1. Clone
git clone https://github.com/lucasrp/edge-of-chaos.git my-agent
cd my-agent

# 2. Configure (edit 5 required fields)
cp agent.yaml.example agent.yaml
nano agent.yaml

# 3. Render + Install
python3 tools/edge-render
python3 tools/edge-apply

# 4. Validate
python3 tools/edge-doctor
```

Done. Dashboard running, 22 skills installed, heartbeat ready.

## agent.yaml

Bootstrap spec. Used at render/install time to create runtime config. Five required fields:

```yaml
name: my-agent                    # unique name (lowercase, hyphens)
codename: ma                      # prefix for skills (/ma-pesquisa, /ma-heartbeat)
missao: "What this agent does"    # 1-2 sentences
persona: "How it communicates"    # tone and style
dominio: "government"             # work domain
```

Everything else has smart defaults. See `agent.yaml.example` for all options.

## What edge-apply Does (8 phases)

1. **Render** — generates all files from agent.yaml + templates
2. **Directories** — creates content dirs (`blog/`, `reports/`, `logs/`, etc.)
3. **Skills** — installs 22 skills with your prefix to ~/.claude/skills/
4. **Identity** — CLAUDE.md, memory files, config, onboarding templates
5. **Dashboard venv** — Flask operator surface with FTS5 search
6. **Tools venv** — edge-consult, review-gate, edge-deepresearch
7. **Systemd** — heartbeat timer + dashboard server service (`blog-server` name kept for compatibility)
8. **Tools** — CLI tools + symlinks to ~/.local/bin/

## After Install

```bash
# Start dashboard (service name kept as blog-server for compatibility)
systemctl --user enable --now blog-server

# Start autonomous heartbeat (every 2h)
systemctl --user enable --now agent-heartbeat.timer

# Or run manually
~/.local/bin/heartbeat.sh
```

The first heartbeat publishes a self-introduction and delivers the first useful content about the domain. No warmup phase — the agent produces from day one.

## Structure

```
my-agent/
├── agent.yaml              ← your config (gitignored)
├── agent.yaml.example      ← template with all fields
├── config/
│   ├── preflight.yaml      ← canonical pre-skill protocol source (compiled and executed by CLI)
│   ├── postflight.yaml     ← canonical post-skill protocol source (compiled and executed by CLI)
│   ├── strategy.md         ← operator direction (agent reads, proposes)
│   ├── interests.md        ← shared interests (guides exploration)
│   ├── branding.yaml       ← agent phenotype (name, colors, dashboard config via legacy `blog` key)
│   └── runtime-routers.yaml ← rendered LLM router config used at runtime
├── skills/                 ← 22 core skills (genotype)
├── tools/                  ← CLI tools (edge-consult, edge-fontes, etc.)
├── blog/                   ← Flask + htmx dashboard server (legacy package name)
├── search/                 ← FTS5 + vector search engine
├── templates/              ← .tpl files rendered by edge-render
├── memory/                 ← personality, rules, method (genotype)
├── autonomy/               ← autonomy policy, capabilities, frontier
└── systemd/                ← service + timer templates
```

## Key Concepts

**Genotype / Phenotype / Epigenetics**

Every change goes through one question: is this genotype or phenotype?

- **Genotype** — shared code (skills, tools, dashboard server). Lives in the repo. Propagates via git pull.
- **Phenotype** — rendered runtime config + local state. Per-agent. Generated at install and evolves in place.
- **Epigenetics** — runtime state (feed entries, reports, memory). Never replicates.

**Heartbeat**

The agent wakes every 2h via systemd timer. It runs internal heartbeat curation over sessions, threads, tasks, and health, then dispatches one action skill: research, discovery, report, planner, or autonomy.

**Adversarial Review**

The agent never evaluates its own output. Before publishing, it submits conclusions to GPT/Grok via `edge-consult`. This creates a cross-model review loop.

**Onboarding**

New agents produce from the first heartbeat. A checklist tracks progress (identity, production, recognition, calibration) and completes organically as the agent delivers real content. No sequential phases — onboarding is concurrent with production.

**Publication Pipeline (consolidate-state)**

Atomic publication: state snapshot → adversarial review → quality gate → entry publish → HTML report → state commit → git commit.

## Tools

| Tool | Purpose |
|------|---------|
| `edge-render` | Generate files from agent.yaml + templates |
| `edge-apply` | Provision host (idempotent, 8 phases) |
| `edge-doctor` | Validate installation (30 checks) |
| `edge-consult` | Cross-model adversarial review |
| `edge-fontes` | Unified external source search |
| `edge-index` | Index content into FTS5 + vectors |
| `edge-search` | Hybrid search (semantic + keyword) |
| `edge-event` | Structured event logging |
| `edge-dispatch` | Shadow dispatch-cycle envelope for heartbeat and operator runs |
| `review-gate` | LLM-as-judge quality gate |

## Requirements

- **Claude Code** CLI (`npm install -g @anthropic-ai/claude-code`)
- **Python 3.10+** with venv
- **Git**
- **Linux** with systemd (or macOS with launchd)

API keys (optional, degrade gracefully):
- `OPENAI_API_KEY` — enables adversarial review and quality gates
- `EXA_API_KEY` — enables semantic search via Exa
- `XAI_API_KEY` — enables Grok as second reviewer

## License

MIT
