# Design do yield join + tabela renderizada (Loop R · faceta 2)

> O posterior transparente do contextual bandit (R4.*): join `fold_grounding` (tentativas, faceta 1)
> × `fold_source_yield` (recompensas, ADR-0009), rendido como TABELA — conselho no briefing/gather,
> painel `/sources`, **nunca roteador** (cicatriz da ROUTING table; 3º degrau do #248 PROIBIDO por
> design). Vocabulário: o fold é o *deep module*; a tabela rendida é a única interface; a costura
> (join key) é materializada no seam que já a computa, nunca reconstruída em dois lugares.

## 1. O join key — dois saltos, ambos mecânicos

O manifest e o source.signal não se conhecem hoje: a row do manifest carrega `dispatch_id`
(tier mapped, via meta.json→toolUseId — faceta 1); o `source.signal` carrega `slug` + `ref` (o
objeto citado: URL/commit) + `similarity` (eventlog.py:428). O que os conecta são dois saltos:

**Salto 1 — slug → dispatch.** O ADR-0016 já é a ligação: um publish consome o `dispatch.open`
mais novo (`wake_fresh`, eventlog.py:419). Hoje o pareamento é só um invariante de seq; a decisão
é **materializá-lo**: `publish_artefato_atomic` grava `dispatch_seq [SUPERSEDIDO por E1/E1b: dispatch_id proof-bound]` no payload do
`artefato.published` — no `_wake_gate`, o único lugar que JÁ computa `last_open` sob o lock (uma
linha, zero disciplina nova). O fold tolera a ausência (eventos legados): fallback = reconstrução
por intervalo de seq (o `dispatch.open` máximo < seq do publish). Um stamp aberto que nenhum
publish consumiu (beat abortado) vira estrato `unconsumed` — visível no painel, fora do
aprendizado (crash ≠ fonte ruim, mesmo racional do R4.2).

**Salto 2 — ref → tentativa.** Dentro do dispatch, o `ref` citado casa com os hits da row
(`retrieval.documents`, R2.1), após normalização de URL declarada (esquema, barra final, params
de tracking; **nunca fuzzy** — miss normalizado conta como orphan, não se inventa match).
Escada de join, com tier gravado no resultado do fold (espelha a escada de atribuição da faceta 1):

| tier | regra | alimenta score? |
|---|---|---|
| `exact` | ref ∈ hits de exatamente UMA row do dispatch | sim — célula cheia (intent×source×lens×geometry) |
| `coarse` | ref não está em hits (recognizer coarse/opaque-script), mas o host mapeia à fonte pelo MESMO seam `agent.yaml sources[].via` da faceta 1 | sim — só na marginal da fonte |
| `ambiguous` | ref ∈ hits de 2+ rows do mesmo dispatch | marginal da fonte (crédito por célula seria fabricado) |
| `orphan` | não casa com nada (inclui cites de recall — self não é Source, R1.1) | não — contado e visível |

## 2. O fold — `fold_grounding_yield` / `grounding_yield_at`

Puro, tolerante, no idioma da casa (payload não-dict → skip, degrade never crash — mesmo padrão
de `fold_direction`). Consome `[grounding.manifest, dispatch.open, artefato.published,
source.signal]`; cursor `grounding_yield_at(seq=None, ts=None, log=LOG)` reconstrói o posterior
de qualquer passado (strategic versioning, como `direction_at`).

Retorna `{"cells": {...}, "marginals": {...}, "excluded": {...}, "orphans": n, "unconsumed": n}`.
Célula = (intent, source, interface, lens, geometry) → `{attempts, hits, dry, cited, rewards[],
mean_sim, score}`.

**Exclusões do aprendizado (R4.2 + extensão da faceta 1) — excluído ≠ invisível:** rows com seca
`suspeita:instrumento`/`suspeita:overspecified` E rows com atribuição `inferred`/`unknown` saem do
denominador (viés de instrumento fossilizaria o braço — o caso X teria yield 0 perpétuo) mas
entram em `excluded` com contagem por motivo, rendida no painel. A magnitude do viés do estimador
fica inspecionável mesmo sem correção de propensity (resíduo R4.4, aberto — ver §7).

**Recompensa graduada (PURPLE: relevância ≠ utilidade):** por tentativa,
`r = max(similarity dos signals casados a ela)` — a tentativa vale o melhor que contribuiu.
Três degraus, nunca achatados num binário:
- **citada com score** → r = similarity (utilidade revelada × relevância medida — o sinal forte);
- **citada sem score** → `similarity == 0.0` do publisher sem embedder (publisher.py:209 emite 0.0
  quando `embed_fn is None`) é artefato de instrumento, não medida: conta em `cited`, **excluída**
  de `mean_sim`/score (senão o no-embedder envenena a média por baixo);
- **hit sem citação** → r = 0 no score, mas a coluna `hits` fica na tabela como diagnóstico —
  relevância recuperada-não-usada é informação de instrumento, não de utilidade; fundi-la no score
  seria exatamente o erro que o PURPLE nomeia.

**Dimensões e esparsidade:** intent mecânico = o `skill` do artefato (já no payload — zero
disciplina), sobrescrito pelo intent `declared` do dispatch.open quando presente (enxerto A2).
`geometry: ambient` (wake/delta) não tem canal de recompensa (não publica) — suas células rendem
só saúde (hits/secas), nunca score; é dimensão de estratificação, não de política. Backoff
declarado contra esparsidade: célula < min_attempts → marginal da fonte → piso do roster.

## 3. Política como DADO — constantes com racional, não mágica

```python
YIELD_POLICY = {
    "min_attempts": 5,     # abaixo: célula rende "EXPLORE (n<5)", nunca score. O bônus de
                           # exploração é um RÓTULO declarado, não um termo UCB escondido —
                           # transparência > regret ótimo (trade-off assumido). Com heartbeat 3h,
                           # célula quente cruza em ~1 dia; fria fica EXPLORE — que é o conselho.
    "shrink_pseudo_n": 3,  # empirical-Bayes: score = (n·mean_sim + k·global_mean)/(n+k) —
                           # célula jovem regride à média global, nunca crava 0.9 com n=2.
    "cite_prior": (1, 2),  # Beta(1,2) na taxa de citação: levemente pessimista — citação é rara
                           # por construção; prior uniforme inflaria braço novo.
}
```

É deliberadamente um posterior-como-tabela, não Thompson sampling: a política inteira cabe numa
tela, cada número tem contagem visível, e o consumidor é um LLM lendo conselho — não um argmax.

## 4. Superfícies de render (as duas, e só as duas)

**Briefing — bloco no source-orientation** (`_section_sources`, briefing.py:218): abaixo do
roster/curated/yield atuais, ≤6 linhas, tom de conselho:
`- research → exa/deep: util 0.62 (n=9, citada 5×)` · `- discovery → x: EXPLORE (n=2<5)`.
Piso never-blank (ADR-0011, mesmo idioma do roster): sem manifest ainda, o bloco rende as linhas
seed (§5) — a seção nunca abre vazia nem fabrica contagem.

**Painel `/sources`** (R8.2, irmão do `/llm` — blog/server.py:2333, adapter fino sobre
`grounding_yield_at` como `/llm` é sobre `llm_routes`): uma row por source×interface com colunas
`tentativas · hits · citadas · mean sim · score · secas(por tier) · excluídas(por motivo) ·
canário · unconsumed`; fonte-declarada-sem-manifest = perna morta visível; orphans/ambiguous no
rodapé. O painel é o degrau **observe**; o briefing é o **advisory**.

## 5. Seed (R4.5) — prior é prosa marcada, nunca contagem falsa

Os datapoints do dogfood do Loop R (exa-deep: entidades nomeadas 5/5 no topo; conceitos compostos
~2-3/5; /contents falha em PMC por reCAPTCHA) entram como **linhas seed com proveniência**
(`seed:loopR-2026-07-01`), moradia canônica no Source roadmap (R8.1), rendidas pelo bloco do
briefing enquanto a célula real está abaixo de `min_attempts` — e substituídas célula a célula
quando a medida chega. Nunca viram pseudo-eventos nem entram no fold: semear contagem seria
fabricar log (ADR-0006, o log é verdade).

## 6. A interface proibida — por construção, não por aviso

O módulo exporta fold + render e **nada mais**: não existe `choose_source()`/argmax, e adicionar
um é violação de design nomeada (a ROUTING table morreu disso — arqueologia #248, fase
enforcement→monstro). O consumidor é sempre um agente lendo texto; a tabela aconselha, o agente
decide, o manifest registra o que ele fez de fato — e o desvio do conselho é ele mesmo dado
(é o que um bandit chama de exploração natural, de graça).

Rollout pela escada: painel primeiro (observe, sem consumidor), bloco no briefing depois de ~2
semanas de células povoadas (advisory). O 3º degrau não existe.

## 7. Trade-offs assumidos + questões abertas

- **Excluir seca-suspeita enviesa o estimador** (seleção condicionada a estado do instrumento,
  correlacionado com fonte). Sem correção off-policy/propensity nesta iteração (resíduo R4.4);
  mitigação = `excluded` contado e rendido, o viés fica inspecionável. Varrer Buckley & Voorhees
  2004 / Zobel 1998 antes de sofisticar.
- **Citada×similarity ainda não é utilidade ground-truth**: é o melhor proxy barato (uso revelado
  × relevância medida), mas um snippet citado pode ser ornamental. O PURPLE pede graduação — temos;
  validação contra julgamento humano fica para quando a calibragem (R7.2) apresentar anomalias.
- **Intent = skill é proxy grosso**: um `/roberto-research` sobre tema X e outro sobre Y caem na
  mesma célula. Refinar só se as células divergirem na prática (não especular vocabulário agora).
- **Crédito `ambiguous` na marginal perde granularidade** de propósito: crédito fracionário por
  célula seria contagem inventada numa tabela cujo valor é ser literal.
- **Constantes (5, 3, Beta(1,2)) são chute declarado**, não fit: recalibrar quando houver ~um mês
  de células — a calibragem escreve por cima (mesmo canal do Source roadmap, R8.1).
- **Aberta:** o `dispatch_seq` no payload do published muda um evento Tier-0 — confirmar no gate
  que o fold legado (corpus/wake_fresh) ignora campo extra (deve: payloads são tolerantes).
