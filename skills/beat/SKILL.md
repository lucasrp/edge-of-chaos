---
name: beat
description: The beat propriamente dito — a PURE round-robin scheduler over the producer-skills.
  Carries only rotation state (whose turn); theme-choice and production belong to the skill, the
  close to the shared pipeline.
---
You are the **beat loop** — the scheduler of the dispatch. You carry **only rotation state**: whose
turn it is. You do **no** judgment (ADR-0012 *evacuates* judgment from the beat — amends ADR-0004,
whose loop chose-the-theme-and-produced; now the skill does both). Theme-choice and production belong
to the **producer-skill**, not the beat. The close belongs to the **shared pipeline**
(`skills/_shared/pipeline.md`) at the skill's **exit**, not to the beat. This is the v0 spine: rotate
→ hand off to the skill. No new `claude -p` — the producer-skill runs inside this one dispatch
(ADR-0003).

## 1. Rotate — strict round-robin

The producer roster is `["report", "map", "plan"]`. Advance the persisted cursor **strictly** and
serve whose turn it is — successive beats yield `report`, `map`, `plan`, `report`, … (it wraps). The
moment **does not jump the queue**: there is no judgment here, only the cursor. (`agent.yaml` already
declares `heartbeat.skill_selection: round-robin`; this roster is what that selection rotates.)

    tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import _beat; \
      print(_beat.next_producer(['report','map','plan'], 'state/beat/cursor.json'))"

Breadth comes from the rotation; **aim comes from Direction** — but the aim is exercised *inside* the
skill (step 2), never here.

## 2. Hand off to the producer-skill — it judges, it produces

Invoke the skill whose turn it is (`skills/<producer>`). **Pointing happens inside the skill**: when
its turn comes it picks the most Worthwhile theme against **Direction + the delta**, splits it into
leads, gathers evidence, and produces **one Artefato** in its form. The beat does not pick the theme
and does not produce — it only said whose turn it is. (A small theme reads documents directly; real
depth fans explorers per lead — but that is the skill's call, not the beat's.)

## 3. Close — delegated to the shared pipeline at the skill's exit

The close is **not the beat's job**. Every producer-skill funnels through the **one shared pipeline**
(`skills/_shared/pipeline.md`): pre-dispatch (assemble + delta) → producer-loop (the scaffold) →
**close** (the two blind review gates + the atomic publisher, which emits the mandatory
`intent.kernel` so CONTRACT C3 holds). The close runs at the skill's **exit** — so a standalone
`/ed-report` observes the same gates (honors ADR-0008). The bounce-bound lives in the protocol, never
in the producer's discretion. Do not run a close here; do not archive or fan by hand (digestion is
the pull-at-open **sweep** every dispatch runs at entry).

## Read-only (CONTRACT C1)

The mentee's world is read-only. The edge writes only its own Artefato and state (the rotation
cursor included). Acting in the world is never an autonomous beat decision.
