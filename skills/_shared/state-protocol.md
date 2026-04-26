# State Protocol — State Management Between Skills

Used by: ALL skills that produce output or change status.
Each skill references this file instead of having its own state management instructions.

**Autonomy decisions:** see `~/edge/autonomy/autonomy-policy.md` (when to execute vs ask).
**Audit tool:** `edge-state-audit` (snapshot, propose, audit, scan).
**Step tracking:** `edge-skill-step` (records steps executed/skipped per skill).
**Status consistency:** `edge-state-lint` (detects drift between memory files).

---

## Step Tracking (MANDATORY in skills with protocol)

When executing a skill with numbered steps, log each executed step:

```bash
edge-skill-step <skill> <step_id>              # step executed
edge-skill-step <skill> skip <step_id> [reason]  # step explicitly skipped
edge-skill-step <skill> end                     # summary (detects silent skips)
```

**Rule:** call `edge-skill-step <skill> end` when finishing the skill. The tool compares logged steps against the registry (`~/edge/tools/skill-steps-registry.yaml`) and reports silently skipped steps.

If a step is skipped for a valid reason (e.g.: cache hit, already ran this session), use `skip` with a reason. A step not logged as either executed or skipped = **silent skip** = /ed-reflection will flag it.

---

## Core Principle

**Every change to a protected file must be PROPOSED before and AUDITED after.**

The agent can edit its own status files — but each change must be:
1. **Declared** (proposed with justification BEFORE editing)
2. **Visible** (automatically audited by the pipeline)
3. **Traceable** (recorded in the commit with status ok/partial/failed)

An unproposed change to a protected file = **fatal violation** = pipeline aborted.

---

## Protected Files

Any change to these files is monitored by `edge-state-audit`:

**Memory** (paths use Claude Code project dir — resolve via `~/.claude/projects/-home-$USER/memory/`):
- `~/.claude/projects/-home-$USER/memory/MEMORY.md`
- `~/.claude/projects/-home-$USER/memory/debugging.md`
- `~/.claude/projects/-home-$USER/memory/personality.md`

**Autonomy:**
- `~/edge/autonomy/capabilities.md`
- `~/edge/autonomy/frontier.md`
- `~/edge/autonomy/workflows.md`
- `~/edge/autonomy/metrics.md`
- `~/edge/autonomy/autonomy-policy.md`

**Skills:**
- `~/.claude/skills/*/SKILL.md`
- `~/.claude/skills/_shared/*.md`

**Exception:** debugging.md can be edited immediately when a CRITICAL error is found (>5min wasted, user intervention, error that will recur). Record the exception in the scratchpad.

---

## Async Inbox (MANDATORY, before execution)

**User interaction is priority.** The async blog chat is the canonical operator
input channel, but skills must consume it through the structured inbox
contract rather than scraping `/api/chat` directly.

Before meaningful execution, read the inbox:

```bash
edge-skill-inbox read --skill <skill> | tee /tmp/edge-skill-inbox.json
```

Rules:
- `edge-skill-inbox read` returns the **captured dispatch snapshot** when the
  skill was already dispatched. This is the deterministic contract for the
  current cycle (`request.async_inbox` in `state/current-dispatch.json`).
- If there is no active dispatched cycle yet, the tool falls back to a live
  view. Use that only for lightweight routing/bootstrap. The real contract is
  captured at `edge-dispatch dispatch --skill <skill>`.
- Inspect all buckets: `direct_messages`, `task_intents`, `steering_intents`,
  `runtime_intents`, and `pinned_messages`.
- If the inbox reports `priority: high`, address it before generic exploration,
  rotation, or opportunistic work.
- `task_intents`, `steering_intents`, and `runtime_intents` are operator
  instructions queued for the **next dispatch**, not immediate mutations.
- Do **not** mark chat messages as processed or post manual acknowledgements
  inside the skill. The captured `message_ids` are acknowledged and consumed
  by the `async_inbox.respond` postflight procedure only after the skill
  reaches completion evidence.
- The shared protocol is the genotype of this rule. `pre-skill` is its
  phenotype. They must agree: user interaction outranks generic exploration.

---

## Workflow Lookup (MANDATORY, before execution)

Before starting any skill, look up relevant workflows and save the results:

```bash
edge-cap invoke search.corpus -- "terms relevant to what I'm about to do" --type workflow -k 3 | tee /tmp/edge-recalled-workflows.txt
```

Returns validated workflows (steps, secrets, when it works/fails) and anti-patterns (what didn't work and why). The results are saved to `/tmp/edge-recalled-workflows.txt` so they're available at entry-creation time (recall happens early, entry is written late).

### Procedure capture in frontmatter (MANDATORY in every entry)

When creating the blog entry, **read `/tmp/edge-recalled-workflows.txt`** to fill in citations:

```bash
# Recall what workflows were returned at the start of the skill
cat /tmp/edge-recalled-workflows.txt 2>/dev/null
```

Then include procedure capture fields in frontmatter:

```yaml
# Recalled workflows that were followed and worked (MANDATORY if workflows were recalled):
workflows_used: [workflow-slug-1, workflow-slug-2]

# Recalled workflows that failed or are outdated:
workflows_broken: [broken-workflow-slug]

# If no workflows were recalled, use empty lists:
workflows_used: []
workflows_broken: []

# NEW procedures (not covered by recalled workflows):
procedure:
  - "When [context], do [action] -- [result/reason]"
  - "!When [context], avoid [action] -- [failure reason]"
```

**Rule:** `procedure:` only captures the DELTA — procedures NOT covered by the recall. If the procedure already exists as a workflow, cite in `workflows_used:` (reinforcement) or `workflows_broken:` (healing).

**Note:** `consolidate-state` warns if `procedure:` is present but `workflows_used:` is missing — the pipeline expects both.

See `~/.claude/skills/_shared/workflow-conventions.md` for lifecycle details.

---

## Source Lookup

When a skill needs external evidence, recent information, examples, public discussions, papers, repositories, or broader context, use the source capability wrapper:

```bash
edge-cap invoke sources.aggregate -- "topic" --intent <skill>
```

The current implementation behind that capability is `edge-sources` (plural). Do not use `edge-source` singular; it is not the current command.

Use direct web search only as a complement when the source capability does not cover the needed page, document, or precise verification target.

The output artifact should say which source routes were used and how they changed the analysis. If source lookup is unavailable or degraded, surface that limitation instead of silently proceeding as if external context was checked.

---

## Full Flow (with status changes)

### Step 1: Execute skill + note in scratchpad

```bash
edge-scratch add "what I observed, discovered, or want to record"
```

Accumulate observations. DO NOT edit protected files yet.

### Step 2: PRE Snapshot (before any changes)

When the skill identifies that it needs to change protected files:

```bash
edge-state-audit snapshot --slug <SLUG>
```

Captures SHA256 of all protected files BEFORE any editing.
The pipeline (consolidate-state Phase 0a) skips if the snapshot already exists.

### Step 3: Propose changes

Declare EXACTLY which protected files will be modified and why:

```bash
# Create YAML with proposed changes
cat > /tmp/state-changes-<SLUG>.yaml <<'EOF'
changes:
  - path: "~/.claude/projects/-home-$USER/memory/MEMORY.md"
    action: modify
    reason: "Add insight about X confirmed this session"
    sections: ["Consolidated Knowledge"]
  - path: "~/edge/autonomy/capabilities.md"
    action: modify
    reason: "Register new capability #24"
EOF

# Register proposal
edge-state-audit propose --slug <SLUG> --file /tmp/state-changes-<SLUG>.yaml
```

**Proposal rules:**
- **File-level + action + justification.** DO NOT detail lines/hunks.
- Actions: `add` (new file), `modify` (change existing), `delete` (remove)
- `sections` is optional — indicates which sections will be affected
- Proposal reflects **original intent** — NEVER rewrite after execution

### Step 4: Execute changes

Now proceed to edit the protected files as proposed.

If during editing you realize you need to change a file NOT proposed:
- **Stop.** Update the proposal with `edge-state-audit propose` again.
- Or accept that the audit will record it as a violation.

### Step 5: Create blog entry + claims + procedures

#### Blog Entry Voice Contract

The blog entry body is the invitation, not the report. Write it as a short,
light read that helps the operator remember why this work matters and decide
whether to open the attached report.

Required voice:
- Keep the body to a few concise paragraphs; default to 2-4 paragraphs.
- Lead with what changed, what was learned, or what door this opens.
- Use plain language and an exploratory tone; avoid implementation dumps,
  acronyms, long lists, stack traces, and dense protocol detail in the body.
- Put technical depth in the report, notes, claims, procedures, and metadata.
- End by pointing toward the reader-visible report or next question when useful.

If a publication needs heavy detail, the entry should summarize the shape of the
finding and let the content report carry the technical load.

```yaml
claims:
  - "Verified fact I learned"
  - "!Gap — thing I still don't know"
threads: [related-thread]
keywords: [kw1, kw2]

# Procedure capture (see workflow-conventions.md)
workflows_used: [slug-of-workflow-that-worked]
workflows_broken: [slug-of-workflow-that-failed]
procedure:
  - "When [context], do [action] -- [result]"
  - "!When [context], avoid [action] -- [reason]"
```

Claims are durable knowledge (the WHAT). Procedures are operational knowledge (the HOW).
`procedure:` only captures the delta — procedures NOT covered by recalled workflows.

### Step 5b: Emit operational signals (MANDATORY — minimum 2)

Every entry MUST include at least **2 signals** from the typed fields below. Agent chooses which types are relevant — but must emit at least 2. This ensures operational memory accumulates.

```yaml
# Typed signals — pick the ones that apply (minimum 2 total)
autonomy:    # what's missing — capabilities, access, tools needed
  - "edge-consult needs openai in venv"
strategy:    # direction — market, positioning, priorities, external changes
  - "Boring wedge > category narrative"
reflection:  # meta-cognition — how the work went, cost, efficiency
  - "3 review gate iterations for 1 point — diminishing returns"
friction:    # pain points — what broke, what's slow, what's hard
  - "YAML report format consumes most tokens"
decision:    # governance — what operator approved/rejected
  - "Operator approved pip install"
serendipity: # positive surprises — what worked unexpectedly well
  - "Corpus search found a 3-week-old note that connected 3 threads"
```

Prefixes: (none)=verified, `!`=open gap, `?`=speculative.
consolidate-state extracts these automatically via `edge-signal`.

### Step 6: Publish via consolidate-state (MANDATORY)

**NEVER publish entries or reports manually.** Always use consolidate-state.
Without it: no meta-report, no state commit, no adversarial review, no git audit trail.

```bash
# With content report
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-<skill>.yaml

# Without content report (meta-only)
consolidate-state ~/edge/blog/entries/<slug>.md
```

The pipeline automatically handles:
- **Phase 0a:** PRE Snapshot (skips if already exists — Step 2)
- **Phase 1-4:** Entry, report, verification, meta-report
- **Phase 5:** State commit (claims + threads + event)
- **Phase 5b:** **State audit** — compares PRE snapshot vs current status vs proposal
  - `exit 0` = OK (everything proposed and executed)
  - `exit 2` = partial (proposed but not executed — WARN)
  - `exit 4` = divergence (action different from proposal — **ABORT**)
  - `exit 5` = violation (unproposed change — **ABORT**)
- **Phase 6:** Diffs + git commit with `[state:ok|partial|failed]`

### Step 7: Read meta-report

The pipeline prints the path. Read before continuing.

---

## Simplified Flow (without status changes)

If the skill does NOT change any protected file (e.g.: pure blog entry, research):

1. Look up relevant workflows (`edge-cap invoke search.corpus -- "terms" --type workflow -k 3`)
2. Execute skill
3. Note in scratchpad
4. Create blog entry with claims (+ blog entry with tag `workflow` if a new combination emerged)
5. `consolidate-state` (Phase 0a captures snapshot, Phase 5b confirms nothing changed — OK)

No proposal needed. The pipeline is backwards-compatible.

---

## Audit Result Policy

| Case | Result | Action |
|------|--------|--------|
| Proposed and executed as planned | OK | Pipeline continues |
| Proposed but not executed | WARN (exit 2) | Pipeline continues, commit records `partial` |
| Executed without proposal | VIOLATION (exit 5) | **Pipeline ABORTED** |
| Action different from proposal | DIVERGENCE (exit 4) | **Pipeline ABORTED** |
| No proposal, no changes | OK | Pipeline continues |

**Main rule:** for protected files, any unproposed change is a fatal failure.

---

## What Replaced What

| Before | Now |
|--------|-----|
| Append 3-5 lines to working-state.md Timeline | `edge-scratch add "observation"` |
| Read working-state.md for context | Read `~/edge/briefing.md` (generated by edge-digest) |
| Manually update "Active Threads" | Threads in `~/edge/threads/`, updated by pipeline |
| Edit MEMORY.md/debugging.md ad-hoc | Proposal → edit → audit |
| breaks-archive.md / breaks-active.md | Unchanged (break records, not status) |

---

## Break Records (preserved)

Skills that take breaks (/ed-leisure, /ed-research, /ed-discovery, /ed-planner) continue recording in:

1. **breaks-archive.md** — full entry with metadata
2. **breaks-active.md** — summary of the last 5 breaks

This does NOT change. Breaks are activity records, not status management.

---

## Glossary

| Term | Definition |
|------|------------|
| **scratchpad** | Temporary file (`/tmp/edge-scratch-*.md`) for mid-session observations |
| **meta-report** | Markdown in `~/edge/meta-reports/` with state delta + scratchpad + adversarial |
| **content report** | HTML in `~/edge/reports/` — heavy analytical artifact (optional) |
| **briefing.md** | `~/edge/briefing.md` — compacted status, generated by edge-digest |
| **claims** | Durable knowledge in frontmatter. `!` = open gap |
| **threads** | Investigation threads in `~/edge/threads/` |
| **events** | Status transitions in `~/edge/logs/events.jsonl` |
| **state commit** | Phase 5 of consolidate-state: claims + threads + events + digest |
| **state proposal** | YAML in `~/edge/meta-reports/<slug>.state-proposal.yaml` with intended changes |
| **state audit** | YAML in `~/edge/meta-reports/<slug>.state-audit.yaml` with PRE vs POST result |
| **snapshot PRE** | YAML in `~/edge/state-snapshots/<slug>.pre.yaml` with SHA256 before changes |

---

## Quick Reference for Skills

Add to each skill's SKILL.md:

```markdown
**Follow `~/.claude/skills/_shared/state-protocol.md` for status management.**
```

### If the skill modifies protected files:
```markdown
### State Management
1. `edge-state-audit snapshot --slug <SLUG>` (before editing)
2. `edge-state-audit propose --slug <SLUG> --file /tmp/state-changes.yaml`
3. Edit protected files
4. `consolidate-state` audits automatically (Phase 5b)
```

### If the skill does NOT modify protected files:
```markdown
### Record observations
`edge-scratch add "what happened and why"` during execution.
State is processed at publication (meta-report → state commit).
```
