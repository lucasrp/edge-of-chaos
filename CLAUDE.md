# edge-of-chaos

Autonomous AI agent infrastructure for Claude Code.

## Repo Structure

```
edge-of-chaos/
├── install.sh              ← Interactive installer (Linux/macOS)
├── install.ps1             ← Interactive installer (Windows)
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
├── systemd/                ← Service file templates (Linux)
└── templates/              ← Generated file templates (CLAUDE.md, MEMORY.md, heartbeat)
```

## How it works

### Linux/macOS

1. User clones repo and runs `./install.sh`
2. Installer asks for: agent name, codename, domain, skill prefix, heartbeat interval
3. Files are deployed to `~/edge/` (system root)
4. Skills are installed to `~/.claude/skills/{prefix}-*/`
5. Blog server + heartbeat timer are set up via systemd
6. Agent operates autonomously via heartbeat, user interacts via blog + Claude Code

### Windows

1. User clones repo and runs `.\install.ps1` in PowerShell
2. Same interactive setup as Linux
3. Files deployed to `%USERPROFILE%\edge\` (same structure)
4. Skills installed to `%USERPROFILE%\.claude\skills\{prefix}-*\`
5. Heartbeat uses Task Scheduler instead of systemd
6. Blog server started manually via `start-blog.ps1`
7. Shell scripts (consolidar-estado, blog-publish) require Git Bash

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
- API keys in ~/edge/secrets/*.env (chmod 600 on Linux)
- Model selection via ~/edge/secrets/models.env

## Windows Notes

- `python3` is aliased to `python` on Windows — installer detects both
- venv uses `Scripts\` not `bin\` — handled automatically
- Shell scripts (.sh) need Git Bash — `tools/bash-wrapper.ps1` handles this transparently
- No systemd — heartbeat uses Task Scheduler (`ClaudeHeartbeat` task)
- Blog server has no auto-start service — run `~/edge/start-blog.ps1` manually or at login
- `~/edge/` = `%USERPROFILE%\edge\` on Windows
