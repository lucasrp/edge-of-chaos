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
**E é AÍ que entra a serendipidade (operador):** a perna diverge/discovery (o budget de curiosidade reservado) consolida significado de OUTRO campo de estudo no grafo — **formando neurônios "aleatórios"**: nós/arestas de longo alcance que o trabalho on-topic jamais criaria. São os atalhos small-world do grafo — a discovery deixa de ser só um texto curioso e vira ESTRUTURA que aproxima campos distantes (o insight de outro domínio fica navegável a 1 hop do problema vivo). A serendipidade ganha função de gênese, não de enfeite.

## Hierarquia de ORIGEM (operador): pedido-pelo-usuário ≫ beat
Um artefato **pedido pelo usuário é exatamente onde está a cognição dele AGORA** — é uma FONTE DE SINAL de primeira ordem (alimenta o quente, a persona, a escolha do ato-1, o peso no grafo). Um artefato **de beat não dá pra diferenciar de ruído** (o edge escolheu sozinho; pode ter acertado, pode não). Consequência no schema: o artefato carrega a origem (`origin: user_requested | beat`, do dispatch), e tudo que aprende com artefatos (curadoria de sources, pontes, atenção do quente, o próprio ato-1) **pesa user_requested acima de beat** — o pedido do usuário é o gradiente; o beat é exploração.
