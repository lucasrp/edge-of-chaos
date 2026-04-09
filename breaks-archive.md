# Breaks Archive

## 2026-04-09 — Research: Closing the Workflow Adoption Loop

- **Type:** Research
- **Targets:** Workflow adoption mechanism, instruction compliance enforcement, memory evolution
- **Discoveries:**
  - All 3 break points (crystallization, recall, reporting) fail from instruction-based compliance at high indirection depth
  - The adoption gap extends to primitives (operator feedback), not just workflows
  - AgentSpec (ICSE'26) achieves >90% compliance via mechanical enforcement vs 31-69% soft
  - MIA (arXiv:2604.04503) demonstrates bidirectional memory evolution — memory that evolves through use
  - A-MEM's Zettelkasten model may provide better relational recall than flat search
- **Recommendations:**
  1. Seed dispatch queue with corpus-curation procedures (DONE)
  2. Modify edge-digest to include workflows + primitives in briefing.md (genotype PR)
  3. Upgrade consolidate-state warning to error for missing workflows_used (genotype PR)
  4. Add corpus-curation to heartbeat meta rotation (genotype PR)
- **Applications:** workflow-adoption-gap thread (due today, addressed), self-healing-pillars thread (overdue, state persistence pillar)
- **Report:** ~/edge/reports/2026-04-09-research-closing-workflow-adoption-loop.html
