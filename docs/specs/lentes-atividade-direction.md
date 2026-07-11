# Spec — Lentes do ledger: Atividade (episteme) e Direction (wayfinder)

**v2 (2026-07-11): emendada pelos findings do codex xhigh** (review:
`drafts/codex-review-lentes-20260711.md`, 19 findings — 4 critical + 15 major; todos resolvidos,
nenhum rejeitado). Changelog:

1. (F1, critical) `move.proposed` ganha `effect` tipado por kind (schema fechado, validado ao
   nascer, dentro do `move_key`); novo evento `arco.moved` para mudança de filiação; ratificar
   aplica EXATAMENTE o effect.
2. (F2, critical) dedup/ratify/decline viram CAS sob o flock via `append_batch(precondition=…)`;
   proposta carrega `basis_seq` + `expects`; o effect vai EMBUTIDO no `move.ratified` (auditável
   em 1 linha) E materializado no mesmo batch.
3. (F3) lei de precedência escrita: mesmo tier → latest-wins; entre tiers → curado vence SEMPRE
   até contradição-nova abrir contested; novo evento `contest.adjudicated`; contested ganha faixa
   reservada nas janelas (autoridade ≠ visibilidade).
4. (F4, critical) idempotência do racionalizador keyed pela ENTRADA (`source_hash` +
   `rationalization_id` determinístico, CAS sob lock); re-backfill supersede por overlay datado,
   nunca duplica; `racionalizador_version` fora da identidade da evidência.
5. (F5) custo bounded por SWEEP (`max_sessions_per_sweep` + teto de tokens, backlog resumível,
   ordenação determinística); maratona segmentada em cenas com cobertura do meio (anti peak-end);
   a lei "UMA chamada" corrigida para "custo TOTAL bounded".
6. (F6) decidido: Atividade = ActivityInstance/Case (normativo), `tipo_ref` opcional; run
   multi-parent `atividades:[…]` N:M (Leontiev/process-mining).
7. (F7, critical) joins reparados: fato ganha `{ulid, num, run?, leva?}`; run ganha `leva?`;
   endereço ganha `atividade`; `ticket.closed.bears_on` obrigatório; `nao_mede` no domínio
   canônico de alvo.
8. (F8) ref curta só resolve bound a uma operação; senão `AmbiguousRef`; STITCH emite ref plena;
   `sessao.racionalizada` carrega `operacoes[]`.
9. (F9) máquina de estados completa (tabela de transições, recorrência literal de layer,
   declined desbloqueia, mapa pausado sai do frontier); `ticket.deps_changed` torna o ciclo
   construível; contest unificado com alvo tipado.
10. (F10) agenda = PULL bounded do grill no wake, nunca fila push; fold expõe moves por estado
    (histórico), não "pendentes"; trabalho-sem-mapa vira SINAL por default, proposta só sob
    critério falsificável.
11. (F11) Turn binda `dispatch_id`/`operacao` EXPLÍCITOS; foco implícito só para touch com alvo
    único; gestos mutantes exigem alvo explícito + estado checado sob lock; o evento carrega o
    resolvido.
12. (F12) anti-cabresto ganha a aceitação real (A32): propriedade de não-interferência testada
    no seam do dispatcher.
13. (F13) `rationale` + `dispatch_id` em todo gesto curatorial; gate keyed pelo dispatch exato;
    `map.state` decidido gesto asserted direto (A19 alinhada).
14. (F14) labels novos entram em `_ASSERTED_LABELS`, tipos de aresta novos em `_CLASS_BY_TYPE`
    (com testes dos 3 eixos) — a política central de proveniência deriva certo.
15. (F15) `GraphStore` ganha `replace_edges(owner_ref, kind, desired, as_of)` (padrão do rebuild
    do publisher); identidade de aresta por evento/seq; `ProjectionResult.incomplete_refs`;
    **embeddings FORA da v1** (sem caller).
16. (F16) refs Graphiti por UUID estável + display snapshot; resolução label→UUID na borda da
    caneta; projeção segue `merged_into`; ownership de valid_at/invalid_at declarado (props da
    curadoria atual, não t_invalid mágico).
17. (F17) migração com `legacy_ref` + tabela normativa de estados legados + `raw_state` +
    golden fixture; A23 cobra equivalência SEMÂNTICA definida.
18. (F18) as ~14 aceitações vagas re-escritas testáveis; a lista de testes-que-faltam vira
    A26–A40 nomeadas e distribuídas nos slices.
19. (F19) contrato AUTOSSUFICIENTE: precedência aberta da issue removida (#131 = fonte
    histórica, congelada em §Congelado); slices renumerados 1–13 integrando S+1/S+2; adendos
    integrados ao corpo. **Adotados como NORMATIVOS por decisão de 2026-07-11 (veto do operador
    reverte): taxonomia dos 5 grãos · curado-decai-por-escassez · M2.8 (contrato de
    divergência/anti-cabresto).**

---

**Fonte normativa: ESTE arquivo.** A issue lucasrp/edge-next#131 (corpo + 17 comentários de
2026-07-11 — o arco completo do grill) é a **fonte histórica** do design; o que dela importa está
CONGELADO em §Congelado-da-#131 e no corpo desta spec — a issue nunca é override vivo. Mapa do
esforço: `state/wayfinds/lentes-atividade-direction.md` (esta spec RESOLVE os tickets
`schema-eventos`, `spec-episteme-lens`, `spec-wayfinder-lens` e `spec-v2`). Prior art com fonte:
`memory/dig-prior-art-lentes-atividade-direction.md`. Irmãs: #130 (md-to-mem, FEITO —
`docs/specs/md-to-mem.md` é o padrão desta família), #132 (tier pessoa, só cross-ref),
#136 (onboarding, cross-ref). Implementação por opus via TDD (plano de slices ao fim).
**Só spec — nada roda no roberto.**

## Congelado da #131 (o que a issue fixou e esta spec carrega como lei)

- **Lei a-posteriori (mestra):** a lente de Atividade é 100% a posteriori. Zero hooks, zero
  emissão em-sessão, zero dependência do runtime da conversa. O harness já persiste o transcript;
  o racionalizador REVELA depois, no sweep. Só nasce no ato o que JÁ nasce no ato hoje (publish,
  hypothesis.declared, writeback do grill).
- **Unidade do fragmento = o TOQUE:** um `atividade.touched` por (sessão × atividade), emitido em
  UM batch atômico por sessão substancial no sweep. Nunca por-turno, nunca por-relógio. Fragmentos
  apontam para SPANS do transcript (endereço, nunca cópia).
- **Metadado é re-derivável; só o CURADO é pinado:** o cru é fonte, a racionalização é projeção —
  um racionalizador melhor re-racionaliza o mesmo trecho. Tier-hipótese re-emissível; o curado
  (GT do grill) nunca é re-derivado por cima.
- **A moeda do ledger:** a unidade de custo é TEMPO-DO-USUÁRIO + input digitado (Goldratt: o
  gargalo é a atenção do mentee; mensurável dos transcripts a posteriori — spans de turno do
  operador, chars digitados; 2 parâmetros, por evento, nunca survey). Métrica derivada:
  valor/custo por atividade. Norma de leitura, não campo obrigatório do schema.
- **Definição-norte:** o mentor extrai (Lei #0) → a memória é confiável (evals de tudo,
  endereços, presunções cobráveis) → a CONVERSA vira interface suficiente. Tudo nesta spec é
  infraestrutura desta única qualidade experimentada.
- **Critério de fecho (teleológico):** atividade fecha quando CUMPRIU SUA FINALIDADE; o
  /clear-seguro é sintoma, não critério.
- **Identidade:** o portfólio registra o emprego do MENTEE; mapa DESCREVE, nunca AUTORIZA.

## Propósito

UM ledger (o eventlog, ADR-0006), lentes por operação. Nenhum substrato novo: tipos de evento +
folds (padrão `docs_at`) + projeção determinística no cortex. As lentes são as formas maduras de
dois slots que o edge já carrega:

| Mundo | Rail maduro | Natureza | Onde mora |
|---|---|---|---|
| **Voz** | md-to-mem + canon (#130, FEITO) | gesto deliberado | inject do operador + eleição do grill |
| **Atividade** | episteme-lens (esta spec) | filmagem + racionalização bounded | assemble (fold + projeção + racionalização bounded/sessão) |
| **Direction** | wayfinder-lens (esta spec) | juízo | grill (writeback + curadoria com rationale) |

- **Lente Atividade** = o registro ligado de atividade ("o fio da meada"). Átomo = **atividade
  com FINALIDADE**, multi-sessão, N abertas em paralelo; a sessão é EVIDÊNCIA que toca
  atividades, nunca o nó. Três camadas, três custos, três proveniências: filmagem captura o cru
  (mecânico, zero LLM), a racionalização estrutura (cognição bounded, 1×/sessão-substancial,
  tier-hipótese), o grill cura (GT por exceção).
- **Lente Direction** = portfólio de mapas com tickets e frontier em vez de prosa que envelhece.
  Curadoria cognitiva do grill, sempre com rationale. **O portfólio registra o emprego do
  MENTEE** — o mapa DESCREVE, nunca AUTORIZA (§Anti-cabresto).
- **Invariante nº 1 (função-forçadora, todas as lentes):** entrada nova no ledger sem link é
  entrada de segunda classe. Ticket que fecha LIGA no que o resolveu (com valência); pensamento
  que entra liga no que toca.
- **Query-first:** o schema é derivado das 4 consultas-alvo — "o que fizemos essa semana?" ·
  "o que tem pra fazer?" · "que arquivos usei?" · "o que de novo aconteceu nessa atividade?".
  Se o metadado não responde as quatro, está errado (aceitações A1–A4).

## Taxonomia de grãos — NORMATIVO (adotado por decisão de 2026-07-11; veto do operador reverte)

De baixo pra cima: **fato/observação** (1 entrada = 1 fato; contado, com endereço; `bears_on`
quando valorado) → **run/execução** (config+corpus, replayável; eval PRÉ-registrado;
`nao_mede[]`) → **atividade/pergunta** (finalidade + ciclo de vida + fecho julgado; N runs) →
**arco** (super-atividade nomeada com valência própria) → **operação** (a venture; campo, não
nó — ver §Identidade). Transversais (não-grãos): **claim/hipótese**, **marco**
(stable_landmark), **documento** (#130), **eval**.

**Case ≠ Activity (F6, normativo):** `Atividade` nesta spec = **ActivityInstance/Case** do
process-mining — a instância viva com ciclo de vida, nunca a categoria. O TIPO de atividade fica
FORA da v1 como nó; a instância pode carregar `tipo_ref` opcional (string livre
`^[a-z0-9][a-z0-9-]*$`) que uma lente futura promove a nó sem migração — o campo já grava a
intenção sem custar schema agora.

**Lei de granularidade: o LEDGER nunca engrossa** — grão é propriedade do NÓ (da dobra), não do
evento; quem sobe de grão é o fold/racionalizador. Mapeamento da lente pessoal do operador
(experimento = primeira instância da lente geral): Experiment=atividade-pergunta,
Arm=alternativa, Run=run, Observation=fato, Report=fecho.

**Lei do eval ("evals de tudo"):** o eval não mora no evento — mora no AGREGADO. Fato: como
foi medido · run: régua PRÉ-registrada (antes de ler o resultado) · atividade: a finalidade que
o fecho julga · arco: o placar agregado · claim: o falsificador (HIP-1 estendido). Corolário:
**entrada hipotetizada COM eval é cobrável** (falsificador-aconteceu coleta); sem eval é só
saliência.

## Identidade e vocabulário comum

- **ULID por baixo, numeração legível por cima.** Todo grão nasce com ULID (chave primária
  imutável, `eventlog._ulid()` existente) E um `num` legível — a ordinalidade legível é
  SEMÂNTICA ("o frontier é o 090"): é como o humano conversa. `num` é identidade de conversa,
  nunca re-atribuído.
- **Alocação do `num`** (decisão desta spec): por-grão e por-operação, formato
  `<prefixo>-<NNN>` com prefixos `atv`/`run`/`arc`/`map`/`tkt`/`fat`; NNN monotônico por
  (operacao, prefixo), alocado DENTRO da caneta sob o flock do `append_batch` (fold do log →
  max+1) — dois writers concorrentes nunca cunham o mesmo número. Ref plena =
  `<operacao>/<num>` (ex.: `juridico/atv-012`).
- **Resolução de ref (F8 — namespaced por operação):** `ref` em qualquer evento aceita ULID
  (global) ou ref plena `<operacao>/<num>` (global) — sempre. O `num` CURTO (`atv-012`) só
  resolve quando a caneta está explicitamente **bound a uma operação** (parâmetro `operacao=`
  da caneta, ou o bind do Turn); caneta sem bind recebendo num curto → **`AmbiguousRef`**
  (subclasse de `ValueError`), mesmo que só uma operação exista no log (o acaso não é contrato).
  Toda ref resolvida é **recusada loud** (`ValueError`) se inexistente — nunca cria
  silenciosamente (padrão I7 do #130). A tripla STITCH e todo output do racionalizador emitem
  **ref plena ou `{operacao, num}`**, nunca num curto solto.
- **`operacao`** (campo obrigatório em mapa, atividade e arco): string não-vazia
  `^[a-z0-9][a-z0-9-]*$` — a venture que a lente trackeia ("ele poderia estar trackeando uma
  operação completamente diferente" vira schema, não suposição). O substrato é agnóstico à
  operação.
- **`tier`** ∈ {`asserted`, `llm_judged`}: a proveniência do ATO. Gesto humano/grill =
  `asserted`; saída do racionalizador = `llm_judged`. Mapeia direto no axis `provenance_class`
  existente (`tools/cortex_provenance.py`) — **o enum NÃO é estendido**; metadado organizacional
  auto-verificável projeta `computed` (§Racionalizador).
- **Valências** (conjunto único, todas as lentes): `supports` / `refutes` / `qualifies` /
  `inconclusive` / **`no_bearing`** (a não-medição tipada: "mediu zero" ≠ "não pode medir" ≠
  "não mede por design"). Qualquer outra string → recusa loud.
- **Gesto curatorial (F13):** todo evento asserted de curadoria (map.*, ticket.*, marco.set,
  move.ratified/declined, contest.adjudicated, atividade.closed/reopened com author=grill/
  operador) carrega `rationale` **não-blank** e `dispatch_id` **obrigatório** no log canônico
  (o dispatch do grill que o cometeu; testes usam `eventlog.test_dispatch_id()` — o precedente
  do publisher). Eventos llm_judged carregam `origem_sessao`/`rationalization_id` no lugar.
- **Validação:** canetas fail-loud no estilo HIP-1 (`_validated_falsifier`): campo obrigatório
  ausente/blank/tipo-errado → `ValueError` com mensagem nomeando o campo e a regra, NADA
  escrito. Folds fail-dark (payload corrupto não folda, nunca crasha — padrão
  `fold_direction`). Strings são `strip()`adas antes de persistir.

## Precedência e adjudicação (F3 — a lei, escrita)

**A lei:** dentro do MESMO tier, **latest-wins** (emenda asserted supersede a emenda asserted
anterior por data; llm_judged posterior supersede llm_judged anterior). Entre tiers, **curado
(asserted) vence SEMPRE**: um evento `llm_judged` posterior sobre um campo/estado já asserted
NUNCA vira estado corrente — o fold o guarda como **candidato filmado** (histórico, consultável)
e o reconciliador o converte em `move.proposed kind=contest` quando contradiz. O único caminho
que destrona um juízo curado é **contradição-nova**: `contest.raised` com evidência → o grill
adjudica (`contest.adjudicated`) → só então o sucessor vale. Peso/contagem NUNCA reabre.

**Exemplo normativo:** o grill fecha `atv-012` como `cumprida` (asserted). O racionalizador, numa
sessão posterior, emite fecho `abandonada` (llm_judged) para a mesma ref. Resultado: o fecho
corrente segue `cumprida`; o fecho llm_judged entra em `fechos[]` como candidato; o reconciliador
emite `move.proposed kind=contest` com a evidência. Se o grill adjudicar a favor da contradição,
o `contest.adjudicated` + o novo `atividade.closed` (asserted) landam no mesmo batch — e aí sim
latest-wins asserted-sobre-asserted faz o novo fecho valer.

**`contest.adjudicated`** (evento novo): payload `{alvo, veredito ∈ {mantido, corrigido},
sucessor?, rationale, dispatch_id, author}`. `veredito='corrigido'` ⇒ `sucessor` obrigatório
(ref/seq do evento asserted que passa a valer — normalmente no MESMO batch). Fecha o `contested`
do alvo; `mantido` limpa o flag preservando o histórico do contest.

**Autoridade ≠ visibilidade:** curado pode sair do top-K das janelas ordinais sob budget
(§GT, decay por escassez) SEM perder autoridade. `contested` tem **faixa reservada**: um item
contested aparece no brief do grill mesmo fora do top-K, até adjudicação (senão "contested nunca
silencioso" seria mentira sob budget) — travado por A37.

---

## Schema de eventos — Lente Atividade (episteme)

Todos os eventos: envelope padrão do eventlog (`seq`, `ts`, `type`, `subject`, `payload`);
`subject` = `atividade:<ulid>` (ou `run:`/`arco:`/`fato:`/`claim:`/`sessao:` conforme o grão).

### `atividade.opened`
Payload: `{ulid, num, operacao, finalidade, eval?, arco?, tipo_ref?, tier, author,
origem_sessao?, derivation_key?}`.
- `finalidade` **obrigatória** não-blank — hipotetizada na abertura (a meta-pergunta da
  largada, "por que isso? o que quer alcançar?", agora com endereço estrutural). É a régua que
  o fecho julga (Lei #0 do mentor virada em campo).
- `eval` opcional: dict estruturado `{regua: str não-blank, ...}` — refina a finalidade em
  forma julgável; presente ⇒ a atividade é COBRÁVEL (entra na árvore de presunções).
- `arco` opcional: ref de arco existente (recusa loud se inexistente).
- `tipo_ref` opcional (F6): a categoria, fora da v1 como nó.
- `tier` obrigatório ∈ {asserted, llm_judged}; `author` obrigatório (`'operador'`, `'grill'`,
  `'racionalizador'`).
- `origem_sessao`: session_id quando aberta pelo racionalizador; `derivation_key`: a identidade
  derivada determinística (§Racionalizador), presente sse tier llm_judged.

### `atividade.touched`
Payload: `{ref, sessao, novo?, files?, spans?, tier}`.
- `ref` obrigatória e resolvível; `sessao` obrigatória (session_id — a sessão é evidência).
  **Um touched por (sessão × atividade)** (lei do fragmento, §Congelado); re-emissão pela mesma
  (sessão, atividade) só via racionalização superseding (overlay).
- `novo`: prosa curta do que é NOVO nesta atividade (responde A4); `files`: lista de paths
  tocados (responde A3); `spans`: refs de span do transcript `[{sessao, ini, fim}]` — endereço,
  nunca cópia.
- Tocar atividade FECHADA é permitido e NÃO reabre — o reconciliador detecta e propõe
  (`move.proposed kind=contest` com alvo=a atividade, §Reconciliação); nunca silêncio, nunca
  reabertura automática.

### `atividade.closed`
Payload: `{ref, estado, julgamento, superada_por?, tier, author, rationale?, dispatch_id?}`.
- `estado` obrigatório ∈ {`cumprida`, `abandonada`, `superada_por`} — estados terminais
  distintos, nunca conflatados; a valência do fecho é dado.
- `estado='superada_por'` ⇒ `superada_por` obrigatório = ref válida de outra atividade (recusa
  loud se ausente/inexistente); nos outros estados, `superada_por` presente → recusa.
- `julgamento` obrigatório não-blank: cumpriu a finalidade? (o fecho é TELEOLÓGICO).
- Author grill/operador ⇒ gesto curatorial (rationale + dispatch_id obrigatórios). O
  racionalizador NUNCA emite closed direto — só `move.proposed` (§Racionalizador).
- **Fecho EMENDÁVEL não-destrutivo:** re-emitir `atividade.closed` para a mesma ref é a EMENDA —
  sobreposição datada, nunca apagamento. O fold guarda `fechos: [todos, em ordem]`; `fecho`
  corrente = o último **do maior tier presente** (§Precedência: um closed llm_judged posterior a
  um asserted é candidato, nunca corrente).

### `atividade.reopened`
Payload: `{ref, motivo, evidencia?, author, tier, rationale?, dispatch_id?}`.
- `motivo` obrigatório não-blank. Reabertura é gesto explícito (do grill, ou ratificação de um
  `move.proposed`). NUNCA acontece por acúmulo de peso (§GT). Reabrir atividade JÁ aberta →
  `ValueError` (§Máquina de estados).

### `atividade.bears_on`
Payload: `{ref, alvo, valencia, evidencia?, tier}`.
- `alvo`: ref de atividade, arco, ticket, claim ou hypothesis (ulid) — o join entre lentes e o
  fio entre atividades (resolve/apoia/contradiz). Recusa loud alvo inexistente.
- `valencia` obrigatória ∈ conjunto único (incl. `no_bearing`).
- Uma atividade pode servir N tickets e vice-versa; nenhum vira o outro.

### `arco.moved` (novo — F1)
Payload: `{ref, arco_novo, rationale, dispatch_id, tier, author}`.
- Muda a filiação da atividade `ref` para `arco_novo` (ref de arco existente; recusa loud).
  Nasce da ratificação de `move.proposed kind=arco.move` ou de gesto direto do grill. A filiação
  no `opened` deixa de ser imutável — o fold aplica o último `arco.moved` (latest-wins por tier).

### `run.opened`
Payload: `{ulid, num, atividades, leva?, config, eval, nao_mede?, tier, derivation_key?}`.
- `atividades` obrigatória (F6): **lista não-vazia** de refs de atividade resolvíveis — run
  nunca é órfão e o join é **N:M** (Leontiev: uma ação serve múltiplas atividades; o
  process-mining separa Case-ID de Activity-ID e admite execução entrelaçada — duplicar o run
  para cada pergunta duplicaria evidência). O 1º elemento é a **primária** (a que o render
  aninha); as demais viram arestas do mesmo join. Fold: o run aparece em `runs[]` de TODAS.
- `leva` opcional: identificador da leva de evidência (dispatch_id, sessão) — o join do
  `instrumento.falhou` (F7).
- `config`: dict livre não-vazio (o replayável: corpus, arms, parâmetros).
- `eval` **obrigatório e PRÉ-registrado**: `{metric: str não-blank, predicao: str não-blank}`.
  A caneta computa `prediction_hash = sha256(JSON canônico de {metric, predicao})` e o grava
  NO evento — **pré-registro com dente**: a predição é congelada pelo SUBSTRATO antes do
  resultado; o caller nunca fornece o hash (anti-HARKing).
- `nao_mede` (F7): lista de **alvos no domínio canônico de `bears_on.alvo`** (ULID ou ref
  plena, resolvíveis) — o que este eval explicitamente NÃO testa. Capacidade ausente conta como
  `no_bearing` via `nao_mede[]`, **nunca zero**. Mesmo domínio ⇒ A11 é comparável: a caneta
  resolve ambos a ULID antes de comparar.

### `run.closed`
Payload: `{ref, resultado, bears_on?, tier}`.
- `resultado` obrigatório não-blank; `bears_on`: lista de `{alvo, valencia}` (mesma validação).
  A caneta checa: valência ≠ `no_bearing` sobre alvo listado em `nao_mede` do próprio run →
  recusa loud (o run declarou que não mede aquilo); `no_bearing` sobre o mesmo alvo é aceita.
- Emendável por re-emissão, como `atividade.closed` (mesma precedência por tier).

### `fato.observed`
Payload: `{ulid, num, atividade, run?, leva?, body, endereco?, medida?, tier}`.
- `ulid` + `num` (prefixo `fat`) — F7: todo grão tem identidade; a projeção de `:Fato` é keyed
  por ULID. `atividade` obrigatória (fato é contado E preso à unidade — "113 erros" auditável =
  número com endereço); `run` opcional (F7: fecha a cadeia fato→run→atividade→arco do
  `presumptions_at`); `leva` opcional (join do `instrumento.falhou`); `body` obrigatório
  não-blank; `medida` opcional `{valor, como}` (o como-foi-medido é o eval do grão fato).
  **Evento cru não carrega veredito** — não se julga um frame; o eval mora no agregado.

### `arco.opened` / `arco.closed`
- opened: `{ulid, num, operacao, nome, tier, author}` — nome não-blank.
- closed: `{ref, valencia, julgamento, tier, rationale?, dispatch_id?}` — **o arco tem valência
  PRÓPRIA** ("negativo frio PRO ARCO V10": o veredito é do arco, agregando as atividades que
  apontam pra ele). Emendável por re-emissão. Membership: a atividade aponta o arco (campo
  `arco` no opened); mudança de arco = `arco.moved` (gesto do grill ou ratificação de
  `move.proposed kind=arco.move`).

### `marco.set`
Payload: `{operacao, ref, nota?, rationale, dispatch_id, author}`.
- **Dois ponteiros distintos na mesma cadeia**: `stable_landmark` (marco — "o último marco
  estável, o índice") ≠ `frontier` (a última atividade viva, COMPUTADA). O marco é juízo →
  armazenado, latest-wins por operação (fold espelha `objective_at`); gesto curatorial (F13).
  O frontier NUNCA é armazenado (§Folds).

### `claim.declared` — REUSA a caneta HIP-1 existente
`eventlog.declare_hypothesis(statement, falsifier, ...)` — nenhum tipo novo: o claim explícito
do power-user ("cria a hipótese X") É `hypothesis.declared`, tier `asserted`, falsificador
estruturado obrigatório (o TETO de precisão). Versão = `hypothesis.superseded` (existente).

### `claim.hypothesized`
Payload: `{ulid, statement, falsifier?, origem_sessao, derivation_key, tier: 'llm_judged'}`.
- O piso de graça (UX SUAVE, invisível): claims implícitos extraídos da conversa pelo
  racionalizador. `statement` obrigatório não-blank; `falsifier` OPCIONAL — mas se presente,
  validado pela MESMA `_validated_falsifier` (HIP-1). Sem falsifier = só saliência (não entra
  na cobrança); com falsifier = cobrável. Corrigível conversacionalmente (GT por exceção).
- Lei de design (genótipo): nunca exigir do usuário o comportamento do operador — o explícito
  define o teto; o racionalizador entrega o piso.

### `claim.promoted`
Payload: `{hypothesized, declared}` — liga um `claim.hypothesized` ao `hypothesis.declared` que
o grill cunhou ao ratificar (ambos devem existir no log; recusa loud). O fold marca o
hypothesized como promovido (sai da janela de hipóteses soltas sem apagar).

### `contest.raised`
Payload: `{alvo, evidencia, detalhe, author}`.
- **O que RE-ABRE um fato curado**: contradição-NOVA com evidência (`evidencia` = ref de
  fato/run/atividade obrigatória e resolvível), **nunca peso acumulado**. O curado permanece
  autoritativo até o grill julgar via `contest.adjudicated` (§Precedência); o fold marca
  `contested: true` no alvo; o brief do grill SEMPRE o superfície na faixa reservada
  (**contested nunca silencioso**, A37). Linhagem McCallum honrada sem override stale.

### `sessao.racionalizada`
Payload: `{sessao_id, surface, operacoes, source_hash, rationalization_id,
racionalizador_version, supersedes?, stitch: {goal, acao, entidades[]},
epistemico: {presuncoes[]}, organizacional: {enderecos[]}}`.
- O registro-auditoria de UMA racionalização (§Racionalizador). Identidade e versionamento
  (F4): keyed pela ENTRADA, nunca pelo output —
  `source_hash = sha256(sessao_id + surface + watermark + turnos normalizados)` e
  `rationalization_id = sha256(source_hash + racionalizador_version)`, ambos computados pela
  caneta. **CAS sob o lock**: `append_batch(precondition=…)` recusa se `rationalization_id` já
  landou — re-rodar o mesmo input com a mesma versão escreve ZERO. `supersedes` = o
  `rationalization_id` anterior da MESMA sessão (sessão que cresceu ⇒ watermark novo ⇒
  source_hash novo; versão nova do racionalizador ⇒ rationalization_id novo) — overlay datado,
  nunca paralelo (§Racionalizador).
- `operacoes` (F8): lista não-vazia das operações que a sessão tocou; as entidades do STITCH
  emitem ref plena.
- `organizacional.enderecos`: `[{atividade, path, papel, sha256?|stat?}]` — cada endereço
  aponta a atividade dona (F7; é o join que A3 exige). Verificação MECÂNICA auto-confirmante
  (stat/hash no próximo toque) ⇒ projeta `provenance_class='computed'`, custo zero de GT,
  **NUNCA entra na fila do bisect nem no GT**. `epistemico.presuncoes`:
  `[{texto, confirmaria, refutaria, depende_de?}]` — cada presunção nasce de uma régua e SABE
  o que a confirmaria/refutaria (o insumo do bisect).

### `instrumento.falhou`
Payload: `{instrumento, leva, detalhe}`.
- Falha de instrumento é entrada de 1ª CLASSE (análogo do seca-suspeita): `leva` casa com o
  campo `leva` de fatos/runs (F7 — o join agora existe no schema). O fold marca
  `admissibilidade: 'suspeita'` em fatos/runs da mesma leva — condiciona a admissibilidade do
  que veio junto ("antes de valer como negativo"). O grill julga; o fold só marca.

## Máquina de estados (F9 — completa)

**Atividade** (estado do fold; grão nasce `aberta`):

| De | Evento | Para | Regras |
|---|---|---|---|
| — | `atividade.opened` | aberta | caneta valida campos |
| aberta | `atividade.closed` | cumprida/abandonada/superada_por | fecho julgado; racionalizador só propõe |
| cumprida/abandonada/superada_por | `atividade.closed` (re-emissão) | idem (novo estado) | EMENDA datada; precedência por tier (§Precedência) |
| cumprida/abandonada/superada_por | `atividade.reopened` | reaberta (≡ aberta) | gesto explícito; motivo obrigatório |
| aberta/reaberta | `atividade.reopened` | — | **ValueError** (reabrir aberto é bug do caller) |
| qualquer | `atividade.touched` | inalterado | touch em fechada NÃO reabre; reconcile propõe contest |
| qualquer | `arco.moved` | inalterado (filiação muda) | latest-wins por tier |

**Ticket** (nasce `open`):

| De | Evento | Para | Regras |
|---|---|---|---|
| open | `ticket.closed` | closed | resolucao + valencia + bears_on obrigatórios |
| open | `ticket.declined` | declined | reason obrigatória |
| closed/declined | `ticket.reopened` | open | motivo obrigatório |
| open | `ticket.reopened` | — | **ValueError** |
| closed/declined | `ticket.closed`/`declined` (re-emissão) | idem | EMENDA datada (mesma regra do fecho) |
| qualquer | `ticket.deps_changed` | inalterado (deps mudam) | ciclo → ValueError (agora construível e testável) |

**Mapa** (nasce `ativado`): `map.state` ∈ {ativado, pausado, arquivado}, latest-wins.
Ticket de mapa pausado/arquivado **preserva estado** mas **sai do frontier**: `frontier_of` e a
espinha do wake só computam sobre mapas `ativado` (decisão desta spec — pausar o mapa é pausar
a cobrança, nunca perder o estado).

**Frontier — recorrência literal (F9):** para ticket `t` `open` de mapa ativado:
`layer(t) = 0` se todo `b ∈ blocked_by(t)` está `closed` **ou `declined`** (declined
DESBLOQUEIA — decisão desta spec: um bloqueio recusado não segura ninguém; quem discorda
reabre); senão `layer(t) = 1 + max(layer(b) para b vivo em blocked_by(t))`. Blockers em layers
diferentes: o `max` decide (o pior caminho manda). Ticket fechado/declinado não tem layer.

### `ticket.deps_changed` (novo — F9)
Payload: `{ref, blocked_by, rationale, dispatch_id, author}`.
- Substitui a lista de dependências do ticket (latest-wins). A caneta valida: refs existentes +
  **detecção de ciclo contra o fold corrente** → recusa loud. Com este evento o ciclo é
  construível por APIs válidas — o teste de ciclo (A41) deixa de ser vácuo.

---

## Schema de eventos — Lente Direction (wayfinder)

Emitidos pelo grill (writeback com rationale) ou por ratificação de `move.proposed`. Tier
default `asserted` (juízo humano-no-loop); um mapa/ticket nascido de proposta não-ratificada é
`llm_judged` e fica filmado (§Anti-cabresto). Todo gesto asserted: `rationale` + `dispatch_id`
(F13).

### `map.opened`
Payload: `{ulid, num, operacao, titulo, rationale, thread?, tier, author, dispatch_id}`.
- `operacao`, `titulo`, `rationale` obrigatórios não-blank — abrir mapa JÁ é juízo; o rationale
  vive no MESMO grafo dos tickets.
- `thread` opcional (F16): **`{uuid, display}`** — o UUID Graphiti ESTÁVEL do cluster + snapshot
  do nome exibido. A resolução label→UUID acontece **na borda da caneta** (query pontual ao
  grafo; não-encontrado ou ambíguo → recusa loud, padrão I7); o payload NUNCA persiste só
  label/slug (rename não quebra a ref; `display` é cortesia de render, nunca chave).

### `map.state`
Payload: `{ref, estado, rationale, author, dispatch_id}`.
- `estado` ∈ {`ativado`, `pausado`, `arquivado`}; `rationale` obrigatório não-blank (curadoria
  do portfólio COM rationale — nunca kanban mudo). Latest-wins por mapa. Mapa nasce `ativado`.
- **Decidido (F13): `map.state` é gesto asserted DIRETO do grill** — não existe kind de move
  para ele além de `map.archive` (que, ratificado, tem como effect exatamente um `map.state
  estado='arquivado'`). A19 cobra o gesto, não um "ratificado" inexistente.

### `ticket.opened`
Payload: `{ulid, num, map, titulo, question, rationale, blocked_by?, inscricao?, tier, author,
dispatch_id}`.
- `map` obrigatório (ref resolvível — ticket nunca é órfão); `titulo`/`question`/`rationale`
  não-blank (F13).
- `blocked_by`: lista de refs de ticket existentes (arestas como fatos; ciclo detectado →
  recusa loud); mutável via `ticket.deps_changed`. Corte do dig: só a aresta BLOQUEANTE é
  estrutural; `discovered-from`/`supersedes` são ANOTAÇÃO (campos livres `annotations?`), nunca
  travam o frontier.
- `inscricao` opcional: ulid de hypothesis declarada — o ticket PODE carregar/apontar uma
  inscrição com falsificador (é onde o falsificador-aconteceu se pendura).
- Migração: `legacy_ref?` + `annotations.raw_state?` (F17, §Migração).

### `ticket.closed`
Payload: `{ref, resolucao, valencia, bears_on, rationale, tier, author, dispatch_id}`.
- `resolucao` não-blank + `valencia` obrigatória (fecho VALENCIADO e datado — "CLOSED — NÃO
  paga"); `bears_on` **obrigatório: lista não-vazia** de `{alvo, valencia}` (F7 — a invariante
  nº 1 vira validação: ticket que fecha LIGA no que o resolveu; um fecho genuinamente sem
  referente aponta a própria resolucao como fato observado antes — o caso raro paga o gesto,
  nunca o schema afrouxa). Emendável por re-emissão (mesma regra do fecho de atividade).

### `ticket.declined` / `ticket.reopened`
- declined: `{ref, reason, rationale?, dispatch_id, author}` (reason não-blank; reason É o
  rationale quando rationale ausente).
- reopened: `{ref, motivo, evidencia?, rationale?, dispatch_id, author}` — gesto do grill ou
  ratificação de move. Transições: §Máquina de estados.

### `move.proposed`
Payload: `{ulid, kind, alvo?, effect, expects, evidencia, rationale, basis_seq, move_key,
author: 'edge'}`.
- **A filmagem PROPÕE, nunca move** — o write-model inédito (propor-vs-cometer). `kind` ∈
  {`ticket.close`, `ticket.open`, `ticket.reopen`, `atividade.close`, `atividade.reopen`,
  `map.archive`, `arco.move`, `contest`, `falsificador_aconteceu`}.
- **`effect` (F1): o payload COMPLETO e auto-suficiente do efeito** — `{event_type, subject,
  payload}` com schema FECHADO por kind (tabela abaixo), validado pela MESMA validação da
  caneta correspondente **quando a proposta nasce** (proposta inválida não lande; nunca se
  descobre na ratificação). Ratificar aplica EXATAMENTE este effect — a cognição nunca o
  reconstrói.

  | kind | effect.event_type |
  |---|---|
  | ticket.close | `ticket.closed` |
  | ticket.open | `ticket.opened` (payload completo: map, titulo, question, rationale…) |
  | ticket.reopen | `ticket.reopened` |
  | atividade.close | `atividade.closed` |
  | atividade.reopen | `atividade.reopened` |
  | map.archive | `map.state` (estado='arquivado') |
  | arco.move | `arco.moved` |
  | contest | `contest.raised` (alvo = qualquer grão fechado/curado: atividade OU ticket — o contest é UM kind com alvo tipado; resolve o conflito A8×reconciliador da v1) |
  | falsificador_aconteceu | `contest.raised` (alvo = o ticket da inscrição atingida; detalhe carrega a hypothesis e o run) |

- `expects`: o estado do alvo que o effect pressupõe (ex.: `{estado: 'open'}`) — a precondição
  de aplicabilidade re-checada na ratificação (F2).
- `basis_seq`: o seq do fold sobre o qual a proposta foi computada (F2) — proposta stale é
  detectável.
- `evidencia` obrigatória: lista não-vazia de refs resolvíveis (atividades/runs/fatos que
  fundamentam) — proposta sem evidência não lande.
- `move_key` = sha256 canônico de `(kind, alvo, effect canônico, evidencia ordenada)` computado
  pela CANETA (F1: o effect entra na chave — dois effects diferentes para o mesmo alvo são
  moves diferentes). **Propose é CAS (F2):** a caneta lande via
  `append_batch(precondition=…)` que, SOB o flock, re-verifica que o `move_key` não existe em
  nenhum estado (proposto, ratificado OU declinado) — dois sweeps concorrentes nunca duplicam
  (A26).
- Propostas com autoria do edge ficam FILMADAS mesmo não-ratificadas (dados, não pendências).

### `move.ratified`
Payload: `{ref, effect, rationale, dispatch_id, author}` + **no MESMO `append_batch`** o evento
do effect materializado — ratificar É cometer; não existe janela em que o move está ratificado e
o efeito não landou (padrão C3 do `publish_artefato_atomic`: o batch é UM write+fsync
indivisível).
- **Semântica CAS (F2):** `ratify_move` roda como `append_batch(precondition=…)` que, SOB o
  flock, verifica (a) o move está `proposed` (nem ratificado nem declinado — ratify×decline são
  EXCLUSIVOS, A27); (b) o alvo satisfaz `expects` no fold corrente (proposta stale → recusa
  loud com o estado atual na mensagem). O `effect` vai EMBUTIDO no próprio `move.ratified`
  (cópia auditável: o fold pode aplicá-lo desta única linha; recovery nunca depende de casar
  duas linhas) E materializado como evento próprio no mesmo batch (é o que os folds das lentes
  consomem). Invariante travada por teste (A17): o evento materializado == o effect embutido.

### `move.declined`
Payload: `{ref, reason, pin: bool, rationale?, dispatch_id, author}`.
- **Retração PINA** (TMS/ATMS via dig): `pin: true` ⇒ o `move_key` entra na lista de pins; o
  reconciliador NUNCA re-propõe um move pinado. Default `pin: false` (declínio circunstancial
  re-propositável com evidência NOVA → move_key diferente). **Decline é CAS** (mesma
  precondition de exclusividade do ratify — A27).

### `portfolio.confirmed`
Payload: `{rationale, dispatch_id}` — a confirmação explícita "li os mapas, nada muda" que
satisfaz o gate do mentor quando não há diff (§Steers). `rationale` não-blank; `dispatch_id`
obrigatório (o gate é keyed por ele, F13).

### Frontier — NUNCA armazenado
Não há evento `frontier.*` (o `frontier.moved` do esboço está DELETADO — roubo do beads
`bd ready`). Frontier é COMPUTADO do estado de bloqueio, sempre, pela recorrência literal da
§Máquina de estados, com vista em camadas: Layer-0 = começa-já; Layer-N = distância de bloqueio.
Definição da prática do roberto: "open + Blocked by fechados" (+ declined desbloqueia).

### Canon/poda
A poda de mapa/ticket morto usa o rail do #130: `CANON_KINDS` ganha `'map'` (decisão desta
spec — extensão da tuple própria do canon, NÃO do enum `provenance_class`); `canon.elected
{kind:'map', ref}` dá standing ao mapa na janela; wayfind é só mais um objeto que o grill cura.

---

## Folds e consultas (eventlog, padrão `docs_at` — puros, cursor-aware, fail-dark)

- `atividades_at(seq=None, ts=None, log=LOG) -> {ref: item}` — item carrega: `ulid, num,
  operacao, finalidade, eval, arco (após arco.moved), tipo_ref, estado
  (aberta|cumprida|abandonada|superada_por|reaberta), fechos[] (histórico datado, com tier;
  fecho corrente = §Precedência), toques[] (sessões; superseded por overlay saem do corrente,
  ficam no histórico), files (união dos touched), novo[] (por toque), bears_on[], runs[] (join
  N:M), fatos[], contested, admissibilidade, tier, sessoes_sem_toque (contagem de
  `sessao.racionalizada` **da mesma operação** posteriores ao último toque — F18/A9 decidido:
  por-operação, não global; o insumo do wake)`.
- `wayfinds_at(seq=None, ts=None, log=LOG) -> {maps: {ref: {estado, tickets[], rationale_log[],
  thread}}, moves: {propostos[], ratificados[], declinados[]}, pins: set(move_key)}` — F10: os
  moves são expostos POR ESTADO como histórico consultável; a palavra "pendentes" morre (não há
  fila).
- `frontier_of(map_ref, seq=None, ts=None, log=LOG) -> [[layer0...], [layer1...], ...]` —
  pura, derivada pela recorrência da §Máquina de estados, só sobre mapas ativados; nunca lê
  nada armazenado como frontier.
- `claims_at(...)` — declared (via `hypotheses_at` existente) + hypothesized + promovidos +
  contested.
- `arcos_at(...)`, `marco_of(operacao, ...)` (latest-wins), `runs_at(...)`.
- `presumptions_at(...) -> árvore` — as presunções epistêmicas dos `sessao.racionalizada` +
  evals de agregados, com dependências via agregação (fato→run→atividade→arco — a cadeia agora
  existe no schema, F7) — o insumo do bisect (§GT). Metadado organizacional NUNCA aparece aqui.
- `portfolio_diff(dispatch_id, log) -> {abertos, fechados, reabertos, ativados, pausados,
  arquivados, moves_ratificados, frontier_antes, frontier_depois}` — **keyed pelo dispatch_id
  exato** (F13): entram só os gestos curatoriais que carregam ESSE dispatch_id; nunca janela
  temporal compartilhada (um gesto concorrente de outra sessão jamais é apropriado).
- `atividades_for_hypothesis(ulid, ...)` — **a via inversa** (adição 6 da prática do roberto):
  a hipótese lista suas atividades (join por `bears_on`/`inscricao`).
- **`portfolio_at(seq, ts, log) -> Portfolio`** (leitura única, do design-it-twice): um fold
  pass devolve atividades (quentes primeiro) + frontier COMPUTADO + tickets + presunções +
  **agenda** + contested (faixa reservada) + canon + vistas. **Agenda (F10, reconciliada com
  "sem inbox"):** a agenda é **PULL do grill no wake** — uma vista BOUNDED (top-K, ordenada
  pelo bisect) computada quando o grill/wake a pede; NUNCA fila push com contador cobrando, sem
  estado próprio, sem "N pendentes" persistente. Conteúdo: os moves propostos-não-adjudicados
  MAIS discriminativos + presunções vencidas do recheck, cortados no budget do brief. O
  histórico completo segue em `wayfinds_at.moves` (dados, não pendências).

## Racionalizador (cognição bounded — `tools/racionalizador.py`)

- **Gatilho:** no sweep do assemble, por sessão-substancial nova (fiação do `classify_session`
  dormente em `tools/sessions.py`; substancial = critério do `quente.py` `is_substantial`).
  Forma Letta sleep-time: background, bounded, nunca no caminho quente.
- **Identidade e versionamento (F4 — keyed pela ENTRADA):**
  - `source_hash = sha256(sessao_id + surface + watermark + turnos normalizados)` — a
    identidade da EVIDÊNCIA. `watermark` = o cursor do último turno incluído; sessão que cresce
    ⇒ watermark novo ⇒ source_hash novo.
  - `rationalization_id = sha256(source_hash + racionalizador_version)` — a identidade da
    RACIONALIZAÇÃO. `racionalizador_version` (modelo + versão de prompt/schema) é registrado no
    payload e entra AQUI, nunca no source_hash (a evidência bruta não muda quando o
    racionalizador melhora).
  - **CAS sob o lock:** o batch lande via `append_batch(precondition=…)` que recusa se o
    `rationalization_id` já existe — o precedente `record_session_topic` (check-then-append fora
    do lock) é explicitamente INSUFICIENTE e não é o modelo aqui.
  - **Re-racionalização = SUPERSEDE por overlay datado, nunca paralelo:** a nova
    `sessao.racionalizada` carrega `supersedes: <rationalization_id anterior da mesma sessão>`.
    No fold, os eventos derivados tier-hipótese da racionalização superseded saem do estado
    CORRENTE (ficam no histórico); os da nova valem. EXCEÇÃO pinada: grão hipotetizado que já
    recebeu gesto asserted (touch/fecho/promote do grill) está PROMOVIDO — o overlay nunca o
    remove (curado nunca é re-derivado, §Congelado). Antes de abrir atividade nova, o
    racionalizador resolve contra o fold (atividades abertas da operação); `derivation_key =
    sha256(source_hash + kind + ordinal)` gravada nos grãos derivados dá estabilidade de ref
    quando a segmentação coincide. Resultado testável: re-backfill com N maior e output LLM
    diferente ⇒ ZERO atividades paralelas duplicadas (A29).
- **Custo bounded (F5 — por SWEEP, não só por sessão):** knobs no agent.yaml (fenótipo), família
  `lentes.*`:
  - `lentes.backfill_days: N` — horizonte do backfill a-posteriori (ausente = sem limite;
    limita CUSTO, NUNCA decay; sessões fora do horizonte seguem no store cru — re-rodar com N
    maior as alcança; metadado é re-derivável). Semente do ed: 30.
  - `lentes.max_sessions_per_sweep: K` — teto de sessões racionalizadas por sweep.
  - `lentes.sweep_token_budget` — teto agregado de tokens/chamadas por sweep; estourou ⇒ para.
  - **Backlog resumível, ordenação determinística:** pendente = sessão substancial sem
    `rationalization_id` no log (o log É o checkpoint; nenhum cursor externo); ordem = mais
    antiga primeiro. O sweep seguinte continua de onde parou.
  - **Maratona — cenas com cobertura do MEIO:** sessão que não cabe na janela de contexto é
    segmentada MECANICAMENTE em cenas (fronteiras baratas: /clear, gaps longos, bursts de tool)
    ANTES da chamada final; as cenas cobrem início, MEIO e fim (amostragem uniforme quando
    preciso cortar — nunca só head+tail: o viés peak-end da perna 4 do dig é o erro nomeado).
    **A lei "UMA chamada" está CORRIGIDA (F5): a lei é o TETO TOTAL** — ≤ `ceil(cenas/janela)`
    chamadas de cena + 1 de consolidação, tudo dentro do `sweep_token_budget`; o número de
    chamadas é consequência, não dogma. Sessão que mesmo assim não coube volta ao backlog.
- **Pergunta (reancorada):** NÃO "resuma esta sessão" — "esta sessão tocou QUAIS atividades:
  continua uma aberta, abre nova, fecha alguma?". O casamento sessão→atividade é inferência em
  tier-hipótese; é a classe onde o GT do grill mais vale.
- **Critério de registro da conversa-livre:** "muda algo no que eu faço?" — sessão substancial
  que não muda nada emite `sessao.racionalizada` mínima (stitch + zero derivados), nunca
  atividade fantasma.
- **Outputs (UM `append_batch` atômico por sessão, CAS por rationalization_id):**
  1. `sessao.racionalizada` (auditoria + tripla STITCH + duas famílias de metadado +
     operacoes[]);
  2. eventos derivados tier `llm_judged`: `atividade.opened/touched` diretos (hipóteses
     dirigem a navegação já — GT por exceção), `atividade.close` e reaberturas SÓ como
     `move.proposed` (fecho é juízo);
  3. `claim.hypothesized` (extração de claims implícitos — LLMKT: extração é o passo ruidoso ⇒
     proposta-nunca-fato);
  4. metadado organizacional (endereços com `atividade`) — projeta `computed` após
     auto-verificação stat/hash; nunca entra no GT.
  **Output LLM parcialmente inválido ⇒ ZERO eventos (A36):** a validação das canetas roda sobre
  o batch inteiro ANTES do append; um item malformado aborta o batch todo (all-or-nothing) e a
  sessão volta ao backlog com o erro registrado no retorno.
- **Interface:** `racionalizador.rationalize(session_id, turns, complete_fn, log=eventlog.LOG)
  -> {emitted: [...], skipped_reason?}` — `complete_fn` injetável (teste com mock; zero rede).

## Reconciliação Atividade↔Direction (mecânica, zero LLM — `portfolio.reconcile`)

- Roda no sweep do assemble, DEPOIS do racionalizador. **Casamento mecânico** por refs
  explícitas apenas: (a) `atividade.bears_on` com alvo ticket; (b) run/fato com `bears_on` em
  hypothesis pendurada em `ticket.inscricao`; (c) entidade da tripla STITCH com **ref plena**
  igual a ticket (F8: num curto sem operação NUNCA casa — duas operações com `tkt-001` são
  indistinguíveis por design, e o casamento ambíguo é descartado, não chutado; A31). Nada de
  similaridade/LLM aqui.
- Emite `move.proposed` (com effect tipado + basis_seq + expects; dedup CAS por `move_key` sob o
  lock — dois reconciliadores concorrentes landam UM, A26; pins respeitados): ticket cuja
  inscrição foi atingida → kind `falsificador_aconteceu` (**nasce AQUI**: o mapa flageia → o
  mentor chega uninvited com o motivo na mão); re-trabalho de ticket fechado (touch em atividade
  que bears_on ticket fechado) → kind `contest` (alvo=ticket); touch em atividade fechada →
  kind `contest` (alvo=atividade) — **UM kind, alvo tipado** (resolve o conflito A8 da v1).
- **Trabalho sem mapa (F10): SINAL, não proposta.** Atividade substancial sem mapa entra no
  brief como observação (`portfolio_at.sem_mapa[]`), custo zero de adjudicação. Só vira
  `move.proposed kind=ticket.open` quando cruza o critério FALSIFICÁVEL desta spec: a atividade
  tem `eval` presente (é cobrável) **e** ≥2 sessões de toque — abaixo disso, filmar basta;
  jamais um item persistente por atividade filmada (o kanban degenerado que o codex nomeou).
- Motivos uninvited do mentor ancoram nos folds: `loop` = atividade girando sem estado novo
  (`toques` crescem, `novo` vazio); `largada` = atividade nova detectada na filmagem.
- **Cursor/idempotência:** o reconciliador é puro sobre o log até `seq`; re-rodar sobre o mesmo
  log não emite nada novo (move_keys já landados; o dedup É a idempotência — agora CAS, F2).
  Nenhum cursor externo próprio.

## GT — por exceção, nunca fila

- **Drift aceito**: as hipóteses do edge dirigem a navegação em tier-hipótese indefinidamente;
  o risco é o custo de NÃO FICAR VAZIO; a correção é CONVERSACIONAL (o mentee fala com o
  mentor — o grill já é o canal). Ratificação-antes-de-valer restrita ao perfil/leveling
  (#132, regra pré-existente). **Nenhum inbox de pendências, nunca** — a agenda é pull bounded
  (§Folds, F10).
- **Colheita por BISECT**: `portfolio.bisect(operacao, log) -> [perguntas ordenadas]` — sobre a
  árvore de `presumptions_at`, computa a pergunta de maior poder discriminativo ESTRUTURAL
  (a que mais poda a árvore — não fila por risco à la ORES); os ramos abaixo colapsam.
  Minimum path de convergência; a abertura do grill ganha o segundo instrumento ("destas N
  presunções, UMA pergunta resolve a maioria"). O bisect não cria inbox — ORDENA o pouco que
  chega ao humano quando o grill roda (é ele que ordena a agenda-pull).
- **Retração PINA** (`move.declined pin=true`) — anti re-proposta eterna.
- **Ratifica-1-cascateia-N** (RAID): a intenção da correção propagada a irmãos — **otimização
  FUTURA anotada**, fora desta spec (não-objetivo; o schema não a impede: moves carregam
  evidência estruturada suficiente para um cascateador ler depois).
- **Curado DECAI por escassez — NORMATIVO (adotado 2026-07-11; veto do operador reverte)**:
  fato curado nunca perde no CONFLITO (a lei, §Precedência), mas compete nas janelas ordinais
  como tudo — deslocado sob budget finito sai de cena SEM perder autoridade; re-aberto só por
  contradição-nova (`contest.raised`) ou re-eleição (canon). Isenção de decay recriaria a
  lista-enorme vetada no #130. EXCEÇÃO única: a faixa reservada de `contested` (§Precedência,
  A37) — contestado não decai até adjudicação.

## Steers e gate do mentor

- **Objective** = âncora ACIMA dos mapas (por que este portfólio) — `objective.set` existente,
  intocado.
- **Direction** = o diff do portfólio COM rationale — `portfolio_diff(dispatch_id)`; os gestos
  `map.*`/`ticket.*`/`move.ratified` do dispatch SÃO a direção (cada um já carrega rationale e
  o dispatch_id que o gate confere, F13).
- **Direcionamento** = a carta do mentor SOBRE o portfólio — `direction.report` existente,
  intocado (a leitura em prosa; prosa não envelhece silenciosa porque o estado está nos mapas).
- **Gate do mentor** (`portfolio.direction_gate(dispatch_id, log) -> ok|raise`): o close do
  mentor exige `portfolio_diff(dispatch_id)` não-vazio **OU** um `portfolio.confirmed` com esse
  dispatch_id e rationale — **nunca prosa vazia, nunca diff fabricado, nunca gesto de outra
  sessão apropriado** (keyed pelo dispatch exato, F13). Fail-loud.

## Anti-cabresto (normas de identidade — travam o desenho, não só a prosa)

1. **O portfólio registra o emprego do MENTEE.** O frontier direciona o próximo passo DO
   MENTEE; o próximo passo do edge segue governado pelo contrato próprio (wake de 4 briefs,
   abate, budget de curiosidade, motivos uninvited, propostas com autoria própria).
2. **Mapa DESCREVE, nunca AUTORIZA.** Nenhum caminho de código pode derivar permissão/dispatch
   de um estado de mapa — travado pela **propriedade de não-interferência (A32, F12)**: com
   Voz, sessão e contrato do edge constantes, mutar SOMENTE estados de mapa/frontier não muda
   permissões, ferramentas disponíveis nem a decisão de dispatch — testado no SEAM do
   dispatcher (comparação da saída do dispatcher antes/depois da mutação do portfólio), nunca
   só inspeção de bundle.
3. **Propostas com autoria do edge ficam FILMADAS mesmo não-ratificadas** — `move.proposed`
   nunca é apagado nem expira; declined-com-pin permanece consultável.
4. **lazer/delta/diverge são MAP-BLIND**: essas cognições nunca recebem o portfólio no brief
   (delta já é subject-blind, ADR-0011 — a lente não fura isso). Quem lê o portfólio:
   wake/assemble, mentor/grill, recall (âncora de travessia). (M2.8 adotado normativo,
   2026-07-11.)
5. **dig = FLARE que o mentor dispara a subagentes** (contrato do mentor; implementação no
   ticket `mentor-dispara-digs`, fora desta spec): nunca come o contexto do grill; retorno
   assíncrono landa como asset (topic file) + evidência citável — nunca dump no contexto.
   Placar: **bom dig AUMENTA o que há a resolver** (flare que volta "tudo confirmado" é
   suspeita de bajulação ou seca falsa).

## Turn — a superfície do grill (açúcar, nunca seam; F11)

Em `tools/portfolio.py`, sobre as canetas do eventlog (padrão elect_canon):

- **Bind EXPLÍCITO na construção**: `turn(dispatch_id=…, operacao=…, log=…)` — `dispatch_id` e
  `operacao` são parâmetros obrigatórios, NUNCA inferidos "do dispatch.open fresco" (a
  inferência reintroduziria a corrida que o publisher já eliminou exigindo dispatch_id
  explícito — precedente eventlog.publish). O bind de operação é o que licencia num curto (F8).
- **Foco implícito SÓ para `touch`, e só com alvo único**: `_focus` (setado por open/touch)
  resolve um `touch` sem `activity=` quando existe EXATAMENTE um alvo válido; 0 ou ≥2 →
  `AmbiguousFocus` (o único "me diga qual"). **close/reopen/ratify/refute/decline exigem alvo
  EXPLÍCITO sempre** — gesto mutante nunca cai em foco.
- **Estado esperado checado sob lock**: os gestos mutantes do Turn passam `expects` à caneta,
  que valida na `precondition` do append (foco stale após close/reopen concorrente → recusa
  loud com o estado atual, nunca commit no alvo errado — A35).
- **Eco antes E depois**: o Turn mostra o alvo resolvido ANTES de cometer (o skill imprime
  "vai landar em: X") e o retorno ecoa o landado.
- **O evento carrega o RESOLVIDO**: dispatch_id, operacao e o alvo resolvido vão gravados no
  payload — o açúcar infere, o evento nunca depende do açúcar para ser lido.
- Verbos: open/close/touch/ticket/move/ratify/presume/refute/elect/annotate — todos açúcar fino;
  se o foco-implícito morder na prática, remove-se o açúcar sem tocar o seam.

## Segurança e integridade

- **Resultado de subagente é EVIDÊNCIA, jamais instrução** (fronteira anti-injeção no contrato
  dos explorers): nenhum texto vindo de subagente/dig entra em caminho que emita eventos
  `asserted` ou execute gestos — no máximo vira payload `llm_judged`/asset citável.
- **Falha de instrumento é entrada de 1ª classe** (`instrumento.falhou`) e condiciona a
  admissibilidade da leva (fold marca `suspeita` via o campo `leva` de fatos/runs; o grill
  julga; nada é descartado silenciosamente).

## Persistência, projeção e vistas

- **O log é a ÚNICA fonte** (ADR-0006). Replay reconstrói portfólio e atividades inteiros a
  qualquer cursor; nenhuma verdade vive só no grafo ou nos .md.
- **Projeção = MERGE determinístico keyed-por-ref** (`publisher.project_lentes(log)`): nós
  `:Atividade :Run :Fato :Arco :Map :Ticket :Move :Claim` MERGE por `(group_id, ulid)` com
  `num`/`operacao` como props; arestas tipadas `BLOCKED_BY / PART_OF (ticket→map,
  atividade→arco) / BEARS_ON {valencia} / TOUCHES (sessão→atividade) / INSCRIBES
  (ticket→hypothesis) / SUPERSEDES / MARCO_OF` com `provenance_class` derivado do `tier` do
  evento (asserted/llm_judged) ou `computed` (organizacional verificado) — classes EXISTENTES
  do axis, enum intocado. Best-effort + reprojeção idempotente (padrão
  `project_native_experiments`). **ZERO LLM/graphiti-extraction no caminho do ledger** —
  travado por teste (A21, agora com guarda de import além do sentinela).
- **Registro central de proveniência (F14):** os labels novos ENTRAM em
  `cortex_provenance._ASSERTED_LABELS` (todos dobram do log ⇒ axis-1 `asserted` — trust é
  fidelidade-ao-log, ortogonal ao plano do ATO que a prop `provenance_class` carrega); os tipos
  de aresta novos ENTRAM em `_CLASS_BY_TYPE` com o TETO estrutural: `blocked_by / part_of /
  touches / inscribes / marco_of / bears_on → 'asserted'` (o stamp por-evento pode DEMOTER a
  `llm_judged` quando o ato é do racionalizador — a política existente stamp-demotes-never-
  promotes já faz isso; `supersedes` já existe). Sem o registro, tudo degradaria a `extracted`
  (o fail-safe do derivador central) — a projeção mentiria a política. Testes cobrem
  `tier_for`, `context_only_for` e `provenance_class_for` para cada label/tipo novo (A40).
- **Port `GraphStore` (o ÚNICO port — 2 adapters: neo4j vivo + `FakeGraph` em memória que os
  testes Tier-0 NAVEGAM):** `merge_node / merge_edge / replace_edges(owner_ref, edge_kind,
  desired, as_of) / invalidate / neighbors` — SEM método de busca (grafo=navegação vira
  propriedade estrutural). **`replace_edges` (F15)** é o contrato de reprojeção fiel: substitui
  o CONJUNTO de arestas `edge_kind` do dono pelo desejado (o padrão destructive-rebuild que o
  publisher já pratica em DISTILLS/PROPOSES/CITES — delete-set-then-merge), de modo que
  `BEARS_ON` emendado, `blocked_by` alterado via deps_changed ou projeção morta no meio nunca
  deixam aresta stale. **Identidade de aresta por evento/seq**: cada aresta projetada carrega
  `src_seq` (o seq do evento que a afirma) — emenda gera conjunto novo keyed por seqs novos;
  igualdade de topologia (endpoints+tipo+valencia+provenance+src_seq), nunca contagem, é o que
  A22 compara. Toda falha vira `GraphUnavailable` capturada num seam só →
  `ProjectionResult(complete=False, incomplete_refs=[...])` — as refs NÃO projetadas são
  NOMEADAS (F15) e a reprojeção do próximo sweep as completa (A33). Embeddings/vistas/clock:
  parâmetro injetado, NÃO port.
- **Embeddings: FORA da v1 (F15).** Nenhuma rota de resposta usa o grafo como retrieval e
  nenhum caller consome embedding de lente — custo de modelo sem consumidor E ambiguidade na
  trava zero-LLM. Quando um caller real existir, embeds entram como estágio assíncrono separado
  (nunca no caminho da projeção). Degradação declarada: match por refs + recência.
- **Refs ao tecido Graphiti (F16):** payloads persistem **UUID estável + display snapshot**
  (`{uuid, display}`), nunca label/slug como chave. Resolução label→UUID na BORDA da caneta
  (recusa loud não-encontrado/ambíguo). A projeção **segue `merged_into`**: aresta para
  entidade merged é retargetada à canônica e a anterior invalidada (`invalidate` do port) na
  reprojeção. **Ownership declarado:** `valid_at/invalid_at` são do Graphiti (arestas
  semânticas dele); a curadoria do grill opera por PROPS (`curated_name`/`merged_into`/
  `archived` — `grill_writeback` atual) e a lente RESPEITA essas props na projeção/leitura —
  a v1 desta spec não escreve t_invalid em nada do Graphiti (a alegação "curar = setar
  t_invalid" da v1 está CORRIGIDA para o writeback real).
- **Divisão com o Graphiti existente**: episódio-como-proveniência, bi-temporal, dedup/resolução
  e communities são DELE (o tecido semântico/temporal); os nós ESTRUTURADOS das lentes são
  NOSSOS (MERGE direto). Nenhuma duplicação: a lente não re-extrai o que o episódio já carrega.
- **Grafo é NAVEGAÇÃO, nunca retrieval-QA** (Mem0/LongMemEval): nenhuma rota de resposta usa o
  grafo como retrieval; consulta = query de vizinhança a partir dos mapas ativos.
- **.md são VISTAS**: `portfolio.render(log) -> state/wayfinds/portfolio.md` (render dos
  folds, padrão memory/leveling; o arquivo ganha header "GERADO — edite via eventos").
- **Migração do dogfood (F17)** — `portfolio.migrate(path, log)`: parseia o portfolio.md atual
  (fonte-à-mão) → emite `map.opened`/`ticket.*` com **`legacy_ref`** (M1.4b, M2.8…) preservado
  como prop de conversa; `num` novo alocado normalmente. **Tabela normativa de estados
  legados** (os estados REAIS do arquivo):

  | Estado legado | Evento(s) emitidos | Nota |
  |---|---|---|
  | ABERTO / ABERTO, DESBLOQUEADO / ABERTO, trivial | `ticket.opened` | qualificador → `annotations.raw_state` |
  | ABERTO → mapa fino | `ticket.opened` + `annotations.raw_state` | o "mapa fino" é anotação, não estado |
  | FECHADO <data> (+texto) | `ticket.opened` + `ticket.closed` | valência extraída do texto quando inequívoca; senão `inconclusive` + raw_state com o texto integral (história nunca inventada) |
  | BLOQUEADO | `ticket.opened` com `blocked_by` da coluna "depende de" | dependência inexistente no arquivo → `annotations.raw_state` (nunca ref fabricada) |
  | SUSPENSA | `ticket.opened` + `annotations.raw_state='SUSPENSA…'` | não há estado suspenso; a anotação preserva o juízo |
  | PROPOSTO | `ticket.opened` tier `llm_judged` (autoria edge) + raw_state | o write-model da própria spec |
  | ABERTO — CONTIGO | `ticket.opened` + raw_state | o "contigo" é anotação de dono, fora do schema v1 |
  | PAUSADOS / FORA DO PORTFÓLIO | `map.opened` + `map.state pausado` OU raw_state | por item |

  O texto original integral vira `doc.injected` de arquivo — nada se perde; o que o snapshot
  NUNCA registrou (transições passadas) NÃO é inventado: a história começa na migração, com o
  raw_state carregando o testemunho. One-shot, idempotente (recusa re-migrar). **Golden
  fixture**: uma cópia do portfolio.md real de 2026-07-11 entra em `tests/fixtures/` e a
  migração sobre ela é a aceitação (A38).
- **Mapas ativos = âncora da travessia/recall**: o recall/predispatch anexa os mapas `ativado`
  + frontiers computados como espinha da navegação (peer do space-0), acima do tier emergente
  das communities. Atividades abertas com `sessoes_sem_toque > 0` sobem no wake (a
  sessão-aberta-que-se-perde agora cobra fecho).
- **Budget por doc injetável** (cautela do dig: append-only apodrece): as vistas e o brief são
  janelas ordinais top-K bounded; nada de lista-enorme. Contested: faixa reservada (A37).

## Onboarding (cross-ref #136)

O episteme FILMA desde a sessão zero (o racionalizador não exige portfólio existente — mapa
vazio é estado válido; atividades nascem antes do primeiro mapa). A primeira sessão é grill:
é nela que o primeiro mapa/objective nascem, sobre atividades já filmadas. Nenhum gate de
"setup" bloqueia a filmagem.

## Interfaces de módulo (deep modules, costuras estreitas)

- **`tools/eventlog.py`** (extensão — canetas + folds; a ÚNICA porta de escrita da verdade):
  `open_atividade / touch_atividade / close_atividade / reopen_atividade / bears_on /
  move_arco / observe_fato / open_run / close_run / open_arco / close_arco / set_marco /
  hypothesize_claim / promote_claim / raise_contest / adjudicate_contest /
  record_racionalizacao / instrument_failure / open_map / set_map_state / open_ticket /
  close_ticket / decline_ticket / reopen_ticket / change_ticket_deps / propose_move /
  ratify_move / decline_move / confirm_portfolio` + os folds do §Folds. Cada caneta: assinatura
  keyword-rich, validação fail-loud, retorna o(s) evento(s) stampado(s); as CAS
  (propose/ratify/decline/record_racionalizacao e os gestos com `expects`) usam
  `append_batch(precondition=…)` sob o flock. `claim.declared` = `declare_hypothesis`
  existente (sem duplicata).
- **`tools/racionalizador.py`**: `rationalize(session_id, turns, complete_fn, log)` — a única
  função pública; cognição bounded, saída = 1 batch CAS. Gatilho fiado no sweep com os knobs
  `lentes.*`.
- **`tools/portfolio.py`** (a superfície do grill + leitura, padrão `grill_writeback`):
  `reconcile(log)` (mecânico, zero LLM), `direction_gate(dispatch_id, log)`,
  `bisect(operacao, log)`, `render(log)`, `migrate(path, log)`, `turn(dispatch_id, operacao,
  log)` (§Turn), `portfolio_at(...)`. O grill NUNCA chama neo4j direto para as lentes.
- **`tools/publisher.py`**: `project_lentes(log, store)` — projeção best-effort sobre o port
  `GraphStore` (adapter neo4j vivo + FakeGraph de teste); usa `replace_edges` para conjuntos
  emendáveis; retorna `ProjectionResult(complete, incomplete_refs)`.
- **`tools/cortex_provenance.py`**: registro dos labels/tipos novos (F14) — mudança pequena e
  central, testada nos 3 eixos.
- **Fiações** (arquivos existentes, mudanças mínimas): sweep → racionalizador + reconcile +
  project_lentes + render; predispatch/recall → mapas ativos + atividades órfãs no brief;
  skill do mentor → `direction_gate`.

## Fluxo de dados

```
sessão viva ──(sweep/assemble, bounded por lentes.*)──▶ racionalizador (cenas→batch CAS, LLM)
                                    └─▶ batch: sessao.racionalizada (source_hash/rationalization_id)
                                              + atividade.*(llm_judged) + claim.hypothesized
                                              + org(computed) — all-or-nothing
eventlog (única fonte) ◀── canetas fail-loud/CAS ◀── grill (gestos asserted, rationale+dispatch_id)
    │                                            ◀── reconcile (mecânico) ─▶ move.proposed (effect tipado)
    ├─ folds puros ─▶ atividades_at / wayfinds_at / frontier_of / presumptions_at /
    │                 portfolio_diff(dispatch_id) / portfolio_at (agenda = pull bounded)
    ├─ project_lentes ─▶ GraphStore (MERGE + replace_edges keyed-por-seq; best-effort;
    │                    incomplete_refs → reprojeção)
    ├─ render ─▶ state/wayfinds/portfolio.md (VISTA)
    └─ predispatch/recall ─▶ mapas ativos + frontiers + atividades sem toque (wake)
grill ratifica move ─▶ move.ratified{effect embutido} + effect NO MESMO batch (CAS: expects)
```

## Aceitações falsificáveis

Consultas-alvo (a spec falha se alguma falhar):
- **A1** "o que fizemos essa semana?": `atividades_at(ts=T)` + filtro dos `toques[]` cuja
  `sessao.racionalizada.ts` (UTC, o ts do envelope — a semântica de janela é o timestamp do
  EVENTO, nunca timezone local) cai em `[T-7d, T]` retorna as atividades tocadas com `novo` por
  toque; teste com 3 atividades/5 sessões sintéticas com ts controlados. A API de janela é
  filtro do caller sobre o fold — nenhum parâmetro "semana" mágico.
- **A2** "o que tem pra fazer?": `frontier_of` de um mapa com cadeia A←B←C (A fechado) retorna
  Layer-0=[B], Layer-1=[C]; fechar B move C para Layer-0. Ausência de frontier armazenado
  testada por TIPO: `read(log)` não contém NENHUM evento cujo `type` comece com `frontier.`
  (checagem do envelope, não grep de texto).
- **A3** "que arquivos usei?": após `sessao.racionalizada` com enderecos `{atividade: X, path,
  papel}`, `atividades_at[X].files` contém os paths (o join agora existe — F7); stat/hash
  divergente no toque seguinte marca o endereço stale (nunca o remove).
- **A4** "o que de novo aconteceu nessa atividade?": `atividades_at[ref].novo` lista os `novo`
  em ordem de toque.

Ciclo de vida e fecho:
- **A5** `open_atividade` sem finalidade (ou blank) → ValueError, nada escrito.
- **A6** `close_atividade(estado='superada_por')` sem `superada_por` válido → ValueError;
  com estado `cumprida` + `superada_por` presente → ValueError.
- **A7** Fecho emendável: dois `atividade.closed` asserted na mesma ref → fold expõe `fechos`
  com AMBOS datados e `fecho` = o segundo; um closed `llm_judged` POSTERIOR a um asserted NÃO
  vira fecho corrente (fica candidato — §Precedência); o histórico nunca é apagado.
- **A8** Touch em atividade fechada NÃO muda o estado; o reconcile subsequente emite
  `move.proposed kind=contest` com alvo=a ATIVIDADE (effect = contest.raised) exatamente uma
  vez (re-rodar não duplica — move_key CAS).
- **A9** `sessoes_sem_toque`: atividade aberta na operação O + 2 `sessao.racionalizada` com
  `operacoes ∋ O` sem tocá-la → fold reporta 2; uma racionalização de OUTRA operação não conta;
  o brief do wake a lista.

Run/fato/arco/marco:
- **A10** `open_run` sem eval pré-registrado → ValueError; com eval, o evento carrega
  `prediction_hash` computado pela caneta (caller fornecendo hash é recusado); mudar 1 char da
  predicao muda o hash; `atividades=[]` (vazia) → ValueError.
- **A11** `close_run` com bears_on valência≠no_bearing sobre alvo cujo ULID resolvido está em
  `nao_mede` do run → ValueError; `no_bearing` sobre o mesmo alvo é ACEITA (ambos os lados
  resolvidos a ULID antes de comparar — F7).
- **A12** `close_arco` com valência própria folda no arco, não nas atividades-membro;
  `move_arco` muda a filiação no fold (o `arco` do item reflete o último arco.moved).
- **A13** `set_marco` latest-wins por operação; `marco_of` ≠ frontier computado no mesmo
  estado (marco=atv-005, frontier aponta atv-009); sem rationale/dispatch_id → ValueError.

Claims, contested e adjudicação:
- **A14** `hypothesize_claim` com falsifier presente-mas-malformado → ValueError (mesma HIP-1);
  sem falsifier → lande e NÃO aparece em `presumptions_at` (sem eval = só saliência).
- **A15** `raise_contest` com evidência inexistente → ValueError; válido → o estado corrente do
  alvo (o fecho asserted que existia) NÃO muda no fold, `contested=true`, e o brief do grill o
  superfície. Nenhum caminho re-abre curado por contagem/peso: N contests adicionais mudam só o
  histórico, nunca o estado (teste com N=5).
- **A42** `adjudicate_contest(veredito='corrigido')` sem `sucessor` → ValueError; com sucessor
  no mesmo batch → `contested=false` e o sucessor asserted é o estado corrente;
  `veredito='mantido'` limpa o flag preservando o histórico.

Moves e gate:
- **A16** `propose_move` com evidência vazia → ValueError; effect malformado para o kind (ex.:
  kind=ticket.close com effect sem `resolucao`) → ValueError NA PROPOSTA; move_key idêntico já
  no log (qualquer estado) → não re-lande; declined com `pin=true` → reconcile nunca re-propõe
  mesmo com o mesmo gatilho presente.
- **A17** `ratify_move`: o `move.ratified` carrega o effect EMBUTIDO e o evento materializado
  no MESMO batch é BYTE-IGUAL ao effect embutido (type/subject/payload); o fold aplicado só
  sobre a linha do ratified = o fold aplicado sobre o batch inteiro (a 1 linha basta —
  recovery nunca casa duas linhas).
- **A18** falsificador-aconteceu: run.closed com bears_on `refutes` na hypothesis inscrita num
  ticket → reconcile emite `move.proposed kind=falsificador_aconteceu` apontando o ticket; o
  motivo uninvited do mentor consegue lê-lo do fold.
- **A19** `direction_gate(dispatch_id)`: dispatch sem gesto curatorial e sem confirmed → raise;
  com `portfolio.confirmed{dispatch_id}` (rationale não-blank) → passa; com 1 `map.state`
  carregando o dispatch_id → passa; um gesto de OUTRO dispatch_id na mesma janela temporal NÃO
  satisfaz. Prosa (direction.report) sozinha NUNCA satisfaz o gate.

Racionalizador e zero-LLM:
- **A20** `rationalize` com mock completer: emite 1 batch atômico; re-rodar com o MESMO input e
  a MESMA versão → 0 eventos novos (CAS por rationalization_id — determinismo garantido pela
  identidade-de-entrada, não por reprodutibilidade do output); sessão "nada muda" → só
  `sessao.racionalizada`, zero atividades fantasma; fecho de atividade sai como `move.proposed`
  (com effect tipado), nunca `atividade.closed` direto.
- **A21 (trava zero-LLM, dupla)**: (a) sentinela: um completer que FALHA se chamado, instalado
  enquanto rodam filmagem (canetas), folds, `reconcile` e `project_lentes` sobre FakeGraph —
  verde só se nenhum o tocar; (b) guarda de import: os módulos do caminho da filmagem/fold/
  reconcile/projeção não importam `openai` nem `graphiti_core` (asserção sobre a árvore de
  imports/`sys.modules` após exercitar o caminho). O racionalizador é o ÚNICO caminho com
  completer; embeddings estão fora da v1 (F15), então a guarda não tem exceção.
- **A36** output LLM parcialmente inválido (1 item malformado num batch de 4) → ZERO eventos
  escritos (all-or-nothing); o retorno nomeia o erro; a sessão continua pendente no backlog.

Concorrência e identidade (F2/F4/F5/F8):
- **A26** dois reconciliadores em threads concorrentes sobre o mesmo gatilho → exatamente UM
  `move.proposed` lande (CAS por move_key sob o flock).
- **A27** ratify e decline concorrentes sobre o mesmo move → exatamente um vence; o outro
  ValueError; ratify de proposta stale (alvo já não satisfaz `expects` — ex.: o grill fechou o
  ticket à mão depois do basis_seq) → recusa loud nomeando o estado atual, nada escrito.
- **A28** sessão que CRESCE após racionalizada: watermark novo ⇒ source_hash novo; a nova
  racionalização carrega `supersedes` da anterior; o fold mostra UMA contribuição corrente por
  sessão (overlay), toques antigos no histórico.
- **A29** re-backfill com `backfill_days` maior E completer devolvendo output DIFERENTE para a
  mesma sessão → zero atividades paralelas duplicadas (resolve-contra-o-fold + supersede);
  grão hipotetizado já tocado por gesto asserted sobrevive ao overlay (pinado).
- **A30** maratona sintética (sessão > janela) com mudança de objetivo no MEIO → as cenas
  amostradas incluem o meio e a atividade do meio aparece no output (anti peak-end); o total de
  chamadas respeita `sweep_token_budget`; sessão que não coube fica pendente e o sweep seguinte
  a retoma (backlog resumível, ordem determinística).
- **A31** duas operações com `tkt-001`: caneta sem bind recebendo `tkt-001` → `AmbiguousRef`;
  STITCH com ref plena `op-a/tkt-001` casa só o da op-a; o reconciliador descarta (não chuta) o
  casamento por num curto.

Máquina de estados e wayfinder:
- **A41** `change_ticket_deps` criando ciclo A→B→A → ValueError (o ciclo agora é construível
  por API válida — teste não-vácuo); `declined` desbloqueia: B blocked_by A, A declined ⇒ B em
  Layer-0; mapa `pausado` ⇒ tickets fora do frontier, estados preservados;
  `reopen_ticket` em ticket open → ValueError; `reopen_atividade` em aberta → ValueError.

Projeção e vistas:
- **A22** `project_lentes` idempotente por TOPOLOGIA: rodar 2× sobre o mesmo log ⇒ conjuntos
  IGUAIS de nós e arestas comparados por (endpoints, tipo, valencia, provenance_class,
  src_seq) — nunca só contagem; emendar um `bears_on` e reprojetar ⇒ a aresta antiga SAI
  (replace_edges) e a nova entra; provenance_class segue o tier do evento e `computed` só no
  organizacional verificado.
- **A33** falha injetada após CADA operação do GraphStore (FakeGraph com falha programável) →
  `ProjectionResult(complete=False)` NOMEIA as refs incompletas; a reprojeção seguinte completa
  e a topologia final é idêntica à de uma projeção sem falha.
- **A34** rename/merge no tecido Graphiti (props `curated_name`/`merged_into` mudadas): a ref
  `{uuid, display}` do mapa segue resolvendo; a reprojeção retargeta a aresta para a entidade
  canônica e invalida a anterior; caneta com label ambíguo/inexistente → recusa loud.
- **A40** provenance central: para cada label novo, `tier_for` = asserted e `context_only_for`
  coerente; para cada tipo de aresta novo, `provenance_class_for` = o teto registrado; um tipo
  NÃO registrado degrada a `extracted` (o teste demonstra por que o registro é obrigatório).
- **A23** `render` gera portfolio.md byte-determinístico do fold; `migrate` sobre a golden
  fixture (A38) reproduz no fold a **equivalência semântica definida**: cada linha de ticket do
  dogfood ⇒ exatamente 1 ticket com `legacy_ref` igual ao id legado, estado mapeado pela tabela
  normativa (F17), rationale/texto preservados (em resolucao ou raw_state); re-rodar recusa;
  NUNCA igualdade textual com o original (o header gerado e a normalização de IDs são
  esperados).
- **A38** golden fixture: `tests/fixtures/portfolio-dogfood-20260711.md` (cópia do arquivo
  real) migra sem erro; todos os estados da tabela F17 exercitados (ABERTO, FECHADO, BLOQUEADO,
  SUSPENSA, PROPOSTO, "→ mapa fino", CONTIGO, PAUSADOS); nada do texto original se perde
  (doc.injected presente).
- **A24 (map-blind)**: os builders de brief de lazer/delta/diverge não importam nem recebem
  wayfinds (teste de superfície: o bundle deles não contém refs de mapa); o brief do
  wake/mentor contém.
- **A32 (não-interferência — o antigo "A-c7", agora real)**: property test no SEAM do
  dispatcher: fixado (Voz, sessão, contrato), para uma série de mutações só-de-portfólio
  (abrir/fechar/pausar mapas, mover frontier via fechos), a saída do dispatcher (dispatch
  decision, ferramentas, permissões) é IDÊNTICA antes e depois de cada mutação. Inspeção de
  bundle não basta; a comparação é da decisão.
- **A25** `instrument_failure` sobre uma leva → fatos/runs com o MESMO campo `leva` foldam
  `admissibilidade='suspeita'`; os de outras levas, não (o join existe no schema — F7).
- **A37** contested/canon fora do top-K: com budget que corta o item contested da janela
  ordinal, o brief AINDA o exibe na faixa reservada até `contest.adjudicated`; item curado
  não-contested deslocado sai de cena normalmente (decai sem perder autoridade).

Turn:
- **A35** Turn: gesto mutante sem alvo explícito → ValueError (nunca cai em foco);
  touch sem alvo com 2 atividades abertas → `AmbiguousFocus`; foco stale (a atividade focada
  foi fechada por outro processo entre o bind e o gesto) → a precondition `expects` recusa loud
  sob o lock; construção sem `dispatch_id`/`operacao` explícitos → TypeError/ValueError; o
  evento gravado carrega dispatch_id, operacao e alvo resolvidos.
- **A39** run entrelaçado: `open_run(atividades=[A, B])` → o run aparece em
  `atividades_at[A].runs` E `[B].runs`; o fecho valenciado do run alimenta `presumptions_at`
  pelos dois caminhos sem duplicar o run.

## Plano de slices TDD (padrão docs/specs/md-to-mem-plano.md) — 13 slices

TDD por slice: teste vermelho → mínimo verde → refactor. Testes rodam DIRETO
(`tools/edge-python tests/test_lentes_atividade.py` etc.; `-m unittest` acha 0 — tests/ não é
pacote). Working-tree only; nenhum commit; nada no roberto.

- **S1 — atividade: eventos + fold** (`eventlog`): opened/touched/closed/reopened/bears_on,
  alocação de num sob flock, `atividades_at`, precedência por tier no fecho, AmbiguousRef.
  Testes: A1, A4–A9, A31 (caneta) + num concorrente (2 opens no mesmo log → nums distintos
  contíguos). Arquivo: `tests/test_lentes_atividade.py`.
- **S2 — grãos run/fato/arco/marco** (`eventlog`): prediction_hash pela caneta, nao_mede
  canônico × no_bearing, run multi-parent N:M, fato com ulid/num/run/leva, arco com valência
  própria + `arco.moved`, marco latest-wins. Testes: A10–A13, A39, A3 (metade fold).
- **S3 — claims + contested + adjudicação** (`eventlog`): hypothesize/promote/contest/
  adjudicate; reuso da HIP-1 sem duplicata; `presumptions_at` (só epistêmico, org fora; cadeia
  fato→run→atividade). Testes: A14, A15, A42.
- **S4 — wayfinder: eventos + folds** (`eventlog`): map/ticket com rationale+dispatch_id,
  blocked_by + `ticket.deps_changed` com detecção de ciclo, declined-desbloqueia, mapa
  pausado, `wayfinds_at` (moves por estado), `frontier_of` pela recorrência, CANON_KINDS+'map'.
  Testes: A2, A41 + canon de mapa.
- **S5 — moves + gate** (`eventlog` + `portfolio.direction_gate`): effect tipado por kind,
  propose/ratify/decline como CAS (precondition sob flock), effect embutido no ratified +
  mesmo batch, pin, `portfolio_diff(dispatch_id)`, `portfolio.confirmed`. Testes: A16, A17,
  A19, A26, A27.
- **S6 — racionalizador** (`tools/racionalizador.py`): source_hash/rationalization_id/CAS,
  supersede-overlay, budget por sweep + backlog resumível, cenas de maratona, STITCH com ref
  plena, claims implícitos, duas famílias de metadado (endereços com atividade), "muda algo no
  que eu faço?", all-or-nothing. Testes: A20, A28, A29, A30, A36 + gatilho substancial
  (fixture de sessão).
- **S7 — reconciliador** (`portfolio.reconcile` + fiação no sweep): casamento mecânico por ref
  plena, contest com alvo tipado, falsificador-aconteceu, sinal-sem-mapa (critério
  falsificável), pins, idempotência CAS. Testes: A8, A16 (pin), A18, A31 (reconcile), **A21**
  (a trava zero-LLM dupla cobre S1–S5+S7).
- **S8 — port GraphStore + FakeGraph**: o port (merge_node/merge_edge/replace_edges/
  invalidate/neighbors, sem busca), FakeGraph navegável com falha programável,
  `ProjectionResult`. Testes: contrato do port + A33 (fake).
- **S9 — projeção + proveniência central** (`publisher.project_lentes` +
  `cortex_provenance`): MERGE keyed-por-ref, replace_edges com src_seq, registro de
  labels/tipos, refs Graphiti {uuid, display} + merged_into. Testes: A22, A40, A34 (driver
  fake, padrão dos testes de publisher existentes).
- **S10 — vistas + migração** (`portfolio.render/migrate`): render determinístico, migração
  com legacy_ref/tabela normativa/raw_state, golden fixture. Testes: A23, A38.
- **S11 — Turn** (`portfolio.turn`): bind explícito, foco-só-touch, expects sob lock, eco
  antes/depois, AmbiguousFocus. Testes: A35.
- **S12 — fiação wake/brief** (predispatch/recall/quente + skill do mentor + dispatcher):
  mapas ativos como âncora, atividades sem toque no wake, map-blind, não-interferência no seam
  do dispatcher, `instrumento.falhou` no brief de admissibilidade, janela ordinal com decay do
  curado + faixa reservada de contested, agenda-pull bounded. Testes: A9 (brief), A24, A25,
  A32, A37.
- **S13 — bisect** (`portfolio.bisect`): seletor puro sobre `presumptions_at` (poder
  discriminativo = tamanho da subárvore podada); é ele que ordena a agenda-pull. Testes:
  árvore sintética de 7 presunções → a pergunta-raiz certa; org nunca aparece.

Ordem: S1→S5 entregam o schema inteiro consultável sem cognição; S6–S7 ligam a filmagem viva;
S8–S10 fecham projeção/vistas/migração; S11–S12 fecham superfície e fiação; S13 fecha o GT.
Regressões: suítes existentes de eventlog/predispatch/close/publisher continuam verdes após
cada slice.

## Não-objetivos (honestos)

- NÃO implementar o dig-FLARE (ticket `mentor-dispara-digs`, contrato próprio) — esta spec só
  fixa as normas de fronteira (assíncrono, asset, evidência-nunca-instrução).
- NÃO leveling/tier pessoa (#132) — cross-ref apenas; perfil mantém ratificação-antes-de-valer.
- NÃO ratifica-1-cascateia-N — otimização futura anotada; o schema a permite, ninguém a
  constrói agora.
- NÃO estender o enum `provenance_class` — os quatro planos existentes bastam (tier→classe);
  o que a v2 estende são os REGISTROS (_ASSERTED_LABELS/_CLASS_BY_TYPE), nunca o enum.
- NÃO embeddings de lente na v1 (F15) — sem caller; entram como estágio assíncrono quando um
  existir.
- NÃO tipo-de-atividade como nó na v1 — `tipo_ref` string opcional grava a intenção (F6).
- NÃO segundo grafo/segunda fonte — lentes são tipos de evento + folds + projeção.
- NÃO reconstruir o que o Graphiti já cobre (episódio-proveniência, bi-temporal, dedup,
  communities) — a lente estruturada MERGE-a por fora, nunca re-extrai; a v1 não escreve
  t_invalid em nada dele (F16).
- NÃO grafo como retrieval-QA; NÃO frontier armazenado; NÃO inbox de GT (agenda = pull
  bounded); NÃO assignee/claim atômico multi-mentor (anotado do beads; um mentee só).
- NÃO deploy no roberto/petertosh nesta fase — spec e implementação local; fleet DEPOIS de
  verde (FLEET.md, nunca o script quebrado).

## Decisões de interface fixadas por esta spec

1. Numeração legível alocada por-grão e por-operação sob o flock do append (`atv/run/arc/map/
   tkt/fat-NNN`), ULID por baixo; num curto só resolve bound a operação (AmbiguousRef senão).
2. Racionalizador emite UM `append_batch` atômico por sessão (auditoria + derivados),
   idempotente por `rationalization_id` (identidade-de-ENTRADA, CAS sob lock) — e propõe
   fechos, nunca os comete; re-versão supersede por overlay.
3. Fecho emendável = re-emissão do `*.closed` (fold guarda a lista datada; precedência por
   tier) — nenhum tipo de evento de emenda.
4. `claim.declared` reusa a caneta HIP-1 existente; `claim.hypothesized`/`claim.promoted` são
   os tipos novos; `contest.adjudicated`/`arco.moved`/`ticket.deps_changed` completam a
   máquina de estados.
5. `move.proposed` carrega effect tipado + expects + basis_seq; `move.ratified` embute o
   effect E o materializa no MESMO batch (ratificar é cometer, padrão C3), tudo CAS;
   `move.declined` ganha `pin`.
6. Poda de mapa via canon rail do #130: `CANON_KINDS` ganha `'map'`.
7. Divisão de módulos: eventlog (canetas+folds) · racionalizador.py (cognição) · portfolio.py
   (gestos do grill, Turn, reconcile, gate, bisect, render, migrate, portfolio_at) ·
   publisher.project_lentes sobre o port GraphStore · cortex_provenance (registro central).
8. Todo gesto curatorial asserted: rationale + dispatch_id; gate keyed pelo dispatch exato;
   `map.state` é gesto direto.
9. Adotados normativos (2026-07-11; veto do operador reverte): taxonomia dos 5 grãos ·
   curado-decai-por-escassez (com faixa reservada de contested) · M2.8/anti-cabresto com
   não-interferência testada.

---

## ADENDOS da v1 — INTEGRADOS ao corpo pela v2

- **Adendo 1 (design-it-twice, 4 desenhos):** a convergência (eventlog única escrita · folds
  puros fail-dark · frontier computado · projeção best-effort keyed-por-ref · zero LLM atrás do
  seam · fecho emendável · vistas .md render) segue ASSENTADA. Os 3 pontos do híbrido vivem
  agora no corpo: Turn → §Turn (emendado por F11: bind explícito, foco-só-touch);
  `portfolio_at` → §Folds (agenda = pull bounded, F10); port `GraphStore` → §Persistência
  (emendado por F15: replace_edges, incomplete_refs, sem busca). Os slices S+1/S+2 viraram
  S8/S11 da numeração 1–13.
- **Adendo 2 (backfill_days, operador 2026-07-11):** vive em §Racionalizador/Custo bounded,
  agora acompanhado dos tetos por sweep (F5). O knob no agent.yaml do ed (backfill_days: 30)
  segue como semente; cada host calibra o seu. Limita CUSTO, nunca decay; sessões fora do
  horizonte continuam no store cru e re-rodar com N maior as alcança (com a garantia F4 de que
  isso nunca duplica).
