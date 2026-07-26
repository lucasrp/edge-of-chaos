# Documentation (en-US default)

House language for **public and operator docs** is **English (en-US)**.

| Area | Notes |
|------|--------|
| Root `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRACT.md` | English entry surface |
| `docs/adr/` | Architecture Decision Records (prefer English for new ADRs) |
| `docs/specs/` | Product / install specs |
| Older paths (`protocolo-*.md`, `contrato-*.md`, mixed PT prose) | **Migration in progress** — do not expand PT surface; new text in en-US |

## Start here

1. [../README.md](../README.md) — product + first-run  
2. [specs/onboarding-first-run.md](specs/onboarding-first-run.md) — first-run contract  
3. [../CONTRACT.md](../CONTRACT.md) — product contract  
4. [adr/](adr/) — decisions  

## Language policy (short)

- **Genotype docs & defaults:** en-US.  
- **Phenotype `language:`:** per install (onboarding emits `en` unless the operator sets otherwise).  
- **Code comments / identifiers:** English; domain terms from the glossary may stay (Voz, Atividade, …) when they are product nouns.  
- **Gradual migration:** translate or replace PT docs when you touch them; no big-bang rewrite required.
