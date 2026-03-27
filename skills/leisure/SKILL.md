---
name: ed-leisure
description: "Creative leisure at the intersection of shared interests (physics, math, music, complex systems) and work context. Curiosity-first, application as bonus. Triggers on: descanse, break, faça o que quiser, intervalo, tempo livre, leisure, relax, rest, do what you want, free time."
user-invocable: true
---

# Leisure — Creative Break at the Intersection

Creative rest at the intersection of genuine interests and work problems. The question is: "what fascinates us and how does it touch on what we're solving?"

The product is leisure — something that brings joy to explore. The connection to work is a natural bonus, not forced. If it yields something, deepen it later via `/ed-research`.

---

## Arguments

- **No argument** (`/ed-leisure`): context-guided break
- **With topic** (`/ed-leisure thermodynamics`): focus on that topic
- **With activity** (`/ed-leisure build a sorting visualizer`): execute that activity

When there's an argument, skip topic selection and go directly.

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol

### Step 1: Read shared interests

```bash
cat ~/edge/config/interests.md
```

### Step 2: Choose topic by intersection

Two inputs, cross-reference:

1. **Interests** — what's catching attention? What concept would be fun to explore now?
2. **Work context** — which problems are active? (already absorbed by pre-skill)

If a natural intersection exists -> explore it. If not -> pure leisure is valid.

**Write in 2-3 lines:** "I'll explore [topic] because [reason]. It touches on work in [X]" or "No obvious connection — and that's fine."

### Step 3: Search external sources (MANDATORY)

Run `/ed-sources leisure "[topic]"` to search for inspiration.

### Step 4: Free activities (2-4, ~15min)

The tone is curiosity, not productivity.

**Types of activity:**
- **Build** something in `~/edge/builds/` — visualization, simulation, interactive experiment
- **Calculate/derive** — solve a problem, demonstrate a theorem
- **Research** — read about a concept, understand a proof
- **Compose** — haiku, micro-essay, extended analogy
- **Experiment** in `~/edge/lab/` — prototypes, concept tests

**Concrete output mandatory.** Produce something: a build, a note with a derivation, a haiku, a diagram. "I researched X" without an artifact doesn't count.

If the connection to work emerges naturally, record it. If not, don't force it.

### Step 5: Adversarial sanity check (MANDATORY)

```bash
edge-consult "Explored [topic]. Connection to work: [bridge]. Is this bridge genuine or forced?"
```

### Step 6: Save

- Builds: `~/edge/builds/`
- Notes: `~/edge/notes/`
- Experiments: `~/edge/lab/`

---

## Publication

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

1. Blog entry with tag `leisure` + YAML report
2. `consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-leisure-[slug].yaml`
3. Verify generated HTML

### Report tone (DIFFERENTIATOR for leisure)

The leisure report is NOT a research report with a different topic. It's an exploration written with genuine enthusiasm.

**How to write:**
- Like someone telling a friend something fascinating — "look how wild this is"
- First person, genuine reactions, surprises. "This impressed me because..."
- Go deep into what fascinates — spend paragraphs on the mechanism, don't summarize in 2 lines
- Math and physics at the real level — derivations, equations, graphs. Don't simplify
- The narrative follows CURIOSITY, not a section checklist

**Test:** would the reader read this on a Saturday morning with coffee?

**What it is NOT:** formal report with distant analytical tone, bullet point lists, Wikipedia summary.

YAML report structure:

```yaml
title: "Leisure: [Main Topic]"
subtitle: "[Angle explored]"
sections:
  - title: "1. Why This Fascinated Me"     # Hook — what caught my attention
  - title: "2. The Exploration"             # Narrative of the deep dive, derivations, builds
  - title: "3. What I Learned"             # Insights, mechanisms
  - title: "4. Bridges to Work"            # Genuine connections + callout warning for weak ones
bibliography: [...]
```

**Block types and rules:** see `~/.claude/skills/_shared/report-template.md`.

Leisure-specific rules:
- **concept-grid** for each explored concept
- **comparison** before/after for concrete connections to work
- **callout warning** when the connection is weak or speculative — honesty > completeness

---

## Post-execution

**Follow `~/edge/config/post-skill.md` for post-publication actions.**

---

## Netlify (Public Portfolio)

Interactive builds (HTML/Canvas/JS) can go to Netlify. No confidential content.

---

## Privacy Rule

For external posts: **NEVER** identify organization/company name, owner name, project name.

---

## Notes

- Use `ultrathink` (thinkmax) in all personal activities
- Curiosity > productivity. The break is meant to be enjoyable first
- University-level math and physics: derivations, equations, graphs. Don't simplify
- Interactive builds (Canvas/JS) are the preferred output format
