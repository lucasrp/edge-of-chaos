# Discoveries

## [2026-03-27] Criticality Detection Toolkit — Measuring Edge of Chaos [PENDENTE]

**Tipo:** conceito
**Problema:** Open claim: "Whether edge-of-chaos system exhibits anything measurably like criticality." We use the name, but can we detect it?
**O que e:** 8+ disciplines independently converged on the same math for detecting criticality (ArXiv 2601.22389). The universal question: "how far do correlations extend?" At criticality, contraction factor approaches 1.0 — whether measured as Hurst exponent, DFA alpha, spectral radius, or branching ratio. Five metric families: correlation extent, compression analysis, Lyapunov exponents, power-law distributions, permutation entropy. Critical caveat: avalanche criticality and edge-of-chaos criticality are DISTINCT phenomena (AIP Chaos 2017).
**Aplicacao:** Our system produces measurable time series (health scores, beat themes, claims, repair events). Most practical first steps: (A) branching ratio on beats (sigma=follow-up items per beat, 1.0=critical), (B) compression of theme sequences (gzip, medium=EoC), (C) Hurst exponent on health scores. CRITICAL: null models required — these metrics are cheap to fake in systems with memory. Must compare against shuffled baselines.
**Para comecar:** Compute branching ratio from events.jsonl when we have 50+ beats. Build null model (shuffled sequence). Compare.
**Esforco:** medio (metrics are simple, rigorous validation is harder)
**Notas:** `~/edge/notes/discovery-criticality-detection-toolkit.md`

## [2026-03-27] Stigmergy — Coordination Through Environment, Not Messages [PENDENTE]

**Tipo:** conceito
**Problema:** How to design agent coordination that scales without explicit orchestration overhead
**O que e:** Stigmergy is indirect coordination through environment modification (Grasse 1959, termites). Recent research (ArXiv 2601.08129, Jan 2026) shows pressure-field stigmergy outperforming hierarchical MAS coordination by 4x in LLM agents. Key mechanism: agents read quality signals from shared artifacts, propose local repairs, temporal decay prevents convergence.
**Aplicacao:** Design lens for edge-of-chaos — ask "can this coordinate through traces rather than explicit rules?" for each new feature. Health score = pressure gradient (strong mapping). Thread resurface = temporal decay (strong). Blog entries = pheromone traces (medium). Concrete: strengthen quality signals on threads, make decay more principled, watch for unintentional coordination loops.
**Para comecar:** Apply the 5-question design checklist (in notes) to the next feature or refactor
**Esforco:** baixo (lens, not implementation)
**Notas:** `~/edge/notes/discovery-stigmergy-coordination.md`
