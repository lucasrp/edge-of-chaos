# Edge of Chaos

Framework para agentes autônomos (sobre Claude Code) que une duas coisas: a
**persistência de estado** ao longo do tempo e uma **exploração livre cujo
resultado é destilado num artefato bem definido**. A qualidade vem do formato do
*artefato*, não de restringir a exploração — a exploração é livre. O nome é a
tese: exploração livre (caos) destilada em estrutura (ordem); o agente opera na
borda entre as duas.

Quanto ao *como*: opera como um agente de **baixo efeito colateral**. Em vez de
atuar no mundo e gerar side effects, ele lê, capta, absorve e entende contexto
e, ao final, entrega um artefato para o operador **ler**. O produto é
conhecimento para leitura, não uma ação executada.

> **ed** — diminutivo de *Edge of Chaos*; o nome e a identidade **compartilhados por
> toda instância** (genótipo). Não é um codinome de uma instância específica.

## Language

> Esta linguagem registra a **intenção** — o que cada conceito *deve* significar, o
> norte. O runtime foi remendado sob pressão (ver ADR-0001) e em pontos derivou
> dessa intenção; onde isso acontece, marcamos como *drift conhecido* — não
> reescrevemos a definição para imitar o código. O glossário é o norte, não o espelho.

### Núcleo

**Dispatch**:
Uma execução preparada do agente — o mecanismo do pilar "exploração → artefato".
Nasce de um gatilho (um beat de heartbeat, ou o operador invocando uma skill),
capta os signals do momento, recebe a orientação de preflight, e entrega a uma
skill o prompt para produzir ou avançar um artefato. É o envelope do runtime; a
skill é o julgamento semântico dentro dele.
_Avoid_: request, job, task, run

**Preflight**:
O protocolo de orientação injetado **antes** de a skill agir — o "como pensar"
daquele dispatch: papel, o que conta como evidência (runtime > prosa otimista),
semântica das superfícies (intenção × runtime observado). Genótipo no formato,
fenótipo no conteúdo (as `context_notes` da instância). Não é gate — *orienta*, não
barra nem avalia mérito.
_Avoid_: gate (preflight orienta, não verifica); setup, init.

**Heartbeat**:
O gatilho autônomo e periódico (a cada 3h). Não faz trabalho ele mesmo — é
*router-only*: pega o beat, escolhe a skill apropriada e a invoca. O artefato sai
da skill, nunca do heartbeat.
_Avoid_: cron, loop, scheduler (o heartbeat roteia para uma skill; não executa
trabalho)

**Artifact**:
O produto que um dispatch existe para gerar e que o operador vai **ler** — hoje,
sempre um documento HTML (um report ou post de blog). Quem produz é **sempre a
skill**; o gatilho (heartbeat ou operador) só muda quem disparou, não quem gera.
A garantia de qualidade vem de o artefato ter um **formato bem definido** (somado
aos quality gates); é o artefato que é estruturado, não a exploração, que
permanece livre.
_Avoid_: output, resultado, entrega, side effect

**Continuity**:
A persistência de estado entre dispatches — o pilar "persistência de estado". O
que um dispatch deixa registrado (delta, briefing) e que o próximo lê para não
recomeçar do zero.
_Avoid_: histórico, log; memória (a memória é um mecanismo da continuity, não um
sinônimo)

### Sinais

**Signal**:
Um pedaço de contexto que o agente capta no instante em que um dispatch é
liberado, para se situar no "agora", e que é injetado na exploração. Um dispatch
lê vários signals.
_Avoid_: input, dado; evento (um evento de estado é gravado para a continuity; um
signal é captado para contextualizar)

**Operator pressure**:
O signal que resume o que está rolando no chat do Claude com o operador — um dos
signals mais fortes. É fonte de contexto injetada no dispatch, não um pilar e nem
o gatilho.
_Avoid_: comando, ordem, request

**Affordance**:
Uma propriedade graduável de uma fonte/canal — *para que ela serve* num dado
contexto (ex.: novelty, confirmation, continuity) — que o agente nota (score 1–5)
ao usá-la, para o sistema aprender quais fontes valem a pena. Descreve o **valor de
uma fonte**, não algo que se invoca.
_Avoid_: orçamento/budget (o trocadilho afford→budget engana — para um conceito de
orçamento use outro nome, nunca "affordance"); capability (capability é o que se
invoca; affordance é qualidade de fonte).

### Exploração (o "caos")

**Exploration pack**:
A **padronização** determinística e *read-only* da exploração: o loop fixo que o
runtime roda antes de a skill agir — memory retrieval → fan-out de sources/signals
→ Feynman adversarial → segundo round direcionado — entregue como base de evidência
com um veredito de prontidão (`decision_readiness`: ok/degraded). Padronizar compra
consistência e resiliência (fonte quebrada vira warning, não para o ciclo), mas ao
prescrever os passos tende a *ancorar* o agente neles: mesmo livre para ir além, ele
costuma parar no padrão — o trade-off ganha-perde detalhado no ADR-0001.
_Avoid_: exploração livre (o pack é a parte padronizada, não a livre); piso (sugere
que a exploração livre se acumula por cima, mas na prática o padrão tende a virar
teto); pesquisa, busca, contexto.

### Capacidades

**Capability**:
Uma superfície de invocação que **orquestra uma-ou-mais primitivas** (ou ferramentas
externas) atrás de um handle único, invocável de forma uniforme (`edge-cap invoke
<nome>`) e sondável por saúde. Critério de identidade: *se não orquestra, não é
capability* — uma primitiva re-etiquetada 1:1 não vira capability (isso é drift; ver
ADR-0002). Exemplar legítimo: `sources.aggregate`, que faz fan-out por vários
provedores de fonte.
_Avoid_: wrapper (um wrapper 1:1 é justamente o que NÃO é capability); tool, comando.

**Primitive**:
A operação ou fonte **atômica** que o agente chama — a peça indivisível que uma
capability orquestra. É a camada original do sistema; a capability veio depois, por
cima dela (ver ADR-0002).
_Avoid_: capability (esta orquestra primitivas — não são sinônimos); helper, função.

### Qualidade (a "ordem" do artefato)

A qualidade do artefato não mora num lugar só — é fragmentada em formato + três
fontes de julgamento. Saber qual é qual é o que tira o medo de mexer.

**Skill**:
A receita por *tipo de artefato* (`/ed-report`, `/ed-research`…). Contribui sua
fatia *local* de formato (as seções próprias) e de julgamento (o "como pensar"
daquele tipo) e roda a exploração livre — mas não é dona única nem do formato nem
do julgamento; ambos têm camadas compartilhadas (Artifact Rite, Personality,
Review gate).
_Avoid_: comando, função, plugin

**Artifact Rite** (Uniform Artifact Rite):
O piso de formato compartilhado por toda skill `/ed-*`, sem exceção
(`skills/_shared/report-template.md`), somado ao "ARTIFACT SKILL CONTRACT" que o
runtime injeta em cada dispatch. Define o mínimo obrigatório de todo artefato:
blog entry + YAML spec + HTML report + review adversarial, com Lineage, Gaps,
Glossary, Bibliography e ≥1 SVG. As seções próprias de cada skill são a camada
local sobre esse piso.
_Avoid_: template (o template é só o arquivo; o Rite é protocolo + contrato)

**Personality**:
O **núcleo da identidade** do agente e genótipo puro — *o que ele tem de mais
importante*. É a orientação de julgamento que atravessa todas as skills (o "como"
pensar, não o "o quê"), e por isso também entra aqui como uma das fontes da "ordem"
do artefato — mas seu peso é maior que isso: define quem o agente é. Dupla:
`memory/personality.md` (quem o agente é) + `memory/metodo.md` (o método Feynman:
derivar do zero antes de pesquisar, mostrar o *processo* do pensamento, deixar as
lacunas emergirem inline).
_Avoid_: tom, estilo, voz (a personality guia julgamento e identidade, não só voz)

**Adversarial**:
A postura de **contestar para forçar humildade** — baixar a confiança do agente,
expor o que ele não sabe, dar direção. Atravessa o sistema: na exploração (o Feynman
adversarial do Exploration pack, que proíbe soar certo sobre evidência fraca) e como
mecanismo de gate que enforça o pipeline. O Review gate é a instância dela aplicada
ao artefato pronto.
_Avoid_: crítica, validação (adversarial força humildade/calibração, não só aponta
erro de superfície).

**Review gate**:
O avaliador adversarial *separado* que julga o artefato pronto contra uma rubrica
(`tools/review-gate.py`): co-autor sugere melhorias → reviewer avalia → refine,
em 2 rounds. A skill produz; o Review gate contesta. É um **gate de mérito** —
controle de qualidade do *resultado*, distinto do julgamento interno da skill.
_Avoid_: linter, validador (avalia mérito, não conformidade sintática). Cuidado com
"gate", palavra sobrecarregada: aqui é **mérito**; não confundir com *gating de
sinal* (um signal crítico que barra a decisão — severidade, não mérito), com o
*artifact gate* (exigência estrutural de publicar um artefato de verdade), nem com o
**Preflight** (que orienta, não barra).

### Camadas do repositório (genótipo / fenótipo / epigenética)

O repo é open source e roda em várias instâncias. Confundir estas três camadas
quebra o sistema para todas. Teste decisivo: *"se eu mudar isto, afeta outras
instâncias?"*

**Genótipo (Genotype)**:
A fonte **compartilhada por todas** as instâncias edge — skills, tools, runtime,
blog/search, e o piso de memória (`personality`, `rules-core`, `metodo`). Mudar
genótipo afeta toda instância, então passa pelo loop issue → clone → PR → merge →
close → propagate. *"Afeta outras instâncias? Sim → genótipo."*
_Avoid_: core, base, shared (use genótipo).

**Fenótipo (Phenotype)**:
A customização **desta** instância — identidade (nome, missão, domínio), branding,
estratégia, interests, configs de preflight/postflight. Muda livremente; não propaga.
_Avoid_: config (genérico demais), perfil.

**Epigenética (Epigenetics)**:
O **estado de runtime que a instância produz** — blog entries, reports, logs,
threads, state. Gerado à vontade; não é fonte.
_Avoid_: não confundir com Artifact — o artefato é *um tipo* de epigenética (o
produto-para-ler); epigenética inclui também logs, threads e state.
