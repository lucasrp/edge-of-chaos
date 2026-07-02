# Plano de implementação por slice (Loop P)

> Consome: requirements.md + 4 designs + design-amendments-r1.md (emendas E1-E7, E1b/E1c/E2b
> vinculantes). Cada slice: TDD (teste primeiro, verde), codex adversarial no diff até só-nits,
> commit. Branch feat/grounding-iteration; NUNCA deploy da worktree (edge-apply só pós-merge).

## Fatiamentos alternativos considerados (design-it-twice do plano)

(a) **por camada** (eventos→folds→integrações→textos) — escolhido: cada slice deixa a base verde e
consumível pelo próximo, dependências explícitas, codex revisa diffs coesos por tema;
(b) por fluxo (dig e2e primeiro) — rejeitado: o dig atravessa 5 camadas, diff gigante, viola o
"cada slice verde"; (c) por risco (harvest primeiro) — rejeitado: harvest sem dispatch_id/schema
re-trabalha o join depois (E1/E3 são fundações).

## S1 — eventlog: tipos + folds do grounding

Novos tipos `grounding.manifest`, `grounding.finding`, `canary.result`, `grounding.floor_dark`,
`grounding.unmanifested`. `fold_grounding` (dedup por `raw_ref` bruto E2b: (session_id, line_offset,
tool_use_id, occurrence_index); `supersedes` last-wins por (recognizer_rev, seq); seca-suspeita e
attribution inferred/unknown contados em `excluded` por motivo) + `grounding_at(seq, ts)`.
**Verify:** pytest — fixtures de eventos com duplicatas, supersedes, desempate, corrupt payload
(fail-dark contado); folds puros sem I/O.

## S2 — dispatch_id: identidade + cadeia proof-bound (E1/E1b/E1c)

Predispatch cunha ULID e o retorna; `dispatch.open` payload ganha campos declarados opcionais
(theme/intent/geometry — tier `declared`). `artefato` dict ganha `dispatch_id`; entra em
`proof_digest`/`_mint_proof`/`verify_proof`/`publisher.publish`/`publish_artefato_atomic`
(obrigatório no log canônico; helper test-only injeta sintético; `publish_artefato` legado =
migration/test-only). Snippets das producer skills atualizados (`dispatch_id=art['dispatch_id']`).
**Verify:** suite existente do close VERDE (byte-compat fora do novo campo) + testes novos: digest
muda se dispatch_id muda; publish canônico sem id falha loud; concorrência (2 dispatches abertos,
cada publish consome o seu).

## S3 — agent.yaml schema: interfaces[] + acts (E3)

Migração das fontes atuais pro schema `{interface_id, via, idiom, canary, dry_semantics}` por fonte
(exa: search-deep + contents como 2 interfaces; x: v2-recent [+ xai como interface declarada-sem-
chave]; arxiv; hn; github; gdrive: read em interfaces, upload movido pra seção `acts:` HITL).
Loader com validação (fonte sem interfaces = warning no doctor, não crash; acts nunca viram
recognizer). Dados medidos do R2.5/R2.6 entram AQUI (canary/idiom/dry_semantics por interface).
**Verify:** pytest do loader (schema válido/inválido/legado-sem-interfaces degrada declarado);
`edge-render`/doctor dry-run verde.

## S4 — harvest.py: o colhedor (espinha C + E2b)

`harvest(log, cursors_path, project_dirs)` cursor por arquivo (idioma sweep; glob estendido a
`subagents/` E a TODOS os project-dirs do store — E7); `recognize(tool_use, tool_result, recognizers)`
pura; recognizers derivados de `interfaces[].via` (S3) + pseudo-sources websearch/webfetch-native +
scripts conhecidos → `attribution: opaque-script`; raw_ref bruto com occurrence_index (uma tool call
com N queries = N rows); atribuição mapped (meta.json→toolUseId→prompt) / declared (S2) / unknown;
hits None≠0 sagrado; tool-results derramados seguidos por ponteiro; `unrecognized` tally.
**Verify:** fixtures DOURADAS extraídas do store real desta sessão (curl exa/X/arxiv, WebSearch,
gh, subagent com meta.json) — cada recognizer com caso feliz + malformado; idempotência (re-run
sem novos raw_refs = 0 rows novas); teste de retro-harvest (cursor reset → mesmas rows, fold
deduplica).

## S5 — predispatch: harvest + canário + ambient (R3, design-emissao)

`harvest_fn` degrade-dark no chão mecânico (uma linha + try); passo `canary`: secas pendentes →
bateria por interface (spec do agent.yaml S3) → `canary.result` appendado (rótulo final é FOLD:
verificada = canário-pass E idiom conforme; suspect:instrumento; suspect:overspecified;
não-aplicável por dry_semantics — B1); stamp `ambient_rows`/`harvested` no dispatch.open.
**Verify:** unit com store fake (secas viram suspects; canário-pass+idiom-ok → fold projeta
verificada; wake NUNCA raise — fonte morta = perna escura anotada); smoke read-only no store real.

## S6 — close: genus floor + publish-with-residuals (design-close + E6/E7)

`run_close(..., floor_fn=None)` — violações somadas às do genus (blocking-first herdado);
`harvest.session_floor()` via recognize() no transcript vivo (locator por índice E7;
`grounding.floor_dark` contado; knob `EDGE_GROUNDING_FLOOR=0/1/2` default 1=observe).
Publish-with-residuals: branch na exaustão de bounce pós-review (genus limpo + só strikes reais —
strikes sintéticos/transport re-raise desqualificam); seção "Crítica não endereçada" apensada a
`additional_sections` ANTES do mint; re-roda genus pós-append (sujo → hard-fail); `unaddressed` no
proof (nome distinto de `residual`) e campo de 1ª classe no evento; `verify_proof` branch
`residual_publish` (token+digest+identidades mantidos); knobs opt-in default OFF;
`EDGE_GENUS_BOUNCE_MAX` default = BOUNCE_MAX (E6).
**Verify:** suite close inteira VERDE com knobs off (byte-compat); fixtures novas: residual-publish
feliz; genus-sujo-pós-append hard-faila; transport error nunca vira residual; digest cobre a seção
apensada; floor=2 bloqueia artefato sem leitura reconhecida (fixture com transcript sintético).

## S7 — yield: join + tabela + painel (design-yield + E1)

`fold_grounding_yield`/`grounding_yield_at`: join por dispatch_id (S2) → slug; escada
exact/coarse/ambiguous/orphan; similarity==0.0-sem-embedder excluída de mean_sim (artefato de
instrumento); `YIELD_POLICY` como DADO (min_attempts=5→"EXPLORE", shrink_pseudo_n=3, cite_prior);
excluded contado por motivo; sem `choose_source()` exportado. Render: bloco ≤6 linhas em
`_section_sources` (never-blank = linhas seed com proveniência `seed:loopR` vindas do roadmap,
NUNCA pseudo-eventos); rota `/sources` no blog/server.py (adapter fino, irmão do /llm) com
tentativas/hits/citadas/sim/secas por tier/excluídas/canário/bypass(unrecognized+unmanifested).
**Verify:** fold unit (join com 2 dispatches concorrentes; orphans; excluded); render do bloco e do
painel com fixture; painel mostra fonte-declarada-sem-chave como perna morta.

## S8 — textos de genótipo: glossário, scaffold, roadmap, dig, calibrate, clerk (design-skills + E4/E5)

CONTEXT.md verbete `Grounding` (R1.1-R1.3 + harvested-never-emitted, com linha *Avoid*); parágrafo
no slot gather-grounding do scaffold (reads harvested; roadmap lido no gather; yield advisory;
seca-suspeita não licencia negativa; scripts logam query no stdout); `state/source-roadmap.md`
SUBSTITUÍDO (skeleton do design-skills §c, Voz REMOVIDA do roster — E5, linhas X/exa/arxiv dos
dados medidos, seed exa-deep com proveniência); `skills/dig/SKILL.md` (fecho = evento
`grounding.finding` + topic file como projeção — E4); `skills/calibrate/SKILL.md` (pack mecânico
por subagente próprio ADR-0014; beat=propose, operador=Voz); emenda clerk nos producer skills
(prosa+brief com ponteiros+pull-channel; devolve slug+custo+resíduos+rationales).
**Verify:** consistência mecânica (grep: zero 'Voz' no roster; verbete referencia os termos que
existem; skills renderizam no edge-render dry-run); revisão minha linha-a-linha (texto é genótipo).

## S9 — E2E smoke + PR

Harvest REAL sobre o store desta máquina (read-only, cursor em scratch): contagem de rows por
fonte/geometry, tabela de yield renderizada com dados reais, painel /sources local. Rodar suite
completa. PR único da branch com o arco (requirements→designs→emendas→slices), corpo com o mapa
de knobs e o plano de rollout (#248: tudo nasce observe).
**Verify:** suite verde + smoke com números reais no corpo do PR.

## Dependências

S1 → S2 → {S3 → S4 → S5, S6} → S7 → S8 → S9 (S6 depende de S2+S4-parcial [session_floor];
S8 depende de S4/S7 pros nomes finais; S3 pode andar em paralelo a S2).

## Fora do plano (declarado)

Espelho OTel exporter (projeção — segue desenhada, implementação adiada: nenhum consumidor ativo
hoje; entra quando Langfuse for ligado); resíduos R4.4 (off-policy/pooling-bias/SOAR-PURPLE 1-0)
= itens de pesquisa da calibragem, não código; interop OTel×OpenInference (segue com o exporter).
