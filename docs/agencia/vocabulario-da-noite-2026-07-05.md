# Vocabulário da noite (2026-07-05) — o que merece verbete e o que ainda não tem nome

> Consolidação pedida pelo operador. Camada 1 = conceitos que a noite estabilizou e merecem
> entrar no glossário interno (CONTEXT.md — fold conceitual é do agente A; verbetes prontos
> abaixo). Camada 2 = o mais importante: conceitos que CARREGARAM a noite sem ter palavra —
> nomeá-los é o 4º quadrante aplicado ao próprio vocabulário.
> Lastro: experimentos-wake-quente.md · proposta-novo-wake.md · experimento-clusters-graphiti.md ·
> commits 4ff9cab/082ce5c/2d59e4d + build communities (working tree).

## Camada 1 — merecem virar palavra (verbetes prontos)

- **Quente / Frio** — as duas metades da orientação de wake. *Quente*: leitura direta das
  últimas K sessões substanciais, dois trilhos, gerado NO wake (nunca cache — envelhece em
  horas). *Frio*: o durável — o assertado (folds do log) + o índice de communities. Fronteira:
  **tempo-divide-donos** (cluster tocado dentro da janela do quente não expande no frio).
- **Dois trilhos** — os insumos ortogonais do olhar: *voz* (prompts verbatim do operador) e
  *executado* (âncoras mecânicas). Prosa de assistente NUNCA é fonte de fato. (Já doutrina no
  design-organismo; falta o verbete.)
- **Âncora mecânica** — fato executado verificável por instrumento: git log, eventlog, /proc.
  O que separa "aconteceu" de "alguém disse que aconteceu".
- **Ordinal-K** — janela de recência contada em SESSÕES substanciais, não em relógio;
  wall-clock só como teto; K é valor fenótipo (ed≈semana, roberto≈1-2 dias).
- **Knowledge cluster (REDEFINIÇÃO — o verbete existe, o significado mudou):** era "o grafo
  propõe, o grill cura por harm potential" (e por isso ficou vazio um mês). Vira: "o grafo
  propõe, a MÁQUINA consolida (label-prop + sumário LLM, tier-hipótese, recência por
  last_touched), o humano cura SÓ o harm-bearing (Earmarked)".
- **Âncora humana** — o julgamento extrínseco do operador como perna obrigatória de validade
  de construto de todo aceite (a parede-de-construto do v10, generalizada).

## Camada 2 — tocamos e NÃO tem palavra (os sem-nome, com nomes propostos)

1. **Trilho órfão** (patologia) / **Lei do leitor** (a lei) — escritor sem leitor num caminho
   obrigatório apodrece. Matou chat-digest, handoff-latest, feedback-digest (duas gerações!) e
   curated_cluster — QUATRO mortes da mesma doença, nenhuma tinha nome. A lei: nenhum escritor
   nasce sem leitor no caminho obrigatório.
2. **Vazão × Confiança** — o eixo que curou o pipeline: *automatize a vazão, gateie a
   confiança*. Gate de vazão com humano = sistema que não aprende; gate de confiança sem
   humano = falha-Zep. A decisão de design mais transferível da noite — e não existia em
   palavra nenhuma.
3. **Desorientação confiante** — o modo-de-falha do wake frio, MEDIDO no E5: não é ignorância,
   é o primeiro movimento apontado pro mês passado com plena convicção (sims frios → pauta de
   junho). Merece nome porque é o que a régua do wake mede — e porque é pior que não saber.
4. **Defasagem do extraído** — o extraído está estruturalmente ATRÁS do vivido (ingest
   best-effort, consolidação offline) — por design, não por bug. É a razão de existir do
   quente; sem o nome, cada gap parece defeito.
5. **As três velocidades** — a economia da memória: quente-grátis · consolidado-centavos ·
   curado-caro. Decide onde cada informação MORA; resolve metade do mapa de redundância sozinha.
6. **Esfriamento indevido** — tema com last_touched velho mas importância declarada alta
   (Objective/Direction). O gatilho computável de um ato de agência novo: "vim te buscar
   porque isto esfriou e não devia". (O DSPy-moment derivável de query.)
7. **Posição no mapa** (dentro / borda / fora) — a geografia de um take via `locate()`.
   "Borda" liga direto na banda-da-fronteira-adjacente (H3): o Worthwhile mora na borda;
   dentro = repetição; fora = ruído ou dimensão nova (o teste do Objective ganhou geometria).
8. **Hierarquia de verdade** — docs commitados > topic-files de memória > grafo. A regra
   anti-clobber que faltou hoje de manhã (sync sobrescreveu memória sem merge, 2×).

## Camada 2b — pós-abate do operador (2026-07-05: 3 de 4 mortas)

9. ~~Minuto-zero~~ **MORTA** — "produto do wake" já cobre; produtor-vs-consumidor não paga palavra.
10. ~~Teste do primeiro movimento~~ **ABSORVIDA** — é o teste canônico DE **temperatura** (conceito
    do A). Procedimento preservado sob temperatura: agente fresco só com a injeção → "qual teu
    próximo movimento?" → apontar pro passado = falha (recall mede o que se sabe; o primeiro
    movimento mede pra onde se vai).
11. ~~Fiação antes de adoção~~ **RECATEGORIZADA** — boa prática de desenvolvimento, não conceito
    do edge; foi pra memória de método do agente, fora do glossário.
12. ~~Inscrição~~ **MORTA (operador: "não é thread essa palavra?")** — dissolve em vocabulário
    existente: CHEGAR cujo entregável é um THREAD aberto no sistema do mentee (no episteme:
    uma Hipótese com falsificador — H-007). O que sobrevive é REGRA DE DESIGN pro CHEGAR do
    organismo, não verbete: *o CHEGAR de maior valor termina abrindo um thread no sistema do
    mentee, não uma nota na atenção dele* — o thread trabalha quando a conversa morre.
    → pro A foldar no design-organismo (CHEGAR).

**Placar do abate do operador na camada 2b: 4/4 mortas** — por quatro razões distintas
(redundância · absorção · categoria errada · dissolução em composição). O filtro discrimina.

## Nota de fold
Camada 1 + redefinição do Knowledge cluster → CONTEXT.md (fold conceitual: agente A).
Camada 2: os nomes são PROPOSTAS — o operador bate o martelo; os que pegarem entram no
glossário com os verbetes acima como rascunho.
