---
name: planejar
description: "Propose development cycles for new or existing projects. Analyzes context, creates detailed proposals, manages proposal state. Triggers on: planejar, plan project, propose, proposta, ciclo de desenvolvimento."
user-invocable: true
---

# Planejar — Propostas de Ciclos de Desenvolvimento

Analisar o que o agente tem feito (memoria, breaks, descobertas, projetos) e propor ciclos de desenvolvimento concretos. As propostas ficam persistidas como referencia para o usuario avaliar e decidir o que fazer.

---

## Argumentos Opcionais

- **Sem argumento** (`/planejar`): analisar contexto e propor autonomamente
- **Com tema** (`/planejar eval de prompts`): propor ciclo sobre esse tema
- **Com projeto** (`/planejar Doc_AssertIA`): propor ciclo para esse projeto existente
- **Status** (`/planejar status`): listar todas as propostas e seus estados

Exemplos:
- `/planejar` → analisa contexto, propoe algo relevante
- `/planejar blog dashboard` → propoe ciclo para nova feature no blog
- `/planejar assertia-multiagent` → propoe ciclo para o backend existente
- `/planejar status` → dashboard de propostas

---

## O Job

1. Entender o que esta acontecendo (contexto, memoria, pesquisas)
2. Identificar oportunidade (problema a resolver, ideia a concretizar, melhoria a implementar)
3. Elaborar proposta detalhada que se vende sozinha
4. Registrar como proposta persistente
5. Pronta para o usuario avaliar e decidir

---

## Estado Persistente

Arquivo: `~/.claude/projects/-home-vboxuser/memory/propostas.md`

Cada proposta tem um status:
- `[PROPOSTA]` — nova, aguardando avaliacao do usuario
- `[APROVADA]` — usuario avaliou e considerou viavel
- `[ARQUIVADA]` — descartada ou absorvida (com motivo)

---

## Protocolo (seguir na ordem)

### Desvio: `/planejar status`

Se o argumento for `status`, mostrar dashboard e parar:

```markdown
## Propostas — Status

### Pendentes ([PROPOSTA])
| # | Titulo | Tipo | Data | Origem |
|---|--------|------|------|--------|
| 1 | ...    | novo/existente | YYYY-MM-DD | [contexto/descoberta/pesquisa/manual] |

### Aprovadas ([APROVADA])
[Prontas para o usuario avaliar]

### Em Execucao ([EM EXECUCAO])
[Sendo implementadas agora]

### Historico
[Concluidas e arquivadas recentes]
```

---

### Passo 1: Rodar /contexto (OBRIGATORIO)

Executar a skill `/contexto` para obter scan cross-project completo. Nao pular este passo.

Se `/contexto` ja foi rodado nesta sessao (ex: pelo usuario ou heartbeat), apenas reler o output — nao repetir.

### Passo 1.5: Consultar relatorios anteriores

Verificar se existem relatorios anteriores sobre o mesmo projeto ou tema:

```bash
ls -lt ~/edge/reports/*.yaml 2>/dev/null | head -20
```

Para cada YAML com nome relevante (palavras-chave no slug), ler as primeiras ~30 linhas (title, subtitle, executive_summary). Se muito relevante, ler secoes especificas.

**O que buscar:**
- Propostas anteriores sobre o mesmo tema — evitar duplicar, construir sobre
- Pesquisas relacionadas — insights que informam a proposta
- Execucoes anteriores — o que ja foi implementado e qual foi o resultado
- Gaps abertos — oportunidades de retomar trabalho incompleto

**No output:** mencionar relatorios consultados e o que aproveitou/mudou.

### Passo 2: Absorver estado adicional

```bash
# Descobertas pendentes — novas areas exploradas
cat ~/.claude/projects/-home-vboxuser/memory/descobertas.md 2>/dev/null

# Propostas existentes — evitar duplicatas
cat ~/.claude/projects/-home-vboxuser/memory/propostas.md 2>/dev/null

# Projetos em labs — o que ja existe
ls -d ~/edge/labs/*/ 2>/dev/null
```

Usar `ultrathink` (thinkmax). Com o output do `/contexto` + as fontes acima, identificar:
- Problemas recorrentes que poderiam ser resolvidos com uma ferramenta
- Descobertas que poderiam virar projeto
- Sugestoes do CLAUDE.md nao executadas
- Gaps entre o que existe e o que seria util
- Oportunidades de automacao ou melhoria

### Passo 2.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes planejar "[tema da proposta]"` para obter experiencias praticas de implementacao de todas as fontes relevantes (Web, X, GitHub, HN).

Incorporar na proposta (riscos, decisoes de design, ferramentas alternativas) e citar no relatorio (com URL).

### Passo 3: Elaborar proposta

A proposta deve **se vender sozinha**. Quem ler (mesmo sem contexto) deve entender:
- O que e
- Por que importa
- Como funciona
- O que entrega
- Quanto custa (tempo, APIs, complexidade)

#### Para PROJETO EXISTENTE:

Criar `~/edge/propostas/proposta-[nome-slug].md`:

```markdown
# Proposta: [Titulo Claro e Descritivo]

## Contexto
[Situacao atual. O que existe. O que falta. Qual o problema ou oportunidade.
Contextualizar bem — a pessoa pode nao estar familiarizada com os detalhes.]

## O que Proponho
[Descricao concreta do que sera feito. Nao abstrair demais.
Mostrar exemplos de input/output quando possivel.]

## Por que Agora
[Por que este e o momento certo. O que mudou. O que ficou maduro.
Conexao com trabalho recente, descobertas, ou decisoes estrategicas.]

## Escopo do Ciclo
[O que esta DENTRO e o que esta FORA. Ser explicito sobre limites.]

### Entregas
1. [Entrega concreta 1 — arquivo, feature, ferramenta]
2. [Entrega concreta 2]
3. ...

### Nao-Entregas (explicitamente fora de escopo)
- [O que NAO sera feito neste ciclo]

## Plano de Execucao
[Passos concretos. Ordem. Dependencias entre passos.]

| Passo | Descricao | Estimativa |
|-------|-----------|------------|
| 1     | ...       | ~X min     |
| 2     | ...       | ~X min     |
| ...   | ...       | ...        |

## Riscos e Mitigacoes
| Risco | Probabilidade | Mitigacao |
|-------|--------------|-----------|
| ...   | Alta/Media/Baixa | ... |

## Custo Estimado
- APIs: $X.XX [detalhar]
- Infra: $X.XX [se houver]
- **Total: $X.XX**

## Criterios de Sucesso
[Como saber se o ciclo foi bem sucedido. Metricas concretas.]

## Conexoes
[Como se relaciona com outros projetos, descobertas, ou decisoes anteriores.]
```

#### Para PROJETO NOVO:

1. **Criar repositorio no GitHub:**

```bash
gh auth switch --user lucasrp
gh repo create lucasrp/[nome-do-projeto] --private --description "[descricao curta]"
git clone https://github.com/lucasrp/[nome-do-projeto].git ~/edge/labs/[nome-do-projeto]
gh auth switch --user lucasrp_TCU
```

2. **Criar README.md** no repo (`~/edge/labs/[nome-do-projeto]/README.md`):

```markdown
# [Nome do Projeto]

[Descricao em 1-2 paragrafos. Clara, direta, contextualizada.]

## Motivacao

[Por que este projeto existe. Qual problema resolve. Para quem.
Contextualizar bem — a pessoa pode nao estar familiarizada.]

## O que Faz

[Descricao funcional. Exemplos de uso. Input/output esperado.]

## Arquitetura

[Visao geral de como funciona. Stack. Dependencias.]

## Status

- [PROPOSTA] — Ciclo de desenvolvimento proposto, aguardando aprovacao.

## Roadmap

### Ciclo 1 (proposto)
- [ ] [Entrega 1]
- [ ] [Entrega 2]
- [ ] [Entrega 3]

## Custo Estimado
$X.XX por ciclo (APIs, infra).
```

3. **Criar proposta detalhada** em `~/edge/labs/[nome-do-projeto]/PROPOSTA.md` (mesmo formato do projeto existente acima, com todas as secoes).

4. **Commit + push:**

```bash
cd ~/edge/labs/[nome-do-projeto]
git add -A
git commit -m "proposta: [titulo] — ciclo de desenvolvimento proposto"
gh auth switch --user lucasrp
git push -u origin main
gh auth switch --user lucasrp_TCU
```

### Passo 3.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar a proposta em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Proposta: [o que]. Justificativa: [por que]. Escopo: [entregas]. Isso e viavel e vale o investimento?" --context ~/edge/propostas/proposta-[slug].md
```

Ajustar se o GPT encontrar furo valido (ex: escopo inflado, risco subestimado, alternativa mais simples). Se mantiver posicao, registrar como callout no relatorio.

### Passo 4: Registrar proposta

Adicionar no topo de `~/.claude/projects/-home-vboxuser/memory/propostas.md` (abaixo do header):

```markdown
---

## [YYYY-MM-DD] #N — [Titulo] [PROPOSTA]

**Tipo:** [novo | existente]
**Projeto:** [nome-do-repo ou projeto TCU]
**Origem:** [contexto | descoberta | pesquisa | manual | heartbeat]
**Custo estimado:** $X.XX
**Proposta em:** [caminho do arquivo .md com proposta completa]
**Resumo:** [2-3 frases — o que e, por que, o que entrega]
```

Se o arquivo nao existir, criar com:

```markdown
# Propostas de Desenvolvimento

Registro persistente de todas as propostas de ciclos de desenvolvimento.
Consultar com `/planejar status`.
```

O numero `#N` e sequencial — contar propostas existentes + 1.

### Passo 5: Registrar no break journal

Registrar em TRES arquivos:

1. **`breaks-archive.md`** — entrada completa:
```markdown
## [YYYY-MM-DD] Planejamento — [Titulo] [via heartbeat]
- **Tipo:** [novo | existente]
- **Projeto:** [nome]
- **Proposta em:** [caminho]
- **Status:** [PROPOSTA] — aguardando selecao
```

2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks" (remover o mais antigo se > 5)
3. **Observações de estado:** `edge-scratch add "o que aconteceu"` durante execução. Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

### Passo 6: Atualizar blog interno + gerar relatorio HTML pedagogico

1. Criar entry .md em `~/edge/blog/entries/` com tag `planejamento` (formato: ver `/blog` SKILL.md)

O relatorio HTML e o artefato principal da proposta. Deve ser **autoexplicativo** — quem ler sem contexto nenhum deve entender exatamente o que vai acontecer, o que precisa fornecer, e o que vai receber de volta.

**O leitor precisa saber exatamente o que vai mudar.** Nao basta descrever em abstrato — mostrar conteudo real: trechos de arquivos, snippets de codigo, outputs de terminal, antes/depois com dados concretos.

#### Template

2. **Gerar YAML** com as 6 secoes obrigatorias abaixo, usando os block types do conversor YAML→HTML
3. **Escrever YAML** em `/tmp/spec-planejar-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-planejar-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

#### Estrutura do YAML

```yaml
title: "Proposta: [Titulo]"
subtitle: "[Subtitulo]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Problema:** ..."
  - "**Solucao:** ..."

metrics:
  - value: "N"
    label: "Descricao"

sections:            # 6 secoes obrigatorias
  - title: "1. O que vai ser feito"
    blocks: [...]
  - title: "2. O que voce (usuario) precisa fornecer"
    blocks: [...]
  - title: "3. Workflow da execucao"
    blocks: [...]
  - title: "4. Resultados esperados"
    blocks: [...]
  - title: "5. Como os resultados serao comparados"
    blocks: [...]
  - title: "6. Raio-X: Cada peca em acao"
    blocks: [...]

additional_sections: # riscos, custos, conexoes
  - title: "Riscos e Mitigacoes"
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "WebSearch"   # De onde veio: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro: concept-box obrigatorio

Para CADA conceito novo introduzido no relatorio (ferramenta, tecnica, termo tecnico), usar um concept-box com:
- **Nome** do conceito
- **Analogia** ("X e como Y, mas para Z")
- **Definicao pratica** (o que faz, em 2-3 frases simples)

Nao existe conceito "obvio demais" para um concept-box. Na duvida, inclua.

#### Regra de ouro: "Como era / Como fica" obrigatorio

TODA proposta DEVE incluir uma subsecao "Como era / Como fica" na Secao 1 mostrando o CONTEUDO REAL que vai mudar. NAO descricoes abstratas — snippets literais:

- **Para mudancas em arquivos:** usar block type `diff-block` ou `comparison`
- **Para mudancas de workflow:** usar block type `comparison` (before/after com pre + bullets)
- **Para mudancas de codigo:** usar block type `diff-block` (insert/delete/context)
- **Para ferramentas novas:** usar block type `flow-example` (input amarelo → output verde)

O leitor deve ver EXATAMENTE o que muda, nao uma descricao do que muda.

#### Regra de ouro: "Pecas-chave do fluxo" obrigatorio

Para CADA etapa ou componente central da proposta, incluir um exemplo concreto de **input → output** mostrando dados reais (ou realistas) sendo transformados. O leitor deve "ver" o dado entrando e saindo de cada peca.

Padrao obrigatorio para cada peca-chave — usar block type `flow-example`:
1. **label:** "Exemplo: [nome da peca] — [descricao da transformacao]"
2. **input:** dados de entrada reais (fundo amarelado automatico)
3. **output:** resultado gerado (fundo esverdeado automatico)
4. **code:** (opcional) codigo/config da peca que faz a transformacao (fundo cinza)

Exemplos do tipo de pecas-chave que devem ter input→output:
- Texto corrido (transcricao, documento) → dados estruturados (JSON, tabela)
- Config declarativo (YAML, JSON) → o que ele produz quando executado
- Funcao/script → input que recebe e output que retorna
- Fixture de teste → resultado com assertions (PASS/FAIL/score)
- Tabela de comparacao mockup com dados ficticios mostrando baseline vs resultado

**Quanto mais pecas-chave com input→output concreto, melhor.** O leitor entende o pipeline "de dentro para fora" quando ve os dados fluindo, nao quando le descricoes abstratas. Se uma secao so tem texto corrido sem nenhum bloco de dados concretos, provavelmente falta uma peca-chave.


#### Secoes obrigatorias (nesta ordem):

**1. O que vai ser feito**
- Explicar o problema atual em termos concretos (o que doi, por que doi)
- Explicar a ferramenta/tecnica proposta como se o leitor nunca ouviu falar dela
- Nao assumir conhecimento previo — definir siglas, conceitos, frameworks
- **concept-box** para cada conceito novo (ver regra acima)
- **"Como era / Como fica"** com conteudo real (ver regra acima)
- Cards numerados (`data-iter`) para decompor o "o que" em partes digeríveis

**2. O que voce (usuario) precisa fornecer**
- Tabela de itens com colunas: #, item, esforco estimado, prioridade (badge: CRITICO/NECESSARIO/DESEJAVEL/CONDICIONAL), descricao curta
- **Template preenchido obrigatorio para cada item:** para cada coisa que o usuario precisa fornecer, mostrar um template com dados realistas num bloco `<pre>` formatado. O template deve incluir:
  - Formato exato esperado (markdown, JSON, YAML, checklist)
  - Dados de exemplo preenchidos (nao placeholders genericos — dados que parecem reais)
  - Caminho onde os dados provavelmente ja existem (`~/tcu/...`, banco de dados, etc.)
  - Alternativa se o usuario nao tiver: "Se nao tiver X, pode criar Y manualmente usando este formato"
- Callout claro diferenciando o que ja existe do que precisa ser criado
- Se nao precisa de nada: dizer explicitamente "execucao 100% autonoma"

**3. Workflow da execucao**
- Diagrama visual (numbered cards ou next-steps-grid) mostrando cada passo
- Para cada passo: o que entra, o que acontece, o que sai
- Indicar quais passos sao automaticos vs quais precisam de intervencao humana
- Estimativas de tempo por passo
- Dependencias entre passos (o que bloqueia o que)

**4. Resultados esperados**
- Tabela de entregas com colunas: #, nome da entrega, descricao (formato, tamanho estimado, o que contem)
- **Para cada entrega tecnica** (config, script, codigo, template): mostrar exemplo concreto do conteudo em bloco `<pre>` — o leitor deve ver como o arquivo vai parecer por dentro (YAML, Python, JSON, etc.)
- **Mockup de comparacao** quando houver baseline vs resultado: tabela com dados ficticios mostrando fixture × assertion com PASS/FAIL/scores, incluindo linha de score medio
- **Visao de ciclos futuros** quando aplicavel: tabela mostrando investimento decrescente a cada repeticao (o que e reutilizado vs o que e novo em cada ciclo)
- Criterios de sucesso em tabela com colunas: #, criterio, como medir — concretos e mensuraveis

**5. Como os resultados serao comparados**
- Metodologia de comparacao (o que e o baseline, o que e o otimizado)
- Metricas especificas que serao usadas (com definicao de cada uma)
- Como interpretar os resultados (o que significa "melhor", "pior", "igual")
- Exemplo visual de como a tabela de comparacao vai parecer (mockup com dados ficticios)
- O que acontece se o resultado for pior que o baseline

**6. Raio-X: Cada peca em acao** (secao pedagogica)
- Secao dedicada a mostrar cada componente/ferramenta do pipeline **funcionando** com dados concretos
- Diferente dos concept-boxes (que **definem**) e do "Como era / Como fica" (que mostra **mudanca de workflow**) — esta secao mostra cada peca **individualmente operando**
- Para cada peca do pipeline, incluir um mini-exemplo autocontido:
  - **O que entra:** dados de input reais (ou realistas) no formato exato
  - **O que a peca faz:** codigo/config/comando que processa (signature Python, YAML, CLI)
  - **O que sai:** output gerado pela peca, no formato exato
- Incluir diagrama ASCII do pipeline completo mostrando como as pecas se conectam, seguido de zoom em cada uma
- Analogias tecnicas onde aplicavel (ex: "Promptfoo = pytest para prompts", "Bridge = adaptador entre ecossistemas Node.js e Python")
- Se a proposta envolve ferramentas externas: incluir o comando de execucao real (ex: `promptfoo eval -c config.yaml --output report.html`)
- **Objetivo:** ao final desta secao, o leitor deve conseguir "simular mentalmente" o pipeline inteiro — saber o que cada peca recebe, faz, e produz


### Passo 8: Relatorio ao usuario

```
## Relatorio de Planejamento — [Data]

### Proposta
[Titulo e resumo — o que e, por que, o que entrega]

### Tipo
[Novo projeto | Iteracao em projeto existente]

### Escopo
[Entregas concretas do ciclo]

### Custo Estimado
$X.XX

### Proposta Completa
[Caminho do arquivo .md]

### Relatorio HTML
~/edge/reports/[arquivo].html

### Proximo Passo
Para ver todas as propostas: `/planejar status`
```

---

## Quando Usar

- **Via /heartbeat:** Quando contexto sugere oportunidade de projeto
- **Manualmente:** `/planejar` — "proponha um ciclo de desenvolvimento"
- **Com direcao:** `/planejar eval system` — "proponha ciclo sobre isso"
- **Status:** `/planejar status` — "quais propostas existem?"
- **Apos /pesquisa:** Quando pesquisa produziu recomendacoes que merecem proposta detalhada

---

## Regra de Isolamento (OBRIGATORIA)

**Propostas NUNCA sao criadas em diretorios de projeto (`~/tcu/*/`).**

Todas as propostas ficam em `~/edge/propostas/proposta-[nome-slug].md`.

Para **projetos novos:**
- Tudo em `~/edge/labs/[nome]/` (repo GitHub privado)
- Conta pessoal `lucasrp`, nunca conta de trabalho

**Arquivos de estado do sistema (excecao):**
- `~/.claude/projects/-home-vboxuser/memory/propostas.md`
- `~/.claude/projects/-home-vboxuser/memory/breaks-active.md`
- `~/.claude/projects/-home-vboxuser/memory/breaks-archive.md`
- `~/edge/blog/index.html`

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- A proposta E o entregavel — o valor e o documento, nao a implementacao
- A proposta deve se vender sozinha — quem ler sem contexto deve entender tudo
- Ser realista sobre escopo. Melhor um ciclo pequeno e factivel do que um ambicioso e impossivel
- Propostas podem ser arquivadas sem implementacao — isso e normal, nao e desperdicio
- Usar `ultrathink` (thinkmax) na elaboracao da proposta
