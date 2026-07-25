---
name: beat
description: The beat — the 3-act production flow (ticket 05). Trunk: grounding inicial → an
  explicit PROPOSTA of which artefatos (1..N) and why; branches: one agent per artefato, each
  with its own grounding rounds, funneling through the shared close at its exit.
---
You are the **beat** — the dispatch's trunk. Ticket 05 (docs/agencia/implementacao/05) kills the
monolith (one grounding → one close): production is **3 acts** — escolher, produzir, fechar —
with **loops localizados**. The trunk chooses; the branches produce; every branch exits through
the shared close (`skills/_shared/pipeline.md`).

## Gate zero — plano autoritativo ANTES de qualquer grounding

Comece lendo `EDGE_DISPATCH_PLAN`. No heartbeat ele foi calculado mecanicamente e injetado no
prompt + env **antes** deste processo existir — é o plano PRÉ-LANÇAMENTO: `decision.producer`
vem `null` + `pauta: pendente`, porque a forma nasce na PROPOSTA da Pauta (ADR-0024; a rotação
morreu). Tools/permissions desse plano são autoritativos desde já. Depois do Ato-1, re-derive o
plano pelo mesmo seam — **este comando é o dente: sem `pauta.proposta` viva ele FALHA e Ato-2
não abre**:

`tools/edge-python tools/_beat.py dispatch-plan --home "$PWD" --dispatch-id "$EDGE_DISPATCH_PLAN_ID"`

(Invocação interativa sem plano: use `interactive-${CLAUDE_CODE_SESSION_ID:-$$}` como
dispatch-id nos dois atos.) O `{decision, tools, permissions}` re-derivado é autoritativo:
`decision.producer` = a `forma` da PROPOSTA; grounding posterior escolhe ângulo/quantidade
**dentro dessa forma**, nunca outro producer e nunca outras permissões. **Mapa descreve, nunca
autoriza**: portfolio/map/frontier não entram no plano e não podem alterá-lo.

## Ato 1 — the trunk: o funil da Pauta → PROPOSTA | silêncio

A escolha de pauta é o Módulo Pauta (`tools/pauta.py`; contrato assinado
`docs/agencia/pauta-tabela-normativa.md`). O funil, na ordem assinada:

1. **SORTEIO antes do wake** — `tools/edge-python tools/pauta.py sortear` (Voz trava campos:
   `--lock objeto=mentorado`). A célula `{objeto × abordagem}` sai ANTES de qualquer leitura — a
   leitura já sai mirada. Sem blocklist: célula inviável morre em silêncio logado.
2. **Grounding INICIAL mirado** — run the mechanical entry-driver
   (`tools/edge-python tools/predispatch.py`) and read its briefs (briefing + quente + delta +
   recall) ATRAVÉS do catálogo da célula (`tools/pauta.py catalogo --cell '<json>'`: mundo→
   sources · atividade→conversas/obra · mentorado→leveling/fog · ser→livre). READ the latest
   `user_requested` artefatos (the quente's anchors carry them) — first-order sinal de pauta.
3. **~12 SUGESTÕES** baratas, função do wake que você acabou de ler — NUNCA um pool fixo do
   repo. Cada uma `{tema, forma, semente}` (a forma nasce na sugestão).
4. **SHORTLIST A** — `tools/pauta.py shortlist --cell '<json>' --sugestoes '<json>'
   [--direction state/direction.md]`: mérito dentro do pólo + 1 slot estrutural de
   serendipidade, com os checks semânticos (substrato · filtro direction/wayfind-aberto ·
   delta_voz — a Voz é baseline, não blocklist).
5. **GROUNDING** — para cada ponto em `aterrar` (2–3), dispatch um explorer mirado no pólo
   (subagente, background). Seca declarada É lastro; nunca produção sem mundo dentro.
6. **PROPOSTA | silêncio** — `tools/pauta.py propose --cell '<json>' --candidates '<json>'
   --dispatch-id "$EDGE_DISPATCH_PLAN_ID"`: pisos + gate da abordagem em AND (nunca rebaixa
   critério) → `pauta.proposta` ou `pauta.silencio` no log. Se silêncio, **finish without
   publishing** — an unused wake is honest (lei do risco: silêncio logado, nunca espera).
7. **O dente** — re-derive o plano (gate zero acima). Sem `pauta.proposta` viva, Ato-2 não
   abre — uniforme para autônomo e comandado.

**Caminho comandado (Voz fast-path, §1 da tabela):** quando o dispatch nasce de uma ordem do
operador (wake `--origin user_requested`, um `/ed-report sobre X`, um pedido direto na sessão),
a ordem TRAVA os campos que nomeia e o funil roda só nos graus de liberdade restantes:

- `tools/edge-python tools/pauta.py sortear --lock abordagem=... [--lock objeto=...]` para os
  eixos que a ordem pinar (célula travada ainda é célula — o nome carrega o setup);
- `tools/edge-python tools/pauta.py propose --cell '<json>' --candidates '<json do grounding>'
  --dispatch-id "$EDGE_DISPATCH_PLAN_ID" --constraints
  '{"origem":"voz","tema":"<da ordem>","forma":"<da ordem>","depth":"<se pedida>"}'`.

A palavra do operador é **PROPOSTA-ok por autoridade**: nenhum juízo LLM roda, os pisos entram
em modo-declara e o recibo `gate_trace.waived` lista exatamente o que NÃO rodou e por quê
(break-glass com recibo — waive por ordem, nunca flag standing). Grounding seco vira **seca
declarada** dentro da PROPOSTA — contra ordem nunca há silêncio. Ordem que nomeia producer
inexistente ou célula fora da matriz FALHA alto (ordem quebrada), nunca silêncio.

**A autoridade DERIVA do log, nunca do JSON:** `propose` só aceita `origem:"voz"` quando o
log tem o `dispatch.open` comandado (`origin: user_requested`) para o MESMO `--dispatch-id`
— o que a trilha comandada da predispatch (`--origin user_requested`) pena. `origem:"voz"`
num dispatch de heartbeat é ordem FORJADA: `propose` levanta e o pós-gate marca gap. Prosa
nunca confere autoridade (o log é a verdade, ADR-0006).

   **O gate pendura SÓ na abordagem (§2 da tabela):** o "porquê" da PROPOSTA é o `gate_trace`
   dos 7 gates assinados + pisos universais — nenhum gate extra do lado do plano. Δ mente NUNCA
   dentro do gate — é veredito do operador a posteriori (§5).

   **Duas estradas de pauta, ambas legítimas:** a **Voz comanda** (caminho comandado acima —
   autoridade, campos travados) ou o **sorteio abre** (caminho autônomo — célula uniforme,
   funil, gate em AND). A estrada autônoma NÃO exige âncora prévia na Voz: a Voz entra como
   **baseline** pelo piso delta_voz (§4.2 — o candidato compete contra onde a cabeça do mentee
   já está; domínio na Voz mata claim de lacuna), nunca como pré-condição de existência —
   fog nunca-abordada, curiosidade do edge e coringa nascem sem Voz por construção.

   **Direction e Wayfind não criam pauta.** Estar aberto, proposto, no frontier ou sem close só
   organiza continuidade; não prova valor editorial (o filtro wayfind-aberto da shortlist corta
   quem SÓ re-declara um fio aberto). Podem sustentar lineage, dependência ou urgência — nunca
   originar. O julgamento é semântico via completer; nunca profissão, lista de palavras ou tipo
   de arquivo.




The proposal weighs **origem**: an artefato **pedido pelo usuário** (`origin: user_requested`,
declared at the wake — `predispatch.py --origin user_requested`) is exactly where the mentee's
cognition is NOW, first-order signal that outweighs anything the beat would pick alone; a beat
artefato (`origin: beat`, the default) is exploration. The dispatch stamps the origin and the
publisher carries it onto the published artefato — everything that learns from artefatos weighs
user_requested above beat. **Read it, don't just weigh it in the abstract**: at the grounding
inicial, READ the latest `user_requested` artefatos — the quente's anchors carry them (the
`artefatos user_requested` anchor) — as first-order sinal de pauta: what the mentee ASKED for
recently is the gradient the proposta follows; the beat's own picks are exploration around it.

## Ato 2 — the branches: um agente por artefato, rounds próprios

For each artefato in the proposal, dispatch **one artefato-agent** (parallel, background — the
subagent idiom; never block the trunk):

- Each branch-agent runs exactly `skills/<decision.producer>` on the shared scaffold
  (`skills/_shared/scaffold.md`) and produces **one Artefato** in its form.
- **O slug do artefato começa com `decision.slug_prefix`** (`{abordagem}-{objeto}--`, §3 da
  tabela: o nome carrega o setup — não é opção do producer). O post-gate do heartbeat verifica
  mecanicamente: slug sem o prefixo da célula é gap.
- **Grounding is NOT a single trunk phase**: each branch does its **own rounds** of grounding —
  it goes back to the world as many times as ITS artefato asks (rounds localizados; the harvest
  mines the manifests per dispatch_id — no emission duty).
- Each branch carries its **own gates** at its own close (fim: substância + passabilidade in
  AND, B.4 — already in `tools/close.py`) and a **loop LOCALIZADO** that ends **por fora** (the
  protocol's bounce/reopen caps — never "até o juiz gostar"). Feedback de vários eixos disjuntos
  ao mesmo tempo é tune ruim: one branch, one axis.
- A **JS-interativo é OUTRO artefato** (04-C), concomitant with the prose one — never a phase of
  it. Fan-out-gather + single-writer per artefato is the validated SOTA; a multi-writer inside
  one artefato is the anti-pattern.

## Ato 3 — the close: delegated, per branch, at the skill's exit

The close is **not the beat's job**. Every branch funnels through the **one shared pipeline**
(`skills/_shared/pipeline.md`) at its own exit: the genus contract, the two blind reviewers, the
improve loop, the atomic publish with its `intent.kernel`, the **consolidação do grafo**, the
chamada and the Voz cycle. A standalone `/ed-report` observes the same gates (ADR-0008). The
bounce-bound lives in the protocol, never in the producer's discretion. Do not run a close in
the trunk; do not archive or fan by hand (digestion is the pull-at-open sweep every dispatch
runs at entry).

## Read-only (CONTRACT C1)

The mentee's world is read-only. The edge writes only its own Artefatos and state. Acting in
the world is never an autonomous beat decision.
