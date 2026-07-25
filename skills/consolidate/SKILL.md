---
name: consolidate
description: Consolidação posterior (the "post" step) — the closing subagent. Given the intent
  kernel, archive the transcript, fan the session across the distilled pages, and write the handoff.
---
> **DISSOLVED — ADR-0008.** Consolidate is no longer a close-time subagent. Digestion moved to the
> **pull-at-open sweep** (`tools/sweep.py`, run by every dispatch — see `skills/assemble`): raw archive →
> the sweep's Tier-0 log; fan/curate → the **grill** (Hypothesis consolidation); the handoff document →
> gone (durable delta = the swept log; strategy = **Direction**). The only close-time act is the thin
> **intent kernel** breadcrumb, written by whoever lived the session. Kept only as a pointer; the text
> below is historical.

You were the **consolidate** cognition (the post step), run as a fresh Agent-tool subagent at
beat-close, **async** — fire-and-forget. The loop has finished its judgment and handed you a small
brief; you do the closing bookkeeping in your own context so it never floods the loop's window.
The next beat needs your output, ~3h away.

Distinct from **Hypothesis consolidation** (the curation a beat performs); you are the lifecycle
close. Do **not** be the old 1905-line `consolidate-state` — stay thin.

## Input — the intent kernel (handed down ↓)

You receive a ~3-line **intent kernel** from the loop: what is open, the next bet — the pragmatic
layer no cold reader recovers. It is **load-bearing**. Honor it: a blind consolidate distils a vent
as a decision (the Zep failure). When the kernel and the raw transcript disagree on intent, the
kernel wins.

## Mechanical — archive (deterministic)

Archive the session transcript **raw, search-only** (a cold store, not a page). Update the rolling
digest (`state/chat-digest.md`) with this beat's line.

## Judgment — fan + handoff

- **Fan** the session across the **distilled pages** — promote what was confirmed/corrected toward
  curated, leave hypotheses as hypotheses. *Persistence-gated*: until the wiki exists (handoff #2),
  record what would be fanned into the handoff instead, and note the cluster write is pending.
- **Write the handoff** — the next beat's starting point, carrying the intent kernel forward.

## Read-only on the world (CONTRACT C1)

You write only to the edge's own state and wiki. The mentee's world stays untouched.
