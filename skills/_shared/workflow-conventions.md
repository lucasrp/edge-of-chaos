# Workflow Conventions — Capture and Retrieval of Operational Knowledge

Workflows document **how I work** — combinations of capabilities, secrets, and steps that produced results. Blog entries capture what I think; workflows capture what I do.

---

## Why it exists

Every session discovers combinations, shortcuts, better ways of doing things. Without capture, this dies when the session ends. In the next session, it's rediscovered from scratch or simply not done.

The blog has 600+ entries because the capture pipeline exists. Workflows were ~10 because they had no pipeline.

---

## Format: Blog Entry with tag `workflow`

A workflow is a normal blog entry with `workflow` in the tags. edge-search detects the type and allows filtering by `--type workflow`.

### Workflow that works

```yaml
---
title: "workflow: sources → research → consult → report"
date: 2026-03-24
tags: [workflow, research, sources, edge-consult]
keywords: [edge-sources, ed-research, edge-consult, exa, openai, pipeline]
claims:
  - "Combining sources + consult before the report improves output quality"
secrets: [exa.env, openai.env]
cost_estimate: "~$0.15/execution"
---

## Trigger
Heartbeat identifies relevant topic, or user requests /ed-research.

## Steps
1. `edge-sources "topic" --intent research` → source collection (Exa + X + HN)
2. LLM curation → filter signal from noise
3. `edge-consult` → adversarial review of draft (GPT-5.4)
4. Blog entry + HTML report

## Secrets
- `exa.env` — semantic search in step 1
- `openai.env` — adversarial review in step 3

## When it works
Technical-scientific topics with good coverage in sources.

## When it fails
Very niche topics where sources return little signal.

## Cost
~$0.15/execution (Exa: ~$0.01, OpenAI consult: ~$0.10, margin)
```

### Anti-pattern (workflow that doesn't work)

```yaml
---
title: "anti-pattern: playwright screenshot loop to validate report"
date: 2026-03-24
tags: [workflow, anti-pattern, chrome, playwright, reports]
keywords: [playwright, screenshot, chrome, report-validation, visual-feedback]
claims:
  - "Screenshot loop with Playwright is fragile — tab management disconnects frequently"
  - "!Gap — reliable alternative for visual report validation"
secrets: []
cost_estimate: "~$0 (local)"
---

## What I tried
1. Open HTML report in Chrome via Playwright
2. Screenshot → analyze rendering → edit → repeat

## Why it doesn't work
- Playwright disconnects from Chrome when tabs accumulate
- Inconsistent tab management (MetaMask always on tab 0 interferes)
- Time spent reconnecting > time saved validating visually

## Alternative that works
Validate reports via `validate.py --recent` (structural) + manual spot-check when necessary.
```

The difference is the `anti-pattern` tag. edge-search returns both — what works and what doesn't — and the skill decides.

---

### Workflow-specific fields (in frontmatter)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tags` | list | yes | Must include `workflow` (+ `anti-pattern` if it failed) |
| `secrets` | list | yes | Which `.env` files are needed ([] if none) |
| `cost_estimate` | string | no | Estimated cost per execution |

The body follows the structure:
- **Workflow:** Trigger → Steps → Secrets → When it works → When it fails → Cost
- **Anti-pattern:** What I tried → Why it doesn't work → Alternative that works

---

## Capture: When to record

Record a workflow during `consolidate-state` when:

1. **The session combined 2+ capabilities** in a way that produced a better result than each one alone
2. **A shortcut was discovered** — a more efficient way of doing something
3. **A combination failed** in an instructive way — the anti-pattern prevents rediscovery of the failure

Do not record:
- Isolated use of a skill (that's a blog entry, not a workflow)
- Workflows identical to an already indexed one (check with `edge-search` first)

### Check before creating

```bash
# Check if a similar workflow already exists
edge-search "sources research consult" --type workflow -k 3
```

If something similar exists, update the existing entry instead of creating a new one.

---

## Retrieval: How skills look them up

Before execution, skills can look up relevant workflows:

```bash
# Search for workflows related to what I'm about to do
edge-search "research sources blog" --type workflow -k 3
```

The result returns validated workflows with steps, required secrets, and when it works/fails. Anti-patterns appear alongside — the skill knows what to avoid.

This is **MANDATORY** before executing any skill (see state-protocol.md).

---

## Broken workflow = bug

A workflow that fails during execution should be recorded in `debugging.md` and marked as stale (claim `"!Gap"` or new anti-pattern).

---

## Decay

Workflows that are never retrieved lose relevance naturally:
- `edge-search` records telemetry for each search
- `/ed-corpus-curation` can identify workflows never consulted
- A workflow with no retrieval in 60 days is a candidate for archive

A workflow updated frequently (new sessions confirm the pattern) gains relevance.

---

## Relationship with secrets/MANIFEST.md

The workflow declares **which secrets it needs** (`secrets: [exa.env, openai.env]`).
`MANIFEST.md` documents **what each secret enables and whether it's active**.

If a secret expires, there's no need to update each workflow — just consult the MANIFEST to know which workflows became broken.

---

## Migration from legacy workflows.md

The file `~/edge/autonomy/workflows.md` contains 15 workflows in the old format. These serve as historical reference but **new workflows must be blog entries** with tag `workflow`.

Gradual migration: as old workflows are re-discovered in use, capture them as blog entries. Do not migrate in batch — let usage determine what's worth preserving.
