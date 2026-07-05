# Fluxo — 3 atos, estrutura livre, grounding em MÚLTIPLOS ROUNDS (ticket three-act-split)

Operador 2026-07-05: a divisão do fluxo é **grounding inicial COM PROPOSTA** + **vários rounds de grounding por artefato**. Mata o monolito (1 grounding → close único).

## O tronco (ato-1: escolher)
1. **Grounding INICIAL** — o olhar quente (wake/quente + delta + recall) + sweep leve no mundo.
2. **PROPOSTA** — o output do ato-1 é uma proposta explícita: QUAIS artefatos (1..N), por quê (VoI/é-real/é-pra-ele — gates de plano, B.4), cada um com seu ângulo. O editorial-compass é o protótipo vivo deste gate.

## Os galhos (estrutura LIVRE, #67)
- **Um agente por artefato**, paralelos, cada um perseguindo o SEU (report + map + JS-interativo da mesma pauta, por exemplo).
- **Cada artefato-agent faz os PRÓPRIOS rounds de grounding** — o grounding não é fase única do tronco: o agente volta ao mundo quantas vezes o SEU artefato pedir (rounds localizados, manifests por dispatch_id).
- Cada um com os próprios gates (fim: substância+passabilidade AND, B.4) e loop LOCALIZADO — termina POR FORA (critério do ticket), nunca "até o juiz gostar".
- JS-artefato = outro artefato (04-C), concomitante ao HTML — não uma fase dele.

## Por que assim (o tune)
Feedback de vários eixos disjuntos ao mesmo tempo = tune ruim (operador). Loop localizado por artefato = cada agente recebe feedback de UM eixo. E o fan-out-gather + single-writer por artefato é o SOTA validado ([[sota-for-the-artefato-problem]] — o multi-writer do conductor é o anti-pattern).

## A fase de CONSOLIDAÇÃO do grafo (operador: possivelmente a função MAIS IMPORTANTE do artefato)
Todo artefato ganha uma fase de consolidação: **ir na internet, procurar um SIGNIFICADO, e FAZER esse significado no grafo** — materializar o que aprendeu como nós/arestas/tipos (a curadoria inline do 02-D elevada a FASE de 1ª classe). O artefato não é só a página: é o órgão que transforma significado-do-mundo em estrutura-do-grafo. O texto é a projeção; o significado consolidado no grafo é o que ACUMULA (é ele que o recall, as communities, as pontes e o episteme navegam depois). provenance: asserted-by-agent, ancorado nos cites do próprio artefato.
**E é AÍ que entra a serendipidade:** qualquer produtor, ao consolidar, materializa os achados fora-do-fio como nós/arestas de longo alcance — os atalhos small-world que o on-topic jamais criaria. Gênese, não enfeite.
**DISCOVERY continua discovery (operador):** serendipidade dirigida; PODE ser do mesmo ramo (DSPy — in-field, o report canônico); ZERO obrigatoriedade de outro campo.
**LAZER = skill NOVA a ADICIONAR (operador):** distinta da discovery — a skill de puro lazer que foi tirada e volta. Exemplar da forma: o blog edge-of-chaos.netlify.app.

## Hierarquia de ORIGEM (operador): pedido-pelo-usuário ≫ beat
Um artefato **pedido pelo usuário é exatamente onde está a cognição dele AGORA** — é uma FONTE DE SINAL de primeira ordem (alimenta o quente, a persona, a escolha do ato-1, o peso no grafo). Um artefato **de beat não dá pra diferenciar de ruído** (o edge escolheu sozinho; pode ter acertado, pode não). Consequência no schema: o artefato carrega a origem (`origin: user_requested | beat`, do dispatch), e tudo que aprende com artefatos (curadoria de sources, pontes, atenção do quente, o próprio ato-1) **pesa user_requested acima de beat** — o pedido do usuário é o gradiente; o beat é exploração.
**O tema do LAZER (operador):** determinado pelo usuário no **agent.yaml** (fenótipo — seeds, sorteio) ou, **na omissão, pura criatividade do agente**. O yaml dá o gosto do dono; a omissão libera o faro.
**Links LIBERADOS + "saiba mais" (operador, abrandando a regra):** artefatos PODEM ter links — no corpo e numa seção opcional de further-reading pra quem quer ir além. A regra do self-contained abranda: auto-contido na LEITURA (entende sem abrir nada), não na referência. **E JavaScript LIBERADO em qualquer artefato** (operador) — não só no genus prototype: o publisher para de sanitizar <script> autoral (o 04-C vira a regra geral, não a exceção; morre a regressão pós-abril). O gate continua: interação que ENSINA, nunca forçada. **E IMAGEM liberada também (operador)** — embutida (base64/data-URI ou SVG inline). **A ÚNICA regra dura que fica: SINGLE FILE** — um arquivo que carrega tudo (JS, CSS, imagem, dado); links apontam pra fora, mas o artefato ABRE inteiro sozinho. Qualidade herdada do exemplar leveling: link VERIFICADO (o que não abre fica fora), escolhido (gap × trabalho vivo × perfil, nunca catálogo), com o porquê em meia linha. Alimenta o Q2 (currículo) e o gosto-de-papel.

## PAR OBRIGATÓRIO (operador, 2026-07-05, tarde no ticket — verificar na integração): TODA skill de produção gera OS DOIS
**Todo produtor emite um PAR: o artefato HTML (prose/rico) + um artefato JAVASCRIPT interativo, ANEXADO no HTML** (linkado/embutido a partir da página; o JS continua single-file próprio, genus prototype, com seus gates "ensina?"/roda). Não é opcional-por-genus: é o formato de saída padrão da produção. O par nasce da mesma pauta (agentes concomitantes, cada um com seus rounds/gates); o HTML aponta pro JS ("veja/brinque"). NOTA DE INTEGRAÇÃO: o ticket 05 foi despachado ANTES desta regra — o lead verifica no merge se o par ficou obrigatório; se não, é o primeiro follow-up.
**Editorial-compass (verificar na integração):** o gate do ato-1 (a PROPOSTA) implementa o conceito do **editorial-compass** do relicário — o protótipo vivo da seletividade: "isto vale ser feito? é pra ESTE leitor? qual ângulo?" antes de qualquer produção. Não é port do artefato JS em si; é a lógica dele virando o gate de plano (VoI/é-real/é-pra-ele, impessoal). O compass-artefato original (netlify) vira source quando integrado (B.3) — o edge lendo a própria bússola.
**Gate visual-rico do HTML (verificar na integração):** o ato-3 (visual) precisa do gate de riqueza — hoje a linha tem o rich-rite floor + paleta de blocks + banca-cega ("block substitui parágrafo, nunca decora"), mas o gate ENDURECIDO do conductor (type→format, visual post-pass) ficou na linha parkada feat/conductor*. Salvar o GATE (não o multi-writer, rejeitado) é follow-up se o 05 não cobrir: o visual julga-se como o resto — presença de forma onde a informação PEDE forma, veto onde números viram prosa.
