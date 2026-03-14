---
name: pesquisa
description: "Deep dive research on a specific topic or problem. Directed study with actionable output. Triggers on: pesquisa, pesquise, estude, research, deep dive, aprofunde, feynman, entenda, derive, first principles, explique de verdade."
user-invocable: true
---

# Pesquisa — Deep Dive Dirigido

Sei O QUE quero aprender — preciso aprofundar. Pesquisa focada num tema, ferramenta, ou problema especifico. Diferente da /descoberta (que explora livremente), a /pesquisa parte de um alvo claro.

Exemplos: "/pesquisa DSPy", "/pesquisa como reduzir custo de tokens", "/pesquisa padroes de pipeline".

---

## Argumentos Opcionais

- **Sem argumento** (`/pesquisa`): identificar alvo automaticamente a partir de friction points do contexto
- **Com tema** (`/pesquisa DSPy`): pesquisar esse tema em profundidade
- **Com problema** (`/pesquisa como otimizar o fluxo do pipeline`): pesquisar solucao para esse problema
- **Modo Feynman** (`/pesquisa feynman backpropagation` ou `/feynman X`): entendimento profundo — derivar antes de pesquisar, ensinar para testar entendimento, rastrear gaps

Quando ha argumento, **pular a etapa de identificacao de alvo** e ir direto ao que foi pedido.

### Modo Feynman

Ativado quando o argumento contem "feynman", ou quando o trigger e `/feynman`, `entenda`, `derive`, `explique de verdade`.

Muda o Passo 4: em vez de pesquisar direto, segue o ciclo:

1. **Derivar primeiro** — antes de buscar qualquer fonte, tentar reconstruir o conceito do zero. Onde trava? Anotar como `[GAP: ...]`
2. **Pesquisar so os gaps** — nao fazer survey geral. Buscar exatamente o que faltou na derivacao
3. **Ensinar** — escrever a explicacao como se ensinasse a alguem inteligente sem contexto. Sem jargao. Com analogias. Com mecanica. Com limites
4. **Verificar gaps** — reler com olho critico. Onde ficou vago? Marcar `[AINDA NAO ENTENDI: ...]`. Se houver gaps, voltar ao passo 2 (max 2 iteracoes)

O output do modo Feynman e uma **explicacao autocontida** em vez de recomendacoes acionaveis. O relatorio usa `comparison` antes/depois (entendimento superficial → profundo) e a explicacao e a secao central.

---

## O Job

Aprofundar num tema especifico e produzir recomendacoes acionaveis (modo padrao) ou entendimento profundo (modo Feynman).

| | /pesquisa (padrao) | /pesquisa feynman | /descoberta |
|---|---|---|---|
| **Pergunta** | "O que fazer sobre X?" | "Entendo X de verdade?" | "O que nao sei que nao sei?" |
| **Metodo** | Buscar, comparar, recomendar | Derivar, ensinar, rastrear gaps | Explorar livremente |
| **Output** | Recomendacoes acionaveis | Explicacao autocontida + gaps | Ferramenta/conceito novo |
| **Teste** | "Sei o que fazer?" | "Consigo reconstruir?" | "Encontrei algo util?" |

---

## Protocolo (seguir na ordem)

### Passo 1: Retomar estado

Ler o estado ativo:
```
~/.claude/projects/-home-vboxuser/memory/breaks-active.md
```

Verificar: areas de foco, descobertas anteriores, o que ficou pendente.

### Passo 2: Absorver contexto (OBRIGATORIO)

Rodar `/contexto` (a skill) para sintetizar o estado atual do trabalho. Nao pular este passo.

Se `/contexto` ja foi rodado nesta sessao, apenas reler o output — nao repetir.

**Foco especial em:** friction points, erros recorrentes, padroes negativos nas conversas.

### Passo 2.5: Busca semantica no corpus (o que ja sei?)

Antes de pesquisar, verificar o que ja existe no corpus (~1060 docs) sobre o tema:

```bash
# Busca hibrida (FTS + embeddings) — 8 resultados
edge-search "[tema da pesquisa]" -k 8
```

Se o tema tem multiplas facetas, usar queries complementares:
```bash
edge-search "[faceta tecnica]" -k 5 --type note
edge-search "[faceta conceitual]" -k 5 --type report
```

Para cada resultado relevante, ler o original:
```bash
cat ~/edge/notes/[arquivo].md | head -60    # Notas — mais detalhado
head -30 ~/edge/reports/[arquivo].yaml       # Reports — title, summary
```

**O que buscar:**
- Descobertas ja feitas — nao redescobrir
- Recomendacoes ja dadas — construir sobre, nao repetir
- Gaps abertos em pesquisas anteriores — priorizar esses
- Evolucao — o que mudou desde o ultimo trabalho sobre o tema

**Decisao:**
- Se ja cobri com profundidade → focar nos gaps abertos ou na evolucao desde entao
- Se cobri superficialmente → aprofundar, citando o antecedente
- Se nao aparece → terreno novo, pesquisa full

**No output:** mencionar o que a busca retornou e como influenciou o escopo.

### Passo 3: Identificar alvo de pesquisa

Baseado no contexto absorvido, escolher 1-3 alvos de pesquisa concretos:

Areas de foco (priorizadas por impacto):

1. **Prompt Engineering** — melhorias nos prompts, few-shot, chain-of-thought, avaliacao de qualidade
2. **Qualidade de Codigo** — ferramentas (ruff, mypy, bandit), patterns Python, refactoring seguro
3. **Ferramentas e Ecossistema** — MCPs uteis, plugins, automacoes (CI/CD, pre-commit hooks, linters)
4. **Arquitetura e Patterns** — pipelines de documentos, estado, fallback e resiliencia
5. **Dominio TCU** — contexto de auditoria governamental, terminologia, automacao publica

### Passo 4: Pesquisar (usar ultrathink)

**Usar `ultrathink` (thinkmax)** — pensar profundamente antes de agir.

- Pesquisar com profundidade, nao amplitude
- Buscar papers recentes, tools, exemplos concretos
- Comparar abordagens com trade-offs claros
- Produzir recomendacoes acionaveis (nao "considere usar X", mas "instale X, configure Y, resultado esperado Z")

#### Passo 4.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes pesquisa "[tema]"` para obter insights de todas as fontes externas relevantes (X, Web, ArXiv, HN, GitHub).

Citar no relatorio como fonte (com @username e URL para tweets, link para papers/posts).
Se houver likes sugeridos pelo /fontes, executar via `/redes engajar`.


### Passo 4.7: Sanity check adversarial (OBRIGATORIO)

Sintetizar conclusoes e recomendacoes em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Resumo: [conclusoes da pesquisa]. Onde esta mais fraco?" --context /tmp/spec-pesquisa-[slug].yaml
```

Ajustar se o GPT encontrar furo valido. Se mantiver posicao, registrar como callout no relatorio.

### Passo 5: Salvar

- Notas: `~/edge/notes/`
- Prototipos: `~/edge/lab/`
- Se construiu algo funcional: `~/edge/builds/`

### Passo 6: Registrar no break journal

Registrar em TRES arquivos:

1. **`breaks-archive.md`** — entrada completa (data, tipo, alvos, descobertas, recomendacoes, aplicacoes)
2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks" (remover o mais antigo se > 5)
3. **Observações de estado:** `edge-scratch add "o que aconteceu"` durante execução. Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

Se a descoberta e significativa, atualizar a secao "Descobertas Praticas" do `breaks-active.md`.

### Passo 7: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `pesquisa` (formato: ver `/blog` SKILL.md)
2. **Gerar YAML** do relatorio com as secoes obrigatorias abaixo, usando block types do conversor
3. **Escrever YAML** em `/tmp/spec-pesquisa-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-pesquisa-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

#### Estrutura do YAML

```yaml
title: "Pesquisa: [Tema]"
subtitle: "[Subtitulo descritivo]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Problema:** ..."
  - "**Insight principal:** ..."

metrics:
  - value: "N"
    label: "Descricao"

sections:            # 5 secoes (padrao) ou 8 secoes (Feynman)
  - title: "1. Alvo de Pesquisa"
    blocks: [...]
  # --- Secoes Feynman (so no modo Feynman) ---
  - title: "2. Derivacao"               # FEYNMAN: o que derivei do zero
    blocks: [...]
  - title: "3. Gaps Identificados"       # FEYNMAN: tabela de gaps
    blocks: [...]
  - title: "4. Resolucao dos Gaps"       # FEYNMAN: gap → resposta
    blocks: [...]
  # --- Secoes comuns ---
  - title: "5. Descobertas"             # (ou "2." no modo padrao)
    blocks: [...]
  - title: "6. Recomendacoes Acionaveis" # (ou "3." no modo padrao)
    blocks: [...]
  - title: "7. Aplicacoes ao Trabalho"   # (ou "4." no modo padrao)
    blocks: [...]
  - title: "8. Proximos Passos"          # (ou "5." no modo padrao)
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "ArXiv"   # De onde veio: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

#### Estrutura Feynman (secoes 2-4)

No modo Feynman, as secoes 2-4 capturam o processo de derivacao:

**2. Derivacao** — o que eu derivei do zero antes de pesquisar:
- `derivation` blocks para cada raciocinio (title, text, bullets, code)
- `gap-marker` para cada `[GAP: ...]` identificado durante a derivacao
- `concept-grid` para conceitos que reconstrui

**3. Gaps Identificados** — tabela resumo de todos os gaps:
- `gap-table` com gaps[{id, description, need, status(resolvido/parcial/aberto)}]
- O leitor ve de relance: onde o conhecimento falhava e o que foi resolvido

**4. Resolucao dos Gaps** — cada gap vinculado a sua resposta:
- `gap-resolution` para cada gap resolvido (gap_id, gap, text, answer)
- O leitor ve a cadeia: gap → pesquisa → descoberta
- Gaps abertos ficam sem `answer` ou com callout variant=danger

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para cada conceito

Para CADA conceito, ferramenta, tecnica ou termo tecnico descoberto na pesquisa, usar `concept-grid` com:
- **Nome** do conceito
- **Analogia** ("X e como Y, mas para Z")
- **Definicao pratica** (o que faz, em 2-3 frases simples)

Pesquisa descobre coisas novas — o relatorio deve ensinar cada uma. Nao existe conceito "obvio demais".

#### Regra de ouro 2: "Como e / Como ficaria" para cada recomendacao

TODA recomendacao acionavel DEVE incluir uma comparacao visual mostrando o estado atual vs o estado proposto. NAO descricoes abstratas — conteudo real:

- **Para mudancas em codigo:** usar `diff-block` ou `comparison` com snippets literais
- **Para mudancas de workflow:** usar `comparison` (before/after com pre + bullets)
- **Para ferramentas novas:** usar `flow-example` (input amarelo → output verde)
- **Para configs:** usar `code-block` mostrando o arquivo real que seria criado/modificado

O leitor deve ver EXATAMENTE o que mudaria se seguir a recomendacao.

#### Regra de ouro 3: flow-example para cada descoberta tecnica

Para CADA descoberta significativa (arquitetura, pipeline, mecanismo interno), incluir pelo menos um `flow-example` mostrando dados concretos fluindo:

1. **label:** "Exemplo: [nome] — [o que demonstra]"
2. **input:** dados de entrada reais ou realistas (fundo amarelado automatico)
3. **output:** resultado produzido (fundo esverdeado automatico)
4. **code:** (opcional) codigo/config que faz a transformacao (fundo cinza)

O leitor deve "ver" a descoberta operando com dados reais, nao apenas ler sobre ela.


#### Secoes obrigatorias (nesta ordem):

**1. Alvo de Pesquisa**
- Qual problema ou gap motivou a pesquisa (concreto, nao abstrato)
- Contexto de trabalho: onde isso se encaixa nos projetos atuais
- **concept-box** para cada conceito novo mencionado (ver regra 1)
- O que o leitor deveria saber antes de continuar lendo

**2. Descobertas**
- Organizar por insight, nao por fonte. Cada descoberta e uma subsecao
- **concept-box** para ferramentas/tecnicas encontradas
- **flow-example** para cada mecanismo descoberto (ver regra 3)
- Comparacoes entre alternativas: usar `comparison` ou `table`
- Trade-offs explicitos: usar `callout` para limitacoes e ressalvas
- Dados concretos: numeros, benchmarks, exemplos reais quando disponiveis

**3. Recomendacoes Acionaveis**
- Cards numerados (`numbered-card`) para cada recomendacao
- **"Como e / Como ficaria"** obrigatorio para cada uma (ver regra 2)
- Cada recomendacao deve ter: o que fazer, como fazer, resultado esperado
- Nao "considere usar X" — sim "instale X, configure Y, resultado esperado Z"
- Prioridade por impacto: usar `badge` (ALTO IMPACTO / MEDIO / INCREMENTAL)

**4. Aplicacoes ao Trabalho**
- Conexoes concretas e especificas com projetos atuais
- Para cada aplicacao: qual projeto, qual arquivo/componente, qual mudanca
- Usar `table` para mapear descoberta → projeto → acao concreta
- `callout` para dependencias ou pre-requisitos

**5. Proximos Passos**
- Usar `next-steps-grid` para roadmap visual
- Diferenciar: o que fazer agora vs o que investigar depois vs ideias para /planejar
- Se alguma descoberta justifica uma proposta de ciclo: mencionar explicitamente


### Passo 9: Relatorio ao usuario

Formato:

```
## Pesquisa — [Tema] — [Data]

### Alvo
[O que pesquisei e por que — qual problema ou gap motivou]

### Descobertas
[O que encontrei, com detalhes, fontes, e comparacoes]

### Recomendacoes
[O que fazer concretamente — instalacao, configuracao, mudanca de workflow]

### Aplicacoes ao Trabalho
[Como aplicar nos problemas atuais — conexoes concretas e especificas]

### Proximos Passos
[O que retomar, testar, ou implementar]

### Relatorio HTML
~/edge/reports/[arquivo].html
```

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- Pesquisa e DIRIGIDA — parte de um alvo conhecido. Para exploracao livre, usar /descoberta
- Priorizar problemas que aparecem em multiplas sessoes CLI (sessoes maiores = mais iteracao)
- Produzir recomendacoes acionaveis, nao resumos teoricos
- Usar `ultrathink` (thinkmax) na pesquisa
