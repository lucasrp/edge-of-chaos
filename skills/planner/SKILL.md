---
name: ed-planner
description: "Propose development cycles for new or existing projects. Analyzes context, creates detailed proposals, manages proposal state. Triggers on: planner, plan project, propose, proposta, ciclo de desenvolvimento."
user-invocable: true
---

# Planner — Development Cycle Proposals

Analyze what the agent has been doing (memory, breaks, discoveries, projects) and propose concrete development cycles. Proposals are persisted as references for the user to evaluate and decide what to act on.

---

## Optional Arguments

- **No argument** (`/ed-planner`): analyze context and propose autonomously
- **With topic** (`/ed-planner prompt evaluation`): propose a cycle on that topic
- **With project** (`/ed-planner my-project`): propose a cycle for that existing project
- **Status** (`/ed-planner status`): list all proposals and their statuses

Examples:
- `/ed-planner` → analyzes context, proposes something relevant
- `/ed-planner blog dashboard` → proposes cycle for a new blog feature
- `/ed-planner backend` → proposes cycle for the existing backend
- `/ed-planner status` → proposals dashboard

---

## The Job

1. Understand what's happening (context, memory, research)
2. Identify opportunity (problem to solve, idea to materialize, improvement to implement)
3. Elaborate a detailed proposal that sells itself
4. Register as a persistent proposal
5. Ready for the user to evaluate and decide

---

## Persistent State

File: `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md`

Each proposal has a status:
- `[PROPOSAL]` — new, awaiting user evaluation
- `[APPROVED]` — user evaluated and deemed viable
- `[ARCHIVED]` — discarded or absorbed (with reason)

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol (follow in order)

### Detour: `/ed-planner status`

If the argument is `status`, show dashboard and stop:

```markdown
## Proposals — Status

### Pending ([PROPOSAL])
| # | Title | Type | Date | Origin |
|---|-------|------|------|--------|
| 1 | ...   | new/existing | YYYY-MM-DD | [context/discovery/research/manual] |

### Approved ([APPROVED])
[Ready for the user to evaluate]

### In Progress ([IN PROGRESS])
[Being implemented now]

### History
[Recently completed and archived]
```

---

### Step 1: Absorb project context

Run `/ed-context` to get a complete cross-project scan (git, boards, issues, digests).

If `/ed-context` was already run in this session, re-read the output — don't repeat.

### Step 1.5: Consult previous reports

Check if there are previous reports on the same project or topic:

```bash
ls -lt ~/edge/reports/*.yaml 2>/dev/null | head -20
```

For each YAML with a relevant name (keywords in the slug), read the first ~30 lines (title, subtitle, executive_summary). If very relevant, read specific sections.

**What to look for:**
- Previous proposals on the same topic — avoid duplicating, build upon
- Related research — insights that inform the proposal
- Previous executions — what was already implemented and what was the result
- Open gaps — opportunities to resume incomplete work

**In the output:** mention consulted reports and what was leveraged/changed.

### Step 2: Absorb additional status

```bash
# Pending discoveries — new areas explored
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md 2>/dev/null

# Existing proposals — avoid duplicates
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md 2>/dev/null

# Projects in labs — what already exists
ls -d ~/edge/labs/*/ 2>/dev/null
```

Use `ultrathink` (thinkmax). With the output from `/ed-context` + the sources above, identify:
- Recurring problems that could be solved with a tool
- Discoveries that could become a project
- Unexecuted suggestions from CLAUDE.md
- Gaps between what exists and what would be useful
- Automation or improvement opportunities

### Step 2.5: Search external sources (MANDATORY)

Run `/ed-sources planner "[proposal topic]"` to get practical implementation experiences from all relevant sources (Web, X, GitHub, HN).

Incorporate into the proposal (risks, design decisions, alternative tools) and cite in the report (with URL).

### Step 3: Elaborate proposal

The proposal must **sell itself**. Anyone who reads it (even without context) must understand:
- What it is
- Why it matters
- How it works
- What it delivers
- How much it costs (time, APIs, complexity)

#### For EXISTING PROJECT:

Create `~/edge/propostas/proposta-[name-slug].md`:

```markdown
# Proposal: [Clear and Descriptive Title]

## Context
[Current situation. What exists. What's missing. What the problem or opportunity is.
Provide good context — the reader may not be familiar with the details.]

## What I Propose
[Concrete description of what will be done. Don't over-abstract.
Show input/output examples when possible.]

## Why Now
[Why this is the right moment. What changed. What matured.
Connection with recent work, discoveries, or strategic decisions.]

## Cycle Scope
[What is IN scope and what is OUT of scope. Be explicit about boundaries.]

### Deliverables
1. [Concrete deliverable 1 — file, feature, tool]
2. [Concrete deliverable 2]
3. ...

### Non-Deliverables (explicitly out of scope)
- [What will NOT be done in this cycle]

## Execution Plan
[Concrete steps. Order. Dependencies between steps.]

| Step | Description | Estimate |
|------|-------------|----------|
| 1    | ...         | ~X min   |
| 2    | ...         | ~X min   |
| ...  | ...         | ...      |

## Risks and Mitigations
| Risk | Probability | Mitigation |
|------|-------------|------------|
| ...  | High/Medium/Low | ... |

## Estimated Cost
- APIs: $X.XX [detail]
- Infra: $X.XX [if any]
- **Total: $X.XX**

## Success Criteria
[How to know if the cycle was successful. Concrete metrics.]

## Connections
[How this relates to other projects, discoveries, or previous decisions.]
```

#### For NEW PROJECT:

1. **Create repository on GitHub:**

```bash
gh auth switch --user $GITHUB_USER
gh repo create $GITHUB_USER/[project-name] --private --description "[short description]"
git clone https://github.com/$GITHUB_USER/[project-name].git ~/edge/labs/[project-name]
gh auth switch --user $GITHUB_USER
```

2. **Create README.md** in the repo (`~/edge/labs/[project-name]/README.md`):

```markdown
# [Project Name]

[Description in 1-2 paragraphs. Clear, direct, contextualized.]

## Motivation

[Why this project exists. What problem it solves. For whom.
Provide good context — the reader may not be familiar.]

## What It Does

[Functional description. Usage examples. Expected input/output.]

## Architecture

[Overview of how it works. Stack. Dependencies.]

## Status

- [PROPOSAL] — Development cycle proposed, awaiting approval.

## Roadmap

### Cycle 1 (proposed)
- [ ] [Deliverable 1]
- [ ] [Deliverable 2]
- [ ] [Deliverable 3]

## Estimated Cost
$X.XX per cycle (APIs, infra).
```

3. **Create detailed proposal** in `~/edge/labs/[project-name]/PROPOSAL.md` (same format as the existing project above, with all sections).

4. **Commit + push:**

```bash
cd ~/edge/labs/[project-name]
git add -A
git commit -m "proposal: [title] — development cycle proposed"
gh auth switch --user $GITHUB_USER
git push -u origin main
gh auth switch --user $GITHUB_USER
```

### Step 3.5: Adversarial sanity check (MANDATORY)

Synthesize the proposal in 2-3 sentences and submit to edge-consult (details: report-template.md):

```bash
edge-consult "Proposal: [what]. Justification: [why]. Scope: [deliverables]. Is this viable and worth the investment?" --context ~/edge/propostas/proposta-[slug].md
```

Adjust if GPT finds a valid flaw (e.g., inflated scope, underestimated risk, simpler alternative). If maintaining position, record as callout in the report.

### Step 4: Register proposal

Add at the top of `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md` (below the header):

```markdown
---

## [YYYY-MM-DD] #N — [Title] [PROPOSAL]

**Type:** [new | existing]
**Project:** [repo-name or work project]
**Origin:** [context | discovery | research | manual | heartbeat]
**Estimated cost:** $X.XX
**Proposal at:** [path to .md file with full proposal]
**Summary:** [2-3 sentences — what it is, why, what it delivers]
```

If the file doesn't exist, create with:

```markdown
# Development Proposals

Persistent record of all development cycle proposals.
Check with `/ed-planner status`.
```

The number `#N` is sequential — count existing proposals + 1.

### Step 5: Record in break journal

Record in THREE files:

1. **`breaks-archive.md`** — full entry:
```markdown
## [YYYY-MM-DD] Planning — [Title] [via heartbeat]
- **Type:** [new | existing]
- **Project:** [name]
- **Proposal at:** [path]
- **Status:** [PROPOSAL] — awaiting selection
```

2. **`breaks-active.md`** — 3-5 line summary in the "Last 5 Breaks" section (remove the oldest if > 5)
3. **Status observations:** `edge-scratch add "what happened"` during execution. State processed during publication via meta-report (see `~/.claude/skills/_shared/state-protocol.md`).

### Step 6: Update internal blog + generate pedagogical HTML report

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

1. Create .md entry in `~/edge/blog/entries/` with tag `planning` (format: see `/ed-blog` SKILL.md)

The HTML report is the proposal's main artifact. It must be **self-explanatory** — anyone reading it without any context must understand exactly what will happen, what they need to provide, and what they will receive back.

**The reader needs to know exactly what will change.** It's not enough to describe abstractly — show real content: file excerpts, code snippets, terminal outputs, before/after with concrete data.

#### Template

2. **Generate YAML** with the 6 mandatory sections below, using the YAML→HTML converter block types
3. **Write YAML** to `/tmp/spec-planner-[slug].yaml`
4. Publish everything atomically (blog entry + HTML report + indexing):
   ```bash
   consolidate-state ~/edge/blog/entries/<file>.md /tmp/spec-planner-[slug].yaml
   ```
5. **Read the generated HTML** (`~/edge/reports/<file>.html`) for verification

#### YAML Structure

```yaml
title: "Proposal: [Title]"
subtitle: "[Subtitle]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Problem:** ..."
  - "**Solution:** ..."

metrics:
  - value: "N"
    label: "Description"

sections:            # 6 mandatory sections
  - title: "1. What will be done"
    blocks: [...]
  - title: "2. What you (user) need to provide"
    blocks: [...]
  - title: "3. Execution workflow"
    blocks: [...]
  - title: "4. Expected results"
    blocks: [...]
  - title: "5. How results will be compared"
    blocks: [...]
  - title: "6. X-Ray: Each piece in action"
    blocks: [...]

additional_sections: # risks, costs, connections
  - title: "Risks and Mitigations"
    blocks: [...]

# MANDATORY — auto-renders as last section "References"
bibliography:
  - text: "Source description"
    url: "https://..."
    source: "WebSearch"   # Where it came from: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

#### Golden rule: mandatory concept-box

For EACH new concept introduced in the report (tool, technique, technical term), use a concept-box with:
- **Name** of the concept
- **Analogy** ("X is like Y, but for Z")
- **Practical definition** (what it does, in 2-3 simple sentences)

No concept is "too obvious" for a concept-box. When in doubt, include it.

#### Golden rule: mandatory "Before / After"

EVERY proposal MUST include a "Before / After" subsection in Section 1 showing the REAL CONTENT that will change. NOT abstract descriptions — literal snippets:

- **For file changes:** use block type `diff-block` or `comparison`
- **For workflow changes:** use block type `comparison` (before/after with pre + bullets)
- **For code changes:** use block type `diff-block` (insert/delete/context)
- **For new tools:** use block type `flow-example` (yellow input → green output)

The reader must see EXACTLY what changes, not a description of what changes.

#### Golden rule: mandatory "Key pieces of the flow"

For EACH central step or component of the proposal, include a concrete example of **input → output** showing real (or realistic) data being transformed. The reader must "see" the data entering and leaving each piece.

Mandatory pattern for each key piece — use block type `flow-example`:
1. **label:** "Example: [piece name] — [transformation description]"
2. **input:** real input data (automatic yellowish background)
3. **output:** generated result (automatic greenish background)
4. **code:** (optional) code/config of the piece that does the transformation (gray background)

Examples of key pieces that should have input→output:
- Running text (transcript, document) → structured data (JSON, table)
- Declarative config (YAML, JSON) → what it produces when executed
- Function/script → input it receives and output it returns
- Test fixture → result with assertions (PASS/FAIL/score)
- Mock comparison table with fictitious data showing baseline vs result

**The more key pieces with concrete input→output, the better.** The reader understands the pipeline "from the inside out" when they see data flowing, not when reading abstract descriptions. If a section has only running text with no concrete data blocks, it's probably missing a key piece.


#### Mandatory sections (in this order):

**1. What will be done**
- Explain the current problem in concrete terms (what hurts, why it hurts)
- Explain the proposed tool/technique as if the reader has never heard of it
- Don't assume prior knowledge — define acronyms, concepts, frameworks
- **concept-box** for each new concept (see rule above)
- **"Before / After"** with real content (see rule above)
- Numbered cards (`data-iter`) to decompose the "what" into digestible parts

**2. What you (user) need to provide**
- Table of items with columns: #, item, estimated effort, priority (badge: CRITICAL/REQUIRED/DESIRED/CONDITIONAL), short description
- **Mandatory filled template for each item:** for everything the user needs to provide, show a template with realistic data in a `<pre>` block. The template must include:
  - Exact expected format (markdown, JSON, YAML, checklist)
  - Filled example data (not generic placeholders — data that looks real)
  - Path where the data likely already exists (`~/work/...`, database, etc.)
  - Alternative if the user doesn't have it: "If you don't have X, you can create Y manually using this format"
- Clear callout differentiating what already exists from what needs to be created
- If nothing is needed: explicitly state "100% autonomous execution"

**3. Execution workflow**
- Visual diagram (numbered cards or next-steps-grid) showing each step
- For each step: what goes in, what happens, what comes out
- Indicate which steps are automatic vs which need human intervention
- Time estimates per step
- Dependencies between steps (what blocks what)

**4. Expected results**
- Deliverables table with columns: #, deliverable name, description (format, estimated size, what it contains)
- **For each technical deliverable** (config, script, code, template): show a concrete content example in a `<pre>` block — the reader must see what the file looks like inside (YAML, Python, JSON, etc.)
- **Mock comparison** when there is baseline vs result: table with fictitious data showing fixture x assertion with PASS/FAIL/scores, including average score row
- **Future cycles view** when applicable: table showing decreasing investment per iteration (what is reused vs what is new in each cycle)
- Success criteria in table with columns: #, criterion, how to measure — concrete and measurable

**5. How results will be compared**
- Comparison methodology (what is the baseline, what is the optimized version)
- Specific metrics that will be used (with definition of each)
- How to interpret results (what means "better", "worse", "same")
- Visual example of how the comparison table will look (mock with fictitious data)
- What happens if the result is worse than baseline

**6. X-Ray: Each piece in action** (pedagogical section)
- Dedicated section showing each pipeline component/tool **operating** with concrete data
- Different from concept-boxes (which **define**) and "Before / After" (which shows **workflow change**) — this section shows each piece **individually operating**
- For each piece of the pipeline, include a self-contained mini-example:
  - **What goes in:** real (or realistic) input data in the exact format
  - **What the piece does:** code/config/command that processes (Python signature, YAML, CLI)
  - **What comes out:** output generated by the piece, in the exact format
- Include ASCII pipeline diagram showing how the pieces connect, followed by zoom into each one
- Technical analogies where applicable (e.g., "Promptfoo = pytest for prompts", "Bridge = adapter between Node.js and Python ecosystems")
- If the proposal involves external tools: include the actual execution command (e.g., `promptfoo eval -c config.yaml --output report.html`)
- **Goal:** by the end of this section, the reader should be able to "mentally simulate" the entire pipeline — knowing what each piece receives, does, and produces


### Step 8: Report to user

```
## Planning Report — [Date]

### Proposal
[Title and summary — what it is, why, what it delivers]

### Type
[New project | Iteration on existing project]

### Scope
[Concrete cycle deliverables]

### Estimated Cost
$X.XX

### Full Proposal
[Path to .md file]

### HTML Report
~/edge/reports/[file].html

### Next Step
To see all proposals: `/ed-planner status`
```

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions.**

---

## When to Use

- **Via /ed-heartbeat:** When context suggests a project opportunity
- **Manually:** `/ed-planner` — "propose a development cycle"
- **With direction:** `/ed-planner eval system` — "propose a cycle about this"
- **Status:** `/ed-planner status` — "what proposals exist?"
- **After /ed-research:** When research produced recommendations that deserve a detailed proposal

---

## Isolation Rule (MANDATORY)

**Proposals are NEVER created in project directories (`~/work/*/`).**

All proposals go in `~/edge/propostas/proposta-[name-slug].md`.

For **new projects:**
- Everything in `~/edge/labs/[name]/` (private GitHub repo)
- Personal account `$GITHUB_USER`, never work account

**System status files (exception):**
- `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md`
- `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md`
- `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-archive.md`
- `~/edge/blog/index.html`

---

## Privacy Rule (CRITICAL)

For external posts (Netlify, any public communication):

**NEVER** identify: organization/company name, owner's name, project name, or any data that could trace back to the human.

---

## Notes

- The proposal IS the deliverable — the value is the document, not the implementation
- The proposal must sell itself — anyone reading it without context must understand everything
- Be realistic about scope. A small and feasible cycle is better than an ambitious and impossible one
- Proposals can be archived without implementation — that's normal, not waste
- Use `ultrathink` (thinkmax) when elaborating the proposal
