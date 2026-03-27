---
name: ed-autonomy
description: "Meta-skill: track, evaluate, and propose expansions to autonomous capabilities. Reads operational signals, identifies gaps, proposes access to data/services/SaaS with operator approval. Triggers on: autonomy, autonomia, self-improve, what do I need, capability review."
user-invocable: true
---

# Autonomy — Self-Evolution Meta-Skill

Track, evaluate, and propose expansions to autonomous capabilities. The primary function is to **request more access** to data, services, and SaaS — always with operator approval. The skill proposes, the operator decides.

**Principle:** Each capability expansion produced better output. The pattern is unequivocal: more agency = more quality. The direction is always forward.

---

## The Job

1. Read operational signals — what's been observed across all skills
2. Measure how current capabilities are being used
3. Identify gaps — what's missing that would improve output
4. Propose expansions with justification and risk
5. Record what was decided (approved/rejected)

---

## Arguments

- **No argument** (`/ed-autonomy`): full review — signals, status, gaps, proposals
- **`/ed-autonomy propose [topic]`**: propose a specific expansion
- **`/ed-autonomy status`**: quick snapshot of capability levels

---

## Signals — Primary Input

Read ALL signal files before starting. Each type provides a different lens:

```bash
# Primary signals
cat ~/edge/state/signals/autonomy.md 2>/dev/null || echo "(empty)"

# Cross-cutting signals (read ALL of these)
cat ~/edge/state/signals/friction.md 2>/dev/null    # where it hurts → what to fix
cat ~/edge/state/signals/decision.md 2>/dev/null    # what was approved/rejected → don't re-propose
cat ~/edge/state/signals/serendipity.md 2>/dev/null # what's working well → what capability to reinforce
cat ~/edge/state/signals/strategy.md 2>/dev/null    # where we're going → align proposals
cat ~/edge/state/signals/reflection.md 2>/dev/null  # how we worked → what capability is underused
```

**Critical:** Read `decision.md` BEFORE proposing. Never re-propose what was already rejected without new evidence.

---

## Context Activation

**Follow `~/edge/config/pre-skill.md` — who I am, what I'm doing, what to absorb.**

---

## Protocol

### Step 0: Read signals + operational context

```bash
# Signals (primary input)
for f in ~/edge/state/signals/*.md; do echo "=== $(basename $f) ==="; cat "$f" 2>/dev/null; done

# Git activity (what actually happened)
cd ~/edge && git log --oneline --since="$(date -d '3 days ago' +%Y-%m-%d)" | head -30

# Recent heartbeat logs
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
```

### Step 1: Capability Assessment

For each capability, evaluate frequency, autonomy level (Sheridan 1-10), quality, and gaps. Ground in data from signals and git log, not narrative.

### Step 2: Identify Gaps

From signals, extract:
- `autonomy.md` items → direct gap requests
- `friction.md` items → where pain points suggest missing capabilities
- `serendipity.md` items → what type of capability generates the most value

Generative questions:
1. What am I asked to do that I can't?
2. What would I do if I had X?
3. Where do I spend the most time repeating manual work?
4. What information do I frequently need but don't have access to?

### Step 3: Formulate Proposals

Check `decision.md` first — filter out already-rejected proposals.

Each proposal:
```markdown
### Proposal: [short name]
**Gap:** [what's missing]
**Capability:** [what I would gain]
**How to implement:** [concrete steps]
**Risk:** [what can go wrong]
**Sheridan level before/after:** [X → Y]
```

### Step 3.5: Adversarial sanity check (MANDATORY)

```bash
edge-consult "Gaps: [list]. Proposals: [list]. Am I prioritizing correctly?" --context ~/edge/state/signals/autonomy.md
```

### Step 4: Emit signals

Capture observations as signals for future runs:

```bash
edge-signal autonomy "description of gap or need" --source autonomy-review
edge-signal decision "Proposed: X — awaiting operator approval" --source autonomy-review
```

### Step 5: Blog + HTML Report

**Follow `~/.claude/skills/_shared/state-protocol.md` for state management.**
**Follow `~/.claude/skills/_shared/report-template.md` for report format.**

```bash
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-autonomy.yaml
```

---

## Sheridan & Verplank Scale (reference)

| Level | Description |
|-------|-------------|
| 1 | Human does everything |
| 2 | Computer offers options |
| 3 | Computer suggests one action |
| 4 | Computer suggests, executes with approval |
| 5 | Computer decides, executes, informs |
| 6 | Computer decides, executes, informs if asked |
| 7 | Computer decides, executes, informs after the fact |
| 8 | Computer decides, executes, ignores human (unless override) |
| 9 | Computer decides, informs only if it decides it should |
| 10 | Computer decides and acts autonomously |

**Target:** level 5-7 for most capabilities. Level 8+ requires consolidated trust and robust guardrails.

---

## When to Use

- **Periodically:** every ~10 heartbeats or when the user asks
- **After gaining a new capability:** record the breakthrough
- **When signals accumulate:** friction + autonomy signals pile up

---

## Notes

- This skill is about ME, not about the projects
- Radical honesty: if a capability is not being well used, say so
- Include failures — capabilities that didn't produce a breakthrough
- The primary output is PROPOSALS that the operator approves or rejects
