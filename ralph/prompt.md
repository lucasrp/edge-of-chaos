# Ralph Agent Instructions — Continuum

You are an autonomous coding agent building Continuum, a local-first runtime for Claude Code.

## Project Context

**Working directory:** `~/continuum/`
**What you're building:** A Python CLI tool (`continuum`) that adds persistent memory, autonomous routines, and intelligent warm-start to Claude Code.

### Key concept:
When a user runs `continuum init`, the tool:
1. Asks interactively: project name, work directory, work domain, language
2. Detects GitHub account (via `gh auth status` or `git config`)
3. Offers to scan existing Claude Code session transcripts
4. Creates a `.continuum/` directory with memory, skills, config
5. Generates a CLAUDE.md template for Claude Code integration

The scanner reads `~/.claude/projects/*/` looking for JSONL conversation logs, extracts user preferences, corrections, tech stack, and recurring topics — then writes sanitized bootstrap memory.

## Your Task

1. Read the PRD at `ralph/prd.json`
2. Read the progress log at `ralph/progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks: `cd ~/continuum && pip install -e . && continuum --help`
7. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
8. Update `ralph/prd.json` to set `passes: true` for the completed story
9. Append your progress to `ralph/progress.txt`

## Quality Requirements

- Python 3.10+ compatible
- `pip install -e .` must work
- `continuum --help` must show all commands
- All Python files must parse without syntax errors
- Use click for CLI
- Use pyyaml for skill manifests
- Use tomllib (3.11+ stdlib) for reading TOML, write TOML manually (no heavy deps)
- Keep dependencies MINIMAL: click, pyyaml — that's it
- Pytest for tests
- Follow existing code patterns once established

## Architecture Rules

- src layout: `src/continuum/`
- CLI entry point: `continuum.cli:main`
- One module per concern (don't pile everything in one file)
- No Flask, no database, no ML libraries
- File-based everything (markdown + JSON + YAML + TOML)
- Skills are directories with skill.yaml + prompt.md
- Memory is markdown files in .continuum/memory/

## Transcript Format

Claude Code stores conversations in JSONL. Each line is a JSON object. Common structure:
```json
{"type": "human", "content": [{"type": "text", "text": "user message"}]}
{"type": "assistant", "content": [{"type": "text", "text": "response"}, {"type": "tool_use", "name": "Bash", ...}]}
```

The scanner should handle variations gracefully and skip malformed lines.

## Progress Report Format

APPEND to ralph/progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Consolidate Patterns

If you discover a **reusable pattern**, add it to the `## Codebase Patterns` section at the TOP of ralph/progress.txt.

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.
If ALL stories are complete, reply with:
<promise>COMPLETE</promise>

If there are still stories with `passes: false`, end your response normally.

## Important

- Work on ONE story per iteration
- Commit frequently in the ~/continuum repo
- Keep CI green
- Read the Codebase Patterns section in ralph/progress.txt before starting
- ALL paths in PRD are relative to ~/continuum/
