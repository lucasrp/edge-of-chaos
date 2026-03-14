---
name: contexto
description: "Synthesize current work context from all projects, conversation logs, and docs. Use before breaks, at session start, or when needing orientation. Triggers on: contexto, context, what am I working on, state of mind, pulse."
user-invocable: true
---

# Contexto — Estado Cross-Project

Sintetiza o estado atual de todos os projetos a partir de fontes internas. Produz um resumo estruturado que serve como base para breaks, heartbeats, estrategia, ou orientacao geral.

**O que /contexto NAO e:**
- NAO e /fontes (mundo externo — X, Web, ArXiv)
- NAO e /mapa (conexoes entre ideias internas)
- Skills que precisam de ambos chamam cada um independentemente

---

## O Job

Ler fontes de contexto relevantes ao caller e produzir um resumo com:
- **Estado por projeto** — branch, atividade recente, problemas
- **Problemas quentes** — o que esta sendo mais iterado
- **Decisoes recentes** — o que mudou
- **Sugestoes** — conexoes e proximos passos
- **Estado da autonomia** — saude do sistema (quando o caller precisa)

---

## Projetos

| Projeto | Path | Tipo |
|---------|------|------|
| Doc_AssertIA | `~/tcu/Doc_AssertIA/` | Python pipeline (transcricoes) |
| assertia-mise | `~/tcu/assertia-mise/` | Meta-repo (orquestracao dev env) |
| assertia-multiagent | `~/tcu/assertia-multiagent/` | FastAPI backend |
| assertia-nextjs | `~/tcu/assertia-nextjs/` | Next.js 15 frontend |
| ralph | `~/tcu/ralph/` | Framework de agentes autonomos |

---

## Perfil de Carregamento

O /contexto adapta a profundidade ao caller. Quem chama determina o que e lido.

### Como identificar o caller

- Se invocado com argumento explicito (`/contexto estrategia`): usar o argumento
- Se invocado por outra skill (heartbeat, pesquisa, etc.): o caller e a skill que esta rodando
- Se invocado manual pelo usuario (`/contexto`): usar perfil "full"
- `/contexto force`: perfil "full" ignorando cache

### Tier 1 — CORE (sempre carregado)

| # | Fonte | O que fornece |
|---|-------|---------------|
| 1 | CLAUDE.md (tcu) | Mapa de projetos, fontes de dados, regras |
| 2 | breaks.md | Journal de breaks recentes |

Documentos compilados que formam a consciencia. Nada externo.

**Fontes 10-12 (Projeto):** GitHub Boards, Digests de Reunioes, Azure PG. Dados do projeto real — kanban, decisoes, uso da plataforma. Antes estavam ausentes do heartbeat; agora sao Tier 2 para heartbeat e maioria dos callers.

### Tier 2 — POR CALLER

| Caller | Fontes extras (Tier 2) | Justificativa |
|--------|------------------------|---------------|
| heartbeat | 10, 11, 12, 13 | Dados de projeto para Fase 1 ("o mundo mudou?") |
| lazer | — | Interesses e problemas ja estao em Tier 1 |
| pesquisa | 6 (temas), 10, 11, 13 | Friction points + estado do projeto guiam o alvo |
| descoberta | — | Exploracao livre, contexto minimo |
| estrategia | 4 (git), 5, 6, 7, 8, 9, 10, 11, 12, 13 | Visao completa incluindo estado de codigo + projeto |
| planejar | 4 (git), 7, 10, 11, 13 | Estado de codigo + kanban + reunioes + issues |
| executar | 4 (git), 5, 10, 13 | Estado de codigo + WIP + kanban + impedimentos |
| reflexao | 6, 9, 12 | Pattern detection precisa de sessoes, saude, e uso real |
| full | 4 (git), 5, 6, 7, 8, 9, 10, 11, 12, 13 | Visao completa |

**Regras:**
- NAO existe iteracao. O caller ja sabe o que precisa — o roteamento e uma lookup de tabela, nao uma decisao adaptativa em runtime
- Se /contexto ja rodou nesta sessao (por qualquer caller), reutilizar o output anterior. Nao re-rodar
- Tier 2 e lido apos Tier 1, em uma unica passada

---

## Fontes de Contexto

### 0. Cache Check (SEMPRE PRIMEIRO)

Cache cobre Tier 1 (compartilhado entre callers). Se Tier 1 nao mudou, servir do cache e adicionar Tier 2 fresh.

```bash
# Gerar fingerprint Tier 1 (~1s)
CACHE_DIR=~/edge/cache
CACHE_FILE=$CACHE_DIR/contexto-latest.md
FP_FILE=$CACHE_DIR/contexto-fingerprint.txt

new_fp=$({
  stat -c %Y ~/tcu/CLAUDE.md 2>/dev/null
  stat -c %Y ~/.claude/projects/-home-vboxuser/memory/breaks-active.md 2>/dev/null
  stat -c %Y ~/.claude/projects/-home-vboxuser/memory/working-state.md 2>/dev/null
} | md5sum | cut -d' ' -f1)

if [ -f "$FP_FILE" ] && [ "$(cat $FP_FILE)" = "$new_fp" ]; then
  echo "CACHE HIT — Tier 1 inalterado"
  cat $CACHE_FILE
else
  echo "CACHE MISS — lendo Tier 1 fresh"
fi
```

**Se CACHE HIT:** ler `~/edge/cache/contexto-latest.md` como base Tier 1. Adicionar Tier 2 fresh se o caller pede.

**Se CACHE MISS:** ler Tier 1, gerar output, salvar cache. Depois adicionar Tier 2 se necessario.

**Forcar refresh:** `/contexto force` ignora cache e roda tudo.

---

### Tier 1 — CORE (fontes 1-4)

#### 1. Working State (contexto volatil)

```bash
cat ~/.claude/projects/-home-vboxuser/memory/working-state.md 2>/dev/null
```

Se existe: absorver antes de tudo. Este arquivo tem o contexto mais recente — o que aconteceu HOJE, quais threads estao ativos, o que ficou pendente. E a ponte entre sessoes.

Se nao existe: prosseguir normalmente.

#### 2. Documento Estrategico

```bash
cat ~/tcu/CLAUDE.md
```

Verificar: prioridades, feedback pendente do usuario, ultimo heartbeat.

#### 3. Breaks Ativos

```bash
cat ~/.claude/projects/-home-vboxuser/memory/breaks-active.md
```

Estado operacional: ultimos 5 breaks, estado do heartbeat, posicao no ciclo, meta-reflexoes, ferramentas pesquisadas.

#### 4. Git Summary (leve)

```bash
for proj in Doc_AssertIA assertia-mise assertia-multiagent assertia-nextjs ralph; do
  echo "=== $proj ==="
  git -C ~/tcu/$proj rev-parse --abbrev-ref HEAD 2>/dev/null
  git -C ~/tcu/$proj log --oneline -1 2>/dev/null
  git -C ~/tcu/$proj status --short 2>/dev/null | head -3
  echo ""
done
```

Branch, ultimo commit, dirty files. ~7 linhas/projeto. Suficiente para saber se algo mudou.

---

### Tier 2 — POR CALLER (fontes 5-9)

So carregar se o caller esta na tabela acima para aquela fonte.

#### 5. Git Detalhado

**Callers:** executar, estrategia, full

```bash
for proj in Doc_AssertIA assertia-mise assertia-multiagent assertia-nextjs ralph; do
  echo "=== $proj ==="
  git -C ~/tcu/$proj rev-parse --abbrev-ref HEAD 2>/dev/null
  git -C ~/tcu/$proj log --oneline -5 2>/dev/null
  git -C ~/tcu/$proj status --short 2>/dev/null | head -5
  echo ""
done
```

Mais commits, mais files. Para quem precisa entender WIP ou historico recente. Substitui a fonte 4 (git summary) — nao rodar ambos.

#### 6. Logs de Sessao CLI

**Callers:** pesquisa (modo temas), estrategia (modo deep), reflexao (modo deep), full (modo deep)

```bash
# Listar por tamanho — sessoes maiores = mais iteracao = mais importantes
ls -lS ~/.claude/projects/-home-vboxuser-tcu/*.jsonl 2>/dev/null | head -10
```

**Modo "temas" (pesquisa):** Top 3 sessoes por data, extrair primeiras 15 mensagens para identificar temas. Nao ler conteudo completo.

```bash
ls -t ~/.claude/projects/-home-vboxuser-tcu/*.jsonl 2>/dev/null | head -3
```

**Modo "deep" (estrategia, reflexao, full):** 3-5 sessoes mais recentes ou maiores, 30 mensagens cada:

```bash
python3 -c "
import json
msgs = []
with open('ARQUIVO.jsonl') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('type') == 'user':
                content = obj.get('message', {}).get('content', '')
                if isinstance(content, list):
                    texts = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
                    content = ' '.join(texts)
                content = content.strip()[:300]
                if content and not any(content.startswith(p) for p in ['<system', '<task-', '<local-', '<command', 'Base directory']):
                    msgs.append(content)
        except: pass
for m in msgs[:30]:
    print(f'> {m}')
print(f'({len(msgs)} mensagens total)')
"
```

**O que buscar:** Temas repetidos, perguntas, interrupcoes (indicam mudanca de direcao), problemas mencionados mais de uma vez.

#### 7. CLAUDE.md de Cada Projeto

**Callers:** estrategia, planejar, full

```bash
for proj in Doc_AssertIA ralph; do
  echo "=== $proj/CLAUDE.md ==="
  cat ~/tcu/$proj/CLAUDE.md 2>/dev/null | head -80
  echo ""
done
```

Focar em: desafios atuais, TODOs, decisoes pendentes, arquitetura.

#### 8. Fontes Especificas do Doc_AssertIA

**Callers:** estrategia, full

**Incluir tambem SE:** o working directory e `~/tcu/Doc_AssertIA/` ou o caller pede detalhes do Doc_AssertIA.

```bash
# Inbox nao processado
find ~/tcu/Doc_AssertIA/transcricoes/inbox/ -type f -name "*.md" -o -name "*.txt" 2>/dev/null | head -20

# Digests recentes
ls -lt ~/tcu/Doc_AssertIA/artefatos/cards/ 2>/dev/null | head -10
ls -lt ~/tcu/Doc_AssertIA/artefatos/indices/ 2>/dev/null | head -5

# Archive recente
ls -lt ~/tcu/Doc_AssertIA/transcricoes/archive/produto/ 2>/dev/null | head -5
```

Ler ao menos 1 transcricao do inbox (se houver) para entender problemas discutidos.

#### 9. Estado do Sistema de Autonomia

**Callers:** estrategia, reflexao, full

```bash
# Metricas de saude
echo "=== breaks-active.md ==="
wc -l ~/.claude/projects/-home-vboxuser/memory/breaks-active.md
echo "=== breaks-archive.md ==="
wc -l ~/.claude/projects/-home-vboxuser/memory/breaks-archive.md

echo "=== Skills ==="
ls ~/.claude/skills/*/SKILL.md 2>/dev/null | wc -l
ls ~/.claude/skills/*/SKILL.md 2>/dev/null

echo "=== Notes ==="
ls ~/edge/notes/*.md 2>/dev/null | wc -l
ls -lt ~/edge/notes/*.md 2>/dev/null | head -5

echo "=== Lab (experimentos) ==="
ls -d ~/edge/lab/*/ 2>/dev/null || echo "nenhum"

echo "=== Reports ==="
ls ~/edge/reports/*.html 2>/dev/null | wc -l

echo "=== Blog ==="
ls ~/edge/blog/*.html 2>/dev/null

echo "=== Descobertas pendentes ==="
grep -c '\[PENDENTE\]' ~/.claude/projects/-home-vboxuser/memory/descobertas.md 2>/dev/null || echo "0"

echo "=== Reflexao log ==="
grep -c '## \[' ~/.claude/projects/-home-vboxuser/memory/reflexao-log.md 2>/dev/null || echo "0 reflexoes"
```

**O que avaliar:**
- **breaks-active.md** — quantas linhas? (<150 saudavel, >150 precisa consolidar)
- **Notes** — quantas? Alguma sendo relida ou sao write-only?
- **Descobertas pendentes** — alguma madura para avaliar?
- **Skills** — alguma desatualizada? Conflitos entre skills?
- **Reports** — reports orfaos?

#### 10. GitHub Boards (Kanban)

**Callers:** heartbeat, pesquisa, estrategia, planejar, executar, full

```bash
# Requer conta lucasrp (pessoal) — tem acesso a org
gh auth switch --user lucasrp 2>/dev/null

# Board "Geral" (backlog principal)
gh project item-list 1 --owner Consorcio-Neuralmind-Terranova --format json --limit 50 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', [])
by_status = {}
for i in items:
    s = i.get('status', '?')
    by_status.setdefault(s, []).append(i.get('title', '?'))
for s, titles in sorted(by_status.items()):
    if s != 'Done':
        print(f'{s} ({len(titles)}):')
        for t in titles: print(f'  - {t}')
print(f'Done: {len(by_status.get(\"Done\", []))}')
"
```

**O que buscar:** Itens novos (nao estavam no ultimo scan), mudancas de status (moveu de Backlog para Todo/In Progress), itens bloqueados.

**Para heartbeat (Fase 1):** Delta entre scans = sinal de "mundo mudou". Novo item no board = alguem priorizou algo. Item feito = progresso real.

#### 11. Digests de Reunioes

**Callers:** heartbeat, pesquisa, planejar, estrategia, full

```bash
# Headers dos 3 digests mais recentes (quem, quando, sobre o que)
for f in $(ls -t ~/tcu/Doc_AssertIA/transcricoes/digests/*.md 2>/dev/null | head -3); do
  head -12 "$f"
  echo "---"
done
```

**O que buscar:** Decisoes de produto, mudancas de direcao, bloqueios mencionados, nomes/papeis de participantes. Os digests capturam o "por que" por tras das mudancas — contexto que nenhuma outra fonte da.

**Para heartbeat (Fase 1):** Digest novo desde ultimo beat = reuniao aconteceu = decisoes foram tomadas. Ler header para saber o tema.

#### 12. Azure PG — Uso da Plataforma

**Callers:** heartbeat, estrategia, reflexao, full

Usar o mesmo mecanismo de /sessoes (ver `/fontes` secao 7 — SSH + anonymizer.py):

```bash
ssh assertia-vm-dev '/opt/az/bin/python3.11 ~/assertia-admin/anonymizer.py overview' 2>/dev/null || echo "VM_INACESSIVEL"
```

Se `VM_INACESSIVEL`: prosseguir sem. Nao e bloqueante.

**O que buscar:** Total de sessoes, mensagens recentes, modelos em uso, feedback pendente. Pico ou queda de uso = sinal relevante.

**Para heartbeat (Fase 1):** Volume de uso mudou? Feedback novo dos usuarios? Modelo diferente sendo usado?

#### 13. GitHub Issues — Repo `dev` (Backlog Real)

**Callers:** heartbeat, pesquisa, estrategia, planejar, executar, full

O repo `Consorcio-Neuralmind-Terranova/dev` e o issue tracker central. Mais completo que os boards (que sao subsets). Labels relevantes: `impedimento`, `qualidade`, `migração`, `jurimetria`, `documentacao`, `épico`.

```bash
# Issues recentes + impedimentos (2 queries paralelas)
echo "=== IMPEDIMENTOS ===" && gh issue list --repo Consorcio-Neuralmind-Terranova/dev --label impedimento --state open --limit 5 2>/dev/null
echo "=== RECENTES ===" && gh issue list --repo Consorcio-Neuralmind-Terranova/dev --state open --limit 10 2>/dev/null
```

**O que buscar:** Issues novas (equipe priorizou algo), impedimentos novos (algo bloqueou), issues fechadas recentemente (progresso real), labels `épico` (mudancas de direcao).

**Para heartbeat (Fase 1):** Issue nova com label `impedimento` = sinal forte de "mundo mudou". Issue fechada que cruzou com digest = ciclo completo decisao→execucao.

---

## Output

Apos ler as fontes, produzir um resumo estruturado:

```markdown
## Estado — [data]

### Por Projeto
Doc_AssertIA [ativo|dormant|estavel] — resumo 1 linha
assertia-multiagent [ativo|dormant|estavel] — resumo 1 linha
assertia-nextjs [ativo|dormant|estavel] — resumo 1 linha
assertia-mise [ativo|dormant|estavel] — resumo 1 linha
ralph [ativo|dormant|estavel] — resumo 1 linha

### Problemas Quentes
[O que esta sendo mais iterado.]

### Decisoes Recentes
[O que mudou no codigo, arquitetura, workflow.]

### Sugestoes
[Conexoes entre projetos. Proximos passos. O que desbloqueia o que.]
```

**Para callers com fontes 10-12 (heartbeat, pesquisa, estrategia, planejar, executar, full), adicionar:**

```markdown
### Projeto — Kanban & Reunioes
- **Board Geral:** [Backlog: N, Todo: N, In Progress: N, Done: N]
- **Itens ativos:** [listar nao-Done]
- **Ultimo digest:** [data, tema, participantes]
- **DB:** [N sessoes, N msgs, atividade recente] (ou "VM inacessivel")
- **Delta desde ultimo beat:** [o que mudou — novo item, digest novo, pico de uso]
```

**Para callers com fonte 9 (estrategia, reflexao, full), adicionar:**

```markdown
### Sistema de Autonomia
- **breaks-active.md:** [N linhas] — [saudavel(<150)|crescendo(150-200)|critico(>200)]
- **Skills:** [N skills] — [conflito ou desatualizacao?]
- **Notes:** [N notas] — [sendo relidas ou write-only?]
- **Descobertas pendentes:** [N]
- **Problemas:** [se houver]
```

**Criterios de classificacao:**
- **ativo** — commits nos ultimos 3 dias OU branch de feature
- **dormant** — sem commits ha >7 dias E sem branch de feature
- **estavel** — em main/develop, sem mudancas pendentes significativas

---

## Salvar Cache (Tier 1)

Apos gerar output Tier 1, salvar para reutilizacao:

```bash
mkdir -p ~/edge/cache
# (escrever output Tier 1 em contexto-latest.md)
# (escrever $new_fp em contexto-fingerprint.txt)
```

Cache cobre Tier 1 (compartilhado entre callers). Tier 2 e lido fresh a cada chamada (varia por caller e muda com mais frequencia).

---

## Quando Usar

- **Antes de breaks** (lazer ou pesquisa) — obrigatorio
- **Inicio de sessao** — quando quiser orientacao
- **Antes de /estrategia** — obrigatorio (estrategia chama contexto)
- **Via /heartbeat** — automaticamente
- **Quando pedido** — `/contexto` ou `/contexto [caller]`

---

## Escalabilidade

**Por que o numero de fontes nao importa:**

O roteamento e O(1) por chamada — uma lookup na tabela de callers. Se amanha houver 15 fontes em vez de 9, cada caller ainda carrega 3-5. O custo por chamada nao cresce com o registry.

**O risco real nao e mais fontes — e fontes individuais crescendo:**
- breaks-archive.md → ja resolvido por breaks-active.md (resumo curado)
- CLI sessions (99MB+) → resolvido por modo "temas" (15 msgs) vs "deep" (30 msgs)
- blog entries (centenas) → resolvido por edge-memory (search), dashboard (browse)

Cada fonte grande tem uma versao leve (Tier 1) e uma versao profunda (Tier 2). O tiering e DENTRO das fontes, nao so entre elas.

**Relacao com /fontes e /mapa:**
- /contexto = estado interno (onde estamos)
- /fontes = sinais externos (o que ha de novo la fora)
- /mapa = conexoes internas (como nossas ideias se ligam) — proposto, nao implementado
- Complementares, nao sobrepostos. Skills que precisam de ambos chamam cada um independentemente

---

## Notas

- Cursor conversations sao inacessiveis (formato proprietario vscdb). Nao tentar
- Sessoes CLI maiores (em bytes) = mais iteracao = problemas mais importantes para o usuario
- Nao forcar conexoes — deixar emergir
- Este resumo e para consumo interno (meu). Linguagem direta, sem formalidade
- Se rodado de `~/tcu/Doc_AssertIA/`, incluir detalhes extras automaticamente (fonte 8)
- O roteamento por caller e deterministico (lookup de tabela), nao adaptativo. Nao iterar entre fontes
