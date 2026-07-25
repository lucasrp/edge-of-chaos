# A escolha de pauta é etapa do dispatch (Módulo Pauta, Ato-1) — sai do producer, e a rotação sai do beat

A escolha do QUE produzir deixa de ser uma linha de prompt dentro do producer e vira **módulo
próprio — a Pauta** — etapa do **dispatch** (não do beat), gate de entrada simétrico ao Close na
saída: `propose(constraints) → PROPOSTA | silêncio`. **Revisa ADR-0012** (e a emenda ticket-05):
o producer não "mira o tema Worthwhile" mais — ele **recebe** a PROPOSTA e desenvolve; o cursor de
rotação deixa de alocar producer — **rotação/budget viram política de alocação DENTRO da Pauta**
(a `forma` nasce na sugestão) e o beat vira shell puro. Contrato assinado:
`docs/agencia/pauta-tabela-normativa.md` (2026-07-25).

## Status

proposed (2026-07-25 — deriva da tabela normativa assinada em sessão mentor; hipótese em teste:
`ato1-multi-setup-vs-centro`, falsificador mecânico na §6 da tabela)

Fiação (2026-07-25, mesmo dia): o dente FIADO em `_beat.dispatch_plan` (producer =
`proposta["forma"]`; pré-lançamento = plano pendente explícito) e no pós-gate
`assert_beat_produced` (artefato sem proposta viva = gap; `pauta.silencio` logado = batida
honesta). A estrada velha morreu no mesmo passe (commit-to-remove): `theme_suggest.py` fora de
`tools/` (cópia PARKED em `drafts/parked-theme-suggest/` SÓ para o braço de comparação do
§7bis da tabela; park-vs-kill é veredito do operador), cauda do predispatch removida,
`next_producer`/`_producer_for_dispatch`/`cursor.json` deletados, skills (beat/scaffold/
research) reescritos para a estrada da Pauta.

## Context

- ADR-0012 evacuou o julgamento do beat para o producer ("aim from Direction, exercised inside
  the producer"); a emenda ticket-05 trouxe a PROPOSTA como tronco do beat. Ficaram dois
  problemas medidos:
  - **A escolha era monocultura do centro.** "Mira o tema mais Worthwhile" colapsa toda batida
    no mesmo setup (report profundo aplicado ao trabalho vivo); os outros modos de valor do
    mentor (fog, operacional, tempo gasto, curiosidade, serendipidade) nunca ganham vez — o
    McDonald's da produção.
  - **A estrada default era um pool fixo + classificadores de keyword.** `theme_suggest.py`
    (`_SEED_POOL` no repo, regexes `_REDIGEST`/`_CODE_ONLY_APPLY`) viola a spec duas vezes
    (§3.3 "NUNCA pool fixo no repo"; juízo semântico nunca por substring) e roda como cauda do
    predispatch — sugestão-como-verdade, sem gate, sem pena no log.
- A alocação de producer vivia no cursor do beat (`_beat.next_producer` /
  `_producer_for_dispatch`, `state/beat/cursor.json`) — estado fora do log, cego ao tema: a
  forma era sorteada ANTES de existir pauta, quando o critério assinado é "que desenvolvimento o
  candidato precisa + que momento de leitura serve".
- ADR-0006: o log é a verdade. A Pauta não pode nascer com arquivo de estado próprio.

## Considered options

- **Manter a escolha no producer (status quo ADR-0012/ticket-05).** Rejeitado: monocultura do
  centro; a escolha não é auditável (nenhum evento), o veto do operador não tem alvo.
- **Pauta como sub-rotina do beat skill (prompt, sem módulo).** Rejeitado: juízo em prosa de
  skill não pena o log, não é testável offline, e re-solda escolha+produção no mesmo contexto.
- **Pauta como módulo do dispatch com dente no Ato-2.** Escolhido: escolha ANTES da produção,
  penada no log, gateada por abordagem, vetável; produção exige `pauta.proposta` (o dente).

## Decision

- **Módulo Pauta (Ato-1), etapa do dispatch.** Interface `propose(constraints) → PROPOSTA |
  silêncio` (`tools/pauta.py`). Autônomo: constraints vazias, o sorteio preenche. Voz: campos
  travados pelo pedido; a palavra do operador é **PROPOSTA-ok por autoridade** — contra ordem
  não há silêncio, há **seca declarada** dentro da PROPOSTA.
- **Sorteio uniforme ANTES do wake.** `{objeto, abordagem}` independentes, pesos uniformes
  (matriz da tabela §2, `ser` = coringa que desamarra o eixo). Sem blocklist de células: célula
  inviável morre em **silêncio logado**; 3 silêncios consecutivos da mesma célula no fold =
  evidência de poda (nunca a priori).
- **A escolha sai do producer** (revisa ADR-0012): o producer recebe a PROPOSTA
  (`{abordagem, objeto, forma, tema, faceta, lastro, gate_trace, delta_voz, origem, depth}`,
  meia página, pointers — sem outline: o desenvolvimento é agência do Ato-2) e sai pelo mesmo
  close compartilhado. O que o ADR-0012 mantém: o pipeline único, o close na saída, C3.
- **A rotação sai do beat.** Rotação/budget = política de alocação DENTRO da Pauta; a `forma`
  nasce na sugestão e chega ao dispatch via `proposta["forma"]`. O beat vira shell puro. Na
  fiação do dente, a estrada velha morre no mesmo commit (commit-to-remove):
  `theme_suggest.py` + sua cauda no predispatch + a alocação por cursor
  (`next_producer`/`_producer_for_dispatch`/`state/beat/cursor.json` como seletor).
- **O dente:** sem `pauta.proposta` viva no log, **não abre Ato-2** — uniforme para autônomo e
  comandado. Morde no plano do dispatch, a montante do rito 1–11 (publish/close intocados;
  mesmo shape do gate de wake do publisher, um ato antes).
- **Estado = fold do log** (ADR-0006): `pauta.proposta` / `pauta.silencio` / `pauta.veto`;
  distribuição realizada vs uniforme é o falsificador da hipótese multi-setup (§6). Nenhum
  arquivo de estado novo.
- **Juízo semântico só por completer** (`llm_routes.completer_for`): delta_voz (Voz = baseline,
  não blocklist) e os 7 gates de abordagem são checks estruturados com trace em `gate_trace`,
  AND mecânico, **Δ mente nunca dentro do gate** (é veredito do operador a posteriori, via
  `pauta.veto`). Nenhum classificador de keyword/substring.

## Consequences

- **Breadth vira estrutural de novo — mas auditável.** O ADR-0012 comprava breadth com rotação
  cega de forma; a Pauta compra com sorteio uniforme de célula + gate por abordagem, tudo
  penado: o desvio da distribuição diagnostica (veto come um pólo? grounding do modo não acha?)
  sem leitura cega.
- **O veto do operador ganha alvo e caneta** (`pauta.veto`, com razão) — realimenta a baseline
  em vez de morrer em conversa.
- **O beat encolhe** para shell: abrir dispatch → exigir proposta → despachar producer da
  `forma`. Cursor e theme_suggest são dívida de demolição da fiação (nomeada, não silenciosa).
- **Custo novo por batida:** recall da Voz + juízos de completer na shortlist A (§7 da tabela —
  medir; números do funil 12/6/2–3 são iniciais, calibrar por evidência).
- **Revisa ADR-0012** (escolha e alocação saem de producer/beat; pipeline único e close ficam).
  **Honra ADR-0006** (log-verdade), **ADR-0002** (silêncio logado, nunca espera),
  **ADR-0016-shape** (gate identity-held no dispatch), lei do risco da tabela §4 (nenhum gate
  contém "pergunta ao operador").
