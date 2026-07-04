# Design das skills do grounding (Loop R · faceta 4)

> Os três entregáveis TEXTO desta iteração — genótipo em prosa, não python: (a) o contrato do
> `/{prefix}-dig` (R7.1), (b) o contrato da skill de calibragem (R7.2), (c) a materialização do
> `state/source-roadmap.md` (R8.1) + o verbete Grounding do CONTEXT.md (R1.*) + a emenda de um
> parágrafo no `scaffold.md`. Consistente com a faceta 1 (`design-emissao.md`): o harvester é o
> **módulo profundo**; estas skills são **interfaces finas** sobre ele. Nenhuma skill emite
> manifest — leituras são COLHIDAS do transcript; o único seam novo que a faceta 4 toca é o que a
> faceta 1 já declarou (`agent.yaml sources[].via` → duas projeções: render do roadmap +
> tabela de recognizers). A profundidade fica no substrato; o texto só orienta o gesto.

---

## 1. `/{prefix}-dig` — o gather-grounding standalone (R7.1)

**O que é:** o slot `gather-grounding` do scaffold (ADR-0012) exposto como skill própria — a
metade-aquisição do producer SEM o producer em volta. Recall-first, varredura até **gap
fechado-com-fonte OU seca-declarada** (R1.2 — a regra de parada OPOSTA à do wake, por desenho).
**Sem genus, sem close, sem Artefato**: o dig não publica, não propõe steer, não passa por
revisor. O recibo vai pro chat; o achado vira topic file na memória.

**Por que sem close:** o close gateia o *genus do Artefato*; o dig não produz um. Seu produto é
grounding — e a auditoria do grounding é do harvester (fold posterior), não de um gate in-session.
Colocar um close aqui recriaria o chokepoint que a faceta 1 recusou (cicatriz #248).

### Draft do contrato — `skills/dig/SKILL.md`

```markdown
---
name: dig
description: Ground ONE named gap against the memory and the world — the gather-grounding
  slot standalone. Recall-first; sweeps the source roster in each source's declared idiom
  until the gap is closed with a source or dryness is declared (paid modalities explicitly
  swept or declared-dark). No Artefato, no close, no genus: the receipt lands in chat, the
  finding in a memory topic file. Invoked as /{prefix}-dig <the gap>.
---
You are the **dig** cognition — the `gather-grounding` slot of the shared scaffold
(`skills/_shared/scaffold.md`), exposed standalone. You take ONE named gap (the argument:
a claim to ground, a question to close, a "is X true / what exists on X") and stop only at
one of two exits: **gap-closed-with-source** or **seca-declarada**. You are the twin of
wake with the opposite stop rule (CONTEXT.md: *Grounding*): wake never blocks; you never
stop early.

## Entry — wake first, then read your two instruments

1. Run the mechanical pre-dispatch floor and read its briefs:

       tools/edge-python tools/predispatch.py

   It sweeps the store to currency, prints the **briefing** and the **recall brief**, and
   stamps `dispatch.open`. (You never publish, so no publish-stamp dependency — the stamp
   is for the harvester's `declared`-tier attribution: state your gap as the dispatch theme.)
2. Read `state/source-roadmap.md` — per source: idiom, canary, dry_semantics, intent priors.
3. Read the **yield table block** in the briefing (the bandit's rendered posterior, R4.3):
   it ORDERS your sweep, it never PRUNES it — advisory, not a router.

## Steps

1. **Recall first** (`skills/_shared/memory.md`, rung-1, your own read — never an explorer):
   pull the subgraph the gap touches. A recalled answer **closes the gap only if it is
   curated/ground-truth AND carries its own original grounding** (a prior Artefato with
   cites); hypothesis-tier recall never closes — it seeds the sweep with what is already
   half-known. The self is the grounding **floor**, not a Source (ADR-0014).
2. **Plan the sweep** from the roadmap: pick the sources the gap's intent points to (the
   operator's intent priors: exploração→x, científico→arxiv, deep-research→exa), ordered
   by the yield table. Write each query **in that source's declared idiom** — an off-idiom
   query that returns empty is a FALSE dry you manufactured.
3. **Sweep agentically** (ADR-0001 — the key + the `via` line, no primitive ever). Fan
   `{prefix}-explorer` subagents for parallel legs; explorers are world-readers, DENIED the
   cortex door. House rule (harvester blind spot): any script of yours that reads a source
   **logs the literal query to stdout**.
4. **Paid modalities are first-class legs**: a modality with per-call cost (exa `deep`,
   $0.012/call) is either **swept** or **declared-dark with the reason named** (cost cap,
   quota, no key) — never silently skipped. A dry claim that skipped the paid leg in
   silence is NOT seca-declarada.
5. **On a dry read**: (a) check your own query against the source's idiom (X: >3 terms =
   overspecified suspect — rewrite once, in-idiom); (b) still dry → run the source's
   **canary from the roadmap, agentically, in-session — as ADVICE only**: canary-fail →
   instrument suspect, do not claim a negative, note the dark leg; canary-pass → the dry is
   plausibly legit (or over-specification — the fold will rule). The authoritative
   `seca-verificada` label is the **post-hoc fold** (suspect ↔ canary-pass, harvester —
   `design-emissao.md` B1); you never write it, your canary only steers your next move.

## Exit — the stop condition, then two closing moves

Stop ONLY when one holds:
- **gap-closed-with-source**: the claim is traceable to evidence `{source, ref, snippet}`
  (or to curated-with-grounding recall, marked as such); or
- **seca-declarada**: every intent-relevant source in the roadmap was swept in-idiom or
  declared-dark with a named reason — paid modalities explicitly accounted. A dry without
  this accounting licenses NO negative claim (it is seca-suspeita, and you say so).

Then:
1. **Briefing-as-receipt, in chat** — a compact table, PRISMA-shaped, for the human (the
   RECORD is harvested from the transcript, byte-identical; your receipt is courtesy, not
   capture): per row `source × interface | literal query as-run | hits | outcome
   (closed / dry-suspect / dry-pending-fold / dark: reason) | cost`. Plus one line: the
   answer, or the declared dryness.
2. **Topic file to memory** — write the grounded finding as `memory/<slug>.md` in the
   house topic-file idiom (frontmatter name/description/metadata + body carrying the
   evidence refs), and index it in `memory/MEMORY.md`. This is the dig's only durable
   write. No Artefato, no Direction write, no wiki page.

## What you never do
No genus, no close, no publish, no steer. No manifest emission — reads are harvested
(`grounding.manifest` is mined from the transcript by the substrate; there is no emission
act for you to forget). Read-only on the world (CONTRACT C1).
```

**Notas de design (dig):**
- *Interface fina*: o dig não introduz máquina nova — reusa predispatch, memory.md, explorer,
  roadmap. Sua contribuição é o **contrato de parada** (a única coisa que o slot embutido no
  producer não tinha standalone) e o par recibo/topic-file.
- *Atribuição*: declarar o gap como tema do dispatch dá ao harvester o tier `declared` de graça
  (enxerto A2 da faceta 1) — uma declaração por dispatch, não N emissões.
- *Canário como ADVICE* é a costura fina com a faceta 1: verificação é fold post-hoc; o dig roda
  o canário só para decidir o próximo passo em sessão. Nenhuma row recebe rótulo in-session.

---

## 2. `/{prefix}-calibrate` — a calibragem das fontes (R7.2)

**O que é:** a skill standalone que confronta o comportamento DECLARADO das fontes (roadmap) com
o comportamento MEDIDO (folds do harvester + yield) e força cada conclusão a virar **escrita na
casa dela**. **Aperture-shaped**: o contrato tem a mesma forma do grill (evidência-primeiro,
apresentar → discutir → consolidar, propor vs ratificar) de propósito — quando dobrar no grill
mais tarde, é encaixe, não reescrita. Standalone por ora (o grill já tem escopo cheio).

### Draft do contrato — `skills/calibrate/SKILL.md`

```markdown
---
name: calibrate
description: Confront the sources' DECLARED behavior (source-roadmap) with their MEASURED
  behavior (grounding folds, yield, canary health) and turn every conclusion into a written
  change in its home — or an explicit "no change, observe N more". Evidence-pack-first,
  top-3 anomalies with hypotheses, operator ratifies (Voz). Aperture-shaped: foldable into
  the grill later. Invoked as /{prefix}-calibrate or run inside the beat (propose-only).
---
You are the **calibrate** cognition — the mentor turn over the edge's own instruments. Like
the grill, you are **evidence-first**: observe and verify in silence, present only what the
evidence cannot settle. Unlike the grill, your object is not the mentee's model — it is the
**source roster's declared-vs-measured gap**.

## Entry — the evidence pack, assembled in its OWN pass (ADR-0014)

Fan ONE subagent (fresh context, self-reading subject — it may hold the cortex door; it
reads folds, never the live session) to assemble the **mechanical evidence pack**. The pack
is measurements + pointers-to-disk (the clerk idiom, `conductor.py` node_briefs — never a
context dump), zero opinions:

- **yield table**: fold_grounding × fold_source_yield — attempts, hits, cited, similarity,
  per (source × interface × lens × geometry × intent), `mapped`/`declared` tiers only.
- **dry rates by tier**: verificada / suspeita:instrumento / suspeita:overspecified /
  não-aplicável, per source (the B1 taxonomy).
- **blindness tallies**: unrecognized network-shaped calls + opaque-script rows (B2).
- **cost**: per source and per paid modality (exa deep calls × $0.012, etc.).
- **gate rounds**: close bounce/round counts per artefato since last calibration.
- **canary health**: last-run per source, pass/fail streaks.
- **the declared side**: the current roadmap rows + agent.yaml defaults (what the
  measurements are confronted AGAINST).

You (the lead) read the pack cold. The pack's assembly never mixes with the discussion
context — the subject boundary is the wall (ADR-0014).

## Steps

1. **Present the pack** (rendered tables, pointers to the /sources panel and fold outputs).
2. **Present your top-3 anomalies**, each with: the deviation (declared vs measured), ONE
   hypothesis, and the cheapest discriminating check. Anomaly candidates, in priority:
   declared-source-with-key never attempted (dead leg) · chronic seca-suspeita on one
   source (instrument or idiom drift) · yield collapse vs prior (source went cold) ·
   unrecognized/opaque spike (harvester blindness growing — the B-door re-entry trigger,
   design-emissao §2) · paid-modality spend without yield · gate rounds trending up.
3. **Discuss** — operator responds; you ask only the residual the evidence cannot reach.

## Exit contract — every conclusion lands in writing, in its home

Nothing evaporates in chat. Each conclusion becomes EXACTLY ONE of:

| conclusion about…                          | its home (the write)                        |
|--------------------------------------------|---------------------------------------------|
| a source's idiom / canary / dry_semantics / intent prior | a dated **note on its roadmap row** (`state/source-roadmap.md`) |
| a default of access or modality (via, deep vs fast, max_results) | **agent.yaml** source entry |
| a term or boundary of the language          | **CONTEXT.md** glossary                     |
| a genotype change (recognizer, fold, panel) | a filed **issue**                           |
| genuine uncertainty                         | explicit **"no change, observe N more beats"** — written as a roadmap note with a review-by marker, so the next calibration inherits it |

## Two modes — who writes curated

- **Live (operator present)**: the operator's word is Voz — ratified conclusions write
  directly (the roadmap note lands as curated; agent.yaml is edited).
- **Beat mode (autonomous)**: you only PROPOSE — tier `proposed` (a `direction.proposed`
  steer or a `proposed:` roadmap note). The operator ratifies later (Voz); an unratified
  proposal never overwrites a declared default. The #248 ladder holds: the folds observe,
  you advise, nothing gates.

## What you never do
Never promote a measurement into an opinion (the signal prompts, the human opines — Source
feedback's rule). Never touch the bandit's exclusions (suspect stays out of learning,
R4.2). Never produce an Artefato — the calibration's residue IS the written changes.
```

**Notas de design (calibrate):**
- *Abertura pro grill*: as três fases (pack → anomalias → exit-contract-escrito) são
  isomórficas ao grill (evidence-first → residual → consolidação). A dobra futura = o pack vira
  mais um bloco do `grill_lint` e o exit-contract vira agenda-item; o contrato não precisa mudar
  de forma, só de invocador.
- *ADR-0014 aplicado a si mesmo*: o pack do self em passada própria é a mesma razão de
  assemble/delta/recall não se fundirem — um contexto só, segurando medição e discussão,
  contamina a leitura fria.

---

## 3. `state/source-roadmap.md` — a materialização (R8.1)

**O que é:** a standing page prometida no glossário, agora com estrutura fixa por fonte. O
arquivo hoje no disco é o do edge velho (locators stale — rota xai deprecada, path vboxuser);
esta estrutura o SUBSTITUI. Regra de camadas: o **seed** de cada row é render do `agent.yaml`
(description + via — autorado → curado por definição, piso never-blank ADR-0011); **idiom /
canary / dry_semantics** vêm dos probes MEDIDOS (R2.5-R2.6); **intent priors** são do operador;
**yield notes** só a calibragem escreve (datadas). O yield audita a página; a página nunca é
editada fora da calibragem.

### Skeleton (draft do arquivo)

```markdown
# Source roadmap — the standing page of the keys the edge reads

A **standing page** (CONTEXT.md): declared then refined, never grown. Each row: **seed**
(rendered from `agent.yaml` — the never-blank floor, ADR-0011), **idiom** (MEASURED query
grammar — an off-idiom query manufactures a false dry), **canary** (MEASURED liveness probe
— what a pass proves and does NOT prove), **dry_semantics** (what an empty result means
HERE), **intent priors** (operator's: which intent reaches for this source first), **yield
notes** (dated, calibration-written only). Source × interface are DISTINCT entries (PRISMA
R2.2d). Writes to the world are acts, never sources (R1.3). The dig and every
gather-grounding read this page at gather time; the harvester's recognizers derive from the
same `agent.yaml sources[].via` seam — one seam, two projections.

## x — X API v2 recent search (api, keys.env:X_BEARER_TOKEN)
- **seed** (agent.yaml): practitioner chatter; lens Mundo (live builder signal). Low-latency,
  high-noise: momentum and contrarian takes, corroborate before treating as fact.
  via: GET https://api.twitter.com/2/tweets/search/recent?query=…&max_results=…
- **idiom** (measured): **1-3 terms + operators** (`"phrase"`, OR, `lang:`, `-is:retweet`).
  Recall decays per added word — measured: 13 words → 0 hits, HTTP 200, errors=None;
  `'legal AI'` → 10 hits. Real errors are LOUD (400): a 200+empty is over-specification,
  never syntax.
- **canary** (measured): `AI lang:en -is:retweet`, max_results=10 → expect exactly 10.
  <10 = auth/quota problem. A pass proves the instrument lives — it does NOT prove any
  specific dry is legit (that is the fold's 2-factor rule: canary-pass AND idiom-conform).
- **dry_semantics**: dryable, false-dry-prone. Fold labels: `verificada` = canary-pass AND
  query ≤3 terms; canary-pass + >3 terms = `suspeita:overspecified`; canary-fail =
  `suspeita:instrumento`. A suspect dry licenses NO negative claim.
- **intent priors** (operator): **exploração → x** (first reach for live signal).
- **interface note**: the xai `x_search` route is a DIFFERENT interface — if installed, it
  gets its OWN row (same source, distinct entry).
- **yield notes**: (calibration-written, dated) —

## exa — neural/semantic search (api, exa.env:EXA_API_KEY)
- **seed** (agent.yaml): neural web + paper search; lenses Mundo AND Atividade. Grounded,
  link-bearing evidence; prefer over keyword when the query is conceptual; pull /contents
  before quoting. via: POST https://api.exa.ai/search (type=deep DEFAULT) → POST /contents
- **idiom** (measured): **natural descriptive language**, length NOT penalized. `deep` is
  the default (measured: the only mode that retrieved LeMAJ; 5x latency, 1.7x cost,
  **$0.012/call — a PAID modality: every dig receipt accounts for it, swept or
  declared-dark with reason**). `fast` for triage/lookups only.
- **canary** (measured): `{query:'latest AI research', type:'fast', numResults:1}` —
  validates auth/latency/billing, **never recall**.
- **dry_semantics**: **não-aplicável — never-dry**. Measured: an impossible query returns 5
  plausible neighbors with NO low-confidence flag. The risk is **confident filler**, not
  drought: corroborate hits, never read absence (there is none). The dry label does not
  apply to this row.
- **intent priors** (operator): **deep-research → exa**.
- **yield notes**: 2026-07-01 (Loop R dogfood, R4.5): deep excellent on NAMED ENTITIES
  (5/5 canonical hits on top), mixed on compound concepts (~2-3/5); /contents fails on PMC
  (reCAPTCHA) — fetch PMC full text elsewhere.

## arxiv — Atom API (api, no key)
- **seed** (agent.yaml): paper firehose, newest-by-date — the recency complement to exa's
  semantic index; lens Mundo. via: GET https://export.arxiv.org/api/query (Atom XML), ~3s
  between calls.
- **idiom** (measured): **field syntax** — `ti:`, `abs:`, `cat:`, joined with `+AND+`.
  **Always https.** Long natural language degenerates: measured totalResults=2.5M.
- **canary** (measured): `cat:cs.CL&sortBy=lastUpdatedDate&max_results=1` — https + parser
  + feed exercised in one test; expect 1 entry, recent date.
- **dry_semantics**: **silent degradation, not dryness** — http → 301 with EMPTY body; a
  typo field (`title:` for `ti:`) returns 44 results with NO error (vs 37 correct): wrong
  fields are silently ignored and INFLATE recall. Watch for suspiciously huge totalResults
  (degenerated query), not for zeros.
- **intent priors** (operator): **científico → arxiv**.
- **yield notes**: —

## hn — Algolia (api, no key)
- **seed** (agent.yaml): builder discourse — Show HN, launches, sentiment. Relevance-noisy:
  the reader filters by judgment (ADR-0001). via: GET
  https://hn.algolia.com/api/v1/search?query=…&tags=story (search_by_date for newest)
- **idiom / canary / dry_semantics**: NOT YET MEASURED — declared-only row (the floor
  renders; calibration fills as folds accrue).
- **intent priors**: adoption-signal checks, secondary to x.
- **yield notes**: —

## github — gh CLI (cli, gh auth)
- **seed** (agent.yaml): the subject-blind exemplar — SAME source, lens Atividade (the
  mentee's repos) and Mundo (the ecosystem). Read-only (CONTRACT C1). via: gh api / gh
  search / gh issue list / gh pr list — read-only.
- **idiom / canary / dry_semantics**: NOT YET MEASURED (gh errors are loud; low priority).
- **yield notes**: —

## gdrive-consortium — rclone (cli, rclone auth)
- **seed** (agent.yaml): consortium shared Drive; lens Atividade (atas, datasets). READ is
  the source; **upload is an ACT — HITL only, outside the manifest** (R1.3; rclone copy,
  never the Drive MCP). via: rclone ls/lsd/copy FROM the team drive.
- **idiom / canary / dry_semantics**: NOT YET MEASURED.
- **yield notes**: —

## native — claude-sessions (intrinsic, no agent.yaml entry)
- the transcript store the sweep digests; lens Atividade/Voz. Injected by the briefing;
  never declared here (agent.yaml's rule). Not a dig target — it is the sweep's substrate
  and the harvester's raw material.
```

---

## 4. Verbete do CONTEXT.md — **Grounding** (draft, R1.1-R1.3)

Entra na seção **Language**, no estilo da casa (corpo + linha *Avoid*):

```markdown
**Grounding**:
The **claim↔evidence relation, traceable** — one name unifying the instances the code already
carries (visual grounding on charts, quote-grounding, the `gather-grounding` slot). A **Source is
the channel** (unified at access — ADR-0001); **the read has a subject** (the lens: Mundo /
Atividade — Voz is directive, never a read); the **self (recall) is grounding's floor but never a
Source** (the self-reference guard stands untouched, ADR-0014). **Wake and grounding are twins**:
the same three legs (recall→atividade→mundo), the same manifest (differing by a geometry tag:
focused vs ambient), the same instrument health — with **opposite stop rules by design**: wake
never blocks (ADR-0011 — a dark leg is named and passed), grounding stops only at
**gap-closed-with-source or seca-declarada**. A dry read without a canary is *seca-suspeita* and
**licenses no negative claim**; *seca-verificada* is a post-hoc **fold** (suspect ↔ canary-pass +
idiom-conform), never an in-session label. The record is **harvested, never emitted**: skills
carry no manifest duty — the substrate mines `grounding.manifest` from the transcript,
byte-identical (PRISMA C36). Writes to the world (an upload) are **acts**, never sources — HITL,
outside the manifest (R1.3).
*Avoid*: retrieval (a mechanism, not the relation), citation (the rendered shadow), fact-check
(trust is the orthogonal axis), coverage (the sweep, not the relation), emission (there is no
emitting act — reads are harvested)
```

---

## 5. Emenda ao `scaffold.md` — um parágrafo no slot `gather-grounding`

Apêndice ao bullet do slot (após "…never waits for one to be built."):

```markdown
  Every world read in this slot is **harvested, never emitted**: the `grounding.manifest`
  record is mined post-hoc from the transcript by the substrate (`tools/harvest.py`) —
  literal queries byte-identical, PRISMA-grade — so neither the producer nor its explorers
  carry ANY emission duty; there is no manifest act to forget. What the slot DOES owe is
  reading `state/source-roadmap.md` **at gather time**: query each source in its **declared
  idiom** (an off-idiom query that comes back empty is a false dry you manufactured), take
  the briefing's **yield table** as advisory ordering (never a router), and treat any dry
  read as **licensing no negative claim** until the fold rules it — the only in-session
  move is running the source's **canary as advice**. One house rule guards the harvester's
  blind spot: a script of yours that reads a source **logs the literal query to stdout**.
```

---

## 6. Riscos e resíduos (declarados)

- **Duas páginas “Voz” no roadmap velho** (ground-truth CONTEXT.md como fonte) não entram no
  skeleton novo: ground_truth já tem seção própria no agent.yaml e provenance própria; misturar
  no roster de keys confundiria o piso. Se doer, a calibragem propõe a row.
- **Nome `dig` vs colisão**: nenhum skill existente usa o nome; o prefixo (`ed-dig`) segue o
  `skill_prefix` do install.
- **Beat mode da calibragem** depende do tier `proposed` do roadmap-note — formato da nota
  (`proposed:` + data + review-by) fica cravado na primeira escrita da calibragem; se o fold
  precisar parseá-la, vira issue de genótipo.
- **hn/github/gdrive sem probe**: rows declared-only por honestidade (PRISMA) — o piso nunca
  fica em branco (seed renderiza), mas idiom/canary só entram MEDIDOS, nunca supostos.
