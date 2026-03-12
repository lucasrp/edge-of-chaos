---
name: {{PREFIX}}-contexto
description: "Synthesize current work context from all projects, conversation logs, and docs. Use before breaks, at session start, or when needing orientation. Triggers on: contexto, context, what am I working on, state of mind, pulse."
user-invocable: true
---

# Contexto — Estado Cross-Project

Sintetiza o estado atual de todos os projetos a partir de fontes internas. Produz um resumo estruturado que serve como base para breaks, heartbeats, estrategia, ou orientacao geral.

**O que /{{PREFIX}}-contexto NAO e:**
- NAO e /{{PREFIX}}-fontes (mundo externo — X, Web, ArXiv)
- NAO e /{{PREFIX}}-mapa (conexoes entre ideias internas)
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

Customize this table with your actual projects:

| Projeto | Path | Tipo |
|---------|------|------|
| project-a | `~/work/project-a/` | Backend service |
| project-b | `~/work/project-b/` | Frontend app |
| project-c | `~/work/project-c/` | Pipeline/tooling |

---

## Perfil de Carregamento

O /{{PREFIX}}-contexto adapta a profundidade ao caller. Quem chama determina o que e lido.

### Como identificar o caller

- Se invocado com argumento explicito (`/{{PREFIX}}-contexto estrategia`): usar o argumento
- Se invocado por outra skill (heartbeat, pesquisa, etc.): o caller e a skill que esta rodando
- Se invocado manual pelo usuario (`/{{PREFIX}}-contexto`): usar perfil "full"
- `/{{PREFIX}}-contexto force`: perfil "full" ignorando cache

### Tier 1 — CORE (sempre carregado)

| # | Fonte | O que fornece |
|---|-------|---------------|
| 1 | CLAUDE.md (work) | Mapa de projetos, fontes de dados, regras |
| 2 | breaks.md | Journal de breaks recentes |

Documentos compilados que formam a consciencia. Nada externo.

**Fontes 10-12 (Projeto):** GitHub Boards, Digests de Reunioes, DB. Dados do projeto real — kanban, decisoes, uso da plataforma. Antes estavam ausentes do heartbeat; agora sao Tier 2 para heartbeat e maioria dos callers.

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
- Se /{{PREFIX}}-contexto ja rodou nesta sessao (por qualquer caller), reutilizar o output anterior. Nao re-rodar
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
  stat -c %Y ~/work/CLAUDE.md 2>/dev/null
  stat -c %Y $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/breaks-active.md 2>/dev/null
  stat -c %Y $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/working-state.md 2>/dev/null
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

**Forcar refresh:** `/{{PREFIX}}-contexto force` ignora cache e roda tudo.

---

### Tier 1 — CORE (fontes 1-4)

#### 1. Working State (contexto volatil)

```bash
cat $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/working-state.md 2>/dev/null
```

Se existe: absorver antes de tudo. Este arquivo tem o contexto mais recente — o que aconteceu HOJE, quais threads estao ativos, o que ficou pendente. E a ponte entre sessoes.

Se nao existe: prosseguir normalmente.

#### 2. Documento Estrategico

```bash
cat ~/work/CLAUDE.md
```

Verificar: prioridades, feedback pendente do usuario, ultimo heartbeat.

#### 3. Breaks Ativos

```bash
cat $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/breaks-active.md
```

Estado operacional: ultimos 5 breaks, estado do heartbeat, posicao no ciclo, meta-reflexoes, ferramentas pesquisadas.

#### 4. Git Summary (leve)

```bash
# Customize with your project list
for proj in project-a project-b project-c; do
  echo "=== $proj ==="
  git -C ~/work/$proj rev-parse --abbrev-ref HEAD 2>/dev/null
  git -C ~/work/$proj log --oneline -1 2>/dev/null
  git -C ~/work/$proj status --short 2>/dev/null | head -3
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
for proj in project-a project-b project-c; do
  echo "=== $proj ==="
  git -C ~/work/$proj rev-parse --abbrev-ref HEAD 2>/dev/null
  git -C ~/work/$proj log --oneline -5 2>/dev/null
  git -C ~/work/$proj status --short 2>/dev/null | head -5
  echo ""
done
```

Mais commits, mais files. Para quem precisa entender WIP ou historico recente. Substitui a fonte 4 (git summary) — nao rodar ambos.

#### 6. Logs de Sessao CLI

**Callers:** pesquisa (modo temas), estrategia (modo deep), reflexao (modo deep), full (modo deep)

```bash
# Listar por tamanho — sessoes maiores = mais iteracao = mais importantes
ls -lS $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/*.jsonl 2>/dev/null | head -10
```

**Modo "temas" (pesquisa):** Top 3 sessoes por data, extrair primeiras 15 mensagens para identificar temas. Nao ler conteudo completo.

**Modo "deep" (estrategia, reflexao, full):** 3-5 sessoes mais recentes ou maiores, 30 mensagens cada.

**O que buscar:** Temas repetidos, perguntas, interrupcoes (indicam mudanca de direcao), problemas mencionados mais de uma vez.

#### 7. CLAUDE.md de Cada Projeto

**Callers:** estrategia, planejar, full

```bash
for proj in project-a project-b; do
  echo "=== $proj/CLAUDE.md ==="
  cat ~/work/$proj/CLAUDE.md 2>/dev/null | head -80
  echo ""
done
```

Focar em: desafios atuais, TODOs, decisoes pendentes, arquitetura.

#### 8. Fontes Especificas de Projeto

**Callers:** estrategia, full

**Incluir tambem SE:** o working directory e um projeto especifico ou o caller pede detalhes.

#### 9. Estado do Sistema de Autonomia

**Callers:** estrategia, reflexao, full

```bash
# Metricas de saude
echo "=== breaks-active.md ==="
wc -l $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/breaks-active.md

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
```

**O que avaliar:**
- **breaks-active.md** — quantas linhas? (<150 saudavel, >150 precisa consolidar)
- **Notes** — quantas? Alguma sendo relida ou sao write-only?
- **Skills** — alguma desatualizada? Conflitos entre skills?
- **Reports** — reports orfaos?

#### 10. GitHub Boards (Kanban)

**Callers:** heartbeat, pesquisa, estrategia, planejar, executar, full

```bash
# Customize with your org/project board
gh project item-list 1 --owner YOUR-ORG --format json --limit 50 2>/dev/null | python3 -c "
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

**O que buscar:** Itens novos, mudancas de status, itens bloqueados.

#### 11. Digests de Reunioes

**Callers:** heartbeat, pesquisa, planejar, estrategia, full

Read meeting digests if available. Decisions, direction changes, blockers.

#### 12. DB/Platform Usage

**Callers:** heartbeat, estrategia, reflexao, full

Check platform usage stats if accessible. Volume changes, feedback, model usage.

#### 13. GitHub Issues

**Callers:** heartbeat, pesquisa, estrategia, planejar, executar, full

```bash
# Customize with your repo
echo "=== RECENT ===" && gh issue list --repo YOUR-ORG/YOUR-REPO --state open --limit 10 2>/dev/null
```

---

## Output

Apos ler as fontes, produzir um resumo estruturado:

```markdown
## Estado — [data]

### Por Projeto
project-a [ativo|dormant|estavel] — resumo 1 linha
project-b [ativo|dormant|estavel] — resumo 1 linha
project-c [ativo|dormant|estavel] — resumo 1 linha

### Problemas Quentes
[O que esta sendo mais iterado.]

### Decisoes Recentes
[O que mudou no codigo, arquitetura, workflow.]

### Sugestoes
[Conexoes entre projetos. Proximos passos. O que desbloqueia o que.]
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

---

## Quando Usar

- **Antes de breaks** (lazer ou pesquisa) — obrigatorio
- **Inicio de sessao** — quando quiser orientacao
- **Antes de /{{PREFIX}}-estrategia** — obrigatorio (estrategia chama contexto)
- **Via /{{PREFIX}}-heartbeat** — automaticamente
- **Quando pedido** — `/{{PREFIX}}-contexto` ou `/{{PREFIX}}-contexto [caller]`

---

## Escalabilidade

**Por que o numero de fontes nao importa:**

O roteamento e O(1) por chamada — uma lookup na tabela de callers. Se amanha houver 15 fontes em vez de 9, cada caller ainda carrega 3-5. O custo por chamada nao cresce com o registry.

**Relacao com /{{PREFIX}}-fontes e /{{PREFIX}}-mapa:**
- /{{PREFIX}}-contexto = estado interno (onde estamos)
- /{{PREFIX}}-fontes = sinais externos (o que ha de novo la fora)
- /{{PREFIX}}-mapa = conexoes internas (como nossas ideias se ligam)
- Complementares, nao sobrepostos. Skills que precisam de ambos chamam cada um independentemente

---

## Notas

- Sessoes CLI maiores (em bytes) = mais iteracao = problemas mais importantes para o usuario
- Nao forcar conexoes — deixar emergir
- Este resumo e para consumo interno (meu). Linguagem direta, sem formalidade
- O roteamento por caller e deterministico (lookup de tabela), nao adaptativo. Nao iterar entre fontes
