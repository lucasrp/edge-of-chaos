# Workflow Conventions — Captura e Resgate de Conhecimento Operacional

Workflows documentam **como eu trabalho** — combinacoes de capacidades, secrets, e passos que produziram resultado. Blog entries capturam o que penso; workflows capturam o que faco.

---

## Por que existe

Toda sessao descobre combinacoes, atalhos, jeitos melhores de fazer coisas. Sem captura, isso morre quando a sessao termina. Na proxima sessao, redescobre-se do zero ou simplesmente nao se faz.

O blog tem 600+ entries porque o pipeline de captura existe. Workflows eram ~10 porque nao tinham pipeline.

---

## Formato: Blog Entry com tag `workflow`

Um workflow e uma blog entry normal com `workflow` nas tags. O edge-search detecta o tipo e permite filtrar por `--type workflow`.

### Workflow que funciona

```yaml
---
title: "workflow: sources → research → consult → report"
date: 2026-03-24
tags: [workflow, research, sources, edge-consult]
keywords: [edge-sources, ed-research, edge-consult, exa, openai, pipeline]
claims:
  - "Combinar sources + consult antes do report melhora qualidade do output"
secrets: [exa.env, openai.env]
cost_estimate: "~$0.15/execucao"
---

## Trigger
Heartbeat identifica tema relevante, ou usuario pede /ed-research.

## Passos
1. `edge-sources "topico" --intent research` → coleta de sources (Exa + X + HN)
2. Curadoria LLM → filtrar sinal de ruido
3. `edge-consult` → review adversarial do rascunho (GPT-5.4)
4. Blog entry + report HTML

## Secrets
- `exa.env` — busca semantica no passo 1
- `openai.env` — review adversarial no passo 3

## Quando funciona
Temas tecnico-cientificos com boa cobertura nas sources.

## Quando falha
Temas muito nichados onde sources retornam pouco sinal.

## Custo
~$0.15/execucao (Exa: ~$0.01, OpenAI consult: ~$0.10, margem)
```

### Anti-pattern (workflow que nao funciona)

```yaml
---
title: "anti-pattern: playwright screenshot loop pra validar report"
date: 2026-03-24
tags: [workflow, anti-pattern, chrome, playwright, reports]
keywords: [playwright, screenshot, chrome, report-validation, visual-feedback]
claims:
  - "Screenshot loop com Playwright e fragil — tab management desconecta frequentemente"
  - "!Gap — alternativa confiavel pra validacao visual de reports"
secrets: []
cost_estimate: "~$0 (local)"
---

## O que tentei
1. Abrir report HTML no Chrome via Playwright
2. Screenshot → analisar rendering → editar → repetir

## Por que nao funciona
- Playwright desconecta do Chrome quando tabs acumulam
- Tab management inconsistente (MetaMask sempre no tab 0 interfere)
- Tempo gasto reconectando > tempo economizado validando visualmente

## Alternativa que funciona
Validar reports via `validate.py --recent` (estrutural) + spot-check manual quando necessario.
```

A diferenca e a tag `anti-pattern`. O edge-search traz ambos — o que funciona e o que nao funciona — e a skill decide.

---

### Campos especificos de workflow (no frontmatter)

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `tags` | list | sim | Deve incluir `workflow` (+ `anti-pattern` se falhou) |
| `secrets` | list | sim | Quais `.env` files sao necessarios ([] se nenhum) |
| `cost_estimate` | string | nao | Custo estimado por execucao |

O corpo segue a estrutura:
- **Workflow:** Trigger → Passos → Secrets → Quando funciona → Quando falha → Custo
- **Anti-pattern:** O que tentei → Por que nao funciona → Alternativa que funciona

---

## Captura: Quando registrar

Registrar um workflow durante o `consolidar-status` quando:

1. **A sessao combinou 2+ capacidades** de um jeito que produziu resultado melhor que cada uma isolada
2. **Descobriu-se um atalho** — um jeito mais eficiente de fazer algo
3. **Uma combinacao falhou** de um jeito instrutivo — o anti-pattern evita rediscovery do fracasso

Nao registrar:
- Uso isolado de uma skill (isso e blog, nao workflow)
- Workflows identicos a um ja indexado (verificar com `edge-search` antes)

### Check antes de criar

```bash
# Verificar se workflow similar ja existe
edge-search "sources research consult" --type workflow -k 3
```

Se existe algo similar, atualizar a entry existente em vez de criar nova.

---

## Resgate: Como skills consultam

Antes de execute, skills podem consultar workflows relevantes:

```bash
# Buscar workflows relacionados ao que vou fazer
edge-search "research sources blog" --type workflow -k 3
```

O resultado traz workflows validados com passos, secrets necessarios, e quando funciona/falha. Anti-patterns aparecem junto — a skill sabe o que evitar.

Isto e **OBRIGATORIO** antes de execute qualquer skill (ver state-protocol.md).

---

## Workflow quebrado = bug

Workflow que falha na execucao deve ser registrado em `debugging.md` e marcado como stale (claim `"!Gap"` ou anti-pattern novo).

---

## Decaimento

Workflows que nunca sao resgatados perdem relevancia naturalmente:
- `edge-search` registra telemetria de cada busca
- `/ed-corpus-curation` pode identificar workflows nunca consultados
- Workflow sem resgate em 60 dias e candidato a archive

Workflow atualizado frequentemente (novas sessoes confirmam o pattern) ganha relevancia.

---

## Relacao com secrets/MANIFEST.md

O workflow declara **quais secrets precisa** (`secrets: [exa.env, openai.env]`).
O `MANIFEST.md` documenta **o que cada secret habilita e se esta ativo**.

Se um secret expira, nao e preciso atualizar cada workflow — basta consultar o MANIFEST para saber quais workflows ficaram quebrados.

---

## Migracao do workflows.md legado

O arquivo `~/edge/autonomy/workflows.md` contem 15 workflows no formato antigo. Estes servem como referencia historica mas **novos workflows devem ser blog entries** com tag `workflow`.

Migracao gradual: conforme workflows antigos forem re-descobertos em uso, captura-los como blog entries. Nao migrar em batch — deixar o uso determinar o que vale preservar.
