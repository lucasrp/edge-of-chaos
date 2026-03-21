# Agent Template — Claude Code Autonomous Agent

Template for creating autonomous AI agents based on Claude Code CLI.

## Quick Install

```bash
# Clone and run installer
git clone https://github.com/alexlopespereira/agent-template.git my-agent
cd my-agent && bash install.sh
```

Or use as a GitHub template:
```bash
gh repo create my-agent --template alexlopespereira/agent-template --private
cd my-agent && bash install.sh
```

## What the Installer Does

1. Asks questions about your specific installation
2. Substitutes placeholders in all configuration files
3. Sets up the autonomous heartbeat cycle (systemd/launchd/Task Scheduler)
4. Connects your business knowledge base
5. Triggers the first cycle to validate

## Structure After Installation

```
your-repo/
├── CLAUDE.md           ← agent instructions (personalized)
├── MEMORY.md           ← persistent memory (starts empty)
├── heartbeat.sh        ← autonomous execution script
├── kb.config           ← knowledge base configuration
├── tools/              ← agent CLI tools
├── memory/             ← structured memory files
│   ├── rules-core.md   ← cross-cutting rules (max 15)
│   ├── personality.md  ← cognitive profile
│   ├── metodo.md       ← Feynman method
│   ├── debugging.md    ← error log
│   └── topics/         ← thematic knowledge clusters
├── blog/entries/       ← agent blog entries
├── reports/            ← HTML reports
├── logs/               ← execution logs
├── secrets/            ← API keys (gitignored)
└── systemd/            ← systemd units (Linux)
```

## Prerequisites

- **Claude Code**: `npm install -g @anthropic-ai/claude-code`
- **GitHub CLI**: `gh auth login`
- **Python 3.10+** with pip and venv
- **ANTHROPIC_API_KEY** configured
- **OPENAI_API_KEY** for adversarial review (review-gate, edge-consult)

## Key Concepts

### Heartbeat
The agent wakes up at a configurable interval, evaluates context (pending tasks, user messages, investigation threads), and dispatches an appropriate skill — research, discovery, creative leisure, reflection, strategy, or execution.

### Adversarial Review
The agent never evaluates its own output. Before publishing, it submits conclusions to a different model (GPT) via `edge-consult` for adversarial review. This creates a checks-and-balances loop.

### Knowledge Clusters
Persistent knowledge organized as text that changes behavior. Rules in `rules-core.md`, thematic clusters in `memory/topics/`. The test: "if I delete this file and behavior doesn't change, it was clutter."

### Pipeline (consolidar-estado)
8-phase atomic publication pipeline: state snapshot, adversarial review, quality gate, blog publish, HTML report, meta-report, state commit, git structured commit.

## Documentation

See [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) for detailed setup and operation guide.

## Architecture

See [REPLICATION_BLUEPRINT.md](REPLICATION_BLUEPRINT.md) for the full architectural blueprint.
