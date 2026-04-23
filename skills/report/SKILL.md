---
name: ed-report
description: "Generate a structured HTML report on any topic. Use when you need to deeply understand something, analyze a question, or produce a deliverable for the user. Dual-purpose: user invokes for deliverables, edge_of_chaos self-invokes to think through problems. Triggers on: report, gerar report, analise, analyze, explique em detalhe, explain in detail."
user-invocable: true
---

# /ed-report — Thinking by Producing

Generate a structured HTML report on any topic. A tool for both thinking AND communication.

## When to Use

**The user asks:**
- "make a report about X"
- "analyze this in detail"
- "I want to understand Y better"

**edge_of_chaos decides:**
- I need to understand something before acting — the report forces structured thinking
- A complex topic needs to be decomposed — the section format demands clarity
- I want to record reasoning that may be useful later — the HTML persists

**Rule:** if the thinking is complex enough to need more than 3 paragraphs, it deserves a report. The act of structuring into sections, tables, and comparisons FORCES understanding that running text does not.

---

## Context Activation

**Use the runtime pre-skill context injected by `edge-preflight` and sourced from `~/edge/config/preflight.yaml`.**

---

## Protocol

### Step 1: Define scope

Before researching or writing, answer in 1-2 sentences:
- **What do I want to understand?** (central question)
- **For what?** (decision to make, context to build, curiosity to satisfy)
- **What's the minimum the report needs to be useful?**

If invoked by the user with a specific topic, the scope comes from the request.
If self-invoked, make the trigger explicit ("I'm generating this report because...").

### Step 2: Research

Use the available tools depending on the topic:

- **WebSearch / WebFetch** — state of the art, tools, papers, docs
- **Read local files** — projects, previous notes, transcripts
- **Read previous reports** — avoid redoing work:
  ```bash
  ls -lt ~/edge/reports/*.html | head -10
  ```
- **Grep in notes** — connect with past research:
  ```bash
  grep -rl "TERM" ~/edge/notes/*.md | head -5
  ```

**Feynman Method:** derive from first principles before pasting conclusions from others. Show the thinking process, not just the conclusion. If a gap is found in reasoning, mark it explicitly.

### Step 2.5: Search external sources (MANDATORY)

Run `/ed-sources report "[central topic]"` for comprehensive search across ALL external sources (X, Web, ArXiv, HN, GitHub).

Incorporate into the analysis and cite in the report (with @username and URL for tweets, links for papers/posts).

### Step 3: Structure in YAML

Build the YAML spec with sections and block types. The format is the same as `/report`.

```yaml
title: "Report Title"
subtitle: "Contextual subtitle"
date: "DD/MM/YYYY"

executive_summary:
  - "Point 1"
  - "Point 2"

metrics:
  - value: "N"
    label: "Label"

sections:
  - title: "1. Section"
    blocks:
      - type: paragraph
        text: "..."

# MANDATORY — auto-renders as last section "References"
bibliography:
  - text: "Author (2024). Paper title"
    url: "https://arxiv.org/abs/..."
    source: "ArXiv"
  - text: "@username — Tweet about the topic"
    url: "https://x.com/username/status/..."
    source: "X"
  - text: "Post or doc title"
    url: "https://example.com/..."
    source: "WebSearch"
```

**Bibliography is MANDATORY in every report.** The root-level `bibliography:` field in the YAML auto-renders as a last section "References" with:
- Numbering `[1]`, `[2]`, ...
- Clickable URL
- Badge indicating the source that found the reference (ArXiv, X, WebSearch, GitHub, HN, Docs, etc.)

This allows the reader to evaluate WHICH sources are most useful and click to see the original.

Accepted formats:
- **Structured:** `{text, url, source}` — always prefer
- **Simple string:** `"Author (2024). Title. URL"` — quick fallback

`source` reflects WHERE the information came from (which tool/source found it), not the content type. E.g., a paper found via WebSearch has `source: "WebSearch"`, not `source: "Paper"`.

**Choosing block types by content:**

| I need to show... | Block type |
|---------------------|-----------|
| Running text, reasoning | `paragraph` |
| Before vs after, option A vs B | `comparison` |
| Tabular data, patterns | `table` |
| KPIs, key numbers | `metrics-grid` |
| Important highlight | `callout` (info/success/warning/danger) |
| Concepts side by side | `concept-grid` |
| Input → output (examples) | `flow-example` |
| Code, config | `code-block` |
| Proposed changes | `diff-block` |
| Next steps | `next-steps-grid` |
| Sequential items | `numbered-card` |
| Simple list | `list` |
| Sources and references | `bibliography` |

`text` fields support: `**bold**`, `*italic*`, `` `code` ``, `--` (mdash), `->` (rarr).

### Step 3.5: Adversarial sanity check (MANDATORY)

Synthesize the report's conclusions in 2-3 sentences and submit to edge-consult (details: report-template.md):

```bash
edge-consult "Analysis: [conclusions]. Where is this reasoning weakest?" --context /tmp/spec-[slug].yaml
```

Adjust if GPT finds a valid flaw. If position holds, record as callout in the report.

### Step 4: Record in blog and memory (BEFORE the HTML — MANDATORY)

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

**Blog BEFORE HTML. ALWAYS.** The HTML is the most expensive step in tokens. If context runs out during HTML generation, the blog has already been written. The report filename is deterministic (`YYYY-MM-DD-slug.html`) — it can be referenced before it exists.

**4a. Internal blog:**
1. Create .md entry with tag `report` (or from the calling skill). Format: see `/ed-blog` SKILL.md
2. Publication will happen in Step 5 together with the report (via `consolidate-state`)

**4b. Status observations:** `edge-scratch add "Report [topic]: [main conclusion]. [next step]."` (status via meta-report, see `~/.claude/skills/_shared/state-protocol.md`).

**4c. Discoveries** — if the report revealed something new (tool, pattern, bug, insight):
- Note in `~/edge/notes/` if it deserves its own note
- Or add as entry in `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md` with `[PENDING]`
- `/ed-reflection` will process it in the next execution

If self-invoked, explain to the user what was generated and why:
> "I generated a report on X because I needed to understand Y before Z. It's at ~/edge/reports/..."

### Step 5: Publish blog entry + generate HTML + index (atomic)

```bash
consolidate-state ~/edge/blog/entries/<file>.md /tmp/spec-[slug].yaml
```

`consolidate-state` does everything: publishes the blog entry, generates the HTML report in `~/edge/reports/`, and indexes in edge-memory.

If notes were created in ~/edge/notes/, index separately:
```bash
edge-index ~/edge/notes/[note].md
```

### Step 6: Verify

**6a. Validate SVGs** (zero context cost):
```bash
validate-svg ~/edge/reports/[created-report].html
```
If any SVG failed, fix in the YAML and regenerate.

**6b. Review YAML** (automatically saved alongside the HTML). Confirm that:
- Executive summary captures the essence
- Sections have logical flow
- Tables and comparisons communicate more than text would
- Knowledge gaps are marked (honesty > completeness)

---

## Writing Style

Same as the blog: reflective and direct. Neither formal-academic nor too-casual.

Additions specific to reports:
- **Sections tell a story.** Order matters: context → problem → analysis → synthesis → next step
- **Tables > text** when there are 3+ items with comparable attributes
- **Comparisons > paragraphs** when there are options with tradeoffs
- **Callouts for insights** the reader should not miss
- **Honesty about gaps:** "I didn't investigate X" is better than silence or bullshit

---

## Inline SVG Visualizations (MANDATORY when applicable)

Inline SVG is the visual language of reports. Generate via `raw-html` block in the YAML. It's not just for numbers — any information that communicates better as an image than as text deserves SVG.

**Decision rule:** if the reader would need to draw on paper to understand, the report should have SVG.

### When to generate SVG

| Situation | SVG Type | Example |
|-----------|----------|---------|
| Comparison of 3+ values | Horizontal/vertical bars | Costs, durations, counts |
| Statistical distribution | Box plot (whiskers + median) | Response times, scores |
| Trend over time | Grouped bars by period | Metrics evolution |
| Proportion/composition | 100% stacked bars | Distribution by category |
| Relationships between components | Boxes + arrows diagram | Architecture, pipeline, data flow |
| Process with decisions | Flowchart (boxes + diamonds) | Workflow, decision tree |
| Temporal sequence | Horizontal timeline | History, roadmap, evolution |
| 2D positioning | Quadrant/matrix | Urgency x impact, effort x value |
| Hierarchy/taxonomy | Tree diagram | Project structure, dependencies |
| State/progress | Progress bars, gauges | Completeness, health, coverage |
| Cycle/loop | Circular diagram | Feedback loops, iterative cycles |

### Technical standard

- Fixed `viewBox`: `700 280` for charts, `700 400` for diagrams, `700 200` for timelines
- `font-family: 'Segoe UI', sans-serif`
- `max-width: 100%` on the container
- Semantic colors:
  - `#2b6cb0` normal/info (primary blue)
  - `#38a169` success/positive
  - `#e53e3e` danger/critical
  - `#ed8936` alert/attention
  - `#805ad5` highlight/special
  - `#718096` neutral/secondary
- Inline legend (inside the SVG, not separate)
- Text: minimum 12px, adequate contrast
- `<title>` on main elements for accessibility

### Rules

1. **Numeric data: SVG + table = mandatory pair.** The chart is the visualization; the table is the exact reference
2. **Relationship/flow diagrams do not need a table** — they are self-explanatory
3. **Simplicity > decoration.** Horizontal bar works? Don't use 3D. Straight arrow works? Don't use curves
4. **Prefer SVG over text** when 3+ elements have spatial relationships (above/below, before/after, contains/contained, depends/blocks)
5. **Minimum 1 SVG per report.** If there's no data or relationships to visualize, the report is probably too short to be a report

---

## Format Rules

- No internal anchor links (`<a href="#...">` causes blank screen in SharePoint)
- External links ALLOWED and ENCOURAGED (`<a href="https://...">`) — tweets, papers, docs, sources. The reader wants to click and see the original
- 100% self-contained (inline SVG, inline CSS) — single file, no external dependencies
- No emojis (unless the user asks)

---

## Post-execution

**Use the runtime post-skill protocol sourced from `~/edge/config/postflight.yaml` and executed by `edge-postflight`.**

---

## Privacy

Reports live in `~/edge/reports/` — CONFIDENTIAL, human + AI only.
May contain project names, specific details, work insights.
For public content (Netlify), sanitize BEFORE publishing.
