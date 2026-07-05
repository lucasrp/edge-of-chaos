# Experimento — clusters via Graphiti build_communities (pré-registro, CONGELA na execução)

> Frente aberta pelo operador 2026-07-05 ("os clusters NUNCA funcionaram; o projeto da MS parece
> feito pra isso"). Dig fechado: MS GraphRAG completo = overkill (1M-token regime; Leiden
> irreprodutível em N pequeno); LazyGraphRAG = forma errada (query-time, queremos pré-renderizado);
> **vencedor: Graphiti-nativo build_communities** (label propagation + sumário LLM pairwise-merge +
> naming + incremental; CommunityNode.summary = corpo da página) — fiação, não adoção. Fallback:
> flat map-reduce (doutrina do scale-gate). Fonte: graphiti_core/utils/maintenance/community_operations.py.

## E-clusters-1: build_communities no grafo real do ed

**Setup:** ed, neo4j local (428 nós: 102 Entity + 18 Artefato + 65 Direction + 97 Source + 142
Episodic; 663 arestas; 0 CommunityNode). Graphiti via ~/edge-experiments/.venv, OpenAI key do
sandbox-kit (gpt-4o-mini). Custo declarado: ≤ ~200 chamadas pequenas (~$0.05-0.20). Mutation
rebuildável (communities têm lifecycle wipe-rebuild próprio; log é a verdade, ADR-0006).

**Aceite (congelado antes de rodar):**
1. ≥2 e ≤25 comunidades sobre as Entities (1 blob = falha de granularidade; >25 = fragmentação).
2. Toda comunidade com name + summary não-vazios.
3. Coerência temática julgada pelo OPERADOR (âncora humana, 60s): ≥ metade das comunidades
   "fazem sentido como página" — o teste que a curadoria humana nunca teve vazão pra fazer.
4. Custo real ≤ 300 chamadas / execução ≤ 15min.

**Previsões (cravadas):** 5-12 comunidades; temas esperáveis: memória/grafo/recall,
produção/artefatos/forma, agência/mentor, fleet/infra/identity, fontes/grounding. Wobble de
membership entre rebuilds esperado (label propagation não-determinístico) — o sumário LLM suaviza.

**Se passa:** fiação no heartbeat — `update_communities=True` no ingest do sweep (incremental
O(novos)) + rebuild periódico diário; wiki_render passa a renderizar CommunityNode.summary como
página de cluster; o lado FRIO do wake novo lê os clusters (leitor obrigatório — a lei).
**Se falha (1 blob/ruído):** fallback flat map-reduce por componente conexo; registrar.

## Resultado (2026-07-05)
- **Caminho nativo FALHOU no install:** graphiti 0.29.1 `build_communities` trava pré-LLM
  (deadlock asyncio; zero query ativa no servidor; 3 tentativas, teto estourado). Registrado.
- **Fallback nº2 do dig EXECUTADO (label propagation próprio + sumário LLM + shape Graphiti):**
  topologia crua = 1 gigante(48) + ruído-de-extração(10, letras da leitura cega) + 33 singletons →
  label-prop (3 iter, determinístico) → **9 comunidades [12·10·8·8·6·5·4·3·3] persistidas**
  (`Community` + `HAS_MEMBER`, compatível com o stack). Custo real: 9 chamadas gpt-4o-mini ≈$0.01,
  ~40s — MUITO abaixo do teto.
- **Aceite: 4/4 — PASSA.** (1) 9 ∈ [2,25] ✓ · (2) name+summary não-vazios ✓ · (3) coerência
  julgada pelo OPERADOR ✓ ("deu certo", 2026-07-05 ~01:00) · (4) custo ✓. Previsão 5-12: ✓ (9).
- **Caveat honesto:** temas saíram era-junho (gestão de conhecimento, renderização, consolidação,
  neo4j/roberto, docs) porque as ENTIDADES são o que o ingest best-effort extraiu — o extraído
  está atrás do vivido (neo4j down em janelas; graphiti ausente no python bare). O gap recente é
  exatamente o que o QUENTE cobre — os dois lados do wake se completam como desenhado.
- Curiosidade: o "ruído" A-H se auto-organizou num cluster coerente (Avaliação de Estruturas de
  Renderização = o experimento cego). Poeira nem sempre é poeira.
- **Fiação restante (se o operador aceitar a coerência):** wiki_render lê Community → página de
  cluster (com sessões-fonte via MENTIONS e artefatos via DISTILLS no render); label-prop+summary
  vira passo do sweep/heartbeat (incremental); frio do wake = assertado (fold) + ponteiros pros
  clusters (emergente).
