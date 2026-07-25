# The acquisition gate is an auditor with a positive-control, not a compliance blocker; it escalates to blocking only on logged evidence

## Context

Every grounding gate today sits on the lossy publication side; **acquisition** — was the search well
done? were the declared paid legs (x/exa) actually swept? — had no gate. A prior attempt at an
enforcement gate on acquisition became "the monster": it optimized compliance, produced
chokepoint→bypass→chokepoint (the #248 spiral), and fossilized rather than corrected. The operator's
Voz (`fragmentos-prosa-fiduciária`): *método livre, registro contratado* — auditability that
back-pressures acquisition because what is measured gets managed; and the loop closes *through* the
operator, not *over* them.

## Decision

Module 1 · Aquisição owns `grounding.floor(manifest)`; Julgamento (Close) **calls** it, never
re-implements it (or the format leak returns on the acquisition side).

The gate is an **auditor**: it records and surfaces the grounding manifest + yield (into the log, the
briefing, the grill's agenda) and **blocks nothing on thinness**. The single enforcement exception is a
**positive-control** on a "zero results" claim from a declared paid leg — the *seca falsa*, a
false-negative from a broken instrument (the class an after-the-fact auditor cannot catch).

Escalation to a hard publish-block is a **future decision made on logged evidence** — pre-registered so
the log already captures the deciding fields: the grill repeatedly catching thin acquisition, or a
*seca falsa* passing the positive-control. Never on vibe. It is implemented today as the knob-driven
`harvest.close_floor` (`EDGE_GROUNDING_FLOOR`: 0 off / **1 observe = auditor** / 2 gate).

## Consequences

- Método livre on depth; enforcement only on the canary — this is what avoids the monster
  (compliance-optimization → bypass).
- The auditor→blocker move is an evidence-decided ratchet: logged, reversible, never silent.
- The loop closes through the operator — the grill sees thin acquisition and pushes; the gate does not
  refuse.
