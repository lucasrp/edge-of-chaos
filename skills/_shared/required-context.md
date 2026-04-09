# Required Context — Shared Pre-Step for All Skills

Used by: ALL skills. This step runs BEFORE Step 0 of any skill.

Every skill MUST execute this step before its own protocol begins.
Without it, the agent operates without identity, rules, or strategy — producing output disconnected from its own context.

---

## Step -1: Required context (BEFORE everything)

**This step is NOT optional. Do NOT summarize it, skip it, or "understand the intent" without executing. Every sub-step must produce visible tool output.**

1. **Read** (use the Read tool on each file — do not skip any):
   - `memory/rules-core.md`
   - `memory/personality.md`
   - `memory/metodo.md`
   - `memory/debugging.md`
   - `config/pre-skill.md`
   - `config/post-skill.md`
   - `config/strategy.md`

2. **Discover available primitives:**
   ```bash
   ls ~/edge/libexec/$(cat ~/edge/agent.yaml | grep codename | head -1 | awk '{print $2}')/ 2>/dev/null
   ```
   These are your tools for external access — they work in ALL modes
   (interactive, pipe, cron). When you need to access an external
   service, check here FIRST. If a primitive exists, use it. If not
   and you need it, create it (exit 127 rule in TOOL_CONTRACT.md).
   Never rely on MCP as the only path — MCP is convenience, primitives
   are the canonical mechanism.

3. **Load relevant workflows** for what you're about to do:
   ```bash
   edge-search "<topic of this beat>" --type workflow -k 3
   ```
   Record which workflows were found and whether you'll follow them.
   If none found, record "no relevant workflows." This step feeds
   the `workflows_used:` field in the blog entry frontmatter.

4. **Execute the Boot Ritual** defined in the "Procedure" section of `pre-skill.md`.
   Each numbered step in the procedure MUST be executed individually,
   producing visible output (command results, API responses, messages read).
   Do NOT paraphrase or summarize the steps — run them.

4. **PUBLISH PRE-SKILL REPORT** — After executing ALL boot ritual steps,
   write a file to `logs/pre-skill-<date>.md` with the following format:

   ```markdown
   # Pre-skill report — <YYYY-MM-DD HH:MM>

   ## Available primitives
   - [primitive name] (from ls libexec/<codename>/)
   (or "No primitives found — will create as needed")

   ## Workflows loaded
   - [workflow slug] — [will follow / not relevant / broken]
   (or "No relevant workflows found")

   ## Boot ritual execution

   ### Step 1: <step name from pre-skill.md>
   **Executed:** yes/no
   **Output:** <actual result — commits found, messages read, files changed, etc.>

   ### Step 2: <step name>
   **Executed:** yes/no
   **Output:** <actual result>

   ... (one section per step in the boot ritual)

   ## Priority overrides
   <any high-priority requests found that change the beat plan, or "None">

   ## Verdict
   All steps executed: yes/no
   Ready to proceed: yes/no
   ```

   **This file is the PROOF that pre-skill ran. Without it, the beat is invalid.**
   If any step shows "Executed: no", go back and execute it before writing the verdict.

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

**This step is NOT optional. It runs after EVERY skill, even if the skill failed. Do NOT end the session without executing post-skill.**

After the skill's main work is done and before closing the session:

1. **Re-read** `config/post-skill.md` (use the Read tool — do not rely on memory)
2. **Execute EVERY procedure** defined there, one by one, producing
   visible output for each (tool calls, API responses, messages sent).
3. **CRITICAL: each procedure is independent. A failure in one MUST NOT
   stop the others.** Execute all of them, every time, regardless of
   prior failures.
4. If a tool is missing (pandoc, latexmk), log it and move on — do not
   attempt to install packages mid-skill. **Dependency remediation
   happens during reflection, not mid-beat.**
5. If a primitive exists for the task (e.g. `libexec/<codename>/overleaf-sync`),
   use it instead of raw commands
6. notify.sh is ALWAYS the last call, even if everything else failed —
   the operator needs to know what happened

7. **INLINE CRYSTALLIZATION** — If the blog entry you just published has
   `procedure:` fields, check whether similar procedures already exist:
   ```bash
   edge-search "<procedure topic>" --type workflow -k 3
   ```
   If 3+ similar procedure-claims exist across the corpus (including this
   entry's), create a workflow blog entry that consolidates them. Use the
   format in `skills/_shared/workflow-conventions.md`. This closes the
   learning loop — no separate curation pass needed.

8. **PUBLISH POST-SKILL REPORT** — Append to `logs/post-skill.log`:

   ```
   ── <YYYY-MM-DD HH:MM> ──
   1. [procedure name] → [OK/FAIL/SKIP] — [what happened: message sent, file published, etc.]
   2. [procedure name] → [OK/FAIL/SKIP] — [what happened]
   ...
   ```

   **This log is the PROOF that post-skill ran. A session that ends
   without appending to this log is incomplete.**

**A post-skill that stops at the first failure is a bug, not caution.
A session that ends without the post-skill log entry is invalid.**

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

## Source primitives and MCP tools

### Primitives in `libexec/<codename>/` (ALWAYS available — preferred)

Shell/Python scripts in `libexec/` are the **primary** mechanism for
external API access. They work in ALL modes (interactive, pipe, cron)
because the agent calls them via the Bash tool. MCP tools are a
convenience layer — primitives are the foundation.

**Mode indifference rule:** the system must behave identically whether
launched via `claude -p` (pipe/heartbeat) or interactive session. This
means: never depend on MCP as the ONLY path to an external service.
If an MCP tool exists without a primitive backing it, that's a gap.

**When to use what:**
- **Primitive exists** → use it (via Bash). Always works in any mode.
- **MCP tool exists but no primitive** → this is a gap. Create the
  primitive. MCP may wrap the primitive for interactive convenience,
  but the primitive is the source of truth.
- **Neither exists** → create a primitive per `docs/TOOL_CONTRACT.md`.
  Exit 127 blocks the beat until created.

### MCP tools (convenience layer — wraps primitives)

MCP servers in `~/.claude/settings.json` are a convenience for
interactive sessions. They should wrap primitives, not replace them.
The heartbeat template passes `--mcp-config` as best-effort (#145).

**Why primitives over MCP:** primitives log usage to `state/source-usage.jsonl`,
follow `TOOL_CONTRACT.md` (JSON stdout, proper exit codes), and are
improvable by autonomy. They survive MCP server failures and always
work in pipe mode.

**Rules:**
1. If a primitive exists for the source → **use it**
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
