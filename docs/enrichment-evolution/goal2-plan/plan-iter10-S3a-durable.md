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

## Decisão de mecanismo (R2) — fronteira verificável, NÃO presença-de-trace

Presença de trace é forjável (gate Goal2 F2: um visual desenhado direto pode copiar um trace). Duas
opções mecanicamente checáveis, **escolha de S7**:
- **(a) Strip-and-reinsert real:** o publish **descarta TODO visual claim-bearing autorado (owed OU
  opcional)** — exceto formas do allowlist decorativo mecânico — e re-insere só via `add_visuals` a
  partir da evidência; o publisher nunca confia no visual do produtor. Exige a evidência no seam de
  publish. *(Não pode recair em "só owed", senão o opcional não-sustentado sobrevive — gate reframe-3.)*
- **(b) Proof tamper-evident por-visual:** `add_visuals` emite um **digest sobre {dados-do-bloco +
  span-de-evidência}** ligado ao **proof do close** (o digest que o close já assina); publish
  **re-verifica** o digest. Um trace copiado/forjado/stale **não bate** o digest → strippado.
Default recomendado: **(b)** — reusa o proof-digest existente do close, não roteia evidência ao publish.
Testes vermelhos: trace **forjado**, **stale** e **mismatched** todos falham. (Fecha Q3/F2.)

## Fase A — fazer o review convergir (destrava tudo)

### S1 — Cap de review + **classificação de severidade** + ship-with-logged-residual (R7 **+ R5-severity**)
- **Por quê juntos (gate Goal2 F1, crítico):** um cap que publica residual SEM saber o que é
  bloqueante normaliza enviar defeito de corretude como "residual logado". R7 e R5 são acoplados — a
  severidade tem de existir ANTES de qualquer ship-with-residual.
- **Severidade inclui R0-class DESDE O DIA 1 (gate Goal2-v2):** findings de corretude/evidência/
  grounding/render-fail **E de R0** (conceito perdido, visual-substitui-prosa, storytelling fino,
  **completude < a fonte/baseline do próprio Artefato** — content-relative, NÃO vs. o livro global) são
  **bloqueantes** — nunca viram residual, **mesmo antes de S2** cravar a métrica mecânica (até lá,
  honrados como blocker levantado-pelo-revisor). Red test: um map/plan não-roberto **não** é bloqueado
  por não conter claims do `eeb696e`; perder claim da própria fonte **bloqueia**. Só não-bloqueante vira
  residual. Isto impede que o cap troque conteúdo por visual e publique como residual antes do gate R0.
- **Arquivos:** `tools/close.py` (`IMPROVE_ROUNDS`→cap + classificador de severidade), loop per-node
  `tools/conductor.py`.
- **Vermelho:** (a) loop com finding **não-bloqueante** para em N e publica com residual; (b) finding
  **bloqueante de corretude/evidência/grounding/render-fail** falha-fechado mesmo no cap; (c) finding
  **R0-class** (conceito perdido / visual-substitui-prosa / storytelling fino) **falha-fechado, nunca
  residual**. **Primeiro slice.** (Semantic-discharge conductor-específico em S9; a classificação nasce aqui.)

### S3a — Contrato do store DURÁVEL content-addressed de run (decisão bloqueante, P2)
- **Objetivo:** o store de internal-evidence deve ser **durável e content-addressed** — um evento
  **append-only no eventlog** embutindo os valores medidos + hash, OU um store de run content-addressed
  novo. **Rejeitar** refs a **blob/path de Artefato publicado** (ADR-0006/CONTEXT: blob de Artefato é
  **transiente/prunable**; só o eventlog é verdade durável). Entregar a fixture.
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
- **S2b (avaliador):** R0-I (inventário de termos incl. labels visuais) + R0-II (continuidade vs.
  benchmark congelado) + **R0-III completude RELATIVA À FONTE**: o gate constrói o inventário de claims
  da **fonte do próprio Artefato** e exige ⊇ **dessa fonte** (não do livro); wire no `close.check_genus`
  **content-relative**.
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
- **Vermelho:** (a) visual com proof **forjado/stale/mismatched** (incl. raw-html-SVG) é strippado no
  publish; (b) **chart/diagram OPCIONAL (não-owed)** com dado não sustentado é strippado; (c) visual
  rotulado **"decorativo" mas com labels/números/arestas** é tratado como claim-bearing e strippado
  (default-deny); `raw-html`/SVG nunca passa como decorativo; (d) ascii-edge não sustentado falha mesmo
  com vl-convert ausente; ascii-edge fundamentado passa.
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
- **P2:** o store de run imutável de S3 (R8) — reusar o eventlog/artefato-de-origem existente, ou novo?
- **P3:** extração estável de "conceito/claim" para R0(III) — derivar do inventário de termos (S2-I) p/
  não virar juízo subjetivo.
