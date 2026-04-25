---
name: genotype changes require full issue → clone → PR → merge → close loop
description: For any change to ~/edge/ genotype paths (tools/, skills/, search/, blog/app.py, blog/*.sh, bin/, config/*.tpl, hooks/, memory core, SURVIVAL_POLICY), the required 7-step flow is (1) open GitHub issue, (2) clone to ~/work/<issue-number>/, (3) branch/commit/push, (4) open PR referencing issue, (5) merge, (6) CLOSE the issue, (7) propagate via git pull + edge-apply. Never edit live ~/edge/ in place.
type: feedback
originSessionId: 710c0e56-d64b-456a-b714-d97e861a9753
---
For any genotype change, the required 7-step loop is:

1. **Open a GitHub issue** in `lucasrp/edge-of-chaos` describing the change (use `[genotype]` prefix when reporting a bug found during another beat).
2. **Clone** the repo to `~/work/<issue-number>/` — use the issue number, not the branch name, so workspace is traceable back to the ticket.
3. **Branch, commit, push** from the clone. Never edit live `~/edge/` in place.
4. **Open a PR** that references the issue (`Fixes #N` / `Closes #N` — gives GitHub automatic linking).
5. **Merge** the PR.
6. **Close the issue** explicitly. An open issue with merged code is an inconsistent state — close-issue is the completion gate, not an afterthought.
7. **Propagate** to every fleet member — two steps per agent, not one:
   - `ssh <agent> 'cd ~/edge && git pull --rebase --autostash'` — pulls genotype source
   - `ssh <agent> 'python3 ~/edge/tools/edge-apply --skip-venv'` — syncs `~/edge/skills/` → `~/.claude/skills/<prefix>-<name>/` with the host's prefix (`ed-`/`dru-`/`roberto-`/`bracis-`/`gauss-`). Without step 2 Claude Code still loads the OLD skill at runtime.

**Why:** Two compounding reasons.

First, the operator has had sensitive data from the live instance leak into git via in-place edits. The live `~/edge/` contains epigenetic state (logs, secrets, drafts, search DB) that must never enter the genotype repo. Working in a clone keeps the boundary clean.

Second, the operator has corrected this 8+ times across conversations (2026-04-09 → 2026-04-18). Soft workflow recall (crystallized twice: 2026-04-09, 2026-04-17) is saturated — this is the enforcement-ladder L1→L5 promotion pattern, worked example. The close-issue step was added explicitly on 2026-04-18 because open-issue-with-merged-code kept happening.

**How to apply:**
- Genotype paths (per CLAUDE.md and hooks/): `skills/`, `tools/`, `search/*.py`, `blog/app.py`, `blog/*.sh`, `bin/`, `config/*.tpl`, `hooks/*.sh`, `memory/personality.md`, `memory/rules-core.md`, `memory/metodo.md`, `SURVIVAL_POLICY.md`.
- `edge-apply` is idempotent; `--skip-venv` avoids the slow search-venv rebuild when only skills/code changed.
- Use the same pull command for every fleet host. If a host reports conflicts or local commits, stop and inspect instead of applying a host-specific merge strategy by default.
- Phenotype/epigenetic edits (`agent.yaml`, `state/`, `blog/entries/`, `logs/`, `threads/`, `reports/`) can be done in place — they're per-instance and gitignored or not in genotype.
- The test: "If I change this, does it affect other instances?" YES → genotype → full 7-step loop.
