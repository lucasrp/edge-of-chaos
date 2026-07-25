# Sandbox do edge — instalar, rodar, ver

> Um lugar (usuário temp numa VPS) onde instalo o edge, rodo, e vejo o que fiz.
> Infra mínima.

## O que é
Um host descartável onde:
- instalo o edge com `edge-render` + `edge-apply` (a partir do `agent.yaml`),
- rodo o heartbeat,
- vejo o resultado: o blog no subdomínio, os artefatos, os logs.

## O que posso fazer nela
- Instalar, rodar, observar e iterar livremente — é descartável.
- Usar as keys throwaway (cap pequeno).

## Guardrails
- Usuário temp não-privilegiado; teardown removível.
- Keys throwaway capadas — dano limitado.
- Subdomínio separado (`sandbox.edgeofchaos.net`); produção segue intocada.
- Efeitos ficam dentro da sandbox.

## Fora da sandbox (passa por aprovação / pelo loop)
- Genótipo: loop issue → clone → PR → merge → close.
- Estado do operador ou externo: aprovação explícita.
- Mentor: contribui e recomenda; o trabalho do mentee é do mentee.
