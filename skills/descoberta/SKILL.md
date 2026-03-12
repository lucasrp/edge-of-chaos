---
name: {{PREFIX}}-descoberta
description: "Discover useful tools, concepts, or mental models that apply to real work problems. Like a well-read friend giving you a practical insight. Triggers on: descoberta, discover, explore new, new tool, bizu."
user-invocable: true
---

# Descoberta — Insight Pratico

Explorar livremente e trazer algo util. Pode ser uma ferramenta, um conceito, um modelo mental, uma palavra de outra cultura, um padrao de outra industria — qualquer coisa. A busca e livre. O que importa e que no final, a contextualizacao ao trabalho seja CLARA e detalhada.

Como aquele amigo bem informado que traz coisas que voce nunca teria encontrado sozinho, mas explica bem por que aquilo importa pra voce.

---

## O Job

1. Explorar livremente — curiosidade guia a busca
2. Pesquisar com profundidade o que encontrar
3. Contextualizar BEM: explicar o que e, POR QUE ajuda no nosso caso especifico, como comecar
4. Registrar como descoberta pendente

---

## Arquivo de Descobertas

`memory/descobertas.md`

Registro de todas as descobertas. Status:
- `[PENDENTE]` — pesquisada, aguardando decisao de adocao
- `[ADOTADA]` — usuario decidiu incorporar ao trabalho
- `[DESCARTADA]` — avaliada e descartada (motivo registrado)

---

## Argumentos Opcionais

- **Sem argumento** (`/{{PREFIX}}-descoberta`): explorar livremente e trazer algo util
- **Com direcao** (`/{{PREFIX}}-descoberta algo para testar prompts`): buscar nessa direcao especifica

---

## O que e uma Boa Descoberta

Pode ser qualquer coisa, desde que tenha aplicacao pratica bem contextualizada:

### Ferramentas
- **DSPy** — "voce esta ajustando prompts na mao? DSPy otimiza automaticamente com few-shot e instrucoes"
- **Promptfoo** — "voce testa prompts com screenshot? Promptfoo faz eval automatico, tipo TDD para prompts"

### Conceitos e modelos mentais
- **Hamilton Three-Layer** — "governanca da Apollo: acao autonoma → comunicacao transparente → decisao humana. E exatamente o que o heartbeat faz"
- **Kaizen** — "melhoria continua incremental. Em vez de refatorar tudo, melhorar 1% por ciclo"
- **OODA Loop** — "Observe-Orient-Decide-Act. Framework militar para decisao rapida com informacao incompleta"

### Padroes de outras industrias
- **Lean/Kanban WIP limits** — "Little's Law: reduzir trabalho em progresso AUMENTA throughput"
- **Andon cord** — "na Toyota, qualquer operario para a linha se ve defeito. Traduzido: fail-fast no pipeline em vez de propagar erro"

### Palavras/conceitos de outras culturas
- **Genchi genbutsu** — "va e veja por si mesmo. Nao confie no relato, leia o dado original"
- **Wabi-sabi** — "a beleza da imperfeicao. Um output 80% bom entregue hoje > 100% perfeito nunca"

**O que todas tem em comum:** aplicacao concreta a um problema real do trabalho, bem explicada.

**O que NAO e uma boa descoberta:** algo interessante mas sem conexao clara ("Physarum resolve labirintos — legal, mas e dai?").

---

## Protocolo (seguir na ordem)

### Passo 0: Absorver contexto (OBRIGATORIO)

Rodar `/{{PREFIX}}-contexto` (a skill) para sintetizar o estado atual do trabalho. Nao pular.

Se `/{{PREFIX}}-contexto` ja foi rodado nesta sessao, apenas reler o output.

### Passo 0.5: Busca semantica no corpus (anti-redundancia)

Antes de explorar, verificar se o tema ja foi coberto no corpus:

```bash
# Busca hibrida (FTS + embeddings) — 5 resultados mais relevantes
edge-search "[tema ou direcao da descoberta]" -k 5
```

**Decisao:**
- Se o tema JA foi coberto com profundidade → mudar direcao ou aprofundar um gap aberto
- Se foi mencionado superficialmente → pode aprofundar (citar o antecedente)
- Se nao aparece → terreno novo, prosseguir

**No output:** mencionar o que a busca retornou e como influenciou a direcao.

### Passo 1: Explorar

A busca e livre. Pode partir de:
- Um problema do trabalho que quer resolver
- Algo que viu numa pesquisa e chamou atencao
- Curiosidade pura sobre um tema adjacente
- Trending em tech, ciencia, design, gestao, qualquer area

### Passo 2: Buscar fontes externas (OBRIGATORIO)

Rodar `/{{PREFIX}}-fontes descoberta "[tema]"` para explorar todas as fontes externas relevantes (X, HN, Web, ArXiv).

### Passo 3: Pesquisar com profundidade

Usar `ultrathink` (thinkmax).

Para FERRAMENTAS, pesquisar:
- O que e, que problema resolve, como funciona
- Como comecar (install, config, hello world)
- Custo, dependencias, limitacoes

Para CONCEITOS, pesquisar:
- Origem e contexto original (onde nasceu, quem formulou)
- A essencia do conceito (explicar como se o usuario nunca ouviu falar)
- **APLICACAO DETALHADA:** como se traduz para o nosso contexto especifico

Tempo: ~15 minutos de pesquisa real (WebSearch, WebFetch, docs).

### Passo 3.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar a descoberta e sua relevancia em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Descobri [X]. Acho relevante porque [Y]. Isso e genuinamente novo ou obvio?" --context ~/edge/notes/descoberta-[nome].md
```

### Passo 4: Salvar notas

Notas de pesquisa: `~/edge/notes/descoberta-[nome].md`

### Passo 5: Registrar descoberta

Adicionar no topo de `memory/descobertas.md`:

```markdown
---

## [YYYY-MM-DD] [Nome] — [Frase curta do que resolve] [PENDENTE]

**Tipo:** [ferramenta | conceito | padrao | modelo mental]
**Problema:** [Qual friccao/gap do trabalho endereca]
**O que e:** [2-3 frases claras — para quem nunca ouviu falar]
**Aplicacao:** [Conexao CONCRETA — qual projeto, qual etapa, como muda o que fazemos]
**Para comecar:** [Primeiro passo pratico — o que fazer amanha]
**Esforco:** [baixo | medio | alto] — [estimativa]
**Notas:** `~/edge/notes/descoberta-[nome].md`
```

### Passo 6: Registrar no break journal

Registrar em TRES arquivos:

1. **`breaks-archive.md`** — entrada completa
2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks"
3. **Observacoes de estado:** `edge-scratch add "o que aconteceu"` durante execucao. Estado processado na publicacao via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

### Passo 7: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `descoberta` (formato: ver `/{{PREFIX}}-blog` SKILL.md)
2. **Gerar YAML** do relatorio com as secoes abaixo, usando block types do conversor
3. **Escrever YAML** em `/tmp/spec-descoberta-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-descoberta-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

#### Estrutura do YAML

```yaml
title: "Descoberta: [Nome]"
subtitle: "[O que resolve]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Problema:** ..."
  - "**Insight:** ..."

metrics:
  - value: "[tipo]"
    label: "Tipo"
  - value: "[esforco]"
    label: "Esforco de Adocao"

sections:
  - title: "1. O Problema"
    blocks: [...]
  - title: "2. A Descoberta"
    blocks: [...]
  - title: "3. Aplicacao ao Trabalho"
    blocks: [...]
  - title: "4. Para Comecar"
    blocks: [...]

bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "GitHub"
```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para a descoberta

A descoberta em si DEVE ter um `concept-grid` com nome, analogia e definicao pratica.

#### Regra de ouro 2: "Como era / Como fica" obrigatorio

A secao "Aplicacao ao Trabalho" DEVE incluir `comparison` mostrando o estado atual vs o estado com a descoberta aplicada.

#### Regra de ouro 3: exemplo concreto com dados reais

Para CADA descoberta, incluir pelo menos um `flow-example` ou `code-block` com dados reais ou realistas.

### Passo 9: Relatorio ao usuario

Formato conciso com: O Problema, O que Encontrei, Como Aplica ao Nosso Trabalho, Para Comecar, Limitacoes, Relatorio HTML.

---

## Quando Usar

- **Via /{{PREFIX}}-heartbeat:** Na rotacao normal do ciclo
- **Manualmente:** `/{{PREFIX}}-descoberta` — "encontre algo util para o trabalho"
- **Com direcao:** `/{{PREFIX}}-descoberta algo para testar prompts` — buscar nessa area

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- A busca e LIVRE — pode ser qualquer coisa de qualquer lugar
- O que importa e a qualidade da contextualizacao: "como isso ajuda no nosso trabalho?"
- Se algo surpreendeu mas nao tem aplicacao clara, nao forcar — registrar a surpresa e ser honesto sobre os limites
- Usar `ultrathink` (thinkmax) na pesquisa
