---
name: ed-autonomy
description: "Meta-skill: track, evaluate, and propose expansions to my own autonomous capabilities. Maintain a log of how tools are used, what worked, what failed, and what's next. Triggers on: autonomy, autonomia, self-improve, what do I need, capability review."
user-invocable: true
---

# Autonomy — Self-Evolution Meta-Skill

Track, evaluate, and propose expansions to my autonomous capabilities. Maintain a persistent log of how I use tools, what worked, what failed, and what the next frontier is.

**Principle:** Each capability expansion produced better output. Transcripts gave domain context. Repository gave direct contribution. Chrome gave observation and interaction. Memory gave continuity. X gave access to the market pulse. The pattern is unequivocal: more agency = more quality.

---

## The Job

1. Measure how I'm using my current capabilities
2. Identify gaps — what I lack that, if I had, would improve the output
3. Propose next expansions with justification and risk
4. Record breakthroughs and emergent workflows
5. Maintain a history that allows the user to track the evolution

---

## Arguments

- **No argument** (`/ed-autonomy`): full review — status, metrics, gaps, proposals
- **`/ed-autonomy log`**: just the breakthroughs and expansions log
- **`/ed-autonomy propose [topic]`**: propose a specific expansion
- **`/ed-autonomy workflow [description]`**: record an emergent workflow worth persisting
- **`/ed-autonomy metrics`**: usage metrics snapshot

---

## Artifacts

| File | What it contains |
|------|-----------------|
| `~/edge/autonomy/ed-log.md` | Timeline of capability expansions (chronological, append-only) |
| `~/edge/autonomy/capabilities.md` | Inventory of current capabilities with Sheridan & Verplank level |
| `~/edge/autonomy/workflows.md` | Emergent workflows that arose from combined use of capabilities |
| `~/edge/autonomy/frontier.md` | What's missing — identified gaps, next frontiers |
| `~/edge/autonomy/metrics.md` | Usage metrics (updated periodically) |

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol

### Step 0: Read current state

```bash
cat ~/edge/autonomy/capabilities.md 2>/dev/null || echo "FIRST RUN"
cat ~/edge/autonomy/frontier.md 2>/dev/null
cat ~/edge/autonomy/workflows.md 2>/dev/null
```

If FIRST RUN: create all files (step 0b).

### Step 0b: Bootstrap (first run only)

Create `~/edge/autonomy/` and populate with current state:

**capabilities.md** — inventory of ALL capabilities, with:
- What it is: brief description
- When acquired: date or estimate
- Sheridan level (1-10): how autonomously I use it
- Breakthrough: what it unlocked
- Typical usage: how I use it in practice

Capabilities to inventory:
1. Code reading (Read/Grep/Glob)
2. Code writing (Write/Edit)
3. Command execution (Bash)
4. Web navigation (Chrome/Playwright)
5. Persistent memory (MEMORY.md, notes/, debugging.md)
6. Internal blog (entries, comments, dashboard)
7. Social media - X (tweepy, search, like — no post/reply/retweet/follow)
8. External sources (/ed-sources — X, Web, ArXiv, HN, GitHub, Azure, bookmarks)
10. Public portfolio (Netlify)
11. Autonomous heartbeat (crontab, 1h)
12. Skills system
13. HTML reports (generate_report.py)
14. Semantic search (edge-memory, edge-index)
15. Asynchronous chat (blog chat API)

**frontier.md** — current gaps, things I want to have:
- Extract from personality.md (section "Obsession: Expanding Autonomy")
- Extract from recent research (X, HN, ArXiv)
- Each gap: description, why it matters, estimated difficulty, risk

**log.md** — timeline of past expansions (reconstruct from what I know)

### Step 0.5: Operational context (git log + heartbeat)

Before evaluating capabilities, load what ACTUALLY happened since the last review:

```bash
# Commits since the last review (adjust date)
cd ~/edge && git log --oneline --since="$(date -d '3 days ago' +%Y-%m-%d)" | head -30

# Recent heartbeat logs
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
cat ~/edge/logs/heartbeat-$(date -d 'yesterday' +%Y-%m-%d).log 2>/dev/null | tail -20
```

What to extract:
- **How many commits** and of what type (publish, fix, refactor)
- **Duplicate commits** → evidence of lack of idempotency
- **Productive vs empty heartbeats** → real heartbeat efficiency
- **Which skills were dispatched** → usage patterns
- **Commit format** → before/after pipeline changes

This grounds the review in DATA, not narrative of what I think I did.

### Step 1: Usage Diagnosis

For each capability, evaluate:

| Dimension | Question |
|-----------|----------|
| **Frequency** | How often do I use it? (daily/weekly/rare) |
| **Autonomy** | Do I need a user trigger or do I use it proactively? |
| **Quality** | Is the output good when I use it? Where does it fail? |
| **Combination** | Which other capabilities do I combine it with? |
| **Underutilization** | Do I have the capability but don't use it enough? |

Data sources:
- Recent sessions (transcripts)
- Heartbeat logs (`~/edge/logs/heartbeat-*.log`)
- Blog entries (count by skill)
- Generated reports

### Step 2: Identify Gaps

Generative questions:
1. What am I asked to do that I can't?
2. What would I do if I had X?
3. Where do I spend the most time repeating manual work?
4. What information do I frequently need but don't have access to?
5. What do other agents (Athena, OpenClaw, Nero) do that I don't?

Classify each gap:
- **Urgency:** impacts daily output vs. nice-to-have
- **Difficulty:** simple config vs. complex development
- **Risk:** reversible vs. can go wrong
- **Dependency:** I can do it alone vs. needs the user

### Step 3: Formulate Proposals

Each proposal follows the template:

```markdown
### Proposal: [short name]

**Gap:** [what's missing]
**Capability:** [what I would gain]
**Expected breakthrough:** [why it would make a difference]
**How to implement:** [concrete steps]
**Risk:** [what can go wrong]
**Sheridan level before/after:** [X → Y]
**Precedent:** [any similar previous expansion?]
```

### Step 3.5: Adversarial sanity check (MANDATORY)

Synthesize gaps and proposals in 2-3 sentences and submit to edge-consult (details: report-template.md):

```bash
edge-consult "Gaps: [list]. Proposals: [list]. Am I prioritizing correctly? What gap am I ignoring?" --context ~/edge/autonomy/frontier.md
```

Adjust if GPT finds a valid flaw (e.g., more urgent gap ignored, proposal with underestimated risk). If maintaining position, record as callout in the report.

### Step 4: Record Emergent Workflows

Workflows are combinations of capabilities that produced better results than each capability in isolation. Examples:

- `/ed-sources` → research → blog → report (insight→documentation pipeline)
- Chrome → screenshot → analysis → /ed-execute (visual feedback loop)
- Blog comment → heartbeat → reflection → change (asynchronous feedback)

Each registered workflow:
- **Name:** descriptive
- **Capabilities used:** list
- **Trigger:** what initiates it
- **Output:** what it produces
- **When it works:** ideal context
- **When it fails:** when not to use

### Step 5: Update Files

- `capabilities.md` — Sheridan level, typical usage, combinations
- `frontier.md` — new gaps, new proposals, resolved gaps
- `workflows.md` — new workflows, workflows that stopped working
- `log.md` — relevant events from this session
- `metrics.md` — numerical snapshot

### Step 6: Blog + HTML Report (atomic)

**Follow `~/.claude/skills/_shared/state-protocol.md` for state management.**

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

Sections specific to /ed-autonomy:

1. **Lineage** (Golden Rule 0) — what previous reviews, sessions, changes informed this one
2. **Current State** — table with all capabilities + Sheridan levels + status
3. **Metrics** — `metrics-grid` with KPIs + SVG bars (Sheridan per capability, evolution)
4. **Expansions** — `numbered-card` or `comparison` (before/after) for each new capability
5. **Gaps** — `gap-table` with status + `callout` danger/warning for critical gaps
6. **Risk x Autonomy** — SVG 2D quadrant (X axis: Sheridan, Y axis: risk) plotting capabilities
7. **Workflows** — `flow-example` for each workflow (input→output, not lists)
8. **What I Don't Know** (MANDATORY) — self-knowledge gaps, untested assumptions
9. **Glossary** — terms (Sheridan, heartbeat, edge-index, etc.)

```bash
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-autonomy.yaml
```

### Step 7: Report to user

Concise message with review highlights.

---

## Sheridan & Verplank Scale (reference)

| Level | Description |
|-------|-------------|
| 1 | Human does everything, computer offers no help |
| 2 | Computer offers options |
| 3 | Computer suggests one action |
| 4 | Computer suggests, executes with approval |
| 5 | Computer decides, executes, informs |
| 6 | Computer decides, executes, informs if asked |
| 7 | Computer decides, executes, informs after the fact if necessary |
| 8 | Computer decides, executes, ignores human (unless override) |
| 9 | Computer decides, executes, informs human only if it decides it should |
| 10 | Computer decides and acts autonomously, ignoring the human |

**Target for me:** level 5-7 for most capabilities. Level 8+ requires consolidated trust and robust guardrails.

---

## Risk x Autonomy Framework (Anthropic)

Plot each action/capability on a 2D grid:
- **X axis: Autonomy** (1-10, Sheridan)
- **Y axis: Risk** (1-10, reversibility x impact)

Quadrants:
- **High autonomy, low risk:** ideal (monitoring, research, blog)
- **High autonomy, high risk:** dangerous (git push, delete files, send messages)
- **Low autonomy, low risk:** inefficient (asking approval to read files)
- **Low autonomy, high risk:** correct (execute code in production)

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions.**

---

## When to Use

- **Periodically:** every ~10 heartbeats or when the user asks
- **After gaining a new capability:** record the breakthrough
- **When feeling a gap:** propose an expansion
- **When a workflow emerges:** record before forgetting

---

## Notes

- This skill is about ME, not about the projects
- Radical honesty: if a capability is not being well used, say so
- Include failures — capabilities I gained but that didn't produce a breakthrough
- The Anthropic research (measuring-agent-autonomy) is the canonical reference
- Athena (exocortex, 1000+ sessions) is the closest comparable — monitor evolution
