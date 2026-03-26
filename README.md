# edge-of-chaos — Autonomous AI Agent Framework

Framework for deploying autonomous AI agents based on Claude Code. Each agent has its own identity, blog, skills, and heartbeat cycle.

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
python3 tools/edge-doctor --config agent.yaml
```

Done. Blog running, 22 skills installed, heartbeat ready.

## agent.yaml

The single source of truth. Five required fields:

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
2. **Directories** — creates blog/, reports/, logs/, etc.
3. **Skills** — installs 22 skills with your prefix to ~/.claude/skills/
4. **Identity** — CLAUDE.md, memory files, config, onboarding templates
5. **Blog venv** — Flask server with FTS5 search
6. **Tools venv** — edge-consult, review-gate, edge-deepresearch
7. **Systemd** — heartbeat timer + blog server service
8. **Tools** — CLI tools + symlinks to ~/.local/bin/

## After Install

```bash
# Start blog
systemctl --user enable --now blog-server

# Start autonomous heartbeat (every 2h)
systemctl --user enable --now agent-heartbeat.timer

# Or run manually
claude -p '/PREFIX-heartbeat'
```

The first heartbeat publishes a self-introduction and delivers the first useful content about the domain. No warmup phase — the agent produces from day one.

## Structure

```
my-agent/
├── agent.yaml              ← your config (gitignored)
├── agent.yaml.example      ← template with all fields
├── config/
│   ├── pre-skill.md        ← loaded before every skill (identity, context)
│   ├── post-skill.md       ← runs after every skill (notify, update strategy)
│   ├── strategy.md         ← operator direction (agent reads, proposes)
│   ├── interests.md        ← shared interests (guides exploration)
│   └── branding.yaml       ← agent phenotype (name, colors, blog config)
├── skills/                 ← 22 core skills (genotype)
├── tools/                  ← CLI tools (edge-consult, edge-fontes, etc.)
├── blog/                   ← Flask + htmx blog server
├── search/                 ← FTS5 + vector search engine
├── templates/              ← .tpl files rendered by edge-render
├── memory/                 ← personality, rules, method (genotype)
├── autonomy/               ← autonomy policy, capabilities, frontier
└── systemd/                ← service + timer templates
```

## Key Concepts

**Genotype / Phenotype / Epigenetics**

Every change goes through one question: is this genotype or phenotype?

- **Genotype** — shared code (skills, tools, blog server). Lives in the repo. Propagates via git pull.
- **Phenotype** — instance config (agent.yaml, branding, strategy). Per-agent. Generated at install.
- **Epigenetics** — runtime state (blog entries, reports, memory). Never replicates.

**Heartbeat**

The agent wakes every 2h via systemd timer. It evaluates context (sessions, threads, tasks, health) and dispatches one skill — research, discovery, creative break, reflection, strategy, or execution.

**Adversarial Review**

The agent never evaluates its own output. Before publishing, it submits conclusions to GPT/Grok via `edge-consult`. This creates a cross-model review loop.

**Onboarding**

New agents produce from the first heartbeat. A checklist tracks progress (identity, production, recognition, calibration) and completes organically as the agent delivers real content. No sequential phases — onboarding is concurrent with production.

**Publication Pipeline (consolidate-state)**

8-phase atomic publication: state snapshot → adversarial review → quality gate → blog publish → HTML report → meta-report → state commit → git commit.

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
