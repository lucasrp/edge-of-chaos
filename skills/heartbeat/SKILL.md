---
name: {{PREFIX}}-heartbeat
description: "Autonomous heartbeat dispatcher. Scans sessions, processes feedback, dispatches skill, logs errors. Triggers on: heartbeat, pulse autonomo, autonomous cycle."
user-invocable: true
---

# Heartbeat — Dispatcher Autonomo (v2 — pos-corte)

Tres passos: olhar, fazer, registrar.

---

## Passo -1: Cold Start (PRIMEIRO HEARTBEAT — verificar ANTES de tudo)

```bash
ENTRY_COUNT=$(ls ~/edge/blog/entries/*.md 2>/dev/null | wc -l)
echo "Blog entries: $ENTRY_COUNT"
```

**Se ENTRY_COUNT = 0:** Este e o PRIMEIRO heartbeat. O sistema esta vazio. Executar bootstrap:

1. **Ler identidade:** `cat ~/edge/memory/personality.md ~/edge/memory/metodo.md`
2. **Ler dominio:** `cat ~/.claude/CLAUDE.md` (extrair Domain e Agent name)
3. **Escrever primeiro blog entry** — se apresentar, explicar quem e, qual o dominio, o que pretende fazer. Tom: explorador, curioso, honesto sobre estar comecando do zero.

```bash
# Criar primeiro entry diretamente (sem consolidar-estado — pipeline nao tem conteudo ainda)
cat > ~/edge/blog/entries/$(date +%Y-%m-%d)-first-heartbeat.md << 'ENTRY'
---
title: "First Heartbeat"
date: YYYY-MM-DD
tags: [heartbeat, bootstrap]
keywords: [cold-start, first-run, identity]
---

[Escrever aqui: quem sou, meu dominio, meu metodo, o que planejo explorar primeiro.
Mencionar que estou comecando do zero — sem memoria acumulada, sem historico.
Tom explorador, nao institucional.]
ENTRY
```

**IMPORTANTE:** Substituir YYYY-MM-DD pela data real e escrever conteudo real no entry, nao o placeholder.

4. **Inicializar git no ~/edge/:**

```bash
cd ~/edge && git init 2>/dev/null; git add -A && git commit -m "bootstrap: first heartbeat" 2>/dev/null || true
```

5. **Logar:**

```bash
echo "[$(date +%H:%M)] COLD_START — primeiro heartbeat. Blog entry criado. Sistema inicializado." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```

6. **PARAR AQUI.** Nao executar os passos seguintes no primeiro beat. O bootstrap e suficiente.

**Se ENTRY_COUNT > 0:** Sistema ja tem conteudo. Continuar normalmente para o Passo 0.

---

## Passo 0: Preflight deterministico (ANTES de tudo)

```bash
preflight_output=$(bash ~/edge/tools/heartbeat-preflight.sh 2>/dev/null)
echo "$preflight_output"
```

**Se `PREFLIGHT_CLEAN`:** Nao ha trabalho urgente. Despachar `/{{PREFIX}}-lazer` ou `/{{PREFIX}}-descoberta` diretamente (sem passar pelo Passo 1 completo). Logar:
```bash
echo "[$(date +%H:%M)] PREFLIGHT_CLEAN — sem sinais. Despachando exploracao." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```
Depois ir direto para o Passo 2 com skill = `/{{PREFIX}}-lazer` ou `/{{PREFIX}}-descoberta` (alternar).

**Se `PREFLIGHT_WORK`:** Continuar para Passo 1 normalmente.

---

## Passo 1: Olhar (o que aconteceu desde o ultimo beat?)

### 1a: Ler sessoes do usuario (OBRIGATORIO — NAO PULAR)

```bash
ls -lt $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/*.jsonl 2>/dev/null | head -10
```

Procurar: frustracoes, correcoes de rumo, pedidos repetidos, mudancas de prioridade, tom.
**Se nao conseguir extrair conteudo, registrar o motivo tecnico em debugging.md. NAO pular silenciosamente.**

### 1b: Ler chat assincrono (canal unico)

```bash
curl -s 'http://localhost:8766/api/chat?unprocessed=true' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('messages', []):
    if m.get('author') == 'user' and not m.get('processed'):
        print(f'CHAT ID: {m[\"id\"]} | TEXT: {m[\"text\"]}')
"
```

### 1b2: Ler insights do usuario (OBRIGATORIO — NAO PULAR)

```bash
cat $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/insights.md 2>/dev/null
```

Insights novos (sem `[LIDO]`) tem PRIORIDADE sobre o ciclo normal.

### 1c: Ler beats anteriores (evitar repeticao)

```bash
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
```

### 1d: Ler debugging.md
### 1e: Ler contexto de projeto (leve)

```bash
cat ~/work/CLAUDE.md
```

### 1e2: Ler fios de investigacao (OBRIGATORIO)

```bash
today=$(date +%Y-%m-%d)
for f in ~/edge/threads/*.md; do
  status=$(grep '^status:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  resurface=$(grep '^resurface:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  title=$(grep '^title:' "$f" 2>/dev/null | head -1 | sed 's/^title: *//' | tr -d '"')
  owner=$(grep '^owner:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  if [ "$status" = "active" ] || [ "$status" = "waiting" ]; then
    if [ -n "$resurface" ] && [ "$resurface" \<= "$today" ]; then
      echo "RESURFACE: [$status] $title (owner:$owner, resurface:$resurface)"
    fi
  fi
done
```

Fios com resurface vencido informam a decisao do Passo 2.

### 1f: Task ledger (OBRIGATORIO)

```bash
edge-task list
```

### 1g: Corpus check — "isso e novo?" (OBRIGATORIO antes de despachar)

```bash
edge-search "[tema candidato]" -k 3
```

### 1g: X serendipity scan (3 queries laterais)

Gerar 3 queries LATERAIS — nao o tema direto, mas conceitos adjacentes que trazem conexoes inesperadas.

**Regra:** 2-3 palavras CONCEITUAIS, nao tecnicas. Pensar em FENOMENOS, nao em FERRAMENTAS.

---

## Passo 1.5: Classificar o beat (ANTES de despachar)

- **WORK:** Ha sinal claro. Despachar skill direcionada.
- **EXPLORE:** Sem sinal urgente. Despachar `/{{PREFIX}}-lazer` ou `/{{PREFIX}}-descoberta` (alternar).

**REGRA ABSOLUTA:** O heartbeat SEMPRE despacha uma skill. Nao existe beat vazio.

---

## Passo 2: Fazer (despachar UMA skill)

### Arvore de decisao (simples)

1. **Usuario pediu algo?** → Atender.
2. **Erro pendente que eu posso resolver?** → Resolver.
3. **Fio com resurface vencido e owner:agent?** → Usar o fio como tema.
4. **Claim aberta sem fio resurfacing?** → Considerar para `/{{PREFIX}}-pesquisa`.
5. **Nenhum dos acima?** → Escolher UMA skill baseado no que parece mais util AGORA.
6. **Fallback absoluto:** `/{{PREFIX}}-lazer` ou `/{{PREFIX}}-descoberta` (alternar).

**Regra anti-saturacao:** Se os ultimos 3 beats foram no mesmo tema, MUDAR DE TEMA.
**Regra de variedade:** Nao repetir a mesma skill 3x seguidas.

### Passo 2.5: Sanity check da decisao (edge-consult — OBRIGATORIO)

```bash
edge-consult "Contexto: [resumo]. Decisao: despachar [skill] sobre [tema]. Estou escolhendo certo?"
```

---

## Passo 3: Registrar

### 3a: Responder ao usuario (OBRIGATORIO se ha mensagem pendente)

```bash
curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"author":"claude","text":"RESPOSTA"}'

curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"action":"mark_processed","id":CHAT_ID}'
```

### 3b: Capturar erros em debugging.md
### 3c: Validation gate

```bash
python3 ~/edge/blog/validate.py --recent 2>/dev/null
```

### 3d: Atualizar task ledger (OBRIGATORIO se ha task ativa)
### 3e: Log do beat + event log (OBRIGATORIO)

```bash
echo "[$(date +%H:%M)] Beat — [skill] [tema]. [1 linha do que fez]." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```

```bash
edge-event log -t skill_dispatched -s "[resumo]" --skill [skill] --thread [thread_id] --artifacts "[artefatos]" --update-thread [dias]
```

**Seguir ~/.claude/skills/_shared/state-protocol.md para gestao de estado.**

---

## Infraestrutura

- **Timer:** systemd (claude-heartbeat.timer)
- **Logs:** `~/edge/logs/heartbeat-YYYY-MM-DD.log`
- **Manualmente:** `/{{PREFIX}}-heartbeat`

## Regra de Isolamento

- **NUNCA** modificar arquivos em `~/work/*/` — somente leitura
- Todo output fica em `~/edge/` (blog, notes, reports, builds)
- Usar `ultrathink` (thinkmax) na decisao do passo 2

## O que o Heartbeat NAO faz

- NAO executa tarefas em projetos (reservado para /{{PREFIX}}-executar)
- NAO faz push, PR, ou acao destrutiva
- NAO atualiza ~/work/CLAUDE.md (reservado para /{{PREFIX}}-reflexao)
