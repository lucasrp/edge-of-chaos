# edge-of-chaos

Autonomous AI agent infrastructure for Claude Code.

## Repo Structure

```
edge-of-chaos/
├── install.sh              ← Interactive installer
├── .env.example            ← API key template
├── models.env.example      ← Default model config
├── blog/                   ← Flask internal blog server
├── tools/                  ← 25+ CLI tools
├── search/                 ← SQLite FTS + vector search
├── skills/                 ← 22 skill templates (SKILL.md)
│   └── _shared/            ← Shared protocols (report-template, state-protocol)
├── memory/                 ← Memory templates (personality, rules, method)
├── autonomy/               ← Autonomy policy and capability tracking
├── ralph/                  ← Autonomous coding agent loop
├── avatar/                 ← Visual identity
├── systemd/                ← Service file templates
└── templates/              ← Generated file templates (CLAUDE.md, MEMORY.md, heartbeat.sh)
```

## How it works

1. User clones repo and runs `./install.sh`
2. Installer asks for: agent name, codename, domain, skill prefix, heartbeat interval
3. Files are deployed to `~/edge/` (system root)
4. Skills are installed to `~/.claude/skills/{prefix}-*/`
5. Blog server + heartbeat timer are set up via systemd
6. Agent operates autonomously via heartbeat, user interacts via blog + Claude Code

## Key concepts

- **Skills are SKILL.md files** — invoked via `/prefix-name` slash commands in Claude Code, NOT via CLI
- **Blog is internal** — agent writes entries, owner reads via browser (port 8766)
- **Heartbeat dispatches skills** — systemd timer invokes Claude Code with a skill
- **Memory is markdown** — no database for memory, just files in ~/edge/memory/
- **consolidar-estado is THE pipeline** — all artifacts go through the 7-phase pipeline
- **Prefix is configurable** — ed-heartbeat becomes {prefix}-heartbeat (fleet pattern)

## Conventions

- Skills reference ~/edge/ paths (fixed install root)
- Tools are standalone executables in ~/edge/tools/
- All shell scripts use set -euo pipefail
- Python tools use #!/usr/bin/env python3
- API keys in ~/edge/secrets/*.env (chmod 600)
- Model selection via ~/edge/secrets/models.env
