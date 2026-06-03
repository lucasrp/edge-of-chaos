# Handoff — Edge of Chaos: reconstrução da era limpa (`~/edge-clean`)

**Data:** 2026-06-02 · **Operador:** lucasrp (mktccuidarmais@gmail.com) · **Instância mentora:** ed
**Repo genótipo:** `lucasrp/edge-of-chaos` (gh: ver caveat abaixo) · **Idioma:** PT-BR

---

## Objetivo desta linha de trabalho

Reconstruir um edge-of-chaos **legível** num repositório novo (`~/edge-clean`), partindo de
uma base refatorada limpa e trazendo de volta SÓ o que vale de hosts da "era boa". O alvo
não é "menos LOC" e sim **menos carga cognitiva** (ver `[[project_goal_legible_codebase]]`).

A próxima sessão deve **retomar o `/pocock-grill-with-docs`** (foi pedido e interrompido para
gerar este handoff) e especificar item a item a nova versão, produzindo `CONTEXT.md` + ADRs.

---

## A descoberta central da sessão (não duplicada em outro artefato)

O sistema NÃO degradou uniformemente. Cada subsistema tem trajetória própria, e a regra
"qual época usar" **varia por função**:

- **Provisionamento (install/edge-apply/edge-render/agent.yaml) MELHOROU** → usar o ATUAL (`~/edge`).
- **Pipeline de publicação (consolidate-state/gates) DEGRADOU** → usar o rui (advisory).
- **Runtime `tools/_shared/` INCHOU 5→22 arquivos** (1.986 LOC herdados do rui vs **8.483 LOC nascidos pós-rui**).

**Padrão-mestre provado por código (a chave de tudo):** na era boa (rui), a lógica do beat
morava **na SKILL** (`rui-heartbeat`, 649 linhas de markdown) + 95 linhas de bash preflight.
A acreção **moveu a lógica para runtime determinístico .py** (`dispatch_runtime` 2390 +
`protocol_runtime` 504, que NÃO existiam). Isso é o ADR-0001/0002 em estado puro: forçar um
modelo fraco via código. **Com modelo recuperado, mover a lógica de volta para a skill (prompt)
É o enxugamento** — não perde feature, devolve a decisão ao modelo.

**Corolário (insight do operador, validado no código):** "feature legítima que degradou" ≠
"andaime descartável". Ex.: `operator_pressure.py` (1585 LOC) é feature boa (resumir o chat do
operador) que virou maquinário. A **forma magra já existe e rodava**: o "rolling chat digest"
da skill `rui-heartbeat` §1a0 (`digest anterior + delta → novo digest`, um markdown + offset).
**Regra de reconstrução:** para cada feature ①, procurar a forma intermediária do **rui** ANTES
de reescrever do zero. O rui é o gabarito da "versão magra que funcionava".

---

## Taxonomia de destino (substitui "fonte por cluster")

Cada arquivo de runtime cai em um de 4 destinos:

| Destino | Critério | Exemplos |
|---|---|---|
| **Recuperar forma rui** (lógica→skill) | feature ① que virou runtime .py | operator_pressure, dispatch_runtime, protocol_runtime, signal_runtime, continuity, health_runtime |
| **Cortar** | enforcement puro (só força modelo fraco) | artifact_supervisor, skill_policy, skill_inbox |
| **Manter atual** | melhoria real | capability_runtime (já limpo no #1), artifact_rite (nosso), install/edge-apply, search citation-boost |
| **Plumbing** (trazer, investigar inchaço) | infra burra que engordou | telemetry (277→1068), router_client (367→873), intervals, jsonl_runtime |

Ainda NÃO classificado item a item — é o trabalho da próxima sessão.

---

## Estado concreto: `~/edge-clean`

Repo git novo, 1 commit (`6be57b2`), 230 arquivos, 10.886 LOC. Base = working tree de
`alexlopespereira/agent-template` @ `4ca2d6b` (30/03), history do Alex descartado de propósito.
Genealogia: operador mandou o código dos hosts → Alex refatorou/limpou → este template →
maio (acreção que degradou). **O `consolidate-state`/supervisor "que falta" no template é
justamente o andaime que NÃO queremos.**

**Documentos de decisão já escritos (LER, não recriar):**
- `~/edge-clean/CLUSTERS.md` — 8 clusters A–H + segmentação do runtime em C1–C6.
- `~/edge-clean/MERGE_MANIFEST.md` — o que trazer de rui/nailton vs descartar, com 9 pontos ⚠️ abertos.
- (Do template, do Alex, contexto útil: `REPLICATION_BLUEPRINT.md`, `PLACEHOLDER_MANIFEST.md`, `README.md`.)

**Staging coletado (`~/edge-clean/_incoming/`, só código, ~3.5M):**
- `rui/` — 198 tools, 12 search, 9 blog-scripts, **22 skills reais** (PT-BR, em `claude-skills/`), 8 bin. Era boa (abr), pipeline advisory.
- `nailton/` — 20 tools, 4 search, 52 memory. Era-mãe (mar), `consolidar-estado` PT-BR original.

---

## Fontes (hosts SSH) e o que cada uma representa

| Host/path | Época | Papel | Pipeline |
|---|---|---|---|
| `/root/nailton` (ssh nailton) | era-mãe (04/03) | mais antigo da frota; 258 entries; **código congelado** (0 arquivos <30d), só conteúdo novo | `consolidar-estado` PT-BR |
| `ssh rui` `~/edge` | era boa (abr) | gabarito da forma magra; 454 entries; **working tree sujo (400 untracked)** | review-gate **advisory (exit 0 always)** |
| `~/edge` (local) + ssh petertosh/roberto | atual | degradado; install melhorou | review-gate **enforcing (#538)**, 39 gate-matches |

**Cuidados:** NÃO há fevereiro em lugar nenhum (repo começa 03; "reports de fim de fevereiro"
da memória do operador = entries de início de março do nailton). NUNCA `reset --hard` host
(epigenética produzida). rsync DEVE ser allowlist — disco estourou 2× (blog 7G, gmail-venv 143M);
excluir sempre: `.venv` E venvs com nome custom (gmail-venv), `blog/entries`, `blog/diffs`,
`meta-reports`, `builds`, `reports`, `*.db`, `secrets`, `*.env`.

---

## Diagnóstico em aberto: por que petertosh degradou (thread paralela)

Causa-raiz NÃO é nosso #2 (a Phase 0.2 do Rite gate está `completed`/warn-only, saudável).
São 3 falhas da acreção de maio: (1) **review-gate unavailable** → publish `degraded`;
(2) **blog-publish.sh exit non-zero** + publish manual `degraded`; (3) **issue #543** —
`consolidate-state` Phase 5 `digest: name 'tools_dir' is not defined` + `sqlite_vec` import.
Há um clone de diagnóstico em `~/work/543` (loop pocock-diagnose iniciado, não concluído).
Decisão do operador: em vez de consertar a acreção, **reconstruir limpo** (esta linha de trabalho).
→ #543 provavelmente fica obsoleto quando edge-clean substituir o runtime.

---

## 9 pontos ⚠️ a resolver no grill (detalhe em MERGE_MANIFEST.md)

agent-index/search vs edge-index/search (duplicata?) · consolidar-estado(nailton) vs
consolidate-state(rui) · app.py(rui) vs server.py(Alex) · qual versão do núcleo memory
(personality/metodo/rules-core) · skill `lazer` (removida no genótipo "agents should work")
· notify.sh (credencial hardcoded?) · conversation_miner / edge-yaml-self · idioma das skills
(rui PT-BR vs atual EN) · hooks (enforcement de borda ≠ de qualidade — manter?).

---

## Trabalho de genótipo JÁ entregue nesta sessão (no repo `lucasrp/edge-of-chaos`, não no edge-clean)

Contexto, não refazer — ver PRs: **#554** (+fix #556) colapso capability source.X / ADR-0002;
**#558** validate_rite; **#560** edge-rite-check CLI; **#562** Rite gate warn-only + role + trim
review-gate. Tudo mergeado e propagado a local/roberto/petertosh. Regra do operador: todo
código via `/pocock-tdd`; só mergear o que está testado e verde.

---

## Suggested skills

- **`/pocock-grill-with-docs`** — RETOMAR (era o pedido ativo). Especificar a nova versão item
  a item, produzindo `~/edge-clean/CONTEXT.md` (glossário) + ADRs. Começar pela taxonomia de
  destino e pelos 9 pontos ⚠️. Caminhar cluster a cluster (C1–C6 primeiro — é onde mora a decisão).
- **`/pocock-to-prd`** ou **`/pocock-to-issues`** — depois do grill, transformar o plano de
  merge em issues executáveis (um por cluster/feature a recuperar).
- **`/pocock-tdd`** — para cada feature recuperada na forma magra (red-green).

## Regras operacionais (caveats de ambiente)

- **gh:** conta default `lucasrp_TCU` é EMU **bloqueada** no repo. Antes de qualquer escrita no
  GitHub: `gh auth switch --user lucasrp && gh auth setup-git`; restaurar `lucasrp_TCU` ao fim.
  Ver `[[reference_gh_account_for_genotype]]`. (edge-clean é local, sem remote ainda.)
- **Disco:** `/` estava 93-100% cheio. Conferir `df -h` antes de copiar; staging já enxuto.
- Genótipo do repo principal segue o loop issue→clone→PR→merge→close (`[[feedback_genotype_workflow]]`).
  edge-clean ainda é repo local exploratório — sem remote, sem PR.
