---
name: ed-loader
description: "Manual session resume snapshot from persisted memory. Use only when the user explicitly asks to load, wake up, resume, boot, acorda, or show what is active now."
user-invocable: true
---

# Loader

Use this skill when the operator wants a short, interactive resume of persisted state.

Loader is read-side only. It does not dispatch work, make decisions, write memory, or produce a report. Its output is a compact answer that lets the conversation continue from the best reconstructed current state.

## Responsibility

Loader owns manual session orientation:

- regenerate and read the compiled briefing;
- inspect pending async inbox items for `loader`;
- make the best available context sweep;
- surface active or overdue threads;
- summarize latest relevant outputs, operator direction, and active errors;
- state the most important immediate context in a few lines.

## Method

1. Regenerate the briefing:

```bash
edge-digest 2>/dev/null
```

2. Read the compiled briefing:

```bash
cat ~/edge/briefing.md
```

3. Read the loader inbox:

```bash
edge-skill-inbox read --skill loader 2>/dev/null
```

4. Make a context sweep in the best way available for the situation.

Use judgment. The sweep may include:

- `edge-search` over memory, topics, reports, notes, open gaps, and prior outputs;
- GitHub issues, PRs, boards, or project artifacts;
- local repository status and recent commits;
- recent session logs;
- databases or external sources when they materially improve orientation.

Spend the time needed to avoid missing important context. Prefer targeted queries derived from the briefing, inbox, current user request, and active threads; broaden the sweep when the state is ambiguous.

## Output

Default output:

```markdown
Loaded.

Active: <1-3 bullets about current active/overdue threads>
Direction: <operator direction or priority>
Pending: <pending inbox items or none>
Errors: <active errors or none>

<one short paragraph: what matters now>
```

Quiet output:

```markdown
Loaded: <active thread summary>. Pending: <count or none>.
```

Do not dump raw briefing or inbox content. Synthesize.

## Boundaries

- Do not modify state.
- Do not run heartbeat or dispatch another skill.
- Do not turn this into a status dashboard; use the status/read-model CLIs for factual inventory.
