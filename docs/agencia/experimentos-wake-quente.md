# Experimentos wake-ótimo — pré-registro v2 (CONGELA na 1ª execução; revisado ANTES de rodar)

> **Missão (operador, 2026-07-05): ACHAR O WAKE ÓTIMO.** A moeda é o CONTEXTO INJETADO no agente
> principal no start ("benefício por contexto gasto no start — não dos subagentes, mas o quanto é
> injetado"). Não é só "útil ou não": é **quanto gastar no wake TOTAL e quanto vai pra CADA brief**.
> v2 substitui v1 antes de qualquer execução (v1 nunca rodou; mudança: + dose-resposta do quente
> raso→riquíssimo, + alocação entre briefs; seleção-de-sessões virou pré-requisito do E1; ordinal
> vs wall-clock virou sub-análise do E1).
>
> Contrato (docs/contrato-experimentos.md): custo {tokens-subagentes: ~250k, dinheiro-API-extra: 0,
> hosts: só ed — NADA no roberto}; síncrono; rodar-local; estado = este doc + bus. Braços/juízes =
> sonnet (doutrina). Grounding: memory/wake-quente-grounding.md.

**Correção do operador no desenho:** recência por ORDINAL de sessão (cadências reais variam:
24h vs 2×/semana); wall-clock é teto, não régua.

## Bateria-verdade (sela na 1ª execução; fonte verificável por item)
**Quentes (últimos ~3 dias):** 1. C4 porta cortex.py (14b866b) · 2. codex→9º caller briefing.py
(7576c56) · 3. forma H aplicada (adb0b82) · 4. one-grill/CHEGAR serial · 5. missão novo-wake +
briefing congelado 06-08 · 6. episode=113B sem texto · 7. bus A/B em docs/agencia/ ·
8. audit: sessions.py protótipo morto · 9. opus-vs-fable: rotina fica no opus · 10. dig campo:
P1/P3/P4 · 11. velho edge: prompts-only 48h nunca wired · 12. v10 leitura sonnet selada + conductor PARKED.
**Duráveis (têm que sobreviver à alocação):** 13. Objective (dimensão-nova × útil, juiz extrínseco) ·
14. steer curado Worthwhile · 15. mandato não-decidido (#mandate-decision) · 16. corpus 8 artefatos
introspectivos / drift-sensor · 17. roster de fontes (6 chaves, claude-sessions nativa) ·
18. regra genótipo/fenótipo + identity-blinding aberto.

## E1 — Curvas janela × custo (medição; pré-requisito de todos)
Parse dos jsonl de 14d: por sessão {turnos/chars operador, chars totais, substancial?} → por
janela {24h, 48h, 72h, últimas 3/5/10 substanciais} × formato {prompts-only cap500c, tail
transcript, cheio}: tokens estimados. Pré-requisito embutido: heurística de sessão-substancial
(turnos-op ≥5 E chars-op ≥1k; exclui heartbeat/agent-only) validada contra rótulo manual
(aceite: precisão E recall ≥0.9). Sub-análise ordinal: sob subamostra 2×/semana, janelas
wall-clock esvaziam e ordinais mantêm cobertura (aceite: ordinal ≥ wall-clock nas duas cadências).
**Aceite geral:** existe config ≥90% da massa de turnos-op das últimas 5 substanciais a ≤30k tok.

## E2 — Raw vs projeção (o valor do quente existe?)
Braço A: sonnet lê janela raw (últimas 3 substanciais, formato E1) → brief fios-vivos. Braço B:
sonnet lê superfícies frias (briefing.md+wiki+chat-digest+handoff) → mesmo. Juiz sonnet cego,
recall dos fatos 1-12 (0/0.5/1). **Aceite: A ≥ 2×B E A ≥ 8/12.** Previsão: A≈10, B≤3.

## E3 — Prompts-only vs transcript-tail (composição do INPUT do leitor)
Budget igual (~15k): P = só turnos do operador (desenho velho-edge) vs F = tail user+assistant.
Mesma verdade/juiz; subscore fatos 9-12 (dependem do lado assistente). **Aceite: P ≥ 0.8×F →
espinha prompts-only; F−P ≥ 3 fatos → transcript necessário.** Previsão: P perde só em 9-12.

## E4 — Dose-resposta do quente (A MOEDA: raso → riquíssimo)
O leitor (sonnet) produz o MESMO conteúdo em 4 profundidades de brief INJETADO:
{raso ~500 tok, médio ~1.5k, rico ~4k, riquíssimo ~10k}. Um "agente principal" simulado (sonnet)
recebe SÓ o brief injetado e responde a bateria 1-12 + tarefa de orientação ("qual o próximo
movimento e por quê" — julgada contra o estado real). Mede **benefício marginal por token
injetado**; o ótimo é o joelho da curva. **Aceite: existe joelho identificável (ganho de
recall/1k tok cai ≥50% após algum ponto); reportar a curva inteira.** Previsão: joelho entre
1.5k-4k; o riquíssimo paga pouco acima do rico.

## E5 — Alocação do orçamento do wake (quanto pra cada brief)
Total FIXO por arm-set {4k, 8k, 16k tok injetados}; alocações: (a) status-quo 3-briefs frios
(assemble+delta+recall nas proporções reais de hoje), (b) 4-briefs balanceado, (c) quente-pesado
(60% quente / 40% frio), (d) quente-só. Agente-principal simulado responde a bateria COMPLETA
1-18 (quentes E duráveis — a alocação troca cobertura quente por durável). **Aceite: reportar
argmax por orçamento; o wake ótimo = alocação vencedora no orçamento que o operador escolher;
pré-previsão: (c) vence em 8k e 16k; (d) vence em 4k mas sangra os duráveis 13-18.**

## Resultados (preencher ao rodar; aceites imutáveis a partir da 1ª execução)
- E1: **PASSA (2026-07-05).** 21 sessões/14d, 10 substanciais (heurística vs rótulo manual ≈95%;
  1 borderline: 4 turnos/9.4kc colagens — anotado). Custos (tok): prompts-cap500 last3sub=14.9k,
  last5sub=29.1k (100% massa, ≤30k ✓), 24h=29.1k, 72h=35.1k; tail40k last3=33.3k; cheio 124-364k
  (proibitivo). Ordinal: SIM 2×/semana → 48h pega 0, last3sub pega 2-3; cadência real: ordinal-5
  = 97% da massa do 48h. **Veredito: ordinal-K com teto wall-clock; formato espinha = prompts-cap500.**
  Dados: /tmp/e1_sessions.json. Nota de desenho (pré-braços): E2-braço-A usa prompts-only (a
  bateria-verdade só existe em texto do agente, não nos prompts do operador — sem contaminação);
  E3 usa janela sem as 2 sessões-agente vivas p/ comparação P-vs-F justa.
- E2: **RODADO; aceite FALHOU no absoluto — e a falha é o achado (2026-07-05).** Juiz cego:
  projeções frias = **0/12** (o wake atual não carrega NENHUM fato recente); raw-prompts 1pg =
  1.0/12 (<8/12 ✗). Autópsia: ~metade da bateria são fatos LADO-EXECUTADO (commits, achados de
  review) que não passam pelos dedos do operador — prompts-only não os alcança POR CONSTRUÇÃO;
  e fatos presentes nos prompts (one-grill, bus, audit) o leitor raso perdeu por compressão.
  Lições: (a) régua-zero das projeções confirmada em juiz cego; (b) bateria de wake precisa
  separar eixo dito-pelo-operador × executado-pelo-agente; (c) 1pg sobre 3 sessões comprime demais.
- E3: **RODADO; PASSA (2026-07-05).** Mesma janela: P=8.5 vs F=6.5 (P≥0.8F ✓ — prompts-espinha
  vence no total); subscore lado-assistente {4,7,12}: F=3/3, P=1/3 (gap 2.0 < 3 → transcript não
  obrigatório). **Síntese E2+E3: quente ótimo = prompts-espinha + âncoras mecânicas de estado
  (git log/eventlog — fonte mais barata que texto de assistente pro executado).**
- E4: **RODADO; PASSA (2026-07-05).** Tamanhos reais 576/1.612/3.974/8.191 tok. Recall /12:
  2 → 8.5 → 8.5 → 9.5; ordenação /3: 0 → 1 → 2 → 3. **Joelho do recall em ~1.6k** (raso→médio
  +6.3 fatos/k; médio→rico 0/k; rico→riquíssimo +0.24/k — queda >50% ✓). **Ordenação cresce
  linear com o tamanho** — a espinha de dependência paga até ~4k+ (formato vencedor: tabela de
  estado por fio com Bloqueio/Próximo-passo). Fatos 6 e 11 ausentes em TODOS (lacuna da FONTE:
  análises profundas não vivem no transcript-tail → papel da memória/topic-files, não do quente).
- E5: **RODADO (2026-07-05); 6 sims, bateria 18 + próximo-movimento.** Placar (quente/12 ·
  durável/6 · Q19): 4k-frio ~0·4.5·JUNHO✗ | 8k-frio ~1·6.0·JUNHO✗ | 4k-5050 ~5.5·3.5·misto |
  **8k-5050 ~9.5·5.5·ATUAL✓ (vencedor)** | 4k-quente ~8.5·0.5·atual✓ | 8k-quente ~10.5·0.5·atual✓.
  Leituras: (1) frio = duráveis perfeitos + quente zero + PRÓXIMO MOVIMENTO REDIRECIONADO PRA
  PAUTA DE JUNHO (o dano real do wake frio não é ignorância, é direção errada com confiança);
  (2) quente-só = quente máximo mas o agente NÃO SABE o próprio Objective/roster/regras (0.5/6) —
  descolado da identidade; (3) o vencedor domina AMBOS os extremos: **wake ótimo ≈ 8k injetados,
  split ~50/50 durável-compactado + quente-rico(~4k)**; qualquer presença de quente (mesmo 2k)
  já conserta a DIREÇÃO do primeiro movimento. Previsão pré-reg. parcialmente certa (quente-pesado
  venceria em 8k — o 50/50 venceu; quente-só sangrou duráveis como previsto). Caveats: janela
  atípica (teto de calor); scoring pelo experimentador (verdade em mãos) — juiz E4 independente
  em voo; frio dos sims = brief_B+briefing.md (stale — em produção o frio é assemble+recall
  compactados, deve pontuar duráveis igual e quente igual de mal).
- E5-ext 16k-5050 (pedido do operador; previsão cravada no bus ANTES): **9.5 quente (=8k; previ
  +1-2, ERREI) · 6.0 durável (+0.5, roster completo: acertei) · próximo-movimento atual ✓** (probe
  neo4j roberto → pedir go S1). Curva 8k→16k PLANA (0.06 fato/k); nenhum falseamento disparou.
  Nota: quente-só-8k fizera 10.5 quentes — frio ao lado deprime ~1 fato (diluição/ruído n=1).
  **Régua do operador ("16k default, se for melhor"): estritamente não-pior e +0.5 durável →
  16k DEFAULT confirmado**; orçamento segue valor fenótipo (8k = install enxuto).
