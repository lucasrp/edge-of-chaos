# Pauta — tabela normativa (assinada 2026-07-25)

**Status:** assinada pelo operador em sessão mentor 2026-07-25 (esta página registra; o log é a verdade).
**Ressalvas de assinatura:** `operacional` assinado provisório ("não 100%, revisar depois"); números do funil (tamanho A, nº aterrados) são valores iniciais a calibrar por evidência.
**Escopo:** especificação do módulo Pauta (Ato-1, escolha de pauta). NÃO reabre o rito 1–11; NÃO é código — verbete CONTEXT.md + ADR da cisão + spec `propose()` + ticket derivam DESTE texto.

---

## 1. O módulo

**Pauta** — cisão do "mirar" do Módulo 3 (Produção): a escolha de pauta deixa de ser uma linha de prompt dentro do producer e vira módulo próprio, etapa do **dispatch** (não do beat), gate de entrada simétrico ao Close na saída.

- **Interface:** `propose(constraints) → PROPOSTA | silêncio`
  - autônomo: constraints vazias (o sorteio preenche);
  - Voz: campos travados pelo pedido (`/ed-report sobre X` trava tema+forma); o funil roda nos graus de liberdade restantes (escolha de faceta via grounding). A palavra do operador é PROPOSTA-ok por autoridade; contra ordem não há silêncio — há **seca declarada**.
- **O dente:** sem `pauta.proposta` no log, não abre Ato-2. Uniforme para autônomo e comandado.
- **Estado:** nenhum próprio — alocação é fold do eventlog (`pauta.proposta` / `pauta.silencio` / `pauta.veto`), ADR-0006.
- **Consequências arquiteturais** (ADR a autorar): escolha sai do producer (revisa ADR-0012); rotation state sai do beat (beat vira shell puro); rotação/budget = política de alocação DENTRO da Pauta.

## 2. Os três eixos (matriz plena)

| Eixo | Valores | Papel |
|---|---|---|
| **Objeto** | mundo · atividade · si · **serendipidade (coringa)** | de ONDE vem a evidência (determina o catálogo) |
| **Abordagem** | fog · operacional · estratégico · meta-dica de trabalho · tempo gasto · curiosidade do edge · **serendipidade (coringa)** | COMO se julga (dono do gate) |
| **Forma** | roster de producers (report, research, descoberta, map, plan, prototype, meta-dica, …) | que desenvolvimento e momento de leitura |

- Qualquer objeto × qualquer abordagem. **Serendipidade = valor-coringa: desamarra o eixo onde aparece** (objeto=ser → catálogo sem limite; abordagem=ser → sem lente fixa). {ser, ser} = liberdade máxima, ~1/28 batidas por aritmética dos sorteios.
- **Sorteio:** {objeto, abordagem} sorteados independentes, **pesos uniformes**, ANTES de ler o wake (leitura já sai mirada). Sem blocklist de células: célula inviável morre em silêncio; 3 silêncios da mesma célula no log = evidência de poda.
- **Gate pendura SÓ na abordagem** (7 gates). Objeto re-mira o catálogo, nunca acrescenta critério. Forma nasce na sugestão (`{tema, forma}`), critério = que desenvolvimento o candidato precisa + que momento de leitura serve; a coluna formas-default poda o absurdo.
- **Admissão de abordagem nova:** só se o gate dela julgaria candidatos DIFERENTE das 7 existentes. Candidata em observação: risco/pre-mortem.

## 3. O funil

```
1. SORTEIO    {objeto, abordagem} — uniforme; Voz trava campos
2. WAKE       catálogo da célula (mundo→sources · atividade→conversas/obra · si→leveling/fog · ser→livre)
3. SUGESTÕES  ~12, baratas, função do wake — NUNCA pool fixo no repo
4. SHORTLIST A ~6, mérito dentro do pólo + 1 slot estrutural de serendipidade
              + checks: delta_voz · filtro direction/wayfind-aberto · substrato
5. GROUNDING  2–3 aterrados, explorers mirados no pólo; seca declarada é lastro
6. GATE       AND da abordagem sobre evidência → PROPOSTA (1) | silêncio (0) — nunca rebaixa critério
```

**PROPOSTA** (evento `pauta.proposta`, meia página, pointers): `{abordagem, objeto, forma, tema, faceta, lastro, gate_trace, delta_voz, origem, depth}`. Não carrega outline/ângulo desenvolvido — isso é agência do producer (Ato-2). O lastro da Pauta semeia o gather do producer (grounding pra ESCOLHER ≠ grounding pra DESENVOLVER; encadeiam, não duplicam).

**Nome carrega o setup (operador 2026-07-25):** o artefato publicado informa NO NOME a célula usada — slug prefixado `{abordagem}-{objeto}--<tema>-<install><data>` (ex.: `fog-si--o-ciclo-do-teu-dispatch-ed-0725`) e o título rendido exibe o par (ex.: `fog × si — …`). A forma já é carimbada pelo skill no publish. Vale para todo caminho, inclusive Voz fast-path (campos travados também são célula). Mecânico no publish da PROPOSTA — não é opção do producer.

## 4. Pisos universais (higiene, cortam sem rankear — valem até em {ser,ser})

1. **lastro** — fonte lida ou seca declarada; nunca produção sem mundo dentro.
2. **delta_voz** — a Voz é a **baseline, não blocklist**: candidato compete contra onde a cabeça do mentee já está (recall da Voz no tema → juízo semântico de delta, citado no trace). Redigest = pousar onde a cabeça já está; tema repetido com delta novo É o caso bom. Guarda reversa: Voz mostra domínio → claim de lacuna morre.
3. **substrato** — evidência sobre o mentee vem das conversas dele, nunca de log de agente delegado codando (o catálogo já nasce filtrado; o resíduo delegado tem outro destino: censo do fog).

**Lei do risco (dispatch autônomo):** nenhum gate contém "pergunta ao operador". Toda pergunta vira aposta afirmada com lastro; a válvula é a correção-depois pela Voz (que realimenta a baseline). Modo de falha honesto = silêncio logado, nunca espera.

**Piso com órgão escuro (leitura vinculante, adv R3 [policy], 2026-07-25):** órgão indisponível (ex.: recall da Voz fora do ar) → o piso **degrada DECLARADO** (trace `unavailable` + alarme no fold), nunca bloqueia a batida — mesmo princípio do wake (perna escura é nomeada e passada, ADR-0011) e do "seca declarada é lastro". Fail-closed é para juiz FORA DO PROTOCOLO (resposta malformada = raise); indisponibilidade honesta não é violação de protocolo. Alarme recorrente no fold = ticket de fiação, não silêncio de produção. Operador pode vetar.

## 5. Os 7 gates (AND mecânico; Δ mente NUNCA dentro do gate — é veredito do operador a posteriori; nenhum critério é adjetivo: nomeia/cita/evidencia/propõe)

### fog — "esclarecer o que eu não sei e dizer como saber"
(a) lacuna ancorada em uma de 3 fontes: **declarada** (mentor/wayfind marcou — Q2) · **nunca-abordada** (existe no mundo/produto, zero Voz) · **vibe-coded** (existe e foi feito sem participação direta do mentee — logs delegados provam existência E ausência);
(b) caminho concreto de vir a saber: primeiro passo executável + material verificado (imprimível quando houver — leveling calibra forma, nunca placar).
Entrega em modo **afirmação-com-evidência** (lei do risco). Falso-positivo guardado pelo delta_voz reverso.

### operacional — "dicas para o dia a dia" *(assinado provisório — revisar)*
(a) situação **recorrente** do dia do mentee, evidenciada no runtime (≥2 ocorrências na janela ou rotina observada, citada);
(b) dica usável na **próxima ocorrência**, **zero pré-requisito**, trade-off nomeado;
(c) **mecanismo** em 3–5 linhas (por que funciona) — diagnóstico profundo rebaixado a serviço do porquê, nunca entregável.
Chore de uma vez só REPROVA → ticket por outro rail, não artefato. Registro: "dica de quem acompanha há anos", não listicle.

### estratégico — a encruzilhada com dono
(a) cita a Direction que toca (id no trace) — **set: gate normal; proposed: exigência extra** — o artefato serve de evidência para o mentee RATIFICAR ou DERRUBAR o fio (testa, não constrói sobre);
(b) nomeia a decisão não-tomada + custo de seguir sem decidi-la (afirmado como aposta);
(c) abre obra ou muda rumo (espelho do zero-pré-requisito do operacional).

### meta-dica de trabalho — o método, não a tarefa
(a) jeito-de-trabalhar recorrente do mentee, observado e citado;
(b) **custo do hábito atual evidenciado no runtime** (hábito neutro NÃO é alvo — sem custo citado é opinião de estilo);
(c) método substituto testável na próxima semana, mecanismo + trade-off.

### tempo gasto — o espelho de horas
(a) mede o sumidouro com dado citado (proxy do session store vale, afirmado);
(b) **confronta com prioridade declarada** (Direction/objetivo citado): "você diz que A é prioridade; as horas foram pra B";
(c) realocação explícita: de onde → pra onde → o que ganha, com trade-off.

### curiosidade do edge — sujeito invertido
(a) pergunta genuína do edge: nomeia o que muda no MODELO dele (cortex/persona/modelo-de-domínio) com a resposta;
(b) ponte de volta em UMA linha (declarada, nunca utilidade provada — exigir prova colapsaria o pólo).
Valor de 2ª ordem: publica onde o modelo do edge se sente cego — o mentee audita o mapa lendo.

### serendipidade — o coringa
(a) o desamarrado é real: objeto=ser → fonte fora do circuito habitual (checável nas source keys do lastro); abordagem=ser sobre objeto fixo → a LEITURA é de fora; **nunca os dois comuns**;
**Leitura vinculante da tensão §2×§5-ser(a) (adv R2 #7, resolvida 2026-07-25):** o critério (a) pertence ao GATE da serendipidade e roda **somente quando abordagem=ser**. Célula com **objeto=ser sob outra abordagem** (ex.: {ser, fog}) NÃO ganha critério extra — o coringa no objeto é **liberdade de catálogo, não exigência**: julga-se pelo gate da abordagem sorteada, com catálogo livre. "Nunca os dois comuns" aplica-se na célula {ser, ser}. Mantém intacto o "gate pendura SÓ na abordagem" (§2, assinado). Operador pode vetar esta leitura.
(b) ponte nomeada ao trabalho vivo em uma linha;
(c) pisos valem inteiros — liberdade de onde/como olhar, nunca de olhar pra nada nem de recontar.

## 6. Teste mecânico de sucesso (falsificador da hipótese `ato1-multi-setup-vs-centro`)

Distribuição realizada de `{objeto, abordagem}` em N batidas vs uniforme (produto dos pesos). Desvio sistemático → ou o veto come um pólo, ou o grounding do modo não acha candidato — ambos diagnósticos acionáveis SEM leitura cega. Concentração ≥ ~80% em 2 modos = a aposta multi-setup falhou. Células com 3+ silêncios consecutivos → candidatas a poda (por evidência, nunca a priori).

## 7bis. Plano de teste da leva 1 (operador 2026-07-25: "vamos testar bem ela")

Ordem de execução após o loop convergir; cada nível é barato antes do caro:

1. **Piso unitário** (já no loop): `python3 tests/test_pauta*.py` offline, completer fake no seam. Verde é pré-condição, não evidência.
2. **Distribuição a seco (ed, ~30 sorteios):** só sorteio+catálogo+sugestões+A (sem grounding — custo ~zero). Confere: realizado vs uniforme, coringa ~1/28, slot de serendipidade sempre presente no A, células inviáveis identificáveis. É o falsificador do §6 rodando barato.
3. **Funil cheio no ed (3–5 batidas):** até PROPOSTA|silêncio, com grounding real. Audita: gate_trace legível a frio, delta_voz matando/deixando passar contra a Voz REAL do ed, seca declarada onde faltou fonte, nome com célula no evento.
4. **O TESTE (spec do operador 2026-07-25, supersede o desenho PROPOSTA-level):**
   - **10 artefatos COMPLETOS por install** (ed, petertosh, roberto) pela via nova, **células diversas** — sorteio estratificado p/ cobertura: toda abordagem ≥1×, todo objeto ≥2×, incluir 1 coringa; formas variadas.
   - **+2 artefatos por install pelo jeito original** (caminho velho theme_suggest/round-robin) — os braços de comparação.
   - **O operador avalia** (36 no total). Protocolo da sentada: kit da leitura cega (ordem randomizada por sentada, desconto de comprimento, re-rola extremos) + **anonimização** — o slug novo carrega a célula e desanonimiza o braço, então a avaliação usa cópias com id ANON e chave selada.
   - Pré-requisitos: merge na main ANTES do batch (abaixo); rota de review do roberto re-fiada via completer_for (xai.env removida — senão o rito pendura como o R1); host roberto/petertosh = produções SEQUENCIAIS (OOM); cursors verificados.
5. **As 3 perguntas do loop canônico** na mesma sentada: faz sentido? melhorou? cumpriu a expectativa? A avaliação decide o destino do theme_suggest (park-vs-kill) e a revisão do operacional.

**Merge (autorizado pelo operador 2026-07-25):** ao convergir o loop, commit da versão nova na **main do ed** (re-orientar antes de qualquer mutação git — operador/heartbeat commitam em paralelo) e propagação a petertosh+roberto **pelo procedimento manual do FLEET.md** (stash-identidade; `edge_fleet_deploy.sh` está quebrado — nunca usar).

## 7. Dívidas registradas

- **Etapa 2 (Ato-2) PARKED (operador 2026-07-25):** só esta leva por agora. A proposta "PROPOSTA como régua do review cego no close" (strikes `proposta:<campo>`, presença-nunca-formato) ficou **proposta, não assinada** — reavaliar depois que a primeira leva convergir e for lida. Os deltas mecânicos do Ato-2 (produce(PROPOSTA, depth); lastro semeia grounding1; forma resolve producer; nome com célula) estão especificados nesta conversa/log, sem build autorizado.

- `operacional` — revisão marcada (operador não-100%).
- Números do funil (12 / 6 / 2–3) — iniciais, calibrar por custo observado.
- Peso da serendipidade — uniforme lançado; se ~36% de batidas-com-coringa for liberdade demais na prática, o dial é o peso.
- Órgão delta_voz — recall-da-Voz-por-tema + juízo semântico: custo por proposta a medir (roda só na shortlist A).
- Gate-si de qualidade depende do persona-no-brief (gap nomeado 2026-07-13) — pilotar `si` depois, não primeiro.
- A autorar na implementação: verbete Pauta (+ Modo/Abordagem, PROPOSTA, gate de PROPOSTA/plan-gate, delta_voz/Redigest, shortlist A, catálogo, si, coringa) no CONTEXT.md; ADR único da cisão (escolha sai do producer / Ato-1 etapa do dispatch / rotation migra); revisão dos verbetes Producer-skill, Beat, Worthwhile content (o centro tem nome no glossário); spec `propose()`; ticket via dispatch protocol A–F.

## 8. LEI DAS ÂNCORAS (operador 2026-07-25, vinculante — supersede §4.3-eliminatório e §5 fog(a)/estratégico(a))
**O wake é insumo, não coleira.** A agência leu o wake; se escolheu se afastar dele, o afastamento é julgamento, não defeito. **Nenhuma âncora é eliminatória**: substrato e citação-de-Direction viram ADVISORY (ressalva no trace; candidato segue). Pisos que FICAM (não são âncoras): lastro (evidência do mundo), delta_voz (o objetivo), wayfind-anti-redigest — **este último RATIFICADO pelo operador (2026-07-25, sobre o caso roberto v1): "se já tá especificado e não traz nada de novo, tá certo" negar.** As duas decisões compõem: âncora ausente nunca mata (o fork novo pode não existir na Direction); presença já-especificada sem delta mata certo. O que pontua é o NOVO — nos dois sentidos. Gates julgam SUBSTÂNCIA, nunca fórmula/redação. Evidência: arm-B 3×3 (2026-07-25) — agência livre põe o teto, gate põe o chão; âncora eliminatória era imposto sobre a agência no pólo estratégico.
