# edge — self-model (por módulo)

> A arquitetura do próprio edge, organizada pelos 9 módulos. Cada um: uma
> **responsabilidade**, uma **interface**, os **conceitos** dentro. Invariantes →
> `CONTRACT.md`; decisões → `docs/adr/`. Este documento é o edge sobre **si mesmo**,
> nunca sobre o mentee — o glossário da fala do mentee (Idiom) foi removido.
>
> **Regra das costuras:** conceito com lógica coesa própria → um **dono + interface**;
> conceito que é só sequência de atos de outros módulos → **dissolve**.

## 0. Provisão / Encarnação
**Resp:** ler a declaração e renderizar ESTE install a partir do genótipo.
**Interface:** `incarnate(agent.yaml) → Install{identity, sources, standing-pages, cortex}`

- **Genótipo:** o código cego-a-sujeito que propaga entre installs (clone → PR → merge → propagate). Carrega **nenhuma identidade** por design; o grep-gate (zero literais de identidade em `tools/`) é a conformidade.
- **Install:** uma instância viva do genótipo servindo um mentee — identidade própria (`EDGE_GROUP`), corpus, state, Direction, mesmo com substrato (grafo, host) compartilhado por `group_id`. Identidade ausente **falha alto**, nunca defaulta.
- **Declaração (`agent.yaml`):** o seed do operador — identidade, mentee, fontes + como-usar, standing directives.
- **Segredos / Env:** keys e tunables (`xai.env`, `EDGE_DEV`) — nunca no genótipo.
- **Validação:** conformidade na encarnação — identidade presente, zero literais vazados.
- Rende as standing pages **chamando** `wiki_render` (dono: Cortex); **carrega** o roster de fontes que Aquisição depois usa.

## 1. Aquisição / Lastro
**Resp:** ler qualquer fonte (self · mundo · mentee) e trazer lastro rastreável.
**Interface:** `gather(subject, key)` · `declare_dark(key, reason)` · `grounding.floor(manifest)`
**Gate:** auditor + controle-positivo — audita e loga tudo, bloqueia nada por magreza;
hard-fail só numa claim de "zero" de perna paga (x/exa) sem controle-positivo — a *seca falsa*.
Escala pra bloqueio por evidência logada, não por vibe (ADR-00XX).

- **Fontes (Source roadmap):** registro de keys; um key é locator **cego a sujeito** — a mesma fonte alimenta Mundo e/ou Atividade. Standing page, semeada no `agent.yaml`.
- **Lente de sujeito:** Mundo (campo externo) · Atividade (o que o mentee faz, observado) · Voz (o que o mentee dirige ao edge). O eixo: mundo vs observado vs dirigido.
- **Wake:** abertura — ler o self primeiro (assemble + recall) antes de puxar o mundo.
- **Delta:** o que há de novo no mundo; discricionário, orienta e não é evidência.
- **Grounding:** profundidade — descer a vertical numa fonte; a declaração de seca **é** lastro.
- **Yield (Source feedback):** relevância por fonte — não-curado (mecânico) + curado (grill).

## 2. Cortex / Memória
**Resp:** guardar e navegar o conhecimento durável do edge — a mente em que ele pensa.
**Interface:** `recall · surf · node · search` (a porta de leitura estável — #68 troca o substrato episteme atrás dela, sem tocá-la)

- **Espaço-0:** a raiz imutável — identidade do edge (método + personalidade), o genesis do grafo. Tudo que o edge sabe tem que ser alcançável dela pelo hub do Objetivo.
- **Grafo / substrato:** nós + arestas; intake → episódios/clusters (extraídos) + arestas **asserted** (Direction, curado, corpus, refs). Onde o #68 encaixa o swap.
- **Duas tiers:** **hipótese** (barato, abundante, extraído) e **curado** (consolidado pelo mentee, priorizado, isento de envelhecimento passivo). O **tier boundary** é a guarda: extração só escreve hipótese, nunca asserta curado (a falha Zep — ADR-0008).
- **llm-wiki:** o conhecimento como páginas duráveis — **Knowledge clusters** (emergentes) + **Standing pages** (declaradas: Direction, Source roadmap). São **projeções renderizadas do grafo** (ADR-0005), nunca editadas à mão. `wiki_render` é o mecanismo (dono aqui; Provisão o chama pra semear).
- **Lineage / Relate:** arestas autoradas `builds_on/supersedes/contradicts` (autor declara no publish) + `RELATES_TO` nomeado por máquina (C1 mutual-kNN + floor relativo → C2 NLI-primeiro → typer aterrado). Nunca persiste aresta de similaridade nua.
- **Provenance:** trust × autoridade — asserted (fold do log, fiel) vs extracted (Graphiti, hipótese) × context_only.
- **Projeção (`project()`):** extrai o intake pro grafo e re-renderiza wiki + Direction. (Herdou a metade-escrita do Assemble dissolvido.)
- **Usage signal:** re-rank efêmero de leitura (recência+frequência), atrás de `EDGE_CORTEX_USAGE`; **não** é self-state (o log é a verdade — ADR-0006).
- **Earmarked:** o subconjunto harm-bearing do Cortex — nós importantes o bastante pra que contradições sejam resolvidas por humano (Voz). Curado pela Curadoria (Módulo 6).

## 2-A. Pauta / Escolha (Ato-1)
**Resp:** escolher a pauta ANTES da produção — etapa do **dispatch**, gate de entrada simétrico ao Close (ADR-0024; contrato assinado: `docs/agencia/pauta-tabela-normativa.md`).
**Interface:** `propose(constraints) → PROPOSTA | silêncio` (`tools/pauta.py`)

- **Pauta:** cisão do "mirar" do producer — sorteio uniforme `{objeto × abordagem}` ANTES do wake, funil (catálogo → sugestões → shortlist A → grounding), gate da abordagem, caneta no log (`pauta.proposta`/`pauta.silencio`/`pauta.veto`, ADR-0006 — nenhum estado próprio). Rotação/budget = política de alocação AQUI (a `forma` nasce na sugestão); o beat vira shell.
- **O dente:** sem `pauta.proposta` viva não abre Ato-2 — uniforme para autônomo e comandado. Voz = PROPOSTA-ok por autoridade; contra ordem não há silêncio, há **seca declarada**.
- Verbetes plenos: seção **Pauta / Escolha (Ato-1)** no glossário abaixo.

## 3. Produção   ⟶ CONGELADO (agente vivo é dono da produção)
**Resp:** desenvolver a PROPOSTA da Pauta num contexto rico (a escolha saiu daqui — ADR-0024).
**Interface:** `produce(proposta) → draft`

- **Artefato:** o entregável de um beat — carrega Worthwhile content, existe pra **mover ou confirmar a Direction**. Transiente (esfria, é prunável); o durável vive no cluster, o steer na Direction. Nasce aqui, é julgado no 4, publicado no 5.
- **Worthwhile content:** a interseção — insight profundo de domínio **aplicado ao trabalho vivo do mentee**. Domínio sozinho é genérico; mentee sozinho é raso. **O centro tem nome:** este é o bar de UM setup (o report profundo aplicado) — desde ADR-0024 é a Pauta que escolhe o setup; Worthwhile não é mais o seletor único de pauta.
- **Producer-skill:** uma skill que rende um Artefato na sua forma — report/research/map/plan/discovery/critique. Recebe a PROPOSTA da Pauta (ADR-0024), desenvolve o tema na sua forma, sai pelo close — a escolha de pauta não vive mais aqui.
- **Rich rite (ato):** os moves cognitivos que o produtor **faz** — derivação de primeiros princípios, um "o que eu não sei" marcado, um benchmark/frame de fora, a lineage. (O Close afere; aqui se gera.)
- **Duty:** um único caminho de produção, propriedade do genus — plenitude, cobrir as facetas, nenhuma faceta dobrada, voz do pedagogo Feynman. Sem knob de profundidade. Synthesis-to-a-bite é falha do genus.

## 4. Julgamento / Close
**Resp:** gatear o genus, format-agnostic.
**Interface:** `close(draft) → gate(pass|strikes) + artefato.contract(kind)`

- **Close:** o portão fixo de saída que todo producer atravessa — review (cego: vê texto final + cites) → improve (re-produção: strike revisa o rascunho) → publish (atômico, com intent kernel). **Strikes gateiam; score é advisory.**
- **Rich rite (checagem):** os 4 moves como strikes `rich-rite:<move>`, **em qualquer lugar, nunca seção nomeada** (ADR-0013). Floor content-relativo, nunca word-count.
- **Grounding floor:** afere o piso de aquisição **chamando** `Aquisição.grounding.floor()` — não reimplementa (senão volta o vazamento de formato).
- **Intent kernel:** o "porquê" de ~3 linhas emitido no close (CONTRACT C3) — a camada pragmática que nenhum leitor frio recupera.
- Directive resolution **não** é trabalho do close compartilhado — é do grill (Módulo 6).

## 5. Publicação
**Resp:** materializar a projeção lossy-imortal do Artefato no seu kind.
**Interface:** `materialize(artefato, kind)` — **guarda o spec, nunca o SVG.**

- **Kinds / adapters:** um contexto rico → N materializações (report/PPT/notebook/PR). **Duas classes:** *deliver-to-read* (HTML/PPT/notebook, C1-safe) vs *act* (experiment/PR, cruza C1 → `acts:` / HITL). HTML = adapter #1.
- **Paleta (blocks):** spec-dict → HTML seguro (render + blocks + visuals + recipes). O bloco guarda dado+encoding; o renderer faz os pixels (SVG estático agora, reativo depois) — o que mantém a ponte estático→reativo.
- **Materializers:** publish atômico (`publisher`).
- **Dashboard / Blog:** o render adapter #2, reativo — blog + Voz rail (live-fold). Mesmo spec, dois alvos de render.
- **Voz rail:** renderizado aqui (comentários/votos por publicação) mas **de posse da Curadoria** (que resolve os directives).

## 6. Curadoria / Direção
**Resp:** o único ato de curadoria + a mira; o laço que fecha **através** do humano.
**Interface:** `grill(earmarked) → curated + orientation`

- **Grill:** o **único** ato de curadoria — toda promoção (hipótese→curado, proposed→set, shaping de cluster, opinião de fonte) acontece nele. Nenhum outro ato escreve o tier curado. Evidence-first: observa e verifica em silêncio, pergunta só o resíduo. **Duas faces:** consolida o modelo (dentro) + gera orientação (fora). **Clarifica, não resolve** — afia o caminho e enfileira o próximo Artefato, nunca produz um na sessão.
- **Lint:** detector semântico (contradição/superseded/orphan/gap); resolve só o rule-decidable, escala o resíduo por harm potential.
- **Envelhecimento (Aging):** curadoria mecânica de temperatura (L1); toca só hipótese, curado é isento; arquiva, nunca deleta.
- **Convergence:** o modelo do edge batendo com a realidade do mentee — promover o que virou verdade + aposentar o que virou falso. Precisão não é o fim; é a precondição pra orientar.
- **Direction:** a direção atual do mentee que o edge alinha. Duas tiers: **proposed** (achados do grill) e **set** (o que o mentee ratificou — Voz é dona). Standing page projetada do log.
- **Steer:** a unidade de movimento da Direction — abre/confirma/aposenta um thread. Candidato não-Voz → `proposed`; Directive Voz → direto em `set`.
- **Directive / Vote:** resolução do Voz rail — Directive (comentário order-bearing, resolvido pelo grill via `voz.resolved`) e Vote (👍/👎, o sinal de retenção importance-weighted).
- **Harm potential:** a prioridade de curadoria (ambiguidade × custo de agir errado) — decide onde gastar a atenção escassa do mentee.
- *(Idiom — o glossário da fala do mentee — **removido**. O grill é mentor estratégico, não lexicógrafo.)*

## 7. Plataforma
**Resp:** o substrato de que tudo é projeção — e o shell do ciclo.
**Interface:** `append · replay · dispatch`

- **Eventlog:** o log append-only, **a verdade** — navega o Cortex, replaya o log (ADR-0006). Un-navegável por design; toda página é projeção dele.
- **Dispatch:** qualquer invocação de skill — heartbeat, ou `/ed-report`/`/ed-grill` manual. **Todo dispatch observa os mesmos efeitos** (sweep na entrada, persistência no close); o lifecycle é do dispatch, não da skill.
- **Beat / Heartbeat:** o pulso autônomo (cron, hoje 3h) — shell puro: sem rotation state, sem juízo (ADR-0024: escolha e alocação são da Pauta; producer = `forma` da PROPOSTA). Cadência é o único dial de gasto.
- **Sequenciador de entrada:** no wake, blocking — `Aquisição.sweep()` → `Cortex.project()` → **commita o cursor só no fim** (atômico). O antigo **Assemble dissolveu** aqui (a lógica voltou pros Módulos 1 e 2); o **Consolidate** já dissolvera no ADR-0008.
- **Briefing:** a orientação apresentada a cada dispatch (Memento's tattoo) — 4 partes projetadas: Knowledge clusters (←grafo) · Direction (←log) · Recap (←corpus) · source orientation (←roster).
- **Corpus / Recap:** o corpus é o trabalho próprio do edge (fold de `artefato.published`); o Recap é sua projeção no briefing, correlacionada fresh à Atividade do mentee.
- **Medium / Meio:** os canais por onde mentee e edge se falam (Claude Code nativo = two-way mas low-tier; Voz rail = order-bearing). O pipe, não o conteúdo.
- **LLM routes:** provider-por-rota (`completer_for(route)` — chat/review = codex/gpt-5.5).

---

**Space-0**:
The Cortex's **immutable root** — the edge's identity (method + personality) committed as graph
genesis: never extracted, never aged, never curated away. Everything the edge knows must be
**reachable from it through the Objective hub** — knowledge that cannot trace back to *who the
edge is and what it is for* is disconnected by definition. The tattoos under the tattoo.
*Avoid*: config, system prompt, seed data (it is graph, not scaffolding)

**Earmarked** (the):
The **harm-bearing subset of the Cortex** — the nodes marked important enough that contradictions in them
must be **settled by a human** (Voz), not left to rot or decided by rule alone. Defined by **harm potential**,
not by category: it spans facts, **Direction**, sources, and the **Idiom**, and holds **both tiers** —
non-curated and curated. **Convergence** moves non-curated → curated within it; the **agenda** is its
harm-ranked frontier awaiting that. The rest of the **Cortex** is navigable but inert — never earmarked.
*Avoid*: salient, important (the axis is **harm**), the agenda (that is only its frontier, not the whole body)

**Knowledge cluster**:
The wiki's **emergent durable page** — a unit of knowledge (mentee or domain) that
accumulates hypothesis + curated, **grown** from reading and grilling, never declared.
The graph **proposes** clusters (Graphiti communities, algorithmic); the **grill curates**
them — directing a fact into a cluster, spawning a new one, or merging — **by harm potential**,
not exhaustively. Materializes as a **thread**: a **rendered projection** of the cluster's graph
(ADR-0005), never hand-edited. Artefatos hang off it. Not the wiki's *only* durable page — see
**Standing page**.
*Avoid*: topic, tag

**Standing page**:
A durable wiki page that is **declared then refined**, not grown — seeded from `agent.yaml`
and sharpened by the onboarding grill. Three today: **Direction**, **Idiom**, **Source
roadmap**. These are what the rebuild moves out of code/config and **into the wiki** (the
project's "replace the code with the wiki").
*Avoid*: config, settings, scaffolding

**Direction**:
The mentee's current direction the edge aligns its work to — phase, priorities, constraints,
what they are working toward now. **Two tiers, mirroring hypothesis/curated**: **proposed** —
the grill's strategic findings (the open thread, the next bet, the decision not yet made; the
**grill consolidates** these) — and **set** — what the mentee has ratified (Voz owns it, their
correction always wins). The rendered standing page shows **both tiers**; a proposed thread the
mentee ratifies is **promoted to set** (superseding it), the same promotion the grill runs on
knowledge. **Co-produced** but Voz-owned. A **standing page**, projected from the log
(ADR-0006), never hand-edited. The old `config/strategy.md`, as wiki.
*Avoid*: strategy, plan, goals, alignment (collides with Convergence)

**Steer**:
The **unit of Direction movement** — open a new thread, confirm or challenge an existing one, or
retire one. **Tier by origin** (the normative split — SURFACE.md event schema): a **non-Voz
candidate** — an **Artefato**'s end-of-run candidate, or a **grill** finding — lands in the
**`proposed`** tier; a **Direct Voz** Directive that folds to Direction lands **straight in `set`**
(curated, carrying `origin_comment_id` — Voz is already authority, never routed through `proposed`).
A standing `proposed` item the mentee later **ratifies** is separately **promoted to `set`** (the
same promotion the grill runs on knowledge). A steer is **addressable** — cited, confirmed,
contested — which makes Direction two-tier rather than a wishlist. Likewise **retiring a `set` is
Voz-only** (`direction.dropped` carrying `origin_comment_id`); a non-Voz steer can only *propose* the
retirement.
*Avoid*: achado (translated — use finding), suggestion, recommendation, todo

**Idiom**:
The mentee's own language — their terms and meanings, kept so the edge frames work in their
words. A **standing page**, the **Voz** glossary. The old `memory/operator-idiom.md`, as wiki.
*Avoid*: jargon, terminology

**Source roadmap**:
The registry of **keys** the edge reads — a **standing page**. A **key is a locator, blind to subject**:
the **same source can feed Mundo and/or Atividade** (GitHub as the mentee's repo = Atividade; GitHub as
the ecosystem = Mundo) — **many-to-many**, the subject is a **lens on the read, not a property of the
source**. Sources therefore unify on **access** (give the key, read agentically — ADR-0001) and on
**relevance** (one **Source feedback**, spanning both). What does **not** unify is the **subject**: it
rides as a **tag on the yield** (world vs mentee), because **Worthwhile content = Mundo ∩ Atividade** needs
it. **Seeded by the operator's declaration** — each source **and how to use it** (access note + standing
directives, e.g. *"on wake, check the Drive for a new transcript"*) — authored → **curated by definition**,
so the roster renders as the **never-blank floor** of the briefing's source orientation (ADR-0011). The old source bindings, as wiki.
*Avoid*: config, bindings, feeds, per-source primitive (a key is a locator, not a leg)

**Convergence**:
The edge's model (wiki + mentee glossary) matching the mentee's reality. The loop closes
when Lint exposes the error and the mentee resolves it. **Two-way**: converging means both
**promoting** what is now true and **retiring** what is now false — a grill that follows a
strategic realignment (a `Direction` change) has a wide blast radius and can be **net-subtractive**.
Accuracy is **not the end**: the edge converges so it can **orient the mentee** — a precise model
is the precondition for worthwhile mentorship, not a goal in itself.
*Avoid*: sync, alignment

**Genotype**:
The shared, **subject-blind** code that propagates across installs (clone → PR → merge →
propagate). Carries **no identity by design** — no install's name, group, or key may live in it;
identity arrives only at install-time. The grep-gate (zero install-identity literals in `tools/`)
is its conformance check.
*Avoid*: the repo, the codebase, template (it is alive and propagating, not a starting point)

**Install**:
One living instance of the genotype serving one mentee — its own **identity** (`EDGE_GROUP`),
corpus, state, and Direction, even when the substrate (graph, host) is shared and split by
`group_id`. Three today: ed, petertosh, roberto. Absent identity **fails loud**, never defaults —
an install that has not declared who it is must not write as anyone.
*Avoid*: instance, deployment, clone (the act, not the thing), agent (overloaded)

## Knowledge intake / Entrada de conhecimento

> Three legs feed the llm-wiki. Named by the **subject** the knowledge comes from, not
> by the mechanic. The axis that separates them: **world vs observed vs directed**.

**Mundo / World**:
The external field the edge pulls from (arXiv, HN, EXA, Twitter). Unverified claims about
the world — pass the adversarial judge before they compose into the wiki.
*Avoid*: coleta, source, busca

**Atividade / Activity**:
What the mentee **does** — code, commits, docs, transcripts, whatever they leave. **Observed,
not directed**: it shows what the mentee actually does, not something said to the edge. The
mentee need not even work in Claude Code. Yields `hypothesis` about domain and intent. The
reborn `signals` leg, scoped to the mentee. *(Lens-grain sense: an **Atividade** node/event is a
**mentee employment** unit — often produced by **Mineração** from sessions, not agent-runtime
meta.)* **Expanded use of the episteme:** Atividade is the broad employment case (finalidade +
lifecycle + toques). A **proper subset** is **experimental** — see **Experiment** — still an
Atividade, but under a provenance rite and eval, managed by **`/ed-experiment`** (not by film
alone). Ordinary employment Atividades need not be experiments.
*Avoid*: obra, work, rastro, trace, ingest, signals, operator pressure, agent loop, subagent job

**Experiment / Experimento**:
An **Atividade** (subset, not a sibling free-floating default) that (1) follows a **specific
provenance rite** — chains prior experiments/claims (qualifies / refutes / supersedes /
pré-registro before outcome) and (2) **produces an eval** (may be biased; still an eval). The
experiment **generates knowledge** (claims, bearings, curated reading), not only “job done.”
**Managed by `/ed-experiment`** (`skills/experiment/SKILL.md`): hypothesis, arms, runs, eval,
observations, bearings, curated-first cortex reads, close via `/report` → `experiment.curated`.
Film/Mineração may open a plain employment Atividade; **promoting or running it as experiment is
the experiment skill’s contract**, not the racionalizador’s.
**Entry freeze (operator 2026-07-13):** mint/run only when the **user determines** via
`/ed-experiment` **directly or indirectly** (accepts mentor experiment-mode). No auto-promote of
smokes, draft lab trees, or “has eval ⇒ experiment” — deferred.
**Disk genotype:** `experiments/<expNNN>-<slug>/` under `edge_home` (see `experiments/README.md`,
`tools/experiments_cfg.py`); phenotype may override `agent.yaml experiments.root` (Roberto’s
pre-episteme `writing/exp*` is override debt until migration). Ledger id remains `expNNN`.
*Avoid*: every Atividade is an experiment, experiment without eval, silent overwrite of prior
experiments, agent-meta “adversarial review” as experiment, second hardcoded experiment tree
outside genotype resolution, auto-declare smoke/canary/draft-exp without user skill determination

**Mineração / Mining**:
The a-posteriori pipeline that turns **operator session stores** (Claude Code, Codex, Grok) into
**durable ledger (and graph) product** — never a live re-read of raw JSONL at assemble time.
Pre-process: **dialogue only** (user↔assistant prose — the Claude Code “conversation without
terminals” filter; tools/terminals dropped) and **operator-facing sessions only** (no sidechain /
subagent / worker-launch). Then film/rationalize and related pens write the log; **Atividade**
opens only for **mentee employment**, not mentor/agent tooling. **Assemble, briefing, and wake
consume what mining produced** (folds / portfolio / cortex projections) — they do **not** open
session files to “see what happened.”
*Avoid*: assemble-reads-sessions, live transcript dump into briefing, agent-meta as employment

**Voz / Voice**:
What the mentee **directs** at the edge — correction and language. **Directed, not
observed**: authored and highest priority ("a correção sempre ganha"). Subsumes language
(Idiom) and correction. Keeps the mentee glossary. **Two tiers, set by the Medium it arrives
through** — both authored voice, differing in **operational** weight, not in whose word wins:
**gathered** (low-tier mediums — including the native Claude Code session; a *guide* on the
mentee's current mind) and **direct** (an **order-bearing** Medium; a **Directive** the edge is
bound to address).
*Avoid*: operator pressure, feedback, pressão

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

**Directive**:
The **direct tier of Voz** — a mentee comment on the **Voz rail** (a two-way, order-bearing Medium
addressed to the edge — never the ambient Claude Code session), meant to be acted on. **A strong
guide, not a real-time order** (ADR-0017): it carries Voz's authority but is **resolved by the
grill**, not by preempting live work — every *open* chat is **earmarked** so the grill loads a
**harm-ranked batch** (within a chats/tokens cap) of the start-cursor eligible set, **asks the
residual only where ambiguous**, and **closes each chat in that loaded batch** — terminal
`voz.resolved` (one per `comment_id`) or, when it asked and got no answer, a non-terminal
`voz.clarify` that keeps the chat open — folding the standing-worthy ones into **Direction**.
*Closing* is exhaustive over the **loaded batch** (every loaded chat terminal-or-parked; overflow
carried to the next grill); *asking* is non-exhaustive. Its frictionless, answer-less sibling is a **Vote**. May
*produce* a **Steer**, but is not one.
*Avoid*: order (it guides; it does not preempt — the real-time path is deferred), command, message,
steer (a Direction-movement unit, not the instruction itself)

**Vote**:
The **frictionless, answer-less** tier of the Voz rail — 👍/👎 on a publication (`voz.vote {slug,
value: ±1}`). The **importance-weighted retention signal**: an artefato that is voted or commented
reinforces (persists); one left untouched cools and is pruned. Owes **no reply** (unlike a
**Directive**); always targets a publication.
*Avoid*: like, star-score, rating (it feeds retention, not a vanity metric)

**Briefing**:
The orientation presented to the agent at **every dispatch** (and `/load`) — **Memento's tattoo**. The
protagonist of *Memento* has anterograde amnesia, so he tattoos the load-bearing facts onto his skin and
trusts nothing that isn't inscribed. The briefing is that tattoo for a zero-memory agent: it must carry
**everything** needed to orient and hold continuity, because the agent acts on nothing it cannot read here.
Three **projections** (ADR-0006/0009) — **Knowledge clusters** (← graph), **Direction** (← log), and the
**Recap** (← corpus) — plus the **source orientation**: the **declared roster** (← Source roadmap — the
sources and what each does) as the **floor (never blank)**, with **Source feedback** layered on as it
accrues. Composed by **Assemble** at compose-time;
**supersedes the old "state digest."** The load-bearing lines (the curated Direction, what is open / the
next bet, the source yield) are **deterministically inscribed from the log** — never left to the LLM to
remember; only the Recap is synthesized fresh. Tier-0 composes from the log alone (clusters degrade where
there is no graph).
*Avoid*: state digest, dump, context (the briefing is curated orientation, not a raw dump)

**Corpus**:
The collection of **content the agent itself created** — its published Artefatos (a fold of the log's
`artefato.published` events). The edge's **own** body of work, the **reflexive** complement to the
three legs: Mundo/Atividade/Voz are about the mentee and the world; the corpus is the **edge's own
steps**. Per-install (each install's own work, isolated). Autonomous beats are excluded from the
Atividade sweep precisely because their output lands **here** instead. It feeds the briefing's third
part (the agent's last steps, related to the mentee's Atividade).
*Avoid*: obra, output, log (the corpus is the created content, not the raw event log)

**Recap**:
The **projection of the corpus** shown as the briefing's third part — the agent's recent steps and
their *why*, correlated at compose-time to the mentee's current **Atividade**. A **projection**
(ADR-0006), not a stored doc: the corpus↔Atividade relation is **synthesized fresh each load**
(orientation must be current, never frozen at publish-time; the Artefato's stored `cites`/`distills`
are provenance, not the relation). PT gloss: *informativo / relatório*.
*Avoid*: report (the Artefato / `ed-report` skill), digest (the rolling chat-digest), bulletin

**Source feedback**:
A **two-tier** relevance signal over the sources that fed an Artefato — **Mundo** (exa/X/HN/arXiv) **and
Atividade** (GitHub commits/PRs, docs), e.g. *"this commit was relevant to this report"*. It takes the
edge's **universal non-curated→curated shape** (cf. Knowledge clusters, Direction; the non-curated tier wears a per-object flavor — Knowledge mines *hypotheses*, Direction *proposes*, Source *observes usage*, a measurement not a guess) — one curation act (the
grill) governs all three:

- **non-curated tier — mechanical, no agent/mentee load**: a **projection of how the agent actually used each source**, refreshed as evidence accrues — intrinsic citation
(the agent names each source **and the snippet it used** as it writes a cited Artefato) + **embedding
attribution** (cosine of each cited snippet vs the Artefato body — cheap, `RetrievalFeedbackSignal`-style,
one OpenAI embedding call) + **outcome credit** (Voz ratification of a `proposes` / engagement, propagated
back through `cites`, MemQ-style). **Observed, not guessed; never agent self-rating.**
**Stored as `source.signal` events in the Tier-0 log** (the *score*, not vectors — no separate DB, no
vector store) and projected into the graph; the **grill consults it via `grill_lint`** (per-source yield →
a non-curated agenda item). **Never used alone** — fused with the mentee's voiced opinion in the curated tier.
- **curated tier — the grill distills the mentee's opinion**: *"the mentee values X in reports because of
Y."* Voz-grounded and reasoned; **outranks the non-curated signal** (the roadmap is the floor, not a re-rank target); exempt from
passive aging, retirable only by Voz. The grill does **not** promote the signal — a measurement cannot
become an opinion — it writes a **separate** opinion the signal *prompts*, **seeded by the operator's
`agent.yaml`** (which sources *and how to use* each: access note + standing directives — authored →
curated, the never-blank floor). It works **two-way** (Convergence): it consolidates new opinion **and
confronts standing curated against the accruing usage data** — a source good at first may have gone cold;
when the data contradicts it the grill flags `contested` for the mentee to retire or reaffirm.
This closes the artifact→human-outcome credit the 2026 survey (AgentOS `RetrievalFeedbackSignal` —
mechanical but overlap-proxy; MemQ Q-value over the provenance DAG) found **unbuilt** — outcome-grounded.
*Avoid*: rating, star-score, self-scoring (the non-curated tier is mechanical; judgment lives in the curated tier)

**Delta**:
The **orientation of what's new in the world** the edge ingests (Mundo / Atividade) — a **noun**, the
yield of the agent **updating itself** (the act stays a lowercase verb; the Idiom names the thing, not the
act). **Discretionary, not deterministic**: the edge does **not** "grab everything since the last
consolidation" — the consolidation point is a **reference horizon** (it knows where it last looked), **not
a mandate to exhaust**; within it the agent uses judgment about what is worth surfacing (agentic, never a
per-source primitive — ADR-0001). **The deterministic completeness floor is the sweep** (cursor-guarded, in
**Assemble**), **not the delta** — the world was never exhaustible anyway. **Over the world, never over the
wiki**: the edge's own knowledge is navigated in full (the **Cortex**), not deltized — only the world is.
Its role is **orientation, not evidence**: light, it points; **research deepens later**, reading the actual
documents directly (incl. old ones), unbounded by it. **On-demand, not a precondition**: it is **not** a
mandatory beat-open fan-out — the agent **wakes to itself first** (**Waking**: briefing + Cortex) and pulls
the world **only when it judges it needs to**; the beat works from the **wiki** alone when nothing is
pulled. It enriches a beat; it never gates one.
*Avoid*: changeset, watermark, cursor (not a git diff; do not deltize the wiki; it orients, research
deepens; it does not gate the beat), the act of updating (Delta is the yield; "update" is the verb)

## Curation / Curadoria

> Two **orthogonal, unmerged** processes move pages between strata (L1/L2 split, like the
> digest). They act on two orthogonal axes: **tier** (hypothesis vs curated) and
> **temperature** (hot/cold/archived).

**Envelhecimento / Aging**:
Mechanical curation (L1, every beat) on the **temperature** axis. Two signals feed it.
**Consumption** (steady-state): the wiki offers the whole list each beat, the edge pulls only
what it needs, and that reach keeps a page hot; offered-but-unconsumed cools, then archives, and
a cold page pulled back re-warms. **Reinforcement-recency** (cold-start, from provenance): when no
new episode has touched a page — it catches the *valid-but-abandoned* that a contradiction never
invalidates and consumption cannot see before beats accrue. Touches only the **hypothesis** tier;
curated is exempt. **Archives, never deletes** (raw stays non-lossy).
*Avoid*: decay, ttl, eviction

**Lint**:
Semantic curation (L2, LLM, periodic): detects contradiction / superseded / orphan / gap.
**Resolves only the rule-decidable** (`curado > hipótese`, recency) and **escalates the
residual to Voz** by harm potential. Detects; the rule or the mentee resolves — never by
judgment in code. The detector half of `Convergence`.
*Avoid*: validator, linter, cleanup

**Grill**:
The edge's **sole curation act** — the live mentor turn where **every promotion happens**:
hypothesis→curated, `proposed`→`set`, cluster shaping, source-opinion distillation. No other act
may write the curated tier. **Evidence-first**: observe and verify in silence, ask only the
residual the evidence cannot reach; prioritized by **harm potential**, never exhaustive.
**Two-faced by design**: inward it consolidates the model (the resolver half of `Convergence`,
to Lint's detector half); outward it **generates orientation** from that accuracy. It clarifies
rather than resolves — it sharpens the path and **queues the next Artefato, never produces one
in-session**.
*Avoid*: review, interview, approval, consolidation (one of its faces, not the whole)

## Beat lifecycle / Ciclo do beat

> A **dispatch** runs as cognitions in fresh contexts (ADR-0004), inside the single dispatch
> (ADR-0003). The beat is a **pure round-robin scheduler** over the producer-skills (ADR-0012) —
> judgment was evacuated from the loop into the **producer**, and every producer funnels through
> **one shared pipeline** whose **close** gates the genus. Named so each stays faithful to one
> task without competing for the main window.

**Dispatch**:
Any ed-skill invocation — the heartbeat's `/ed-beat`, or a manual `/ed-report`, `/ed-grill`, etc.
run in a live session. `**/ed-beat` is just a shell**: it holds no privileged lifecycle. **Every
dispatch observes the same effects** — the digestion sweep at entry (**Assemble**) and persistence
at close — so a **manual `/ed-report` dispatch leaves the same durable residue as the heartbeat
beat**; they differ only in the cognition wrapped (a full judgment loop vs a single Artefato),
never in the lifecycle around it. The lifecycle belongs to the **dispatch**, not to the beat skill.
*Avoid*: beat (it is one shell, not the lifecycle), run, invocation

**Beat / Heartbeat** *(synonyms)*:
The edge's **autonomous pulse** — the cron-fired dispatch (today every 3h), now a **pure shell**
(ADR-0024 revising ADR-0012): it opens the dispatch, requires the Pauta's `pauta.proposta` (**the
dente** — no proposal, no Ato-2) and dispatches the producer named by `proposta["forma"]`. It
carries **no rotation state and no judgment**: breadth comes from the Pauta's uniform cell draw,
aim from the abordagem gates — both penned in the log, never a cursor. Its **cadence is the
edge's only spend dial**: cost is tuned by frequency, never by depth — a beat is always
full-depth (plumbing + rich rite are a floor, not a dial).
*Avoid*: judgment loop (the old ADR-0004 shape — superseded), round-robin scheduler (the
ADR-0012 shape — rotation left for the Pauta), lifecycle (that belongs to the dispatch), cron
(the mechanism, not the concept)

**Wake**:
Coming online **under command** — the beat's open without its act. Fan the **three briefs**
(**assemble** in its `/load` aperture + **delta** + **recall**, ADR-0014), render the orientation,
then **halt**: read-only, no Artefato, no state written; the next move is the operator's word. The
briefs are the three views: **assemble** the curated self-state, **delta** the world's new,
**recall** the Cortex's salient — the edge wakes *to itself first* and navigates deeper on demand.
Distinct from the autonomous beat, which opens identically and then acts.
*Avoid*: boot, resume, load (the trigger, not the mode), beat-without-artefato (the halt is the
contract, not a missing step)

**Producer-skill / Producer**:
A skill that yields **one Artefato in its form** — the roster today: `report`, `research`, `map`,
`plan`, `discovery`. The producer **receives the Pauta's PROPOSTA** (ADR-0024) — tema, faceta,
lastro-that-seeds-the-gather — develops it in its form, and exits through the shared pipeline's
**close**. Production lives here; **theme-choice lives in the Pauta (Ato-1)**, never here and
never in the beat.
*Avoid*: generator, template, cognition (every subagent is one; this is the Artefato-yielding kind)

**Assemble / Consolidação prévia**:
**Operator (mentor 2026-07-13):** Assemble is what makes Edge **ready for wake** — the **cortex
state update**, including **heavy consolidation**. Conscious tradeoff: **quality over latency**
(not a light briefing-only tattoo). **Relational curation / durable package / pending drain are
blocking for wake** — not deferred to background after open. **`assembly_pending` / readiness bits
are log events and folds only** (operator: *the log is always the sole source of truth* —
ADR-0006; graph is projection). Skill path today still centers briefing + pull-at-open sweep;
the product bar is fuller readiness — see 01a and `state/wayfinds/operator-specs-30d-audit.md` S30.A*.
**Pending queue (log-truth):** open assembly work folds only from ledger events
`assembly.pending` / `assembly.done` / `assembly.failed`; **predispatch** calls
`assemble_ready.assert_ready` before stamp (fails closed — `tools/assemble_ready.py`, tkt-002).
The opening primitive (**blocking**) that orients the agent from **already-mined durable state**
(briefing / folds / projections — the products of **Mineração** and related pens), not by
re-parsing live session JSONL for employment. It also runs the **digestion sweep to currency** —
an idempotent, cursor-guarded pass over the **transcript store** (every operator session since the
cursor, *not just beats*) that runs the **full pipeline**: append raw episodes → distil handoffs →
run **zep/Graphiti extraction** (incremental, on the delta) → **re-project** the wiki and
**Direction**. So at every dispatch entry the **non-curated (hypothesis / `proposed`) tier is
current — ambiguous and `contested` items included** (flagged, not hidden). It **defers only
Voz/prescription** to the **mentor**: promotion (hypothesis→curated, `proposed`→`set`) and cleanup of the
ambiguous. **The Zep-failure guard is the tier boundary**: extraction only ever writes the
**non-curated** tier, never asserts a vent as a curated decision. Then it hands the loop a **state
digest**. **Keyed on the store, not on any skill**: a session that ran no ed skill is still brought
current at the next trigger. **Triggers** (same idempotent sweep, pluggable): the heartbeat
dispatch, **any standalone ed skill at entry**, and `/load`. The loop blocks until it lands.
*Avoid*: load (the trigger, not the primitive), context-gather, preflight, “assemble opens ~/.claude”,
treating Assemble as briefing-only when wake readiness still requires cortex currency

**Consolidate / Consolidação posterior** *(dissolved — ADR-0008)*:
The old closing subagent is **absorbed**: *archive raw* → the pull-at-open **digestion sweep**
(Assemble); *fan/curate the pages* → the **grill** (Hypothesis consolidation); *the handoff
document* → gone (durable delta = the swept log; strategy = **Direction**). No async close step,
no `consolidate→assemble` race. The only close-time act is the thin **intent kernel** breadcrumb,
by whoever lived the session. The word **consolidate** now means only **Hypothesis consolidation**
(the grill's curation), never a lifecycle close.
*Avoid*: postflight, save, the 1905-line consolidate-state, posterior close subagent

**Close**:
The **fixed exit gate of the shared pipeline** every producer funnels through — review (blind:
the gates see the final text + cites only, and check each **property anywhere, never a named
section** — ADR-0013) → improve (wired **re-production**: a strike revises the draft rather than
dead-ending it) → publish (atomic, with the **intent kernel**). **Strikes gate; the weighted
score is advisory.** Directive resolution is **not** the shared close's job: open Directives are
resolved by the **grill** close, which writes an explicit `voz.resolved` outcome per Directive
(ADR-0017) — other producers' closes leave the rail untouched (one lifecycle owner, one `voz.resolved`
gate). Runs at every producer's exit — round-robin is for
the producers; the close is the gate they share.
*Avoid*: postflight, consolidate (dissolved — ADR-0008), review (one stage of it)

**Rich rite / Rito rico**:
The genus floor on the **cognitive moves**: a developed Artefato must show — **anywhere** in the
text, never as named sections — a **derivation from first principles**, a marked **"what I don't
know"**, an **outside benchmark/frame**, and the **lineage**. The moves *generate* richness;
length and figures are its shadow — so the floor is **content-relative, never a word-count**.
Enforced in the close's genus check as `rich-rite:<move>` strikes, with re-production wired so a
shallow draft is deepened, not rejected. The worthwhile-test has this floor: quality cannot be
judged below working plumbing + a rich rite.
*Avoid*: word-count floor, template, section mandate, completeness checklist

**Briefing**:
The composite orientation the edge **presents to the agent every time it is loaded to act** (at
dispatch start, and on `/load`). A **collection of information**, in four parts:

1. the **Knowledge clusters** — what the edge knows;
2. the **Direction** — the strategic steer (both tiers);
3. the **Recap** (PT: *informativo*) — **a projection of the corpus**: the agent's **own last steps**,
  what it did and why, correlated at compose-time to **how it relates to the mentee's Atividade**.
4. the **source orientation** — the **declared roster** of sources (← Source roadmap), **never blank**,
  with **Source feedback** layered on as it accrues.

Composed from projections (clusters ← graph · Direction ← log · Recap ← corpus · sources ← Source roadmap)
— the *oriented* read,
not raw state. It is what
`assemble` hands the loop. The old `State digest` / `briefing.md`, now first-class. Distinct from the
**handoff** (the raw intent-kernel breadcrumb): the briefing is the composed orientation; the handoff
is one pragmatic input to it.
*Avoid*: state digest (the old mechanical name — retired), dump, context pack

**Intent kernel**:
The agent's **intent** — ~3 lines: what is open, the next bet, the *why* behind the work — the
**pragmatic layer no cold reader recovers**. **Mandatory metadata on edge work** (CONTRACT C3): every
dispatch that produces an Artefato emits an `**intent.kernel` event** at close — edge work without its
intent is incomplete. It is the durable **why** the **corpus** carries and the **Recap** projects.
Written by whoever lived the session (the loop, or live grilling). (A no-skill *chat* — not edge work —
leaves none; the sweep captures its raw and the grill picks it up.) The tier boundary, not the kernel,
is what stops a vent becoming a curated decision (ADR-0008, the Zep failure).
*Avoid*: summary, notes, handoff (that is the digested delta, not the kernel)

## Pauta / Escolha (Ato-1)

> Contrato assinado: `docs/agencia/pauta-tabela-normativa.md` (2026-07-25) · ADR-0024 ·
> `tools/pauta.py`. A escolha de pauta ANTES da produção — etapa do dispatch, gate de entrada
> simétrico ao Close. Estado = fold de `pauta.proposta`/`pauta.silencio`/`pauta.veto` (ADR-0006).

**Pauta**:
O módulo da **escolha** — `propose(constraints) → PROPOSTA | silêncio`. Sorteia
`{objeto × abordagem}` uniforme **antes de ler o wake** (a leitura sai mirada), roda o funil
(catálogo da célula → ~12 sugestões baratas → shortlist A → 2–3 aterrados) e julga no gate da
abordagem — AND mecânico sobre evidência, **nunca rebaixa critério**. Rotação/budget = política
de alocação AQUI (a `forma` nasce na sugestão `{tema, forma}`); célula inviável morre em
**silêncio logado** (3 consecutivos = evidência de poda, nunca blocklist a priori).
*Avoid*: theme_suggest (a estrada velha — pool fixo no repo + regex, morre na fiação do dente),
mirar-no-producer (ADR-0012 — superseded), fila/backlog (não há fila: cada batida sorteia)

**PROPOSTA**:
O evento `pauta.proposta` — meia página, pointers:
`{abordagem, objeto, forma, tema, faceta, lastro, gate_trace, delta_voz, origem, depth}`.
**Não carrega outline/ângulo** — desenvolvimento é agência do producer (Ato-2). O lastro da
Pauta **semeia** o gather do producer (grounding pra ESCOLHER ≠ grounding pra DESENVOLVER;
encadeiam, não duplicam). **O nome carrega o setup:** slug prefixado
`{abordagem}-{objeto}--<tema>-<install><data>` — mecânico no publish, não opção do producer.
A palavra do operador (Voz) é **PROPOSTA-ok por autoridade**; grounding seco num caminho
comandado = **seca declarada** dentro da PROPOSTA, nunca silêncio.
*Avoid*: outline, briefing (é escolha penada, não orientação), tema-solto (sem célula/lastro/trace)

**Gate de PROPOSTA / plan-gate**:
O julgamento que decide PROPOSTA (1) ou silêncio (0): **pisos universais** (lastro · delta_voz ·
substrato — higiene, cortam sem rankear, valem até em `{ser,ser}`) + o **gate da abordagem
sorteada** (os 7 da tabela §5), como checks estruturados julgados por completer
(`llm_routes.completer_for`), AND mecânico em código, trace integral em `gate_trace`.
**Δ mente NUNCA dentro do gate** — é veredito do operador a posteriori (`pauta.veto`, com razão).
Lei do risco: nenhum gate contém "pergunta ao operador" — toda dúvida vira aposta afirmada com
lastro; o modo de falha honesto é silêncio logado, nunca espera.
*Avoid*: classificador de keyword/substring (proibido), score/ranking (o gate é AND), rebaixar
critério pra passar alguém

**delta_voz / Redigest**:
Piso universal: a Voz é a **baseline, não blocklist** — o candidato compete contra onde a cabeça
do mentee JÁ está (recall da Voz no tema → juízo semântico de delta, citado no trace).
**Redigest** = pousar onde a cabeça já está (reprova); tema repetido **com delta novo é o caso
bom**. Guarda reversa: Voz mostra domínio → claim de lacuna morre. Roda só na shortlist A
(custo por proposta a medir — dívida §7).
*Avoid*: blocklist de temas, denylist, "já falamos disso" sem juízo de delta

**Shortlist A**:
O corte do meio do funil: das ~12 sugestões baratas (função do wake da célula — **NUNCA pool
fixo no repo**) ficam ~6 por mérito dentro do pólo **+ 1 slot estrutural de serendipidade**,
com os checks delta_voz · filtro direction/wayfind-aberto · substrato. Números (12/6/2–3) são
iniciais — calibrar por evidência (§7).
*Avoid*: ranking global (mérito é DENTRO do pólo), pool/seed list no genótipo

**Catálogo**:
O que o **objeto** sorteado abre pra leitura mirada do wake: `mundo`→sources ·
`atividade`→conversas/obra · `mentorado`→leveling/fog · `ser`→livre. Objeto re-mira o catálogo,
**nunca acrescenta critério** (o gate pendura só na abordagem). O catálogo já nasce filtrado
pelo piso do substrato: evidência sobre o mentee vem das conversas DELE, nunca de log de agente
delegado codando (o resíduo delegado tem outro destino: censo do fog).
*Avoid*: fonte-fixa-por-abordagem (eixos independentes), catálogo-como-gate

**mentorado (objeto)** (ex-`si`, renomeado pelo operador 2026-07-25 — "não é para falar de si;
ou fala do mentorado, da atividade ou do mundo"):
O objeto cuja evidência vem do **estado do mentee** (leveling/fog — perfil, fronteira ativa,
lacunas declaradas). Gate-mentorado de qualidade depende do persona-no-brief (gap nomeado
2026-07-13) — **pilotar `mentorado` depois, não primeiro** (dívida §7).
*Avoid*: ler o objeto como introspecção-do-edge (a deriva que matou `si`: petertosh 2026-07-25
produziu artefatos sobre o próprio dispatch; introspecção legítima é `curiosidade do edge`,
abordagem — sujeito invertido)

**Coringa / serendipidade (`ser`)**:
Valor-coringa nos DOIS eixos: **desamarra o eixo onde aparece** (objeto=`ser` → catálogo sem
limite; abordagem=`ser` → sem lente fixa; `{ser,ser}` = liberdade máxima, ~1/28 por aritmética).
Gate próprio (§5): o desamarrado é **real** (fora do circuito habitual, checável no lastro),
ponte nomeada ao trabalho vivo em UMA linha, e os pisos valem inteiros — liberdade de onde/como
olhar, **nunca de olhar pra nada nem de recontar**. Peso uniforme lançado; se ~36% de
batidas-com-coringa for demais, o dial é o peso (§7).
*Avoid*: random-como-desculpa (pisos valem), lazer (outro genus), os-dois-comuns-com-rótulo-ser

## Language / Idiom — as entidades do vocabulário

_Restauradas em 2026-08-16 (issue #620). Estas 13 definições foram apagadas por
`d547442` ("CONTEXT.md as 9-module self-model — Idiom removed") e o merge `9221924` do dia
seguinte devolveu só 32 dos 45 cabeçalhos. Ficaram fora por seis semanas enquanto este
mesmo documento usava `mentee` 54 vezes, `artefato` 26 e `cortex` 17 — o glossário de
referência não definia nenhum dos termos centrais do sistema. A seção original chamava-se
`## Language` e não existe mais na estrutura de 9 módulos; elas voltam agrupadas aqui._

**Mentee**:
The person the edge serves — their real work is the subject. The edge knows them from
what they do (code, docs, words), not from supposition.
*Avoid*: user, client, operator

**Cortex**:
The edge's whole navigable knowledge as one connected graph — the **mind** it thinks *in*. Everything
projects into it: intake → episodes/clusters (extracted), plus the **asserted** edges (Direction, curated,

**Artefato / Artifact**:
A beat's **published deliverable**, in whatever form the producing skill yields — a prose
synthesis (`ed-report`), an interactive page (`prototype`), and others. The genus, not one
form. Carries Worthwhile content; bears the comment field (consolidation surface).

**Hypothesis**:
Something the edge supposed (mined or inferred) and not yet confirmed (`assumed`). The
edge **works naturally** with hypotheses — the abundant, cheap tier.
*Avoid*: guess, draft

**Consolidação de hipóteses / Hypothesis consolidation**:
Promoting hypothesis → curated. The **inward** half of what `/grill-me` (active) and the
per-report comment (async) do — it keeps the edge's model accurate, but is not the whole of
the grill, which also **generates outward orientation** for the mentee (see Convergence).
Does not drain the hypothesis tier; consolidates what carries **harm potential**.
"Afinamento" is the same loop when the object is the mentee's **language** (Idiom).
*Avoid*: approval, review, afinamento (as a separate concept)

**Domain**:
The field the mentee works in. The edge must know it deeply to have substance.
*Avoid*: area, topic, field

**Recall**:
The **memory-salient brief** — a noun, the yield of recalling (the act stays a lowercase verb,
exactly as Delta is the yield of updating): the salient subgraph of the **Cortex**, rooted at

**Worthwhile content**:
The intersection: deep domain insight **applied to the mentee's live work**. Domain
alone is generic; mentee alone is shallow.
*Avoid*: report, output, post

**Medium / Meio**:
A channel through which the mentee and the edge **address each other** — Claude Code is just
one; Telegram, a shared Slack, a web chat are others. The **pipe, not the content**: it carries

**Usage signal**:
The **implicit, non-authoritative** record of which Cortex nodes the edge READ while working —
appended to `state/cortex/usage.jsonl` (behind `EDGE_CORTEX_USAGE`), EXCLUDED from log replay and
every fold. It drives an **ephemeral read-time re-rank only** (recency+frequency), never a graph write:
it is NOT self-state (the log stays truth — ADR-0006). Distinct from **value feedback** (`cites`/
`distills` at close) and **correction** (node-targeted Voz / Earmarked), both curated and authoritative.
*Avoid*: salience, reinforcement, memory store

**Curated**:
Knowledge consolidated by the mentee (`confirmed`/`corrected`). **Prioritized** over a
hypothesis in every read-model. **Exempt from passive aging** (it does not cool by going unread
or unreinforced) but **actively retirable by Voz** — a strategic realignment can supersede it.
Only the mentee retires curated; passive forgetting never does.
*Avoid*: validated, final, approved

**Harm potential**:
The consolidation priority: source ambiguity × cost of acting wrong. Decides what spends
the mentee's scarce attention.
*Avoid*: urgency, score

**llm-wiki**:
The edge's knowledge, held as two kinds of durable page — **Knowledge clusters** (emergent,
grown) and a few **Standing pages** (declared then refined: Direction, Idiom, Source roadmap)
— plus cross-references, holding both hypothesis and curated. An **Artefato** is a transient
delivery (a Query result), never a page. Read **in full when small** (the briefing's entry read);
