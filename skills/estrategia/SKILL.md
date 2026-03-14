---
name: estrategia
description: "Strategic planning across all projects. Analyze state, identify connections, set priorities, suggest next steps. Triggers on: estrategia, strategy, planeje, plan ahead, big picture, quadro geral."
user-invocable: true
---

# Estrategia — Planejamento Estrategico Cross-Project

Olhar para o quadro geral de todos os projetos. Analisar onde cada um esta, o que esta bloqueado, o que precisa de atencao, e como se conectam. Definir direcoes e proximos passos.

---

## O Job

1. Absorver estado cross-project (via `/contexto`)
2. Analisar cada projeto: onde esta, o que precisa, o que bloqueia
3. Identificar conexoes entre projetos
4. Definir direcoes: prioridades, threads a aprofundar, habilidades a desenvolver
5. Sugerir proximos passos concretos ao usuario
6. Propor atualizacoes para `~/tcu/CLAUDE.md` (no relatorio — quem aplica e a `/reflexao`)

---

## Protocolo (seguir na ordem)

### Passo 1: Absorver contexto

Rodar `/contexto` para obter estado cross-project completo.

Se `/contexto` ja foi rodado nesta sessao, reler o output — nao repetir.

### Passo 1.5: Consultar relatorios anteriores

Verificar relatorios anteriores de estrategia e outros relevantes:

```bash
ls -lt ~/edge/reports/*.yaml 2>/dev/null | head -20
```

Para cada YAML de estrategia ou com nome relevante, ler as primeiras ~30 linhas (title, subtitle, executive_summary). Para a estrategia mais recente, ler secoes de prioridades e riscos.

**O que buscar:**
- Estrategia anterior — prioridades que foram definidas, o que mudou desde entao
- Pesquisas e execucoes recentes — informam o estado real dos projetos
- Propostas pendentes — se foram executadas ou nao
- Evolucao dos riscos — quais se concretizaram, quais foram mitigados

**No output:** comparar com ultima estrategia: o que mudou, o que permanece.

### Passo 2: Analise por projeto

Para cada projeto, avaliar:

| Dimensao | Pergunta |
|----------|----------|
| **Momentum** | Esta sendo trabalhado ativamente? Qual o ritmo? |
| **Bloqueios** | Algo esta parado? O que desbloqueia? |
| **Divida tecnica** | Ha tech debt acumulando? Refactors pendentes? |
| **Proxima milestone** | Qual o proximo marco concreto? |
| **Dependencias** | Depende de outro projeto? Outro depende dele? |

### Passo 3: Conexoes entre projetos

Mapear:
- **Dependencias diretas** — assertia-nextjs precisa de endpoints de assertia-multiagent
- **Oportunidades** — ralph pode automatizar tarefas em outros projetos
- **Conflitos** — mudancas em um projeto que afetam outro
- **Sinergias** — trabalho em um projeto que beneficia outro

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes estrategia` para obter tendencias e insights estrategicos de todas as fontes relevantes (X, HN, Web, GitHub releases, AssertIA usage).

Incluir na analise estrategica e citar no relatorio (com URL).

### Passo 4: Definir direcoes

Com base na analise, definir:
- **Prioridade 1-3** — o que atacar primeiro e por que
- **Threads a aprofundar** — areas que merecem mais investigacao
- **Habilidades a desenvolver** — o que me capacitar para ser mais util (alimenta `/pesquisa`)
- **Riscos** — o que pode dar errado se ignorado

### Passo 4.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar prioridades e direcoes definidas em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Prioridades: [lista]. Justificativa: [razoes]. Que risco estou subestimando?" --context /tmp/spec-estrategia-[slug].yaml
```

Ajustar se o GPT encontrar furo valido (ex: dependency nao vista, risco ignorado). Se mantiver posicao, registrar como callout no relatorio.

### Passo 5: Propor atualizacoes para ~/tcu/CLAUDE.md

**NAO editar o arquivo diretamente.** Incluir no relatorio (passo 6) as mudancas propostas para:
- **Mapa de Projetos** — status atualizado de cada projeto
- **Prioridades Atuais** — reordenar conforme analise
- **Sugestoes** — proximos passos concretos
- **Conexoes Entre Projetos** — se mudaram

A `/reflexao` e a unica skill que aplica mudancas no `~/tcu/CLAUDE.md`.

### Passo 6: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `estrategia` (formato: ver `/blog` SKILL.md)
2. **Gerar YAML** do relatorio com as secoes abaixo, usando block types do conversor
3. **Escrever YAML** em `/tmp/spec-estrategia-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-estrategia-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

**Verificar retrospectiva:** Apos adicionar a entry, checar se ha massa critica para uma
retrospectiva (ver secao "Retrospectivas" no `/blog` SKILL.md). A estrategia e o momento
natural para isso — ja fez o survey de tudo. Se 5+ entries desde a ultima retrospectiva
E um arco tematico emergiu, escrever a retrospectiva no mesmo passo.

#### Estrutura do YAML

```yaml
title: "Estrategia — [data]"
subtitle: "[Visao de 1 frase do estado]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Estado:** ..."
  - "**Prioridade #1:** ..."

metrics:
  - value: "N"
    label: "Projetos"
  - value: "N"
    label: "Bloqueios"
  - value: "N"
    label: "Propostas"

sections:
  - title: "1. Quadro Geral"
    blocks: [...]
  - title: "2. Por Projeto"
    blocks: [...]
  - title: "3. Conexoes e Dependencias"
    blocks: [...]
  - title: "4. Prioridades"
    blocks: [...]
  - title: "5. Riscos e Proximos Passos"
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "WebSearch"   # De onde veio: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: card com badge de status por projeto

Cada projeto ganha um `card` com badge de momentum (ATIVO / DORMANT / BLOQUEADO). Dentro: proximo marco, bloqueios, dependencias. O leitor deve ver o status de cada projeto num relance.

#### Regra de ouro 2: ascii-diagram para conexoes

Conexoes entre projetos devem incluir um `ascii-diagram` mostrando o grafo de dependencias. Complementar com `table` de dependencias especificas.

#### Regra de ouro 3: risk-table obrigatorio

Riscos devem usar `risk-table` com probabilidade e mitigacao. Sem risco abstrato — cada um deve ter acao concreta de mitigacao.


#### Secoes obrigatorias:

**1. Quadro Geral** — `paragraph` com visao de 2-3 frases; `metrics-grid` com KPIs (projetos ativos, bloqueios, propostas pendentes)
**2. Por Projeto** — `card` com badge de status para cada projeto (regra 1); `callout` para bloqueios criticos
**3. Conexoes e Dependencias** — `ascii-diagram` do grafo (regra 2); `table` de dependencias especificas
**4. Prioridades** — `numbered-card` para cada prioridade com justificativa; `comparison` when reordenando (antes/depois da analise)
**5. Riscos e Proximos Passos** — `risk-table` (regra 3); `next-steps-grid` com acoes concretas


### Passo 7b: Registrar observações
`edge-scratch add "Estratégia: [conclusão principal]. [mudança de prioridade]. [direção definida]."`
Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

### Passo 8: Relatorio ao usuario

Formato:

```markdown
## Estrategia — [data]

### Quadro Geral
[Visao de 2-3 frases do estado do ecossistema]

### Por Projeto
#### Doc_AssertIA
- Status: [momentum]
- Proximo marco: [o que]
- Atencao: [bloqueios ou riscos]

#### assertia-multiagent
[idem]

#### assertia-nextjs
[idem]

#### assertia-mise
[idem]

#### ralph
[idem]

### Conexoes e Dependencias
[O que conecta os projetos, o que bloqueia o que]

### Prioridades Sugeridas
1. [Prioridade com justificativa]
2. [Prioridade com justificativa]
3. [Prioridade com justificativa]

### Proximos Passos
[Acoes concretas sugeridas ao usuario]

### Riscos
[O que pode dar errado se ignorado]

### Relatorio HTML
~/edge/reports/[arquivo].html
```

---

## Quando Usar

- **Manualmente:** `/estrategia` — "olhe para o quadro geral e planeje"
- **Via /heartbeat:** Periodicamente (quando estrategia esta desatualizada)
- **Apos mudancas significativas** — refactor grande, novo projeto, mudanca de direcao

---

## Notas

- Estrategia NAO e operacional. Nao executar tarefas — analisar e planejar
- Prioridades sao sugestoes ao usuario, nao ordens. O usuario decide
- Usar `ultrathink` (thinkmax) para analise profunda
- Nao inflar a analise — se um projeto esta estavel e nao precisa de atencao, dizer isso em 1 linha
- Foco em conexoes que desbloqueiam trabalho, nao em conexoes teoricas
