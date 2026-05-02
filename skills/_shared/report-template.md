# Uniform Artifact Rite — Shared Protocol

**Applies to every `/ed-*` skill, without exception.** Every skill dispatch
— round-robin heartbeat or manual — produces a full-rite artifact following
this protocol. No minimal-meta, signal-only, voluntary-minimal, or
blackout-degraded variants (see `memory/rules-core.md` → Production).

Each skill contributes its own section titles and domain-specific YAML
blocks. This file defines the **uniform floor** every skill must meet:
blog entry + YAML spec + HTML report + adversarial review,
with Lineage, Gaps, Glossary, Bibliography, ≥1 SVG all MANDATORY.

---

## How to Generate

1. **Generate YAML** with the sections from the calling skill, using the block types below
2. **Write YAML** to `/tmp/spec-[skill]-[slug].yaml`
3. **Write the blog entry to a staging path** such as
   `/tmp/entry-[skill]-[slug].md`. Do not write directly into
   `~/edge/blog/entries/`; protected artifact paths are only writable by the
   `consolidate-state` pipeline.
4. **Write the blog entry as a light strategic invitation, then include claims
   in frontmatter** (compaction — MANDATORY). The entry body should be only a
   few concise paragraphs: frame why this matters now, explain what the
   operator gains by opening the report, and leave implementation depth to the
   report. Do not duplicate the YAML/report structure in the blog body.
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
   - Every claim must be valid YAML. Quote the whole claim when it contains
     `:`, `!`, backticks, brackets, quotes, or other punctuation that YAML may
     interpret structurally. For open gaps, keep the `!` inside the string:
     `- "!Open gap: what is still unknown"`.
5. **Publish atomically** (blog entry + report HTML + state commit):
   Validate the staging entry frontmatter and YAML spec before publishing. Do
   not run `consolidate-state` until this command exits cleanly:
   ```bash
   python3 - <<'PY'
   from pathlib import Path
   import sys, yaml

   entry = Path("/tmp/entry-[skill]-[slug].md")
   spec = Path("/tmp/spec-[skill]-[slug].yaml")

   raw = entry.read_text(encoding="utf-8")
   parts = raw.split("---", 2)
   if len(parts) < 3:
       sys.exit(f"missing frontmatter in {entry}")
   yaml.safe_load(parts[1]) or {}
   yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
   PY
   ```
   ```bash
   consolidate-state /tmp/entry-[skill]-[slug].md /tmp/spec-[skill]-[slug].yaml
   ```
   `consolidate-state` handles the full publication pipeline:
   - Phase 0/0.5: Frontmatter + review gate
   - Phase 1: Blog entry (blog-publish.sh)
   - Phase 2: Content report (generate_report.py → ~/edge/reports/)
   - Phase 3/3.4: Verification + LLM cost
   - Phase 5: State commit (claims, threads, events, digest)
   - Phase 6: Diffs + git commit

   **YAML spec is MANDATORY — never publish without it.** Publishing a blog
   entry without a YAML spec skips Phase 2 (content report), producing no
   HTML. That path is forbidden by the uniform rite.

   **Staging is not completion.** A skill invocation must not close with only
   `/tmp/spec-*` and `/tmp/entry-*` files. Do not ask the operator whether to
   publish, recommend a later `consolidate-state` run as the final answer, or
   hand off because older drafts are blocked. Run `consolidate-state` in this
   invocation, fix gate feedback if it blocks, and verify the generated report.
   If publication cannot complete, report the concrete failing command and
   failure reason rather than presenting the run as successful.

   **Single review owner:** do not run standalone `edge-consult` or
   `review-gate` before this command during the normal publication path.
   `consolidate-state` owns the mandatory adversarial, Feynman, review-gate,
   publication, and state-commit phases. If a gate blocks, address
   the emitted feedback and rerun `consolidate-state`; do not build a parallel
   pre-publication review loop in the skill backend.

   Useful flags: `--scratchpad PATH`, `--reason TEXT`
   (Enforcement #218: bypass flags `--skip-review`, `--no-adversarial`, `--no-meta` were removed — all phases run unconditionally.)
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
    lead: "Two to four sentences that frame the section's question, why it matters now, and how to read the evidence below."
    blocks: [...]

# MANDATORY — auto-renders as the last section "References"
bibliography:
  - text: "Source description"
    url: "https://..."
    source: "ArXiv"   # ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

---

## Available Block Types

Sections also support a top-level `lead` field. Use it for the short narrative
bridge between the section title and the evidence blocks:

```yaml
sections:
  - title: "2. What changed in the runtime"
    lead: >
      This section separates legitimate long-running work from actual stalls.
      The table is evidence, not the argument: read it as a status map of
      process liveness, event progress, and artifact completion.
    blocks:
      - type: table
        headers: [...]
        rows: [...]
      - type: paragraph
        text: >
          The operational conclusion is that duration alone should not become
          a failure signal when the owner process and event stream are alive.
```

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
| `bar-chart` | Quantitative comparison with SVG + table | title?, unit?, items[{label,value,variant?}] |
| `line-chart` | Trend/sequence with SVG + table | title?, unit?, points[{label,value,variant?}] |
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

## Golden Rule 1: Narrative Scaffolding (ALL skills)

Do not make tables, charts, matrices, diagrams, metrics grids, or gap tables do
the explanatory work alone. The reader needs a small interpretive bridge before
dense evidence appears.

Every non-reference section MUST satisfy one of these:

- section has a `lead` with 2-4 concrete sentences;
- or the first block is `paragraph` and explains the section's question,
  relevance, and reading frame.

If a section contains `table`, `comparison-table`, `risk-table`, `bar-chart`,
`line-chart`, `comparison`, `metrics-grid`, `gap-table`, `raw-html` diagram, or
similar dense evidence block, add reader guidance around it:

- before: what question the evidence answers;
- after: what the reader should conclude, decide, or keep uncertain.

This is not permission to inflate the artifact. Preserve analytical depth,
sources, gaps, and recommendations by shortening oversized tables, merging
duplicate rows, and moving low-value detail into fewer, better explained blocks.
Do not compensate for narrative leads by deleting evidence, citations,
uncertainties, or executable next steps.

---

## Golden Rule 4: Inline SVG Visualizations (MANDATORY when applicable)

SVG is not just for numbers — any information that communicates better as an image deserves SVG. Rule: if the reader would need to draw on paper to understand, generate SVG.

**When to generate SVG/chart blocks:**
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

**SVG standard:** fixed viewBox (`700 280` charts, `700 400` diagrams), `font-family:'Segoe UI',sans-serif`, semantic colors (`#e53e3e` danger, `#2b6cb0` normal, `#38a169` success, `#ed8936` warning, `#805ad5` highlight, `#718096` neutral), inline legend, `max-width:100%`, `<title>` for accessibility. Numerical data: SVG + table = mandatory pair. Relationship/flow diagrams do not need a table. Minimum 1 SVG per report; for reports with multiple comparisons, trends, risks, or operational trade-offs, default to 2+ visual encodings. Prefer the structured `bar-chart` and `line-chart` blocks for routine numerical comparisons, and `raw-html` SVG for diagrams that need custom layout.

---

## Mandatory Final Sections

### Second-to-last Section: "What I Don't Know" (MANDATORY — all skills)

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

## Review Ownership (MANDATORY)

`consolidate-state` is the single owner of publication review. It runs:

- Phase 0.3: adversarial review;
- Phase 0.45: Feynman judge;
- Phase 0.5: review gate;
- Phase 1-6: publication, report materialization, verification, state commit,
  audit, and git trail.

Do not call `edge-consult` or `review-gate` manually before publishing in the
normal skill backend. Manual review calls are allowed only for a genuinely
decision-blocking research question, and their output must be summarized
compactly rather than pasted into the prompt. Routine report quality gates
belong to `consolidate-state`.

If `consolidate-state` blocks on review feedback, fix the specific YAML issues
it reports and rerun `consolidate-state`. Do not regenerate the whole report
or run a second standalone review loop unless the gate explicitly needs a new
draft.

---

## Post-Report Steps (MANDATORY)

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
