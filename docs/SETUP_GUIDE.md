# Setup Guide — Agent Template

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Post-Install Verification](#post-install-verification)
4. [Day-to-Day Operations](#day-to-day-operations)
5. [Knowledge Base Management](#knowledge-base-management)
6. [Heartbeat Configuration](#heartbeat-configuration)
7. [Adding Tools](#adding-tools)
8. [Skills](#skills)
9. [Adversarial Review Setup](#adversarial-review-setup)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- Claude Code CLI >= 2.1.x (`npm install -g @anthropic-ai/claude-code`)
- Node.js >= 22.x
- Python >= 3.10 with pip and venv
- GitHub CLI installed and authenticated (`gh auth status`)
- Git configured
- Internet access (for external APIs)

### Platform-Specific
- **Linux**: systemd (for timer-based heartbeat)
- **macOS**: launchd (for plist-based heartbeat)
- **Windows**: Task Scheduler (PowerShell script)

### API Keys Required

| Variable | Service | Required? | Where to get |
|----------|---------|-----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic | Yes | console.anthropic.com |
| `OPENAI_API_KEY` | OpenAI | Yes | platform.openai.com |
| `EXA_API_KEY` | Exa.ai | Optional | exa.ai |
| `XAI_API_KEY` | xAI (Grok) | Optional | x.ai |

---

## Installation

Run `bash install.sh` and follow the prompts. The installer will:
1. Ask for agent identity (name, mission, persona, domain)
2. Ask for API credentials
3. Configure heartbeat frequency and prompt
4. Connect your knowledge base
5. Generate all configuration files from templates
6. Install the heartbeat daemon
7. Run the first heartbeat to validate

---

## Post-Install Verification

```bash
# 1. Timer/daemon active?
# Linux:
systemctl --user status claude-heartbeat.timer
# macOS:
launchctl list | grep heartbeat

# 2. Last heartbeat executed?
tail -20 ~/.claude/heartbeat-output.log

# 3. Blog server running? (if configured)
curl -s http://localhost:$BLOG_PORT/api/chat 2>/dev/null

# 4. State consistent?
./tools/edge-state-lint 2>/dev/null

# 5. Claude Code authenticated?
claude --version

# 6. APIs working?
./tools/edge-consult.py "Test: 1+1=2. Any flaws?" 2>/dev/null
```

---

## Day-to-Day Operations

### View Logs
```bash
# Heartbeat output
tail -f ~/.claude/heartbeat-output.log

# Daily log
cat logs/heartbeat-$(date +%Y-%m-%d).log

# Linux systemd journal
journalctl --user -u claude-heartbeat.service --since today
```

### Trigger Heartbeat Manually
```bash
# Via systemd (Linux)
systemctl --user start claude-heartbeat.service

# Via launchd (macOS)
launchctl start com.OWNER.AGENT.heartbeat

# Via Claude Code directly
cd ~/your-agent && claude -p "/PREFIX-heartbeat" --max-turns 30
```

### Check State
```bash
# State consistency
./tools/edge-state-lint

# Claims accumulated
./tools/edge-claims --stats
./tools/edge-claims --open  # open gaps

# Tasks
./tools/edge-task list

# Recent events
./tools/edge-event recent

# Briefing (compacted state)
cat briefing.md
```

### Pause/Resume
```bash
# Linux: stop timer
systemctl --user stop claude-heartbeat.timer

# Linux: resume timer
systemctl --user start claude-heartbeat.timer

# macOS: unload
launchctl unload ~/Library/LaunchAgents/com.OWNER.AGENT.heartbeat.plist

# macOS: reload
launchctl load ~/Library/LaunchAgents/com.OWNER.AGENT.heartbeat.plist
```

---

## Knowledge Base Management

### Initial Setup
The knowledge base path is configured during install. Supported types:
- **local**: directory with documents on disk
- **git**: git repository URL (auto-pulled on heartbeat start)
- **url**: HTTPS URL to documents

### Expanding the KB
1. Add documents to your KB path
2. If type is `git`: commit and push; agent pulls on next heartbeat
3. If type is `local`: just add files — agent reads them next cycle

### KB Config
Edit `kb.config` to change:
- `refresh`: when to update (`on-start`, `hourly`, `daily`, `manual`)
- `priority_files`: agent fills this on first run; edit to prioritize specific docs

---

## Heartbeat Configuration

### Changing Frequency

**Linux (systemd):**
Edit `~/.config/systemd/user/claude-heartbeat.timer`:
```ini
OnActiveSec=1h          # first run after boot
OnUnitActiveSec=1h      # subsequent runs
```
Then: `systemctl --user daemon-reload`

**macOS (launchd):**
Edit `~/Library/LaunchAgents/com.OWNER.AGENT.heartbeat.plist`:
```xml
<key>StartInterval</key>
<integer>3600</integer>  <!-- seconds -->
```
Then: `launchctl unload ... && launchctl load ...`

### Changing the Heartbeat Prompt
Edit the `HEARTBEAT_PROMPT` section in `heartbeat.sh` (or rerun the relevant part of the installer).

---

## Adding Tools

1. Place the tool script in `tools/`
2. Make it executable: `chmod +x tools/my-tool`
3. Add a description to `CLAUDE.md` under the Tools section
4. If the tool has steps to track, add them to `tools/skill-steps-registry.yaml`
5. Create a wrapper in `~/.local/bin/` if you want it available globally:
```bash
cat > ~/.local/bin/my-tool << 'EOF'
#!/bin/bash
~/your-agent/tools/venv/bin/python3 ~/your-agent/tools/my-tool.py "$@"
EOF
chmod +x ~/.local/bin/my-tool
```

---

## Skills

Skills are Claude Code slash commands in `~/.claude/skills/PREFIX-NAME/SKILL.md`.

### Core Skills (installed by template)
- `heartbeat` — autonomous dispatcher
- `pesquisa` — deep research
- `descoberta` — lateral exploration
- `lazer` — creative break
- `reflexao` — self-reflection
- `estrategia` — strategic planning
- `planejar` — concrete proposals
- `executar` — implementation (manual only)

### Creating New Skills
1. Create directory: `mkdir -p ~/.claude/skills/PREFIX-newskill/`
2. Create `SKILL.md` with the skill instructions
3. Register in `tools/skill-steps-registry.yaml` if it has trackable steps

---

## Adversarial Review Setup

### edge-consult (Cross-model Review)
```bash
# Create wrapper
cat > ~/.local/bin/edge-consult << 'EOF'
#!/bin/bash
~/your-agent/tools/venv/bin/python3 ~/your-agent/tools/edge-consult.py "$@"
EOF
chmod +x ~/.local/bin/edge-consult

# Test
edge-consult "Test: 1+1=2. Any flaws?"
```

### review-gate (Quality Gate)
Automatic LLM-as-judge pipeline before publication. 3 phases:
1. Co-author (GPT with tools) enriches draft
2. Reviewer (GPT blind) scores on 6 dimensions (threshold: 3.5/5)
3. Refiner applies feedback. 2 rounds.

Cost: ~$0.02-0.05 per review.

---

## Troubleshooting

| Symptom | Probable Cause | Solution |
|---------|---------------|---------|
| Timer active but heartbeat doesn't run | PATH doesn't include `claude` (node) | Check PATH in .service: must include node/nvm directory |
| Heartbeat runs but doesn't dispatch skill | Claude Code not authenticated | Run `claude` interactively for browser login |
| `consolidar-estado` fails at Phase 1 | Blog server not running | Start blog server |
| `consolidar-estado` fails at Phase 0.5 | YAML doesn't pass review-gate | Adjust YAML based on feedback |
| `edge-consult` fails | OPENAI_API_KEY invalid or missing | Check secrets/*.env |
| `edge-fontes` no Exa results | EXA_API_KEY invalid | Check secrets/exa.env |
| Heartbeat repeats same topic | Anti-saturation not working | Check daily log: if >3 beats on same topic, force change |
| Skills silently skipping steps | Missing `edge-skill-step` calls | Check skill-steps-registry.yaml |
| `heartbeat-preflight.sh` always PREFLIGHT_CLEAN | Blog chat API not responding | Check blog server is running |
