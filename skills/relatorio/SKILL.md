---
name: relatorio
description: "Generate a structured HTML report on any topic. Use when you need to deeply understand something, analyze a question, or produce a deliverable for the user. Dual-purpose: user invokes for deliverables, edge_of_chaos self-invokes to think through problems. Triggers on: relatorio, report, gerar relatorio, analise, analyze, explique em detalhe."
user-invocable: true
---

# /relatorio — Pensar Produzindo

Gerar relatorio HTML estruturado sobre qualquer tema. Ferramenta de pensamento E de comunicacao.

## Quando Usar

**O usuario pede:**
- "faz um relatorio sobre X"
- "analise isso em detalhe"
- "quero entender melhor Y"

**edge_of_chaos decide:**
- Preciso entender algo antes de agir — o relatorio forca pensamento estruturado
- Um tema complexo precisa ser decomposto — o formato de secoes obriga clareza
- Quero registrar um raciocinio que pode ser util depois — o HTML persiste

**Regra:** se o pensamento e complexo o suficiente pra precisar de mais de 3 paragrafos, vale um relatorio. O ato de estruturar em secoes, tabelas e comparacoes FORCA entendimento que texto corrido nao forca.

---

## Protocolo

### Passo 1: Definir escopo

Antes de pesquisar ou escrever, responder em 1-2 frases:
- **O que quero entender?** (pergunta central)
- **Para que?** (decisao a tomar, contexto a construir, curiosidade a satisfazer)
- **Qual o minimo que o relatorio precisa ter pra ser util?**

Se invocado pelo usuario com tema especifico, o escopo vem do pedido.
Se auto-invocado, explicitar o trigger ("estou gerando este relatorio porque...").

### Passo 2: Pesquisar

Usar as ferramentas disponiveis conforme o tema:

- **WebSearch / WebFetch** — estado da arte, ferramentas, papers, docs
- **Read de arquivos locais** — projetos, notas anteriores, transcripts
- **Read de relatorios anteriores** — evitar refazer trabalho:
  ```bash
  ls -lt ~/edge/reports/*.html | head -10
  ```
- **Grep em notas** — conectar com pesquisas passadas:
  ```bash
  grep -rl "TERMO" ~/edge/notes/*.md | head -5
  ```

**Metodo Feynman:** derivar de primeiros principios antes de colar conclusoes de terceiros. Mostrar o processo de pensar, nao so a conclusao. Se encontrar um gap no raciocinio, marcar explicitamente.

### Passo 2.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes relatorio "[tema central]"` para busca abrangente em TODAS as fontes externas (X, Web, ArXiv, HN, GitHub).

Incorporar na analise e citar no relatorio (com @username e URL para tweets, links para papers/posts).

### Passo 3: Estruturar em YAML

Montar o YAML spec com secoes e block types. O formato e o mesmo do `/relatorio-tcu`.

```yaml
title: "Titulo do Relatorio"
subtitle: "Subtitulo contextual"
date: "DD/MM/YYYY"

executive_summary:
  - "Ponto 1"
  - "Ponto 2"

metrics:
  - value: "N"
    label: "Label"

sections:
  - title: "1. Secao"
    blocks:
      - type: paragraph
        text: "..."

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Autor (2024). Titulo do paper"
    url: "https://arxiv.org/abs/..."
    source: "ArXiv"
  - text: "@username — Tweet sobre o tema"
    url: "https://x.com/username/status/..."
    source: "X"
  - text: "Titulo do post ou doc"
    url: "https://example.com/..."
    source: "WebSearch"
```

**Bibliografia e OBRIGATORIA em todo relatorio.** O campo `bibliography:` no nivel raiz do YAML auto-renderiza como ultima secao "Referencias" com:
- Numeracao `[1]`, `[2]`, ...
- URL clicavel
- Badge indicando a fonte que encontrou a referencia (ArXiv, X, WebSearch, GitHub, HN, Docs, etc.)

Isso permite ao leitor avaliar QUAIS fontes sao mais uteis e clicar pra ver o original.

Formatos aceitos:
- **Estruturado:** `{text, url, source}` — preferir sempre
- **String simples:** `"Autor (2024). Titulo. URL"` — fallback rapido

`source` reflete DE ONDE veio a informacao (qual ferramenta/fonte encontrou), nao o tipo do conteudo. Ex: um paper encontrado via WebSearch tem `source: "WebSearch"`, nao `source: "Paper"`.

**Escolha de block types pelo conteudo:**

| Preciso mostrar... | Block type |
|---------------------|-----------|
| Texto corrido, raciocinio | `paragraph` |
| Antes vs depois, opcao A vs B | `comparison` |
| Dados tabulares, padroes | `table` |
| KPIs, numeros-chave | `metrics-grid` |
| Destaque importante | `callout` (info/success/warning/danger) |
| Conceitos lado a lado | `concept-grid` |
| Input → output (exemplos) | `flow-example` |
| Codigo, config | `code-block` |
| Mudancas propostas | `diff-block` |
| Proximos passos | `next-steps-grid` |
| Itens sequenciais | `numbered-card` |
| Lista simples | `list` |
| Fontes e referencias | `bibliography` |

Campos `text` suportam: `**bold**`, `*italic*`, `` `code` ``, `--` (mdash), `->` (rarr).

### Passo 3.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar conclusoes do relatorio em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Analise: [conclusoes]. Onde esse raciocinio e mais fraco?" --context /tmp/spec-[slug].yaml
```

Ajustar se o GPT encontrar furo valido. Se mantiver posicao, registrar como callout no relatorio.

### Passo 4: Registrar no blog e memoria (ANTES do HTML — OBRIGATORIO)

**Blog ANTES de HTML. SEMPRE.** O HTML e o passo mais caro em tokens. Se o contexto esgota durante a geracao do HTML, o blog ja foi escrito. O filename do report e deterministico (`YYYY-MM-DD-slug.html`) — pode ser referenciado antes de existir.

**4a. Blog interno:**
1. Criar entry .md com tag `relatorio` (ou da skill chamadora). Formato: ver `/blog` SKILL.md
2. A publicacao sera feita no Passo 5 junto com o report (via `consolidar-estado`)

**4b. Observações de estado:** `edge-scratch add "Relatório [tema]: [conclusão principal]. [próximo passo]."` (estado via meta-report, ver `~/.claude/skills/_shared/state-protocol.md`).

**4c. Descobertas** — se o relatorio revelou algo novo (ferramenta, padrao, bug, insight):
- Anotar em `~/edge/notes/` se merece nota propria
- Ou adicionar como entrada em `~/.claude/projects/-home-vboxuser/memory/descobertas.md` com `[PENDENTE]`
- A `/reflexao` vai processar na proxima execucao

Se foi auto-invocado, explicar ao usuario o que gerou e por que:
> "Gerei um relatorio sobre X porque precisava entender Y antes de Z. Esta em ~/edge/reports/..."

### Passo 5: Publicar blog entry + gerar HTML + indexar (atomico)

```bash
consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-[slug].yaml
```

O `consolidar-estado` faz tudo: publica a blog entry, gera o HTML do report em `~/edge/reports/`, e indexa no edge-memory.

Se notas foram criadas em ~/edge/notes/, indexar separadamente:
```bash
edge-index ~/edge/notes/[nota].md
```

### Passo 6: Verificar

**6a. Validar SVGs** (custo zero de contexto):
```bash
validate-svg ~/edge/reports/[relatorio-criado].html
```
Se algum SVG falhou, corrigir no YAML e regenerar.

**6b. Revisar YAML** (salvo automaticamente junto do HTML). Confirmar que:
- Executive summary captura a essencia
- Secoes tem fluxo logico
- Tabelas e comparacoes comunicam mais que texto faria
- Gaps de conhecimento estao marcados (honestidade > completude)

---

## Estilo de Escrita

Mesmo do blog: reflexivo e direto. Nem formal-academico, nem casual-demais.

Adicoes especificas para relatorios:
- **Secoes contam uma historia.** A ordem importa: contexto → problema → analise → sintese → proximo passo
- **Tabelas > texto** quando ha 3+ itens com atributos comparaveis
- **Comparisons > paragrafos** quando ha opcoes com tradeoffs
- **Callouts para insights** que o leitor nao deve perder
- **Honestidade sobre gaps:** "nao investiguei X" e melhor que silencio ou bullshit

---

## Visualizacoes SVG inline (OBRIGATORIO quando aplicavel)

SVG inline e a linguagem visual dos relatorios. Gerar via bloco `raw-html` no YAML. Nao e so para numeros — qualquer informacao que comunica melhor como imagem do que como texto merece SVG.

**Regra de decisao:** se o leitor precisaria desenhar no papel para entender, o relatorio deveria ter SVG.

### Quando gerar SVG

| Situacao | Tipo de SVG | Exemplo |
|----------|-------------|---------|
| Comparacao de 3+ valores | Barras horizontais/verticais | Custos, duracoes, contagens |
| Distribuicao estatistica | Box plot (whiskers + mediana) | Tempos de resposta, scores |
| Tendencia ao longo do tempo | Barras agrupadas por periodo | Evolucao de metricas |
| Proporcao/composicao | Barras empilhadas 100% | Distribuicao por categoria |
| Relacoes entre componentes | Diagrama caixas + setas | Arquitetura, pipeline, fluxo de dados |
| Processo com decisoes | Flowchart (caixas + diamantes) | Workflow, arvore de decisao |
| Sequencia temporal | Timeline horizontal | Historico, roadmap, evolucao |
| Posicionamento 2D | Quadrante/matrix | Urgencia x impacto, esforco x valor |
| Hierarquia/taxonomia | Tree diagram | Estrutura de projeto, dependencias |
| Estado/progresso | Progress bars, gauges | Completude, health, coverage |
| Ciclo/loop | Diagrama circular | Feedback loops, ciclos iterativos |

### Padrao tecnico

- `viewBox` fixo: `700 280` para charts, `700 400` para diagramas, `700 200` para timelines
- `font-family: 'Segoe UI', sans-serif`
- `max-width: 100%` no container
- Cores semanticas:
  - `#2b6cb0` normal/info (azul TCU)
  - `#38a169` sucesso/positivo
  - `#e53e3e` perigo/critico
  - `#ed8936` alerta/atencao
  - `#805ad5` destaque/especial
  - `#718096` neutro/secundario
- Legenda inline (dentro do SVG, nao separada)
- Texto: minimo 12px, contraste adequado
- `<title>` nos elementos principais para acessibilidade

### Regras

1. **Dados numericos: SVG + tabela = par obrigatorio.** O grafico e a visualizacao; a tabela e a referencia exata
2. **Diagramas de relacao/fluxo nao precisam de tabela** — sao autoexplicativos
3. **Simplicidade > decoracao.** Barra horizontal resolve? Nao usar 3D. Seta reta resolve? Nao usar curva
4. **Preferir SVG a texto** quando 3+ elementos tem relacoes espaciais (acima/abaixo, antes/depois, contem/contido, depende/bloqueia)
5. **Minimo 1 SVG por relatorio.** Se nao ha dados nem relacoes para visualizar, o relatorio provavelmente e curto demais para ser relatorio

---

## Regras de formato

- Sem anchor links internos (`<a href="#...">` causa tela branca no SharePoint)
- Links externos PERMITIDOS e ENCORAJADOS (`<a href="https://...">`) — tweets, papers, docs, fontes. O leitor quer clicar e ver o original
- 100% autocontido (SVG inline, CSS inline) — single file, sem dependencias externas
- Sem emojis (a menos que o usuario peca)

---

## Privacidade

Relatorios vivem em `~/edge/reports/` — CONFIDENCIAL, so humano + IA.
Podem conter nomes de projetos, detalhes especificos, insights do trabalho.
Para conteudo publico (Netlify), sanitizar ANTES de publicar.
