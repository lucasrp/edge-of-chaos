---
title: "workflow: Exa neural search pra mapear landscape de projetos similares"
date: 2026-03-24
tags: [workflow, exa, pesquisa, landscape, fontes]
keywords: [exa, neural search, landscape, github, similar projects, competitive analysis, content api]
claims:
  - "Exa neural search com includeDomains github.com traz repos similares com boa precisao"
  - "Exa contents API com maxCharacters 2000 traz resumo util sem estourar custo"
  - "Pipeline search → contents em 2 chamadas cobre landscape de um tema"
secrets: [exa.env]
cost_estimate: "~$0.02-0.05 (2 chamadas API)"
---

## Trigger
Preciso entender quem esta fazendo coisas parecidas — repos, artigos, frameworks no mesmo espaco.

## Passos
1. Search neural amplo (sem filtro de dominio):
   ```bash
   curl -X POST "https://api.exa.ai/search" \
     -H "x-api-key: $EXA_API_KEY" \
     -d '{"query": "descricao do que busco", "type": "neural", "numResults": 10, "startPublishedDate": "2026-01-01T00:00:00.000Z"}'
   ```
2. Search focado em GitHub:
   ```bash
   # Mesmo endpoint, com includeDomains
   -d '{"query": "termos", "includeDomains": ["github.com"], "numResults": 10}'
   ```
3. Pegar conteudo dos mais relevantes:
   ```bash
   curl -X POST "https://api.exa.ai/contents" \
     -H "x-api-key: $EXA_API_KEY" \
     -d '{"ids": ["url1", "url2"], "text": {"maxCharacters": 2000}}'
   ```
4. Sintetizar findings no relatorio

## Secrets
- `exa.env` — API key Exa

## Quando funciona
Mapeamento de landscape, competitive analysis, busca de projetos similares.
Neural search entende intencao melhor que keyword.

## Quando falha
- Busca de tweets especificos (Exa nao indexa X/Twitter bem)
- Conteudo muito recente (<24h) pode nao estar indexado
- Paywall forte (Medium parcialmente, sites enterprise)

## Custo
~$0.01/search + ~$0.01/contents call. Muito barato.
