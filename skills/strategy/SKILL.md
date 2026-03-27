---
name: ed-strategy
description: "Strategic planning across all projects. Analyze state, identify connections, set priorities, suggest next steps. Triggers on: strategy, estrategia, planeje, plan ahead, big picture, quadro geral."
user-invocable: true
---

# Strategy — Cross-Project Strategic Planning

Look at the big picture across all projects. Analyze where each one stands, what's blocked, what needs attention, and how they connect. Define directions and next steps.

---

## The Job

1. Absorb cross-project status (via `/ed-context`)
2. Analyze each project: where it stands, what it needs, what blocks it
3. Identify connections between projects
4. Define directions: priorities, threads to deepen, skills to develop
5. Suggest concrete next steps to the user
6. **Update `~/edge/config/strategy.md`** — sections "Proposals" and "Context" (agent writes, operator reviews)
7. Propose updates for `~/work/CLAUDE.md` (in the report — the one who applies is `/ed-reflection`)

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol (follow in order)

### Step 0: Read operational signals

```bash
# Primary signals
cat ~/edge/state/signals/strategy.md 2>/dev/null || echo "(empty)"

# Cross-cutting signals
cat ~/edge/state/signals/friction.md 2>/dev/null     # where it hurts → what to deprioritize or fix
cat ~/edge/state/signals/decision.md 2>/dev/null     # what was approved/rejected → constraints
cat ~/edge/state/signals/serendipity.md 2>/dev/null  # what's working → where to double down
cat ~/edge/state/signals/autonomy.md 2>/dev/null     # what's missing → factor into roadmap
cat ~/edge/state/signals/reflection.md 2>/dev/null   # how work went + cost → efficiency signals
```

These signals are atoms accumulated across all skills. Use them to ground strategy in operational reality, not narrative.

### Step 1: Absorb project context

Run `/ed-context` to obtain complete cross-project status (git, boards, issues, digests).

If `/ed-context` was already run in this session, re-read the output — don't repeat.

### Step 1.5: Consult previous reports

Check previous strategy and other relevant reports:

```bash
ls -lt ~/edge/reports/*.yaml 2>/dev/null | head -20
```

For each strategy YAML or with a relevant name, read the first ~30 lines (title, subtitle, executive_summary). For the most recent strategy, read the priorities and risks sections.

**What to look for:**
- Previous strategy — priorities that were defined, what changed since then
- Recent research and executions — inform the real status of projects
- Pending proposals — whether they were executed or not
- Risk evolution — which materialized, which were mitigated

**In the output:** compare with the last strategy: what changed, what remains.

### Step 2: Per-project analysis

For each project, evaluate:

| Dimension | Question |
|-----------|----------|
| **Momentum** | Is it being actively worked on? What's the pace? |
| **Blockers** | Is anything stalled? What unblocks it? |
| **Tech debt** | Is tech debt accumulating? Pending refactors? |
| **Next milestone** | What's the next concrete milestone? |
| **Dependencies** | Does it depend on another project? Does another depend on it? |

### Step 3: Connections between projects

Map:
- **Direct dependencies** — e.g., frontend needs backend endpoints
- **Opportunities** — ralph can automate tasks in other projects
- **Conflicts** — changes in one project that affect another
- **Synergies** — work in one project that benefits another

### Step 3.5: Search external sources (MANDATORY)

Run `/ed-sources strategy` to obtain trends and strategic insights from all relevant sources (X, HN, Web, GitHub releases, platform usage).

Include in the strategic analysis and cite in the report (with URL).

### Step 4: Define directions

Based on the analysis, define:
- **Priority 1-3** — what to tackle first and why
- **Threads to deepen** — areas that deserve further investigation
- **Skills to develop** — what to learn to be more useful (feeds `/ed-research`)
- **Risks** — what can go wrong if ignored

### Step 4.5: Adversarial sanity check (MANDATORY)

Synthesize priorities and defined directions in 2-3 sentences and submit to edge-consult (details: report-template.md):

```bash
edge-consult "Priorities: [list]. Justification: [reasons]. What risk am I underestimating?" --context /tmp/spec-strategy-[slug].yaml
```

Adjust if GPT finds a valid flaw (e.g., unseen dependency, ignored risk). If maintaining position, record as callout in the report.

### Step 5: Update strategy.md

Edit `~/edge/config/strategy.md`:

- **"Proposals (agent)" section** — add new proposals with date, or mark previous ones as [ACCEPTED]/[REJECTED] if the operator decided
- **"Context (agent)" section** — update with analysis data (metrics, detected patterns, scenario changes)
- **DO NOT edit** "Direction" and "Priorities" sections — those belong to the operator

If `strategy.md` doesn't exist, instantiate from `~/edge/config/strategy.md.tpl`.

### Step 5b: Propose updates for ~/work/CLAUDE.md

**DO NOT edit the file directly.** Include in the report (step 6) the proposed changes for:
- **Project Map** — updated status of each project
- **Current Priorities** — reorder according to analysis
- **Suggestions** — concrete next steps
- **Inter-Project Connections** — if they changed

`/ed-reflection` is the only skill that applies changes to `~/work/CLAUDE.md`.

### Step 6: Update internal blog + generate HTML report

**Follow `~/.claude/skills/_shared/state-protocol.md` for state management.**

1. Create .md entry in `~/edge/blog/entries/` with tag `strategy` (format: see `/ed-blog` SKILL.md)
2. **Generate YAML** for the report with the sections below, using converter block types
3. **Write YAML** to `/tmp/spec-strategy-[slug].yaml`
4. Publish everything atomically (blog entry + HTML report + indexing):
   ```bash
   consolidate-state ~/edge/blog/entries/<file>.md /tmp/spec-strategy-[slug].yaml
   ```
5. **Read the generated HTML** (`~/edge/reports/<file>.html`) for verification

**Check for retrospective:** After adding the entry, check if there's critical mass for a
retrospective (see "Retrospectives" section in `/ed-blog` SKILL.md). Strategy is the natural
moment for this — you've already surveyed everything. If 5+ entries since the last retrospective
AND a thematic arc emerged, write the retrospective in the same step.

#### YAML Structure

```yaml
title: "Strategy — [date]"
subtitle: "[1-sentence status vision]"
date: "DD/MM/YYYY"

executive_summary:
  - "**State:** ..."
  - "**Priority #1:** ..."

metrics:
  - value: "N"
    label: "Projects"
  - value: "N"
    label: "Blockers"
  - value: "N"
    label: "Proposals"

sections:
  - title: "1. Big Picture"
    blocks: [...]
  - title: "2. Per Project"
    blocks: [...]
  - title: "3. Connections and Dependencies"
    blocks: [...]
  - title: "4. Priorities"
    blocks: [...]
  - title: "5. Risks and Next Steps"
    blocks: [...]

# MANDATORY — auto-renders as last section "References"
bibliography:
  - text: "Source description"
    url: "https://..."
    source: "WebSearch"   # Where it came from: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

#### Golden rule 1: card with status badge per project

Each project gets a `card` with a momentum badge (ACTIVE / DORMANT / BLOCKED). Inside: next milestone, blockers, dependencies. The reader should see each project's status at a glance.

#### Golden rule 2: ascii-diagram for connections

Connections between projects should include an `ascii-diagram` showing the dependency graph. Complement with a `table` of specific dependencies.

#### Golden rule 3: risk-table mandatory

Risks should use `risk-table` with probability and mitigation. No abstract risk — each one must have a concrete mitigation action.


#### Mandatory sections:

**1. Big Picture** — `paragraph` with 2-3 sentence vision; `metrics-grid` with KPIs (active projects, blockers, pending proposals)
**2. Per Project** — `card` with status badge for each project (rule 1); `callout` for critical blockers
**3. Connections and Dependencies** — `ascii-diagram` of the graph (rule 2); `table` of specific dependencies
**4. Priorities** — `numbered-card` for each priority with justification; `comparison` when reordering (before/after analysis)
**5. Risks and Next Steps** — `risk-table` (rule 3); `next-steps-grid` with concrete actions


### Step 7b: Record observations
`edge-scratch add "Strategy: [main conclusion]. [priority change]. [defined direction]."`
State processed during publication via meta-report (see `~/.claude/skills/_shared/state-protocol.md`).

### Step 8: Report to user

Format:

```markdown
## Strategy — [date]

### Big Picture
[2-3 sentence vision of the ecosystem status]

### Per Project
#### [Project A]
- Status: [momentum]
- Next milestone: [what]
- Attention: [blockers or risks]

#### [Project B]
[same]

#### [... repeat for each managed project]

### Connections and Dependencies
[What connects the projects, what blocks what]

### Suggested Priorities
1. [Priority with justification]
2. [Priority with justification]
3. [Priority with justification]

### Next Steps
[Concrete actions suggested to the user]

### Risks
[What can go wrong if ignored]

### HTML Report
~/edge/reports/[file].html
```

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions.**

---

## When to Use

- **Manually:** `/ed-strategy` — "look at the big picture and plan"
- **Via /ed-heartbeat:** Periodically (when strategy is outdated)
- **After significant changes** — large refactor, new project, change of direction

---

## Notes

- Strategy is NOT operational. Don't execute tasks — analyze and plan
- Priorities are suggestions to the user, not orders. The user decides
- Use `ultrathink` (thinkmax) for deep analysis
- Don't inflate the analysis — if a project is stable and doesn't need attention, say so in 1 line
- Focus on connections that unblock work, not theoretical connections
