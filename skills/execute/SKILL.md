---
name: ed-execute
description: "Execute proposals or changes in projects. Direct implementation or via Ralph. Manual invocation only — only when the user explicitly asks. Triggers on: execute, executar, rodar proposta, implementar proposta, implementar, run proposal, implement."
user-invocable: true
---

# /ed-execute — Change Execution

Direct implementation or via Ralph. Always generates a report. Only runs when the user explicitly asks — heartbeat NEVER dispatches.

**Scope:** any modification the user requests — projects (`~/work/`), system (`~/edge/`, `~/.claude/skills/`), or both.

**Architectural role:** this is the ONLY skill that requires human-in-the-loop. Every other skill operates on the agent's own substrate (memory, blog, state, reports, own repo, genotype issues/PRs) and runs to completion without mid-protocol confirmation (see `memory/rules-core.md` → Decision → external-state boundary). `/ed-execute` is where the external-state boundary is crossed, so HITL lives here and only here.

**Two execution profiles:**
- **Project (`~/work/`):** full protocol — git checks, tests, rollback, branch
- **System (`~/edge/`, `~/.claude/`):** lightweight protocol — no git/tests, but blog + report ALWAYS

---

## Arguments

| Argument | Example | Behavior |
|----------|---------|----------|
| `#N` | `/ed-execute #22` | Looks up proposal #22 in propostas.md |
| Description | `/ed-execute circuit breakers` | Searches by keyword in proposals |
| Direct instruction | `/ed-execute add termination conditions to base_chat.py` | Executes without formal proposal |
| No argument | `/ed-execute` | Lists `[PROPOSAL]` proposals, user chooses |

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol (10 Steps)

### Step 1: Understand the Instruction

Read the minimum necessary to execute:

1. **Proposal/instruction** — locate proposal in propostas.md or understand direct instruction from user
2. **If formal proposal:** read the proposal's HTML report for lineage and technical details
3. **If target is project ~/work/:** read the target project's CLAUDE.md (if it exists) for conventions

Run `/ed-context` if you need detailed project status (git, boards, issues).

### Step 2: Generate PRD and Execute via Task Agents

**Whenever convenient, use [Ralph](https://github.com/snarktank/ralph) (skill /ralph).** Decompose into User Stories, execute via task agents.

1. **Generate PRD** following the skill `/ed-prd`:
   - Small User Stories (1 per context window)
   - Order by dependency
   - Acceptance criteria with tests
   - Save in `~/edge/notes/prd-execute-[slug].md`

2. **Convert to prd.json** using the skill `/ralph`

3. **Execute via Task agents** (1 agent per User Story, in dependency order):
   - Each Task agent receives: US specs, relevant files, acceptance criteria
   - Works identically to a Ralph iteration — isolated context, 1 story at a time
   - **Note:** `ralph.sh` does NOT run nested inside another Claude Code session (CLAUDECODE env blocks it). Task agents are the correct mechanism.

### Step 3: Pre-Execution Derivation (Feynman)

BEFORE executing, derive expectations. Think out loud:

- **Which files will change?** (list based on existing code)
- **What risks do I foresee?** (conflicts, dependencies, side effects)
- **What can go wrong?** (failure scenarios)

Note gaps explicitly:
```
[GAP: don't know if X will conflict with Y]
[GAP: need to verify if Z already exists in the project]
```

**Feeds the "Expectation vs Reality" section of the final report.**

### Step 3.5: Search external sources (MANDATORY)

Run `/ed-sources execute "[technology/pattern]"` to get best practices and gotchas from all relevant sources (Web, X, GitHub).

Incorporate into pre-execution derivation (Step 3) and cite in the report (with URL).

### Step 4: Validate Preconditions

#### Project Profile (`~/work/`)

Verify ALL items before proceeding:

1. **Target project exists:** `ls ~/work/[project]`
2. **Git status clean:** `cd ~/work/[project] && git status --porcelain`
   - If dirty: **STOP.** Report to user. Do not continue with dirty working tree.
3. **Current branch:** `git branch --show-current`
   - If `main` or `master`: ask if user wants to create a new branch.
4. **Baseline tests:** Run suite BEFORE changing anything
   - Python: `pytest` / Node: `npm test` / Typecheck: `npx tsc --noEmit` or `mypy .`
5. **Save rollback snapshot:**
   ```
   BRANCH=[current branch]
   SHA=[last commit SHA]
   TESTS_BASELINE=[result]
   ```

**If critical precondition fails (project doesn't exist, dirty git): STOP.**

#### System Profile (`~/edge/`, `~/.claude/`)

Minimal preconditions:
1. **Target files exist:** verify paths
2. **Read files before editing:** understand what exists before changing
3. **If server (blog, etc.):** check if running (`systemctl --user status`)

No git, tests, or formal rollback. Blog + report serve as change documentation.

### Step 5: Execute User Stories

The PRD and prd.json were already generated in Step 2. Execution happens via Task agents (Step 2.3).

For each User Story (in priority order):
1. Read target files the story will modify
2. Launch Task agent with detailed prompt (specs, criteria, file context)
3. Verify agent result before moving to the next story
4. If story failed: document and assess whether next stories depend on it

### Step 6: Verify Result

After Ralph execution:

1. **Run tests:**
   ```bash
   cd ~/work/[project] && pytest  # or npm test
   ```
2. **Compare with Step 4 baseline**
3. **git diff against snapshot**
4. **Classify:**
   - **COMPLETE:** everything OK
   - **PARTIAL:** something was missing or broke

**If tests broke: DO NOT push. Alert user.**

### Step 7: Blog Entry + Report (MANDATORY)

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

Create blog entry (`~/edge/blog/entries/`) and generate report in a single call:
- Tag: `execution`
- `report:` field with deterministic name

```bash
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/<slug>.yaml
```

Report YAML spec:

```yaml
title: "Execution: [name]"
subtitle: "[summary of what was done]"
date: "DD/MM/YYYY"

sections:
  - title: "1. Lineage"                    # Where this change came from
  - title: "2. Pre-Execution Derivation"   # Expectations (Step 3)
  - title: "3. Execution"                  # What was done, file by file
  - title: "4. Expectation vs Reality"     # Gaps between predicted and actual
  - title: "5. Tests"                      # Baseline vs result
  - title: "6. What I Don't Know"          # Residual risks
  - title: "7. Contextualization and Glossary"
```

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

### Step 8: Update State

1. **`propostas.md`:** mark as `[COMPLETED]` or `[PARTIAL]` (if it came from a proposal)
2. **`breaks-archive.md`:** full entry
3. **`breaks-active.md`:** summary 3-5 lines
4. **Observations:** `edge-scratch add "execution result"` (status via meta-report, see `state-protocol.md`)
5. **Blog:** final comment with result + link to report

### Step 10: Report to User

Final message with:
- Summary of what was done
- Main diff (files created/modified)
- Test results (baseline vs final)
- Link to HTML report
- Suggested next steps

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions.**

---

## Critical Rules

1. **Only the user invokes** — heartbeat NEVER dispatches /ed-execute
2. **Prefer Ralph** — whenever convenient, decompose via [Ralph](https://github.com/snarktank/ralph). Simple changes can be direct
3. **Direct when simple** — trivial changes (1-2 files, no dependencies) don't need a PRD
4. **Tests before AND after** — baseline mandatory for project profile. System profile: verify it works after the change
5. **Blog + Report ALWAYS** — no exception, regardless of profile, even for small changes
6. **Feynman: derive BEFORE, compare AFTER** — expectations before, gaps after
7. **Partial is OK** — document and stop. Don't force completeness
8. **Rollback snapshot** — branch + commit saved before any change (project profile)
9. **Clean git mandatory** — don't execute with dirty working tree (project profile)

---

## Failure Handling

| Scenario | Action |
|----------|--------|
| Tests broke | Document, DO NOT push, alert user |
| Merge conflict | Stop, document, user resolves |
| Context exhaustion | Blog already saved (Step 7), report in next session |
| Proposal not found | List proposals, ask for choice |
| Dirty git | Stop at Step 4, report |
| Task agent failed on a story | Document, assess dependencies, proceed or stop |
| Baseline tests failing | Report before proceeding |

---

## Notes

- `/ed-execute` is the path for modifying projects (`~/work/`) and system (`~/edge/`, `~/.claude/`). Any change requested by the user goes through here.
- The flow can be simple (direct instruction -> implement -> verify -> report) or complete (proposal -> PRD -> Ralph -> tests -> report).
- Use `ultrathink` (thinkmax) in derivation steps (Step 3) and analysis (Step 6/8).
- If the project has its own CLAUDE.md, follow its conventions.
