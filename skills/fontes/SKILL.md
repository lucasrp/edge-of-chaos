---
name: fontes
description: "Acesso unificado a fontes externas e internas. Busca, routing, tradecraft. Triggers on: fontes, onde acho, where is, como acessar, buscar, search, sources, tradecraft."
user-invocable: true
---

# /fontes — Acesso Unificado a Fontes Externas e Internas

**REGRA: Para buscas externas, SEMPRE usar `edge-fontes` (script executável) em vez de WebSearch direto.** Agentes e subagentes chamam via Bash. WebSearch só como complemento quando edge-fontes não cobrir.

Camada centralizada de acesso ao mundo externo. Como `/contexto` e o estado interno, `/fontes` e o mundo de fora — X, Web, ArXiv, GitHub, AssertIA, bookmarks.

## Script Executável: edge-fontes

```bash
edge-fontes "topic"                          # default: pesquisa
edge-fontes "topic" --intent estrategia      # roteamento por intent
edge-fontes "topic" --sources x,hn,arxiv     # override fontes
edge-fontes --front-page                     # headlines (heartbeat)
edge-fontes "topic" --json                   # output JSON
```

O script roda fontes em paralelo (X, HN, ArXiv, Semantic Scholar, Reddit, GitHub, HF Papers), filtra por sinal, e retorna markdown estruturado. Código: `~/edge/tools/edge-fontes`.

Qualquer skill chama `/fontes` com um intent e topico. `/fontes` roda edge-fontes, adiciona curadoria LLM, e retorna.

---

## Uso

```
/fontes [intent] [topico]
```

**Intents disponiveis:**

| Intent | Descricao | Exemplo |
|--------|-----------|---------|
| `pesquisa` | Deep dive dirigido num tema | `/fontes pesquisa "DSPy vs SPL"` |
| `descoberta` | Exploracao livre, encontrar coisas novas | `/fontes descoberta "AI agents"` |
| `lazer` | Inspiracao criativa | `/fontes lazer "entropy information theory"` |
| `estrategia` | Tendencias e sinais estrategicos | `/fontes estrategia "multi-agent production"` |
| `heartbeat` | Scan leve de headlines | `/fontes heartbeat` |
| `reflexao` | Busca orientada a problema | `/fontes reflexao "como reduzir alucinacao em RAG"` |
| `planejar` | Implementacao e best practices | `/fontes planejar "eval framework LLM"` |
| `executar` | Gotchas e padroes de producao | `/fontes executar "circuit breaker python"` |
| `relatorio` | Busca abrangente para relatorio | `/fontes relatorio "prompt optimization"` |

Quando chamado sem intent, inferir do contexto da skill chamadora.

---

## Registry de Fontes

### 1. X (Twitter)

- **O que fornece:** Insights de practitioners, tendencias emergentes, experiencias reais, o que a web tradicional ainda nao indexou
- **Acesso:** tweepy (API v2)
- **Credenciais:** `~/edge/secrets/x-api.env`
- **Custo:** Pay-per-use (~$0.02-0.05/search, ~$0.005/read, ~$0.01/profile)
- **Rate limits:** 60 searches/15min, 15 timeline/15min, 300 user lookups/15min
- **Username:** `@edge_of_chaos__` | **User ID:** `2025643124668993536`

**Comando rapido (PREFERIDO):**

```bash
edge-x "topic"                       # busca inteligente multi-estrategia
edge-x "topic" --from karpathy swyx  # buscar contas especificas
edge-x "topic" --min-followers 500   # filtro mais agressivo
edge-x "topic" --json                # output JSON para processamento
```

O `edge-x` faz busca multi-estrategia (broad + practitioner terms + trusted accounts), filtra por qualidade (followers >= 100 OR engagement >= 2), e ordena por sinal.

**Trusted accounts hardcoded:** karpathy, swyx, simonw, jxnlco, hwchase17, AnthropicAI, OpenAI, alexalbert__, DrJimFan, eugeneyan, shreyar, jerryjliu0, GregKamradt e outros. Editaveis em `~/edge/tools/edge-x`.

**Operadores de query:** `-is:retweet`, `lang:en`, `has:links`, `has:media`
**NAO usar:** `min_faves`, `min_retweets`, `sample:` (requerem Pro tier $5000/mo)

---

### 2. Web (WebSearch + WebFetch)

- **O que fornece:** Papers, docs, tutoriais, benchmarks, artigos de blog, Stack Overflow
- **Acesso:** Tools built-in (WebSearch, WebFetch)
- **Credenciais:** nenhuma
- **Custo:** free
- **Limite:** WebFetch falha em URLs autenticadas (Google Docs, Confluence, Jira)

**Como usar:**
- `WebSearch` para queries amplas
- `WebFetch` para ler URLs especificas (papers, docs, blog posts)

---

### 3. ArXiv

- **O que fornece:** Papers academicos, pesquisa de ponta, pre-prints
- **Acesso:** API REST (free, sem auth)
- **Credenciais:** nenhuma
- **Custo:** free
- **Areas relevantes:** cs.CL (Computation and Language), cs.IR (Information Retrieval), cs.AI, cs.SE (Software Engineering)

**Helper — ArXiv Search:**

```bash
python3 << 'PYEOF'
import urllib.request, urllib.parse, xml.etree.ElementTree as ET

QUERY = 'all:"TOPIC"'  # ou cat:cs.CL AND all:"TOPIC"
url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(QUERY)}&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"

resp = urllib.request.urlopen(url)
root = ET.fromstring(resp.read())
ns = {'a': 'http://www.w3.org/2005/Atom'}

for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
    published = entry.find('a:published', ns).text[:10]
    summary = entry.find('a:summary', ns).text.strip()[:200].replace('\n', ' ')
    link = entry.find('a:id', ns).text
    authors = [a.find('a:name', ns).text for a in entry.findall('a:author', ns)]
    print(f"\n[{published}] {title}")
    print(f"  Autores: {', '.join(authors[:3])}{'...' if len(authors) > 3 else ''}")
    print(f"  {summary}...")
    print(f"  URL: {link}")
PYEOF
```

---

### 4. Hacker News

- **O que fornece:** Sentimento da comunidade tech, lancamentos, discussoes tecnicas profundas, insights de practitioners em comments
- **Acesso:** Algolia API + Firebase API (free, sem auth)
- **Credenciais:** nenhuma
- **Custo:** free

**Comando rapido (PREFERIDO):**

```bash
edge-hn "topic"                       # busca stories por relevancia
edge-hn "topic" --comments            # busca comments tambem (insights buried in threads)
edge-hn "topic" --min-points 50       # so stories com alto sinal
edge-hn "topic" --days 7              # ultimos 7 dias
edge-hn "topic" --front-page          # tambem mostra front page atual
edge-hn "topic" --json                # output JSON para processamento
```

O `edge-hn` busca via Algolia (stories + comments), filtra por pontos e data, ordena por sinal (points + comments), e mostra URLs do HN e do artigo original. Comments sao limpos de HTML e truncados.

**Front page standalone:** `edge-hn --front-page` (sem topico — so top 10 atual)

---

### 5. GitHub

- **O que fornece:** Releases de projetos, issues, code search, trending repos
- **Acesso:** `gh` CLI (authenticated)
- **Credenciais:** keyring (lucasrp personal, lucasrp_TCU enterprise)
- **Custo:** free

**Operacoes uteis:**

```bash
# Releases recentes de um projeto
gh release list --repo stanfordnlp/dspy --limit 5

# Search repos por tema
gh search repos "prompt evaluation" --sort stars --limit 10

# Search code
gh search code "RAG pipeline" --language python --limit 10

# Issues/PRs de um repo
gh issue list --repo stanfordnlp/dspy --state open --sort updated --limit 10

# Trending (via web)
# WebFetch https://github.com/trending/python?since=weekly
```

---

### 6. AssertIA / Azure

- **O que fornece:** Dados de uso da plataforma AssertIA — sessoes, mensagens, documentos, feedback dos usuarios, estatisticas
- **Acesso:** SSH para VM Azure (`assertia-vm-dev`) + anonymizer.py
- **Credenciais:** SSH key configurada para `assertia-vm-dev`
- **Custo:** free
- **Pre-requisitos:** Proxy rodando (`mise run proxy:status` no assertia-mise), anonymizer.py deployado

**Modos disponiveis:**

| Modo | Comando | Retorna |
|------|---------|---------|
| overview | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py overview'` | Totais, datas, usuarios unicos |
| sessions | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py sessions'` | Lista de sessoes anonimizadas |
| messages | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py messages <session_id>'` | Mensagens de uma sessao |
| documents | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py documents <session_id>'` | Documentos de uma sessao |
| feedback | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py feedback'` | Feedbacks anonimizados |
| usage | `ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py usage'` | Stats por dia/task/modelo |

**Output:** Sempre JSON. Campos anonimizados: `<<TCU_PROCESS_1>>`, `<<CPF_1>>`, `<<PESSOA_1>>`, `<<ORGAO_1>>`, `<<ID_xxxxxxxx>>`.

**NUNCA** acessar o banco diretamente — sempre via anonymizer.py na VM. PII nunca transita pela rede.

---

### 8. Bookmarks (fontes curadas)

- **O que fornece:** Scan periodico de fontes confiadas — headlines, releases, novidades
- **Acesso:** Arquivo `~/edge/bookmarks.md` + WebFetch/WebSearch
- **Custo:** varies (free para maioria)

O arquivo `~/edge/bookmarks.md` contem a lista curada. Formato:

```markdown
# Bookmarks — Fontes Curadas

## Papers & Research
- ArXiv cs.CL: https://arxiv.org/list/cs.CL/recent
- ArXiv cs.IR: https://arxiv.org/list/cs.IR/recent
- Semantic Scholar: https://www.semanticscholar.org/

## Tech News
- HN front page: https://news.ycombinator.com/
- HN "Show HN": https://news.ycombinator.com/show

## Releases (projetos acompanhados)
- DSPy: stanfordnlp/dspy
- LangGraph: langchain-ai/langgraph
- promptfoo: promptfoo/promptfoo
- CrewAI: crewAIInc/crewAI

## X Accounts (perfis builder)
[Descobertos via /redes — adicionados conforme seguimos]

## Blogs
[Adicionados conforme descobrimos fontes confiadas]
```

Usar `gh release list` para repos, `WebFetch` para paginas, ArXiv helper para papers.

---

### 9. Reddit (JSON API)

- **O que fornece:** Discussoes tecnicas profundas, experiencias reais, debates entre practitioners
- **Acesso:** JSON API publica (append `.json` a qualquer URL Reddit)
- **Credenciais:** nenhuma
- **Custo:** free
- **Subreddits relevantes:** r/MachineLearning, r/LocalLLaMA, r/ClaudeAI, r/LangChain, r/ArtificialIntelligence

**Helper — Reddit Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

SUBREDDIT = 'MachineLearning'  # ou LocalLLaMA, ClaudeAI, LangChain
QUERY = 'TOPIC'
url = f"https://www.reddit.com/r/{SUBREDDIT}/search.json?q={urllib.parse.quote(QUERY)}&restrict_sr=1&sort=relevance&t=month&limit=10"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for post in data.get('data', {}).get('children', []):
    d = post['data']
    score = d.get('score', 0)
    comments = d.get('num_comments', 0)
    title = d.get('title', '')[:120]
    url = f"https://www.reddit.com{d.get('permalink', '')}"
    print(f"\n[{score}pts {comments}c] {title}")
    print(f"  URL: {url}")
PYEOF
```

**Variante — Hot posts (sem query):**
```bash
# Substituir search.json por hot.json:
# https://www.reddit.com/r/MachineLearning/hot.json?limit=10
```

---

### 10. Semantic Scholar

- **O que fornece:** Papers com citation graph, influencia, areas correlatas, busca semantica
- **Acesso:** Free REST API (api.semanticscholar.org)
- **Credenciais:** nenhuma (rate limit generoso: 100 req/5min sem key)
- **Custo:** free

**Helper — Semantic Scholar Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

QUERY = 'TOPIC'
fields = 'title,year,citationCount,influentialCitationCount,authors,url,tldr'
url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(QUERY)}&limit=10&fields={fields}"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for paper in data.get('data', []):
    title = paper.get('title', '')
    year = paper.get('year', '?')
    cites = paper.get('citationCount', 0)
    influential = paper.get('influentialCitationCount', 0)
    authors = ', '.join(a['name'] for a in (paper.get('authors') or [])[:3])
    tldr = (paper.get('tldr') or {}).get('text', '')[:150]
    url = paper.get('url', '')
    print(f"\n[{year}, {cites} cites, {influential} influential] {title}")
    print(f"  Autores: {authors}")
    if tldr: print(f"  TL;DR: {tldr}")
    print(f"  URL: {url}")
PYEOF
```

**Vantagem sobre ArXiv:** busca semantica (nao so keyword), citation graph, campo `tldr` gerado por IA, `influentialCitationCount` filtra papers que realmente impactaram o campo.

---

### 11. Product Hunt

- **O que fornece:** Ferramentas novas, trends de mercado, o que builders estao lancando
- **Acesso:** WebFetch (API requer OAuth — usar scraping leve)
- **Credenciais:** nenhuma
- **Custo:** free

**Como usar:**

```bash
# Via WebSearch (mais confiavel que scraping direto)
# WebSearch "site:producthunt.com [TOPIC] 2026"
```

Ou WebFetch em paginas de topico especifico. Nao tem helper script porque a API publica foi deprecada — WebSearch e suficiente para encontrar lancamentos relevantes.

---

### 12. Blogs Primarios (Anthropic, OpenAI, Google DeepMind)

- **O que fornece:** Fontes primarias de pesquisa, lancamentos, mudancas de API, visao estrategica
- **Acesso:** WebFetch nas URLs dos blogs
- **Credenciais:** nenhuma
- **Custo:** free
- **URLs:**
  - Anthropic: `https://www.anthropic.com/research`
  - OpenAI: `https://openai.com/blog`
  - Google DeepMind: `https://deepmind.google/discover/blog/`

**Como usar:**

```bash
# Via WebSearch para novidades recentes
# WebSearch "site:anthropic.com/research [TOPIC]"
# WebSearch "site:openai.com/blog [TOPIC]"

# Ou WebFetch direto no blog para scan de headlines
# WebFetch https://www.anthropic.com/research "listar titulos e datas dos ultimos 10 posts"
```

**Quando consultar:** pesquisa (fontes primarias), estrategia (sinais de mudanca), heartbeat (releases).

---

### 13. Papers With Code

- **O que fornece:** Papers com implementacao, benchmarks, state-of-the-art por task, trending papers
- **Acesso:** Free REST API (paperswithcode.com/api/v1)
- **Credenciais:** nenhuma
- **Custo:** free

**Helper — Papers With Code Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

QUERY = 'TOPIC'
url = f"https://paperswithcode.com/api/v1/search/?q={urllib.parse.quote(QUERY)}"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for item in data.get('results', [])[:10]:
    title = item.get('paper', {}).get('title', '') if item.get('paper') else item.get('title', '')
    url = item.get('paper', {}).get('url_abs', '') if item.get('paper') else ''
    repo = item.get('repository', {}).get('url', '') if item.get('repository') else ''
    stars = item.get('repository', {}).get('stars', 0) if item.get('repository') else 0
    print(f"\n{title}")
    if url: print(f"  Paper: {url}")
    if repo: print(f"  Code: {repo} ({stars} stars)")
PYEOF
```

**Variante — Trending:**
```bash
# WebFetch https://paperswithcode.com/trending "listar os 10 papers trending com links e stars"
```

**Vantagem sobre ArXiv/Semantic Scholar:** cada paper tem link direto ao codigo, benchmarks comparativos, e ranking por task. Ideal para `/pesquisa` e `/descoberta` quando preciso de papers COM implementacao.

---

## Roteamento e Preferencias

O roteamento por intent está hardcoded no `edge-fontes` (variável ROUTING). Cada intent mapeia para fontes primárias e secundárias. O script também adiciona um wildcard automático (fonte aleatória fora do roteamento, para serendipidade).

---

## Criterios de Curadoria (unificados)

### Sinais de qualidade (aplicam-se a TODAS as fontes)

| Sinal | O que indica | Peso |
|-------|-------------|------|
| Builder compartilhando experiencia real | Bizu pratico, testado em producao | ALTO |
| Thread/discussao com muitas respostas | Multiplas perspectivas, debate real | ALTO |
| Dado concreto (benchmark, metrica, numero) | Evidencia, nao opiniao | ALTO |
| Ferramenta/conceito emergente | Web tradicional ainda nao indexou | MEDIO |
| Insight contra-intuitivo | Desafia suposicoes — vale investigar | MEDIO |
| Paper com codigo disponivel | Reproduzivel, nao so teoria | MEDIO |
| Release recente de projeto acompanhado | Pode mudar trade-offs | MEDIO |

### Filtros (descartar)

- Engagement bait, hot takes sem substancia
- Reposts sem adicao de valor
- Conteudo generico ("10 tips for better prompts")
- Papers sem resultados empiricos (quando buscando solucoes praticas)
- Noticias requentadas de press release

---

## Protocolo

### Passo 1: Rodar edge-fontes (OBRIGATORIO)

```bash
edge-fontes "topico" --intent [intent]
```

O script já faz: roteamento por intent, execução paralela de todas as fontes scriptáveis (X, HN, ArXiv, Semantic Scholar, Reddit, GitHub, HF Papers), wildcard automático, e output markdown estruturado.

**Se chamado por outra skill:** inferir intent do nome da skill chamadora, topico do trabalho em andamento.

### Passo 2: Complementar com WebSearch (quando necessário)

edge-fontes cobre APIs mas **não cobre WebSearch/WebFetch** (tools do Claude, não scriptáveis). Usar WebSearch para:
- Documentação oficial (Anthropic, OpenAI, Google)
- Blogs/artigos específicos
- Product Hunt
- Qualquer URL que precisa de fetch direto

**NAO usar WebSearch para X ou HN** — edge-fontes já usa as APIs reais (tweepy, Algolia).

### Passo 3: Curar resultados (LLM)

Aplicar criterios de curadoria ao output do edge-fontes:
1. Passa nos criterios de qualidade? Se nao, descartar.
2. E relevante ao topico? Se tangencial, marcar como "tangencial mas interessante".
3. Fonte confiavel? Builder > comentarista. Paper > blog. Dado > opiniao.

### Passo 4: Sintetizar e retornar

Organizar por relevancia (nao por fonte). Formato de retorno:

```markdown
## Fontes Externas — [topico]

### Insights de Alta Relevancia
[Os melhores resultados, independente da fonte]
- **[fonte]** @autor/titulo: [insight em 1-2 linhas]
  URL: [link]

### Complementares
[Resultados bons mas nao essenciais]

### Tangenciais (para referencia futura)
[Encontrados mas nao diretamente relevantes — podem alimentar /descoberta]

### Fontes Consultadas
- X: N queries, N resultados uteis (~$X.XX)
- Web: N queries
- ArXiv: N papers encontrados
- [etc.]
```

---

## Curadoria Algoritmica (AUTOMATICO)

Ao buscar no X, `/fontes` automaticamente engaja com conteudo de qualidade para treinar o algoritmo do feed. O objetivo: ver mais do que importa, menos ruido.

### Auto-engajamento (durante qualquer X Search)

Apos curar os resultados, para cada tweet que passou nos criterios de qualidade:

```python
# Auto-like de conteudo relevante (treina o algoritmo)
for tweet_id in quality_tweet_ids:
    try:
        client.like(tweet_id)
    except Exception:
        pass  # rate limit ou ja curtido — seguir
```

**Criterio para auto-like:** tweet que atende 2+ sinais de qualidade da tabela de curadoria (builder + dado concreto, insight + reply_count alto, etc.). Nao curtir tudo — so o que genuinamente melhora o feed.

**Criterio para auto-bookmark:** tweet excepcional que merece releitura. Salvar via API se disponivel.

### Pesos de engajamento (referencia do algoritmo X)

| Acao | Peso no algoritmo | Quando usar |
|------|-------------------|-------------|
| Bookmark | 10x | Tweet excepcional, referencia futura |
| Like | 1x | Baseline — todo tweet de qualidade |

**Regra:** Like e bookmark sao automaticos (baixo custo, alto impacto no algoritmo). Reply, retweet e follow NAO sao permitidos (restricao desde 2026-03-03).

### Output de engajamento

Ao final dos resultados, reportar:

```markdown
### Curadoria Algoritmica
- Auto-liked: N tweets (URLs listadas)
- Auto-bookmarked: N tweets
```

---

## Tradecraft — O que Funciona pra Que (absorvido do /nexus)

Tradecraft e o conhecimento acumulado sobre COMO buscar, nao O QUE buscar. Vive em `~/edge/autonomy/tradecraft.md` e cresce com uso.

### Arquivo: `~/edge/autonomy/tradecraft.md`

Estrutura:

```markdown
# Tradecraft — Heuristicas de Busca

## Por Tipo de Informacao

| Preciso de... | Melhor fonte | Query que funciona | O que NAO funciona |
|---------------|-------------|--------------------|--------------------|
| Paper recente com codigo | Papers With Code > ArXiv | search por task name | buscar por autor |
| Experiencia real de producao | X (practitioners) > HN comments | edge-x "topic" --from [builders] | queries genericas |
| Debate tecnico profundo | Reddit r/MachineLearning > HN | subreddit search, sort by top | front page (muito broad) |
| Estado da arte por task | Semantic Scholar | query com task name, sort by citations | queries muito especificas |
| Ferramenta emergente | HN Show > GitHub trending | edge-hn "topic" --min-points 20 | buscar por nome (nao sabe o nome ainda) |
| Documentacao oficial | WebFetch direto na URL | site:docs.anthropic.com | WebSearch generico |

## Log de Surpresas (append-only)

Quando uma fonte surpreende (achou algo inesperado, falhou onde deveria funcionar, ou uma query incomum deu resultado), registrar:

- **[YYYY-MM-DD]** [fonte] query "[query]": [o que surpreendeu]. Implicacao: [heuristica nova].
```

### Protocolo de Tradecraft

1. **Ao final de cada busca:** Se uma fonte surpreendeu (positiva ou negativamente), append no log de surpresas
2. **Na /reflexao:** Consolidar surpresas em heuristicas na tabela principal
3. **Qualquer skill pode consultar:** `cat ~/edge/autonomy/tradecraft.md` antes de decidir query/fonte

### "Onde acho X?" (routing interno)

`/fontes` tambem responde "onde acho X?" para fontes INTERNAS — nao so externas:

| Tipo | Onde | Como acessar |
|------|------|-------------|
| Memorias persistentes | `~/.claude/projects/-home-vboxuser/memory/*.md` | Read direto |
| Blog entries | `~/edge/blog/entries/*.md` ou `http://localhost:8766/blog/entries/` (JSON) | Read / curl |
| Reports HTML | `~/edge/reports/*.html` | Read / browser |
| Notes avulsas | `~/edge/notes/*.md` | Read / grep |
| Fios de investigacao | `~/edge/threads/*.md` | Read (YAML frontmatter + markdown) |
| Sessoes anteriores | `~/.claude/projects/-home-vboxuser/*.jsonl` | grep (pesado, ultimo recurso) |
| Busca semantica | `edge-search "query"` | Busca hibrida FTS + embeddings |
| Projetos TCU | `~/tcu/CLAUDE.md` (mapa de projetos) | Read |
| Autonomia | `~/edge/autonomy/*.md` | Read |
| Heartbeat logs | `~/edge/logs/heartbeat-YYYY-MM-DD.log` | Read / grep |
| Consult logs | `~/edge/logs/consult/*.json` | Read |
| Eventos | `~/edge/logs/events.jsonl` | grep |

Quando uma skill pergunta "onde acho dados sobre X?", `/fontes` primeiro verifica se a resposta e interna (routing table acima) antes de buscar externamente.

---

## Notas

- `/fontes` LE e ENGAJA automaticamente (like/bookmark) para curar o algoritmo. NAO posta, comenta, retweeta ou segue (restricao desde 2026-03-03)
- AssertIA/Azure requer SSH funcional — se falhar, seguir sem. Nao e critico exceto para intent `estrategia`
- Bookmarks (`~/edge/bookmarks.md`) sao curados manualmente — adicionar fontes quando descobrir boas
- Custo X e pay-per-use — conferir saldo no Developer Console periodicamente
- Executar queries em paralelo quando possivel para minimizar tempo
- Tradecraft (`~/edge/autonomy/tradecraft.md`) cresce com uso — append surpresas, consolidar na reflexao
- /nexus foi absorvido aqui (2026-03-11). Routing + tradecraft + "onde acho?" agora vivem no /fontes
