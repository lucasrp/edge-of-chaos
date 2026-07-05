# B — Gates persistem metadado + curadoria de sources + o ATO artefato→source

Achado do gap-map: **o grafo já COMPUTA os sinais e joga fora.** B é *persistir-o-que-já-se-calcula* — fiação, não build novo.

## B.1 — Persistir o verdict do gate (pare de descartar)
Hoje: `run_close` computa 11 dims + strikes + overall (`_mint_proof` → `proof["verdicts"]`), `publisher.publish` lê só `verdict.get("unaddressed")`, e `project_artefato` **nem recebe o verdict**. Fix simétrico e pequeno:
- `publisher.publish`: ler `verdict.get("verdicts")` e passar `gate=` em `publish_artefato_atomic` → um campo novo no payload, no MESMO batch atômico (sem novo tipo de evento, replayável).
- `project_artefato`: `SET` flat props no `:Artefato` (NÃO um nó, NÃO uma aresta — episteme dá badge de verdict no nó, MIR-2/3; Cypher-navegável):
  `a.gate_rubric='gate_rubric@1'`, `a.gate_pass`, `a.gate_strikes_n`, `a.gate_feynman_<dim>`, `a.gate_regular_<dim>`, `a.gate_rationales='<json>'`.
- `gate_rubric@1` = sha256 do canonical-JSON de `DIMENSIONS + DIMENSION_WEIGHTS + os 2 focus prompts` — carimbado no payload. Editar a rubrica = versão nova; verdicts velhos ficam pinados à sua (disciplina GLO-13).
- **provenance:** `provenance_class=llm_judged`, `rigor=lead` (teto duro), `validity=inferred_default`. NUNCA agrega no `verdict` (CX-1). O `verificar` grita se um verdict-de-gate reivindicar cravado.

## B.2 — Curadoria de sources (o feedback que faltava)
Hoje: `grounding_yield.py` é um bandit real, mas o reward é **cite-cosine**, não o resultado do gate. Fix:
- O mesmo evento `gate.scored` é o **reward que falta**: faça JOIN dele no `grounding_yield` por **`dispatch_id`** (a chave de join já existe) → o source-yield aprende do **RESULTADO do gate**, não só de cosine. Resolve o *"pago pra exa/x e nunca vejo usar"*.
- O `source-yield` é o único gate no plano **`computed`** (fold determinístico, bandit posterior com `metric{dist,ci,noise_floor}`) → é uma `observation` no nó `source`, e ganha rigor de verdade (pode ir cravado). Os outros 4 gates (VoI/Feynman/passabilidade/mentora) são `llm_judged`/lead.

## B.3 — O ATO: artefato virando source (fecha o laço)
**Um artefato, quando INTEGRADO, vira uma `source`** — o edge se aterra na própria obra. É a mudança-de-estado no nível do conhecimento (o degrau da "rampa pro mundo", mas no grafo).
- **É um ATO (episteme):** writes são ACTS. A promoção artefato→source é um **evento de integração**, **HITL/autoridade** (`review_approved{authority:reviewer}`, nunca automático — reviewer≠asserter). Não é o edge se auto-promovendo em silêncio.
- **Ontologia — zero tipo novo:** o artefato JÁ é nó. O ato o torna `cites`-able / o adiciona ao pool que o `gather-grounding` lê (a `source-roadmap` / o corpus), e o `source-yield` (computed) passa a rastreá-lo. A curadoria vira **auto-referente:** o edge aprende qual da própria obra é a melhor fonte (o `editorial-compass` integrado = uma source que o edge lê e monitora).
- **O laço fechado:** produzir → gate/curar (B.1/B.2) → artefato-nó → **integrar (ATO) → vira source** (B.3) → o edge se aterra nela → produz melhor. A obra do edge alimenta o edge. Não é só ferramenta (`/artefato`, #69) — é **fonte**.

## Valência sobre gate-scores (o único caminho `computed` legal)
"Reusar os gate-scores como sinal de valência" só honestamente assim: uma Hipótese-meta (ex.: *"briefing Feynman-calibrado sobe o `contextualization` mediano em ≥1 sem baixar `development_completeness"*) declara um `rule_template` REGISTRADO sobre o stream de scores agora persistido:
```yaml
gate_score_delta@1: {params:[dim,direction,threshold,window_n,baseline_window], total:true, emits:[supports,challenges,inconclusive]}
```
O reviewer LLM é o INSTRUMENTO (entra no `provenance_signature`, O-11); o RULER é total/nomeado/versionado/congelado antes da janela, computado pelo fold. `noise_floor` = variância dos scores entre publishes do arm inalterado (a lição n=1 do V10). Até `window_n` publishes, emite `inconclusive` — mecanicamente. O agregador que roda isso é o slice seguinte; o schema reserva a porta, o código não pré-constrói a sala.

## B.4 — Os GATES em si (o passo discutido; a876 dor #3: o gate premiou o oco)
A persistência (B.1) grava o que os gates dizem; ESTE passo conserta o que eles são:
- **Fim = DOIS gates em AND** (P2✗ medido): **substância** (Feynman-destilado impessoal: "é real? cargo-cult? pousou avião?") **+ passabilidade** ("pousa pro colega/cliente que não domina o domínio?" — o leitor-faminto-de-contexto). O substância sozinho assina o enfadonho; o colega pega. Composição AND: qualquer um veta.
- **Veto LIMITADO restaurado**: a sobre-correção do #65 (`6136ae4`, pass derivado só de strikes) fez a nota de clareza virar conselho → shipou "referente sem nome". Clareza/passabilidade volta a VETAR — mas bounded (strike nomeado e endereçável, nunca o loop infinito que o #65 matou; o loop termina POR FORA).
- **Impessoal, semântico**: os conceitos do Feynman como critério (nunca "você é o homem" no gate de produção — conluio self==juiz é medido; nunca keyword-list, #65).
- **Plano** (ato-1, escolher): VoI/é-real-fazer + persona/é-pra-ele — o gate-objetivo NÃO depende de leveling existir (input = olhar quente; leveling afina no fim).
- `EDGE_GROUNDING_FLOOR` default 0=off → **subir para 1=observe** (contar violação, sem gatear) como primeiro degrau honesto.

## Arquivos
`eventlog.py` (payload `gate`, o evento de integração source), `close.py` (`GATE_RUBRIC_VERSION`; `bears_on` no digest), `publisher.py` (forward `gate=`, flat props, promoção→source), `grounding_yield.py` (join por `dispatch_id`). Forward-only, sem backfill.
