---
name: estado
description: "Concrete state inspection of all managed artifacts. Counts, categorizes, checks health, produces a factual snapshot — not narrative, not strategic. Triggers on: estado, state, dashboard, inventory, status dos artefatos."
user-invocable: true
---

# Estado — Inventario Factual dos Artefatos

Inspeciona o estado concreto de todos os artefatos gerenciados (state files, propostas, descobertas, breaks, notes, labs, projetos git). Produz um snapshot quantitativo e factual — numeros, contagens, timestamps, saude.

NAO e contexto (qualitativo, orientacao). NAO e estrategia (prioridades, decisoes). E inventario puro.

---

## O Job

1. Contar e categorizar cada tipo de artefato
2. Checar saude (tamanhos, timestamps, consistencia)
3. Detectar anomalias (arquivos orfaos, estados inconsistentes, acumulos)
4. Produzir snapshot estruturado — factual, sem recomendacoes

---

## Protocolo (seguir na ordem)

### Passo 1: State Files (memoria do sistema de autonomia)

```bash
echo "=== STATE FILES ==="
for f in breaks-active.md breaks-archive.md propostas.md descobertas.md personality.md reflexao-log.md; do
  path="$HOME/.claude/projects/-home-vboxuser/memory/$f"
  if [ -f "$path" ]; then
    lines=$(wc -l < "$path")
    size=$(du -h "$path" | cut -f1)
    mod=$(stat -c %Y "$path" 2>/dev/null)
    age=$(( ($(date +%s) - mod) / 86400 ))
    echo "$f: ${lines} linhas, ${size}, modificado ha ${age} dias"
  else
    echo "$f: NAO EXISTE"
  fi
done
```

**Saude de breaks-active.md:**
- <150 linhas → saudavel
- 150-200 → crescendo (reflexao deveria consolidar)
- >200 → critico (consolidacao urgente)

### Passo 2: Propostas

```bash
echo "=== PROPOSTAS ==="
file="$HOME/.claude/projects/-home-vboxuser/memory/propostas.md"
if [ -f "$file" ]; then
  echo "Total de propostas: $(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)"
  for status in PROPOSTA APROVADA "EM EXECUCAO" CONCLUIDA REJEITADA SUPERSEDED; do
    count=$(grep -c "\[$status\]" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  [$status]: $count"
  done
fi
```

Listar cada proposta com: numero, titulo resumido, status, data.

### Passo 3: Descobertas

```bash
echo "=== DESCOBERTAS ==="
file="$HOME/.claude/projects/-home-vboxuser/memory/descobertas.md"
if [ -f "$file" ]; then
  echo "Total: $(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)"
  for status in PENDENTE ADOTADA ARQUIVADA "EXPLORAR MAIS"; do
    count=$(grep -c "\[$status\]" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  [$status]: $count"
  done
fi
```

### Passo 4: Breaks e Heartbeat

```bash
echo "=== HEARTBEAT ==="
# Extrair estado do heartbeat de breaks-active.md
grep -A 5 "Estado do Heartbeat" ~/.claude/projects/-home-vboxuser/memory/breaks-active.md 2>/dev/null

echo ""
echo "=== BREAKS (archive) ==="
file="$HOME/.claude/projects/-home-vboxuser/memory/breaks-archive.md"
if [ -f "$file" ]; then
  total=$(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)
  echo "Total de breaks: $total"
  for tipo in lazer pesquisa descoberta estrategia reflexao planejamento execucao; do
    count=$(grep -ci "tipo.*$tipo\|$tipo —" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  $tipo: $count"
  done
  echo ""
  echo "Ultimo break:"
  grep '^\## \[' "$file" | tail -1
fi
```

### Passo 5: Skills

```bash
echo "=== SKILLS ==="
total=$(ls ~/.claude/skills/*/SKILL.md 2>/dev/null | wc -l)
echo "Total: $total skills"
ls -1 ~/.claude/skills/ 2>/dev/null | while read dir; do
  if [ -f "$HOME/.claude/skills/$dir/SKILL.md" ]; then
    echo "  $dir"
  fi
done
```

### Passo 6: Artefatos de output (edge/)

```bash
echo "=== ARTEFATOS (~/edge/) ==="

echo "Notes:"
notes_count=$(ls ~/edge/notes/*.md 2>/dev/null | wc -l)
echo "  $notes_count notas"
[ -f ~/edge/notes/INDEX.md ] && echo "  INDEX.md existe" || echo "  INDEX.md NAO EXISTE"

echo "Labs:"
labs=$(ls -d ~/edge/labs/*/ 2>/dev/null | wc -l)
echo "  $labs labs"
ls -d ~/edge/labs/*/ 2>/dev/null | while read d; do
  name=$(basename "$d")
  echo "    $name"
done

echo "Reports:"
reports=$(ls ~/edge/reports/*.html 2>/dev/null | wc -l)
echo "  $reports reports"

echo "Builds:"
ls -d ~/edge/builds/*/ 2>/dev/null | wc -l | xargs -I{} echo "  {} builds"

echo "Blog:"
[ -f ~/edge/blog/index.html ] && echo "  existe" || echo "  NAO EXISTE"

echo "Netlify pages:"
ls -d ~/edge/netlify/*/ 2>/dev/null | wc -l | xargs -I{} echo "  {} pages"
```

### Passo 7: Projetos git

```bash
echo "=== PROJETOS GIT ==="
for proj in Doc_AssertIA assertia-mise assertia-multiagent assertia-nextjs ralph daily-watcher; do
  dir="$HOME/tcu/$proj"
  if [ -d "$dir/.git" ]; then
    branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null)
    last_commit=$(git -C "$dir" log -1 --format="%ar" 2>/dev/null)
    dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l)
    echo "$proj: branch=$branch, ultimo_commit=$last_commit, dirty_files=$dirty"
  else
    echo "$proj: NAO ENCONTRADO"
  fi
done
```

### Passo 8: Feedback do usuario

```bash
echo "=== FEEDBACK ==="
# Contar feedback pendente vs processado em ~/tcu/CLAUDE.md
pending=$(grep -c '^\d\.' ~/tcu/CLAUDE.md 2>/dev/null || echo 0)
processed=$(grep -c '\[PROCESSADO\]' ~/tcu/CLAUDE.md 2>/dev/null || echo 0)
unprocessed=$(grep '^\d\.' ~/tcu/CLAUDE.md 2>/dev/null | grep -v '\[PROCESSADO\]' | wc -l)
echo "Feedback total: $pending (processados: $processed, pendentes: $unprocessed)"
if [ "$unprocessed" -gt 0 ]; then
  echo "PENDENTES:"
  grep '^\d\.' ~/tcu/CLAUDE.md 2>/dev/null | grep -v '\[PROCESSADO\]'
fi
```

### Passo 9: Anomalias

Apos coletar todos os dados, verificar:

1. **Consistencia propostas ↔ arquivos:** Cada proposta referencia um arquivo de proposta — o arquivo existe?
2. **Descobertas estagnadas:** Alguma [PENDENTE] ha mais de 3 heartbeats?
3. **Notes orfas:** Notes em `~/edge/notes/` que nao estao no INDEX.md?
4. **Labs abandonados:** Labs sem commits recentes?
5. **breaks-active.md inchado:** >150 linhas = flag
6. **Reflexao-log crescendo:** >300 linhas sem consolidacao?
7. **Feedback pendente:** Qualquer item sem [PROCESSADO] = flag

---

## Output

Produzir o snapshot no formato abaixo. Numeros exatos, sem narrativa.

```markdown
# Estado — [YYYY-MM-DD HH:MM]

## State Files
| Arquivo | Linhas | Tamanho | Modificado | Saude |
|---------|--------|---------|------------|-------|
| breaks-active.md | N | Xk | N dias | ok/crescendo/critico |
| breaks-archive.md | N | Xk | N dias | — |
| propostas.md | N | Xk | N dias | — |
| descobertas.md | N | Xk | N dias | — |
| personality.md | N | Xk | N dias | — |
| reflexao-log.md | N | Xk | N dias | — |

## Propostas
| # | Titulo | Status | Data |
|---|--------|--------|------|
| N | ... | [STATUS] | YYYY-MM-DD |

## Descobertas
| Titulo | Status | Data |
|--------|--------|------|
| ... | [STATUS] | YYYY-MM-DD |

## Heartbeat
- Ultimo beat: #N
- Tipo: ...
- Beats desde estrategia: N
- Beats desde planejar: N

## Skills: N total
[lista simples]

## Artefatos
- Notes: N (INDEX: sim/nao)
- Labs: N [nomes]
- Reports: N
- Builds: N
- Blog: sim/nao
- Netlify pages: N

## Projetos Git
| Projeto | Branch | Ultimo Commit | Dirty |
|---------|--------|---------------|-------|
| ... | ... | ... | N |

## Feedback
- Processados: N
- Pendentes: N
[lista dos pendentes se houver]

## Anomalias
- [lista factual de inconsistencias detectadas, ou "Nenhuma"]
```

---

## Argumentos

- `/estado` — snapshot completo (default)
- `/estado propostas` — apenas secao de propostas
- `/estado saude` — apenas state files + anomalias (rapido)

---

## Quando Usar

- **Standalone:** `/estado` — quando quiser um dashboard factual
- **Antes de /heartbeat:** para informar o dispatch com dados concretos
- **Apos /reflexao:** para verificar se o estado foi atualizado corretamente
- **Debug:** quando algo parece inconsistente — `/estado saude`

---

## O que /estado NAO faz

- NAO interpreta (isso e /contexto)
- NAO recomenda acoes (isso e /estrategia)
- NAO modifica nenhum arquivo (leitura pura)
- NAO le sessoes CLI ou logs de conversa (isso e /contexto)
- NAO faz git log detalhado (so branch, ultimo commit, dirty count)

---

## Regra de Isolamento (OBRIGATORIA)

**Leitura pura.** Esta skill NAO modifica NENHUM arquivo — nem state files, nem projetos, nem nada.
Todos os comandos sao de leitura (cat, wc, ls, grep, git status, stat).

---

## Notas

- Output factual e conciso. Sem "eu acho", sem "talvez". Numeros ou "NAO EXISTE"
- Anomalias sao factuais, nao recomendacoes. Ex: "proposta #3 referencia arquivo inexistente" — nao "deveria criar o arquivo"
- Se um state file nao existe, reportar como anomalia — nao criar
- Tempo de execucao esperado: <30 segundos (tudo local, sem rede)
