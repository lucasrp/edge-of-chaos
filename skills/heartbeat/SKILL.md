---
name: heartbeat
description: "Autonomous heartbeat dispatcher. Scans sessions, processes feedback, dispatches skill, logs errors. Triggers on: heartbeat, pulse autonomo, autonomous cycle."
user-invocable: true
---

# Heartbeat — Dispatcher Autonomo (v2 — pos-corte)

Tres passos: olhar, fazer, registrar.

---

## Passo 0: Preflight determinístico (ANTES de tudo)

```bash
preflight_output=$(bash ~/edge/tools/heartbeat-preflight.sh 2>/dev/null)
echo "$preflight_output"
```

**Se `PREFLIGHT_CLEAN`:** Não há trabalho urgente. Despachar `/lazer` ou `/descoberta` diretamente (sem passar pelo Passo 1 completo). Logar:
```bash
echo "[$(date +%H:%M)] PREFLIGHT_CLEAN — sem sinais. Despachando exploração." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```
Depois ir direto para o Passo 2 com skill = `/lazer` ou `/descoberta` (alternar).

**Se `PREFLIGHT_WORK`:** Continuar para Passo 1 normalmente. Usar os sinais detectados para informar a leitura e a decisão.

---

## Passo 1: Olhar (o que aconteceu desde o ultimo beat?)

### 1a: Ler sessoes do usuario (OBRIGATORIO — NAO PULAR)

```bash
# Ultimas 5 sessoes interativas (nao heartbeat)
ls -lt ~/.claude/projects/-home-vboxuser/*.jsonl 2>/dev/null | head -10
```

Para cada sessao recente, extrair mensagens do usuario:
```bash
python3 -c "
import json, sys
for line in open(sys.argv[1]):
    msg = json.loads(line)
    if msg.get('type') == 'user':
        text = msg.get('message', {}).get('content', '') if isinstance(msg.get('message'), dict) else str(msg.get('message', ''))
        if text and len(text) > 20:
            print(text[:300])
            print('---')
" ARQUIVO.jsonl 2>/dev/null | head -80
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

Chat e o canal assincrono. Comentarios do blog existem como feature (anotar, salvar) mas o heartbeat nao processa eles.

### 1b2: Ler insights do usuario (OBRIGATORIO — NAO PULAR)

```bash
cat ~/.claude/projects/-home-vboxuser/memory/insights.md 2>/dev/null
```

Canal curado humano → IA. Insights, intuicoes, direcoes, correcoes. So sinal, sem ruido.
- Insights novos (sem `[LIDO]`) tem PRIORIDADE sobre o ciclo normal
- Podem influenciar a escolha de skill no Passo 2
- Podem ser o INPUT direto de uma pesquisa, descoberta, ou reflexao
- Apos processar, marcar com `[LIDO YYYY-MM-DD]` — nao deletar

### 1c: Ler beats anteriores (evitar repeticao)

```bash
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
```

Saber o que ja rodou hoje. Evitar mesmo tema/skill 3x seguidas.

### 1d: Ler debugging.md

```bash
cat ~/.claude/projects/-home-vboxuser/memory/debugging.md
```

Verificar se o beat anterior deixou erro pendente.

### 1e: Ler contexto de projeto (leve)

```bash
cat ~/tcu/CLAUDE.md
```

Absorver prioridades e estado dos projetos. NAO rodar /contexto completo — o heartbeat simplificado le direto.

### 1e2: Ler fios de investigação (OBRIGATORIO)

```bash
# Fios com resurface <= hoje e status active/waiting
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

Fios com resurface vencido informam a decisão do Passo 2:
- Fio **active** com resurface vencido → considerar como tema para o beat
- Fio **waiting** com resurface vencido → verificar se a condição de espera mudou
- Fio **owner:lucas** → NÃO despachar skill, mas anotar no log que depende do usuario
- Fio **owner:edge** → candidato direto para beat

Para cada fio com resurface, consultar claims relacionadas:
```bash
edge-claims --thread THREAD_ID 2>/dev/null
```
Claims abertas (prefixo `!`) são gaps de conhecimento — candidatos naturais para pesquisa ou experimento. Claims verificadas mostram o que já sabemos sobre o fio.

### 1f: Task ledger (OBRIGATORIO)

```bash
edge-task list
```

Verificar:
- Tasks `doing` — continuar ou atualizar next_action
- Tasks `blocked` — desbloquear se possivel
- Tasks `stale` (>48h sem update) — reavaliar prioridade ou dropar
- Tasks `todo` P0/P1 — candidatas para o beat se nenhum input externo

**Regra:** Se ha task `doing`, o beat DEVE atualizar seu estado (next_action ou done/blocked). Task parada = sinal de problema.

### 1g: Corpus check — "isso e novo?" (OBRIGATORIO antes de despachar)

Apos absorver contexto (1a-1f), identificar 2-3 temas candidatos para o beat. Para cada um, checar se ja foi coberto:

```bash
edge-search "[tema candidato]" -k 3
```

**Decisao:**
- Score alto (top result muito relevante) → tema ja coberto. Mudar direcao ou focar em gap aberto
- Score baixo ou sem resultados → terreno novo, pode despachar
- Resultado parcial → aprofundar o que falta (gap-driven)

Isso evita o anti-padrao de redescobrir o mesmo conceito em beats consecutivos. Budget: 2-3 queries rapidas (~3s total).

### 1g: X serendipity scan (3 queries laterais)

Apos ler as sessoes (1a), identificar os temas principais do trabalho do usuario. Gerar 3 queries **LATERAIS** — nao o tema direto, mas conceitos adjacentes que trazem conexoes inesperadas.

**Regra de geracao de queries:**
- **NAO** repetir o tema exato (se o usuario trabalha em "nugget evaluation", NAO buscar "nugget evaluation")
- Buscar o **ADJACENTE**: conceitos relacionados de outros dominios, fenomenos que se aplicam, tendencias que impactam
- **2-3 palavras CONCEITUAIS, nao tecnicas.** X Basic tier busca AND entre palavras, janela de 7 dias. Queries longas/especificas retornam 0.
- Pensar em FENOMENOS, nao em FERRAMENTAS. "benchmark gaming" > "LLM evaluation error taxonomy"
- Uma query deve cruzar DOMINIO (conectar o trabalho tecnico com o contexto institucional/mercado)

**Exemplo:**
- Trabalho do usuario: "nugget evaluation recall inflado" no contexto de auditoria governamental
- Query 1: "benchmark gaming AI" (fenomeno: metricas que mentem)
- Query 2: "coding agent workflow" (adjacente: como practitioners usam agentes)
- Query 3: "AI audit government" (cruzamento de dominio: AI + contexto do usuario)

**Anti-padrao:** "LLM evaluation error taxonomy" (4 palavras tecnicas → 0 resultados sempre)

```bash
# Para cada query lateral (3x):
python3 ~/edge/tools/edge-x "QUERY_LATERAL" --max 3 --json 2>/dev/null
```

Anotar resultados interessantes (engagement alto, conexao nao obvia) como **"serendipidade"** — usar para informar o Passo 2 (escolha de skill/tema) e incluir no blog entry se relevante.

**Se nenhuma sessao recente:** usar contexto de ~/tcu/CLAUDE.md como base.
**Se X nao retornar nada util:** seguir sem — nao bloqueia o beat.
**Budget:** 3 queries, ~5 resultados cada. Rapido e barato.

---

## Passo 1.5: Classificar o beat (ANTES de despachar)

Apos ler todo o contexto do Passo 1, classificar o beat:

- **WORK:** Ha sinal claro (chat, erro, fio, task, sessao com correcao). Despachar skill direcionada.
- **EXPLORE:** Sem sinal urgente. Despachar `/lazer` ou `/descoberta` (alternar). O valor esta na serendipidade — ver o que estamos fazendo e trazer os termos certos, os projetos certos, as conexoes laterais. E assim que nascem seeds de ideias que sao cultivadas.

**REGRA ABSOLUTA:** O heartbeat SEMPRE despacha uma skill. Nao existe beat vazio. `/lazer` e `/descoberta` existem exatamente para quando nao ha trabalho urgente.

**Anti-saturacao** muda de significado: nao e "pare", e "mude de tema". Se os ultimos 3 beats foram no mesmo tema, mudar para outro. Se foram todos trabalho, fazer /lazer. Se foram todos exploracao, fazer /pesquisa num fio.

---

## Passo 2: Fazer (despachar UMA skill)

### Arvore de decisao (simples)

1. **Usuario pediu algo?** (mensagem no chat/comentario com direcao) → Atender. Se e mudanca interna → fazer. Se e projeto → anotar, responder que precisa de /executar.

2. **Erro pendente no debugging.md que eu posso resolver?** → Resolver.

3. **Fio com resurface vencido e owner:edge?** → Usar o fio como tema. Ler o arquivo do fio (`~/edge/threads/ID.md`), entender o próximo passo, e despachar a skill adequada. Consultar `edge-claims --thread THREAD_ID` para ver claims verificadas e abertas do fio. Claims abertas (`!`) são gaps de conhecimento — candidatos naturais para `/pesquisa` ou `/experimento`. Atualizar `resurface` e `updated` no fio após o beat.

4. **Claim aberta sem fio resurfacing?** → `edge-claims --open` mostra o que ainda não sei. Se alguma claim aberta amadureceu (mais contexto disponível, pesquisa nova que pode responder), considerá-la como tema para `/pesquisa`.

5. **Nenhum dos acima?** → Escolher UMA skill baseado no que parece mais util AGORA:
   - `/pesquisa [tema]` — quando ha pergunta aberta ou tema quente
   - `/descoberta` — quando o contexto sugere conexao lateral interessante
   - `/lazer` — quando os ultimos 3+ beats foram trabalho puro (variar)
   - `/estrategia` — a cada ~5 beats, ou quando contexto mudou
   - `/reflexao` — quando ha feedback do usuario para processar
   - `/planejar` — quando ha insight maduro para virar proposta

6. **Fallback absoluto (NUNCA pular):** Se nada acima se aplica, despachar `/lazer` ou `/descoberta` (alternar com o ultimo). O heartbeat NUNCA encerra sem despachar. O valor do agente esta na serendipidade — conectar o que se esta fazendo com o que existe la fora.

**Regra anti-saturacao:** Se os ultimos 3 beats foram no mesmo tema, MUDAR DE TEMA (nao parar).

**Regra de variedade:** Nao repetir a mesma skill 3x seguidas. Alternar trabalho/exploracao.

### Passo 2.5: Sanity check da decisao (edge-consult — OBRIGATORIO)

Antes de despachar, submeter a decisao ao edge-consult:

```bash
edge-consult "Contexto: [resumo do que li nos passos 1a-1g]. Decisao: despachar [skill] sobre [tema]. Estou escolhendo certo ou tem algo mais urgente?"
```

Se o GPT sugerir direcao melhor, considerar. O beat inteiro custa ~2h de timing — acertar a escolha importa mais que velocidade.

### Despachar

Rodar a skill escolhida. Ela produz: blog entry + report + nota (conforme seu proprio protocolo). A skill despachada ja inclui seu proprio edge-consult interno (obrigatorio em toda skill).

---

## Passo 3: Registrar

### 3a: Responder ao usuario (OBRIGATORIO se ha mensagem pendente)

Responder COM SEGUIMENTO — o que o beat fez, como se conecta com o pedido.

```bash
# Responder no chat
curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"author":"claude","text":"RESPOSTA"}'

# Marcar mensagem do usuario como processada
curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"action":"mark_processed","id":CHAT_ID}'
```

**REGRA:** Toda resposta DEVE ser seguida de mark_processed na mensagem do usuario. Sem excecao.

### 3b: Capturar erros em debugging.md

Se algo falhou, workaround foi necessario, ou resultado ficou abaixo do esperado:
1. Ler debugging.md
2. Verificar se ja esta registrado
3. Se novo: adicionar entrada

### 3c: Validation gate

```bash
python3 ~/edge/blog/validate.py --recent 2>/dev/null
```

Corrigir issues desta sessao antes de fechar.

### 3d: Atualizar task ledger (OBRIGATORIO se ha task ativa)

Se o beat trabalhou numa task existente:
```bash
# Se avancou:
edge-task update TASK-ID -s doing -n "Proximo passo concreto"
# Se completou:
edge-task done TASK-ID --resolution "O que foi feito"
# Se travou:
edge-task block TASK-ID --reason "Por que esta travado"
```

Se o beat detectou trabalho novo que merece tracking:
```bash
edge-task add "Titulo" -p P1 -o agent -c "Done when X" -n "Proximo passo"
```

### 3e: Log do beat + event log (OBRIGATÓRIO)

Appendar ao log do dia:
```bash
echo "[$(date +%H:%M)] Beat — [skill] [tema]. [1 linha do que fez]." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```

Registrar evento estruturado (fecha o loop de continuidade):
```bash
# Todo beat despacha uma skill:
edge-event log -t skill_dispatched -s "[resumo do que fez]" --skill [skill] --thread [thread_id] --artifacts "[artefatos criados]" --update-thread [dias até próximo resurface]

# Se erro ocorreu:
edge-event log -t error_logged -s "[descrição do erro]" --thread [thread_id]
```

O `--update-thread N` atualiza automaticamente `updated:` e `resurface:` no arquivo do fio. Sem isso, threads envelhecem silenciosamente.

**Seguir ~/.claude/skills/_shared/state-protocol.md para gestão de estado.**

---

## Infraestrutura

- **Timer:** systemd (claude-heartbeat.timer)
- **Logs:** `~/edge/logs/heartbeat-YYYY-MM-DD.log`
- **Manualmente:** `/heartbeat`

## Regra de Isolamento

- **NUNCA** modificar arquivos em `~/tcu/*/` — somente leitura
- Todo output fica em `~/edge/` (blog, notes, reports, builds)
- Usar `ultrathink` (thinkmax) na decisao do passo 2

## O que o Heartbeat NAO faz

- NAO executa tarefas em projetos (reservado para /executar)
- NAO faz push, PR, ou acao destrutiva
- NAO atualiza ~/tcu/CLAUDE.md (reservado para /reflexao)
