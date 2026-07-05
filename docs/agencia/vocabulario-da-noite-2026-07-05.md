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

## Camada 2b — os sem-nome da esticada final (pós-faca)

9. **Minuto-zero** — o conteúdo que o agente efetivamente segura quando começa a agir; a moeda
   do wake ("benefício por contexto gasto no start"). Todo o wake-ótimo é engenharia do
   minuto-zero; medimos 0/12 nele sem ter o substantivo.
10. **Teste do primeiro movimento** — o instrumento: acordar um agente SÓ com a injeção e
    perguntar "qual teu próximo movimento?". Aponta pro passado = a memória falhou, não importa
    o recall. Vira o aceite-padrão de trabalho de memória/contexto (recall mede o que se sabe;
    o primeiro movimento mede pra onde se vai).
11. **Fiação antes de adoção** — o padrão 4× da noite (build_communities dormante ·
    classify_session sem caller · edge-feedback-digest nunca ligado · §5 olhando o rail errado):
    antes de adotar tech nova, pergunte o que já existe DESLIGADO no substrato.
12. **Inscrição** — o degrau acima do CHEGAR: o juízo vira claim FALSIFICÁVEL dentro do sistema
    do mentee (H-007 no episteme, com falsifier + evidência datada). CHEGAR entrega uma nota;
    inscrição deixa lastro testável no mundo do mentee. Candidato a ato supremo da agência.

## Nota de fold
Camada 1 + redefinição do Knowledge cluster → CONTEXT.md (fold conceitual: agente A).
Camada 2: os nomes são PROPOSTAS — o operador bate o martelo; os que pegarem entram no
glossário com os verbetes acima como rascunho.
