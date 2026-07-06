# Ontologia cortex-v2 (episteme + edge + gates) — superset estrito

Fonte: subagente **opus** (ontologia unificada, 2026-07-05), lendo episteme vivo (roberto `frameworkV9/episteme/` + docs) + o grafo do edge (`tools/{eventlog,cortex_provenance,relate,close}.py`). **Fable POUSOU e é o DEFINITIVO** (converge com o opus no núcleo — provenance-planes, gate nunca agrega, cortex-já-é-espinha). Refina 3 coisas: **(1) `:Experiment` só nasce de `experiment.curated`** — interpretação canônica primeiro, inventário canônico depois, cadeia append-only de curadoria; `:Observation` continua proibido de nascer vazio ou fabricado por resumo. **(2) gate-score = MEDIÇÃO** — número guardado raw (O-9: guarda-se o número, proíbe-se a PALAVRA-verdict); nunca valência-typed; o plano `computed` fica **VAZIO por integridade/unreachability**, não por review; valência-sobre-scores só via `gate_score_delta@1` rule_template REGISTRADO, com noise-floor do stream (a lição n=1 do V10). **(3) thread=hipótese=artefato = CORRESPONDÊNCIA, não identidade** — 3 nós (pergunta/hipotese/render); navegação = 2-hop `(thread)<-PROPOSES-(hyp)<-SUPPORTS-(artefato)`; colapsar falsifica H-001. Gate-verdicts = **flat props no `:Artefato`** (não nó, não aresta — episteme dá badge de verdict no nó, MIR-2/3; Cypher-navegável). **Migração = ~180 linhas em 5 arquivos + 1 schema** (`cortex/schema/ontologia.yaml` = o instrumento que MEDE o diff do H-001), forward-only, sem backfill. H-001 = **apoia/lead** (este design é a 1ª observação dele). Resultado completo no task-output `a190225`. Achado de entrada: **o cortex do edge JÁ É a espinha do episteme** (`eventlog.py` = append-only "nada é verdade que não seja evento aqui"; `cortex_provenance.py` já separa `asserted`=folds vs `extracted`=hypothesis) → **re-instanciação BAIXA** (H-001).

## §0 — O eixo que resolve tudo: `provenance_class`
Toda aresta/anotação carrega `provenance_class`. Ele decide UMA coisa: se pode entrar no rollup do `verdict` computado.
**CX-1 (invariante mestra): o `scoreboard`/`verdict` consome SÓ bearings `computed`; `verificar` grita LOUD se qualquer não-computed cair num rollup.** Teste de deleção: apaga os planos judgment+semantic → o módulo de verdict é byte-idêntico → superset provado (aditivos, nunca tocam a integridade).

| Plano | provenance_class | arestas | rigor teto | agrega no verdict? |
|---|---|---|---|---|
| **Evidence** | `computed` | `bearing`; source-yield observation | cravado (earned) | **SÓ ESTE** |
| **Structural** | `asserted` | mentions·distills·cites·supersede·via·deriva_de·tem | — | não |
| **Judgment (gates)** | `llm_judged` | **`assesses`** (reificada) | **lead (teto duro)** | não (metadado navegável) |
| **Semantic (RAG)** | `extracted` | relates_to·in_community | lead | não (hipótese navegável) |

## §1 — artefato = NÓ (não autoritativo)
`artefato` é nó de 1ª classe (folda do evento `artefato.published`; a página renderizada = blob content-addressed = **projeção**, O-1). `thread` = reusa `run`/`step` (colaboração = subgrafo). O artefato carrega a **facet `experimento`** quando é experimento numérico (testa/decision_rule/prediction_hash → observation + bearings computed); report/map/etc = sem facet. Anticipado por `docs/episteme/modelo-projeto-agente-navegavel.md §0.1` (a 5ª-domínio = o mentor/pesquisador).

## §2 — gate-verdicts = aresta `assesses` (a decisão dura, defendida)
Rejeitado: flag na MESMA `bearing` (vazaria — "bearing é computed EXCETO quando o flag diz llm_judged"; todo consumidor teria que ramificar). Escolhido: **tipo de aresta SEPARADO, plano disjunto.**
`assesses {gate: name@v, verdict, rationale, model, prompt@v, surprise?}`, `provenance_class=llm_judged`, `rigor=lead` (teto), `authority=agent`. Defesa por invariante:
- não é bearing → **nunca entra no scoreboard** (valência-computada intacta, HIP-4).
- rigor teto lead **estrutural** → `verificar` grita se um `assesses` reivindicar cravado (LLM não passa no checklist fail-closed).
- anti-HARKing traduzido: congela a **identidade do juiz** (`gate_template@v` + model + prompt@v, num registry `gate_templates` **paralelo ao `rule_templates`**) já que o julgamento não é computável. Gate ∉ registry → quarantine LOUD.
- `authority=agent` sempre (gate nunca emite `review_approved`; humano promove num evento separado, O-15).
- folda de `gate_assessed`, pinado à versão → tunar o gate **não re-julga** os antigos.
**Achado afiado:** o **source-yield NÃO é llm_judged — é fold determinístico (o bandit `fold_grounding_yield`) → `computed`**, uma `observation` com `metric{dist,ci,noise_floor}` no nó `source` (ganha rigor de verdade, pode ir cravado). Dos 5 gates: **source-yield=computed; VoI/Feynman/passabilidade/mentora=llm_judged.** O design força ordenar cada gate por COMO ele sabe.

## §3 — Nós e arestas
Episteme (reusados verbatim): `pergunta·hipotese·modelagem(arm)·experimento·observation` + `bearing`. Threads = `run`/`step`.
**Novos nós (3):** `artefato`{genus, title, content_blob_sha, cites/proposes/distills, persona@v, dispatch_ref; facet experimento} · `community`{level:[community,topic], label, summary, centroid, gate:consolidate@v} (um nó parametrizado, auto-hierárquico) · `source`{ref, kind}.
**Novas arestas:** STRUCTURAL(`asserted`): `mentions`(artefato→run)·`distills`(artefato→community/artefato)·`cites`(artefato→source). JUDGMENT(`llm_judged`): **`assesses`**(→artefato). SEMANTIC(`extracted`): `relates_to`(artefato↔artefato)·`in_community`. Embeddings = **atributo de nó** (o substrato que `relate.py` consome pra nominar `relates_to` — "cosine nominates, author disposes").
**Schema (drop no `ontologia.yaml`):** enum `provenance_class:[computed,asserted,llm_judged,extracted]` + registry `gate_templates` (curado por humano, GLO-1) + `controlled_paths` pro pen checar `gate∈registry` no write.

## §4 — Reflexão + tuning
A reflexão consome os planos judgment+evidence (+ outcomes) e **PRODUZ uma proposta** — output = um `artefato` genus plan/critique (a cognição `ed-calibrate`) propondo `gate_template@v+1` / pesos de source / persona@v deltas. **Humano promove** (`review_approved`, O-15) → vira PR de schema. Verdicts velhos ficam pinados ao gate@v que os fez. Tunar gate = **versionar um instrumento do schema** (= episteme versiona `rule_template@v`). "agente propõe, humano promove."

## §5 — As 4 costuras (por que a integridade segura)
`fold(events)→Projection` (read; os 4 planos foldam por 1 função) · `Recorder` (a caneta única; `assess`/`consolidate`/`relate` impõem o teto no WRITE — Locality) · `scoreboard`/`verdict` (interface **INALTERADA** — só vê `computed`; os 3 planos novos são invisíveis a ele = a profundidade que protege o episteme) · `verificar` (checks aditivos LOUD: `assesses.rigor≤lead`, `gate∈registry`, `authority=agent`, nenhum não-computed em rollup).

## H-001 (superset): SUPPORTED (lead)
Plano-compute do episteme inalterado byte-a-byte. Tudo adicionado vive em planos NÃO-agregantes. Diff: 3 nós (artefato/community/source) + ~6 arestas + enum `provenance_class` + registry `gate_templates` + CX-1..CX-7 (todos aditivos; nenhum relaxa regra do episteme).

**LOAD-BEARING (implementar PRIMEIRO):** o eixo `provenance_class` + CX-1 no `verificar`. O resto é aditivo e incremental — bota essa invariante e a integridade da valência-computada fica garantida enquanto os planos navegáveis crescem.

**Calls defaulted (ponytail):** community/topic = 1 nó parametrizado (2 só se topic precisar de campos próprios); mentions/distills/cites = nomes de domínio pra legibilidade (colapsáveis em via/deriva_de/tem pra diff menor).

## §6 — Nó `parceiro` (operador, 2026-07-05): a constelação social
Mais uma entidade de 1ª classe: **parceiro de trabalho** — empresa, pesquisador, membro da equipe, usuário de git. O roberto sabe de cor o pessoal do trabalho do operador; o grafo também deve saber. Props: `{name, kind: empresa|pesquisador|equipe|git-user, domain?, contact_ref?}`; arestas: artefato-`PARA`->parceiro (o documento FEITO pra pessoa), parceiro-`MENTIONS`-tópicos/entities. `provenance_class`: asserted quando declarado, extracted quando minerado.
**Por quê (duplo):** (1) **documentos PARA pessoas** — a persona-alvo construída-de-dados (grill-knows-the-mentee) ganha substrato: o report calibra ao parceiro real; (2) **o report compartilhado é o nosso VIRAL** — cada documento passável entregue a um parceiro difunde o edge-of-chaos. O crescimento do produto anda pelo grafo social.
**Verificado no roberto (2026-07-05):** "Julio" JÁ existe como `:Entity` extraída (graphiti, com sumário real de colaboração). O parceiro **EMERGE da extração** — não nasce só declarado. Logo o desenho é **promoção, não mintagem**: a Entity-pessoa extraída ganha a marca `parceiro` (asserted, HITL ou heurística conservadora), mantendo o mesmo nó e as arestas/communities que já tem. As communities já o colocam no contexto certo de graça.
