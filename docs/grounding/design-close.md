# Design do close: publish-with-residuals + genus floor (Loop R · faceta 3)

> Cobre R5.1/R5.2 (teto de bounce → publica com resíduos) e o enxerto A1 do design-emissao.md §2
> (genus floor: dispatch themed sem leitura reconhecida). Referências de código na branch
> `feat/grounding-iteration`: `tools/close.py` (run_close ~1902, BOUNCE_MAX ~1669, hard-fail ~2110,
> zeragem do bounce_budget ~2034, check_genus ~131), `tools/publisher.py` (publish ~554),
> `tools/_identity.py` (project_dir ~50), separação infra≠veredito do #55 (`_llm.LLMTransportError`
> re-raise em ~1969/~2072).

## 1. O fluxo atual e onde o branch entra

`run_close` hoje tem QUATRO saídas de falha, e o branch novo toca exatamente UMA:

| saída | onde | genus | veredito | destino hoje | destino novo |
|---|---|---|---|---|---|
| plateau do improve | ~2024 | pode estar sujo | feedback (degradável, sem identidade canônica) | hard-fail | **hard-fail (inalterado)** |
| exaustão de genus | ~2041 | SUJO | nenhum reviewer rodou | hard-fail c/ `genus_violations` | **hard-fail (inalterado)** — genus segue blocking |
| infra do completer | ~2072 | — | não existe (transporte) | raise `LLMTransportError` | **raise (inalterado)** — infra ≠ resíduo |
| exaustão de bounce com strikes de reviewer | ~2110 | **LIMPO por construção** | 2 vereditos canônicos, identity-stamped, do draft final | hard-fail `{pass: False}` | **publish-with-residuals** |

O ponto ~2110 é o único lugar onde o invariante vale de graça: os reviewers só rodam DEPOIS de
`check_genus(artefato) == []` naquela iteração (genus-first, ~2039). Então "genus limpo + só
strikes de reviewer" não precisa ser re-derivado — é a pós-condição do caminho. **Localidade
máxima: o branch inteiro é uma função privada chamada no lugar do return da linha 2111.**

```python
if bounces >= bounce_budget:
    proof = _try_residual_publish(artefato, verdicts, publish_fn)   # None = não elegível
    if proof is not None:
        return proof
    return {"pass": False, "artefato": artefato, "verdicts": verdicts}
```

**Interação com o improve:** a zeragem do bounce_budget (~2034, improve rodou sem convergir →
uma única review de verificação, sem bounce) NÃO desqualifica o residual-publish. O draft chega
ao gate com genus limpo e vereditos canônicos; o modelo eLife publica-com-assessment independe
de quantas revisões o autor fez. O plateau (~2024) continua hard-fail: seus `verdicts_fb` são
feedback do estágio improve (exceção genérica vira strike sintético, `gv` pode estar sujo) —
nunca a review autoritativa do gate. Resíduo só nasce de review de gate.

**Bounce continua rodando primeiro.** BOUNCE_MAX inalterado: o produtor ainda ganha a(s)
chance(s) de endereçar. Resíduo = strike que SOBREVIVEU ao orçamento, não strike da 1ª rodada.

## 2. O bit sutil: resíduos DENTRO do conteúdo proof-bound

O digest do proof cobre `spec = artefato["content"]` (~2102, `proof_digest` ~1709). O publisher
recomputa o digest do payload que está prestes a publicar (`verify_proof` ~1883). Logo, se a
seção "Crítica não endereçada" fosse anexada DEPOIS do mint, o digest não bateria e o publish
seria recusado — e anexá-la no publisher quebraria o contrato "o proof cobre exatamente o que
publica". **A seção entra no content ANTES do mint.** Sequência do `_try_residual_publish`:

1. **Elegibilidade** (barata, pura): knob ligado; `len(verdicts) == 2` com AMBAS identidades
   canônicas; todo strike é autêntico (ver §4). Senão → `None` (hard-fail de sempre).
2. **Append determinístico**: `_residuals_section(verdicts)` — templater puro, SEM LLM — apensa
   uma seção a `content["additional_sections"]` (slot real de render, ~1281). Título fixo
   "Crítica não endereçada"; blocos paragraph/callout (PROSE_BLOCK_TYPES).
3. **Re-gate do genus no content apensado**: `ground_visuals(artefato)` + `check_genus(artefato)`.
   O append muda o corpus que o genus lê (R0, evidence-anchors, visual-coverage…) — um número
   citado num strike do reviewer viraria claim de prosa sem âncora. Se o content apensado viola
   → `None` (fail-closed; loga o motivo). NUNCA publicar genus-sujo, nem por resíduo. O template
   minimiza o risco (citação formatada, não prosa afirmativa), e o publisher re-roda o MESMO
   `check_genus` no seam (~610) — os dois lados concordam por construção.
4. **Mint**: `_mint_proof(verdicts, ..., residual_publish=True)` — digest sobre o content JÁ
   apensado; proof ganha `residual_publish: True` + `unaddressed: [...]` (§3). Os vereditos
   struck viajam no proof como sempre — o proof É o registro de que a review reprovou.
5. **Publish**: `publish_fn(artefato, proof)` — mesmo seam, artefato com a seção dentro.

Falha em 3–5 nunca regride para publish-sem-resíduos: ou publica COM, ou hard-fail.

## 3. Shape dos resíduos

Duas projeções da mesma verdade, com nome DISTINTO do canal `proof["residual"]` existente
(R5/S1: notas não-bloqueantes de classificador determinístico — semântica oposta; reutilizar o
nome seria colisão):

- **`proof["unaddressed"]`** (e daí o payload do evento): lista por reviewer do ROUND FINAL —
  `{reviewer, strikes: [verbatim], rationales: {dim: texto}, overall}`. Strikes **verbatim,
  nunca parafraseados** (analogia PRISMA C36: captura como-rodou); rationales completos para
  leitura fria (R6.2). Rounds anteriores NÃO entram: ou foram endereçados ou foram superados —
  o proof vincula a review DO draft publicado, nada mais.
- **Seção na página**: 1 parágrafo de protocolo (bounce esgotado, o que a seção significa,
  precedente) + 1 callout por reviewer com os strikes verbatim. Concisa: rationales moram no
  evento, não na página.

**Quem decide o que é resíduo é o PROTOCOLO, nunca o reviewer.** `_sanitize_verdict_residual`
(~1810) continua promovendo residual auto-declarado a strike; a graduação aqui é por EXAUSTÃO
(sobreviveu ao orçamento com genus limpo), não por severidade auto-classificada. Docstring do
`_try_residual_publish` cita o precedente (R5.2): **eLife Reviewed Preprints** (artigo + reviews
públicos + assessment graduado como anexo de 1ª classe) e **F1000Research** (publish-then-review)
— review pública gradua, não gateia binariamente. O cap explícito de rodadas não tem precedente
achado; é escolha nossa, divulgada como tal (resíduo do Loop R: varrer ARR/single-round policy).

## 4. Infra ≠ resíduo (a fronteira do #55, estendida)

- `LLMTransportError` re-raise (~2072) acontece DENTRO do loop de reviewers — o ponto de
  exaustão é **inalcançável** sob falha de transporte, por construção. O branch novo não captura
  exceção nenhuma vinda de reviewer. Escuridão de infra jamais publica-com-resíduos.
- **Strike sintético desqualifica**: o wrap de exceção genérica (~2077) e `_normalize_verdict`
  produzem strikes com prefixos conhecidos (`reviewer raised:`, `malformed strikes:`,
  `malformed score(s):`, `non-dict verdict:`). Um veredito assim é NÃO-REVIEW (crash/drift), não
  crítica — e o wrap genérico stamp'a identidade mesmo assim (~2086), então identidade sozinha
  não basta. Elegibilidade exige: scores dict não-vazio E nenhum strike com prefixo sintético.
  Reviewer-crash cai no hard-fail de sempre (fail-closed).

## 5. verify_proof e publisher

- `verify_proof` ganha um branch: proof com `residual_publish: True` exige token + digest +
  `reviewer_count` vereditos + AMBAS identidades canônicas (tudo igual), mas dispensa
  `_verdict_clean` — e exige o knob ligado TAMBÉM no momento do verify (desligar o knob volta a
  recusar struck-proofs na hora, sem proof órfão publicável). Profundidade preservada: o token
  só nasce em `run_close`, o digest cobre o content COM a seção — a superfície nova é 1 flag.
- `publisher.publish` lê `proof["unaddressed"]` (nunca um arg do caller) e o passa a
  `publish_artefato_atomic(..., residuals=...)` — resíduos como campo de 1ª classe no evento
  `artefato.published`. Redundância deliberada: os mesmos strikes vivem verbatim no spec
  (digest-bound) e no campo do evento (projeção de leitura). *Resíduo declarado:* campos do
  proof-dict são mutáveis in-process pós-mint — mesmo residual de arquitetura já declarado em
  close.py ~1696 (enforcement pleno exige close fora do contexto do produtor); não piora aqui
  porque o conteúdo digest-bound é a verdade e o campo do evento é conveniência.

## 6. Genus floor (enxerto A1): themed sem leitura = violação

**O check é determinístico e mora no harvest; o close só consome uma lista de violações.**

- **Seam**: `run_close(..., floor_fn=None)`. Na iteração do gate:
  `violations = check_genus(artefato) + _floor(floor_fn)`. A lista única herda TODA a mecânica
  blocking-first do genus (roda antes dos reviewers, bounça via `_genus_feedback`, hard-fail na
  exaustão, NUNCA publish-with-residuals — floor é violação de genus, não strike de reviewer).
  `check_genus` em si não muda: ele é contrato de OUTPUT (docstring ~132); o floor é contrato de
  SESSÃO — assinatura diferente, hook separado, mesma esteira. `floor_fn: () -> list[str]`;
  exceção do floor_fn → floor escuro (§ dark), nunca crash do close.
- **Implementação** (`tools/harvest.py`, a espinha C): `harvest.session_floor()` —
  (a) localiza o transcript VIVO: `_identity.project_dir() / f"{os.environ['CLAUDE_CODE_SESSION_ID']}.jsonl"`.
  **Investigado empiricamente nesta sessão: `CLAUDE_CODE_SESSION_ID` está exportada para
  subprocessos Bash** (o close roda como subprocesso da sessão via edge-python), e
  `_identity.project_dir()` já resolve o store (ADR-0015, fail-loud). Zero config nova.
  (b) decide se o dispatch é THEMED: payload do último `dispatch.open` (enxerto A2 — campos
  theme/intent declarados). Sem declaração → geometria desconhecida → floor escuro. Ambient
  nunca gateia (R3.2).
  (c) roda `recognize()` (pura, a MESMA do harvester) sobre as linhas do transcript: zero
  tool_use reconhecido como leitura de source (mundo OU recall) →
  `["grounding-floor: dispatch themed sem nenhuma leitura de fonte reconhecida na sessão"]`.
- **Costura**: close.py NÃO importa harvest (a espinha do close fica import-clean, como hoje só
  importa eventlog/_llm/…). O wiring injeta `floor_fn=harvest.session_floor` no call-site do
  skill-exit (pipeline.md snippet) — mesmo idioma dos seams `complete_fn`/`publish_fn`. Deep
  module dos dois lados: harvest é dono do formato de transcript e da tabela de recognizers;
  close é dono da mecânica de gate; a interface é `list[str]`. Alavancagem: recognizer melhor
  no harvest fortalece o floor de graça.
- **Floor escuro = fail-OPEN (deliberado, inverso do genus)**: env ausente (close fora de sessão
  Claude), transcript inexistente, `CLAUDE_CODE_CHILD_SESSION` setada (leituras podem morar no
  transcript do pai, não identificável hoje), geometria não declarada, recognize sem tabela →
  `[]` + evento best-effort `grounding.floor_dark` (idioma do `_log_infra_error`). Justificativa:
  o floor mede o INSTRUMENTO sobre um artefato out-of-band; escuridão de instrumento é infra, e
  infra ≠ veredito (#55). Um floor fail-closed mataria todo close rodado fora de sessão (testes,
  operador). A escuridão é CONTADA e visível no painel — nunca silêncio (enxerto B2).
- **Cura**: a violação bounça com mensagem nomeada, mas `improve_fn` mecânico não lê fonte — só
  o agente vivo cura (ir ler no meio da sessão e re-fechar). Sem leitura, exaure genus e
  hard-fail. É o comportamento desejado: themed sem grounding não publica.

## 7. Knobs e retrocompatibilidade

| knob | default | semântica |
|---|---|---|
| `EDGE_PUBLISH_WITH_RESIDUALS` | **0 (opt-in)** | 1 = branch do §1 ativo (mint E verify). Default-off: mudança de comportamento do gate nunca é silenciosa; flip de default é degrau posterior da escada #248, com dados do painel (taxa de residual-publish por skill) |
| `EDGE_GROUNDING_FLOOR` | **0 (off)** | 1 = observe (só conta `grounding.floor` no eventlog, nunca bloqueia) · 2 = gate (violação blocking). Escada #248 dentro do próprio knob: observe → gate |
| `EDGE_GENUS_BOUNCE_MAX` | **15** (espelha IMPROVE_BACKSTOP) | contador PRÓPRIO para bounces de genus, separado do BOUNCE_MAX dos reviewers (hoje compartilham `bounces`). "Ilimitado" do R5.1 em espírito; em código, backstop absoluto — nenhum loop roda unbounded (cicatriz ADR-0003, mesmo idioma do IMPROVE_BACKSTOP ~1671) |

Com os três em default, `run_close` é byte-a-byte o comportamento atual (exceto a separação dos
contadores de genus/reviewer, que só se manifesta acima de BOUNCE_MAX bounces de genus — hoje
inalcançável com BOUNCE_MAX=1 e genus determinístico; mudança declarada, não silenciosa).

## 8. Trade-offs honestos e questões abertas

- **O invariante "any strike must bounce/fail" (~1768) é deliberadamente relativizado** com o
  knob ligado: o close deixa de ser gate binário e vira assessment graduado no caso
  genus-limpo-exausto. É a tese do R5 (revisor-LLM satura em ~2 rodadas e vira ruído) + o
  precedente eLife/F1000. O custo: incentivo à preguiça do produtor ("publica mesmo assim").
  Mitigações: bounce roda antes; a crítica é PÚBLICA na página (o mecanismo reputacional do
  eLife); painel conta residual-publishes por skill (observe antes de confiar).
- **Falso-strike de reviewer ruidoso agora vira mancha pública** num artefato bom — o dual do
  falso-fail atual (artefato bom morre). Preferimos mancha visível a morte silenciosa; a
  calibragem lê os `unaddressed` frios e ajusta reviewers.
- **Aberta: o re-gate do genus pós-append (§2.3) pode recusar** por interação template×conteúdo
  (ex.: strike com número vira claim sem âncora). Fixtures douradas do template contra
  check_genus no CI; se a taxa de recusa for real, evoluir o template, nunca afrouxar o genus.
- **Aberta: floor em sessão-filha** (`CLAUDE_CODE_CHILD_SESSION`): hoje escuro. O glob
  `subagents/` do harvester pode habilitar varredura pai+filhos depois — fica para quando o
  harvest existir e medirmos a taxa de escuridão.
- **Aberta: "ilimitado" vs backstop de genus** — R5.1 diz ilimitado; a casa diz nenhum loop
  unbounded. Proposta: backstop 15 operator-set. Se o operador discordar, subir o default, nunca
  remover o teto.
- **Aberta: cap de residual-publishes por beat?** Sem precedente interno; não construir agora —
  observar a taxa no painel primeiro (escada #248).
