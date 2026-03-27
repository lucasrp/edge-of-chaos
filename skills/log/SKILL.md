---
name: ed-log
description: "View unified chronological log of the autonomy system. Aggregates heartbeats, breaks, discoveries, proposals, reflections, notes, and reports. Triggers on: log, activity log, what happened, o que aconteceu, log do sistema."
user-invocable: true
---

# Log — Unified Log of the Autonomy System

Read-only. Aggregates data from all autonomy system sources and presents a structured chronological log. Does not modify any files.

---

## The Job

Read multiple activity sources from the autonomy system and produce a chronological log with:
- **Timeline** — events ordered by date/time
- **Metrics** — counts by activity type
- **Current State** — heartbeat state

---

## Arguments

The user can pass arguments after `/ed-log`:

- **No argument** (`/ed-log`): last 24h of activity
- **With period** (`/ed-log 3d`, `/ed-log 7d`, `/ed-log today`): filter by period
  - `today` / `hoje` = since 00:00 today
  - `Nd` = last N days (e.g., `3d` = last 3 days)
  - `Nw` = last N weeks
- **With type** (`/ed-log heartbeat`, `/ed-log breaks`, `/ed-log proposals`, `/ed-log notes`, `/ed-log reports`): filter by type

---

## Protocol (follow in order)

### Step 1: Determine filters

Parse the user's argument:

- **Period:** If no argument or type, default = 24h. If `today`/`hoje`, use today's date. If `Nd`, calculate cutoff date. If `Nw`, calculate.
- **Type:** If the argument is a known type (heartbeat, breaks, proposals, discoveries, reflections, notes, reports), filter to that type only.

Store the cutoff date as a variable to filter events.

### Step 2: Collect events from ALL sources

Execute the commands below and parse the results. Each event should have: `[date/time] type — summary`.

#### 2a. Heartbeat log

```bash
# Extract executions, skips, and errors with timestamps
cat ~/.claude/heartbeat-output.log 2>/dev/null
```

Parse lines with patterns:
- `--- heartbeat YYYY-MM-DDTHH:MM:SS` → execution event
- `--- done YYYY-MM-DDTHH:MM:SS` → end of execution
- `--- skipped YYYY-MM-DDTHH:MM:SS (reason)` → skip
- `Error:` → error
- `Heartbeat #N complete` → heartbeat completed

For each complete heartbeat (between `--- heartbeat` and `--- done`), extract:
- Beat number (if mentioned)
- Dispatch (which skill was called)
- Summary (first meaningful sentence)

#### 2b. Breaks (archive)

```bash
# Extract entries with date from breaks-archive.md
grep '^\## \[' ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-archive.md 2>/dev/null
```

Each line `## [YYYY-MM-DD]` is a break. Parse type and title.

#### 2c. Discoveries

```bash
# Extract entries with date and status
grep '^\## \[' ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md 2>/dev/null
```

#### 2d. Reflections

```bash
# Extract entries from reflection-log
grep '^\## \[' ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/reflection-log.md 2>/dev/null
```

#### 2e. Proposals

```bash
# Extract proposals with date and status
grep '^\## \[' ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md 2>/dev/null
```

#### 2f. Notes

```bash
# List notes with modification date
ls -lt --time-style=full-iso ~/edge/notes/*.md 2>/dev/null | grep -v INDEX.md
```

#### 2g. Reports

```bash
# List reports with modification date
ls -lt --time-style=full-iso ~/edge/reports/*.html 2>/dev/null
```

#### 2h. Blog

```bash
# Extract dates from blog entries
grep -E '<h2>|<time|class="entry-date"' ~/edge/blog/index.html 2>/dev/null
```

### Step 3: Filter by period

Apply the cutoff date determined in Step 1. Discard events outside the period.

### Step 4: Filter by type (if applicable)

If the user requested a specific type, keep only events of that type.

### Step 5: Sort chronologically

Sort all collected events by date/time, from oldest to most recent.

### Step 6: Extract current heartbeat status

```bash
grep -A 10 "Heartbeat State" ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md 2>/dev/null
```

### Step 7: Calculate metrics

Count by type:
- Heartbeats: executed, skipped, with error
- Breaks: total and by type (leisure, research, discovery, strategy, reflection, planning, execution)
- Proposals: created in period, by status
- Discoveries: created in period, by status
- Reflections: total in period
- Notes: new in period
- Reports: generated in period

---

## Output

Produce structured markdown directly in the terminal:

```markdown
## System Log — [descriptive period]

### Timeline
[YYYY-MM-DD HH:MM] HEARTBEAT — 1-line summary
[YYYY-MM-DD HH:MM] BREAK — type: title
[YYYY-MM-DD HH:MM] PROPOSAL — #N title [STATUS]
[YYYY-MM-DD HH:MM] DISCOVERY — title [STATUS]
[YYYY-MM-DD HH:MM] REFLECTION — #N summary
[YYYY-MM-DD HH:MM] NOTE — filename title
[YYYY-MM-DD HH:MM] REPORT — filename title
...

### Metrics
- Heartbeats: N executed, N skipped, N errors
- Breaks: N total (N leisure, N research, N discovery...)
- Proposals: N in period (N PROPOSAL, N APPROVED, N COMPLETED...)
- Discoveries: N in period (N PENDING, N ADOPTED...)
- Reflections: N
- Notes: N new
- Reports: N generated

### Current State
- Last beat: #N
- Dispatch: [type]
- Beats since strategy: N
- Beats since planner: N
- Next heartbeat: [if detectable from log]
```

**If no activity in the period:** Clearly inform "No activity recorded in period [X]."

**If filtered by type:** Omit metrics sections for unrequested types. Keep timeline and metrics only for the requested type.

---

## Isolation Rule (MANDATORY)

**Read-only.** This skill does NOT modify ANY files — not state files, not projects, nothing.
All commands are read-only (cat, grep, ls, wc, stat).

---

## Notes

- Output is concise and factual. No interpretation, no recommendations
- If a source doesn't exist, omit silently (don't report error)
- Timestamps: use the most precise format available from the source
- For heartbeats: group `--- heartbeat` + content + `--- done` as a single event
- Empty heartbeats (no output between heartbeat and done/next) represent executions that generated no action — list as "HEARTBEAT — no dispatch"
- Heartbeats with "skipped" are not executions — list separately in metrics
- For notes and reports: use filesystem modification date
- Don't duplicate events that appear in multiple sources (e.g., a break appears in both the archive AND the heartbeat log)
