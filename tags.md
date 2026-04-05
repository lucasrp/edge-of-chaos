# Vocabulário de Tags e Keywords

Esquema de metadados para reports, blog entries, notas e artefatos de memória.
Evolui com o tempo — adicionar termos conforme surgem, consolidar na /reflexao.

## Esquema

```yaml
tags: [tipo, dominio, conceito]     # 3-5, vocabulário controlado, pra FILTRAR
keywords: [tech, concept, ref, ...]  # 5-15, semi-livre, pra RETRIEVAL
```

**tags** = poucos, normalizados, respondem "que tipo? sobre qual projeto? qual tema?"
**keywords** = granulares, respondem "quais tecnologias? quais conceitos? quais referências?"

## Tags — Vocabulário Controlado

As próprias tags permanecem em ASCII (convenção de slug, igual a filenames
de blog entries — `reflexao`, não `reflexão`). As seções abaixo usam os
slugs canônicos; o texto explicativo usa acentuação normal.

### Tipo (herdado da skill que gerou)
pesquisa, reflexao, planejamento, descoberta, estrategia,
lazer, capacitacao, relatorio, retrospectiva, executar

### Domínio (projeto/área)
project, autonomia, blog, ralph

### Conceito (tema amplo)
multi-agente, prompt-engineering, calibracao, pipeline,
eval, applied-domain, observabilidade, ux, memoria

## Keywords — Vocabulário de Retrieval

Keyword canônica primeiro, aliases entre parênteses.
Consultar antes de criar keyword nova — se o conceito já existe, usar a canônica.

### Tecnologias
- dspy (DSPy, prompt-compilation, compiled-prompts, prompt-optimizer)
- autogen (AutoGen, ag2, microsoft-autogen)
- langgraph (LangGraph)
- langfuse (Langfuse, observability-tool)
- promptfoo (PromptFoo, prompt-eval-tool)
- lightgbm (LightGBM, gradient-boosting)
- marginaleffects (marginal-effects, avg-predictions)
- instructor (instructor-lib, structured-output-lib)
- tidymodels (tidy-models, r-ml-framework)
- duckdb (DuckDB)
- anthropic-api (claude-api, anthropic-sdk)
- autogen-magentic-one (magentic-one)
- selector-group-chat (group-chat-routing)
- vetiver (vetiver-model-cards)
- arize-phoenix (phoenix-observability)

### Conceitos Técnicos
- structured-extraction (extracao-estruturada, json-extraction)
- semantic-compression (compressao-semantica)
- prompt-specialization (multi-persona, persona-prompts)
- eval-pipeline (evaluation-pipeline, avaliacao-automatica)
- golden-set (ground-truth, test-set, benchmark)
- implicit-feedback (feedback-implicito, user-signals)
- data-flywheel (flywheel, improvement-loop)
- circuit-breaker (circuit-breakers, safety-patterns)
- conformal-prediction (prediction-intervals, uncertainty)
- shap (shapley-values, feature-attribution, explainability)
- lime (local-interpretability)
- contrafactual (counterfactual, causal-inference)
- calibration (model-calibration, confidence-calibration)
- rag (retrieval-augmented-generation, legal-rag)
- streaming (streaming-llm, server-sent-events, sse)
- routing (agent-routing, routing-deterministico)
- handoff (agent-handoff, swarm-handoff)
- decision-debt (divida-decisoria)
- theory-of-constraints (toc, gargalo, bottleneck)
- wardley-mapping (wardley-map, strategy-mapping)
- poka-yoke (error-proofing)
- wip-limits (lean, kanban-limits)
- chain-of-density (summarization-technique)

### Domínio Aplicado (EXAMPLE — customize for your domain)
- domain-knowledge (domain-specific, precedents)
- document-metadata (metadados, document-classification)
- anonymization (anonimizacao, privacy)

### Referências (pessoas, teorias)
- feynman (metodo-feynman, richard-feynman, first-principles)
- turing (alan-turing, turing-patterns, turing-machine)
- arrow (arrow-impossibility, kenneth-arrow, voting-paradox)
- condorcet (jury-theorem, condorcet-paradox)
- hamilton (margaret-hamilton, apollo, software-engineering)
- lovelace (ada-lovelace, first-programmer)
- wardley (simon-wardley)
- dijkstra (edsger-dijkstra, shortest-path)

## Formato nos Artefatos

### Blog entries (frontmatter YAML)
```yaml
---
title: "..."
date: YYYY-MM-DD
tags: [pesquisa, project, multi-agente]
keywords: [autogen, selector-group-chat, langgraph, routing]
report: YYYY-MM-DD-slug.html
---
```

### Reports (header YAML)
```yaml
title: "..."
subtitle: "..."
date: "DD/MM/YYYY"
tags: [pesquisa, project, multi-agente]
keywords: [autogen, selector-group-chat, langgraph, routing]
```

### Notas (frontmatter opcional)
```yaml
---
keywords: [dspy, promptfoo, eval-pipeline]
---
```

## Regras

1. **Consultar este arquivo** antes de criar keyword nova
2. **Tag de tipo é obrigatória** — todo artefato tem pelo menos uma
3. **Keywords são case-insensitive** — sempre minúsculo, hifenizado
4. **Não retroagir** — aplicar daqui pra frente, não voltar nos 161 existentes
5. **Evoluir** — adicionar termos quando surgem, consolidar duplicatas na /reflexao
6. **Índice centralizado** — futuro (INDEX.json), quando volume justificar
