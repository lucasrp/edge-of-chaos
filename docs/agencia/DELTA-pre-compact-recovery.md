# DELTA — recuperação da sessão pré-compact (2026-07-05)

Extraído por subagente-leitor da sessão inteira pré-compact (`6d7f590f….jsonl`, 231 turnos do operador, 2 compactações), diffado contra os docs de `agencia/` + memórias. **Só o que NÃO estava nos docs.** Fonte de verdade pra não perder na próxima.

## 1. Ordens de segurança/operação (VERBATIM — persistir)
- **"o edge neo4j n é pra derrubar pq o agente pode usar. o maieutica tb. é pra vc derrubar coisa como os apps web"** — no roberto, RAM-cleanup só mata web apps (blog servers, cloudflared); NUNCA edge-neo4j/maieutica-neo4j/heartbeat.
- "só deixe tudo recuperavel" + recon read-only no roberto; NUNCA lançar lá sem go explícito.
- NÃO pushar pra origin sem o operador (origin compartilhado; roberto commita lá).
- "vc deu merge sem conferir se tinha codigo novo" → sempre `git fetch origin && git log main..origin/main` antes de qualquer mutação git.
- "enquanto nao deixar tudo clean n tem grill / resolva o merge primeiro" — consolidação git é gate absoluto.
- **Contrato operacional VIVO (só no último turno, em doc nenhum):** subagentes fable pra execução; `/ed-dig` + `/pocock-codebase-design` na ABERTURA de cada subagente; **um de cada vez**; enquanto ele trabalha, o operador e o ed conversam e gerenciam a execução juntos.
- Keepalive <4min (TTL ~4–4.5min, codex-backed) — vale pros subagentes fable também (cadência apertada).
- DB writes/mudança de estado = ATO/HITL, read-only por default (#70).

## 2. Decisões que mudam O QUE se constrói
- **Teste de aceite = `/ed-research` genérico CEGO no roberto** (deploy da versão nova + deixa criar o KG dele + research sem dizer o tema), julgado como leitor-faminto-de-contexto / passável-pro-colega. **É isto ANTES do grill.** "temos todo o wake novo também."
- Forma do MD vencedor (sonnet) **+ agência e coisa útil**, não a forma vazia.
- "gosto da profundidade. nao precisa ser curto pra ser humano. longo e parecendo humano, melhor."
- Régua concreta: **o artefato é passável pra um cliente/colega** — alguém que não é perdido, mas não sou eu e às vezes não domina o domínio (Tiago/Rui entregavam direto pro cliente).
- **O gate-objetivo NÃO pode depender de persona/leveling existir** — o edge antigo/Rui/Nailton gateavam crescimento sem saber de onde a pessoa parte; input = **olhar quente**. Leveling é plus/afinamento.
- "se fiz um experimento, por que não mostrar ele literalmente" — o artefato interativo pode EMBUTIR o experimento literal; **interatividade ≠ riqueza visual** (outra dimensão).
- Ponteiro-Feynman também nos TESTES da implementação ("literal, que o codex vai entender").
- Pseudônimo p/ redes sociais (deferido; conta moltbook nova "tainted" → abandonada).

## 3. Estado do merge (verificado no repo, pré-a671)
- Branch `consolidate-2026-07-05`, **19 paths UNMERGED no index** (conteúdo resolvido, 0 marcadores), suíte nunca rodada.
- **Flip do eventlog MEIO feito:** `winning_manifest_rows` restaurado em `tools/eventlog.py:829`, `fold_grounding` usa ele — MAS `tools/grounding_yield.py:167` mantém `_winners_and_canaries` inline (a duplicação que B quer matar segue). `tests/test_winning_manifest_rows.py` deve passar agora.
- Falta: `git add` dos 19 → suíte → commit → foldar `session/agencia-core-exp` (drafts) → reconciliar origin (50×27). `agent.yaml` já restaurado pro **ed** (commit `92ad2e86` do roberto tinha clobberado a identidade).
- **Judgment calls dos resolvedores (podem morder a suíte):** (a) predispatch — leg de harvest DUPLICADA removida (bug real); (b) predispatch usa `eventlog.grounding_at`, não `cortex.grounding_at` (bypass deliberado do front-door p/ não puxar neo4j no wake load); (c) harvest usa `cortex.supersede_rank`; (d) close.py: residual-publish agora EXIGE `complete_fn` funcional; (e/f) **doutrina DROPADA no merge** — ver §5.4.

## 4. Correções do operador em mim (anti-repetição)
1. Derrubei neo4j no roberto limpando RAM → só web apps.
2. Merge cego sem checar origin → `verify-before-merge`.
3. Trabalhei em checkout stale re-inventando o que B já commitara.
4. Declarei "A ganhou/agência validada" — auto-avaliação single-voice; o veredito CEGO é do operador (P0 aberto).
5. **A decepção central:** report com referentes sem nome ("o mecanismo passou" — que mecanismo?) → "vc me entregou um negocio inutil, me decepcionei". Fix = teste do colega + **"a função do report é INFORMAR, mas de um jeito que cresça a pessoa"**.
6. "não quis dizer impessoal — quis dizer o Feynman explicado numa forma impessoal" (conceitos como critério, não tirar o Feynman).
7. Opus na ontologia → "cancele, mande fable, é o mais crítico de meses".
8. Resumo p/ contexto importante → "não, leia TUDO".
9. Austero puro = oco medroso: "o mentor corre riscos; tirar isso mata a agência antes de nascer".
10. Juiz-IA com material amplo MASCARA a ilegibilidade → juiz = leitor faminto de contexto.

## 5. GAPS — decidido mas NÃO escrito (risco de perda)
1. **`implementacao/02-D-*.md` e `03-migration.md` NÃO EXISTEM** (00-ordem referencia ambos). D: wire `relate.py` (nominate→route) no sweep + `MERGE RELATES_TO` faltante. A-migration: ~180 linhas/5 arquivos + `cortex/schema/ontologia.yaml` (detalhe na ontologia Fable completa → copiada pra `implementacao/ref/ontologia-fable-full.md`).
2. **O aceite roberto (deploy + KG + research cego, ANTES do grill) não é ticket no wayfinder** — é o critério de "agência iterada" do operador.
3. **#70 (skill `app`) fora de todos os docs** — só GitHub + transcrito.
4. **Doutrina dropada no merge:** `X-first-for-agentic` (2026-07-04) sumiu do `dig/SKILL.md` (ORIGIN priors venceu); calibração "assume o que ele domina" dropada em `research/report SKILL.md` → **potencial contradição com a doutrina Feynman-calibrado da noite**. CONFERIR antes de qualquer push (o merge local é reversível).
5. **P0 (veredito cego A-vs-B)** — pré-registração em `docs/agencia/agencia-hipoteses.md`; ausente dos docs de implementação.
6. Ontologia Fable completa estava só em `/tmp` (volátil, task `a190225`) — **copiada pra `implementacao/ref/ontologia-fable-full.md`**. Versão opus convergente no transcrito (task `a563baa`).
7. Glossário: `glossario-agencia.md` é duplicata STALE — canônico = `vocabulario-da-noite-2026-07-05.md`.
