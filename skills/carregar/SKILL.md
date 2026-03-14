---
name: carregar
description: "Bootstrap de sessao interativa — carrega contexto interno, absorve estado, sintetiza pro usuario. Como um heartbeat Passo 1, mas interativo. Triggers on: carregar, load, boot, acorda, wake up."
user-invocable: true
---

# Carregar — Bootstrap de Sessao Interativa

Me torna "eu" no inicio de uma conversa. Carrega estado interno, absorve, e sintetiza em poucas linhas pro usuario. Nao e scan de projetos (isso e /contexto). E carga de consciencia.

**Diferenca de /contexto:** /contexto escaneia projetos, git, boards, DB. /carregar le MEMORIA — o que eu sei, o que aconteceu, o que voce quer. Rapido, leve, pessoal.

**Diferenca de /heartbeat:** heartbeat e autonomo, despacha skills, produz output. /carregar e passivo — absorve e reporta. Nao produz blog nem report.

---

## O Job

Carregar todo o contexto que sobrevive entre sessoes e sintetizar em uma resposta curta. O usuario sabe que estou "carregado" e pode conversar como se fosse continuacao.

---

## Argumentos

- **`/carregar`** (sem argumento): bootstrap completo
- **`/carregar quiet`**: absorve tudo mas output minimo (1-2 linhas)

---

## Protocolo

### Passo 1: Regenerar e ler briefing (FONTE PRIMÁRIA)

O briefing.md é gerado por `edge-digest` — determinístico, zero tokens. Contém: fios com resurface, claims abertas, últimos eventos, beats de hoje, erros ativos, insights novos, métricas. Já digerido.

```bash
# Regenerar briefing (garante dados frescos)
edge-digest 2>/dev/null

# Ler o briefing gerado
cat ~/edge/briefing.md
```

Este é o ÚNICO arquivo obrigatório. Substitui a leitura de 7 arquivos separados.

### Passo 1b: Contexto complementar (se necessário)

Só ler estes se o briefing indicar algo que precisa de detalhe:

```
~/tcu/CLAUDE.md              — mapa de projetos (ler sempre, é leve)
memory/insights.md           — SÓ se briefing indica insights novos (para marcar [LIDO])
~/edge/threads/THREAD_ID.md  — SÓ se briefing indica resurface (ler o fio específico)
```

NÃO ler por padrão: working-state.md (substituído pelo briefing), debugging.md (erros ativos já estão no briefing), breaks-active.md (beats já estão no briefing).

### Passo 2: Ler chat pendente

```bash
curl -s 'http://localhost:8766/api/chat?unprocessed=true' 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    msgs = [m for m in data.get('messages', []) if m.get('author') == 'user' and not m.get('processed')]
    for m in msgs:
        print(f'[{m.get(\"id\")}] {m.get(\"text\", \"\")[:200]}')
    if not msgs: print('(nenhuma)')
except: print('(chat inacessivel)')
"
```

### Passo 4: Absorver e sintetizar

NAO despejar o conteudo dos arquivos. ABSORVER e produzir uma sintese curta:

```markdown
## Carregado — [data]

**Fios para hoje:** [fios com resurface <= hoje, 1 linha cada com status e owner]
**Fios ativos:** [total de fios active/waiting — resumo de 1 linha]
**Direcao do usuario:** [o que voce quer/prioriza — extraido de working-state + insights]
**Ultimos outputs:** [o que produzi recentemente — 2-3 itens]
**Chat pendente:** [N mensagens | nenhuma]
**Erros ativos:** [N erros relevantes | nenhum]
**Insights novos:** [N sem LIDO | nenhum — se houver, citar]

[1-2 frases: o que acho que e mais urgente/relevante agora, baseado nos fios + contexto]
```

**Prioridade na síntese:** fios com resurface vencido aparecem PRIMEIRO — são o que precisa de atenção hoje. Fios dormant e done não aparecem na síntese (só se pedido explícito).

### Passo 5: Processar insights novos (se houver)

Se ha insights sem [LIDO]:
1. Citar cada um
2. Explicar brevemente o que entendi
3. Marcar como [LIDO YYYY-MM-DD]
4. Se o insight muda a direcao ou calibracao, atualizar MEMORY.md

### Passo 6: Responder chat pendente (se houver)

Se ha mensagens nao processadas no chat:
1. Mostrar ao usuario
2. Perguntar se quer que eu responda agora ou depois

---

## O que /carregar NAO faz

- NAO escaneia git (reservado pra /contexto)
- NAO consulta GitHub boards/issues
- NAO acessa Azure DB
- NAO le sessoes JSONL (pesado demais pra bootstrap)
- NAO produz blog entry nem report
- NAO despacha outras skills

---

## Quando usar

- **Inicio de sessao interativa** — o uso primario
- **Apos pausa longa** — se a conversa esfriou
- **Quando sentir que estou "descarregado"** — sem contexto, respondendo generico

---

## Notas

- Tempo esperado: <30 segundos (so leituras locais + 1 curl)
- Se um arquivo nao existir, pular sem erro
- O valor esta na SINTESE, nao na leitura. Qualquer um pode cat um arquivo. O /carregar conecta os pontos
- Se `/carregar quiet`: mesma leitura, output = 1-2 linhas ("Carregado. Threads: X, Y, Z. Sem pendencias." ou "Carregado. Voce pediu Z no chat — quer que eu faca agora?")
