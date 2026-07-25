# Grounding iteration — requirements (Loop R)

> Produto do Loop R (research → design → codex-gate). Pesquisa: deep-research 37 agentes, 14 findings
> verificados adversarialmente + 3 probes EMPÍRICOS (medidos, não literatura) + 8 resíduos declarados.
> Raw: `docs/.loopR_research_raw.json`. Interno: varredura da base em `feat/grounding-iteration`.
> Linhagem: exp062 (feedback mecânico > conselho; juiz-preguiça), arqueologia edge-of-chaos (#248:
> observe→advisory→gate; primitivas mortas), conversa operador 2026-07-01/02.

## 0. Objetivo

Deslocar o centro de gravidade do pipeline: **da forma-na-saída para a aquisição-na-entrada, com teto
fixo na saída.** Três teses (todas com evidência própria): contexto é o produto rico e a publicação é
projeção lossy; conselho-no-prompt não move agente, objetivo mecânico move; o revisor-LLM satura em ~2
rodadas e vira ruído.

## 1. Glossário (CONTEXT.md)

- **R1.1** Entrada `Grounding`: a relação afirmação↔evidência rastreável, unificando as instâncias já
  existentes no código (visual_grounding, quote-grounding, gather-grounding). Source = canal (unifica
  no acesso); **a leitura tem sujeito** (lens: mundo/atividade — Voz é diretiva, não leitura); o self
  (recall) é piso do grounding mas **não é Source** (self-reference guard intocado, ADR-0014).
- **R1.2** Gêmeos wake/grounding: mesmas três pernas (recall→atividade→mundo), mesmo manifest (tag de
  geometria), mesma saúde de instrumento; **regras de parada opostas por desenho** — wake nunca bloqueia
  (ADR-0011, perna escura anota e segue), grounding só para com gap fechado-com-fonte ou seca-declarada.
- **R1.3** Escrita no mundo **não é source**: acts (upload Drive etc.) são HITL, fora do manifest
  (precedente: external-state boundary do edge velho). Entrada gdrive já declara os dois papéis.

## 2. Grounding manifest — o registro

**Adotar, não inventar (cravado pela pesquisa):**
- **R2.1** Emitir no vocabulário **OTel GenAI semconv PINADO em v1.37.0** (status Development — pinar e
  registrar a versão emitida) + **OpenInference** para o átomo de busca: span kind RETRIEVER,
  `retrieval.documents`/`document.score` para hits, `tool_call.function.arguments` para a query.
  Lens/geometry/intent viajam como metadata/tags de spans padrão. Langfuse/LangSmith ingerem de graça.
  - *Resíduo aberto (design loop):* mapa de interop OTel gen_ai × OpenInference (vocabulários
    concorrentes) — resolver no Loop P.
- **R2.2** Campos mínimos cravados por **PRISMA-S/Cochrane** (o análogo maduro, 30 anos de uso):
  (a) query **literal copy-paste como rodou** — nunca redigitada/parafraseada, capturada **no momento
  da execução** (MECIR C36; "reconstrução post-hoc é nearly impossible"); (b) data por varredura;
  (c) contagem de hits **por fonte individual**; (d) **fonte × interface como entradas distintas**
  (o mesmo símbolo tem semântica oposta em interfaces diferentes); (e) dedup documentado.
  Barra de qualidade: **reprodutível por terceiro**.
- **R2.3** Persistência no estilo da casa: novo tipo de evento **`grounding.manifest`** no eventlog
  append-only (família: dispatch.open, artefato.published, source.signal, direction.proposed), com
  fold puro para agregação. O espelho OTel (R2.1) é projeção do evento, não a fonte de verdade.

**A contribuição (o branco confirmado — nenhum standard tem):**
- **R2.4** Rótulo **seca-verificada / seca-suspeita** por leitura: em TODO o stack de observabilidade
  verificado, erro é flag booleana — nada distingue conjunto-vazio legítimo de query malformada.
  Seca-verificada exige canário-passou; seca sem canário = suspeita, **não licencia claim negativa**.
- **R2.5** **Canário por fonte, com taxonomia de falha PRÓPRIA** (medido no probe — cada plataforma
  falha diferente, o canário não generaliza):
  | fonte | falha silenciosa (medida) | canário (medido) |
  |---|---|---|
  | X API v2 | **seca falsa**: 13 palavras → 0 hits, HTTP 200, errors=None ('legal AI'=10). Erros reais são LOUD (400) → 200+vazio = over-especificação, nunca sintaxe | `AI lang:en -is:retweet` max_results=10 → sempre 10; <10 = auth/quota |
  | Exa | **lixo confiante, nunca vazio**: query impossível → 5 vizinhos plausíveis sem indicação de baixa confiança. Rótulo de seca NÃO se aplica; risco é preenchimento | `{query:'latest AI research', type:'fast', numResults:1}` → valida auth/latência/billing, **jamais recall** |
  | arXiv | **degradação silenciosa**: http→301 body vazio; campo com typo (`title:`) retorna 44 resultados SEM erro (vs 37 do `ti:` correto); NL longa → totalResults=2.5M | `cat:cs.CL&sortBy=lastUpdatedDate&max_results=1` → https+parser+feed num teste |
- **R2.6** Idiomas de query por fonte moram no **Source roadmap** (instrução operacional
  auto-recompensadora, alinhada ao gradiente — diferente de conselho disposicional, que não move):
  X = 1-3 termos + operadores (`"frase"`, OR, lang:, -is:retweet), recall decai por palavra; Exa =
  linguagem natural descritiva, comprimento não penaliza, `deep` default (medido: único a recuperar
  LeMAJ; 5x latência, 1.7x custo, $0.012/call), `fast` para triagem; arXiv = sintaxe de campo
  (`ti:`, `abs:`, `cat:` + `+AND+`), sempre https. Prior art Cochrane explícito: interfaces limitadas
  forçam re-escrever com menos termos — o caso X documentado em guideline desde antes de nós.

## 3. Wake — telemetria compartilhada

- **R3.1** O delta emite o MESMO manifest com `geometry: ambient`; recall emite linha própria (self).
- **R3.2** No wake a telemetria **observa e nunca gateia**; saúde de instrumento (canário, taxa de
  seca crônica) é agregada pelo mesmo fold das duas geometrias.

## 4. Yield / bandit — aprender qual fonte serve qual intent

- **R4.1** Já existe a metade da recompensa: `fold_source_yield` (eventlog, ADR-0009) sobre
  `source.signal` (que já carrega **similarity** — recompensa graduada). Falta o **denominador**:
  join com `grounding.manifest` (tentativas), dimensões intent × source × lens × geometry.
- **R4.2** **Excluir seca-suspeita do aprendizado** (senão o bandit fossiliza viés de instrumento e
  mata o braço — o caso X teria yield 0 permanente). Confirmado pela literatura: PURPLE (relevância
  semântica ≠ utilidade → recompensa graduada, não binária); SOAR (bandit sobre M fontes heterogêneas).
- **R4.3** Política = **tabela renderizada** (posterior transparente, contagens explícitas, suavização,
  mínimo de tentativas, bônus de exploração declarado), consumida como conselho no briefing/gather.
  **Nunca roteador duro** (cicatriz da ROUTING table). Rollout pela escada do #248:
  observe (painel) → advisory (briefing) → o 3º degrau é PROIBIDO por design.
- **R4.4** *Resíduos abertos (design loop):* como excluir seca-suspeita sem enviesar o estimador
  (off-policy/propensity); ligar ao prior art clássico de pooling bias (Buckley & Voorhees 2004;
  Zobel 1998); verificar 1-0 SOAR/PURPLE (vieram do sweep, 1 verificador).
- **R4.5** Primeiro datapoint já colhido (dogfood do próprio Loop R): exa-deep excelente em entidades
  nomeadas (5/5 canônicas no topo), misto em conceitos compostos (~2-3/5); /contents falha em PMC
  (reCAPTCHA). Semear a tabela com isso.

## 5. Close — teto + resíduos

- **R5.1** Estado atual: `EDGE_BOUNCE_MAX=1` e **hard-fail** ao estourar (close.py ~1929; bounce_budget
  zerado se improve não convergiu, ~2034). A mudança é cirúrgica: **genus limpo + só strikes de revisor
  ao estourar o bounce → PUBLICA com resíduos anexados** (seção "crítica não endereçada"), nunca
  hard-fail. Genus continua ilimitado (mecânico, converge).
- **R5.2** Precedente direto (verificado): **eLife Reviewed Preprints** (artigo + reviews públicos +
  resposta do autor + assessment graduado, anexados como artefato de 1ª classe) e **F1000Research**
  (publish-then-review). Cap explícito de rodadas NÃO tem precedente achado — é escolha nossa,
  divulgada como tal. *Resíduo:* varrer 'single revision round policy' / ARR antes de cravar no doc.
- **R5.3** **PRESS** (peer review DA estratégia de busca, checklist 6 elementos) = precedente para o
  revisor revisar o **manifest** (a busca foi bem feita?) — candidato a check futuro, fora desta iteração.

## 6. Clerk de publicação

- **R6.1** Subagente tipógrafo-despachante: recebe (a) prosa pronta do autor, (b) brief de substância
  com **ponteiros pra disco** (nunca dump de contexto), (c) canal de pedidos tipados de volta.
  Regra dura: **edita forma, nunca cria claim** — demanda substantiva do revisor vira pedido ao autor.
- **R6.2** Devolve: slug + custo + resíduos + rationales dos revisores (leitura fria posterior).
  Precedente interno: `conductor.py` node_briefs/subagent_completer (mesmo idioma, seta invertida).

## 7. Skills

- **R7.1** **`/roberto-dig`** = o gather-grounding exposto standalone: recall-first, condição de parada
  (gap fechado OU seca-declarada, modalidades pagas explícitas), manifest de fábrica, briefing como
  recibo, fecho → topic file na memória. Sem genus, sem close.
- **R7.2** **Skill de calibragem** standalone (separada do grill por ora, contrato em forma de
  abertura para dobrar depois): evidência-primeiro (pacote mecânico: yield, secas, custo, rodadas de
  gate), edge apresenta 3 anomalias + hipótese, saída = mudança escrita no lugar dela (roadmap/yaml/
  glossário/issue) ou "sem mudança, observar N". Beat **propõe** (tier proposed), operador **ratifica**
  (Voz). Pacote de evidência do self montado em passada própria (fronteira ADR-0014).

## 8. Source roadmap + painel

- **R8.1** SUBSTITUIR `state/source-roadmap.md` (o arquivo no disco é STALE de outra era — aponta
  edge-of-chaos e HOME de vboxuser; gate codex N9): seed
  renderizado do agent.yaml (piso never-blank), + idiomas/canários medidos (R2.5-R2.6), + priors de
  intent do operador (exploração→X, científico→arxiv, deep-research→exa), + heurísticas resgatadas
  das primitivas mortas. Calibragem escreve por cima; yield audita.
- **R8.2** Painel `/sources` no blog server, irmão do `/llm` (#55, blog/server.py:2333): utilização por
  fonte (tentativas/hits/citações/custo), saúde de canário, secas por tier, fonte-declarada-sem-chave
  = perna morta VISÍVEL.

## 9. Fora de escopo (declarado)

Dashboard web além do painel; roteador duro (proibido); verificação mecânica de citações do revisor
(fase 2); ledger de acts (upload etc. — fronteira declarada, livro próprio se doer); alterar o wake
para gatear (nunca).

## 10. Gaps declarados do próprio Loop R (seca do research, honestidade PRISMA)

Do completeness-critic (8): SOAR/PURPLE sem verificação 1-0 · off-policy/propensity sem resposta ·
pooling bias clássico não varrido · "prior art 2019 do caso X" sem fonte · canários sem varredura
externa (só probe interno n pequeno) · eLife/F1000 com <2 primárias verificadas · cap de rodadas sem
varredura dirigida · interop OTel×OpenInference. Caveats: OTel em Development (pinar);
quotes Cochrane de versões arquivadas (v6.5 reformulou levemente); claim-de-ausência (R2.4) verificada
contra LangSmith docs, compensada pelos probes.
