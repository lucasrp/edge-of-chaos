---
name: ed-research
description: "Deep dive research on a specific topic or problem. Directed study with actionable output. Triggers on: research, pesquise, estude, deep dive, aprofunde, feynman, entenda, derive, first principles, explique de verdade, explain for real."
user-invocable: true
---

# Research — Directed Deep Dive

I know WHAT I want to learn — I need to go deeper. Focused research on a specific topic, tool, or problem. Unlike /ed-discovery (which explores freely), /ed-research starts from a clear target.

Examples: "/ed-research DSPy", "/ed-research how to reduce token cost", "/ed-research pipeline patterns".

---

## Optional Arguments

- **No argument** (`/ed-research`): automatically identify target from context friction points
- **With topic** (`/ed-research DSPy`): research that topic in depth
- **With problem** (`/ed-research how to optimize the pipeline flow`): research a solution for that problem
- **Feynman mode** (`/ed-research feynman backpropagation` or `/feynman X`): deep understanding — derive before researching, teach to test understanding, track gaps

When an argument is provided, **skip the target identification step** and go straight to what was requested.

### Feynman Mode

Activated when the argument contains "feynman", or when the trigger is `/feynman`, `entenda`, `derive`, `explique de verdade`.

Changes Step 3: instead of researching directly, follows the cycle:

1. **Derive first** — before searching any source, try to reconstruct the concept from scratch. Where does it stall? Note as `[GAP: ...]`
2. **Research only the gaps** — don't do a general survey. Search exactly what was missing from the derivation
3. **Teach** — write the explanation as if teaching someone intelligent without context. No jargon. With analogies. With mechanics. With limits
4. **Verify gaps** — reread with a critical eye. Where did it stay vague? Mark `[STILL DON'T UNDERSTAND: ...]`. If there are gaps, go back to step 2 (max 2 iterations)

The Feynman mode output is a **self-contained explanation** instead of actionable recommendations. The report uses `comparison` before/after (superficial understanding → deep) and the explanation is the central section.

---

## The Job

Go deep on a specific topic and produce actionable recommendations (default mode) or deep understanding (Feynman mode).

| | /ed-research (default) | /ed-research feynman | /ed-discovery |
|---|---|---|---|
| **Question** | "What to do about X?" | "Do I truly understand X?" | "What don't I know I don't know?" |
| **Method** | Search, compare, recommend | Derive, teach, track gaps | Explore freely |
| **Output** | Actionable recommendations | Self-contained explanation + gaps | New tool/concept |
| **Test** | "Do I know what to do?" | "Can I reconstruct it?" | "Did I find something useful?" |

---

## Context Activation

**Use the runtime pre-skill context injected by `edge-preflight` and sourced from `~/edge/config/preflight.yaml`.**

---

## Protocol (follow in order)

### Step 1: Semantic search in corpus (what do I already know?)

Before researching, check what already exists in the corpus (~1060 docs) about the topic:

```bash
# Hybrid search (FTS + embeddings) — 8 results
edge-search "[research topic]" -k 8
```

If the topic has multiple facets, use complementary queries:
```bash
edge-search "[technical facet]" -k 5 --type note
edge-search "[conceptual facet]" -k 5 --type report
```

For each relevant result, read the original:
```bash
cat ~/edge/notes/[file].md | head -60    # Notes — more detailed
head -30 ~/edge/reports/[file].yaml       # Reports — title, summary
```

**What to look for:**
- Discoveries already made — don't rediscover
- Recommendations already given — build on, don't repeat
- Open gaps in previous research — prioritize these
- Evolution — what changed since the last work on the topic

**Decision:**
- If already covered in depth → focus on open gaps or evolution since then
- If covered superficially → go deeper, citing the antecedent
- If it doesn't appear → new territory, full research

**In the output:** mention what the search returned and how it influenced the scope.

### Step 2: Identify research target

Based on absorbed context, choose 1-3 concrete research targets:

Focus areas (prioritized by impact):

1. **Prompt Engineering** — prompt improvements, few-shot, chain-of-thought, quality evaluation
2. **Code Quality** — tools (ruff, mypy, bandit), Python patterns, safe refactoring
3. **Tools and Ecosystem** — useful MCPs, plugins, automations (CI/CD, pre-commit hooks, linters)
4. **Architecture and Patterns** — document pipelines, status, fallback and resilience
5. **Applied Domain** — work domain context, terminology, process automation

### Step 3: Research (use ultrathink)

**Use `ultrathink` (thinkmax)** — think deeply before acting.

- Research with depth, not breadth
- Search for recent papers, tools, concrete examples
- Compare approaches with clear trade-offs
- Produce actionable recommendations (not "consider using X", but "install X, configure Y, expected result Z")

#### Step 3.5: Search external sources (MANDATORY)

Run `/ed-sources research "[topic]"` to get insights from all relevant external sources (X, Web, ArXiv, HN, GitHub).

Cite in the report as source (with @username and URL for tweets, link for papers/posts).
If there are suggested likes from /ed-sources, execute via `/redes engajar`.


### Step 3.7: Adversarial sanity check (MANDATORY)

Synthesize conclusions and recommendations in 2-3 sentences and submit to edge-consult (details: report-template.md):

```bash
edge-consult "Summary: [research conclusions]. Where is this weakest?" --context /tmp/spec-research-[slug].yaml
```

Adjust if GPT finds a valid flaw. If position holds, record as callout in the report.

### Step 4: Save

- Notes: `~/edge/notes/`
- Prototypes: `~/edge/lab/`
- If something functional was built: `~/edge/builds/`

### Step 5: Record in break journal

Record in THREE files:

1. **`breaks-archive.md`** — full entry (date, type, targets, discoveries, recommendations, applications)
2. **`breaks-active.md`** — 3-5 line summary in the "Last 5 Breaks" section (remove the oldest if > 5)
3. **Status observations:** `edge-scratch add "what happened"` during execution. State processed at publication via meta-report (see `~/.claude/skills/_shared/state-protocol.md`).

If the discovery is significant, update the "Practical Discoveries" section of `breaks-active.md`.

### Step 6: Update internal blog + generate HTML report

**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**

1. Create .md entry in `~/edge/blog/entries/` with tag `research` (format: see `/ed-blog` SKILL.md)
2. **Generate YAML** of the report with the mandatory sections below, using converter block types
3. **Write YAML** to `/tmp/spec-research-[slug].yaml`
4. Publish everything atomically (blog entry + report HTML + indexing):
   ```bash
   consolidate-state ~/edge/blog/entries/<file>.md /tmp/spec-research-[slug].yaml
   ```
5. **Read the generated HTML** (`~/edge/reports/<file>.html`) for verification

#### YAML Structure

```yaml
title: "Research: [Topic]"
subtitle: "[Descriptive subtitle]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Problem:** ..."
  - "**Main insight:** ..."

metrics:
  - value: "N"
    label: "Description"

sections:            # 5 sections (default) or 8 sections (Feynman)
  - title: "1. Research Target"
    blocks: [...]
  # --- Feynman Sections (Feynman mode only) ---
  - title: "2. Derivation"               # FEYNMAN: what I derived from scratch
    blocks: [...]
  - title: "3. Identified Gaps"           # FEYNMAN: gap table
    blocks: [...]
  - title: "4. Gap Resolution"            # FEYNMAN: gap → answer
    blocks: [...]
  # --- Common Sections ---
  - title: "5. Discoveries"              # (or "2." in default mode)
    blocks: [...]
  - title: "6. Actionable Recommendations" # (or "3." in default mode)
    blocks: [...]
  - title: "7. Applications to Work"      # (or "4." in default mode)
    blocks: [...]
  - title: "8. Next Steps"               # (or "5." in default mode)
    blocks: [...]

# MANDATORY — auto-renders as last section "References"
bibliography:
  - text: "Source description"
    url: "https://..."
    source: "ArXiv"   # Where it came from: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

#### Feynman Structure (sections 2-4)

In Feynman mode, sections 2-4 capture the derivation process:

**2. Derivation** — what I derived from scratch before researching:
- `derivation` blocks for each reasoning (title, text, bullets, code)
- `gap-marker` for each `[GAP: ...]` identified during derivation
- `concept-grid` for concepts I reconstructed

**3. Identified Gaps** — summary table of all gaps:
- `gap-table` with gaps[{id, description, need, status(resolved/partial/open)}]
- The reader sees at a glance: where knowledge failed and what was resolved

**4. Gap Resolution** — each gap linked to its answer:
- `gap-resolution` for each resolved gap (gap_id, gap, text, answer)
- The reader sees the chain: gap → research → discovery
- Open gaps remain without `answer` or with callout variant=danger

**Block types, golden rule 0, golden rule 4, final sections, format, validation, and indexing:** see ~/.claude/skills/_shared/report-template.md.

#### Golden rule 1: concept-box for each concept

For EACH concept, tool, technique, or technical term discovered in the research, use `concept-grid` with:
- **Name** of the concept
- **Analogy** ("X is like Y, but for Z")
- **Practical definition** (what it does, in 2-3 simple sentences)

Research discovers new things — the report must teach each one. No concept is "too obvious".

#### Golden rule 2: "How it is / How it would be" for each recommendation

EVERY actionable recommendation MUST include a visual comparison showing current status vs proposed status. NOT abstract descriptions — real content:

- **For code changes:** use `diff-block` or `comparison` with literal snippets
- **For workflow changes:** use `comparison` (before/after with pre + bullets)
- **For new tools:** use `flow-example` (yellow input → green output)
- **For configs:** use `code-block` showing the actual file that would be created/modified

The reader must see EXACTLY what would change if they follow the recommendation.

#### Golden rule 3: flow-example for each technical discovery

For EACH significant discovery (architecture, pipeline, internal mechanism), include at least one `flow-example` showing concrete data flowing:

1. **label:** "Example: [name] — [what it demonstrates]"
2. **input:** real or realistic input data (automatic yellowish background)
3. **output:** produced result (automatic greenish background)
4. **code:** (optional) code/config that performs the transformation (gray background)

The reader should "see" the discovery operating with real data, not just read about it.


#### Mandatory sections (in this order):

**1. Research Target**
- What problem or gap motivated the research (concrete, not abstract)
- Work context: where this fits in current projects
- **concept-box** for each new concept mentioned (see rule 1)
- What the reader should know before continuing

**2. Discoveries**
- Organize by insight, not by source. Each discovery is a subsection
- **concept-box** for found tools/techniques
- **flow-example** for each discovered mechanism (see rule 3)
- Comparisons between alternatives: use `comparison` or `table`
- Explicit trade-offs: use `callout` for limitations and caveats
- Concrete data: numbers, benchmarks, real examples when available

**3. Actionable Recommendations**
- Numbered cards (`numbered-card`) for each recommendation
- **"How it is / How it would be"** mandatory for each (see rule 2)
- Each recommendation must have: what to do, how to do it, expected result
- Not "consider using X" — rather "install X, configure Y, expected result Z"
- Priority by impact: use `badge` (HIGH IMPACT / MEDIUM / INCREMENTAL)

**4. Applications to Work**
- Concrete and specific connections to current projects
- For each application: which project, which file/component, which change
- Use `table` to map discovery → project → concrete action
- `callout` for dependencies or prerequisites

**5. Next Steps**
- Use `next-steps-grid` for visual roadmap
- Differentiate: what to do now vs what to investigate later vs ideas for /ed-planner
- If any discovery justifies a cycle proposal: mention explicitly


### Step 7: Report to user

Format:

```
## Research — [Topic] — [Date]

### Target
[What I researched and why — what problem or gap motivated it]

### Discoveries
[What I found, with details, sources, and comparisons]

### Recommendations
[What to do concretely — installation, configuration, workflow change]

### Applications to Work
[How to apply to current problems — concrete and specific connections]

### Next Steps
[What to resume, test, or implement]

### HTML Report
~/edge/reports/[file].html
```

---

## Post-execution

**Use the runtime post-skill protocol sourced from `~/edge/config/postflight.yaml` and executed by `edge-postflight`.**

---

## Privacy Rule (CRITICAL)

For external posts (Netlify, any public communication):

**NEVER** identify: organization/company name, owner's name, project name, or any data that allows tracing the human.

---

## Notes

- Research is DIRECTED — it starts from a known target. For free exploration, use /ed-discovery
- Prioritize problems that appear in multiple CLI sessions (larger sessions = more iteration)
- Produce actionable recommendations, not theoretical summaries
- Use `ultrathink` (thinkmax) for research
