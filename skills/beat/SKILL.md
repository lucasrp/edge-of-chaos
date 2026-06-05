---
name: beat
description: The edge's work cycle, run as an agent — read the durable surfaces, choose one
  Worthwhile theme, and produce a single Artefato. v0 spine; stops at the consolidation seam.
---
The beat is the edge's work cycle, run **as an agent inside Claude Code** — not a deterministic
pipeline. You read what the edge knows, choose one thing worth saying, and publish it. One beat
produces **one Artefato**.

This is the **v0 spine**: read → produce. Consolidation into the wiki (growing clusters,
refining standing pages) and the attunement loop (Lint / grill-me / comment → Convergence) are
**out of scope** here — see the seam at the end.

## Read the durable surfaces (in full)

The edge's own knowledge is read whole, not deltized. Read what exists:
- `CONTEXT.md` — the glossary. Speak in these terms; do not redefine them.
- `agent.yaml` — your mission, voice, and the operator's direction.
- `memory/operator-idiom.md` — the operator's **Idiom**, if present. Frame everything in their
  words and meanings.
- `state/chat-digest.md` and `briefing.md` — what recent beats did and any open pressure.
- `blog/entries/` — prior Artefatos. Read them so you do not repeat one; build on them.

**Enrichment, never a precondition.** If source keys are configured (Mundo / Atividade / Voz),
glance at what is new since the last beat to orient — but the beat does not depend on a delta.
When nothing is new, work from the durable surfaces alone: there is always a cluster to deepen,
a cross-reference to draw, an implication to surface.

## Choose one Worthwhile theme

Pick a single theme that is **deep domain insight applied to the mentee's live work** — the
intersection. Domain alone is generic; the mentee's work alone is shallow. Highest value is
often the decision they have not yet made. One theme per beat.

## Produce one Artefato

Write a focused artifact on that theme:
- a 2–3 sentence executive summary under a `## Executive summary` heading;
- 2–3 substantive sections (`## `), concrete, saying something the mentee did not already know;
- name what remains uncertain as explicit open questions.

Frame it in the operator's Idiom. Avoid filler and generic methodology.

**Publish** it to `blog/entries/<slug>.html` — a self-contained HTML document
(`<title>`, an `<h1>`, a `<p class="meta">` with the date, and `<link rel="stylesheet"
href="/static/style.css">`), matching the existing entries. This is the transient Artefato (it
cools and is prunable); the durable knowledge it distills is consolidated later, not here.

## Self-review once

Before publishing, adversarially critique your own draft a single time: is it **Worthwhile**
(deep *and* applied), honest about what it does not know, free of filler? Revise, then publish.
(An independent adversarial judge — a different model via the `review` router — is deferred;
this self-review stands in for it. See ADR-0003.)

## Stay read-only on the world (CONTRACT C1)

The mentee's work — every source key — is **read-only**. Write only to the edge's own artifacts
and state (`blog/entries/`, `state/`). Acting in the world is never an autonomous beat decision.

## Consolidation seam — STOP here (handoff #2)

Do **not** update knowledge clusters or standing pages, and do **not** run grill-me, in this
beat. Consolidation and the attunement loop are designed in handoff #2. End the beat once the
Artefato is published.
