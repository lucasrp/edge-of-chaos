# Discoveries — Registry

---

## [2026-03-27] Three Pillars of Self-Healing Agents — Diagnosis, Recovery, Persistence [PENDING]

**Type:** concept
**Problem:** Self-healing agents need to solve three orthogonal problems; edge-of-chaos touches all three but hasn't specialized in any
**What it is:** Three independent projects each pushed one axis of self-healing further: VIGIL (affective appraisal for diagnosis), openclaw-self-healing (tiered watchdog for recovery), TEMM1E (lambda-memories for state persistence). Any production self-healing system needs all three.
**Application:** edge-of-chaos can learn from each: (1) formalize diagnostic signals beyond mechanical health scoring (VIGIL's Roses/Buds/Thorns), (2) add time-series observability to repair cycles (openclaw's Prometheus metrics), (3) implement corpus decay with fidelity layers for aging content (TEMM1E's lambda-memories)
**To start:** Start with the lowest-hanging fruit — add a crash/repair counter with time-decay (openclaw pattern) to edge-repair.sh
**Effort:** medium
**Notes:** `~/edge/notes/discovery-self-healing-agent-pillars.md`
