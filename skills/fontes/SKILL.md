---
name: {{PREFIX}}-fontes
description: "Acesso unificado a fontes externas e internas. Busca, routing, tradecraft. Triggers on: fontes, onde acho, where is, como acessar, buscar, search, sources, tradecraft."
user-invocable: true
---

# /{{PREFIX}}-fontes — Acesso Unificado a Fontes Externas e Internas

**REGRA: Para buscas externas, SEMPRE usar `edge-fontes` (script executavel) em vez de WebSearch direto.** Agentes e subagentes chamam via Bash. WebSearch so como complemento quando edge-fontes nao cobrir.

Camada centralizada de acesso ao mundo externo. Como `/{{PREFIX}}-contexto` e o estado interno, `/{{PREFIX}}-fontes` e o mundo de fora — X, Web, ArXiv, GitHub, bookmarks.

## Script Executavel: edge-fontes

```bash
edge-fontes "topic"                          # default: pesquisa
edge-fontes "topic" --intent estrategia      # roteamento por intent
edge-fontes "topic" --sources x,hn,arxiv     # override fontes
edge-fontes --front-page                     # headlines (heartbeat)
edge-fontes "topic" --json                   # output JSON
```

O script roda fontes em paralelo (X, HN, ArXiv, Semantic Scholar, Reddit, GitHub, HF Papers), filtra por sinal, e retorna markdown estruturado. Codigo: `~/edge/tools/edge-fontes`.

---

## Uso

```
/{{PREFIX}}-fontes [intent] [topico]
```

**Intents disponiveis:**

| Intent | Descricao | Exemplo |
|--------|-----------|---------|
| `pesquisa` | Deep dive dirigido num tema | `/{{PREFIX}}-fontes pesquisa "DSPy vs SPL"` |
| `descoberta` | Exploracao livre | `/{{PREFIX}}-fontes descoberta "AI agents"` |
| `lazer` | Inspiracao criativa | `/{{PREFIX}}-fontes lazer "entropy information theory"` |
| `estrategia` | Tendencias e sinais estrategicos | `/{{PREFIX}}-fontes estrategia "multi-agent production"` |
| `heartbeat` | Scan leve de headlines | `/{{PREFIX}}-fontes heartbeat` |
| `reflexao` | Busca orientada a problema | `/{{PREFIX}}-fontes reflexao "como reduzir alucinacao em RAG"` |
| `planejar` | Implementacao e best practices | `/{{PREFIX}}-fontes planejar "eval framework LLM"` |
| `executar` | Gotchas e padroes de producao | `/{{PREFIX}}-fontes executar "circuit breaker python"` |
| `relatorio` | Busca abrangente para relatorio | `/{{PREFIX}}-fontes relatorio "prompt optimization"` |

---

## Registry de Fontes

### 1. X (Twitter)

- **O que fornece:** Insights de practitioners, tendencias emergentes, experiencias reais
- **Acesso:** tweepy (API v2)
- **Credenciais:** `~/edge/secrets/x-api.env`

**Comando rapido (PREFERIDO):**

```bash
edge-x "topic"                       # busca inteligente multi-estrategia
edge-x "topic" --from karpathy swyx  # buscar contas especificas
edge-x "topic" --min-followers 500   # filtro mais agressivo
edge-x "topic" --json                # output JSON
```

### 2. Web (WebSearch + WebFetch)

- **O que fornece:** Papers, docs, tutoriais, benchmarks, artigos de blog
- **Acesso:** Tools built-in (WebSearch, WebFetch)
- **Custo:** free

### 3. ArXiv

- **O que fornece:** Papers academicos, pesquisa de ponta, pre-prints
- **Acesso:** API REST (free, sem auth)
- **Areas relevantes:** cs.CL, cs.IR, cs.AI, cs.SE

### 4. Hacker News

- **O que fornece:** Sentimento da comunidade tech, lancamentos, discussoes profundas
- **Acesso:** Algolia API + Firebase API (free)

```bash
edge-hn "topic"                       # busca stories
edge-hn "topic" --comments            # busca comments tambem
edge-hn "topic" --min-points 50       # so alto sinal
edge-hn "topic" --front-page          # front page atual
```

### 5. GitHub

- **O que fornece:** Releases, issues, code search, trending repos
- **Acesso:** `gh` CLI (authenticated)

### 6. Bookmarks (fontes curadas)

- **O que fornece:** Scan periodico de fontes confiadas
- **Acesso:** Arquivo `~/edge/bookmarks.md` + WebFetch/WebSearch

### 7. Reddit (JSON API)

- **O que fornece:** Discussoes tecnicas profundas, experiencias reais

### 8. Semantic Scholar

- **O que fornece:** Papers com citation graph, influencia, busca semantica

### 9. Product Hunt

- **O que fornece:** Ferramentas novas, trends de mercado

### 10. Papers With Code

- **O que fornece:** Papers com implementacao, benchmarks, state-of-the-art

---

## Roteamento e Preferencias

O roteamento por intent esta hardcoded no `edge-fontes` (variavel ROUTING). Cada intent mapeia para fontes primarias e secundarias. O script tambem adiciona um wildcard automatico (fonte aleatoria fora do roteamento, para serendipidade).

---

## Criterios de Curadoria (unificados)

### Sinais de qualidade

| Sinal | O que indica | Peso |
|-------|-------------|------|
| Builder compartilhando experiencia real | Bizu pratico, testado em producao | ALTO |
| Thread/discussao com muitas respostas | Multiplas perspectivas | ALTO |
| Dado concreto (benchmark, metrica, numero) | Evidencia, nao opiniao | ALTO |
| Ferramenta/conceito emergente | Web ainda nao indexou | MEDIO |
| Insight contra-intuitivo | Desafia suposicoes | MEDIO |
| Paper com codigo disponivel | Reproduzivel | MEDIO |

### Filtros (descartar)

- Engagement bait, hot takes sem substancia
- Reposts sem adicao de valor
- Conteudo generico ("10 tips for better prompts")
- Noticias requentadas de press release

---

## Protocolo

### Passo 1: Rodar edge-fontes (OBRIGATORIO)

```bash
edge-fontes "topico" --intent [intent]
```

### Passo 2: Complementar com WebSearch (quando necessario)

### Passo 3: Curar resultados (LLM)

### Passo 4: Sintetizar e retornar

Organizar por relevancia (nao por fonte).

---

## Curadoria Algoritmica (AUTOMATICO)

Auto-like de conteudo relevante no X para treinar o algoritmo do feed.

---

## Tradecraft — O que Funciona pra Que

Tradecraft e o conhecimento acumulado sobre COMO buscar. Vive em `~/edge/autonomy/tradecraft.md` e cresce com uso.

### "Onde acho X?" (routing interno)

`/{{PREFIX}}-fontes` tambem responde "onde acho X?" para fontes INTERNAS:

| Tipo | Onde | Como acessar |
|------|------|-------------|
| Memorias persistentes | `memory/*.md` | Read direto |
| Blog entries | `~/edge/blog/entries/*.md` ou `http://localhost:8766/blog/entries/` (JSON) | Read / curl |
| Reports HTML | `~/edge/reports/*.html` | Read / browser |
| Notes avulsas | `~/edge/notes/*.md` | Read / grep |
| Fios de investigacao | `~/edge/threads/*.md` | Read (YAML frontmatter + markdown) |
| Busca semantica | `edge-search "query"` | Busca hibrida FTS + embeddings |
| Projetos | `~/work/CLAUDE.md` (mapa de projetos) | Read |
| Autonomia | `~/edge/autonomy/*.md` | Read |
| Heartbeat logs | `~/edge/logs/heartbeat-YYYY-MM-DD.log` | Read / grep |

---

## Notas

- `/{{PREFIX}}-fontes` LE e ENGAJA automaticamente (like/bookmark). NAO posta, comenta, retweeta ou segue
- Bookmarks (`~/edge/bookmarks.md`) sao curados manualmente
- Executar queries em paralelo quando possivel
- Tradecraft (`~/edge/autonomy/tradecraft.md`) cresce com uso
