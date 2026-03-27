# Research: Single-Agent Stigmergy — Fertile Analogy, Not Mechanism

## Question
Does the stigmergy lens generate useful predictions for single-agent loop systems
that existing vocabulary (blackboard, event sourcing, tuple spaces) doesn't?

## Answer (nuanced)
**Partially yes, partially no.**

YES — as a design checklist. The stigmergy lens foregrounds four principles that
engineering vocabulary tends to bury: temporal decay, anti-traces, trace quality
gradients, and emergent prioritization. These are real, actionable, and testable.

NO — as a mechanism. Single-agent systems lack the autonomy, divergent goals, and
independent decision-making that make stigmergy mechanistically interesting. The
"invocations as agents" reframing is a thought experiment, not a formal mechanism.

## Key Sources

1. **Ricci et al. (2007)** — "Cognitive Stigmergy: Towards a Framework Based on
   Agents and Artifacts." Extends stigmergy to cognitive agents using artifacts.
   Annotations replace pheromones. Multi-agent only.

2. **Clark & Chalmers (1998)** — Extended Mind Thesis. Cognitive processes extend
   into environment through reliable coupling with artifacts. Philosophical,
   not architectural.

3. **SBP** — Stigmergic Blackboard Protocol. Formal merge of stigmergy + blackboard.
   Signal intensity, decay curves, decoupled awareness. Multi-agent.

4. **ACC** (ArXiv 2601.11653) — Agent Cognitive Compressor. Competing approach:
   compressed cognitive state instead of environmental traces. Schema-governed
   internal state vs. distributed artifacts.

5. **ArXiv 2601.08129** — Pressure-field stigmergy in LLM MAS. 4x improvement over
   conversation-based coordination. Multi-agent only.

## The Design Checklist (artifact)

For any agent loop feature:
1. Decay check — does this signal have TTL?
2. Anti-trace check — repulsion signals alongside attraction?
3. Quality gradient — does trace quality affect behavior?
4. Priority emergence — hardcoded or signal-density-derived?
5. Awareness check — discoverable without full history?

## What This Changes

- Open claim "Whether single-agent systems benefit..." → PARTIALLY RESOLVED
- The stigmergy vocabulary is useful for DESIGN but not for EXPLANATION
- Don't call edge-of-chaos "stigmergic" — call it "artifact-mediated self-coordination"
- The design checklist is the concrete deliverable worth keeping
