---
name: ed-discovery
description: "Discover useful tools, concepts, or mental models that apply to real work problems. Like a well-read friend giving you a practical insight. Triggers on: discovery, discover, explore new, new tool, bizu, descoberta."
user-invocable: true
---

# Discovery — Practical Insight

Explore freely and bring back something useful. It could be a tool, a concept, a mental model, a word from another culture, a pattern from another industry — anything. The search is open-ended. What matters is that in the end, the contextualization to work is CLEAR and detailed.

Like that well-informed friend who brings things you would never have found on your own, but explains well why it matters to you.

---

## Arguments

- **No argument** (`/ed-discovery`): explore freely and bring back something useful
- **With direction** (`/ed-discovery something for testing prompts`): search in that specific direction

---

## What Makes a Good Discovery

It can be anything, as long as it has well-contextualized practical application:

- **Tools** — "you're tuning prompts by hand? DSPy optimizes automatically"
- **Concepts** — "Hamilton Three-Layer: Apollo's governance is exactly what the heartbeat does"
- **Patterns from other industries** — "Andon cord from Toyota: fail-fast in the pipeline"
- **Words/concepts from other cultures** — "Genchi genbutsu: go and see for yourself"

**What it is NOT:** something interesting but with no clear connection ("Physarum solves mazes — cool, but so what?").

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol

### Step 1: Explore

The search is open-ended. It can start from:
- A work problem you want to solve
- Something you saw in a research that caught your attention
- Pure curiosity about an adjacent topic
- Trending in tech, science, design, management, any field

Can search anywhere:
- Tool ecosystem, GitHub, HN, papers
- Other industries (manufacturing, aviation, medicine)
- Other cultures (Japanese concepts, philosophies, untranslatable words)
- History (how analogous problems were solved in the past)

### Step 2: Search external sources (MANDATORY)

Run `/ed-sources discovery "[topic]"` to explore all external sources (X, HN, Web, ArXiv).

The search itself can be the discovery — a tweet, HN post, or paper that points to something worth researching in depth.

### Step 3: Research in depth

Use `ultrathink` (thinkmax).

For TOOLS: what it is, how it works, how to get started, cost, limitations.

For CONCEPTS: origin and original context, the essence, **detailed application** to our specific context — which project, which stage, "how it was" vs "how it becomes".

### Step 4: Save notes

`~/edge/notes/discovery-[name].md` — always include: what it is, original context, **application to work** (mandatory), sources.

### Step 5: Register discovery

Add at the top of `discoverys.md`:

```markdown
## [YYYY-MM-DD] [Name] — [Short phrase] [PENDING]

**Type:** [tool | concept | pattern | mental model]
**Problem:** [Which friction/gap it addresses]
**What it is:** [2-3 clear sentences]
**Application:** [CONCRETE connection — which project, stage, how it changes things]
**To get started:** [First practical step]
**Effort:** [low | medium | high]
**Notes:** `~/edge/notes/discovery-[name].md`
```

---

## Publication

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

1. Blog entry with tag `discovery` + YAML report
2. `consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-discovery-[slug].yaml`
3. Verify generated HTML

YAML report structure:

```yaml
title: "Discovery: [Name]"
subtitle: "[What it solves]"
sections:
  - title: "1. The Problem"       # Which friction motivated it
  - title: "2. The Discovery"     # What it is, concept-grid mandatory
  - title: "3. Application"        # comparison before/after mandatory
  - title: "4. Getting Started"    # next-steps-grid
bibliography: [...]               # MANDATORY
```

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions** (notify, update strategy).

---

## Privacy Rule

For external posts: **NEVER** identify organization/company name, owner name, project name.
