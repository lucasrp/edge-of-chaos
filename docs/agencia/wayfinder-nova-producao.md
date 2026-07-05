# Wayfinder — Nova produção (cortex + episteme + 3 atos + gates-metadado + artefato-JS + reflexão)

Charted 2026-07-05, no fim de uma noite de grill que fechou o DESENHO. Este mapa é a rota desenho → implementação. O **grill (leveling/mentor) é DEFERIDO** — a cereja em cima do grafo navegável, effort próprio depois.

## Notes
- **Domínio:** redesign da produção do edge (edge-next), pós-diagnóstico "oco incompreensível → agência = Feynman".
- **Consult:** /ed-dig, /pocock-grilling + /pocock-domain-modeling, /pocock-prototype, /pocock-codebase-design, /pocock-tdd.
- **Standing prefs:** Feynman-como-PONTEIRO (não verborragia; escopo fino "nesse sentido"); gates de produção IMPESSOAIS (conceitos do Feynman, não a persona — o conluio self==juiz é medido, 2404.13076); tudo episteme-native (hipótese/thread/artefato = uma entidade c/ falsificador+valência); grafo navegável = estrutura × julgamento × semântico; loop termina POR FORA (não "até o juiz gostar"); heavy work = subagentes opus em background; **começar de MERGE LIMPO**. Memórias-âncora: `agency-is-feynman`, `dig-3act-production-grounding`, `grill-knows-the-mentee`, `report-shareability-regression`.
- **Provas prontas:** experimento validou "seja Feynman > regra descritiva" (P1/P4) + "gate impessoal resiste à fantasia" (P3) — `drafts/feynman-exp/`. Dig aterrou os 3 atos + gates no mundo — `memory/dig-3act-production-grounding.md`. Exemplar da forma (ato-3) = o blog de lazer `edge-of-chaos.netlify.app` (single-file interativo).

## git-consolidate: Fechar o merge parkado → main limpo
Blocked by: —
Status: resolved — 2026-07-05: merge fechado (6938bdd), doctrine-review (ad9db43: calibração restaurada, X-first drop aceito), wake-quente incluído (71eb9eb), PUSHED origin/main=ad9db43. Follow-ups: #72 agent.yaml, #73 glossário.
Type: Task
### Question
Repo mid-merge em `consolidate-2026-07-05` (19 conflitos JÁ resolvidos no working tree; agent.yaml restaurado pro ed). Falta: o flip do eventlog (`winning_manifest_rows` + teste órfão `test_winning_manifest_rows.py`), rodar a suíte inteira como gate, commitar o merge, foldar `session/agencia-core-exp` (drafts), reconciliar com origin (local divergiu 50×27). **Nada abaixo constrói sem base limpa.**
### Answer

## episteme-ontology: A ontologia concreta do episteme
Blocked by: —
Status: resolved  — asset: `ontologia-cortex-v2.md` (episteme retrieved; opus+Fable convergem; o cortex do edge JÁ é a espinha; migração ~180 linhas)
Type: Research
### Question
O schema REAL do episteme: entidades (Hipótese/Bearing/Observação), falsificador estruturado congelado-por-hash (anti-HARKing), valência por régua total (`delta_ci@1`), eventos append-only, grafo. É o gabarito onde artefato/thread/gate-metadado se encaixam.
### Answer

## gap-map: O que falta pra fechar a perna (contra o código)
Blocked by: —
Status: resolved  — B+D = persistir-o-que-já-computa (fiação); ver `design-nova-producao.md §11`. Ordem: git-consolidate → B+D → A ‖ C
Type: Research
### Question
EXISTS-live/dormant/fused/MISSING para: (B) gates-salvam-metadado, (C) artefato-JS-single-file/Netlify, (D) RAG-semantic-link, (A) prontidão do cortex. Separa fiação (só ligar) de build novo. Complementa o production-map já feito (produtor monolítico, ato-2/persona AUSENTE).
### Answer

## cortex-episteme-schema: Adotar o schema episteme no cortex do edge
Blocked by: episteme-ontology, gap-map, git-consolidate
Status: open
Type: Grilling
### Question
Como o cortex atual (`communities.py`, neo4j, `cortex.py` port) passa a hospedar hipótese/thread/artefato como nós com arestas valenciadas/bearing — mantendo o port estável (recall·surf·node·search)?
### Answer

## gates-as-metadata: Gates persistem a análise como metadado navegável
Blocked by: cortex-episteme-schema
Status: open
Type: Prototype
### Question
Cada gate (VoI/conflito, Feynman-real, passabilidade, crescimento) grava o veredito como metadado estruturado no nó (= a valência do episteme) + feedback de source-yield de volta pro bandit da source-roadmap. Prototipar o schema. (o editorial-compass = protótipo vivo do gate-1.)
### Answer

## three-act-split: Quebrar o produtor monolítico em 3 atos grounded-gated
Blocked by: gates-as-metadata
Status: open
Type: Task
### Question
Escolher / Mentorar-voz / Visual — cada ato com grounding próprio + gates próprios, loop localizado. Hoje = 1 grounding + close monolítico; ato-2/persona ausente. Wire "seja Feynman" no escritor + os gates impessoais.
### Answer

## js-interactive-artefato: Artefato = HTML+JS single-file (esquema Netlify)
Blocked by: three-act-split
Status: open
Type: Prototype
### Question
Tornar o single-file interativo um genus de primeira classe (a skill `prototype` do relicário já fazia). Regras: NÃO forçar interação; ancorado em dado real; roda (render→ver→revisar); e o gate "a interatividade ENSINA?" (white-space, arxiv 2606.31012).
### Answer

## rag-semantic-link: Acordar os embeddings → artefato↔community↔tópico
Blocked by: cortex-episteme-schema
Status: open
Type: Task
### Question
Ligar os embeddings dormentes (`recall.py` 16/16, hybrid g.search documentado-e-dormente) como arestas semânticas artefato↔community↔tópico. Terceira camada do grafo navegável. (fiação-antes-de-adoção.)
### Answer

## reflection-skill: A reflexão que navega o grafo e TUNA
Blocked by: rag-semantic-link, gates-as-metadata
Status: open
Type: Grilling
### Question
A skill de reflexão (que o edge antigo tinha) navega o grafo (estrutura×julgamento×semântico) e afina gates/sources/persona **um eixo por vez** — "se tuna na reflexão". O self olhando a própria obra; o tuning localizado que o feedback-disjunto impedia.
### Answer

## grill: A cereja — leveling/mentor em cima do grafo (DEFERIDO)
Blocked by: reflection-skill
Status: open
Type: Grilling
### Question
O grill (conhecer o mentee, leveling, o meta-grill "por que você faz isso?") em cima do grafo navegável. Deferido de propósito — "a cereja do bolo, effort próprio depois". Não puxar antes da base existir.
### Answer

## aceite-roberto: Deploy consolidado + research CEGO no roberto (o critério de "agência iterada")
Blocked by: gates-as-metadata, three-act-split
Status: open
Type: Task
### Question
Deploy da versão nova no roberto (bundle; inclui wake-quente), deixar criar/atualizar o KG, e rodar um /ed-research genérico CEGO (sem dizer o tema) — julgado como leitor-faminto-de-contexto/passável-pro-colega. O operador dá o veredito. É ISTO antes do grill.
### Answer

## final-dashboard-onboarding: O FINAL do arco — a superfície humana
Blocked by: reflection-skill
Status: open
Type: Task
### Question
Dashboard = console compartilhado user↔edge, EMERGE dos artefatos JS (#69/#70), não build à parte. Onboarding = persona-bootstrap (novo mentee → template persona → meta-grill "por que você está aqui?"). O onboarding É o primeiro grill. Multi-persona DENTRO DO ROSTER só (FLEET.md): roberto=jurídico, petertosh=CRM. gauss/bobmarley/rui = usos do edge-of-chaos FORA da fleet — contexto conceitual, NUNCA alvo de deploy/mexida (operador 2026-07-05).
### Answer
