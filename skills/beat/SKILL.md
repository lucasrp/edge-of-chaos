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

Comece lendo `EDGE_DISPATCH_PLAN`. No heartbeat ele já foi calculado mecanicamente e injetado no
prompt + env **antes** deste processo existir. Se ausente numa invocação interativa, execute primeiro:

`tools/edge-python tools/_beat.py dispatch-plan --home "$PWD" --dispatch-id "interactive-${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-$$}}}"`

Esse `{decision, tools, permissions}` é autoritativo. `decision.producer` fixa o producer desta
batida; grounding posterior escolhe pauta/ângulo/quantidade **dentro dessa forma**, nunca outro
producer e nunca outras permissões. **Mapa descreve, nunca autoriza**: portfolio/map/frontier não
entram no plano e não podem alterá-lo.

## Ato 1 — the trunk: grounding inicial → PROPOSTA

1. **Grounding INICIAL** — the hot look: run the mechanical entry-driver
   (`tools/edge-python tools/predispatch.py`) and read its briefs (briefing + quente + delta +
   recall). On an ambient `origin: beat` wake, next run
   `tools/edge-python tools/pauta.py candidates`: this is the only topic-opening surface and contains
   exact current human turns, never Direction/Wayfind. Choose an actionable theme from those turns
   and bind it before spawning any branch:

   `tools/edge-python tools/pauta.py select --dispatch-id "$DISPATCH_ID" --theme "..." --decision "..." --voice-fragment "vf:..."`

   Repeat `--voice-fragment` only for additional direct-human anchors. If no turn contains a real
   problem, decision, doubt, criterion, or desired result that opens an artefact in the fixed form,
   **finish without publishing**; an unused wake is honest. Then do a LIGHT sweep of the world —
   enough to see what moved, not a deep dive (depth belongs to the branches, each doing its own
   rounds).
2. **PROPOSTA** — respeitando o `decision.producer` já fixado, o trunk produz uma proposta
   explícita: QUAIS artefatos (1..N) nessa forma, por que cada um vale, e qual ângulo.

   **Theme choice (operator 2026-07-24) — mandatory for beat picks:**
   - Run (or read from the wake if already printed):
     `tools/edge-python tools/theme_suggest.py --edge-home "$PWD" -n 6 --form <decision.producer>`
     (omit `--form` if the producer is not a form in the tool's choices; still run the tool).
   - Primary gate is **Δ mente / abertura / bom-para-mim**: the mentee can say
     *“eu não estava vendo X — e isso muda o jogo para mim”* **no domínio deste install**
     (mission + Direction *set* already rank the candidates). Utility for code/board is
     **optional and secondary** — never the default success criterion.
   - Prefer candidates from that list (or invent a peer that passes the same DV). Reject
     activity redigest (exp-as-title, placar, thrash, “o que se liga”, next arm) even if
     Direction is noisy with tickets. Direction **profiles domain**; it does **not** monopolize theme.
   - GraphRAG-class success is the template: a **world mechanism** that reopens what the
     operator is already doing — not a safe remapping of open bets.

   The "why" also carries the plan-side gates (B.4): **VoI > custo**, **é real**, **é pra ele**
   (except `lazer`, taste only) — and for beat origin, **Δ mente no domínio** is first among
   them. The editorial-compass is the living prototype of this gate. A rotação já foi consumida
   uma única vez pelo plano autoritativo; a cognição não a reabre nem faz queue-jump.

   **Contrato de pauta por atribuição:** a **Voz humana abre a pauta** — um problema formulado,
   uma decisão, uma dúvida, um critério ou um resultado desejado que os turnos humanos realmente
   sustentam. A execução do edge/IA, commits e outros rastros de Atividade só dizem o que mudou,
   qual risco apareceu ou o que bloqueia essa pauta. Eles não transferem ao leitor o vocabulário
   de implementação do executor. Se o humano discutiu o trade-off técnico, o detalhe técnico é
   legítimo; se apenas dirigiu a entrega, o detalhe fica como evidência da implicação no horizonte
   que ele formulou. Isso é inferido semanticamente dos papéis no diálogo — nunca por profissão,
   lista de palavras ou tipo de arquivo.

   **Direction e Wayfind não criam pauta.** Estar aberto, proposto, no frontier ou sem close só
   organiza continuidade; não prova valor editorial. Eles podem sustentar lineage, dependência ou
   urgência de uma pauta que a Voz abriu, nunca originá-la. Para cada artefato proposto, declare:
   (a) a âncora na Voz, (b) como execução/estado a suporta e (c) a **decisão utilizável pelo leitor**
   ao terminar — decidir, comparar, recalibrar um risco ou escolher um próximo movimento. Se não
   existe essa acionabilidade, o item permanece contexto e não vira artefato.

   Esse limite agora é runtime, não só instrução: um publish `origin: beat` sem `dispatch.theme`
   ancorado em `vf:*` ativo falha; no rito, o revisor final também falha se houver apenas sobreposição
   ampla de assunto e a ação/ordem/prioridade específica tiver vindo de Direction, Wayfind ou da
   execução. O julgamento é semântico; não use profissão, lista de palavras nem tipo de arquivo.

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

The mentee's world is read-only. The edge writes only its own Artefatos and state (the rotation
cursor included). Acting in the world is never an autonomous beat decision.
