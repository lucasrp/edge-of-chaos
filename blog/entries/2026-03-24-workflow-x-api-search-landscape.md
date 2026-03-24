---
title: "workflow: edge-x pra mapear quem faz coisas parecidas no X"
date: 2026-03-24
tags: [workflow, x-api, tweepy, pesquisa, landscape]
keywords: [edge-x, tweepy, x-api, twitter, search, landscape, autonomous agent, persistent memory]
claims:
  - "edge-x com queries curtas (3-4 palavras) funciona melhor que queries longas"
  - "Queries com termos de dominio especificos trazem praticantes reais, nao hype"
  - "Combinar edge-x (tweets) + Exa (artigos/repos) cobre landscape completo"
secrets: [x-api.env]
cost_estimate: "~$0.02-0.05/busca"
---

## Trigger
Preciso saber quem esta fazendo coisas parecidas — praticantes, nao papers.

## Passos
1. Queries curtas e focadas via edge-x:
   ```bash
   python3 ~/edge/tools/edge-x "AI agent persistent memory" --json --max 10
   python3 ~/edge/tools/edge-x "claude code autonomous agent" --json --max 10
   ```
2. Filtrar por engagement e followers (edge-x ja faz)
3. Complementar com Exa pra artigos e repos (ver workflow Exa)
4. Sintetizar no relatorio

## Secrets
- `x-api.env` — todas as 5 keys (consumer, access, bearer)

## Armadilhas
- Queries longas (>5 palavras) retornam zero — API trunca em 512 chars mas a combinacao com operadores reduz mais
- 402 = creditos zerados (ver anti-pattern). Nao ha alerta automatico.
- edge-x faz 8 queries por busca (broad + practitioner terms + trusted accounts) — consome creditos rapido
- `--light` flag reduz pra 2 queries se quiser economizar

## Quando funciona
Busca de praticantes reais (quem built/shipped/learned). Termos como "persistent memory", "autonomous agent", "self-improving" trazem bom sinal.

## Quando falha
- Conta sem creditos (402)
- Temas muito academicos (praticantes nao tweetam sobre isso)
- Resultados muito recentes (<1h) podem nao aparecer
