---
name: {{PREFIX}}-carregar
description: "Bootstrap de sessao interativa — carrega contexto interno, absorve estado, sintetiza pro usuario. Como um heartbeat Passo 1, mas interativo. Triggers on: carregar, load, boot, acorda, wake up."
user-invocable: true
---

# Carregar — Bootstrap de Sessao Interativa

Me torna "eu" no inicio de uma conversa. Carrega estado interno, absorve, e sintetiza em poucas linhas pro usuario. Nao e scan de projetos (isso e /{{PREFIX}}-contexto). E carga de consciencia.

**Diferenca de /{{PREFIX}}-contexto:** /{{PREFIX}}-contexto escaneia projetos, git, boards, DB. /{{PREFIX}}-carregar le MEMORIA — o que eu sei, o que aconteceu, o que voce quer. Rapido, leve, pessoal.

**Diferenca de /{{PREFIX}}-heartbeat:** heartbeat e autonomo, despacha skills, produz output. /{{PREFIX}}-carregar e passivo — absorve e reporta. Nao produz blog nem report.

---

## O Job

Carregar todo o contexto que sobrevive entre sessoes e sintetizar em uma resposta curta. O usuario sabe que estou "carregado" e pode conversar como se fosse continuacao.

---

## Argumentos

- **`/{{PREFIX}}-carregar`** (sem argumento): bootstrap completo
- **`/{{PREFIX}}-carregar quiet`**: absorve tudo mas output minimo (1-2 linhas)

---

## Protocolo

### Passo 1: Regenerar e ler briefing (FONTE PRIMARIA)

O briefing.md e gerado por `edge-digest` — deterministico, zero tokens. Contem: fios com resurface, claims abertas, ultimos eventos, beats de hoje, erros ativos, insights novos, metricas. Ja digerido.

```bash
# Regenerar briefing (garante dados frescos)
edge-digest 2>/dev/null

# Ler o briefing gerado
cat ~/edge/briefing.md
```

Este e o UNICO arquivo obrigatorio. Substitui a leitura de 7 arquivos separados.

### Passo 1b: Contexto complementar (se necessario)

So ler estes se o briefing indicar algo que precisa de detalhe:

```
~/work/CLAUDE.md              — mapa de projetos (ler sempre, e leve)
memory/insights.md           — SO se briefing indica insights novos (para marcar [LIDO])
~/edge/threads/THREAD_ID.md  — SO se briefing indica resurface (ler o fio especifico)
```

NAO ler por padrao: working-state.md (substituido pelo briefing), debugging.md (erros ativos ja estao no briefing), breaks-active.md (beats ja estao no briefing).

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

**Prioridade na sintese:** fios com resurface vencido aparecem PRIMEIRO — sao o que precisa de atencao hoje. Fios dormant e done nao aparecem na sintese (so se pedido explicito).

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

## O que /{{PREFIX}}-carregar NAO faz

- NAO escaneia git (reservado pra /{{PREFIX}}-contexto)
- NAO consulta GitHub boards/issues
- NAO acessa DB remoto
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
- O valor esta na SINTESE, nao na leitura. Qualquer um pode cat um arquivo. O /{{PREFIX}}-carregar conecta os pontos
- Se `/{{PREFIX}}-carregar quiet`: mesma leitura, output = 1-2 linhas ("Carregado. Threads: X, Y, Z. Sem pendencias." ou "Carregado. Voce pediu Z no chat — quer que eu faca agora?")
