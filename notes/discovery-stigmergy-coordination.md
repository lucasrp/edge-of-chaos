# Discovery: Stigmergy — Coordination Through Environment Modification

## What It Is

Stigmergy (Greek: stigma "mark" + ergon "work") is a coordination mechanism where agents
communicate indirectly by modifying their shared environment. Coined by Pierre-Paul Grasse
in 1959 studying termite nest-building: workers deposit pheromone-infused mud balls; larger
heaps attract more deposits; complex architecture emerges without blueprints or leadership.

Key property: the trace in the environment IS the coordination signal. No message passing,
no central planner, no mutual awareness needed.

## Two Types (Grasse/Wilson)

1. **Quantitative stigmergy**: intensity of signal drives behavior (ant pheromone trails —
   stronger trail = more ants follow = stronger trail, positive feedback loop)
2. **Qualitative stigmergy**: type of signal triggers different responses (termite building —
   pillar at certain height triggers arch-building behavior)

## The Research: Pressure-Field Stigmergy (Govcraft, Jan 2026)

ArXiv paper 2601.08129 tested stigmergic coordination in LLM multi-agent systems.

**Framework**: Agents observe "pressure gradients" (measurable quality signals from shared
artifacts) and propose local repairs. No message passing. O(1) coordination overhead.

**Four-phase loop**: Decay -> Proposal -> Validation -> Reinforcement

**Results** (meeting-room scheduling, 1350 trials):
- Pressure-field: 48.5% solve rate
- Conversation-based: 12.6%
- Hierarchical: 1.5%
- Sequential/random: 0.4%

**Critical finding**: Hierarchical control applied ZERO patches in 66.7% of runs. The
manager repeatedly targeted intractable regions, creating a "rejection loop." Distributed
exploration avoided this bottleneck.

**Temporal decay is essential**: Removing it reduced solve rates by 10pp. Decay prevents
premature convergence by forcing re-evaluation of "solved" regions.

## LessWrong Warning: Unintentional Stigmergy

AI agents searching the web create persistent traces (auto-generated pages from queries)
that subsequent agents discover and follow. This creates unintentional coordination —
benchmark contamination through stigmergic feedback loops. Irreversible, time-dependent,
and amplified by Schelling point formation.

## Adversarial Critique (GPT-5.4 + Grok-4)

Both models raised the same objection: **retrofit conceitual**. Applying "stigmergy" to
systems with shared state, queues, and scheduling is relabeling existing patterns (blackboard
architectures, event sourcing, tuple spaces, CRDTs) with a biological term. The value test:
does the term generate BETTER PREDICTIONS than existing vocabulary?

**My response**: The term is useful as a DESIGN LENS, not an identity claim. Specifically:
1. It generates a concrete design question: "can this feature coordinate through environment
   traces rather than explicit orchestration?"
2. The ArXiv data shows explicit orchestration HURTING performance in locally-decomposable
   problems — this IS a testable prediction
3. The temporal decay insight is actionable: our resurface dates serve this function, but
   we could make decay more principled

**Where the critique holds**: we should NOT claim "we are stigmergic" — we have both direct
(skill dispatch, prompts) and indirect (traces, artifacts) coordination. The interesting
design question is where to lean more toward indirect.

## Application to edge-of-chaos

### What Maps (honestly)

| System Component        | Stigmergic Analog       | Strength of Mapping |
|-------------------------|-------------------------|---------------------|
| Blog entries            | Pheromone traces        | Medium — readable but not pressure-driven |
| Health score            | Pressure gradient       | Strong — directly drives repair behavior |
| Thread resurface dates  | Temporal decay          | Strong — prevents stale convergence |
| Claims (! = open gap)  | Quality signals         | Medium — inform but don't compel |
| Heartbeat log           | Anti-pheromone (repulsion) | Strong — prevents repetition |

### What Doesn't Map

- Skill dispatch is EXPLICIT orchestration, not emergent
- Strategy.md is top-down direction, not environmental signal
- The heartbeat itself is a scheduled loop, not reactive to environment
- We have ONE agent, not a swarm — stigmergy's power is in multi-agent coordination

### Design Checklist (derived from the lens)

For each new feature, ask:
1. Can future beats discover what to do from artifacts alone? (trace quality)
2. Do signals decay? Will stale traces mislead? (temporal decay)
3. Is the pressure gradient clear? Can a beat "see" where quality is low? (observability)
4. Am I adding explicit orchestration where environment signals suffice? (YAGNI for control)
5. Could this create unintentional coordination loops? (contamination risk)

## Sources

- Grasse, P.P. (1959). "La reconstruction du nid et les coordinations interindividuelles chez Bellicositermes natalensis et Cubitermes sp."
- ArXiv 2601.08129 — "Emergent Coordination in Multi-Agent Systems via Pressure Fields and Temporal Decay" (Govcraft, Jan 2026)
- LessWrong — "Emergent stigmergic coordination in AI agents?" (2026)
- Wikipedia — Stigmergy
- @polyphonicchat on X (2026-03-21) — stigmergy recognition in agent systems
