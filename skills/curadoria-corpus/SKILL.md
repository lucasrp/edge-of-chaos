---
name: {{PREFIX}}-curadoria-corpus
description: "Corpus curation skill. Computes document health metrics, identifies redundancy clusters, proposes merge/archive/strengthen actions. Triggers on: curadoria, curadoria corpus, corpus health, document curation, corpus cleanup."
user-invocable: true
---

# Curadoria de Corpus

Avaliar saude do corpus de documentos, identificar redundancias, propor acoes (KEEP/ARCHIVE/MERGE/STRENGTHEN), e manter o corpus curado ao longo do tempo.

Pode ser invocado standalone ou pelo /{{PREFIX}}-reflexao (que passa contexto de threads ativas e gaps recentes).

---

## Modos de Operacao

| Modo | Invocacao | Tempo | O que faz |
|------|-----------|-------|-----------|
| **stats** | `/{{PREFIX}}-curadoria-corpus stats` | ~10s | Metricas por documento (retrieval count, top3, diversidade de queries) |
| **lite** | `/{{PREFIX}}-curadoria-corpus lite` | ~30s | Stats + identificacao de candidatos stale (age>45d, sem retrieval recente) |
| **full** | `/{{PREFIX}}-curadoria-corpus` | ~3min | Lite + self-probes + clustering nearest-neighbor + classificacao + veto estrategico |

---

## Argumentos

- **modo**: `full` (default), `lite`, `stats`
- **active_threads**: lista de threads ativas (passada pelo /{{PREFIX}}-reflexao ou informada manualmente). Suprime archive de docs relacionados.
- **recent_gaps**: lista de gaps recentes (passada pelo /{{PREFIX}}-reflexao). Docs que cobrem gaps nao sao arquivados.

---

## Protocolo

### Passo 1: Determinar modo

Verificar argumento passado pelo usuario:
- Sem argumento ou `full` → modo full
- `lite` → modo lite
- `stats` → modo stats

### Passo 2: Coletar metricas (todos os modos)

Executar curadoria_compute.py no modo correspondente:

```bash
python3 ~/edge/tools/curadoria_compute.py --mode stats
```

Isso consulta a tabela `search_events` em `~/edge/search/edge-memory.db` e computa por documento:
- **retrieved_count**: total de vezes que o doc apareceu em resultados de busca
- **top3_count**: vezes que apareceu no top-3
- **last_retrieved**: data da ultima recuperacao
- **query_diversity**: numero de queries distintas que recuperaram o doc
- **age_days**: idade do documento em dias

Apresentar resumo ao usuario: total de docs, docs com 0 retrievals, doc mais acessado, doc mais antigo sem acesso.

**Se modo = stats, parar aqui.**

### Passo 3: Identificar candidatos stale (lite e full)

```bash
python3 ~/edge/tools/curadoria_compute.py --mode lite
```

Criterios de stale:
- **age > 45 dias** E **retrieved_30d = 0** (ninguem buscou nos ultimos 30 dias)
- OU **age > 45 dias** E **top3_30d = 0** (apareceu em buscas mas nunca no top-3)

Listar candidatos stale com suas metricas.

**Se modo = lite, parar aqui.**

### Passo 4: Self-probes (full only)

Para cada candidato stale, o script executa uma self-probe:
- Constroi uma query a partir do titulo + 2 termos raros do conteudo
- Executa `edge-search --no-telemetry "query"`
- Registra o **self_rank** (posicao do doc nos resultados)

```bash
python3 ~/edge/tools/curadoria_compute.py --mode full --active-threads "thread1,thread2" --recent-gaps "gap1,gap2"
```

Interpretacao:
- self_rank <= 3: doc e relevante para seu proprio conteudo → KEEP
- self_rank 4-5: doc e encontravel mas nao dominante → avaliar contexto
- self_rank > 5 ou ausente: doc esta enterrado → candidato a ARCHIVE/MERGE

### Passo 5: Clustering por nearest-neighbor (full only)

O script agrupa candidatos stale por similaridade semantica:

**Algoritmo (union-find):**
1. Para cada candidato stale, buscar top-3 vizinhos do mesmo tipo no corpus
2. Adicionar aresta se: `nn_sim >= 0.90` OU (`nn_sim >= 0.83` E `title_overlap >= 0.5`)
3. Formar clusters via union-find

### Passo 6: Classificacao (full only)

O script classifica cada documento/cluster em uma das 4 categorias:

#### ARCHIVE (auto)
Criterios (TODOS devem ser verdadeiros):
- age > 120 dias
- rrf_30d = 0 (nenhuma recuperacao nos ultimos 30 dias)
- self_rank > 5 (nao e encontrado nem por self-probe)
- Tem vizinho forte (nn_sim >= 0.90) que cobre o conteudo

#### MERGE (review)
Criterios:
- Cluster com >= 3 documentos
- Similaridade mediana no cluster >= 0.83
- Requer revisao humana antes de executar

#### STRENGTHEN
Criterios:
- Cluster com alta demanda (rrf acima do p75 do corpus)
- Mas nenhum doc consistente no top-3
- Acao: melhorar titulo/conteudo do doc mais relevante

#### KEEP
- Todos os demais documentos

### Passo 7: Veto estrategico (full only)

Mecanismo de supressao para proteger docs ativos:
- Se o titulo ou conteudo de um doc candidato a ARCHIVE menciona alguma **active_thread** → suprimir (mover para `suppressed_due_to_active_thread`)
- Se o conteudo cobre algum **recent_gap** → suprimir

Isso impede que /{{PREFIX}}-reflexao archive documentos que sao relevantes para trabalho em andamento.

### Passo 8: Persistir resultados

O script salva automaticamente em:

```
~/edge/state/curadoria-candidates.json
```

Estrutura do JSON:
```json
{
  "generated_at": "ISO timestamp",
  "mode": "full|lite|stats",
  "total_docs": N,
  "stale_candidates": N,
  "archive_auto": [
    {"doc_id": 1, "title": "...", "age_days": N, "self_rank": N, "nn_sim": 0.95, "reason": "..."}
  ],
  "merge_review": [
    {"cluster_id": 1, "docs": [...], "median_sim": 0.87, "suggestion": "..."}
  ],
  "strengthen_targets": [
    {"doc_id": 2, "title": "...", "demand_rrf": N, "best_rank": N, "suggestion": "..."}
  ],
  "suppressed_due_to_active_thread": [
    {"doc_id": 3, "title": "...", "matching_thread": "...", "original_action": "ARCHIVE"}
  ]
}
```

### Passo 9: Apresentar resultados

Resumir para o usuario:
1. Quantos docs analisados, quantos stale
2. **Archive auto**: listar docs que serao arquivados (acao automatica, mas confirmar se > 3)
3. **Merge review**: listar clusters que precisam de revisao humana
4. **Strengthen**: listar docs que precisam de melhoria
5. **Suprimidos**: listar docs protegidos por veto estrategico e o motivo

---

## Integracao com /{{PREFIX}}-reflexao

Quando invocado pelo /{{PREFIX}}-reflexao em modo manual:
1. /{{PREFIX}}-reflexao passa `active_threads` (de git_signals thread_coverage) e `recent_gaps` (de claims_summary persistent_gaps)
2. /{{PREFIX}}-curadoria-corpus roda em modo full com esses parametros
3. /{{PREFIX}}-reflexao le o resultado em `curadoria-candidates.json` e toma decisoes estrategicas

---

## Arquivos

| Arquivo | Leitura/Escrita | Descricao |
|---------|----------------|-----------|
| `~/edge/search/edge-memory.db` | Leitura | Tabelas documents e search_events |
| `~/edge/state/curadoria-candidates.json` | Escrita | Resultado da curadoria |
| `~/edge/tools/curadoria_compute.py` | Execucao | Engine de computacao |
