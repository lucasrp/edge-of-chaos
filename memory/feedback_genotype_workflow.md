---
name: genotype changes go through clone → branch → push → propagate
description: For any change to ~/edge/ genotype paths (tools/, skills/, search/, blog/app.py, bin/, config/*.tpl, memory core, SURVIVAL_POLICY), never edit the live ~/edge/ directory. Clone to ~/work/<branch>/, code there, commit, push to GitHub, then propagate via git pull on each fleet member.
type: feedback
originSessionId: 710c0e56-d64b-456a-b714-d97e861a9753
---
For any genotype change in `~/edge/`: clone to `~/work/<branch>/`, code/commit/push there, then propagate via `git pull --rebase` on each fleet instance. Never edit the live `~/edge/` directory in place.

**Why:** The user has had sensitive data from the live instance leak into git via in-place edits. The live `~/edge/` contains epigenetic state (logs, secrets, drafts, search DB) that must never enter the genotype repo. Working in a clone keeps the boundary clean. The user has corrected me on this twice — first time was the #226 telemetry work ("vc tem que dar clone e trabalhar no projeto clonado").

**How to apply:**
- Genotype paths (per CLAUDE.md): `skills/`, `tools/`, `search/*.py`, `blog/app.py`, `blog/*.sh`, `bin/`, `config/*.tpl`, `memory/personality.md`, `memory/rules-core.md`, `memory/metodo.md`, `SURVIVAL_POLICY.md`
- Clone target: `~/work/<branch-or-issue-number>/`
- After push, fleet propagation is TWO steps on each agent (not one):
  1. `ssh <agent> 'cd ~/edge && git pull --rebase --autostash'` — pulls genotype source
  2. `ssh <agent> 'python3 ~/edge/tools/edge-apply --skip-venv'` — syncs `~/edge/skills/` → `~/.claude/skills/<prefix>-<name>/` with the host's prefix (`ed-`/`dru-`/`roberto-`/`bracis-`/`gauss-`). Without step 2 Claude Code still loads the OLD skill at runtime. Caught by MD5 diff on 2026-04-18 after shipping heartbeat Step 1a0.
- `edge-apply` is idempotent; `--skip-venv` avoids the slow search-venv rebuild when only skills/code changed.
- `gauss` has chronic drift (100+ local commits). Use `git pull --rebase -X theirs --autostash` there so gauss's own `memory/debugging.md` wins on conflict — genotype change still lands.
- Phenotype/epigenetic edits (`agent.yaml`, `state/`, `blog/entries/`, `logs/`, `threads/`, `reports/`) can be done in place — they're per-instance and gitignored or not in genotype.
- The test: "If I change this, does it affect other instances?" YES → genotype → clone first.
