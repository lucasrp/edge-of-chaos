# Required Context — Shared Pre-Step for All Skills

Used by: ALL skills. This step runs BEFORE Step 0 of any skill.

Every skill MUST execute this step before its own protocol begins.
Without it, the agent operates without identity, rules, or strategy — producing output disconnected from its own context.

---

## Step -1: Required context (BEFORE everything)

1. Read: `memory/rules-core.md`, `memory/personality.md`, `memory/metodo.md`, `memory/debugging.md`
2. Read: `config/pre-skill.md`, `config/post-skill.md`, `config/strategy.md`
3. Execute the Boot Ritual defined in `pre-skill.md` procedure section
4. Only then proceed to Step 0.

**Paths are relative to `~/edge/`.** Memory files use the Claude Code project directory (`~/.claude/projects/-home-$USER/memory/`) when they live there.

---

## Why

CLAUDE.md declares required reading for every session. Skills that skip it lose:
- **Rules** (rules-core.md) — guardrails, genotype/phenotype boundary
- **Voice** (personality.md) — who the agent is
- **Method** (metodo.md) — how the agent thinks
- **Error memory** (debugging.md) — mistakes that must not recur
- **Context activation** (pre-skill.md) — operator-specific checklist
- **Strategy** (strategy.md) — current phase and priorities

The heartbeat is especially vulnerable because it runs autonomously with no user present to course-correct.

---

## Step Final: Post-skill execution (AFTER work completes)

After the skill's main work is done and before closing the session:

1. Re-read `config/post-skill.md`
2. Execute each procedure defined there, in order
3. If a procedure fails, log the failure and continue — do not block
4. If a procedure is blocked by missing prerequisite, log as blocked — do not skip silently

Post-skill is the counterpart to Step -1. Pre-skill loads context before work.
Post-skill executes commitments after work. Neither is optional.

---

## Blog entry frontmatter (EVERY entry, no exception)

Every blog entry published via consolidate-state MUST include these fields
in the YAML frontmatter (per `state-protocol.md`):

```yaml
claims:
  - "Verified fact learned"
  - "!Open gap — thing I don't know"
threads: [related-thread-id]
keywords: [kw1, kw2]
workflows_used: [slug-of-workflow-that-worked]
workflows_broken: [slug-of-workflow-that-failed]
procedure:
  - "When [context], do [action] -- [result]"
  - "!When [context], avoid [action] -- [reason]"
```

`procedure:` captures the DELTA — new operational knowledge not already
covered by recalled workflows. Without it, the crystallize → workflow
loop is broken at the first step.

---

## Source primitives (when using declared sources)

When a repeated source operation doesn't have a primitive in
`libexec/<codename>/`, create one per `docs/TOOL_CONTRACT.md`:

1. Write contract: `libexec/<codename>/<name>.meta.yaml`
2. Write impl: `libexec/<codename>/<name>` (chmod +x)
3. Register in `state/sources-manifest.yaml`
4. Log usage to `state/source-usage.jsonl` via `_shared/usage_log.py`

One-off queries via raw Bash are fine. Repeated operations must become
primitives so they are logged, versioned, and improvable by autonomy.
