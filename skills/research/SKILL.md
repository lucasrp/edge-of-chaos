---
name: ed-research
description: "Deep dive research on a specific topic or problem. Directed study with actionable output. Triggers on: research, pesquise, estude, research, deep dive, aprofunde, feynman, entenda, derive, first principles, explique de verdade."
user-invocable: true
---

# Pesquisa — Deep Dive Dirigido

Sei O QUE quero aprender — preciso aprofundar. Pesquisa focada num tema, ferramenta, ou problema especifico. Diferente da /ed-discovery (que explora livremente), a /ed-research parte de um alvo claro.

Exemplos: "/ed-research DSPy", "/ed-research como reduzir custo de tokens", "/ed-research padroes de pipeline".

---

## Argumentos Opcionais

- **Sem argumento** (`/ed-research`): identificar alvo automaticamente a partir de friction points do context
- **Com tema** (`/ed-research DSPy`): researchr esse tema em profundidade
- **Com problema** (`/ed-research como otimizar o fluxo do pipeline`): researchr solucao para esse problema
- **Modo Feynman** (`/ed-research feynman backpropagation` ou `/feynman X`): entendimento profundo — derivar antes de researchr, ensinar para testar entendimento, rastrear gaps

Quando ha argumento, **pular a etapa de identificacao de alvo** e ir direto ao que foi pedido.

### Modo Feynman

Ativado quando o argumento contem "feynman", ou quando o trigger e `/feynman`, `entenda`, `derive`, `explique de verdade`.

Muda o Passo 3: em vez de researchr direto, segue o ciclo:

1. **Derivar primeiro** — antes de buscar qualquer fonte, tentar reconstruir o conceito do zero. Onde trava? Anotar como `[GAP: ...]`
2. **Pesquisar so os gaps** — nao fazer survey geral. Buscar exatamente o que faltou na derivacao
3. **Ensinar** — escrever a explicacao como se ensinasse a alguem inteligente sem context. Sem jargao. Com analogias. Com mecanica. Com limites
4. **Verificar gaps** — reler com olho critico. Onde ficou vago? Marcar `[AINDA NAO ENTENDI: ...]`. Se houver gaps, voltar ao passo 2 (max 2 iteracoes)

O output do modo Feynman e uma **explicacao autocontida** em vez de recomendacoes acionaveis. O report usa `comparison` antes/depois (entendimento superficial → profundo) e a explicacao e a secao central.

---

## O Job

Aprofundar num tema especifico e produzir recomendacoes acionaveis (modo padrao) ou entendimento profundo (modo Feynman).

| | /ed-research (padrao) | /ed-research feynman | /ed-discovery |
|---|---|---|---|
| **Pergunta** | "O que fazer sobre X?" | "Entendo X de verdade?" | "O que nao sei que nao sei?" |
| **Metodo** | Buscar, comparar, recomendar | Derivar, ensinar, rastrear gaps | Explorar livremente |
| **Output** | Recomendacoes acionaveis | Explicacao autocontida + gaps | Ferramenta/conceito novo |
| **Teste** | "Sei o que fazer?" | "Consigo reconstruir?" | "Encontrei algo util?" |

---

## Ativação de Contexto

**Seguir `~/edge/config/pre-skill.md` — quem eu sou, o que estou fazendo, o que absorver.**

---

## Protocolo (seguir na ordem)

### Passo 1: Busca semantica no corpus (o que ja sei?)

Antes de researchr, verificar o que ja existe no corpus (~1060 docs) sobre o tema:

```bash
# Busca hibrida (FTS + embeddings) — 8 resultados
edge-search "[tema da research]" -k 8
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
- Gaps abertos em researchs anteriores — priorizar esses
- Evolucao — o que mudou desde o ultimo trabalho sobre o tema

**Decisao:**
- Se ja cobri com profundidade → focar nos gaps abertos ou na evolucao desde entao
- Se cobri superficialmente → aprofundar, citando o antecedente
- Se nao aparece → terreno novo, research full

**No output:** mencionar o que a busca retornou e como influenciou o escopo.

### Passo 2: Identificar alvo de research

Baseado no context absorvido, escolher 1-3 alvos de research concretos:

Areas de foco (priorizadas por impacto):

1. **Prompt Engineering** — melhorias nos prompts, few-shot, chain-of-thought, avaliacao de qualidade
2. **Qualidade de Codigo** — ferramentas (ruff, mypy, bandit), patterns Python, refactoring seguro
3. **Ferramentas e Ecossistema** — MCPs uteis, plugins, automacoes (CI/CD, pre-commit hooks, linters)
4. **Arquitetura e Patterns** — pipelines de documentos, status, fallback e resiliencia
5. **Dominio Aplicado** — context do dominio de trabalho, terminologia, automacao de processos

### Passo 3: Pesquisar (usar ultrathink)

**Usar `ultrathink` (thinkmax)** — pensar profundamente antes de agir.

- Pesquisar com profundidade, nao amplitude
- Buscar papers recentes, tools, exemplos concretos
- Comparar abordagens com trade-offs claros
- Produzir recomendacoes acionaveis (nao "considere usar X", mas "instale X, configure Y, resultado esperado Z")

#### Passo 3.5: Buscar sources externas (OBRIGATORIO)

Rodar `/ed-sources research "[tema]"` para obter insights de todas as sources externas relevantes (X, Web, ArXiv, HN, GitHub).

Citar no report como fonte (com @username e URL para tweets, link para papers/posts).
Se houver likes sugeridos pelo /ed-sources, execute via `/redes engajar`.


### Passo 3.7: Sanity check adversarial (OBRIGATORIO)

Sintetizar conclusoes e recomendacoes em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Resumo: [conclusoes da research]. Onde esta mais fraco?" --context /tmp/spec-research-[slug].yaml
```

Ajustar se o GPT encontrar furo valido. Se mantiver posicao, registrar como callout no report.

### Passo 4: Salvar

- Notas: `~/edge/notes/`
- Prototipos: `~/edge/lab/`
- Se construiu algo funcional: `~/edge/builds/`

### Passo 5: Registrar no break journal

Registrar em TRES arquivos:

1. **`breaks-archive.md`** — entrada completa (data, tipo, alvos, discoverys, recomendacoes, aplicacoes)
2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks" (remover o mais antigo se > 5)
3. **Observações de status:** `edge-scratch add "o que aconteceu"` durante execução. Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

Se a discovery e significativa, atualizar a secao "Descobertas Praticas" do `breaks-active.md`.

### Passo 6: Atualizar blog interno + gerar report HTML

**Seguir `~/.claude/skills/_shared/state-protocol.md` para gestão de status.**

1. Criar entry .md em `~/edge/blog/entries/` com tag `research` (formato: ver `/ed-blog` SKILL.md)
2. **Gerar YAML** do report com as secoes obrigatorias abaixo, usando block types do conversor
3. **Escrever YAML** em `/tmp/spec-research-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-status ~/edge/blog/entries/<arquivo>.md /tmp/spec-research-[slug].yaml
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

**2. Derivacao** — o que eu derivei do zero antes de researchr:
- `derivation` blocks para cada raciocinio (title, text, bullets, code)
- `gap-marker` para cada `[GAP: ...]` identificado durante a derivacao
- `concept-grid` para conceitos que reconstrui

**3. Gaps Identificados** — tabela resumo de todos os gaps:
- `gap-table` com gaps[{id, description, need, status(resolvido/parcial/aberto)}]
- O leitor ve de relance: onde o conhecimento falhava e o que foi resolvido

**4. Resolucao dos Gaps** — cada gap vinculado a sua resposta:
- `gap-resolution` para cada gap resolvido (gap_id, gap, text, answer)
- O leitor ve a cadeia: gap → research → discovery
- Gaps abertos ficam sem `answer` ou com callout variant=danger

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para cada conceito

Para CADA conceito, ferramenta, tecnica ou termo tecnico descoberto na research, usar `concept-grid` com:
- **Nome** do conceito
- **Analogia** ("X e como Y, mas para Z")
- **Definicao pratica** (o que faz, em 2-3 frases simples)

Pesquisa descobre coisas novas — o report deve ensinar cada uma. Nao existe conceito "obvio demais".

#### Regra de ouro 2: "Como e / Como ficaria" para cada recomendacao

TODA recomendacao acionavel DEVE incluir uma comparacao visual mostrando o status atual vs o status proposto. NAO descricoes abstratas — conteudo real:

- **Para mudancas em codigo:** usar `diff-block` ou `comparison` com snippets literais
- **Para mudancas de workflow:** usar `comparison` (before/after com pre + bullets)
- **Para ferramentas novas:** usar `flow-example` (input amarelo → output verde)
- **Para configs:** usar `code-block` mostrando o arquivo real que seria criado/modificado

O leitor deve ver EXATAMENTE o que mudaria se seguir a recomendacao.

#### Regra de ouro 3: flow-example para cada discovery tecnica

Para CADA discovery significativa (arquitetura, pipeline, mecanismo interno), incluir pelo menos um `flow-example` mostrando dados concretos fluindo:

1. **label:** "Exemplo: [nome] — [o que demonstra]"
2. **input:** dados de entrada reais ou realistas (fundo amarelado automatico)
3. **output:** resultado produzido (fundo esverdeado automatico)
4. **code:** (opcional) codigo/config que faz a transformacao (fundo cinza)

O leitor deve "ver" a discovery operando com dados reais, nao apenas ler sobre ela.


#### Secoes obrigatorias (nesta ordem):

**1. Alvo de Pesquisa**
- Qual problema ou gap motivou a research (concreto, nao abstrato)
- Contexto de trabalho: onde isso se encaixa nos projetos atuais
- **concept-box** para cada conceito novo mencionado (ver regra 1)
- O que o leitor deveria saber antes de continuar lendo

**2. Descobertas**
- Organizar por insight, nao por fonte. Cada discovery e uma subsecao
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
- Usar `table` para mapear discovery → projeto → acao concreta
- `callout` para dependencias ou pre-requisitos

**5. Proximos Passos**
- Usar `next-steps-grid` para roadmap visual
- Diferenciar: o que fazer agora vs o que investigar depois vs ideias para /ed-planner
- Se alguma discovery justifica uma proposta de ciclo: mencionar explicitamente


### Passo 7: Relatorio ao usuario

Formato:

```
## Pesquisa — [Tema] — [Data]

### Alvo
[O que pesquisei e por que — qual problema ou gap motivou]

### Descobertas
[O que encontrei, com detalhes, sources, e comparacoes]

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

## Pós-execução

**Seguir `~/edge/config/post-skill.md` para ações pós-publicação.**

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- Pesquisa e DIRIGIDA — parte de um alvo conhecido. Para exploracao livre, usar /ed-discovery
- Priorizar problemas que aparecem em multiplas sessoes CLI (sessoes maiores = mais iteracao)
- Produzir recomendacoes acionaveis, nao resumos teoricos
- Usar `ultrathink` (thinkmax) na research
