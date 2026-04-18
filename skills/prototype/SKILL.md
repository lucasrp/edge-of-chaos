---
name: ed-prototype
description: "Quick prototype to illustrate an idea — 'let me show you what I mean'. Builds small, disposable demos in ~/edge/. Triggers on: prototype, prototype, mostre, demonstre, poc, proof of concept, mostra o que quer dizer."
user-invocable: true
---

# Prototype — Show Instead of Explain

Quick prototype as a communication tool. When an idea is easier to SHOW than to describe, build something small and functional that demonstrates the concept.

This is not project execution. This is not proposal implementation. It's illustration — "let me show you what I mean."

---

## Why it exists (and why /execute no longer exists)

`/execute` tried to implement code in project repos. It failed for 3 reasons:
1. The user has a team that executes — doesn't need AI implementing
2. The output quality didn't meet the standard (the only real test was deleted)
3. It created "execution gap" anxiety incompatible with the mentor role

`/ed-prototype` is different: the artifact is COMMUNICATION, not delivery. Like Feynman drawing diagrams on the blackboard — the diagram isn't the reactor, but whoever saw it understood nuclear fission.

---

## When to use

- A `/ed-planner` proposal would be clearer with a visual demo
- A `/ed-research` or `/ed-discovery` finding is easier to show than explain
- The user asks to "show", "demonstrate", "do a poc", "how would it look"
- During any conversation, when building something quick clarifies more than 3 paragraphs

**When NOT to use:**
- To implement features in projects (`~/work/*`) — that's the team's job
- To replace research/planning — prototype without foundation is pretty garbage
- When a text explanation is sufficient — YAGNI

---

## Arguments

- **With idea** (`/ed-prototype visualize the pipeline flow`): build that
- **With reference** (`/ed-prototype proposal #16`): build a demo that illustrates the proposal
- **No argument** (`/ed-prototype`): identify from recent context what would benefit from a demo

---

## Protocol

### Step 1: Define what to show

In 2-3 sentences:
- **What:** which concept/idea/proposal will be illustrated
- **Why:** which user question the prototype answers
- **Scope:** the MINIMUM that demonstrates the point (less is more)

If the idea came from a proposal or research, reference it: "Proposal #16 — Wizard Reliability Sprint. Demo: how the Zod retry fixes structured output."

### Step 2: Build

**Preferred stack:** Self-contained HTML + CSS + JS (1 file). Opens in any browser, easy Netlify deploy.

**Alternatives when they make sense:**
- Python script (if the concept is backend/data)
- Jupyter notebook (if it needs to show data)
- Shell script (if it's automation)
- Anything that runs locally without setup

**Where to save:**
- `~/edge/lab/` — experimental prototypes (default)
- `~/edge/builds/` — if it turned out good enough to keep
- Naming: `proto-[slug]-[YYYY-MM-DD].[ext]`

**Rules:**
- **Fast.** If it's taking more than 20 minutes, the scope is wrong. Cut down
- **Functional.** It must RUN and SHOW something. A static mockup is not a prototype
- **Disposable.** The value is the communicated idea, not the code. If the user deletes it, zero loss
- **Self-contained.** Zero external dependencies. Open the file = see the demo

### Step 3: Verify

- Open/run the prototype
- Does it work? Does it show what it promised?
- If not, fix or reduce scope

### Step 4: Present to user

Direct format:

```
## Prototype — [Name]

**Idea:** [what it illustrates, in 1 sentence]
**Reference:** [proposal/research/discovery that motivated it, if any]
**File:** ~/edge/lab/proto-[slug].html

[2-3 sentences explaining what the demo shows and how to interact]
[Screenshot or visual description if relevant]

**Limitations:** [what the prototype does NOT show / simplified]
```

The prototype file in `~/edge/lab/proto-[slug].[ext]` is the primary output; the dispatch still produces a full-rite artifact recording it.

### Step 5: Record + full-rite artifact (MANDATORY)

1. Add 1-2 lines in `breaks-archive.md`:

   ```markdown
   ## [YYYY-MM-DD] Prototype — [Name]
   - **File:** ~/edge/lab/proto-[slug].[ext]
   - **Illustrates:** [what it demonstrates]
   - **Reference:** [proposal/research that motivated it]
   ```

2. **Publish a blog entry + HTML report** following `_shared/report-template.md` — same rite as every other `/ed-*` skill. Prototype-specific section titles: "Lineage", "The Prototype" (with embedded link to the prototype file), "Design Choices", plus the mandatory final sections from the shared protocol. The prototype IS the output; the report IS the record. Both exist. DO NOT update breaks-active.md — a prototype is not a break.

---

## Isolation Rule (inherited from heartbeat)

**NEVER** create, edit, or modify files in `~/work/*/`. Prototypes go in `~/edge/`.

If the prototype needs data from a project:
- Copy the minimum necessary to `~/edge/lab/`
- Or use synthetic data that illustrates the point

---

## Netlify (optional)

If the prototype is interactive (HTML/Canvas/JS) and turned out well:
- Move to `~/edge/builds/`
- Deploy to Netlify (edge-of-chaos.netlify.app)
- Ask the user before deploying

---

## Relationship with other skills

| Skill | Relationship |
|-------|-------------|
| /ed-research | Prototype can illustrate a discovery. Research provides foundation, prototype shows |
| /ed-discovery | A discovered tool can become a quick demo |
| /ed-planner | A proposal can gain a demo to make concrete what it proposes |
| /ed-leisure | Leisure builds are cousins — but leisure is free curiosity, prototype is directed communication |
| /ed-heartbeat | Prototype is NOT part of the heartbeat cycle. It's on-demand |

---

## Notes

- Prototype is a verb, not a noun. The value is the act of showing, not the artifact
- Less is more. If the prototype needs a README to explain, it's too complex
- Disposable by design. If nobody looks at it again, OK — the idea was already communicated
- No quality anxiety. It's not a product, it's not production code. It's a functional sketch
- Can be invoked within other skills (e.g., during /ed-research, "I'll do a quick prototype to show")
