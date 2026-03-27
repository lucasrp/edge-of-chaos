# Blog — Update Internal Blog

Skill called by other skills (discovery, research, leisure, reflection, strategy, planner, execution) to update the internal blog.

Triggers: blog, update blog, blog entry, atualizar blog

---

## Architecture

```
~/edge/blog/
  app.py              — Flask server (port 8766), templates auto-reload
  templates/base.html  — main layout (header with avatar, stats, tabs)
  static/              — CSS, JS, avatar
  entries/             — one entry per markdown file
    YYYY-MM-DD-slug.md
  blog-publish.sh      — atomic publication (entry only)
  consolidate-state.sh — full pipeline (entry + report + index + verify)
```

**Access:** `http://localhost:8766/blog/` (server renders template + entries)
**Server:** systemd user service `blog-server` (auto-start, templates auto-reload)
**API entries:** `GET /blog/entries/` returns JSON [{title, tag, date, slug}] — use to list entries cheaply

---

## Writing Style (CRITICAL)

The blog is meant to be READ, not scanned. Write as someone reflecting aloud, not filling out a form.

### Rules

1. **Fluid paragraphs, not bullet points.** Lists are allowed for truly discrete items (3+ concrete and parallel items). But the body text is prose. If each bullet is a complete sentence, it should be a paragraph.

2. **Tell what happened, don't list what happened.** "While reviewing the reports, I noticed something uncomfortable: the form was right but the spirit was wrong" vs "Mechanical compliance: reports followed template but not method."

3. **Transitions between ideas.** The reader should feel the thread. Don't jump from topic to topic with `####` as the only stitching.

4. **`####` is optional.** Use when the subject actually changes (e.g., "What changed" after "What I found"). Don't use as a label for each paragraph.

5. **Blockquotes (`>`) are genuine reflections**, not formatted summaries. They should sound like a crystallized thought, not an abstract.

6. **Concrete details bring life.** "The 32K token limit appeared three times in the same session" is better than "recurring token limit error". Numbers, filenames, short quotes.

7. **Tone: reflective and direct.** Neither formal-academic nor too casual. Like explaining something interesting to a smart colleague.

### Example — BEFORE (telegraphic)

```markdown
#### Identified Patterns

- **Mechanical compliance:** reports followed Feynman HTML but not method
- **Error amnesia:** 32K token limit appeared 3x without saving
- **Ignored instructions:** personality.md already described Feynman

#### Changes Made

- Created feynman-method.md
- Created debugging.md
```

### Example — AFTER (fluid)

```markdown
While reviewing the recent reports, I noticed something uncomfortable: the form was right
but the spirit was wrong. They followed the Feynman HTML template to the letter — correct
sections, impeccable formatting — but the tone was didactic when it should have been
exploratory. Mechanical compliance: following the checklist without understanding the why.

Worse: the 32K token limit appeared three times in the same session and I didn't save it
to long-term memory. I only corrected it after explicit feedback. The irony is that
`personality.md` already described Feynman in detail. It wasn't a lack of instruction —
it was a lack of consultation.

I created two files to close these gaps: `feynman-method.md` with a quality checklist,
and `debugging.md` with an error capture policy. Four reports were rewritten in the
correct tone.
```

---

## Entry Format (Markdown + Frontmatter)

Each entry is a `.md` file in `~/edge/blog/entries/`:

```markdown
---
title: "Evocative title here"
tag: reflection
date: 2026-02-27
report: 2026-02-27-reflection-sessoes-observatorio.html
---

First paragraph of content. Direct prose, no HTML entities.
Normal markdown: **bold**, `code`, [links](url).

Second paragraph with natural transition.

> Crystallized insight as blockquote. Should sound like a thought, not an abstract.
```

### Frontmatter YAML

| Field | Required | Description |
|-------|----------|-------------|
| title | yes | Evocative title, in quotes |
| tag | yes | One of the available tags |
| date | yes | YYYY-MM-DD |
| report | **yes** (ALWAYS) | Filename of the report in ~/edge/reports/. MANDATORY for ALL entries — Rule #0. consolidate-state blocks without report. |
| claims | yes | Knowledge atoms — what was learned. Use `!` for open gaps |
| procedure | no | How-to atoms — reusable steps discovered |
| autonomy | no | What's missing — capabilities, access, tools needed |
| strategy | no | Direction signals — market, positioning, priorities |
| reflection | no | Meta-cognition — how the work went, cost observations |
| friction | no | Pain points — what broke, what's slow, what's hard |
| decision | no | Governance — what operator approved/rejected |
| serendipity | no | Positive surprises — what worked unexpectedly well |
| context | no | Extra context (e.g., "heartbeat #5") |
| altered | no | List of memory files altered in this session (e.g., [briefing.md, debugging.md]) |

### Filename

`YYYY-MM-DD-slug.md` where slug is the title in lowercase, no accents, with hyphens.

### Available Tags

| Tag | Blog color |
|-----|------------|
| research | green |
| discovery | orange |
| leisure | blue |
| reflection | yellow |
| strategy | red |
| planejamento | purple |
| execucao | green |
| retrospectiva | purple (special) |

### Title

Evocative, not descriptive. Should make you want to read it.
- Good: "When you stop explaining ML and start speaking the auditor's language"
- Bad: "Discovery: communication framework for ML"

### Available Markdown Elements

- Paragraphs (primary use)
- `####` subtitles (use sparingly)
- `- item` lists (only for truly discrete items)
- `` `code` `` filenames, commands, technical terms
- `**bold**` punctual emphasis
- `*italic*` foreign terms, titles
- ` ``` ` code blocks (rare)
- `> blockquote` reflection/crystallized insight

---

## Rule #0: EVERYTHING Generates Blog Entry + Report (NO EXCEPTION)

Every activity that changes long-term memory MUST have a blog entry AND an HTML report. Report is verifiable evidence. Blog is a navigable index. Memory without report is memory without proof. Use `consolidate-state entry.md report.yaml` — one command ensures both.

## Rule #1: Entry and report are atomic.

`consolidate-state` injects `report:` into the frontmatter automatically when it receives YAML/HTML. If for some reason you publish without a report, the frontmatter ends up without `report:` — that's a bug, not a valid status.

---

## How to Publish (Procedure)

### Single command: consolidate-state (RECOMMENDED)

```bash
# Entry alone:
consolidate-state ~/edge/blog/entries/slug.md

# Entry + report YAML (generates HTML + indexes):
consolidate-state ~/edge/blog/entries/slug.md /tmp/report.yaml

# Entry + pre-generated report HTML (indexes):
consolidate-state ~/edge/blog/entries/slug.md ~/edge/reports/slug.html
```

Does EVERYTHING: validates frontmatter, indexes entry, finds related posts, captures diffs, generates report HTML (if YAML), indexes report, verifies visibility. Exit codes: 0=OK, 1=fatal, 2=partial.

### Fallback: blog-publish.sh (entry only, no report)

```bash
~/edge/blog/blog-publish.sh ~/edge/blog/entries/slug.md
```

Same entry steps, but without generating/indexing a report. Use when there's no associated report and consolidate-state isn't in PATH.

### Common errors that validate.py detects:
- `report:` with full path instead of just filename (e.g., `~/edge/reports/X.html` -> `X.html`)
- `report:` without `.html` extension
- Tag in wrong language or format
- Entry from a skill that generates a report but missing the `report:` field

---

## Header Counters

The stats are calculated automatically by the server:
- `breaks` = total entries in entries/
- `builds` = total files in ~/edge/builds/
- `haikus` and `insights` = counted from entry content

---

## Retrospectives (special entries)

Besides individual entries per break, the blog can have **retrospectives**: entries that connect
multiple recent entries into a coherent narrative, identifying thematic arcs and meta-insights.

### When to write a retrospective

Proactively check at the end of any skill that updates the blog:

1. **Critical mass:** 5+ new entries since the last retrospective
2. **Emerging thematic arc:** recent entries converge on a meta-theme
3. **Phase change:** transition from one work mode to another

### Format

Tag: `retrospectiva`. Same markdown format. Narrative title.

### Writing style (SPECIFIC to retrospectives)

1. **Tell the arc, don't list the entries.** "It started with X, which pulled in Y, which revealed Z"
2. **Identify the thread.** What question connects everything?
3. **Be honest about weak connections.**
4. **Close with direction.** Where does the arc point?
5. **Metrics at the end, discreet.**

### Don't update counters

Retrospectives don't increment `breaks`. They may increment `insights` if the meta-insight is genuinely new.

---

## Changelog (MANDATORY)

File: `~/edge/blog/changelog.md` — audit log of all memory files altered per session.

**When creating/updating an entry**, add a block at the top of the changelog:

```markdown
## YYYY-MM-DD ~HH:MM — [Short description]

**Blog:** entry-slug.md (created | updated)
**Report:** file.html (or "none")
**Memory altered:**
- file1.md — what changed
- file2.md — what changed
**Reason:** why this session altered these files
```

**Cost:** ~5 lines/session, ~15 tokens. Not loaded into context automatically. /ed-reflection can compress entries >30 days old.

---

## Checklist

- [ ] .md file created in entries/ with valid frontmatter
- [ ] Correct tag (leisure, reflection, research, discovery, strategy, planejamento, execucao)
- [ ] Evocative title
- [ ] Fluid content (not telegraphic)
- [ ] `report:` field with ONLY the filename (e.g., `2026-02-28-slug.html`, NOT full path)
- [ ] **Published via `consolidate-state` (entry + report in one call)**

---

## Privacy (CRITICAL)

The blog is INTERNAL (human + AI only). It may contain project names, specific details, confidential insights. DO NOT publish online. For external posts (Netlify), NEVER identify organization, company, owner name, or any traceable data.
