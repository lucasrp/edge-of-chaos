# Proposta — o wake ótimo (v1, 2026-07-05)

> Missão do operador: "achar o wake ótimo" — moeda = contexto INJETADO no agente principal no
> start. Grounding: dig fechado (memory/wake-quente-grounding.md) + 5 experimentos pré-registrados
> e RODADOS (docs/agencia/experimentos-wake-quente.md) + parecer conceitual do agente A (bus).
> Status: PROPOSTA — review conceitual do A e go do operador ANTES de build.

## O número: 16k injetados default, split ~50/50 (DECISÃO DO OPERADOR, 2026-07-05)

- **Orçamento total do wake: ~16k tok DEFAULT** (~8k frio-durável + ~8k quente). Decisão do
  operador ("16k default") sobre a evidência: E5 mostrou o 50/50 dominando os extremos em 8k;
  o operador escolheu pagar o dobro pela ponta da curva — a resposta implícita à pergunta aberta:
  **fio perdido custa mais que contexto gordo.** Orçamento é valor FENÓTIPO (contrato): installs
  enxutos podem declarar 8k; o braço 16k-5050 (sim em voo) mede o que o segundo 8k compra.
- **Split ~50/50 mantido** (E5: frio-só manda o agente pra pauta de junho com confiança;
  quente-só não sabe o próprio Objective — a proporção é o achado robusto, o total é o dial).

## O 4º brief — "quente" (o SENTIR em modo passivo; doutrina P4 do A)

1. **Janela: ordinal — últimas K=3 sessões substanciais** (E1; wall-clock só como teto ~7d).
   K é FENÓTIPO (contrato-experimentos): ed K=3 ≈ 1 semana; roberto K=3 ≈ 1-2 dias (recon A).
   Substancial = turnos-op ≥5 E chars-op ≥1k (E1: ~95% vs rótulo manual; revive
   `sessions.py.classify_session` — o spike ADR-0004 ganha seu caller).
2. **Dois trilhos de insumo (doutrina nova, corroborada 2× independente):**
   - **Trilho voz:** prompts do operador VERBATIM, cap 500c/turno (E3: 8.5 vs 6.5 por token; o
     desenho do velho edge `edge-feedback-digest` validado — agora WIRED no wake, o que ele nunca foi).
   - **Trilho executado:** âncoras mecânicas — `git log` dos repos vivos + tail do eventlog
     (E2/E3: o executado não passa pelos dedos do operador e NÃO vem de prosa de assistente;
     retro-run do A: T1 errou fato executado de memória-de-conversa, /proc corrigiu).
3. **Formato do brief (~3.5-4k): rico-grade** — fios mais-recente-primeiro, cada um com estado
   exato e refs; **TABELA DE ESTADO por fio (Bloqueio · Próximo passo)** + **espinha de
   dependência "por onde começar"** (E4: recall satura em 1.6k, ordenação paga até 4k; calibração
   do operador: o gargalo é a ordem, não os fatos — "extração é pré-requisito de grafo...").
4. **Execução: subagente fresco no wake** (wake é READ, não compute — P4; o leitor queima o
   próprio contexto: ~15-20k in / 4k out por wake, sonnet).
5. ~~Persistência: digest rolante com watermark~~ **CORTADO (faca de redundância, 2026-07-05):**
   com communities (sumário temático automático) + eventlog (verdade cronológica) + quente
   gerado-fresco-sempre, o digest rolante seria um TERCEIRO sumarizador sem função própria —
   a doença da mini-wiki paralela renascendo. `chat-digest.md` aposenta de vez.

## Os frios — compactação

- assemble+recall re-renderizados a ~4k somados: Objective + steers curados + roster + corpus
  1-linha/artefato. **Tatuagens (personality/method) saem do orçamento de orientação** — são
  system-load, não brief (hoje 65% do briefing.md).
- delta intocado (mundo; nunca gata o wake). ADR-0014 preservado: 4 apertures, nunca fundidas.
- Consolidação/sumarização: SEMPRE offline/entre-sessões — nunca no wake (P4).

## O que o quente NÃO cobre (honesto)

Fatos 6/11 do E4 ausentes em TODOS os briefs: análises profundas (ex.: "episode=113B",
"leitor do velho edge nunca wired") não vivem no transcript-tail — vivem em topic-files de
memória. O quente cobre os últimos dias; a memória cobre o entendido. Não confundir os órgãos.

## Caveats de evidência

Janela dos experimentos ATÍPICA (1º dia fable + sexta intensa — teto de calor); juízes-LLM n=1
(direcionais, não cravados — parede de construto); E5 pontuado pelo experimentador com a verdade
em mãos; frio dos sims = superfícies stale reais (em produção, frio compactado deve pontuar
duráveis igual e quente igual de mal).

## Fork aberto

- **Onde aterra o build** — branch refactor/modularize (recomendado; porta pro roberto junto com
  o organismo — é o mesmo órgão SENTIR) vs main vivo. (K=3 ordinal default; K=5 se o
  E1-do-roberto mostrar sessões curtas demais — dado do A chegando.)

## Build (quando houver go): ~1 sessão, TDD

`skills/quente/SKILL.md` (novo subagente) · helper em `tools/sessions.py` (revive o spike:
substanciais + prompts-cap + git/eventlog anchors) · patch `skills/wake/SKILL.md` (fan 4,
orçamentos) · compactação assemble/recall · testes: seleção de sessões (E1 como fixture) +
formato do brief.
