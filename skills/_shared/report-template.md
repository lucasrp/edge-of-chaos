# Template de Relatorio — Referencia Compartilhada

Usado por: /{{PREFIX}}-pesquisa, /{{PREFIX}}-descoberta, /{{PREFIX}}-lazer, /{{PREFIX}}-estrategia, /{{PREFIX}}-planejar, /{{PREFIX}}-reflexao.
Cada skill define suas proprias secoes obrigatorias e regras de ouro 1-3. Este arquivo define o que e COMUM a todas.

---

## Como Gerar

1. **Gerar YAML** com as secoes da skill chamadora, usando os block types abaixo
2. **Escrever YAML** em `/tmp/spec-[skill]-[slug].yaml`
3. **Incluir claims no frontmatter da blog entry** (compactacao — OBRIGATORIO):
   ```yaml
   claims:
     - "Fato verificado que aprendi"
     - "!Coisa que ainda nao sei — gap de conhecimento"
   threads: [fio-relacionado-1, fio-relacionado-2]
   ```
   - Claims = conhecimento duravel extraido do entry. O que sobrevive sem reler o texto inteiro.
   - Prefixo `!` = "nao sei" — gap aberto, candidato a pesquisa futura.
   - `threads:` = fios de investigacao relacionados (ver `~/edge/threads/`).
   - O `consolidar-estado` avisa se claims estao ausentes.
4. **Publicar atomicamente** (blog entry + report HTML + meta-report + state commit):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-[skill]-[slug].yaml
   ```
   O `consolidar-estado` faz tudo em 7 fases:
   - Phase 0/0.5: Frontmatter + review gate
   - Phase 1: Blog entry (blog-publish.sh)
   - Phase 2: Content report (generate_report.py → ~/edge/reports/)
   - Phase 3/3.4: Verificacao + LLM cost
   - **Phase 4: Meta-report** (state delta + scratchpad + adversarial → ~/edge/meta-reports/)
   - Phase 5: State commit (claims, threads, events, digest)
   - Phase 6: Diffs + git commit

   Content report e opcional — publicar sem YAML gera apenas meta-report:
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md
   ```

   Flags uteis: `--scratchpad PATH`, `--no-adversarial`, `--no-meta`, `--skip-review`
5. **Ler meta-report** (`~/edge/meta-reports/<slug>-meta.md`) ANTES de editar estado
6. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

---

## YAML Base

```yaml
title: "[Skill]: [Tema]"
subtitle: "[Subtitulo descritivo]"
date: "DD/MM/YYYY"

executive_summary:
  - "**[Campo 1]:** ..."
  - "**[Campo 2]:** ..."

metrics:
  - value: "N"
    label: "Descricao"

sections:
  - title: "1. [Secao da skill]"
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "ArXiv"   # ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

---

## Block Types Disponiveis

| Tipo | Uso | Campos principais |
|------|-----|-------------------|
| `paragraph` | Texto corrido | text, style? |
| `subsection` | Sub-titulo h3 | title |
| `concept-grid` | Concept-boxes 2-col | items[{name, text}] |
| `callout` | Destaque colorido | variant(info/success/warning/danger), text |
| `card` | Bloco com titulo | title?, badge?, badge_class?, text? |
| `numbered-card` | Card numerado | number, title, badge?, badge_class?, text, card_class? |
| `flow-example` | Input→Output | label, input, output, input_label?, output_label?, code? |
| `comparison` | Antes/Depois 2-col | before{title,badge?,pre?,bullets?}, after{...} |
| `table` | Tabela simples | headers, rows, highlight_rows?, score_row? |
| `comparison-table` | Tabela com status | headers, rows[{cells,classes}], score_row?, note? |
| `risk-table` | Riscos | rows[{risk,probability,mitigation}] |
| `code-block` | Codigo/config | label?, badge?, content |
| `ascii-diagram` | Diagrama ASCII | title?, content |
| `template-block` | Template exemplo | title, description?, content, note? |
| `next-steps-grid` | Roadmap visual | steps[{number,title,description}] |
| `metrics-grid` | KPIs inline | items[{value,label}] |
| `list` | Lista ul/ol | items, ordered? |
| `diff-block` | Antes/depois diff | header?, lines[{type(insert/delete/context),text}] |
| `raw-html` | HTML passthrough | content |
| `derivation` | Feynman: derivacao | title?, text?, bullets?, code? |
| `gap-marker` | Feynman: gap individual | id?, text |
| `gap-table` | Feynman: tabela de gaps | gaps[{id, description, need, status}] |
| `gap-resolution` | Feynman: gap → resposta | gap_id?, gap, text?, answer |
| `glossary` | Glossario + contexto | context?, terms[{term, definition}] |

Campos `text` suportam `**bold**`, `*italic*`, `` `code` ``, `--` (mdash), `->` (rarr).

---

## Regra de Ouro 0: Linhagem Obrigatoria (TODAS as skills)

A PRIMEIRA secao de todo relatorio DEVE incluir um bloco mostrando a cadeia de raciocinio que levou ate aqui. Usar `table` com colunas: **Acao Anterior** | **O que Trouxe** | **Conexao com Este Trabalho**.

Incluir: relatorios anteriores, breaks, descobertas, propostas, pesquisas, execucoes, conversas com o usuario — qualquer acao que informou este trabalho. Citar pelo nome/numero (ex: "Break #26 — tradecraft", "Pesquisa pipeline-minimo-viavel").

Se nao ha trabalho anterior relevante, dizer explicitamente: "Primeiro trabalho sobre este tema."

---

## Regra de Ouro 4: Visualizacoes SVG Inline (OBRIGATORIO quando aplicavel)

SVG nao e so para numeros — qualquer informacao que comunica melhor como imagem merece SVG. Regra: se o leitor precisaria desenhar no papel para entender, gerar SVG.

**Quando gerar SVG:**
- Comparacao de 3+ valores: barras horizontais/verticais
- Distribuicao estatistica: box plot (whiskers + mediana + media)
- Tendencia ao longo do tempo: barras agrupadas por periodo
- Proporcao/composicao: barras empilhadas 100%
- Relacoes entre componentes: diagrama caixas + setas (arquitetura, pipeline, fluxo de dados)
- Processo com decisoes: flowchart (caixas + diamantes)
- Sequencia temporal: timeline horizontal
- Posicionamento 2D: quadrante/matrix (urgencia x impacto, esforco x valor)
- Hierarquia/taxonomia: tree diagram
- Ciclo/loop: diagrama circular (feedback loops, ciclos iterativos)

**Padrao SVG:** viewBox fixo (`700 280` charts, `700 400` diagramas), `font-family:'Segoe UI',sans-serif`, cores semanticas (`#e53e3e` perigo, `#2b6cb0` normal, `#38a169` sucesso, `#ed8936` alerta, `#805ad5` destaque, `#718096` neutro), legenda inline, `max-width:100%`, `<title>` para acessibilidade. Dados numericos: SVG + tabela = par obrigatorio. Diagramas de relacao/fluxo nao precisam de tabela. Minimo 1 SVG por relatorio.

---

## Secoes Finais Obrigatorias

### Penultima Secao: "O que Nao Sei" (OBRIGATORIA — exceto /{{PREFIX}}-lazer)

- `gap-table` com gaps abertos (status: aberto/parcial)
- `callout` variant=danger para incertezas criticas (que podem invalidar uma recomendacao)
- `callout` variant=warning para suposicoes nao testadas
- NAO minimizar — "Nao sei" e informacao valiosa
- Inclui: dados que faltaram, hipoteses nao testadas, alternativas nao exploradas, riscos de estar errado

### Ultima Secao: "Contextualizacao e Glossario" (OBRIGATORIA)

- `paragraph` com 2-3 frases contextualizando: para quem, em que momento, que conhecimento previo ajuda
- `glossary` com campo `context` e campo `terms` listando TODOS os termos tecnicos com definicao pratica
- Permite densidade alta no corpo sem perder acessibilidade

---

## Regras de Formato (OBRIGATORIAS)

- Sem anchor links internos (`<a href="#...">` causa tela branca no SharePoint)
- Links externos PERMITIDOS e ENCORAJADOS (`<a href="https://...">`)
- 100% autocontido (SVG inline, CSS inline) — single file, sem dependencias externas
- Sem emojis (a menos que o usuario peca)
- Densidade de sinal alta — cada bloco deve adicionar informacao, nao decoracao
- Preferir exemplos concretos a descricoes abstratas

---

## Sanity Check Adversarial (edge-consult — OBRIGATORIO em TODA skill)

ANTES de gerar o YAML do relatorio, submeter as conclusoes/recomendacoes ao `edge-consult` para deliberacao cross-model. Um modelo diferente do autor encontra furos, biases, premissas fracas.

```bash
# Adversarial (default) — sintetizar conclusoes em 2-3 frases
edge-consult "Resumo: [conclusoes]. Onde esse raciocinio e mais fraco?" --context /tmp/spec.yaml

# Colaborativo (quando travado em direcao)
edge-consult --mode collab "Estou travado em X, que angulos explorar?"
```

**Protocolo de resposta:**
1. Ler a critica com honestidade
2. Se o argumento e valido → ajustar conclusoes/YAML
3. Se mantiver posicao → registrar no relatorio como `callout` variant=info: "Sanity check: [objecao]. Resposta: [por que mantenho]."

**No relatorio:** incluir bloco mostrando o que foi desafiado e como respondeu. Conviccao testada > conviccao nao desafiada.

**Custo:** ~$0.02/consulta. **Log:** ~/edge/logs/consult/ (para /{{PREFIX}}-reflexao revisar).

---

## Passos Pos-Relatorio (OBRIGATORIOS)

### Review Gate (LLM-as-judge — RODAR ANTES de publicar)

Antes de chamar `consolidar-estado`, rodar o review gate para validacao semantica:

```bash
# Review standalone (loop de refinamento)
review-gate /tmp/spec-[skill]-[slug].yaml --skill [skill]

# Se FAIL: ajustar YAML com base no feedback, re-rodar ate PASS
# Se PASS: publicar
```

O review gate avalia 6 dimensoes (structural_completeness, content_depth, writing_quality, visualization, intellectual_honesty, internal_consistency) via LLM-as-judge. Custo: ~$0.002/review. Threshold: 3.5/5.

**IMPORTANTE:** O `consolidar-estado` tambem roda o review gate automaticamente (Phase 0.5). Se o YAML nao passar, a publicacao e bloqueada. Use `--skip-review` para forcar (so quando ja revisou manualmente).

### Validation Gate (NAO PULAR)

O `consolidar-estado` ja executa a publicacao, geracao de HTML e indexacao do report. Apos ele, validar:

```bash
python3 ~/edge/blog/validate.py --recent
```

Issues comuns:
- `report:` com path completo em vez de filename → usar so o filename
- Tag em ingles → usar PT-BR (lazer, reflexao, pesquisa, descoberta, estrategia, planejamento)
- Report orfao → criar blog entry referenciando-o

### Auto-indexar artefatos adicionais

Se notas adicionais foram criadas em ~/edge/notes/ (alem do report e blog entry ja indexados pelo consolidar-estado):

```bash
edge-index ~/edge/notes/[nota].md
```

Comando silencioso — erros nao interrompem o fluxo.
