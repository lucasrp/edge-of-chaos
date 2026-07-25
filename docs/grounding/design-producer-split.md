# Design do producer split invertido (#61): grounding no MAIN, publish num PUBLISHER

> Faceta do Loop de grounding. Inverte o split do scaffold: o **grounding fica no agente
> PRINCIPAL** (leituras diretas → contexto rico pra síntese; explorers = fan-out OPCIONAL de
> largura) e o **publish mecânico vai pra um subagente PUBLISHER dedicado** (recebe o spec
> assentado, roda o close+publish, devolve slug/URL). Interface/fluxo apenas — sem código.
> Verificado contra `tools/close.py`, `tools/publisher.py`, `tools/eventlog.py`,
> `tools/harvest.py`, `tools/predispatch.py` nesta branch (`feat/producer-split-61`).

## 0. O fork resolvido: ONDE mora o wake / dispatch_id (o crux)

**Resolução: o MAIN acorda (predispatch UMA vez), grounda, sintetiza; entrega o spec assentado
+ o MESMO `dispatch_id` ao publisher; o publisher roda SÓ `close.run_close` com esse
`dispatch_id`, NUNCA um predispatch fresco.** Um único `dispatch_id` atravessa a costura.

O issue sugere "publisher roda predispatch" — está **errado**, e o código prova por quê. Três
razões, todas verificadas:

1. **A atribuição de grounding (S4) casa as leituras do MAIN ao `dispatch_id` via
   `session_id`.** O `dispatch.open` grava `session_id: os.environ.get("CLAUDE_CODE_SESSION_ID")`
   do MAIN (`predispatch.py:130`); o harvester mapeia rows por `(session anchor, dispatch
   interval)` (`harvest.py:1242-1248`, `_map_dispatch`), onde o anchor é o `session_id`+`seq`
   do `dispatch.open`. As leituras que fundam vivem no transcript do MAIN. Se o PUBLISHER
   minta-se um `dispatch_id` novo, o `dispatch.open` carregaria o `session_id` do PUBLISHER e as
   leituras do MAIN (na sessão do MAIN) **não mapeariam** pra esse dispatch → atribuição quebra.
2. **O yield-join (S7) casa publish→grounding pelo `dispatch_id`** — bound no digest do proof
   (`close.py:1741-1743`). Dois `dispatch_id` diferentes (um que fundou, outro que publicou)
   desconectam o join sem violar o proof.
3. **O gate identity-held NÃO exige mesmo-processo — só a identidade no log.**
   `eventlog.wake_fresh_for(dispatch_id)` (`eventlog.py:492-510`) retorna `opened and not
   consumed`, lendo APENAS o log compartilhado: existe um `dispatch.open` cujo payload mintou
   esse id **E** nenhum `artefato.published` o consumiu. Não checa processo, nem `session_id`,
   nem "mesma sessão do wake". Logo o MAIN pode stampar o `dispatch.open` e NÃO publicar; o
   PUBLISHER publica com o MESMO id: `opened=True` (MAIN stampou), `consumed=False` (ninguém
   publicou) → **o gate passa sem UMA linha de código nova.**

**O código já suporta a costura de dispatch_id único — ZERO mudança no gate.** Confirmado:
- `publisher.publish(..., dispatch_id=...)` gateia por `wake_fresh_for(dispatch_id)`
  (`publisher.py:593-597`) — id-scoped, não global. O MAIN acorda, o PUBLISHER (mesmo log)
  publica sob o mesmo id: passa.
- `run_close` lê `dispatch_id` de `artefato.get("dispatch_id")` (`close.py:2332`) e o repassa ao
  `_mint_proof`/`proof_digest`. O proof é mintado NO CONTEXTO DO PUBLISHER a partir do spec
  recebido — e isso é são (§2).

O `predispatch` continua rodando UMA vez, no MAIN, no entry da skill (inalterado). O
`DISPATCH_ID=<id>` impresso (`predispatch.py:298`) é o que o MAIN carrega no brief pro publisher.

## 1. O handoff: o que o MAIN passa ao PUBLISHER (pointers, nunca dump)

Idioma `conductor.node_briefs` (`conductor.py:600-611`): brief + POINTERS de disco, jamais um
dump de contexto. O MAIN escreve o spec assentado num path e passa **referências**:

```
publish-brief (o payload do Agent-tool spawn):
  dispatch_id     : "<id do DISPATCH_ID= do wake do MAIN>"   # a identidade única
  main_session_id : "<CLAUDE_CODE_SESSION_ID do MAIN>"       # p/ o floor S6 (§4, crux)
  skill           : "report" | "map" | "research" | "plan" | …
  intent_kernel   : "open: …; bet: …"                        # o porquê (C3), ~3 linhas
  spec_path       : "<path>/spec.json"    # o artefato content assentado (blocks), no disco
  cites_path      : "<path>/cites.json"   # [{ref,kind,relevant,snippet}]
  proposes_path   : "<path>/proposes.json"
  distills_path   : "<path>/distills.json" # ["cluster:<label>", …] ou []
  lineage_path    : "<path>/lineage.json"  # [{type,slug}] ou []
  slug            : "<slug>"
```

Regra de ouro (a parede do tipógrafo, `pipeline.md:149-161`, ESTENDIDA): o publisher **recebe o
spec ASSENTADO — cada claim já feito**. Ele não cria claim, cite, proposal nem frase de
substância. A síntese pertence a quem tem o contexto rico (o MAIN). O que o publisher faz é
mecânico: gate de revisão, improve mecânico, mint, render, publish.

Por que pointers e não dump: mantém a janela do PUBLISHER enxuta (ele renderiza e gateia, não
raciocina sobre o mundo) e a do MAIN livre da máquina de publish (a que **travou >4min** rodando
inline). O spec no disco é a única fonte de verdade; o proof será mintado sobre ele.

## 2. Contrato do PUBLISHER: proof-bound através da fronteira de processo

**Input** (pointers acima) → o publisher lê os arquivos, remonta o `artefato` dict carregando
**todo campo proof-bound** (`slug`, `intent`, `content`=spec, `cites`, `proposes`, `distills`,
`skill`, `lineage`, `dispatch_id`) e chama:

```
close.run_close(artefato, produce_fn=lambda: artefato, improve_fn=<mecânico>,
  floor_fn=lambda: harvest.close_floor(session_id=main_session_id),   # §4 — o fio do floor
  complete_fn=<review-completer>, publish_fn=<publisher.publish-backed>)
```

**Integridade proof-bound é SÃ através do boundary.** O digest cobre exatamente
`{slug, spec, intent, cites, proposes, distills, skill, lineage, dispatch_id}`
(`close.py:1745-1758`, `proof_digest`) — **nenhum campo de sessão/processo**. O `_mint_proof`
(`close.py:1762-1792`) sela o token `run_close`-only e o digest; o `verify_proof`
(`close.py:1902-1921`) e o `publisher.publish` (`publisher.py:561`) **recomputam o digest do
payload prestes a publicar** e conferem token+digest+2 vereditos. Nada no mint/verify assume
"mesmo processo que o wake" além da IDENTIDADE `dispatch_id` — que viaja no brief. Logo mintar o
proof no contexto do PUBLISHER, a partir do spec que ele recebeu, é são: o proof vincula o
CONTEÚDO do spec + o `dispatch_id`, mintados onde quer que o close rode.

**Output** — canal de pull tipado (idioma `subagent_completer`, `conductor.py:614`), o publisher
retorna ao MAIN um dict pequeno, NUNCA um dump:

```
{ "status": "published" | "bounced" | "residual-published",
  "slug": "<slug>", "url": "blog/entries/<slug>.html",
  "cost": <float>, "residuals": [...], "rationales": {dim: texto},
  "bounce_reason": "<named gap>"  # só quando status == "bounced" (§3)
}
```

`published` = passou; `residual-published` = publicou-com-resíduos (S6, knob
`EDGE_PUBLISH_WITH_RESIDUALS`, tidy mecânico esgotou mas genus-limpo); `bounced` = precisa do
autor (§3).

## 3. A fronteira do review-bounce: mecânico fica, substantivo volta

Reviewers podem strikar → `run_close` roda o improve loop (`improve_fn`, `close.py:2113-2124`).
**O PUBLISHER É DONO DO IMPROVE MECÂNICO.** O improve revisa o draft a partir de
rationales+strikes — é edição de forma/clareza/craft, exatamente o rung 4→5 do ladder que já é
context-denied (reviewers veem "content + cites only"; publisher vê "final Artefato only",
`scaffold.md:166-170`). Esse trabalho **nunca precisou do contexto rico** do MAIN — mové-lo pro
publisher é natural.

Na exaustão, DUAS saídas, decididas pela NATUREZA do gap:

- **Tidy mecânico esgotou, genus-limpo** → `publish-with-residuals` (S6, `design-close.md §1`,
  `close.py:2058` `_try_residual_publish`): o publisher publica com a seção "Crítica não
  endereçada" e retorna `residual-published`. Não precisa do autor: a crítica é de forma, e o
  precedente eLife/F1000 gradua-sem-gatear.
- **Strike SUBSTANTIVO** (a crítica exige re-derivar, re-fundar, re-raciocinar — um claim novo,
  uma âncora factual faltante, a rich-rite floor pedindo derivação/lineage) → o publisher NÃO
  tem o contexto pra curar (ele recebeu o spec assentado, não o mundo). Ele **devolve
  `bounced: needs author`** com o gap nomeado; o MAIN — que segura o contexto rico — re-produz e
  reentrega. Uma re-produção substantiva precisa do autor; um tidy mecânico não.

A linha divisória prática: o publisher tenta o improve mecânico dentro do `BOUNCE_MAX`/backstop;
se o que sobra é forma → residual-publish; se o que sobra pede substância (o próprio `improve_fn`
mecânico não consegue fechar sem re-fundar) → bounce ao MAIN. O MAIN decide re-produzir ou aceitar.

Nota: o genus floor (S6) e a violação de genus são **blocking-first, nunca residual**
(`design-close.md §6`). Uma violação de floor que sobrevive ao improve mecânico é sempre um
`bounced: needs author` (o autor tem que ir ler/fundar) — ver §4.

## 4. RESIDUAL RISK #1 (o mais afiado): o floor S6 perde os dentes na sessão do publisher

`close_floor` resolve `session_id` de `CLAUDE_CODE_SESSION_ID` do processo que roda o close
(`harvest.py:1729-1730`) e (a) decide THEMED via `_last_geometry(session_id)`
(`harvest.py:1777-1795`, casa `payload.session_id == session_id`) e (b) roda `session_floor`
sobre `*/{session_id}.jsonl` + subagents (`harvest.py:1681-1688`).

Se o close roda no PUBLISHER com o `CLAUDE_CODE_SESSION_ID` do PUBLISHER:
- `_last_geometry(publisher_session)` → **None** (o `dispatch.open` foi stampado com o
  `session_id` do MAIN, não do publisher) → `_floor_dark("undeclared geometry")` → `[]`
  (fail-OPEN, `harvest.py:1739-1741`).
- Mesmo se a geometria fosse vista, `session_floor` escanearia o transcript do PUBLISHER — que
  **não tem leitura de fonte nenhuma** (o publisher não grounda) → `reads=0`.
- Subagente: `CLAUDE_CODE_CHILD_SESSION` provavelmente setada → `_floor_dark("child session")`
  → `[]` (`harvest.py:1735-1737`).

**Consequência: com o split ingênuo, o floor de grounding do #59 vira SEMPRE-DARK — perde os
dentes.** Justo o floor que o issue cita como reforço do requisito.

**A cura é uma injeção de UM parâmetro (o código já suporta):** `close_floor` aceita
`session_id=` e `store_root=` injetáveis (`harvest.py:1706`). O handoff carrega `main_session_id`;
o publisher fia `floor_fn=lambda: harvest.close_floor(session_id=main_session_id)`. Aí:
- `_last_geometry(main_session_id)` acha o `dispatch.open` themed do MAIN → geometria correta.
- `session_floor(main_session_id)` escaneia o transcript do MAIN — onde as leituras VIVEM
  (o MAIN está vivo, o `.jsonl` é append-live, as leituras já aconteceram antes do handoff) →
  `reads>0` → floor satisfeito.

Isso **restaura os dentes do floor através do split**, sem código novo — só o wiring do call-site
carregar o `session_id` do MAIN. É por isso que `main_session_id` é campo de 1ª classe no brief.

## 5. Facet A (grounding fica no MAIN): as mudanças de prosa (genótipo)

O default vira "recall + leituras DIRETAS do MAIN; explorers = fan-out OPCIONAL de largura".
Invariantes S5 **preservados**: harvested-never-emitted (o harvester minera post-hoc) e
roadmap-at-gather (ler `state/source-roadmap.md` na hora, canário como conselho).

**`skills/_shared/scaffold.md`, slot `gather-grounding` (linhas 30-64):**
- Trocar "the producer **freely delegates to its subagent fleet**" → o produtor **grounda no
  próprio contexto: recall (rung 1) + leituras DIRETAS das fontes** (o contexto rico fica nele,
  disponível pra síntese). Delegar a explorers é **fan-out OPCIONAL de largura** — quando o tema
  tem facetas independentes que valem paralelismo — **não o caminho default do grounding**.
- Manter intacto: "recall before you research", o bloco harvested-never-emitted +
  roadmap-at-gather (linhas 43-53), e a parede ADR-0014 do explorer (deny `cortex`, linhas
  55-64) — ela vale ainda mais quando o grounding volta pro MAIN (o MAIN lê mundo E self; o
  explorer opcional segue world-only).
- Acrescentar a razão de uso real: leitura direta = casos reais e profundidade; `{source,ref}`
  raso de explorer perde o contexto que funda (o issue).

**`skills/report/SKILL.md` (linhas 35-42) e as demais producer-skills, mapping do
`gather-grounding`:** trocar "**delegate freely** to reach plenitude" → "**recall first, then
DIRECT reads by the main agent** (o contexto fica); explorers = fan-out opcional por faceta pra
largura, não o default". Manter o piso factual (claim sobre o Mundo sem evidência não embarca).

## 6. Facet B (publish delegado): CÓDIGO vs PROSA — a chamada mínima

**Recomendação: PROSA + reuso do que já existe. Zero tool nova.** O publisher-delegation é uma
**instrução de skill**: o produtor, uma vez o spec assentado, spawna um subagente via o Agent
tool com o publish-brief (§1). O subagente roda o snippet `close.run_close` que HOJE já vive no
SKILL.md (linhas 111-138) — só que agora num processo separado, lendo o spec dos pointers e
fiando `floor_fn` com `session_id=main_session_id` (§4).

Por que não uma tool nova:
- Todo o mecanismo já existe: `close.run_close`, `publisher.publish`, `close_floor(session_id=)`,
  o gate id-scoped `wake_fresh_for`. Nada falta no substrato.
- A casa proíbe primitives especulativos (ADR-0001; CLAUDE.md "Simplicity First"). Um
  "publish-brief packager" seria abstração de uso único.
- O `conductor.node_briefs`/`subagent_completer` já são o idioma de brief+pull-channel a copiar.

O único artefato de configuração necessário é o **agente publisher committado** (à la
`.claude/agents/explorer.md`): um `.claude/agents/publisher.md` cujo frontmatter dá ao publisher
as tools mecânicas (Bash pra `edge-python`, Read pros pointers) e **nega o `cortex` self-door**
(ele não recalls; não é autor) — a mesma parede de escopo por construção do explorer. Isso é
config declarativa, não código.

**A emenda tipógrafo existente (`pipeline.md:149-161`) é o precedente — mas o publisher do #61 é
mais pesado:** o tipógrafo edita só FORMA e o produtor ainda roda `run_close`; o publisher do #61
**é dono do `run_close` inteiro** (gate de revisão, improve mecânico, mint, render, publish). A
emenda pipeline.md deve ser reescrita pra descrever esse publisher (não o clerk-só-forma), OU um
parágrafo novo que a substitui. Ambos são context-denied por design (rungs 4-5), então mover o
close pro subagente é a extensão natural da mesma parede, não uma nova.

## 7. Riscos residuais declarados

1. **[CRÍTICO — §4] O floor S6 vira sempre-dark se o wiring esquecer `session_id=main_session_id`.**
   Mitigação: campo obrigatório no brief + o call-site do snippet o fia explicitamente. Sugestão
   de teste: golden que roda `close_floor(session_id=<main>)` contra um transcript-fixture do MAIN
   com leituras e confirma `reads>0` (dentes) vs `close_floor()` sem session → dark (o bug).
2. **Frescor do transcript do MAIN no momento do publish.** `session_floor` escaneia o `.jsonl`
   live do MAIN. As leituras aconteceram ANTES do handoff, então já estão no arquivo — mas se o
   flush do transcript for lazy, uma leitura muito recente poderia não estar persistida. Risco
   baixo (o gather termina antes da síntese, que termina antes do handoff); flag pra observar.
3. **Duas escritas concorrentes no log?** Não — o MAIN não publica; só o publisher escreve
   `artefato.published`. O gate `wake_fresh_for` é consumido sob o lock do
   `publish_artefato_atomic` (`publisher.py:423`). Um único consumidor. Sem corrida.
4. **`dispatch_id` órfão se o publisher falhar (bounce → needs author) e o MAIN nunca republicar.**
   O `dispatch.open` fica unconsumed — idempotente e benigno (o próximo publish sob esse id ainda
   passa). O MAIN re-produz e reentrega ao publisher com o MESMO id (não reacorda). Só um
   predispatch novo (novo beat) mintaria id novo.
5. **Contexto do publisher inflando via pointers grandes.** Mitigar mantendo o spec no disco e o
   publisher lendo sob demanda (Read com offset), não colando o spec inteiro no prompt do spawn.

## 8. Resumo da costura (uma linha por decisão)

- **Um `dispatch_id`**, mintado pelo predispatch do MAIN, carregado no brief, usado pelo close do
  publisher. Gate id-scoped já suporta (`eventlog.py:508-510`). Sem código no gate.
- **Grounding no MAIN** (recall + leituras diretas); explorers = fan-out opcional. Prosa em
  scaffold.md + producer-skills.
- **Publish no PUBLISHER** (run_close inteiro: gate+improve mecânico+mint+render+publish). Prosa +
  `.claude/agents/publisher.md`; zero tool nova.
- **Proof mintado no publisher** a partir do spec recebido — são (digest não tem campo de
  processo/sessão, `close.py:1745-1758`).
- **Bounce**: mecânico fica no publisher (improve/residual); substantivo volta ao MAIN
  (`bounced: needs author`).
- **Fio invisível a não esquecer**: `close_floor(session_id=main_session_id)` — sem ele o floor
  S6 perde os dentes (§4).
