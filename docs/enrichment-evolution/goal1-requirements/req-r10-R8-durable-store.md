# Requisitos — Adoção total do enriquecimento de Artefato

**Goal 1 de 3** (requisitos → plano → slices). Gate: `/codex:adversarial-review`.
Critério de parada: quando a revisão só levantar defeitos cosméticos/novos-e-mais-estreitos
(o *recursive-trap escape*, `feedback_adversarial_review_recursive_trap.md`).

## Propósito

O edge construiu a maquinaria de enriquecimento, mas a evidência de campo (feedback do operador,
2026-06-17) inverteu o problema: **o formato rico ficou bonito e perdeu o storytelling.** Comparado ao
**formato livro** (`roteiro-paper-v8-retrieval-publicavel.html` @ commit `eeb696e`/tag
`pre-deploy-d3e150f`, produtor single-writer pré-conductor: ~29,6k palavras, parágrafos de até 1.552
palavras, fio narrativo profundo, 0 visuais), o formato rico do conductor (`novoformato`, que
`builds_on` o livro) **regrediu MUITO em explicação e qualidade de escrita**. Logo o requisito não é
"adotar visuais" — é **enriquecer SEM perder o storytelling do livro**, e parar de queimar review em
loop. Isto reordena tudo abaixo.

## Alinhamento com o objetivo (objetivos atualizados, 2026-06-17)

Objetivo do edge: Artefatos que abrem uma dimensão que o operador não via (worthwhile-test), com um
**piso**. A evidência redefiniu o piso em três camadas, nesta ordem de prioridade:

1. **Storytelling (dominante) — R0/R0a.** O fio narrativo e a densidade do livro são o piso
   inegociável. Visual é ADITIVO, nunca substitutivo. Um output rico-mas-raso é regressão.
2. **Review que converge — R7+R8+R9.** Três causas do livelock do roberto (15 rodadas, "saiu na
   marra"): sem cap (R7); gate mis-calibrado p/ medição interna = alvo que recua (R8 internal-evidence);
   revisor estocástico re-levanta o resolvido (R9 discharge persiste). Ganho marginal → 0 após as
   primeiras rodadas.
3. **Adoção visual (subordinada) — R1–R6.** Só vale onde acrescenta ao livro sem canibalizar a prosa.

Régua de cada requisito: *preserva/eleva o storytelling do livro?* antes de *adota o visual?*

## Inventário — o que já foi construído (com evidência)

- **E1. Blocos visuais ricos.** `chart` (Vega-Lite: line·sparkline·bar·scatter·slopegraph) e
  `diagram` (Vega: dag·force node-link). Writer emite **spec de recipe fechado** → `vl-convert`
  renderiza p/ SVG (puro-Python, sem binário/root) → sanitizado → inlinado. *Store the spec, never
  the SVG.* — `tools/blocks.py:171-172`, `tools/render.py:482-566`. Backend instalado: `vl-convert 1.9.0`.
- **E2. Scaffold compartilhado ensina o bloco-por-forma-de-conteúdo.** property-not-section; cada
  produtor "leads with" os blocos do seu `richness.require`; `ascii-diagram` é declarado **fallback**. —
  `skills/_shared/scaffold.md:129-146`, `tools/producer_descriptor.py`.
- **E3. Rich-rite gate.** Os quatro movimentos (derivation, marked-unknown, external-frame, lineage),
  content-relative, disparado por ≥3 blocos de prosa. — `tools/close.py:123` (`check_genus`),
  `:330` (`_check_rich_rite`).
- **E4. Lineage tipada autorada** (builds_on/supersedes/contradicts) no publish, e checada no
  rich-rite. — `tools/close.py:427`, série cortex-v1.
- **E5. Saída rica do conductor** (type→format blocks, content titles, floor de densidade visual). —
  merge #40 (`35c92de`), `tools/conductor.py:1091`. **Dark by default.**
- **E6. Gate de visual-coverage RENDERABILIDADE-aware.** Flag iff há material quantitativo/multi-valor
  e nenhum visual **substantivo**; `_visual_substantive` canonicaliza e, para chart/diagram, exige que
  o bloco **de fato renderize** (`_RENDERABLE_VISUALS` → `chart_renderable`/`diagram_renderable`). Um
  chart/diagram que não renderiza NÃO satisfaz o owe. — `tools/close.py:270-293`,
  `tools/producer_descriptor.py:120-127`. *(Correção vs. rascunho v1: a renderabilidade JÁ é checada;
  o gate de close não é a lacuna.)*

## Lacunas de adoção — onde o edge NÃO usa o que construiu

*(Diagnóstico revisado após o gate adversarial v1: a capacidade e a checagem de renderabilidade
existem — a lacuna está na CAMADA DE SELEÇÃO/FLOOR do produtor e na ausência de grounding, não no
close.)*

- **G1. O floor primário do produtor é satisfeito por um tipo-fallback, mesmo com backend presente (a
  lacuna-espinha).** `map.require = min_blocks_of [diagram, ascii-diagram] n=2` — `ascii-diagram` é um
  tipo-fallback que **co-satisfaz a obrigação primária**: dois ascii já zeram o floor, então o produtor
  nunca alcança o bloco renderizado. Não é `any_of` (esse é o `plan`, `:38-40`) — é o tipo-fallback
  dentro do `min_blocks_of`. O comportamento está **travado por teste**: `tests/test_floor_evaluator.py`
  (`test_visual_producers_owe_their_form_floor`) afirma que `map` com dois `ascii-diagram` **não tem
  violação** — esse teste codifica o bug. Sintoma observado: `map` saiu ASCII com `vl-convert` presente.
  — `tools/producer_descriptor.py:33-40`, `tests/test_floor_evaluator.py`.
- **G2. Sem requisito de grounding sobre o visual renderizado — apesar do seam existir e não estar
  mandado.** Renderabilidade prova que o spec Vega converte, não que nós/arestas/números são
  atribuíveis à fonte. Forçar render sem forçar dado fundamentado torna o caminho-mais-barato-para-passar
  **inventar** um grafo pequeno renderável — regressão de corretude (o próprio `map` SKILL.md adverte
  contra "data-model dump"). O seam de grounding **já existe** — `tools/visuals.py`:
  `add_visuals(content, *, evidence) -> (content, flags)` + `attributable(block, provenance, evidence)`
  com laundering guard ("GROUNDED visuals — never fabricated") — mas **não é o caminho obrigatório**
  para chart/diagram nos produtores standalone (provável: só fiado no conductor). — `tools/visuals.py:18,249`.
- **G3. Texto local da SKILL.md contradiz o scaffold.** `skills/map/SKILL.md` lista "vocabulário
  canônico" stale (ascii-diagram, table, raw-html, gap-table, callout — **omite chart/diagram**) e seu
  exemplo emite `ascii-diagram`; o exemplo local vence a regra compartilhada. scan: `chart/diagram-aware=0`
  em todos os 13 SKILL.md. — `skills/map/SKILL.md`.
- **G4. O caminho do conductor (a adoção mais completa) está dark e em livelock.** A saída rica do #40
  não roda no beat vivo; o contract-gate faz verbatim-discharge → não-convergência (15 rodadas no
  roberto, mesmo genótipo). O seed-discharge "pousar OU cortar-com-razão-logada" só tem o caminho
  *pousar* implementado. — `tools/conductor.py`, Direction.
- **G5. Sem prova de que blocos ricos renderizam no corpus publicado.** Desconhecido quantos Artefatos
  usam `chart`/`diagram` vs ascii/prosa. Se for 0, a capacidade está 100% não-usada em produção.
  Mensuração pendente: auditar `blog/entries/` por tipo de bloco.

## Requisitos

Cada R: *requisito · porquê · critério de aceitação (falsificável)*.

> **NORTE (spec do operador):** *mesma informação da versão livro, porém visualmente rica — sem trocar
> conteúdo por visual. Não precisa ficar mais burro pra ficar mais visual.* Visual é **net-aditivo**;
> nada de conteúdo é sacrificado. Este é o teste de aceitação acima de todos.

- **R0 — Piso de storytelling: EXPLICAR, não rotular (DOMINANTE, bloqueante).** O formato enriquecido
  iguala o livro em EXPLICAÇÃO: todo termo/sigla/fase/label introduzido é **expandido em prosa** — o
  que é, o que faz, por que importa. Uma sigla de fase sem dizer "qual é qual" é regressão (exemplo do
  operador: o report atual do roberto lista as siglas das phases do harness sem explicar cada uma; o
  livro explicaria). Um bloco visual (grid/card/diagram/comparison) que **nomeia sem expandir** falha —
  ele vem ACOMPANHADO da prosa que explica seus rótulos, nunca a substitui.
  *Porquê:* o objetivo nº1 atualizado — o formato rico regrediu em explicação vs. o livro `eeb696e`.
  *Aceitação — avaliador mecânico em DUAS partes (definir acrônimo NÃO basta, gate v-reframe F1):*
  **(I) Inventário de termos COMPLETO** — não só ALL-CAPS: headings, phase-ids, **labels de bloco
  visual, headers de table/card, labels de eixo/nó de diagrama**, acrônimos, e termos de domínio
  marcados. Cada um, no primeiro uso, tem **≥1 frase de definição** (o-que/faz/por-que) em proximidade
  (mesma seção, em prosa, não em label). **(II) Continuidade GENUS-RELATIVA (ADR-0013) — calibrada, não
  imposta globalmente:** a continuidade é da **FORMA** do produtor, não um arco de prosa universal.
  **Forma narrativa (report/research):** arco de prosa, métricas com fórmula definida e **valores
  CONGELADOS do `eeb696e`** no Goal 2 — (a) **prosa-explicativa/conceito** = tokens de prosa não-rotular
  ÷ nº de conceitos do inventário (I), ≥ a razão do livro; (b) **cobertura de transição** = fronteiras de
  seção com ≥1 frase conectiva, ≥ a do livro; (c) **through-line** = tese enunciada + referenciada em ≥K
  seções. **Formas não-narrativas (map/plan/…):** continuidade é da própria forma — conexões/dependências
  coerentemente relacionadas e explicadas — **NÃO** o arco de prosa do livro (impor a métrica narrativa
  global false-falharia um map ou o incharia em prosa). (d) [genus-GERAL] **um parágrafo explicativo
  não-visual por estrutura visual/rotulada**. Um Artefato que define os acrônimos mas pontua **abaixo do
  piso da SUA forma** em (II) **FALHA**. *(`eeb696e` calibra a forma narrativa + a slice de migração; não
  é piso narrativo de todo genus — gate reframe-3 F-II.)*
  **(III) Completude de conteúdo (o NORTE) — RELATIVA À FONTE do próprio Artefato (gate reframe-3 F1;
  CONTEXT/ADR-0013 content-relative, property-not-section):** ao enriquecer, o Artefato não pode
  **perder** claim da sua **própria fonte/baseline declarada**. Essa fonte é destilada num **inventário
  de claims tipados** (claim-id, **span de origem**, entidades normalizadas, congelado por-Artefato);
  cada claim da fonte está **suportado em prosa não-visual** no enriquecido, casado por **regras
  explícitas** (paráfrase / split / merge), **sem claim retido contraditório**. **`eeb696e` NÃO é um
  superset global** que todo Artefato deva conter — é (i) o benchmark de storytelling/continuidade de
  (II) e (ii) o alvo da slice de **migração do livro-roberto**; não se cabeia um claim-set fixo do livro
  no `close.check_genus` genérico (senão um map/plan sobre outro material false-falha). Visual é camada
  adicional sobre a prosa completa, nunca no lugar dela. Testes negativos (sobre a fonte do próprio
  Artefato): (a) **menção de superfície** que cita o termo mas **não preserva o claim** → FALHA; (b)
  **claim contraditório** retido → FALHA; (c) **paráfrase válida** → PASSA. (Resolve a P3.)

- **R0a — Continuidade narrativa é invariante de RESULTADO; single-writer é HIPÓTESE (não mandato).**
  Invariante: o Artefato final passa as métricas de continuidade de R0(II) — independente de arquitetura.
  Hipótese a A/B-testar (não impor por folclore — gate v-reframe F3): a fan-out de ESCRITA per-node
  fragmenta a narrativa numa anthology de rótulos; single-writer (fan-out só na COLETA) corrige
  ("fan-out gather, one writer" / "division-without-reconciliation-is-a-thick-anthology"). A/B sobre
  material idêntico, prompts/visual/review controlados, medindo parágrafos-conectados /
  labels-não-resolvidos / cobertura-de-transição / densidade-de-explicação — ANTES de declarar a
  fan-out culpada e forçar a reescrita.
  *Porquê:* não forçar um rewrite arquitetural sobre suspeita; exige-se o RESULTADO (R0), com a causa
  validada (a perda pode vir de prompt, pressão visual-first ou churn de review, não só da fan-out).
  *Aceitação:* (a) qualquer arquitetura que passe R0(II) satisfaz R0a; (b) o A/B controlado mostra se
  single-writer move a métrica — só então o mandato vira estrutural.

- **R7 — Review que PARA quando para de GANHAR (não um teto fixo baixo).** O stop não é um N pequeno
  arbitrário — é (i) um **detector de ganho-marginal→0**: quando uma rodada não muda a substância (só
  recicla forma ou re-levanta o já-resolvido), para; e (ii) um **backstop generoso** contra livelock
  infinito. Enquanto cada rodada melhora substancialmente, **itera-se em cheio** — loops longos rendem,
  desde que cada volta ganhe. No stop, **ship-with-logged-residual** (subordinado a R5: só não-bloqueante).
  roberto fez 15 e "saiu na marra" porque o loop **não convergia** (alvo que recua, R8) — não porque
  iterou demais.
  *Porquê:* objetivo nº2 — o mal não é iterar muito, é iterar SEM ganho (gate mis-calibrado). Conserta-se
  a convergência (R8/R9) e detecta-se o platô; não se mata um loop que ainda ganha.
  *Aceitação:* um loop cujo ganho-marginal caiu a ~0 (rodada sem mudança de substância) **para** e publica
  com residual; um loop que ainda muda substância **continua**; o backstop impede loop infinito. Teste:
  loop que platô na rodada k para em k; loop divergente para no backstop.

- **R8 — Tier "internal-evidence" no gate de cite/grounding (bloqueante p/ Artefato de medição).** Dado
  de medição do projeto (números de runs/experimentos: AUC, exact_match, deltas) é admissível com
  **proveniência INTERNA DURÁVEL content-addressed** (evento **append-only no eventlog** com valores+hash,
  OU store de run content-addressed; **NÃO** blob/path de Artefato publicado — prunable, ADR-0006) em vez
  de cite externo, **apenas no gate de cite/grounding e apenas para claims numéricos internos**. **CISÃO obrigatória (gate reframe-3,
  CONTEXT):** internal-evidence **NÃO** satisfaz o move `rich-rite:external-frame` — esse continua
  exigindo um **benchmark/frame de FORA** (cite Mundo / bibliografia), porque a proveniência interna é
  explicitamente *não-externa* no modelo (CONTEXT: rich rite importa um frame de fora; o close já trata
  `atividade`/interno como não-external). Um Artefato de medição que só re-aplica o próprio dado a si
  mesmo **não** clareia external-frame. Sem o tier de cite, porém, o gate é um **alvo que recua**: o
  número ou vira texto-de-cite (absurdo) ou some (esvazia) — a causa-raiz nº1 do livelock do roberto.
  *Porquê:* objetivo nº2 — o gate de **cite** foi calibrado p/ síntese-sobre-o-mundo e torna a medição
  interna impassável; conserta-se o cite SEM quebrar o invariante de mentor (external-frame importa de
  fora). Achado sobre o RITO (vale issue no edge).
  *Aceitação (não basta auto-atestar — gate v-reframe-2 F2 + reframe-3):* o ref interno deve ser
  **dereferenciável** a uma fonte **durável content-addressed** (eventlog event / store de run), e o
  valor reportado deve **bater** com o valor na fonte (checado mecanicamente). Um número com ref que
  **não resolve**, cujo **valor diverge**, ou que aponta a **blob de Artefato publicado (prunable)**
  **falha**; **prune/edição da origem NÃO altera nem quebra a verificação** (red test); número sem
  proveniência alguma **falha**; o tier é explícito — não afrouxa o gate de síntese-sobre-o-mundo.

- **R9 — Discharge persiste entre rodadas (anti re-emergência estocástica).** Um claim/finding que passa
  um revisor é **carimbado resolvido** e NÃO é re-levantado por rodada posterior nos mesmos termos
  (reviewer estocástico: passou na rodada 3, re-emergiu na 5). Combina com R7 (cap) e R5 (semantic
  discharge) para convergência determinística.
  *Porquê:* objetivo nº2 — revisor estocástico + claim honesto-mas-bounded = nunca-verde sem
  persistência de discharge.
  *Aceitação:* um finding marcado resolvido na rodada k não reaparece na k+1 sem fundamento NOVO; teste
  com revisor mockado que re-levanta o mesmo ponto → é suprimido.

- **R1 — Tipo-fallback não satisfaz o floor primário com backend presente (camada do produtor, não o
  close).** Invariante: enquanto `vl-convert` importa, um tipo-fallback (`ascii-diagram`) **não conta**
  para a obrigação primária `min_blocks_of` do produtor; o floor exige o bloco **renderizável**
  (`diagram`/`chart`). `ascii-diagram` só satisfaz quando o backend está **ausente** (degradação logada)
  — **sem exceção de grafo-pequeno** (removida no gate v4, F2: um limiar qualitativo reintroduz o
  ascii-first sob outro nome; o renderer Vega dá conta de grafos pequenos). Aplica-se igualmente ao
  `min_blocks_of` com tipo-fallback (`map`) e ao `any_of` (`plan`) — duas formas do mesmo defeito. *(Retarget vs. v1: a
  mudança é no descriptor/seleção, não em re-afirmar renderabilidade no close, que já existe, E6.)*
  *Subordinação a R0 (gate v-reframe F2):* um visual só **conta** para o floor se a prosa pareada passa
  R0; o floor R1 **não dispara como falha enquanto R0 falha** (não brigar render-vs-ascii num Artefato
  que já perdeu storytelling); nenhum visual substitui explicação exigida. *Owe-detector (resolve Q1):*
  o produtor owe um visual sse o descriptor declara a forma (map→relação, plan→dependência) OU o
  conteúdo dispara o trigger quantitativo de `_check_visual_coverage`.
  *Porquê:* G1 (Direction "flip the shape-gate") — mas SUBORDINADO: visual é aditivo a R0, nunca o
  substitui.
  *Aceitação (testes vermelhos primeiro):* com `vl-convert` presente **e R0 satisfeito** — (a) `map`+2×
  `ascii-diagram` **falha**; (b) `plan` ascii-only **falha**; (c) ambos com `diagram` renderável + prosa
  que passa R0 **passam**; (d) um `diagram` renderável com **prosa fina falha** (R0 não satisfeito,
  apesar da forma R1 ok). Com `vl-convert` ausente — todos passam (degradação). O teste
  `test_visual_producers_owe_their_form_floor` (que trava o oposto) **é atualizado** — a virada da
  expectativa é a prova do conserto.

- **R2 — Grounding como invariante verificável no publish, não como contrato-de-origem (bloqueante).**
  Invariante: **nenhum visual reader-visível autorado que carregue dado/relação (claim-bearing) — `owed`
  OU opcional** (chart, diagram, ascii-diagram fallback, **e qualquer alias desenhado —
  raw-html/svg/custom-html inline-SVG**) chega ao Artefato publicado sem que cada datum/aresta resolva
  contra um span da evidência (`visuals.attributable` + laundering guard). **Tirar o qualificador "owed"
  fecha o bypass do visual opcional** (gate reframe-3 F2): um chart opcional com dado não sustentado seria
  uma fuga. Regra decorativa = **default-deny (gate reframe-3 F3):** TODO visual autorado reader-visível
  é tratado como claim-bearing (→ grounded) **a menos que** case uma forma do **allowlist decorativo
  mecânico** (sem labels/números/arestas — ex.: divisor, ícone, ornamento). **`raw-html`/SVG arbitrário
  NUNCA qualifica** (forma livre demais p/ checar). O ônus é provar decorativo, não o contrário.
  Visual desenhado que não pode passar pelo seam (ex.: SVG arbitrário em `raw-html`) é **banido** como
  caminho de visual-autorado-do-produtor — não há caminho de visual claim-bearing que escape o grounding. Mandar "produza via `add_visuals`" não basta — o close só vê o spec final e **não
  distingue** um visual spliced por `add_visuals` de um desenhado direto no spec (gate v3, F1). Logo a
  fronteira precisa ser mecanicamente verificável **no caminho que publica**. Mecanismo = escolha do
  Goal 2 entre: (a) **inserção centralizada** — o publisher *strippa* **TODO visual claim-bearing autorado
  (owed OU opcional)** pré-desenhado e só `add_visuals` (re)insere, grounded por construção (gate
  reframe-3 F2: (a) **não pode** recair em "só owed", senão o visual opcional não-sustentado sobrevive);
  ou (b) **proveniência no proof do close** —
  ligar a atestação por-visual ao digest e checar no close. `add_visuals` retorna **shortfall** quando a
  evidência não sustenta, nunca fabrica. *(Reusa `visuals.py`; resolve Q3.)*
  *Porquê:* G2 + F1 — sem fronteira verificável, R1 (floor renderável) é satisfeito por um grafo
  **inventado** que ninguém checou (regressão de corretude).
  *Aceitação:* (a) um chart/diagram/ascii-edge **ou `raw-html`/SVG-inline** desenhado **direto** no spec
  (fora do seam) é **rejeitado pelo MESMO runtime que publica**; (b) um **chart/visual OPCIONAL
  (não-owed)** com dado não sustentado é **rejeitado** (fecha o bypass do opcional); (c) um visual rotulado
  "decorativo" que carrega labels/números/relação **falha** (claim-bearing por default-deny); só a forma
  do **allowlist decorativo** passa; `raw-html`/SVG **nunca** é decorativo; (d) um visual com edge-list
  atribuída passa; um datum fora da evidência é bounced.
  Nenhum schema novo de bloco.

- **R3 — Só o RENDER é ambiente-dependente; o grounding nunca.** R1 é capability-gated: `vl-convert`
  ausente → ascii aceito + perna escurecida logada. Mas o grounding (R2) é obrigação de **conteúdo** e
  vale **igualmente para o ascii-diagram fallback**: suas arestas/nós também resolvem contra a evidência
  (gate v3, F2 — senão relação fabricada passa escondida atrás da degradação). rich-rite (E3) idem. Não
  se afrouxa conteúdo num host degradado; só se troca SVG por ASCII.
  *Porquê:* F2 + gate v1 — acoplar *validade de conteúdo* ao estado de dependência deixa fabricação
  passar pelo caminho de degradação.
  *Aceitação:* com `vl-convert` mockado ausente — (a) um ascii-edge **não sustentado** pela evidência
  **falha** mesmo degradado; (b) um ascii-edge **fundamentado** passa, com degradação logada; nenhuma
  exceção sobe.

- **R4 — Texto das SKILL.md reconciliado com o scaffold.** Remover/atualizar vocabulário stale e
  exemplos `ascii-diagram`-first nas skills de produtor (map, plan, discovery, report, research,
  critique) para refletir o floor capability-conditional (diagram/chart-first, ascii como degradação
  declarada).
  *Porquê:* G3 — o exemplo local vence a regra compartilhada.
  *Aceitação:* nenhum SKILL.md de produtor apresenta `ascii-diagram` como escolha primária **nem oferece
  `raw-html`/SVG-inline como visual autorado** (caminho ungroundable — gate v4, F1); o `map` SKILL.md em
  particular perde a opção "raw-html block carrying an inline SVG graph".

- **R5 — Conductor: CUT-com-razão + disjuntor COM classificação de severidade.** Finding se descarrega
  por bloco substantivo **OU** por `declined:{finding_id, reason}` que o reviewer aceita ou escala com
  fundamento novo. **Só findings NÃO-bloqueantes** viram residual logado; corretude, evidência,
  grounding (R2), falha de render e violação de gate **falham-fechado**. Cap duro de rodadas com saída
  *ship-with-logged-residual* apenas para o não-bloqueante.
  *Porquê:* G4 + o gate v1: sem classificação, o disjuntor vira brecha que loga-pra-fora um defeito
  real de corretude.
  *Aceitação:* (a) seed com finding não-bloqueante declinado-com-razão → converge a `final`; (b) seed
  com finding bloqueante (ex.: dado não fundamentado) → **não** pode virar residual, falha-fechado
  mesmo no cap. Ambos com teste.

- **R6 — Telemetria de adoção como EVENTO durável emitido no publish (não scan retrospectivo).** Por
  Artefato e por produtor, o close/publisher **emite no momento do publish** um evento de adoção com:
  `producer`, `owed` (a forma devia visual?), `satisfied` (rendeu?), `degraded` (ascii por `vl-convert`
  ausente), `shortfall` (`add_visuals`/`visual_flags` derrubou por falta de grounding) e `capability_state`
  (vl-convert presente no publish?). O relatório/dashboard **lê o event stream**, não reconstrói o
  denominador depois (gate v3, F3 — um scan de corpus não recupera o que foi *owed* nem o capability-state
  no publish; map/plan nem emitem `visual_flags`).
  *Porquê:* G5 + F3 — "fully use" é a taxa satisfied/owed e precisa ser falsificável entre beats; sem
  evento no publish, adoção é silenciosamente sobre/sub-contada.
  *Aceitação:* publicar um Artefato emite um evento de adoção com os seis campos; o comando de relatório
  computa satisfied/owed por produtor **a partir do stream**, não do HTML publicado; um Artefato
  não-visual legítimo aparece com `owed=false` (não polui a taxa).

## Não-objetivos

- **NÃO** trocar storytelling por visual — um visual que canibaliza a prosa do livro é regressão, não
  adoção (R0 domina R1–R6). "Sigla sem explicação" não conta como adoção.
- **NÃO** re-afirmar renderabilidade no close — já existe (E6); o forçamento vai no descriptor (R1).
- **NÃO** ligar o conductor no beat vivo antes de R5 pousar (Direction: dark até convergir).
- **NÃO** introduzir backend que precise de binário/root (mermaid-cli, graphviz): vl-convert
  puro-Python é a escolha (E1); `diagram` (Vega dag/force) cobre node-link.
- **NÃO** impor word-count nem seção obrigatória (property-not-section, ADR-0012/0013).
- **NÃO** refatorar o render layer; ele já é rico (E1). O trabalho é *adoção*, não reconstrução.
- **NÃO** punir Artefato genuinamente não-visual: R1 é content-relative (só quando a forma owes).

## Questões abertas / riscos

- **Q1. (RESOLVIDA, gate v-reframe.)** Owe-detector em R1: descriptor declara a forma (map→relação,
  plan→dependência) OU trigger quantitativo de `_check_visual_coverage`. Caso concreto: o report do
  roberto owe **dois** — um `diagram` (relação das phases do harness) e um `chart` (AUC/exact_match/
  deltas) — e renderizou **zero** (owed=2, satisfied=0).
- **Q2. (RESOLVIDA pelo gate v4.)** Exceção de grafo-pequeno **removida** — era um limiar qualitativo
  que reintroduz o ascii-first. Regra única e testável: vl-convert presente → todo visual owed renderiza.
- **Q3. (PARCIAL — não resolvida só por `add_visuals`; gate v-reframe-2 F3.)** R2 reusa a maquinaria de
  `visuals.attributable`, mas mandar "produza via `add_visuals`" **não** torna a fronteira verificável —
  o publisher não distingue um visual spliced de um desenhado direto. Q3 só se resolve quando o
  mecanismo do Goal 2 der ao publish **um trace/proof por-visual verificável OU inserção centralizada
  que rejeita visuais autorados diretos** (as duas opções de R2). A fiação de evidência
  produtor→`add_visuals` (estender do conductor aos standalone) é necessária mas **não suficiente** —
  dimensionar ambas no Goal 2.
- **Q4.** R1/R4 tocam descriptor + skills = genótipo; propaga p/ roberto/petertosh. Confirmar que
  nenhum depende do floor capability-blind atual (ou do teste que o trava).
