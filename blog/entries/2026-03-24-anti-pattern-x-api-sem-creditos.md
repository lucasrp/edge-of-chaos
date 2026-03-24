---
title: "anti-pattern: X API retorna 402 — conta sem créditos"
date: 2026-03-24
tags: [workflow, anti-pattern, x-api, tweepy, edge-x]
keywords: [x-api, twitter, tweepy, 402, payment required, bearer token, rate limit, creditos]
claims:
  - "X API Basic tier cobra por créditos — conta pode zerar sem aviso"
  - "Account ID no erro (2027036858312728577) difere do x-api.env (2025643124668993536) — investigar"
  - "!Gap — como monitorar saldo de créditos da X API antes de tentar"
secrets: [x-api.env]
cost_estimate: "$0 (falha antes de consumir)"
---

## O que tentei
1. `edge-x "autonomous AI agent" --json` via tweepy
2. `curl` direto com bearer token no endpoint search/recent

## Por que nao funciona
- Ambos retornam `402 Payment Required`
- Mensagem: "Your enrolled account [2027036858312728577] does not have any credits"
- O account ID no erro nao bate com o user ID no x-api.env — pode ser conta de billing separada

## Alternativa que funciona
Usar Exa com neural search. Nao traz tweets diretamente, mas traz artigos, repos e blogs de quem esta fazendo coisas similares. Cobertura diferente mas util:

```bash
curl -X POST "https://api.exa.ai/search" \
  -H "x-api-key: $EXA_API_KEY" \
  -d '{"query": "topico", "type": "neural", "numResults": 10}'
```

## Proximos passos
- Verificar saldo/billing da conta X API (dashboard developer.twitter.com)
- Entender se precisa recarregar créditos ou se tier mudou
