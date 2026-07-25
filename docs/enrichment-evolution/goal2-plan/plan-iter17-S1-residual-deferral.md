# Plano de implementação — Enriquecimento que preserva o livro

**Goal 2 de 3.** Re-derivado de `docs/enrichment-adoption-requirements.md` (reframe storytelling-first,
R0/R0a + R1–R9). Gate: `/codex:adversarial-review`, **iteração completa até SHIP** (sem teto fixo — para
quando o ganho marginal → 0, R7). Cada slice = tracer-bullet vertical, TDD (`/pocock-tdd`), genótipo
(propaga p/ roberto/petertosh). **Dogfood:** cada iteração produz um artefato que o build de fato precisa.

> **NORTE:** mesma informação do livro, visualmente rica, sem trocar conteúdo por visual.

## Ordenação por dependência (não por importância)

R0 (storytelling/conteúdo) é o dominante, mas **não é o primeiro a construir** — depende de o produtor
TERMINAR (hoje livielocka em 15 rodadas) e de um benchmark congelado. A ordem real:

```
Fase A (destravar)      Fase B (o coração)        Fase C (aditivo, subordinado)
  S1 R7 cap ──────────►  S2 R0 gate ───────────►  S6 R1 floor (só conta se passa R0)
  S3 R8 internal-evid    S5 R0a A/B (arquitetura   S7 R2/R3 grounding boundary
  S4 R9 discharge          decidida por evidência)  S8 R4 skills · S9 R5 conductor · S10 R6 telemetria
```

Fase A destrava a produção terminável; Fase B define e mede "bom" (e decide single-writer por A/B, não
por decreto); Fase C adiciona visual SEM tocar no conteúdo que B protege.

## Decisão de mecanismo (R2) — proof-digest PROOF-ONLY (respeita o blindfold do publisher)

Presença de trace é forjável (gate Goal2 F2). Mecanismo **único** = **proof tamper-evident por-visual**.
Strip-and-reinsert no publish está **FORA**: exigiria evidência/contexto no publish, violando ADR-0013
(publish é **blind**, final-Artefato-only — gate reframe-3 F-pub):
- `add_visuals` (no produtor, evidência viva) **cunha uma ATTESTATION inforjável APENAS quando
  `attributable()` passa** — token **assinado** (HMAC com segredo do grounding/close que o produtor
  **não reproduz**) sobre {dados-do-bloco canônicos + ids-de-span}, incluída **separada** no proof
  assinado do close; o publish **re-verifica a attestation** (prova provenance "passou pelo grounding",
  não só integridade de payload) — proof-only, nenhuma evidência cruza. Um **digest auto-consistente que
  o produtor computa NÃO basta** (gate reframe-4 F1).
- Cobre **todo visual claim-bearing (owed OU opcional)**; só formas do allowlist decorativo mecânico
  ficam de fora; `raw-html`/SVG nunca é decorativo.
Testes vermelhos: trace **forjado/stale/mismatched** falha; **visual autorado direto com digest
auto-consistente + proof de close válido falha** (sem attestation do grounding); visual **opcional
não-sustentado** falha; **fake-decorativo com dado** falha. (Fecha Q3/F2/F-pub/F-attest.)

## Fase A — fazer o review convergir (destrava tudo)

### S1 — Stop de review por GANHO-MARGINAL + **severidade** + ship-with-logged-residual (R7 **+ R5**)
- **Por quê juntos (gate Goal2 F1, crítico):** um cap que publica residual SEM saber o que é
  bloqueante normaliza enviar defeito de corretude como "residual logado". R7 e R5 são acoplados — a
  severidade tem de existir ANTES de qualquer ship-with-residual.
- **Severidade inclui R0-class DESDE O DIA 1 (gate Goal2-v2):** findings de corretude/evidência/
  grounding/render-fail **E de R0** (conceito perdido, visual-substitui-prosa, storytelling fino,
  **completude < a fonte/baseline do próprio Artefato** — content-relative, NÃO vs. o livro global) são
  **bloqueantes** — nunca viram residual, **mesmo antes de S2** cravar a métrica mecânica (até lá,
  honrados como blocker levantado-pelo-revisor). Red test: um map/plan não-roberto **não** é bloqueado
  por não conter claims do `eeb696e`; perder claim da própria fonte **bloqueia**.
- **DESCOBERTA na implementação (Codex S1 #7/#25): residual de REVISOR-LLM não é confiável.** Um revisor
  LLM pode rotular um bloqueante (corretude/grounding/R0) como "non_blocking" sob qualquer categoria, e
  classificar texto-livre por substring é forjável. Logo S1 **promove TODO residual autorado-por-revisor
  a strike** (fail-closed). O "ship-with-logged-residual de NÃO-bloqueante" fica **DIFERIDO**: o canal
  `proof['residual']` só é populável por um **classificador cosmético DETERMINÍSTICO** (linter de
  typo/whitespace — slice futura), nunca pelo revisor. S1 entrega o invariante crítico (bloqueante
  **sempre** falha-fechado) + o loop limitado; o ship-de-nit cosmético não é de S1.
- **Arquivos:** `tools/close.py` (`IMPROVE_ROUNDS`→ **detector de ganho-marginal→0 + backstop generoso**
  contra divergência — **NÃO** um N fixo baixo; + classificador de severidade), loop per-node
  `tools/conductor.py`.
- **Vermelho (contrato R7 + severidade, como implementado):** (a) loop **convergido** (issues→0) → gate
  → mint; (b) loop que **ainda muda o draft CONTINUA** (não cortado por um N); (c) **platô** (draft
  inalterado com issues) → **falha-fechado preservando o feedback** (nunca re-reviewa um draft inalterado
  — um revisor estocástico só poderia flipá-lo a um pass espúrio); (d) loop que bate o **bound**
  (`EDGE_IMPROVE_BACKSTOP`) ainda mudando → **UMA** review de verificação sem bounce (mint se a última
  melhora convergiu, senão fail-closed); (e) finding **bloqueante** (corretude/evidência/grounding/render
  **E R0-class**) **e TODO residual autorado-por-revisor** → strike/fail-closed, **nunca publicado**;
  (f) qualquer input malformado (revisor não-dict, scores inválidos, improve_fn que levanta/retorna
  não-dict) → fail-closed, sem crash. **Primeiro slice.** (Semantic-discharge conductor em S9.)

### S3a — Contrato do store DURÁVEL content-addressed de run (decisão bloqueante, P2)
- **Objetivo:** o store de internal-evidence é **ancorado no eventlog** (ADR-0006, autoridade única) —
  um evento **append-only** com valores+hash, OU um store de run content-addressed **referenciado por um
  evento append-only que carrega o manifesto imutável** (p/ replay); **sem 2ª autoridade fora do
  eventlog**. **Rejeitar** refs a **blob/path de Artefato publicado** (transiente/prunable). Entregar a fixture.
- **Aceitação:** ref dereferenciável a um run **imutável/content-addressed** com valores; **prune/edição
  do artefato de origem NÃO altera nem quebra a verificação** (red test); fixture pronta. **Bloqueia S3.**

### S3 — Tier internal-evidence (R8) — depende de S3a
- **Arquivos:** o revisor de cite/grounding + `visuals.attributable` (admitir proveniência interna).
- **CISÃO R8 (espelha requirements):** internal-evidence vale **só** para cite/grounding de claim
  numérico interno; **NÃO** satisfaz `rich-rite:external-frame`.
- **Vermelho:** (a) número com `run_id`/ref **dereferenciável ao store de S3a** e **valor que bate** passa
  o **grounding** sem cite externo; ref que **não resolve** OU **valor divergente** **falha**; sem
  proveniência falha. (b) um Artefato de medição **só com refs internos e sem benchmark externo** ainda
  **leva strike `rich-rite:external-frame`** (interno não substitui frame de fora); (c) o mesmo Artefato
  **passa external-frame só após** adicionar um cite/benchmark **Mundo** real.
- **Risco:** médio — agora com o contrato de store fechado por S3a.

### S4 — Discharge persiste entre rodadas (R9)
- **Arquivos:** estado de review no `tools/close.py`/`tools/conductor.py` (carimbo resolvido).
- **Vermelho:** finding resolvido na rodada k não reaparece em k+1 sem fundamento novo (revisor mockado
  re-levantando o mesmo ponto → suprimido).
- **Risco:** baixo; combina com S1+R5.

## Fase B — o coração: definir e medir "bom", decidir a arquitetura

### S2 — O gate dominante R0 (storytelling + completude)
- **S2a (calibrar a forma NARRATIVA, não todo genus):** rodar o livro `eeb696e`; congelar
  prosa/conceito-ratio, transição, K-through-line **como piso da forma narrativa (report/research)** —
  ADR-0013: map/plan têm continuidade **genus-relativa** (conexões/deps coerentes), não as métricas do
  livro. O claim-set do livro fica **só** para a slice de migração do livro-roberto, não no gate genérico.
- **S2b (avaliador):** R0-I (inventário de termos incl. labels visuais) + R0-II (continuidade
  genus-relativa) + **R0-III completude RELATIVA À FONTE com contrato de claim TIPADO** (espelha o
  requirements, não reduzir a "menção de termo"): inventário de **claims tipados da fonte do próprio
  Artefato** — `claim-id` + **span de origem** + entidades normalizadas; cada claim **suportado em prosa
  não-visual**, casado por **regras explícitas paráfrase/split/merge**, **sem claim contraditório
  retido**; **+ R0-II(d) genus-GERAL: um parágrafo explicativo não-visual por cada estrutura
  visual/rotulada** (a explicação nunca é só o visual). Wire tudo no `close.check_genus` content-relative.
- **Vermelho R0-III/d (espelha requirements):** (i) **menção de superfície** que cita o termo mas não
  preserva o claim → FALHA; (ii) **claim contraditório** retido → FALHA; (iii) **paráfrase válida** →
  PASSA; (iv) map/plan não-roberto não false-falha por não conter claims do livro; (v) **labels+claims
  presentes mas estrutura visual/rotulada SEM parágrafo explicativo não-visual → FALHA**.
- **Vermelho:** o report `novoformato` (rico-mas-raso) **falha**; o livro `eeb696e` **passa**; um
  Artefato que define acrônimos mas perde claims/continuidade **da própria fonte/forma** **falha**; um
  map/plan **não-roberto NÃO é bloqueado** pela K-through-line/densidade-de-prosa do livro, mas **falha**
  se perde suas próprias conexões/deps ou deixa label sem explicação (R0-I genus-geral).
- **Risco (alto):** a métrica de "conceito/claim" precisa de uma extração estável — é o ponto que pode
  virar subjetivo. Ancorar no inventário de termos (S2 parte I) para objetivar.

### S5 — A/B single-writer vs fan-out (R0a, decide a arquitetura)
- **Objetivo:** sobre material idêntico, prompts/visual/review controlados, medir pelo gate S2:
  single-writer (fan-out só na coleta) vs conductor per-node. Decidir a arquitetura **por evidência**.
- **Vermelho/critério:** se single-writer move as métricas de R0 acima do per-node no mesmo material →
  o mandato single-writer vira estrutural; senão, a causa é outra (prompt/pressão-visual) e se corrige lá.
- **Risco:** é experimento, não feature — orçar como tal; resultado alimenta a Fase C.

## Fase C — adoção visual, ADITIVA e subordinada a R0

### S7 — Boundary de grounding de TODO visual claim-bearing (owed OU opcional) (R2/R3) — **ANTES do floor**
- **Por quê antes de S6 (gate Goal2 F3):** se o floor vier primeiro, ele fica verde com um visual
  renderável-mas-fabricado e S7 depois strippa o que S6 ensinou o produtor a depender. O grounding
  protege o conteúdo ANTES de o floor exigir o visual.
- **Arquivos:** `tools/visuals.py` (proof-digest por-visual + ascii-edge grounding), guard de
  **verificação do proof** em `tools/publisher.py`/`close`.
- **Sub:** S7a evidência produtor→`add_visuals`; S7b guard que **verifica o proof** (não presença);
  S7c grounding do ascii-edge.
- **Vermelho:** (a) visual com proof **forjado/stale/mismatched**, **OU com digest auto-consistente sem
  a attestation inforjável do grounding** (incl. raw-html-SVG), é strippado no publish; (b) **chart/diagram
  OPCIONAL (não-owed)** com dado não sustentado é strippado; (c) visual rotulado **"decorativo" mas com
  labels/números/arestas** é tratado como claim-bearing e strippado (default-deny); `raw-html`/SVG nunca
  passa como decorativo; (d) ascii-edge não sustentado falha mesmo com vl-convert ausente; ascii-edge
  fundamentado passa.
- **Risco (alto):** S7a depende de a evidência do explorer chegar à montagem do spec — **verificar P1**.

### S6 — Floor capability-conditional, subordinado a R0 **E a S7** (R1)
- **Arquivos:** `tools/producer_descriptor.py`, `tests/test_floor_evaluator.py` (virar o teste que trava).
- **Vermelho:** com vl-convert presente, **R0 satisfeito E o visual sobrevive ao guard de grounding de
  S7** — map+2×ascii falha, plan ascii-only falha, ambos com diagram **renderável+grounded+prosa-que-
  passa-R0** passam; diagram com **prosa fina** falha; diagram renderável mas **não-grounded falha** (a
  forma não basta).
- **Risco:** baixo-médio; o floor já é capability-aware.

### S8 — Reconciliação das SKILL.md (R4)
- **Arquivos:** `skills/{map,plan,discovery,report,research,critique}/SKILL.md`. map perde "inline SVG".
- **Vermelho:** lint de doc: nenhum SKILL.md de produtor com ascii-primário nem raw-html-SVG-autorado.
- **Risco:** baixo (texto).

### S9 — Conductor: semantic-discharge CUT-com-razão (R5; aplica a severidade nascida em S1)
- **Arquivos:** `tools/conductor.py` (contract gate: discharge por bloco substantivo OU
  `declined:{id,reason}`; usa o classificador de severidade de S1). **Não** un-dark.
- **Vermelho:** finding não-bloqueante declinado-com-razão → converge a `final`; bloqueante (datum não
  fundamentado) → falha-fechado. **Risco:** independente; pré-condição de un-dark.

### S10 — Evento de adoção no publish (R6)
- **Arquivos:** `tools/close.py`/`publisher.py` (evento `producer/owed/satisfied/degraded/shortfall/
  capability_state`), comando de relatório lendo o stream.
- **Vermelho:** publicar emite os 6 campos; relatório computa satisfied/owed do stream; não-visual →
  owed=false. **Risco:** baixo se o eventlog já é o substrato.

## Sequência (Goal 3 = um /goal por slice, gate /codex:review, iteração completa até SHIP)

`S1 → S3a → (S3‖S4) → S2 → S5 → S7 → S6 → (S8‖S9‖S10)`. (S1 já carrega a severidade que torna o
ship-with-residual seguro; S7 grounding antes do S6 floor; S3a fecha o store antes do S3.)

## Não-objetivos

- **NÃO** un-dark o conductor antes de S9 (Direction).
- **NÃO** trocar conteúdo por visual em nenhum slice (R0 domina cada gate de slice).
- **NÃO** registrar Artefato por reproject-fora-do-gate (laundering do contrato de review).
- **NÃO** schema de bloco novo nem backend com binário.

## Questões abertas (de plano)

- **P1 (RESOLVIDA).** A evidência (`seed.findings` de `excavate`) está **viva** no seam produtor→close;
  o conductor já chama `add_visuals(deep_spec, evidence=...)` em `tools/conductor.py:1357-1363` antes do
  `run_close`. Standalone producers (`report`/`map`/...) NÃO chamam — então S7a/S6 é **só WIRING**
  (chamar `add_visuals` antes de `run_close`, com a evidência em escopo), não plumbing nova. De-risca S7.
- **P2 (decidida por S3a):** store **ancorado no eventlog** (ADR-0006, autoridade única) — evento
  append-only com valores+hash, OU store de run novo **referenciado por evento append-only (manifesto
  imutável)**; **blob de Artefato publicado está FORA** (prunable).
- **P3 (RESOLVIDA por S2b):** "conceito/claim" não é juízo subjetivo — é o **contrato de claim tipado**
  (claim-id + span de origem + entidades normalizadas, casamento paráfrase/split/merge, suporte em prosa
  não-visual, rejeição de contraditório), com red tests de superfície/contradição/paráfrase.
