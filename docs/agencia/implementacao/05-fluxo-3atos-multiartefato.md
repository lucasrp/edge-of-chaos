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
**"Saiba mais" (operador):** os artefatos ganham uma seção opcional de further-reading — uns links pra quem quer ir além. Regras do exemplar leveling: **links VERIFICADOS um a um** (o que não abre fica fora, dito), poucos e escolhidos (gap × trabalho vivo × perfil, nunca catálogo), com o porquê de cada um em meia linha. Alimenta o Q2 (sei-que-não-sei → currículo) e o gosto-de-papel (imprimível).
