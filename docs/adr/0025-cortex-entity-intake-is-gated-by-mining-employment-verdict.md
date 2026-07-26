# Cortex Entity intake is gated by the mining employment verdict

## Status

Accepted (2026-07-26). Operator + turing product decision; implemented as `tools/emprego.py`.

## Context

Communities and Graphiti `:Entity` nodes were built from raw session dialogue
(`sweep.graphiti_ingest` on human+edge `clean_body`). That bypassed Mineração's
employment judgment (`sessao.racionalizada.stitch.attribution.activity_relevant`).

Live consequence (roberto): mega-clusters mixing real domain work with addresses,
CNPJs, toy examples, and agent-meta name soup. Glossary already said Atividade /
employment only; code violated it.

## Decision

1. **Porteiro:** only material accepted as **mentee employment** may enter Cortex
   Tier-1 (`:Entity` / communities via extraction).
2. **Verdict source:** `activity_relevant is True` on the current
   `sessao.racionalizada` (supersedes chain). No second judgment at consolidate.
3. **Intake body:** deterministic employment digest (FINALIDADE / EXECUCAO /
   RESULTADO / … / CENAS) — never raw dialogue, never `organizacional.enderecos`.
4. **`sweep.execute`:** Tier-0 only (episode events + cursors). Raw Graphiti
   dialogue ingest is deleted.
5. **Assemble tooth:** residual `session-*` Episodic names block wake
   (`CODE_EMPLOYMENT`) until `tools/emprego.py --migrate`.

## Consequences

- The session Entity tier becomes **rebuildable from the log**
  (`reset_bypass` + `project`) — closes the ADR-0006 gap the old ingest admitted.
- Graphs go **sparse-and-correct** until rationalization backlog drains (accepted).
- Communities code unchanged: after migration, all Entity = accepted set.
- Migration preserves curated entities (`parceiro` / `curated_cluster`).

## Rejected alternatives

- **Voz-rail-only cortex** — too narrow for domain maps (emprego is Atividade).
- **Filter at communities.consolidate** — second judgment; wrong seam.
- **Pretty cluster names only** — treats symptom, not intake.
