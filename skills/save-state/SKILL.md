---
name: ed-save-state
description: "Save current session state to persistent memory. Checkpoint working context, pending decisions, and insights before ending a session or switching context. Triggers on: salvar status, save state, checkpoint, salvar, guardar status, salvar context, save context."
user-invocable: true
---

# Save State — Session Checkpoint

Write-side complement to `/ed-loader` (which is read-side). Saves the current session state to persistent memory, allowing the next session to resume where it left off.

**When to use:**
- Before ending a long session
- When the user asks to "remember where I stopped"
- Before switching context (e.g., from project A to project B)
- When there are pending decisions that should not be lost
- At the end of any significant work not yet committed via consolidate-state

**What it is NOT:**
- NOT `/ed-blog` (publish to internal blog)
- NOT `/ed-reflection` (deep self-review)
- NOT git commit (version control)
- It's a quick and lightweight checkpoint — 2-3 minutes maximum

---

## The Job

Capture and persist the current session state across 4 dimensions:
1. **What was being done** — task, project, context
2. **Decisions made** — what was decided and why
3. **Pending items** — what was left for later
4. **Insights** — what was learned (claim candidate)

---

## Protocol (follow in order)

### Step 1: Synthesize session state

Without reading additional files — use what's already in the conversation context. Mentally produce:

- **Project/area:** in which work area the session operated
- **Main task:** what the user asked or what the heartbeat dispatched
- **Status:** completed / partially completed / blocked / abandoned
- **Decisions:** any decision made (technical, architectural, priority)
- **Pending items:** what remains open, depends on a third party, or needs more work
- **Insights:** any learning worth preserving
- **Artifacts created:** new or significantly modified files

### Step 2: Update breaks-active.md

Add/update in the "Last 5 Breaks" section (or equivalent section):

```bash
# Read current state
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md | head -30
```

Entry format:
```markdown
- **[DATE] [TYPE] — [SUMMARY]**: [Status]. [Pending items if any].
```

### Step 3: Record observations in scratchpad

```bash
edge-scratch add "[summary of what happened in the session]"
```

If multiple points, record each one:
```bash
edge-scratch add "Decision: [what was decided]"
edge-scratch add "Pending: [what remains open]"
edge-scratch add "Insight: [what I learned]"
```

### Step 4: Update relevant threads (if applicable)

If the session advanced any investigation thread:

```bash
# Check existing threads
ls ~/edge/threads/
```

Update the thread file with:
- New `updated:` in the frontmatter
- Note about what progressed
- Adjust `resurface:` if necessary

### Step 5: Claims (if applicable)

If the session produced durable knowledge that deserves becoming a claim:

```bash
edge-claims add "Verified fact I learned in this session"
edge-claims add '!Gap I identified and still don't know'
```

### Step 6: Confirm to user

Output format:

```
## State Saved

**Session:** [date/time]
**Area:** [project/context]
**Status:** [completed/partial/blocked]

### What was done
- [item 1]
- [item 2]

### Decisions
- [decision 1 and rationale]

### Pending Items
- [pending item 1]

### To Resume
[Concrete instruction for what to do in the next /ed-loader]
```

---

## Rules

1. **Speed:** 2-3 minutes maximum. This is not deep reflection — it's a checkpoint.
2. **Don't duplicate:** If the session already published via consolidate-state, the state commit (Phase 5) already saved claims/threads. Don't duplicate.
3. **No overthinking:** If the session was short or trivial, record only in the scratchpad. Don't force insights where there are none.
4. **Always confirm:** Show the user what was saved. Transparency.
5. **Git:** Do NOT make automatic git commits. State is saved in memory files, not in VCS.
