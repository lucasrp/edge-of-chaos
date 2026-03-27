# Discoveries

## [2026-03-27] Stigmergy — Coordination Through Environment, Not Messages [PENDENTE]

**Tipo:** conceito
**Problema:** How to design agent coordination that scales without explicit orchestration overhead
**O que e:** Stigmergy is indirect coordination through environment modification (Grasse 1959, termites). Recent research (ArXiv 2601.08129, Jan 2026) shows pressure-field stigmergy outperforming hierarchical MAS coordination by 4x in LLM agents. Key mechanism: agents read quality signals from shared artifacts, propose local repairs, temporal decay prevents convergence.
**Aplicacao:** Design lens for edge-of-chaos — ask "can this coordinate through traces rather than explicit rules?" for each new feature. Health score = pressure gradient (strong mapping). Thread resurface = temporal decay (strong). Blog entries = pheromone traces (medium). Concrete: strengthen quality signals on threads, make decay more principled, watch for unintentional coordination loops.
**Para comecar:** Apply the 5-question design checklist (in notes) to the next feature or refactor
**Esforco:** baixo (lens, not implementation)
**Notas:** `~/edge/notes/discovery-stigmergy-coordination.md`
