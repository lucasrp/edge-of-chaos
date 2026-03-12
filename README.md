# edge-of-chaos

Autonomous AI agent infrastructure for Claude Code.

Blog, skills, heartbeat, memory, tools, search — everything an autonomous agent needs to operate continuously.

## What is this?

A complete system that turns Claude Code into an autonomous agent with:

- **22 skills** invoked via `/slash-commands` — heartbeat, research, reflection, discovery, strategy, and more
- **Internal blog** — Flask server where the agent writes entries, the owner reads via browser
- **Heartbeat** — systemd timer that dispatches skills on schedule (autonomous operation)
- **consolidar-estado** — 7-phase atomic pipeline for publishing (entry → review → report → verify → meta → state → git)
- **Persistent memory** — markdown files with personality, rules, debugging logs, knowledge clusters
- **25+ CLI tools** — source search, adversarial review, state audit, task ledger, corpus curation
- **Search/RAG** — SQLite + FTS5 + optional vector search across all artifacts
- **Ralph** — autonomous coding agent loop (PRD → implement → commit → repeat)
- **Autonomy policy** — explicit framework for when to execute vs ask

## Quick Start

```bash
git clone https://github.com/lucasrp/edge-of-chaos.git
cd edge-of-chaos
./install.sh
```

The installer will:
1. Ask for agent name, codename, domain, and preferences
2. Deploy all files to `~/edge/`
3. Install 22 skills to `~/.claude/skills/`
4. Set up blog server, heartbeat, and tools
5. Print a capabilities report

**Time:** ~5 minutes for core, ~15 minutes with all options.

## Requirements

- Python 3.10+
- Node.js 18+ (for Claude Code CLI)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Linux with systemd (for heartbeat timer) — macOS/WSL work for manual operation

## API Keys

After install, add your keys to `~/edge/secrets/keys.env`:

```bash
OPENAI_API_KEY=sk-...    # Required: review-gate, edge-consult, search embeddings
EXA_API_KEY=...          # Required: edge-fontes (web search)
XAI_API_KEY=...          # Optional: X/Twitter search
```

## Architecture

```
~/edge/                    ← System root
├── blog/                  ← Flask internal blog (port 8766)
├── tools/                 ← 25+ CLI tools
├── search/                ← SQLite FTS + vector search
├── memory/                ← Personality, rules, debugging, knowledge
├── autonomy/              ← Autonomy policy and capability tracking
├── ralph/                 ← Autonomous coding agent
├── avatar/                ← Visual identity
├── secrets/               ← API keys (.env files)
├── notes/                 ← Research notes
├── logs/                  ← Heartbeat and execution logs
├── state/                 ← Runtime state (tasks, signals, hotspots)
├── reports/               ← Generated reports (YAML + HTML)
└── threads/               ← Investigation threads

~/.claude/skills/{prefix}-*/  ← Skills (slash commands)
~/.claude/CLAUDE.md           ← Global agent instructions
```

## Skills

Skills are invoked via `/{prefix}-{name}` in Claude Code:

| Skill | Purpose |
|-------|---------|
| heartbeat | Autonomous dispatch — scans state, picks and runs one skill |
| pesquisa | Deep dive research on specific topic |
| reflexao | Self-review: process feedback, identify patterns, update files |
| descoberta | Discover useful tools/concepts for real work |
| estrategia | Strategic planning across projects |
| relatorio | Generate structured HTML report |
| blog | Update internal blog |
| contexto | Synthesize current work context |
| carregar | Bootstrap session — load context, absorb state |
| estado | Concrete state inspection of all artifacts |
| executar | Implement proposals or changes |
| experimento | Hypothesis → build → measure → conclude |
| fontes | Unified external source access |
| lazer | Creative leisure at intersection of interests |
| planejar | Propose development cycles |
| prd | Generate Product Requirements Document |
| prototipo | Quick prototype to illustrate an idea |
| autonomia | Track and expand autonomous capabilities |
| curadoria-corpus | Corpus health metrics and curation |
| log | View unified chronological system log |
| mapa | Query connections between ideas/projects |
| salvar-estado | Checkpoint session state to memory |

## Key Tools

| Tool | Purpose |
|------|---------|
| `consolidar-estado` | 7-phase atomic publication pipeline |
| `edge-fontes` | Unified external source search |
| `edge-consult` | Cross-model adversarial review |
| `edge-state-lint` | State consistency linter |
| `edge-state-audit` | State audit and snapshot |
| `review-gate.py` | LLM-as-judge quality gate |
| `yaml_to_html.py` | YAML → HTML report converter |
| `edge-task` | Task ledger management |

## Heartbeat

The heartbeat is a systemd timer that runs `/{prefix}-heartbeat` on schedule.

The heartbeat skill:
1. Scans for signals (user messages, errors, thread deadlines, task updates)
2. Classifies the beat (WORK vs EXPLORE)
3. Dispatches exactly one skill
4. Logs the result

Enable: `systemctl --user enable --now claude-heartbeat.timer`

## License

MIT
