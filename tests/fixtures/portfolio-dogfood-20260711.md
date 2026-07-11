# Portfólio de wayfinds — ed × operador
<!-- DOGFOOD #131: este arquivo É a rotina grill-wayfind rodando à mão, como se já especificada.
     Sob o design final: cada linha daqui = evento no ledger (ticket.opened/closed, frontier.moved,
     depends_on) projetado no cortex; este md = a vista humana + índice canônico (via #130).
     Gambiarra usada CONSCIENTEMENTE como piloto — a última vez em substrato emprestado.
     Contrato da sessão 2026-07-11: operar por este mapa até o fim; no fim, voltamos AQUI e o
     diff da sessão (seção final) é o teste: custo de reconstrução = ler o diff. -->

**Identidade (lei, operador 07-11):** este portfólio registra o emprego do MENTEE, nunca o do ed.
O ed é mentor — filma, cura, questiona o mapa; não é definido por ele. Frontier direciona o mentee;
o ed segue seu próprio contrato (wake, abate, curiosidade, propostas com autoria própria).

**Direction (o juízo, não o kanban):** a noite separou dois órgãos — estado (cortex) e comunicação
(report para leitor). Os 3 mapas ativos servem essa separação: M2 termina de dar ao estado seu
substrato nativo; M1 investe o report da única função que restou (o leitor); M3 é o exemplar vivo
de M1 chegando a um leitor real. M2 > M1 > M3 em prioridade estrutural; M3 > tudo em urgência de
gesto (só depende de você ler).

## M1 — etapa-da-forma (ATIVO)
*Visão: report purificado ganha a forma que ensina — reestrutura-conservadora + visual que constitui.*

| id | ticket | estado | depende de | rationale |
|---|---|---|---|---|
| M1.1 | spec fable (`docs/specs/etapa-da-forma.md`) | FECHADO 07-11 | — | 537 linhas, gate 2 camadas |
| M1.2 | dry-run: calibração do juiz de conservação | FECHADO 07-11 (4 fixes: piso-no-render-real + duas garras + contrato no envelope + alias prose/md no renderer) | — | história completa em out/RESULTS.md; tudo vira M1.6 |
| M1.3 | dry-run: arms B–E + kit cego | FECHADO 07-11 — ratios 0.96–1.03, zero fallback, 5 SHAs distintos; gates FUNCIONARAM (E atuação-2 vetada legitimamente, publicou a 1ª) | M1.2 | kit: ~/forma-impl-opus/drafts/forma-dryrun/out/ |
| M1.4 | leitura cega do operador (7 páginas P–V, 2 sentadas) | **SUSPENSA como confirmatória** (codex ultra 07-11: cegamento vazou por contagens; figuras TODAS mortas no gate de proveniência → contraste de dose visual não existe nos artefatos; PREREG sobrescrevível) | M1.3 | pode ler como EXPLORATÓRIA; confirmatória exige: re-permutação sem contagens, renderer único, ≥1 figura viva nos arms visuais, corpus fresco |
| M1.4b | consertos do kit (14 findings do codex → triagem no M1.6) | ABERTO | — | os 8 blocking-if-gate: side-channel, dose-morta, prereg-mutável, inventário-vazio-passa, juiz≠render-real, prefixo-8k, enriched-indistinto, piso-inflável |
| M1.5 | decisão regra-vs-agência (C>B ∧ E>D, re-roll) | BLOQUEADO | M1.4 | pré-registrado; aposta do ed: ponteiro>regra |
| M1.6 | revisão do spec com os achados do dry-run | ABERTO | M1.2 | piso mecânico + juiz claim-com-explicação viram texto normativo |
| M1.7 | implementação real no genótipo + deploy | BLOQUEADO | M1.5, M1.6 | só após vencedor conhecido |

**Frontier M1:** M1.3 terminar (agente 3 rodando) → te chamar pra M1.4.

## M2 — memória nativa: ledger & lentes (ATIVO)
*Visão: um ledger (eventlog), lentes por operação (episteme=Atividade/assemble; wayfinder=Direction/grill); Voz=md-to-mem.*

| id | ticket | estado | depende de | rationale |
|---|---|---|---|---|
| M2.1 | #130 md-to-mem S1–S6 + fiação briefing | FECHADO 07-11 | — | 25/25 verdes; working-tree |
| M2.2 | consumo I3/I4 (quente/recall janela-por-tipo; curado>desejado) | ABERTO | — | pequeno; o que falta do #130 |
| M2.3 | piloto: injetar `wayfinder-nova-producao.md` + canon | FECHADO 07-11 (inject sha 3f78a530, canon eleito, docs_at confirma) | — | o rito inteiro rodou em 2 comandos; gambiarra oficialmente mais cara |
| M2.4 | inscrição: driver do episteme = ligação forçada (ablação) | FECHADO 07-11 (seq 1003, ulid 01KX7R9F, falsificador delta-reconstrução >0) | — | o próximo mentor cobra com evidência na mão |
| M2.5 | spec episteme-lens (racionalizador sessão→atividade, tier-hipótese) | ABERTO → mapa fino | dig-prior-art | ver `lentes-atividade-direction.md` (wayfind dedicado deste esforço) |
| M2.6 | spec wayfinder-lens (eventos+projeção+gate do mentor) | ABERTO → mapa fino | dig-prior-art | idem — o M2 ganhou mapa pocock próprio |
| M2.7 | canon vs prune (artefato eleito não esfria) | BLOQUEADO | prune não existe | só fold travado por teste, honesto |
| M2.8 | contrato de divergência da wayfinder-lens (anti-cabresto) | PROPOSTO — **autor: edge** | — | mapa DESCREVE nunca AUTORIZA; propostas do edge com autoria própria ficam filmadas mesmo não-ratificadas; lazer/delta/diverge MAP-BLIND por contrato; fechamento de ticket pede valência (apoiou/refutou) |

**Frontier M2:** M2.4 (inscrição, gesto barato) → M2.6 com o diff DESTA sessão + M2.8 como insumo.

## M4 — o tier PESSOA: leveling de primeira classe (ATIVO — issue #132)
*Visão: "o emprego dele é sobre MIM" — medir o mentee (perfil/escada/placar/amarração) para crescer o mentee; lente-pessoa sobre o mesmo ledger.*

| id | ticket | estado | depende de | rationale |
|---|---|---|---|---|
| M4.1 | issue #132 com a extração completa | FECHADO 07-11 | — | protótipo roberto (~/leveling) como norma; rail grill_writeback.leveling já existe |
| M4.2 | spec lente-pessoa (eventos tipados, escada mecânica, colher no assemble, banca no grill) | ABERTO | — | mesma divisão filmagem-vs-cognição da #131 |
| M4.3 | port da skill roberto pro genótipo + migração ~/leveling → ledger | BLOQUEADO | M4.2 | paridade antes de aposentar o substrato emprestado |

**Frontier M4:** M4.2.

## M3 — report do Felipe (ATIVO, urgência de gesto)
*Visão: o exemplar do report purificado chegando a um leitor real.*

| id | ticket | estado | depende de | rationale |
|---|---|---|---|---|
| M3.1 | report publicado no roberto + Drive | FECHADO 07-11 | — | rito 11 estágios, review duplo advisory |
| M3.2 | revisão do operador | ABERTO — CONTIGO | — | tu disseste "eu vou revisar" |
| M3.3 | envio ao Felipe | BLOQUEADO | M3.2 | nunca sem tua revisão |
| M3.4 | fix 1-linha rito blog_dir=None (genótipo) | ABERTO, DESBLOQUEADO | — | crash Path(None) contornado no call-site |
| M3.5 | dispatch.open órfão no log do roberto | ABERTO, trivial | — | inofensivo; higiene |

**Frontier M3:** M3.2 — só depende de você.

## FILA GENOTYPE (higiene, issues abertas 07-11)
- **#133** filmar sessões do grok CLI (3ª superfície; padrão `quente._include_codex`) — ABERTO
- **#134** agent.yaml bonitinho (rotas/auth/billing/adversarial declarados; declared-dark; painel /llm) — ABERTO; caso fundador = grok Build queimando free-tier em silêncio
- **#136** onboarding first-run (provision→seed→episteme-filma→PRIMEIRA SESSÃO É GRILL→só então beat; heartbeat nasce desligado) — ABERTO

## PAUSADOS / FORA DO PORTFÓLIO
- grok-as-builder (free tier morreu; achado registrado; retomar só por decisão tua)
- PR #129 (aguarda teu merge) · rotação da XAI key (recomendada, contigo) · #131 spec formal (alimentada por M2.5/M2.6)

---

## DIFF DA SESSÃO 2026-07-11 (o teste do dogfood: reconstruir ≈ ler isto)

**M1 forma**: spec fable + dry-run A–D renderizados (E em juízo; montagem cega pendente).
Achado de spec: 3 calibrações do juiz de conservação (literal→veto-tudo; superficial→lobotomia
60%; estável = piso words_ratio 0.8 + juiz claim-com-explicação) — M1.6 alimentado.
**M2 memória**: M2.1–M2.4 FECHADOS (md-to-mem implementado+fiado; piloto inject+canon rodou;
inscrição do fio seq 1003). Nasceu o mapa fino `lentes-atividade-direction.md` — nele:
dig 5 pernas resolvido (topic file em memory/), spec fable escrita, design-it-twice (4 desenhos
→ híbrido: canetas-verbo + portfolio_at único + Turn-açúcar-com-eco + port GraphStore) em
adendo, backfill_days no agent.yaml. #131 carrega o design COMPLETO (~30 comentários; ler antes
de qualquer spec de memória). M2.8 (anti-cabresto) PROPOSTO por ed.
**M3 Felipe**: M3.1 fechado (publicado no roberto + Drive com SHA). M3.2 CONTIGO.
**M4 pessoa**: nasceu (issue #132; protótipo = skill leveling do roberto).
**Fila genotype**: #133 (grok 3ª superfície), #134 (agent.yaml declarativo), #136 (onboarding:
primeira sessão é grill). Grok-as-builder: morto no free-tier (achado).
**Telescópio**: sessão do roberto filmada ao vivo — evidência: ledger-de-2-camadas orgânico,
fractal→confissão→teste→lift 1,12×, exp092 (6 arms de INTERFACE), "pare de re-derivar".
**Leis novas do operador**: tudo-a-posteriori · eval-em-todo-grão (no agregado) · GT-bisect ·
claims-suaves · conversa=interface-suficiente · dig=flare (bom dig AUMENTA o resolvível).
**PENDÊNCIAS**: (a) teu go pro opus-TDD das lentes (spec pronta); (b) tua leitura do Felipe;
(c) ratificar: taxonomia 5 grãos · curado-decai-por-escassez · M2.8; (d) leitura cega da forma
quando o kit sair; (e) teste-do-wake no roberto (falsificável: te contextualiza sem tu explicar).
