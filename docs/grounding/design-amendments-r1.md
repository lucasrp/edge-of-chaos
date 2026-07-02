# Emendas vinculantes — gate codex, rodada 1 (Loop R)

> O codex (adversarial, full repo access) encontrou 7 defeitos reais nos designs. Cada emenda abaixo
> SUPERSEDE o trecho que nomeia. O Loop P consome designs+emendas como conjunto. Thread codex:
> 019f20cf-189d-7af1-878c-7fcbb5c61930.

## E1 — dispatch_id é identidade real, nunca reconstruída (supersede design-yield §join, design-emissao enxerto A2)

O `_wake_gate` atual é booleano global ("houve dispatch.open depois do último publish"), não
identidade — dispatches concorrentes (operador + heartbeat + dig) roubariam stamps uns dos outros, e
como chave de atribuição do yield isso corrompe o join. **Correção:** `dispatch_id` cunhado no
predispatch (ULID), retornado ao chamador, carregado explicitamente até close/publish (parâmetro, não
inferência), gravado no payload de `artefato.published`, e consumido sob o mesmo lock do wake-gate.
Proibido reconstruir por "último dispatch.open antes do publish".

## E2 [texto original SUPERSEDIDO por E2b abaixo] — dedup por chave estável; retro-harvest é re-FOLD, não re-append (supersede design-emissao §retro-harvest)

Log é append-only sem dedupe (eventlog.append); reset de cursor ou crash entre append e cursor-save
re-emitiria manifests, inflando tentativas/secas/yield (viola ADR-0006 e R2.2e). **Correção:** cada
row carrega `raw_ref` estável = hash(sessionId, toolUseId) (+interface); `fold_grounding` dedupa por
`raw_ref` — a PRIMEIRA emissão vence, re-harvests são no-ops no fold. Retro-mineração com recognizer
melhor emite rows novas apenas para raw_refs inéditos; para reinterpretar raw_refs já emitidos, o
evento novo carrega `supersedes: raw_ref` e o fold aplica last-wins por recognizer_rev — a história
bruta nunca é reescrita, a interpretação é versionada.

## E3 — schema `sources[].interfaces[]` + seção `acts` (supersede o seam "via freeform" em design-emissao §recognizers e os via's atuais do agent.yaml)

O `via` freeform mistura interfaces (exa search + /contents; X v2 + upgrade xai) e até WRITE (gdrive)
— um recognizer derivado disso conflate fonte×interface (R2.2d) e registraria upload como leitura
(viola R1.3). **Correção:** agent.yaml ganha, por fonte, `interfaces[]` read-only estruturado —
`{interface_id, via, idiom, canary, dry_semantics}` — e uma seção separada `acts:` (HITL, ex.
gdrive-upload) que o harvester NUNCA lê. Recognizers derivam de `interfaces[].via`; a prosa
description continua livre. (Os via's que editamos nesta worktree — exa deep, X, gdrive — serão
re-expressos nesse schema no slice correspondente.)

## E4 — o achado do dig vive no LOG; topic file é projeção (supersede design-skills §dig-exit)

Escrever `memory/<slug>.md` como única forma durável cria segunda verdade fora de replay/folds/Cortex
(briefing só lê tattoos method/personality — verificado). **Correção:** o fecho do dig apenda evento
`grounding.finding` (refs, snippets, gap fechado/seco, manifest raw_refs); o topic file, se existir,
é projeção regenerável do evento — nunca a fonte.

## E5 — Voz fora do roster (supersede design-skills §roadmap linha native, e o state/source-roadmap.md stale inteiro)

Voz é diretiva, não leitura (o próprio verbete diz); "Atividade/Voz" como lens de fonte contradiz o
glossário. **Correção:** roster só tem lens mundo/atividade; Claude sessions = substrato/Medium (não
entrada do roster de dig); o arquivo `state/source-roadmap.md` atual é STALE de outra era (aponta
edge-of-chaos, HOME de vboxuser) — será SUBSTITUÍDO, não emendado.

## E6 — genus budget default = BOUNCE_MAX; backstop 15 é opt-in (supersede design-close §knobs)

Hoje genus compartilha BOUNCE_MAX=1 (close.py:1669, :2036); default 15 mudaria custo/comportamento
mesmo com tudo desligado. **Correção:** `EDGE_GENUS_BOUNCE_MAX` default = BOUNCE_MAX (byte-a-byte);
o backstop maior é opt-in explícito documentado como mudança de comportamento.

## E7 — locator do transcript do floor: contratado ou medido-antes-de-gatear (supersede design-close §floor path)

`_identity.project_dir()` deriva do HOME/cwd — numa worktree o project-dir muda de slug
(`-home-roberto-edge-wt-grounding` ≠ `-home-roberto`) e o floor ficaria dark→fail-open, gate que
nunca gateia. **Correção:** resolução por ÍNDICE (procurar `CLAUDE_CODE_SESSION_ID.jsonl` em todos os
project-dirs do store, mais barato que parece: glob único), com `grounding.floor_dark` contado; e a
escada do knob é OBRIGATÓRIA: FLOOR=1 (observe) roda semanas e só promove a FLOOR=2 (gate) quando a
taxa de dark medida for ~0.

## Nits corrigidos

N8: caminho é `blog/server.py:2333` (não `server.py`) — vale onde design-yield/requirements ainda
digam `server.py`. N9: requirements R8.1 corrigido — o source-roadmap.md não está "ausente", está
STALE (formato antigo); a ação é substituir.

---

# Rodada 2 (mesmo thread codex)

## E1b — dispatch_id é PROOF-BOUND (refina E1)

Se o dispatch_id afeta o fold de yield, ele é state-affecting — fora do digest, um publish_fn
poderia publicar com OUTRO dispatch_id sem mismatch, corrompendo o join sem violar o proof.
**Correção:** `dispatch_id` entra no dict do artefato e em TODA a cadeia proof-bound —
`_mint_proof`/`proof_digest`/`verify_proof`/`publisher.publish`/`publish_artefato_atomic` — e os
snippets de publish das producer skills (report/research/map/...) passam
`dispatch_id=art['dispatch_id']`. Mesma classe do slug: campo persistido = campo digerido.

## E1c — contrato de compatibilidade do dispatch_id (refina E1)

**Correção:** obrigatório para publish no LOG CANÔNICO; testes/custom logs injetam ID sintético via
helper test-only; o wrapper legado `eventlog.publish_artefato` é declarado migration/test-only OU
ganha o parâmetro. Opcional-em-produção é proibido (reabriria o join sem identidade).

## E2b — raw_ref é ocorrência BRUTA; interpretação fica no payload (refina E2)

`interface` é interpretação do recognizer — se entrar no raw_ref, um recognizer corrigido muda a
chave e o supersedes não encontra o alvo; e uma tool call com N queries colapsaria em 1.
**Correção:** `raw_ref = (session_id, transcript_line/offset, tool_use_id, occurrence_index)` —
localização bruta estável, nada de interpretação. source/interface/lens/query vivem no payload
interpretado; `supersedes` aponta pro MESMO raw_ref; desempate determinístico por
`(recognizer_rev, seq)`. Ocorrência ≠ leitura-interpretada — duas camadas, como menção ≠ referência.
