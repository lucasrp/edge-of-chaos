# Install identity — who am I AND where I read — resolves at one fail-loud seam; the genotype carries no install literals

Everything install-specific (the group, the transcript store, any display name) resolves through
**one seam, `tools/_identity.py`**, in **fail-loud** mode: absent identity raises or runs
explicitly anonymous — **never a silent default, never a baked-in literal**. The transcript store
joins the identity contract: it derives from the running install's `$HOME` (or `EDGE_PROJECT_DIR`
explicitly), and **a store directory that does not exist is an error, not "nothing new."** The
grep-gate — zero install-identity literals in `tools/` — becomes the seam's conformance test.

## Status

proposed (2026-06-10; Voz ratifies — "next steps" session). Inscribes the Direction steers from
`the-genotype-still-wears-the-devs-name` (proposed since 06-08) as architecture. Pairs with
ADR-0016 (pre-dispatch enforcement — the other half of the same incident).

## Context

- **The disease bit a third time, in a new face, on a live install.** `sweep.py:29` defaults the
  transcript store to `~/.claude/projects/-home-vboxuser` — the **developer's host path** baked
  into the genotype. On roberto (deployed 06-09, 294 session files in `-home-roberto*`), the sweep
  scans a nonexistent directory and reports **"nothing new (cursor up to date)"** — a silent
  success. Result: cursor `{}` since deploy, **zero episodes ever extracted**, no Direction/wiki
  projections on disk. Roberto produced two Artefatos briefed from an empty memory, and nothing
  ever errored.
- The earlier faces of the same disease: the `EDGE_GROUP` → `"edge-next"` default (sweep), the
  `or "edge"` display default (wiki_render), the stale `lucasrp/edge-of-chaos` source key (now
  also found as a placeholder in roberto's agent.yaml).
- The seam exists but is **shallow**: of `_identity.group()`'s 7 callers, 3 inline their own
  resolution (`briefing.py:419`, `recall.py:115`, `wiki_render.py:50-52`), and `sweep.py:34`
  caches the group at **import time** (stale-copy risk). The fail-loud rule the glossary ratified
  ("an install that has not declared who it is must not write as anyone") lives **nowhere in code**
  — every caller silently accepts `None` and degrades.
- Three installs now share one graph split by `group_id`; fail-open identity is multi-tenant
  contamination risk, not hygiene.

## Considered options

- **Fix each literal where it lies** (patch sweep.py's path, drop the group default, leave the
  callers' inline resolutions). Rejected: the next literal lands the same way — the disease is
  the *absence of a deep seam*, not any one literal. Per-caller fixes also leave the fail-loud
  rule unenforceable (each caller decides its own degrade).
- **Keep silent degrade for reads, fail loud only for writes.** Rejected by tonight's evidence:
  the read-side silent degrade ("nothing new") is exactly what hid a 294-session amnesia for two
  days. Reads that orient the edge are load-bearing; lying quietly is worse than stopping.
- **Chosen: one fail-loud seam.** `_identity` owns the whole install-identity contract; callers
  make one call and carry no fallback of their own.

## Decision

- `_identity.group(require=True)` — the ONE resolution (env → agent.yaml), raising
  `IdentityError` when absent; `require=False` callers get `None` and must label their degrade
  honestly. No caller re-implements the precedence; no module caches the result at import time.
- `_identity.project_dir()` joins the seam — `EDGE_PROJECT_DIR` env, else derived from the
  running `$HOME` (`-home-<user>` per the Claude store convention); **raises when the resolved
  directory does not exist**. "Nothing new" is reserved for a real store with no new lines.
- **No install literals in `tools/`**: no host paths, no group defaults, no display-name
  fallbacks. The grep-gate runs as a test (`test_identity_blinding`) and as the pre-propagate
  acceptance check in the genotype→clone→PR→merge→propagate flow.
- The inline re-resolutions in `briefing.py`, `recall.py`, `wiki_render.py` are deleted;
  `sweep.py` resolves at call time.

## Consequences

- A fresh install that boots without declared identity **stops loudly at the first read or
  write** instead of producing plausible work from an empty or foreign state.
- Roberto needs a backfill after the fix deploys: one sweep over `-home-roberto*` digests the
  ~294-session backlog (cursor-guarded, resumable).
- `edge-apply` / provisioning must set or derive `EDGE_PROJECT_DIR` where the convention doesn't
  hold (the proxy-harness hosts write transcripts under the harness home).
- The identity seam becomes the natural home for any future tier (per-host overrides,
  multi-mentee groups) — one file to change.
