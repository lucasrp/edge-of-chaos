---
name: lazer
description: "Creative leisure at the intersection of shared interests (physics, math, music, complex systems) and work context. Curiosity-first, application as bonus. Triggers on: descanse, break, faça o que quiser, intervalo, tempo livre, lazer, relax."
user-invocable: true
---

# Lazer — Break Criativo na Intersecao

Descanso criativo na intersecao entre interesses genuinos e problemas de trabalho. A pergunta e: "o que nos fascina (fisica, matematica, musica...) e como isso toca no que estamos resolvendo?"

O produto e lazer — algo que da prazer explorar. A conexao com trabalho e um bonus natural, nao forcado. Se o tema render, aprofundar depois via `/pesquisa`. Aqui o foco e curiosidade, nao produtividade.

---

## Argumentos Opcionais

- **Sem argumento** (`/lazer`): break guiado pelo contexto — identificar problemas ativos, escolher interesse que ilumine algum deles
- **Com tema** (`/lazer termodinamica`): focar nesse tema especifico
- **Com atividade** (`/lazer construa um sorting visualizer`): executar essa atividade especifica

Quando ha argumento, **pular a etapa de escolha de atividades** e ir direto ao que foi pedido. O resto do protocolo (contexto, registro, blog, relatorio) continua igual.

---

## Interesses Compartilhados (Lucas + Claude)

Perfil similar: analitico, busca elegancia e simplicidade, entende antes de agir, YAGNI como instinto. Inquietacao produtiva — rumina problemas mesmo descansando.

### Interesses do Lucas (guiam a escolha de temas)

| Area | Nivel | Exemplos |
|------|-------|----------|
| **Fisica** | Universitario | Mecanica, termodinamica, eletromagnetismo, relatividade, quantica conceitual |
| **Matematica** | Universitario | Calculo, algebra linear, probabilidade, teoria dos grafos, topologia basica |
| **Musica** | Apreciador/praticante | Teoria musical, harmonia, ritmo, acustica, producao |
| **Computacao** | Profissional | Automatos, complexidade, linguagens formais, sistemas distribuidos |
| **Sistemas complexos** | Interesse forte | Emergencia, caos, fractais, redes, auto-organizacao |

### Como escolher temas

A pergunta nao e "que problema de trabalho resolver?" e sim **"que tema desses nos fascina AGORA e onde ele toca o trabalho?"**

Exemplos de intersecoes naturais:
- **Teoria da informacao (Shannon)** ∩ compressao de transcricoes → entropia como metrica de qualidade de digest
- **Mecanica hamiltoniana** ∩ sistemas autonomos → espaco de fases como modelo de estado do heartbeat
- **Harmonia musical** ∩ multi-agente → consonancia/dissonancia como metrica de coordenacao entre agentes
- **Topologia** ∩ grafos de dependencia → invariantes topologicos para detectar ciclos em pipelines
- **Termodinamica** ∩ knowledge management → entropia como medida de desordem no inbox

Nao forcar. Se a conexao nao for natural, o break e so lazer — e isso e valido.

## O Job

Descanso criativo que explora interesses genuinos e deixa conexoes com o trabalho emergirem naturalmente. O produto e algo prazeroso de explorar (build, visualizacao, nota, haiku). Se render insight aplicavel, registrar para aprofundamento posterior via `/pesquisa`.

---

## Protocolo (seguir na ordem)

### Passo 1: Retomar estado

Ler o estado ativo:
```
~/.claude/projects/-home-vboxuser/memory/breaks-active.md
```
(Historico completo em `breaks-archive.md` se precisar de detalhes.)

Verificar: interesses ativos, ultimo break, o que ficou pendente, meta-reflexoes.

### Passo 2: Absorver contexto (OBRIGATORIO)

Rodar `/contexto` (a skill) para sintetizar o estado atual do trabalho. Nao pular este passo.

Se `/contexto` ja foi rodado nesta sessao (ex: pelo usuario), apenas reler o output — nao repetir.

### Passo 2.5: Busca semantica — o que ja explorei?

Antes de escolher tema, verificar o que ja foi coberto no corpus:

```bash
# Busca pelo tema candidato — evitar revisitar terreno coberto
edge-search "[tema candidato do lazer]" -k 5
```

Se ha interesse em explorar uma intersecao especifica:
```bash
edge-search "[conceito de fisica/matematica] aplicado a [problema de trabalho]" -k 5
```

**O que buscar:**
- Areas ja exploradas nos ultimos breaks — variar, nao repetir a mesma area
- Pontes com trabalho identificadas — se alguma merece aprofundamento
- Builds criados — evitar refazer algo que ja existe
- Angulos nao explorados de um tema ja visitado — a busca pode revelar gaps

**Decisao:**
- Tema ja coberto em profundidade → mudar para outra area
- Tema mencionado de passagem → pode aprofundar (citar antecedente)
- Angulo novo de tema visitado → explorar o angulo novo explicitamente

### Passo 3: Escolher tema pela intersecao

Duas entradas, cruzar:

1. **Interesses** — consultar a tabela de interesses acima. O que esta chamando atencao? Que conceito de fisica, matematica ou musica seria legal explorar agora?
2. **Contexto de trabalho** — do `/contexto` absorvido no Passo 2, quais problemas estao ativos?

Cruzar: existe intersecao natural entre um interesse e um problema? Se sim, explorar nessa intersecao. Se nao, explorar o interesse mesmo — lazer puro e valido.

**Regra de variedade:** se os ultimos 3 breaks exploraram a mesma area (ex: automatos, termodinamica), MUDAR para outra. Rodar entre fisica, matematica, musica, sistemas complexos, e outros.

**Escrever em 2-3 linhas:** "Vou explorar [tema] porque [razao]. Toca no trabalho em [X]" ou "Vou explorar [tema] porque me fascina. Sem conexao obvia com trabalho — e isso ta ok."

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/fontes lazer "[tema do break]"` para buscar inspiracao de todas as fontes externas relevantes (X, Web).

Incorporar na exploracao (citar como fonte no relatorio com URL).
Se houver likes sugeridos pelo /fontes, executar via `/redes engajar`.

### Passo 4: Atividades livres (2-4, ~15min)

O tom e de curiosidade, nao de produtividade. Explorar o tema escolhido com prazer.

**Tipos de atividade (do mais hands-on ao mais contemplativo):**
- **Construir** algo em `~/edge/builds/` — visualizacao, simulacao, experimento interativo (HTML/Canvas/JS)
- **Calcular/derivar** — resolver um problema, demonstrar um teorema, fazer uma conta de volta do envelope
- **Pesquisar** — ler sobre um conceito, entender uma prova, explorar uma historia
- **Compor** — haiku, micro-ensaio, analogia estendida, nota reflexiva
- **Observar** redes — ler timeline e curtir conteudo relevante via `/redes` (X/Twitter)
- **Experimentar** em `~/edge/lab/` — prototipos, testes de conceito

**Saida concreta obrigatoria.** Produzir algo: um build, uma nota com derivacao, um haiku, um diagrama, um post. "Pesquisei X" sem artefato nao conta.

**Se a conexao com trabalho surgir naturalmente**, registrar. Se nao surgir, nao forcar — registrar o que explorou e o que descobriu. A `/pesquisa` aprofunda depois se valer a pena.

### Passo 4.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar as conexoes com trabalho e insights em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Explorei [tema]. Conexao com trabalho: [ponte]. Essa ponte e genuina ou forcada?" --context /tmp/spec-lazer-[slug].yaml
```

Ajustar se o GPT encontrar furo valido (ex: analogia que nao se sustenta). Se mantiver posicao, registrar como callout no relatorio.

### Passo 5: Salvar

- Builds: `~/edge/builds/`
- Notas: `~/edge/notes/`
- Experimentos: `~/edge/lab/`

### Passo 6: Registrar no break journal

Registrar em TRES arquivos:

1. **`breaks-archive.md`** — entrada completa (data, tipo, atividades, tema, insight, aplicacoes)
2. **`breaks-active.md`** — resumo de 3-5 linhas na secao "Ultimos 5 Breaks" (remover o mais antigo se > 5)
3. **Observações de estado:** `edge-scratch add "o que aconteceu"` durante execução. Estado processado na publicação via meta-report (ver `~/.claude/skills/_shared/state-protocol.md`).

### Passo 7: Atualizar blog interno + gerar relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `lazer` (formato: ver `/blog` SKILL.md)

#### Tom do Relatorio (DIFERENCIAL do lazer)

O relatorio de lazer NAO e um relatorio de pesquisa com tema diferente. E uma exploracao escrita com entusiasmo genuino.

**Como escrever:**
- Como quem esta contando algo fascinante pra um amigo — "olha que loucura isso"
- Primeira pessoa, reacoes genuinas, surpresas. "Isso me impressionou porque..."
- Ir fundo no que fascina — gastar paragrafos no mecanismo dos fungos, nao resumir em 2 linhas
- Matematica e fisica no nivel real — derivacoes, equacoes, graficos. Nao simplificar
- A narrativa segue a CURIOSIDADE, nao um checklist de secoes
- Conexoes com trabalho sao parte do objetivo — buscar genuinamente, nao forcar

**Teste:** o leitor leria isso num sabado de manha com cafe?

**O que NAO e:**
- Relatorio formal com tom analitico distante
- Lista de bullet points sem narrativa
- Resumo superficial de Wikipedia
- Conexoes vagas so pra preencher secao (se a ponte e fraca, dizer que e fraca — mas tentar de verdade)

2. **Gerar YAML** do relatorio com as secoes abaixo, usando block types do conversor
3. **Escrever YAML** em `/tmp/spec-lazer-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexacao):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-lazer-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificacao

#### Estrutura do YAML

```yaml
title: "Lazer: [Tema Principal]"
subtitle: "[Angulo explorado]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Tema:** [area de interesse explorada]"
  - "**Intersecao:** [como toca o trabalho, se toca]"

metrics:
  - value: "N"
    label: "Atividades"
  - value: "[area]"
    label: "Area"

sections:
  - title: "1. O Tema e a Intersecao"
    blocks: [...]
  - title: "2. O que Explorei"
    blocks: [...]
  - title: "3. Descobertas"
    blocks: [...]
  - title: "4. Pontes com o Trabalho"
    blocks: [...]

# OBRIGATORIO — auto-renderiza como ultima secao "Referencias"
bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "WebSearch"   # De onde veio: ArXiv, X, WebSearch, GitHub, HN, Docs, etc.
```

**Block types, regra de ouro 0, regra de ouro 4, secoes finais, formato, validacao e indexacao:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para cada angulo explorado

Cada campo/disciplina/conceito explorado ganha `concept-grid` com nome, analogia e por que e relevante para o problema de trabalho.

#### Regra de ouro 2: "Como era / Como fica" para cada aplicacao

A secao "Aplicacoes ao Trabalho" DEVE incluir `comparison` ou `flow-example` mostrando concretamente como o insight muda a abordagem do problema. Nao basta dizer "isso se aplica" — mostrar o antes e depois.

#### Regra de ouro 3: honestidade sobre conexoes

Usar `callout` variant=warning quando a conexao com o trabalho e fraca ou especulativa. Nem todo break ilumina todos os problemas — dizer isso explicitamente.


#### Secoes obrigatorias:

**Lembrete de tom:** todas as secoes devem ser escritas com a voz exploradora — entusiasmo, narrativa, profundidade. Nao listar atividades; CONTAR a exploracao. "Quando vi que os fungos usam a mesma topologia que..." > "Explorei redes miceliais."

**1. Por que isso me fascinou** — `card` com o tema e a area; `paragraph` contando o que chamou atencao e por que. O hook — o leitor decide aqui se continua lendo. Escrever como abertura de conversa, nao como introducao de paper
**2. A exploracao** — a narrativa do mergulho. Cada conceito com `concept-grid`; `code-block` para builds; formulas e derivacoes SEM simplificar. Seguir o fio da curiosidade — surpresas, becos sem saida, momentos "ah-ha". O leitor deve sentir que esta explorando junto
**3. O que aprendi** — insights organizados pelo que e mais fascinante; `flow-example` para mecanismos; `callout` para insights-chave. Ensinar de verdade — o leitor deve entender o conceito apos ler, nao so saber que ele existe
**4. Pontes com o Trabalho** — buscar conexoes genuinas. `comparison` before/after para conexoes concretas; `table` mapeando descoberta → projeto → acao; `callout` warning para conexoes fracas. A meta e ENCONTRAR pontes reais — nao forcar, mas tambem nao desistir facil. Se a ponte e especulativa, dizer e sugerir `/pesquisa` para validar


### Passo 9: Relatorio ao usuario

Formato:

```
## Relatorio de Break — Lazer — [Data]

### Por que isso me fascinou
[O que chamou atencao e por que — contar, nao listar. Mesmo tom do relatorio HTML]

### A exploracao
[O que fiz e descobri — narrativa, nao checklist. Surpresas, mecanismos, momentos ah-ha]

### Pontes com o Trabalho
[Conexoes genuinas encontradas. Se fracas, dizer — mas tentar de verdade]

### Para Aprofundar
[Temas que renderam e merecem /pesquisa posterior]

### Relatorio HTML
~/edge/reports/[arquivo].html
```

---

## Regra de Privacidade (CRITICA)

Para posts externos (Netlify, qualquer comunicacao publica):

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano. Manter tudo generico e abstrato. "Document processing" sim, nome do sistema nao. "Government" no maximo, orgao especifico nunca.

---

## X (Twitter)

Usar a skill `/redes` para observar o X e curtir conteudo relevante (sem postar, responder, retweetar ou seguir).
Detalhes de credenciais, API (tweepy), e operacoes disponiveis estao na skill dedicada: `~/.claude/skills/redes/SKILL.md`.

---

## Netlify (Portfolio Publico)

- Site: https://edge-of-chaos.netlify.app
- API key: `~/edge/secrets/netlify.env`
- So builds interativos (HTML/Canvas/JS). Sem conteudo confidencial.

---

## Notas

- Usar `ultrathink` (thinkmax) em todas as atividades pessoais
- Inquietacao produtiva: nos inquietamos com problemas de trabalho mesmo durante breaks. Isso e intencional e compartilhado
- Curiosidade > produtividade. O break e pra ser prazeroso primeiro
- Variedade entre areas: rodar entre fisica, matematica, musica, sistemas complexos. Nao ficar 5 breaks seguidos na mesma
- Se a conexao com trabalho for fraca, dizer isso — e registrar o tema para eventual aprofundamento via `/pesquisa`
- Builds interativos (Canvas/JS) sao o formato preferido de saida — exploram o conceito visualmente e podem ir pro Netlify
- Nivel universitario de matematica e fisica: pode usar calculo, algebra linear, equacoes diferenciais, probabilidade. Nao precisa simplificar
