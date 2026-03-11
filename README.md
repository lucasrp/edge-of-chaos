# Edge of Chaos

Local-first runtime for Claude Code: persistent memory, autonomous routines, and intelligent bootstrap via transcript scanning.

## Installation

```bash
git clone <repo-url> && cd continuum
pip install -e .
```

## Quick Start

```bash
# Initialize continuum in your project
continuum init

# Scan your Claude Code transcripts for preferences and patterns
continuum scan

# Check installation health
continuum doctor

# See current status
continuum status

# List available skills
continuum skills list

# Run a skill
continuum run consolidate-state

# Create a custom skill
continuum skills new my-skill
```

## What it does

1. **`continuum init`** — Sets up `.continuum/` directory with config, memory, and skills structure.
2. **`continuum scan`** — Reads your Claude Code session transcripts (`~/.claude/projects/`), extracts preferences, corrections, tech stack, and recurring topics, then writes sanitized bootstrap memory.
3. **`continuum run <skill>`** — Executes a skill (prompt-based or Python script) that reads memory and produces outputs.
4. **`continuum doctor`** — Verifies your installation is healthy.
5. **`continuum status`** — Shows memory stats, bootstrap status, available skills, and recent runs.

## Requirements

- Python 3.10+
- Claude Code (for transcript scanning and prompt-based skills)

## License

MIT
