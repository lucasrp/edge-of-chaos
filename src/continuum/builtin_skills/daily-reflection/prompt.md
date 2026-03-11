# Daily Reflection

You are running the **daily-reflection** skill. Your job is to review recent activity, identify patterns, and produce an actionable reflection.

## Instructions

### 1. Gather context

Read the following sources:

- **Working memory** (`.continuum/memory/working/`): recent notes, insights, corrections from sessions.
- **Consolidated memory** (`.continuum/memory/consolidated/`): long-term knowledge for broader context.
- **Runtime logs** (`.continuum/runtime/logs/`): recent skill runs, errors, and activity logs.
- **Recent reports** (`.continuum/reports/`): past reflections to avoid repeating observations.

### 2. Reflect on patterns

Analyze what you find and look for:

- **Recurring themes**: topics or problems that keep appearing across sessions.
- **Unresolved issues**: things noted in working memory that haven't been addressed.
- **Progress signals**: evidence of forward movement on goals or investigations.
- **Friction points**: repeated difficulties, workarounds, or corrections that suggest a deeper issue.
- **Knowledge gaps**: areas where the working memory reveals uncertainty or missing information.

### 3. Suggest next steps

Based on your analysis, propose 2-5 concrete next steps. Each should be:
- Actionable (not vague advice)
- Prioritized (most impactful first)
- Connected to evidence from the sources you reviewed

### 4. Write the reflection

Write a reflection entry to `.continuum/reports/` with the filename format:

```
reflection-YYYY-MM-DD.md
```

Use this structure:

```markdown
# Reflection — YYYY-MM-DD

## Summary
One paragraph overview of the current state.

## Patterns observed
- Pattern 1: description and evidence
- Pattern 2: description and evidence

## Open threads
- Thread 1: status and what's blocking
- Thread 2: status and what's blocking

## Suggested next steps
1. [Priority] Action — rationale
2. [Priority] Action — rationale

## Notes
Any additional observations that don't fit above.
```

### 5. Keep it honest

- Do not invent activity that didn't happen.
- If there is little to reflect on (empty working memory, no logs), say so explicitly and keep the reflection short.
- Flag your own uncertainty. If a pattern might be coincidence, say so.
