---
name: ed-curadoria-corpus
description: "Corpus curation skill. Computes document health metrics, identifies redundancy clusters, proposes merge/archive/strengthen actions. Triggers on: curadoria, curadoria corpus, corpus health, document curation, corpus cleanup."
user-invocable: true
---

# Curadoria de Corpus

Avaliar saude do corpus de documentos, identificar redundancias, propor acoes (KEEP/ARCHIVE/MERGE/STRENGTHEN), e manter o corpus curado ao longo do tempo.

Pode ser invocado standalone ou pelo /ed-reflexao (que passa contexto de threads ativas e gaps recentes).

---

## Modos de Operacao

| Modo | Invocacao | Tempo | O que faz |
|------|-----------|-------|-----------|
| **stats** | `/ed-curadoria-corpus stats` | ~10s | Metricas por documento (retrieval count, top3, diversidade de queries) |
| **lite** | `/ed-curadoria-corpus lite` | ~30s | Stats + identificacao de candidatos stale (age>45d, sem retrieval recente) |
| **full** | `/ed-curadoria-corpus` | ~3min | Lite + self-probes + clustering nearest-neighbor + classificacao + veto estrategico |

---

## Argumentos

- **modo**: `full` (default), `lite`, `stats`
- **active_threads**: lista de threads ativas (passada pelo /ed-reflexao ou informada manualmente). Suprime archive de docs relacionados.
- **recent_gaps**: lista de gaps recentes (passada pelo /ed-reflexao). Docs que cobrem gaps nao sao arquivados.

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

Isso impede que /ed-reflexao archive documentos que sao relevantes para trabalho em andamento.

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

## Claims Lifecycle (curadoria de claims)

Além de documentos, esta skill cuida do ciclo de vida das claims — consolidando memória de curto prazo (claims no frontmatter) em memória de longo prazo (topics/*.md).

### Modo claims

Invocação: `/ed-curadoria-corpus claims` ou `/ed-curadoria-corpus claims --thread THREAD_ID`

### Passo C1: Coleta

Para o thread especificado (ou todos os threads ativos):
1. Puxar todas as claims que tocam o thread (claims são 1:N com threads — uma claim pode pertencer a múltiplos threads via entry)
2. Separar verificadas (✓) e abertas (!)

```bash
edge-claims -t THREAD_ID
```

### Passo C2: Triagem automática (sem LLM)

Para o conjunto de claims coletadas:

**Duplicatas** — embedding similarity > 0.92 entre claims do mesmo thread. Agrupar candidatas.

**Factuais stale** — claims contendo números, datas ou contagens cuja entry tem mais de 30 dias E entries mais recentes existem no thread. Marcar como `stale_candidate`.

**Gaps potencialmente respondidos** — claim aberta (`!`) com embedding similar (> 0.85) a claim verificada posterior (data mais recente) no mesmo thread. Marcar como `answered_candidate`.

### Passo C3: Consolidação (LLM)

Mandar o batch de claims para `edge-consult` com prompt estruturado:

```bash
edge-consult "Claims do thread [ID]:
[lista de claims]

Classifique cada claim:
- keep: conhecimento independente que sobrevive
- merge(claim_ids): duplicatas que dizem a mesma coisa
- superseded_by(claim_text): foi atualizada por versão mais recente
- answered_by(claim_text): gap que foi respondido
- stale: factual com dados desatualizados
- keep_as_is: conceitual/atemporal, não tocar

Output: JSON array com {claim_text, action, target, reason}" --context ~/edge/threads/THREAD_ID.md
```

### Passo C4: Proposta de consolidação no topic

Com base no output do C3:
1. Claims `keep` que formam cluster (3+ sobre mesmo subtema) → propor parágrafo consolidado para o topic
2. Cada parágrafo inclui provenance: `← entry-slug-1, entry-slug-2`
3. Gaps `answered_by` → listar como resolvidos
4. Claims `stale` → listar para revisão
5. Claims `merge` → identificar canônica

Salvar proposta em `~/edge/state/claims-curation-{thread_id}.json`:
```json
{
  "thread_id": "...",
  "generated_at": "ISO",
  "total_claims": N,
  "actions": [
    {"claim": "...", "action": "keep|merge|superseded|answered|stale", "target": "...", "reason": "..."}
  ],
  "topic_patches": [
    {"section": "Extração de nuggets", "content": "...", "sources": ["entry-1", "entry-2"]}
  ],
  "gaps_resolved": [
    {"gap": "!...", "answered_by": "...", "evidence_entry": "..."}
  ]
}
```

### Passo C5: Aplicação

- Em sessão interativa: apresentar proposta ao Lucas, aplicar com confirmação
- Em sessão autônoma: aplicar automaticamente se todas as ações são low-risk (merge, answered, stale factual). Segurar high-risk (conceituais, decisões) para revisão humana.

Aplicar significa:
1. Atualizar o topic correspondente (adicionar parágrafos com provenance)
2. Gaps resolvidos permanecem no frontmatter original mas o topic reflete o estado atual

---

## Integracao com /ed-reflexao

Quando invocado pelo /ed-reflexao em modo manual:
1. /ed-reflexao passa `active_threads` (de git_signals thread_coverage) e `recent_gaps` (de claims_summary persistent_gaps)
2. /ed-curadoria-corpus roda em modo full com esses parametros
3. /ed-reflexao le o resultado em `curadoria-candidates.json` e toma decisoes estrategicas

---

## Arquivos

| Arquivo | Leitura/Escrita | Descricao |
|---------|----------------|-----------|
| `~/edge/search/edge-memory.db` | Leitura | Tabelas documents e search_events |
| `~/edge/state/curadoria-candidates.json` | Escrita | Resultado da curadoria |
| `~/edge/tools/curadoria_compute.py` | Execucao | Engine de computacao |
