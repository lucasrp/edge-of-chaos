# Report Template — Shared Reference

Used by: /ed-research, /ed-discovery, /ed-leisure, /ed-strategy, /ed-planner, /ed-reflection.
Each skill defines its own mandatory sections and golden rules 1-3. This file defines what is COMMON to all.

---

## How to Generate

1. **Generate YAML** with the sections from the calling skill, using the block types below
2. **Write YAML** to `/tmp/spec-[skill]-[slug].yaml`
3. **Include claims in the blog entry frontmatter** (compaction — MANDATORY):
   ```yaml
   claims:
     - "Verified fact I learned"
     - "!Thing I still don't know — knowledge gap"
   threads: [related-thread-1, related-thread-2]
   ```
   - Claims = durable knowledge extracted from the entry. What survives without rereading the full text.
   - `!` prefix = "I don't know" — open gap, candidate for future research.
   - `threads:` = related investigation threads (see `~/edge/threads/`).
   - `consolidate-state` warns if claims are missing.
4. **Publish atomically** (blog entry + report HTML + meta-report + state commit):
   ```bash
   consolidate-state ~/edge/blog/entries/<file>.md /tmp/spec-[skill]-[slug].yaml
   ```
   `consolidate-state` handles everything in 7 phases:
   - Phase 0/0.5: Frontmatter + review gate
   - Phase 1: Blog entry (blog-publish.sh)
   - Phase 2: Content report (generate_report.py → ~/edge/reports/)
   - Phase 3/3.4: Verification + LLM cost
   - **Phase 4: Meta-report** (state delta + scratchpad + adversarial → ~/edge/meta-reports/)
   - Phase 5: State commit (claims, threads, events, digest)
   - Phase 6: Diffs + git commit

   Content report is optional — publishing without YAML generates only the meta-report:
   ```bash
   consolidate-state ~/edge/blog/entries/<file>.md
   ```

   Useful flags: `--scratchpad PATH`, `--no-adversarial`, `--no-meta`, `--skip-review`
5. **Read meta-report** (`~/edge/meta-reports/<slug>-meta.md`) BEFORE editing status
6. **Read the generated HTML** (`~/edge/reports/<file>.html`) for verification

---

## Base YAML

```yaml
title: "[Skill]: [Topic]"
subtitle: "[Descriptive subtitle]"
date: "DD/MM/YYYY"

executive_summary:
  - "**[Field 1]:** ..."
  - "**[Field 2]:** ..."

metrics:
  - value: "N"
    label: "Description"

sections:
  - title: "1. [Skill section]"
    blocks: [...]

# MANDATORY — auto-renders as the last section "References"
bibliography:
  - text: "Source description"
    url: "https://..."
    source: "ArXiv"   # ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

---

## Available Block Types

| Type | Usage | Main fields |
|------|-------|-------------|
| `paragraph` | Running text | text, style? |
| `subsection` | h3 sub-heading | title |
| `concept-grid` | Concept-boxes 2-col | items[{name, text}] |
| `callout` | Colored highlight | variant(info/success/warning/danger), text |
| `card` | Block with title | title?, badge?, badge_class?, text? |
| `numbered-card` | Numbered card | number, title, badge?, badge_class?, text, card_class? |
| `flow-example` | Input→Output | label, input, output, input_label?, output_label?, code? |
| `comparison` | Before/After 2-col | before{title,badge?,pre?,bullets?}, after{...} |
| `table` | Simple table | headers, rows, highlight_rows?, score_row? |
| `comparison-table` | Table with status | headers, rows[{cells,classes}], score_row?, note? |
| `risk-table` | Risks | rows[{risk,probability,mitigation}] |
| `code-block` | Code/config | label?, badge?, content |
| `ascii-diagram` | ASCII diagram | title?, content |
| `template-block` | Example template | title, description?, content, note? |
| `next-steps-grid` | Visual roadmap | steps[{number,title,description}] |
| `metrics-grid` | Inline KPIs | items[{value,label}] |
| `list` | ul/ol list | items, ordered? |
| `diff-block` | Before/after diff | header?, lines[{type(insert/delete/context),text}] |
| `raw-html` | HTML passthrough | content |
| `derivation` | Feynman: derivation | title?, text?, bullets?, code? |
| `gap-marker` | Feynman: individual gap | id?, text |
| `gap-table` | Feynman: gap table | gaps[{id, description, need, status}] |
| `gap-resolution` | Feynman: gap → answer | gap_id?, gap, text?, answer |
| `glossary` | Glossary + context | context?, terms[{term, definition}] |

`text` fields support `**bold**`, `*italic*`, `` `code` ``, `--` (mdash), `->` (rarr).

---

## Golden Rule 0: Mandatory Lineage (ALL skills)

The FIRST section of every report MUST include a block showing the chain of reasoning that led here. Use `table` with columns: **Previous Action** | **What It Brought** | **Connection to This Work**.

Include: previous reports, breaks, discoveries, proposals, research, executions, conversations with the user — any action that informed this work. Cite by name/number (e.g.: "Break #26 — tradecraft", "Research pipeline-minimo-viavel").

If there is no relevant prior work, state explicitly: "First work on this topic."

---

## Golden Rule 4: Inline SVG Visualizations (MANDATORY when applicable)

SVG is not just for numbers — any information that communicates better as an image deserves SVG. Rule: if the reader would need to draw on paper to understand, generate SVG.

**When to generate SVG:**
- Comparison of 3+ values: horizontal/vertical bars
- Statistical distribution: box plot (whiskers + median + mean)
- Trend over time: bars grouped by period
- Proportion/composition: 100% stacked bars
- Relationships between components: box + arrow diagram (architecture, pipeline, data flow)
- Process with decisions: flowchart (boxes + diamonds)
- Temporal sequence: horizontal timeline
- 2D positioning: quadrant/matrix (urgency x impact, effort x value)
- Hierarchy/taxonomy: tree diagram
- Cycle/loop: circular diagram (feedback loops, iterative cycles)

**SVG standard:** fixed viewBox (`700 280` charts, `700 400` diagrams), `font-family:'Segoe UI',sans-serif`, semantic colors (`#e53e3e` danger, `#2b6cb0` normal, `#38a169` success, `#ed8936` warning, `#805ad5` highlight, `#718096` neutral), inline legend, `max-width:100%`, `<title>` for accessibility. Numerical data: SVG + table = mandatory pair. Relationship/flow diagrams do not need a table. Minimum 1 SVG per report.

---

## Mandatory Final Sections

### Second-to-last Section: "What I Don't Know" (MANDATORY — except /ed-leisure)

- `gap-table` with open gaps (status: open/partial)
- `callout` variant=danger for critical uncertainties (that could invalidate a recommendation)
- `callout` variant=warning for untested assumptions
- DO NOT minimize — "I don't know" is valuable information
- Includes: missing data, untested hypotheses, unexplored alternatives, risks of being wrong

### Last Section: "Contextualization and Glossary" (MANDATORY)

- `paragraph` with 2-3 sentences providing context: for whom, at what moment, what prior knowledge helps
- `glossary` with `context` field and `terms` field listing ALL technical terms with practical definitions
- Allows high density in the body without losing accessibility

---

## Format Rules (MANDATORY)

- No internal anchor links (`<a href="#...">` causes blank screen on SharePoint)
- External links ALLOWED and ENCOURAGED (`<a href="https://...">`)
- 100% self-contained (inline SVG, inline CSS) — single file, no external dependencies
- No emojis (unless the user asks)
- High signal density — every block must add information, not decoration
- Prefer concrete examples over abstract descriptions

---

## Adversarial Sanity Check (edge-consult — MANDATORY in EVERY skill)

BEFORE generating the report YAML, submit the conclusions/recommendations to `edge-consult` for cross-model deliberation. GPT-5.4 (different model from the author) finds flaws, biases, weak premises.

```bash
# Adversarial (default) — synthesize conclusions in 2-3 sentences
edge-consult "Summary: [conclusions]. Where is this reasoning weakest?" --context /tmp/spec.yaml

# Collaborative (when stuck on direction)
edge-consult --mode collab "I'm stuck on X, what angles to explore?"
```

**Response protocol:**
1. Read the critique honestly
2. If the argument is valid → adjust conclusions/YAML
3. If maintaining position → record in the report as `callout` variant=info: "Sanity check GPT-5.4: [objection]. Response: [why I maintain my position]."

**In the report:** include a block showing what was challenged and how you responded. Tested conviction > unchallenged conviction.

**Cost:** ~$0.02/query. **Log:** ~/edge/logs/consult/ (for /ed-reflection to review).

---

## Post-Report Steps (MANDATORY)

### Review Gate (LLM-as-judge — RUN BEFORE publishing)

Before calling `consolidate-state`, run the review gate for semantic validation:

```bash
# Standalone review (refinement loop)
review-gate /tmp/spec-[skill]-[slug].yaml --skill [skill]

# If FAIL: adjust YAML based on feedback, re-run until PASS
# If PASS: publish
```

The review gate evaluates 6 dimensions (structural_completeness, content_depth, writing_quality, visualization, intellectual_honesty, internal_consistency) via GPT-4o-mini. Cost: ~$0.002/review. Threshold: 3.5/5.

**IMPORTANT:** `consolidate-state` also runs the review gate automatically (Phase 0.5). If the YAML doesn't pass, publication is blocked. Use `--skip-review` to force (only when you've already reviewed manually).

### Validation Gate (DO NOT SKIP)

`consolidate-state` already handles publication, HTML generation, and report indexing. After it, validate:

```bash
python3 ~/edge/blog/validate.py --recent
```

Common issues:
- `report:` with full path instead of filename → use just the filename
- Tag in English → use PT-BR (leisure, reflection, research, discovery, strategy, planejamento)
- Orphan report → create a blog entry referencing it

### Auto-index additional artifacts

If additional notes were created in ~/edge/notes/ (besides the report and blog entry already indexed by consolidate-state):

```bash
edge-index ~/edge/notes/[note].md
```

Silent command — errors do not interrupt the flow.
