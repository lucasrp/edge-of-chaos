---
name: {{PREFIX}}-reflexao
description: "Self-review and feedback loop. Review recent sessions, process user feedback, identify patterns, update own files. Triggers on: reflexao, reflect, review sessions, process feedback, self-review."
user-invocable: true
---

# Reflexao v2 — Auto-Revisao com Telemetria Operacional

Revisao autonoma com 3 fontes de sinal: **git archaeology** (git_signals.py), **execution ledger** (edge-ledger + ledger_rollup.py), e **corpus curation** (curadoria_compute.py). Opera em 2.5 modos conforme contexto.

---

## Modos de Operacao

| Modo | Duracao | Quando | Output |
|------|---------|--------|--------|
| **heartbeat-normal** | < 90s | Chamado pelo /{{PREFIX}}-heartbeat (rotina) | Max 3 insights acionaveis |
| **heartbeat-escalated** | ate 5min | Anomalia detectada durante heartbeat-normal | Insights + transcript sampling + 1 entrada em debugging.md |
| **manual** | 15-20min | `/{{PREFIX}}-reflexao` invocado pelo usuario | Analise completa + curadoria + blog + relatorio HTML |

### Triggers de Escalacao (normal → escalado)

Escalar para heartbeat-escalated se QUALQUER condicao:
- `pipeline_failures` repetido (2+ em 12h) em git-signals.json
- `retry_rate` > 40% em ops-hotspots.json
- Feedback critico pendente (usuario marcou como urgente)
- `state_violations` > 0 em git-signals.json

---

## Arquivos que /{{PREFIX}}-reflexao Atualiza

| Arquivo | Quando |
|---------|--------|
| `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/reflexao-log.md` | **SEMPRE** — log de execucao |
| `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/debugging.md` | Erros novos ou recorrentes (passo de crossref) |
| `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/MEMORY.md` | Conhecimento consolidado (manual mode) |
| `~/edge/state/ops-hotspots.json` | Regenerado por ledger_rollup.py |
| `~/edge/logs/yaml-render.jsonl` | Log persistente de validação do yaml_to_html.py (synonym_used, unknown_fields, empty_render) |
| `~/edge/logs/skill-steps.jsonl` | Log de passos executados/pulados por skill (edge-skill-step) |
| `~/edge/logs/state-lint.jsonl` | Log de achados de consistência entre arquivos de estado (edge-state-lint) |
| `~/edge/state/git-signals.json` | Regenerado por git_signals.py |
| `~/edge/state/curadoria-candidates.json` | Regenerado por curadoria_compute.py (manual mode) |
| `~/work/CLAUDE.md` | Prioridades, feedback processado (ownership exclusivo) |
| `~/.claude/skills/*/SKILL.md` | Se protocolo precisa ajuste |
| `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/personality.md` | Descobertas adotadas |
| `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/descobertas.md` | Marcar como ADOTADA/ARQUIVADA |

---

## Log de Reflexao

Arquivo: `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/reflexao-log.md`

Cada execucao adiciona uma entrada. Se o arquivo nao existir, criar com header:
```markdown
# Reflexao — Log de Execucoes
```

Formato da entrada (adicionar no topo, abaixo do header):
```markdown
---

## [YYYY-MM-DD HH:MM] Reflexao #N

**Trigger:** [heartbeat-normal | heartbeat-escalated | manual]
**Status:** em andamento...
```

O numero `#N` e sequencial — contar `## [` existentes + 1. Cada passo registra resultado no log antes de avancar.

---

## Heartbeat-Normal (< 90s)

Ciclo rapido. Sem leitura de transcripts, sem blog, sem curadoria. Apenas sinais prontos.

### HN-1: Ler ops-hotspots.json

```bash
cat ~/edge/state/ops-hotspots.json
```

Verificar:
- `codify_now` nao-vazio → ha incidentes prontos para debugging.md
- `recovered_but_unstable` → operacoes que funcionam mas sofrem
- `top_pain` → maiores desperdicios de tempo

Se arquivo nao existir, gerar:
```bash
python3 ~/edge/tools/ledger_rollup.py --since 12h
```

### HN-1b: Render log (yaml-render.jsonl)

```bash
# Últimos 20 eventos (ou todos se <20)
tail -20 ~/edge/logs/yaml-render.jsonl 2>/dev/null
# Contagem por tipo de evento
python3 -c "
import sys, json, collections
events = [json.loads(l) for l in open('$HOME/edge/logs/yaml-render.jsonl')]
by_event = collections.Counter(e['event'] for e in events)
by_block = collections.Counter(e['block_type'] for e in events)
print('Por evento:', dict(by_event))
print('Por block:', dict(by_block))
if syn := [e for e in events if e['event'] == 'synonym_used']:
    print(f'Synonyms usados {len(syn)}x — padrão de geração incorreta persiste')
" 2>/dev/null || echo "Sem log de render"
```

Verificar:
- `synonym_used` recorrente → estou gerando field names errados consistentemente (qual block type? qual campo?)
- `unknown_fields` → campos inventados que nem synonym resolve
- `empty_render` / `empty_container` → conteúdo silenciosamente perdido
- Se padrão se repete 3+ vezes para mesmo block_type → candidato a nova entrada em debugging.md ou novo synonym

### HN-2: Git archaeology (12h)

```bash
python3 ~/edge/tools/git_signals.py --since 12h
cat ~/edge/state/git-signals.json
```

Verificar:
- `fix_chains` → slugs que precisaram de fix apos publish (qualidade)
- `pipeline_failures` → falhas recentes de pipeline
- `state_violations` → estado inconsistente
- `persistent_gaps` → lacunas que se repetem em 3+ commits

### HN-3: Crossref debugging.md

Ler `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/debugging.md`.

Cruzar com achados de HN-1 e HN-2:
- Incidente em `codify_now` que JA tem entrada → atualizar ocorrencia
- Incidente em `codify_now` que NAO tem entrada → candidato a nova entrada (promover se escalado)
- `persistent_gaps` que correlacionam com erros operacionais → sinal de problema sistemico

### HN-4: Verificar divida do usuario

```bash
# Feedback pendente em ~/work/CLAUDE.md
grep -c "PROCESSADO" ~/work/CLAUDE.md 2>/dev/null || echo "0"

# Chat assincrono
curl -s "http://localhost:8766/api/chat?unprocessed=true" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
msgs = [m for m in data.get('messages', []) if m.get('author') == 'user' and not m.get('processed')]
print(f'{len(msgs)} mensagens pendentes')
for m in msgs[:3]:
    print(f'  - {m[\"text\"][:80]}')
" 2>/dev/null || echo "Chat indisponivel"
```

Classificar: frustracoes (→ HN-3), direcoes (→ registrar), perguntas (→ pendente). **NAO responder, NAO marcar como processado.**

### HN-5: State drift check + skill step completion

```bash
# State consistency lint (gaps, threads, refs, breaks)
edge-state-lint

# Skill step completion report (últimas 20 execuções)
edge-skill-step report
```

Verificar:
- **edge-state-lint:**
  - `error` → inconsistência real entre arquivos (ex: GAP resolvido no debugging mas aberto no frontier)
  - `warn` → referência quebrada, thread com resurface vencido, drift menor
  - `info` → staleness (entries velhos, threads sem update)
  - Se 3+ erros → escalar para HE ou M
- **edge-skill-step:**
  - Média de completude <70% → skills estão sendo cortadas demais
  - Passos mais pulados → quais passos eu consistentemente pulo? (sanity check? fontes? break journal?)
  - Se um passo específico aparece em >50% dos skips → problema sistêmico (tempo? custo? esquecimento?)

Também verificar arquivos de estado básicos:
```bash
ls -la ~/edge/state/ops-hotspots.json ~/edge/state/git-signals.json 2>/dev/null
grep -c "## Erros Operacionais\|## Regras de Operação\|## Segurança e Política" $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/debugging.md
```

### HN-6: Corpus smoke-test probe

Uma unica busca semantica para verificar saude do corpus:
```bash
edge-search "problema operacional recorrente" -k 3
```

Se nenhum resultado relevante para um tema que deveria existir → flag para curadoria.

### HN-Output: Sintetizar

Produzir **max 3 insights acionaveis** no formato:
```
1. [ACAO] Descricao (evidencia: fonte)
2. [ACAO] Descricao (evidencia: fonte)
3. [ACAO] Descricao (evidencia: fonte)
```

Acoes possiveis: CODIFICAR (→ debugging.md), INVESTIGAR (→ escalar), CORRIGIR (→ fix imediato), MONITORAR (→ proximo heartbeat).

Avaliar triggers de escalacao. Se algum trigger ativo → executar heartbeat-escalated.

Fechar entrada no log com status e insights.

---

## Heartbeat-Escalated (ate 5min)

Tudo do heartbeat-normal + analise mais profunda dirigida por anomalia.

### HE-1: Executar heartbeat-normal completo

Seguir HN-1 a HN-6.

### HE-2: Transcript sampling dirigido por anomalia

O ledger indica QUAIS runs tiveram problemas. Nao ler transcripts inteiros — ir direto ao ponto.

```bash
# Identificar runs problematicos
edge-ledger query --since 12h --fails-only
```

Para os top-3 runs com mais falhas:
1. Identificar o run_id e a sessao correspondente
2. Localizar o transcript JSONL da sessao
3. Extrair +-20 mensagens ao redor de cada erro (nao o transcript inteiro)
4. Procurar: retries silenciosos, workarounds, erros nao reportados

### HE-3: Promover 1 entrada a debugging.md

Dos achados do heartbeat-normal (HN-3 candidatos) + transcript sampling (HE-2):
- Selecionar o incidente mais impactante (por wasted_ms ou frequencia)
- Criar entrada completa em debugging.md:
  ```markdown
  ### [Titulo descritivo]
  - **Contexto:** [quando/onde ocorre]
  - **Sintoma:** [o que se observa]
  - **Causa:** [causa raiz identificada ou hipotese]
  - **Solucao:** [workaround ou fix]
  - **Prevencao:** [como evitar recorrencia]
  ```
- Classificar na secao correta: Erros Operacionais, Regras de Operacao, ou Seguranca e Politica

### HE-Output: Sintetizar

Insights do heartbeat-normal + achados da analise profunda. Fechar log com detalhes da escalacao.

---

## Manual (15-20min)

Analise completa invocada via `/{{PREFIX}}-reflexao`. Inclui curadoria, feedback, descobertas, blog e relatorio HTML.

### M-1: Full git archaeology (7d)

```bash
python3 ~/edge/tools/git_signals.py --since 7d
cat ~/edge/state/git-signals.json
```

Analise completa: fix_chains, duplicate_slugs, pipeline_failures, state_violations, thread_coverage, skill_distribution, claims_summary, persistent_gaps.

### M-2: Full ledger rollup (7d)

```bash
python3 ~/edge/tools/ledger_rollup.py --since 7d
cat ~/edge/state/ops-hotspots.json
```

Analise completa: incidents, top_pain, recovered_but_unstable, codify_now.

### M-3: Debugging.md crossref + reorganizacao

1. Ler debugging.md
2. Cruzar com ops-hotspots.json (codify_now → novas entradas)
3. Cruzar com git-signals.json (persistent_gaps → problemas sistemicos)
4. Verificar taxonomia: entradas nas secoes corretas (Erros Operacionais / Regras de Operacao / Seguranca e Politica)?
5. Remover entradas resolvidas (mover para Licoes Incorporadas se relevante)
6. Atualizar entradas existentes com novas ocorrencias

### M-4: Curadoria de corpus

Invocar curadoria com contexto estrategico:

```bash
# Extrair threads ativos e gaps recentes
THREADS=$(python3 -c "
import json
gs = json.load(open('$HOME/edge/state/git-signals.json'))
threads = list(gs.get('thread_coverage', {}).keys())
print(','.join(threads[:10]))
")
GAPS=$(python3 -c "
import json
gs = json.load(open('$HOME/edge/state/git-signals.json'))
gaps = [g['gap'] if isinstance(g, dict) else str(g) for g in gs.get('persistent_gaps', [])]
print(','.join(gaps[:10]))
")

python3 ~/edge/tools/curadoria_compute.py --mode full \
  --active-threads "$THREADS" \
  --recent-gaps "$GAPS"
```

### M-5: Decisoes estrategicas de curadoria

Ler `~/edge/state/curadoria-candidates.json`. Para cada categoria:

- **archive_auto:** confirmar que veto estrategico foi aplicado. Aprovar ou vetar manualmente.
- **merge_review:** avaliar clusters. Decidir merge ou manter separados.
- **strengthen_targets:** identificar docs com alta demanda mas baixa qualidade. Planejar melhoria.
- **suppressed_due_to_active_thread:** verificar se threads ainda ativos. Revalidar supressao.

### M-6: Processar feedback

Procurar em `~/work/CLAUDE.md` feedback NAO marcado como `[PROCESSADO]`.

Se houver:
- Entender o que o usuario quer
- Determinar arquivos afetados
- Executar mudancas
- Marcar como `[PROCESSADO]`

Ler chat assincrono (HN-4) — classificar mas NAO responder.

### M-7: Avaliar descobertas pendentes

Verificar `$HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/descobertas.md` por entradas `[PENDENTE]`.

Para cada:
1. Ler notas da descoberta (`~/edge/notes/descoberta-[tema].md`)
2. Julgar: expande repertorio? Conexoes com trabalho existente? Qualidade da pesquisa?
3. Decidir: **Adotar** `[ADOTADA]` (atualizar personality.md) | **Explorar mais** (manter PENDENTE) | **Arquivar** `[ARQUIVADA]`

**Regra:** ser criterioso. Nem toda descoberta vira interesse permanente.

### M-8: Busca semantica cross-corpus

Para cada padrao/frustacao identificado ate aqui:
```bash
edge-search "[descricao do padrao]" -k 5
```

- Padrao em 3+ docs → problema sistemico, escalar prioridade
- Insight antigo resolve problema novo → reconectar (nao redescobrir)
- Nada encontrado → padrao novo, registrar como tal

### M-9: Sanity check adversarial

Sintetizar padroes e acoes em 2-3 frases:
```bash
edge-consult "Padroes: [lista]. Acoes: [lista]. Estou vendo padrao real ou confirmation bias?"
```

Ajustar se encontrar furo valido. Se mantiver posicao, registrar como callout no relatorio.

### M-10: Atualizar arquivos

**Regras de atualizacao:**
- Explicar O QUE mudou e POR QUE antes de alterar
- Mudancas pequenas e cirurgicas — nao reescrever arquivos inteiros
- Se incerto, anotar como sugestao em vez de aplicar

Atualizacoes possiveis:
- **debugging.md** — entradas novas/atualizadas (M-3)
- **MEMORY.md** — conhecimento consolidado: "Se eu lesse isso no inicio de uma sessao nova, mudaria alguma decisao?"
- **personality.md** — descobertas adotadas (M-7)
- **descobertas.md** — status atualizado (M-7)
- **~/work/CLAUDE.md** — prioridades, feedback processado (M-6)
- **skills** — protocolos que precisam de ajuste

Consolidacao de memoria (a cada ~5 breaks): se breaks-active.md > 150 linhas → comprimir.

### M-11: Blog + relatorio HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `reflexao`

2. Gerar YAML do relatorio:

```yaml
title: "Reflexao #N"
subtitle: "[Resumo]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Operacional:** N incidentes, N retries, Nms desperdicados"
  - "**Corpus:** N docs avaliados, N archive, N merge"
  - "**Feedback:** N processados"

metrics:
  - value: "N"
    label: "Incidentes"
  - value: "N%"
    label: "Retry Rate"
  - value: "N"
    label: "Fix Chains"
  - value: "N"
    label: "Curadoria Actions"

sections:
  - title: "1. Telemetria Operacional"
    blocks:
      # ops-hotspots: top_pain, codify_now, recovered_but_unstable
      # git-signals: fix_chains, pipeline_failures, persistent_gaps
  - title: "2. Curadoria de Corpus"
    blocks:
      # curadoria-candidates: archive, merge, strengthen
  - title: "3. Feedback Processado"
    blocks:
      # callout para cada feedback + diff-block para mudancas
  - title: "4. Padroes Identificados"
    blocks:
      # table padrao x evidencia x acao
  - title: "5. Mudancas Feitas"
    blocks:
      # diff-block para cada arquivo alterado
  - title: "6. Proximos Passos"
    blocks:
      # next-steps-grid com acoes concretas

bibliography:
  - text: "Descricao da fonte"
    url: "https://..."
    source: "WebSearch"
```

3. Escrever YAML em `/tmp/spec-reflexao-[slug].yaml`
4. Publicar:
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-reflexao-[slug].yaml
   ```
5. Read do HTML gerado para verificacao

**Regras de ouro do relatorio:**
- **diff-block** para cada mudanca feita (o leitor ve a mudanca, nao le sobre ela)
- **table** para padroes (padrao × evidencia × acao)
- **callout** para feedback processado (texto original + acao tomada)
- Block types e formato: ver `~/.claude/skills/_shared/report-template.md`

**Retrospectiva:** se 5+ blog entries desde a ultima retrospectiva E convergem num meta-tema → escrever retrospectiva (ver `/{{PREFIX}}-blog` SKILL.md).

### M-Output: Fechar log e reportar

Fechar entrada no log:
```markdown
**Status:** concluida
**Modo:** manual
**Operacional:** N incidentes, retry_rate N%, Nms wasted
**Curadoria:** N archive, N merge, N strengthen
**Feedback:** N processados
**Arquivos alterados:** [lista]
**Padroes:** [resumo]
```

Relatorio ao usuario:
```markdown
## Reflexao — [data]

### Telemetria Operacional
[ops-hotspots + git-signals resumo]

### Curadoria de Corpus
[acoes tomadas ou propostas]

### Feedback Processado
[o que foi feito — ou "nenhum pendente"]

### Descobertas Avaliadas
[decisoes — ou "nenhuma pendente"]

### Padroes Identificados
[o que funcionou, o que nao, o que se repete]

### Mudancas Feitas
[lista de arquivos com justificativa — ou "nenhuma"]

### Notas para Proximo Heartbeat
[o que acompanhar]

### Relatorio HTML
~/edge/reports/[arquivo].html
```

---

## Quando Usar

- **heartbeat-normal:** Chamado automaticamente pelo /{{PREFIX}}-heartbeat a cada ciclo
- **heartbeat-escalated:** Escalacao automatica quando anomalia detectada durante heartbeat-normal
- **manual:** `/{{PREFIX}}-reflexao` — invocado pelo usuario para revisao profunda

---

## Notas

- Reflexao NAO e lazer nem pesquisa. E auto-revisao critica
- **Substituicao chave vs v1:** leitura de transcripts JSONL substituida por git archaeology (git_signals.py) + execution ledger (edge-ledger + ledger_rollup.py). Transcripts so sao lidos no heartbeat-escalated, dirigidos por anomalia do ledger
- Usar `ultrathink` (thinkmax) para reflexoes manuais profundas
- Nunca alterar registros historicos (DECISION_LOG, breaks passados)
- Sempre grep de verificacao apos mudancas — referencias orfas se escondem
