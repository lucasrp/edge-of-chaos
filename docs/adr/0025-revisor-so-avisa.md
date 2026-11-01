# O revisor só avisa dos furos; o produtor corrige ou anota

Os artefatos passavam por várias etapas de revisão que bloqueavam a publicação ou obrigavam
nova rodada. Agora há **um revisor**, numa **passada**, **sem veto**. Ele aponta furos: fato sem
fonte, número errado, conclusão que não segue, trecho confuso, o que faltou. O produtor decide
cada furo como achar melhor: **corrige** no texto, ou **deixa** e menciona a nota numa seção curta
**"Notas do revisor"** (o furo e, se quiser, a resposta). A revisão nunca bloqueia. Revisa o
ADR-0013 (dois portões cegos que precisavam passar) e a decisão "basta" do rito
(docs/rito-runtime.md: o `final_review` fail-closed era o bilhete de publicação).

## Status

accepted (2026-11-01, decisão do dono)

## Context

O dono, em 2026-11-01 (literal): *"quero fazer um pr nele. to achando que os artefatos que ele gera
estao muito burocraticos com varias etapas de revisao. quero que o revisor só avise dos furos, e o
edge pode ou corrigir ou só mencionar a nota do revisor, à sua conveniencia"*.

Antes desta decisão havia três caminhos de saída, e todos tinham revisão que bloqueava ou forçava
rodada:

- **Rito** (report, research, discovery, map, plan, mentor): `gap_critique` → `grounding2_targeted`
  → `provisional_rewrite` → `fact_audit` → `author_correction` → dois laços Feynman obrigatórios
  (nota → lastro novo → reescrita, duas vezes) → uma revisão Feynman de fecho → `final_review` com o
  cabeçalho `ACCEPTANCE: PASS|FAIL`, que era o único bilhete de publicação (FAIL derrubava o rito).
- **Close legado** (`close.run_close`: prototype, lazer, publisher subagent): dois revisores cegos
  (feynman + regular) que **ambos** precisavam passar; laço de melhoria até 15 rodadas; bounce em
  qualquer strike; veto de passabilidade (nota < 3 em clareza/contextualização); ledger de
  descarte; meta-juiz "cosmético vs substantivo"; publish-with-residuals atrás de knob.
- **Beat** (Tetris): `review-gate.py` com duas rodadas revisão→refino, refino final automático e
  exit 1 quando a nota não passava.

## Decision

- **Um revisor, uma passada, sem veto.** O contrato vive em `tools/revisor.py` e é o mesmo nos
  três caminhos. O revisor devolve furos e nada mais (sem nota, sem placar, sem veredito).
- **O produtor decide cada furo.** No rito: `reviewer_notes` (revisor) → `author_revision` (autor:
  corrige ou anota em `## Notas do revisor`). No close: `improve_fn(artefato, verdict)` é chamado
  **uma vez**; o artefato devolvido lista em `reviewer_notes` os furos mantidos (omitir = manter
  todos, o padrão seguro); o close grava em `content["reviewer_notes"]` antes do mint (o digest
  amarra) e o render mostra a seção "Notas do revisor". No beat: `review-gate.py` faz uma passada,
  sai 0, escreve `furos` no feedback; o agente corrige no YAML ou anota.
- **Ninguém revisa a revisão.** Não há segunda rodada.
- **Revisor quebrado não bloqueia.** Resposta ilegível ou exceção vira nota `degraded` sem furos.
  Só erro de infra (quota, auth, rede) sobe, porque não é revisão (#55); o run é retomável.
- **Fica o que é mecânico e barato e protege o leitor, como checagem:** contrato de genus
  (cites com snippet, schema dos blocos, piso rich-rite, cobertura visual, piso de grounding da
  sessão; bounce limitado por `BOUNCE_MAX`), varredura de vazamento de processo, imutabilidade do
  primeiro texto, render pinado + hash no publish, token + digest + identidade do revisor no proof
  (prova que a revisão rodou, não que concordou), wake e intent kernel.
- **O grounding novo vai para antes do texto.** O rito perdeu o `grounding2_targeted`: o alcance de
  grounding novo (buscado e citado, nunca inventado) acontece ao montar o `grounding1_dossier`. Fato
  sem fonte vira furo.

## Considered options

- **Manter os portões e só afrouxar limiares.** Rejeitada: continua burocrático e continua
  bloqueando; o dono pediu que o revisor só avise.
- **Tirar a revisão.** Rejeitada: o dono quer o aviso dos furos; o revisor cego continua útil
  como segundo olhar.
- **Um revisor consultivo, o produtor decide.** Escolhida.

## Consequences

- Menos chamadas de LLM por artefato: o rito cai de 17 para 7 estágios (2 LLM de revisão/reescrita
  em vez de 13), o close faz 1 chamada de revisão em vez de até 2×15.
- O leitor vê os furos que o produtor não corrigiu, em vez de o artefato ser barrado em silêncio.
- `RITO_VERSION` muda para `artefato-revisor-avisa/v1`; run dirs antigos falham `verify_rito` por
  `schema-mismatch`, de propósito. O gate persistido (`gate=` no `artefato.published`) passa a ser
  o contrato `revisor@1` + os furos; `gate.pass` = "nenhum furo" (sinal para o yield, não bilhete).
- Custo aceito: perde-se a segunda rodada de grounding dirigido que o exp072 tinha. Se a qualidade
  cair de forma medida, a resposta é um experimento numerado, não um portão de volta.
- O contrato de genus continua bloqueante (é checagem mecânica, não revisão). O piso rich-rite e a
  cobertura visual são os candidatos óbvios se o dono quiser cortar mais.
