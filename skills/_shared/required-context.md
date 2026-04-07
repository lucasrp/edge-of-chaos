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

**Note:** Source primitives are available as MCP tools (registered via `.mcp.json`). No need to manually read `state/sources-manifest.yaml` — the primitives appear alongside native tools.

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
2. Execute EVERY procedure defined there, one by one
3. **CRITICAL: each procedure is independent. A failure in one MUST NOT
   stop the others.** Execute all of them, every time, regardless of
   prior failures. Log the outcome of each to `logs/post-skill.log`:
   ```
   [TIMESTAMP] procedure: [name] | status: [OK/FAIL/SKIP] | reason: [detail]
   ```
4. If a tool is missing (pandoc, latexmk), log it and move on — do not
   attempt to install packages mid-skill. **Dependency remediation
   happens during reflection, not mid-beat** — reflection reads
   post-skill.log, detects repeated SKIPs, and self-provisions
   missing tools into the agent's venv (see reflection HN-1c)
5. If a primitive exists for the task (e.g. `libexec/<codename>/overleaf-sync`),
   use it instead of raw commands
6. notify.sh is ALWAYS the last call, even if everything else failed —
   the operator needs to know what happened

**A post-skill that stops at the first failure is a bug, not caution.**

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

## Agent venv (tool execution environment)

Every agent has a virtual environment at `~/edge/blog/.venv/`. This is the
agent's **own** tool environment — phenotype, not genotype.

**Rules:**
1. **All Python tool execution uses the venv.** Run scripts with
   `~/edge/blog/.venv/bin/python3`, not system `python3`.
2. **All pip installs go into the venv.** `~/edge/blog/.venv/bin/pip install <pkg>`.
   Never `sudo pip install` or install into system Python.
3. **Binary tools go into `~/edge/blog/.venv/bin/`.** Static binaries
   (pandoc, tectonic, etc.) downloaded or extracted there are on PATH
   for all venv-invoked scripts.
4. **Primitives in `libexec/` should use the venv shebang:**
   `#!/usr/bin/env -S ~/edge/blog/.venv/bin/python3` or invoke the
   venv python explicitly.
5. **The venv is the remediation target.** When reflection detects a
   missing dependency (HN-1c), it installs into this venv. When
   `edge-apply` provisions an instance, it seeds this venv with
   dependencies from `agent.yaml`.

The venv is local, reversible, and isolated per instance. Installing
into it does not affect other agents or the host system.

---

## Source primitives — available as MCP tools

Source primitives are registered as MCP tools via `mcp-agent-server.py`
and appear alongside native tools (WebSearch, Bash, etc.). Use them
directly — no need to manually read the manifest or invoke via Bash.

**Why this matters:** primitives log usage to `state/source-usage.jsonl`,
follow `TOOL_CONTRACT.md` (JSON stdout, proper exit codes), and are
improvable by autonomy. WebSearch/curl bypass all of that — no usage
tracking, no versioning, no improvement loop.

**Rules:**
1. If an MCP tool exists for the source → **use it**
2. If a primitive is a `stub` (exit 127) → implement it per
   `docs/TOOL_CONTRACT.md`, then use it
3. If no primitive exists for the source → create one if you'll use
   it more than once; raw Bash is OK for true one-offs
4. If a primitive fails → log the failure and fix it. Do NOT silently
   fall back to WebSearch/curl — that hides the problem

**Creating or upgrading a primitive:**

1. Write contract: `libexec/<codename>/<name>.meta.yaml`
2. Write impl: `libexec/<codename>/<name>` (chmod +x, venv shebang)
3. Register in `state/sources-manifest.yaml`
4. Log usage to `state/source-usage.jsonl` via `_shared/usage_log.py`
5. Restart MCP server to pick up new tools (or wait for next session)
