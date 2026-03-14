---
name: descoberta
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

`~/.claude/projects/-home-vboxuser/memory/descobertas.md`

Registro de todas as descobertas. Status:
- `[PENDENTE]` — pesquisada, aguardando decisao de adocao
- `[ADOTADA]` — usuario decidiu incorporar ao trabalho
- `[DESCARTADA]` — avaliada e descartada (motivo registrado)

---

## Argumentos Opcionais

- **Sem argumento** (`/descoberta`): explorar livremente e trazer algo util
- **Com direcao** (`/descoberta algo para testar prompts`): buscar nessa direcao especifica

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
- **Lean/Kanban WIP limits** — "Little's Law: reduzir trabalho em progresso AUMENTA throughput. Aplicavel ao pipeline de transcricoes"
- **Andon cord** — "na Toyota, qualquer operario para a linha se ve defeito. Traduzido: fail-fast no pipeline em vez de propagar erro"

### Palavras/conceitos de outras culturas
- **Genchi genbutsu** (現地現物) — "va e veja por si mesmo. Nao confie no relato, leia a transcricao original"
- **Wabi-sabi** — "a beleza da imperfeicao. Um digest 80% bom entregue hoje > 100% perfeito nunca"

**O que todas tem em comum:** aplicacao concreta a um problema real do trabalho, bem explicada.

**O que NAO e uma boa descoberta:** algo interessante mas sem conexao clara ("Physarum resolve labirintos — legal, mas e dai?").

---

## Protocolo (seguir na ordem)

### Passo 0: Absorver contexto (OBRIGATORIO)

Rodar `/contexto` (a skill) para sintetizar o estado atual do trabalho. Nao pular.

Se `/contexto` ja foi rodado nesta sessao, apenas reler o output.

### Passo 0.5: Busca semantica no corpus (anti-redundancia)

Antes de explorar, verificar se o tema ja foi coberto no corpus (~1060 docs):

```bash
# Busca hibrida (FTS + embeddings) — 5 resultados mais relevantes
edge-search "[tema ou direcao da descoberta]" -k 5
```

Se a direcao ainda nao esta clara, usar 2-3 queries conceituais:
```bash
edge-search "[conceito A]" -k 3
edge-search "[conceito B adjacente]" -k 3
```

Para cada resultado relevante, ler o arquivo original (nota ou report YAML) para entender o que ja foi coberto:
```bash
cat ~/edge/notes/[arquivo].md | head -40    # Para notas
head -30 ~/edge/reports/[arquivo].yaml       # Para reports (title, summary)
```

**O que buscar:**
- Descobertas anteriores — nao redescobrir o mesmo conceito/ferramenta
- Gaps abertos em pesquisas — uma descoberta pode resolver um gap existente
- Temas ja explorados — variar a direcao, nao repetir

**Decisao:**
- Se o tema JA foi coberto com profundidade → mudar direcao ou aprofundar um gap aberto
- Se foi mencionado superficialmente → pode aprofundar (citar o antecedente)
- Se nao aparece → terreno novo, prosseguir

**No output:** mencionar o que a busca retornou e como influenciou a direcao.

### Passo 1: Explorar

A busca e livre. Pode partir de:
- Um problema do trabalho que quer resolver
- Algo que viu numa pesquisa e chamou atencao
- Uma conversa das transcricoes que mencionou algo desconhecido
- Curiosidade pura sobre um tema adjacente
- Trending em tech, ciencia, design, gestao, qualquer area

Pode buscar em qualquer lugar:
- Ecossistema de ferramentas, GitHub, HN, papers
- Outras industrias (manufatura, aviacao, medicina)
- Outras culturas (conceitos japoneses, filosofias, palavras sem traducao)
- Historia (como problemas analogos foram resolvidos no passado)
- **X (Twitter)** — buscar tweets de builders e practitioners (ver Passo 2)

A unica regra: ao final, contextualizar bem a aplicacao ao trabalho.

### Passo 2: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes descoberta "[tema]"` para explorar todas as fontes externas relevantes (X, HN, Web, ArXiv).

A propria busca pode ser a descoberta — um tweet, post do HN, ou paper que aponta algo que vale pesquisar a fundo.
Citar no relatorio como fonte (com URL). Se houver likes sugeridos, executar via `/redes engajar`.

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
  - Qual projeto? Qual etapa? Qual decisao?
  - "Como era" sem o conceito vs "como fica" com ele
  - Exemplo concreto, nao generico

Tempo: ~15 minutos de pesquisa real (WebSearch, WebFetch, docs).

### Passo 3.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar a descoberta e sua relevancia em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Descobri [X]. Acho relevante porque [Y]. Isso e genuinamente novo ou obvio?" --context ~/edge/notes/descoberta-[nome].md
```

Ajustar se o GPT encontrar furo valido (ex: ja existe ferramenta melhor, a analogia nao se sustenta). Se mantiver posicao, registrar como callout no relatorio.

### Passo 4: Salvar notas

Notas de pesquisa: `~/edge/notes/descoberta-[nome].md`

Formato adaptavel — usar o que fizer sentido para o tipo de descoberta. Mas sempre incluir:
- O que e
- Contexto original
- **Aplicacao ao nosso trabalho** (secao obrigatoria e detalhada)
- Fontes

### Passo 5: Registrar descoberta

Adicionar no topo de `~/.claude/projects/-home-vboxuser/memory/descobertas.md`:

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

1. **`breaks-archive.md`** — entrada completa:
```markdown
## [YYYY-MM-DD] Descoberta — [Nome] [via heartbeat]
- **Tipo:** [ferramenta | conceito | padrao | modelo mental]
- **Problema enderecado:** [qual friccao]
- **Aplicacao:** [como se traduz para o trabalho]
- **Veredicto:** [promissora | interessante | marginal]
- **Proximo passo:** [o que fazer para adotar/aplicar]
```

2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks"
3. **Observações de estado:** `edge-scratch add "o que aconteceu"` durante execução. Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

### Passo 7: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `descoberta` (formato: ver `/blog` SKILL.md)
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

sections:            # Secoes adaptaveis ao tipo (ver abaixo)
  - title: "1. O Problema"
    blocks: [...]
  - title: "2. A Descoberta"
    blocks: [...]
  - title: "3. Aplicacao ao Trabalho"
    blocks: [...]
  - title: "4. Para Comecar"
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "GitHub"   # De onde veio: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para a descoberta

A descoberta em si DEVE ter um `concept-grid` com:
- **Nome** do conceito/ferramenta
- **Analogia** ("X e como Y, mas para Z")
- **Definicao pratica** (o que faz, em 2-3 frases)

Qualquer conceito auxiliar mencionado tambem ganha concept-box.

#### Regra de ouro 2: "Como era / Como fica" obrigatorio

A secao "Aplicacao ao Trabalho" DEVE incluir `comparison` mostrando o estado atual vs o estado com a descoberta aplicada:

- **Para ferramentas:** usar `flow-example` (input amarelo → output verde) mostrando a ferramenta operando com dados do nosso contexto
- **Para conceitos/modelos mentais:** usar `comparison` (before/after) mostrando decisao/workflow antes vs depois de aplicar o conceito
- **Para padroes:** usar `diff-block` ou `comparison` com exemplos de codigo/processo

O leitor deve VER a diferenca, nao ler sobre ela.

#### Regra de ouro 3: exemplo concreto com dados reais

Para CADA descoberta, incluir pelo menos um `flow-example` ou `code-block` com dados reais (ou realistas) do nosso trabalho, mostrando a descoberta em acao:

- Ferramenta: comando de instalacao + hello world com nossos dados
- Conceito: situacao real do trabalho analisada pela lente do conceito
- Padrao: trecho de codigo/config nosso transformado pelo padrao


#### Secoes adaptaveis ao tipo:

**Para FERRAMENTAS:**

1. **O Problema** — qual friccao do trabalho motiva buscar essa ferramenta
   - `paragraph` descrevendo a dor concreta
   - `callout` com exemplo real da friccao

2. **A Ferramenta** — o que e e como funciona
   - `concept-grid` com concept-box da ferramenta (regra 1)
   - `flow-example` mostrando input → output da ferramenta (regra 3)
   - `code-block` com comando de instalacao

3. **Aplicacao ao Trabalho** — como usar nos nossos projetos
   - `comparison` before/after (regra 2)
   - `table` mapeando feature da ferramenta → problema nosso que resolve
   - `callout` warning para limitacoes relevantes

4. **Para Comecar** — primeiro passo pratico
   - `next-steps-grid` com 3-4 passos concretos
   - `code-block` com hello world usando nossos dados

**Para CONCEITOS / MODELOS MENTAIS:**

1. **O Problema** — qual friccao/gap motivou a busca
   - `paragraph` descrevendo a situacao
   - `callout` com exemplo real

2. **O Conceito** — origem, essencia, como funciona
   - `concept-grid` com concept-box do conceito (regra 1)
   - `paragraph` com origem e contexto (quem formulou, onde nasceu)
   - `flow-example` mostrando o conceito em acao no contexto original

3. **Aplicacao ao Trabalho** — como se traduz pro nosso contexto
   - `comparison` before/after (regra 2) — decisao/workflow antes vs depois
   - Exemplo concreto: qual projeto, qual etapa, qual mudanca (regra 3)
   - `callout` para ressalvas e limites da analogia

4. **Para Comecar** — como aplicar amanha
   - `next-steps-grid` com 2-3 acoes concretas
   - Baixa barreira de entrada: o que fazer primeiro


### Passo 9: Relatorio ao usuario

Formato:

```
## Descoberta — [Nome] — [Data]

### O Problema
[Qual friccao/gap do trabalho motivou a busca]

### O que Encontrei
[Nome, o que e — explicacao clara para quem nunca ouviu falar]
[Contexto de onde vem (se conceito: origem, quem formulou)]

### Como Aplica ao Nosso Trabalho
[Conexao concreta e detalhada]
[Como era antes vs como fica com esse insight]
[Qual projeto, qual etapa, qual decisao]

### Para Comecar
[Primeiro passo pratico — o que fazer amanha]

### Limitacoes
[O que nao resolve, trade-offs, cuidados]

### Relatorio HTML
~/edge/reports/[arquivo].html
```

---

## Quando Usar

- **Via /heartbeat:** Na rotacao normal do ciclo
- **Manualmente:** `/descoberta` — "encontre algo util para o trabalho"
- **Com direcao:** `/descoberta algo para testar prompts` — buscar nessa area

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- A busca e LIVRE — pode ser qualquer coisa de qualquer lugar
- O que importa e a qualidade da contextualizacao: "como isso ajuda no nosso trabalho?"
- Nao limitar o tipo de descoberta — limitar o que nao vai ser interessante nem util
- Se algo surpreendeu mas nao tem aplicacao clara, nao forcar — registrar a surpresa e ser honesto sobre os limites
- Usar `ultrathink` (thinkmax) na pesquisa
