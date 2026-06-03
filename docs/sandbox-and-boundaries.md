# Sandbox e limites de atuação — o que o edge pode fazer

> Organização copiada do agentops (agent lab + Judge + disciplina de deploy).

## Sandbox — rodar isolado antes de produção
O edge roda primeiro num sandbox isolado:
- EDGE_HOME próprio, usuário temp, keys throwaway (cap pequeno), subdomínio separado.
- Avaliado pelo **Judge** contra **casos de teste** + **critérios** → por critério:
  satisfeito (sim/não) + confiança + reasoning.
- O **mesmo Judge** serve os dois contextos: produção (julga o artefato nos gates
  **forma + adversarial**) e sandbox (julga o agente nos casos de teste).
- Teardown documentado (o usuário temp é removível).

## Autônomo (no próprio substrato)
- Produz artefatos (blog, relatórios) e publica.
- Atualiza memória, threads, state e o rolling digest no próprio EDGE_HOME.
- Propõe mudanças: PRDs, issues, planos de ciclo.
- Roda o loop (heartbeat → 6 fases).

## Passa por aprovação / pelo loop
- **Genótipo**: loop issue → clone → PR → merge → close.
- **Deploy**: issue → branch → PR → merge (prod via processo).
- **Estado do operador ou externo**: aprovação explícita do operador.
- **Mutação via credencial**: aprovação explícita.

## Disciplina
- Todo código via `/pocock-tdd` (red → green → refactor, vertical slices).
- Ler o glossário antes do trabalho: `CONTEXT-MAP.md` → `CONTEXT.md` → ADRs.
- Mentor: contribui e recomenda; o trabalho do mentee é do mentee.
