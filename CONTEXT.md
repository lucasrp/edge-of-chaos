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

## 3. Produção   ⟶ CONGELADO (agente vivo é dono do conductor)
**Resp:** mirar o tema Worthwhile e montar contexto rico num rascunho.
**Interface:** `produce(theme, depth) → draft`

- **Artefato:** o entregável de um beat — carrega Worthwhile content, existe pra **mover ou confirmar a Direction**. Transiente (esfria, é prunável); o durável vive no cluster, o steer na Direction. Nasce aqui, é julgado no 4, publicado no 5.
- **Worthwhile content:** a interseção — insight profundo de domínio **aplicado ao trabalho vivo do mentee**. Domínio sozinho é genérico; mentee sozinho é raso.
- **Producer-skill:** uma skill que rende um Artefato na sua forma — report/research/map/plan/discovery/critique. Mira o tema mais Worthwhile contra Direction + delta, produz, sai pelo close.
- **Conductor:** a maquinaria de montagem do genus deep-dive — outline vivo por-nó (empty→draft→revised→final), split/merge, arco motivate→deliver→change-the-course estrutural. O gate de discharge por-nó **chama** a interface do Close. **Dark by default** (`EDGE_CONDUCTOR`).
- **Rich rite (ato):** os moves cognitivos que o produtor **faz** — derivação de primeiros princípios, um "o que eu não sei" marcado, um benchmark/frame de fora, a lineage. (O Close afere; aqui se gera.)
- **Depth:** o alvo de desenvolvimento que o **operador** seta (brief/standard/deep) — o recurso escasso é a atenção do mentee. Ceiling, não floor.

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
- **Beat / Heartbeat:** o pulso autônomo (cron, hoje 3h) — round-robin puro sobre os producers, carrega só rotation state. Cadência é o único dial de gasto.
- **Sequenciador de entrada:** no wake, blocking — `Aquisição.sweep()` → `Cortex.project()` → **commita o cursor só no fim** (atômico). O antigo **Assemble dissolveu** aqui (a lógica voltou pros Módulos 1 e 2); o **Consolidate** já dissolvera no ADR-0008.
- **Briefing:** a orientação apresentada a cada dispatch (Memento's tattoo) — 4 partes projetadas: Knowledge clusters (←grafo) · Direction (←log) · Recap (←corpus) · source orientation (←roster).
- **Corpus / Recap:** o corpus é o trabalho próprio do edge (fold de `artefato.published`); o Recap é sua projeção no briefing, correlacionada fresh à Atividade do mentee.
- **Medium / Meio:** os canais por onde mentee e edge se falam (Claude Code nativo = two-way mas low-tier; Voz rail = order-bearing). O pipe, não o conteúdo.
- **LLM routes:** provider-por-rota (`completer_for(route)` — chat/review = codex/gpt-5.5).
