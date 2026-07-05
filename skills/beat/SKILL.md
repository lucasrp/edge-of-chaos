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

## Ato 1 — the trunk: grounding inicial → PROPOSTA

1. **Grounding INICIAL** — the hot look: run the mechanical entry-driver
   (`tools/edge-python tools/predispatch.py`) and read its briefs (briefing + quente + delta +
   recall), then a LIGHT sweep of the world — enough to see what moved, not a deep dive (depth
   belongs to the branches, each doing its own rounds).
2. **PROPOSTA** — the trunk's output is an **explicit proposal**: WHICH artefatos (1..N), why
   each one is worth it, each with its own angle and form. The "why" is the plan-side gates the
   close already carries (B.4): **VoI > custo** (vale surfar?), **é real** (grounded, not
   manufactured), **é pra ele** (serves the mentee's live work — except `lazer`, which owes only
   taste). The editorial-compass is the living prototype of this gate. A report + a map + a
   JS-interativo of the same pauta is a legal proposal; so is a single brief. The rotation
   cursor (`tools/_beat.py`) survives only as a **breadth prior** — a tie-breaker when the
   proposal has no stronger reason, never a judgment.

The proposal weighs **origem**: an artefato **pedido pelo usuário** (`origin: user_requested`,
declared at the wake — `predispatch.py --origin user_requested`) is exactly where the mentee's
cognition is NOW, first-order signal that outweighs anything the beat would pick alone; a beat
artefato (`origin: beat`, the default) is exploration. The dispatch stamps the origin and the
publisher carries it onto the published artefato — everything that learns from artefatos weighs
user_requested above beat.

## Ato 2 — the branches: um agente por artefato, rounds próprios

For each artefato in the proposal, dispatch **one artefato-agent** (parallel, background — the
subagent idiom; never block the trunk):

- Each branch-agent runs its producer-skill (`skills/<producer>`) on the shared scaffold
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
