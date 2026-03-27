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

### Workflow-specific fields (in frontmatter of workflow entries)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tags` | list | yes | Must include `workflow` (+ `anti-pattern` if it failed) |
| `secrets` | list | yes | Which `.env` files are needed ([] if none) |
| `cost_estimate` | string | no | Estimated cost per execution |

The body follows the structure:
- **Workflow:** Trigger → Steps → Secrets → When it works → When it fails → Cost
- **Anti-pattern:** What I tried → Why it doesn't work → Alternative that works

---

## Procedure Capture: Fields in EVERY blog entry

Beyond workflow-specific fields, **every blog entry** (research, discovery, strategy, etc.) can contain procedure capture fields. These feed the workflow lifecycle.

### Three fields, three signals

| Field | Type | When to use | Signal for corpus |
|-------|------|-------------|-------------------|
| `procedure:` | list of strings | NEW procedure discovered that was NOT covered by workflows recalled from RAG | Atom for crystallization into future workflow |
| `workflows_used:` | list of slugs | Workflow recalled from RAG that was followed AND produced good results | Reinforcement — boost relevance in RAG |
| `workflows_broken:` | list of slugs | Workflow recalled from RAG that was followed but FAILED or is outdated | Healing — flag for /ed-corpus-curation to fix/archive |

### Capture rule

1. Before executing, the skill consults workflows via `edge-search --type workflow -k 3`
2. During execution, the agent follows (or not) the recalled workflows
3. In the blog entry frontmatter:
   - If used a workflow and it worked → `workflows_used: [workflow-slug]`
   - If used a workflow and it failed → `workflows_broken: [workflow-slug]`
   - If discovered a new procedure (NOT covered by recall) → `procedure:` with format "When [context], do/avoid [action] because [result]"

### procedure: format

```yaml
procedure:
  - "When researching a new topic, run edge-sources BEFORE edge-consult -- external context strengthens adversarial review"
  - "When review-gate scores below threshold, fix section titles and inline acronyms first -- cheapest structural points"
  - "!When edge-search returns empty for workflows, log it as evidence the system needs seeding"
```

- `!` prefix marks anti-patterns (procedures to AVOID), same convention as claims
- Format: "When [context], do/avoid [action] -- [reason/result]"
- Each procedure is an atom — a single observation, not a full workflow

### How the corpus processes these signals

**`workflows_used:`** — `/ed-corpus-curation` counts citations per workflow. Frequently cited workflows gain relevance in RAG (confirmed_useful signal). Never-cited workflows are candidates for decay.

**`workflows_broken:`** — `/ed-corpus-curation` flags workflows cited as broken. Possible actions:
- Update the workflow (if the problem is fixable)
- Mark as anti-pattern (if the workflow is fundamentally broken)
- Archive (if the workflow is obsolete)

**`procedure:`** — `/ed-corpus-curation` (mode `procedures`) clusters procedure-claims by similarity. When 3+ claims converge on the same topic, proposes crystallization into a full workflow entry.

### Full example

```yaml
---
title: "Research: Secret Management for Agents"
date: 2026-03-27
tags: [research, security]
claims:
  - "Zero-knowledge proxy prevents credential exfiltration"
threads: [agent-security]
procedure:
  - "When researching a new topic, search internal corpus first (edge-search) -- prevents rediscovery"
  - "When edge-consult returns valid criticism, adjust conclusions BEFORE building report YAML -- retrofitting is harder"
  - "!When review-gate fails, do NOT regenerate entire YAML -- fix specific issues for cheaper recovery"
workflows_used: [sources-research-consult-report]
workflows_broken: [playwright-screenshot-validation]
---
```

---

## Capture: Two levels

### Level 1: Procedure-claims (atoms — in EVERY entry)

Capture in the `procedure:` field when:
- Used a combination of tools/steps that was NOT covered by workflows recalled from RAG
- Discovered a shortcut or a new anti-pattern

Do NOT capture:
- Procedures already covered by a recalled workflow (use `workflows_used:` to reinforce)
- Trivial single-tool usage

### Level 2: Workflow entries (molecules — when atoms crystallize)

Create a full workflow entry when:
1. **3+ similar procedure-claims** already exist in the corpus (detected by /ed-corpus-curation)
2. **The session combined 2+ capabilities** in a significant way that justifies immediate documentation
3. **A combination failed** in an instructive way — the anti-pattern prevents rediscovery of the failure

### Check before creating

```bash
# Check if a similar workflow already exists
edge-search "sources research consult" --type workflow -k 3
```

If something similar exists, use `workflows_used:` to reinforce instead of creating a duplicate.

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

## Lifecycle: Reinforcement, Decay and Healing

### Reinforcement (workflows_used:)

Workflows cited in `workflows_used:` accumulate a **confirmed_useful** signal. `/ed-corpus-curation` counts citations per workflow entry. The more cited, the more relevant in RAG.

### Decay (absence of citation)

Workflows never cited in `workflows_used:` lose relevance naturally:
- `edge-search` records telemetry for each search
- `/ed-corpus-curation` identifies workflows with no recent citation
- A workflow with no citation in 60 days is a candidate for archive

### Healing (workflows_broken:)

Workflows cited in `workflows_broken:` receive a **needs_attention** signal. `/ed-corpus-curation` flags these for action:
- If fixable → update the workflow
- If obsolete → mark as anti-pattern or archive
- If multiple entries cite the same workflow as broken → high priority

---

## Relationship with secrets/MANIFEST.md

The workflow declares **which secrets it needs** (`secrets: [exa.env, openai.env]`).
`MANIFEST.md` documents **what each secret enables and whether it's active**.

If a secret expires, there's no need to update each workflow — just consult the MANIFEST to know which workflows became broken.

---

## Migration from legacy workflows.md

The file `~/edge/autonomy/workflows.md` contains 15 workflows in the old format. These serve as historical reference but **new workflows must be blog entries** with tag `workflow`.

Gradual migration: as old workflows are re-discovered in use, capture them as blog entries. Do not migrate in batch — let usage determine what's worth preserving.
