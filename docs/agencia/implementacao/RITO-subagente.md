# Rito do subagente de execução (Fable, codex-backed)

Todo subagente de build (B/D/A/C e além) segue este rito. Ele é o **espelho, no loop de DEV, da estrutura de gates da produção** (adversarial + meta-gate que decide se o adversarial agrega) — o mesmo *abate* de Feynman, agora na construção. Operador, 2026-07-05.

## O rito
1. **ABRE** com `/pocock-codebase-design` (mapear interfaces/seams/best-practices do alvo ANTES de editar) + `/ed-dig` onde houver claim a aterrar no mundo (só onde há afirmação externa a checar — não em toda tarefa).
2. **CONSTRÓI** via `/pocock-tdd` (red → green → refactor; o teste falho primeiro).
3. **ADVERSARIAL = codex:** um codex ataca o trabalho — tenta refutar, achar o furo, o cargo-cult (o abate). Crítica independente, não o autor se auto-aprovando (evita o conluio self==juiz, que é medido).
4. **GATE DO ADVERSARIAL = um SEGUNDO codex:** julga se a crítica do adversarial **AGREGA (sinal)** ou é **RUÍDO (nitpick, alucinação, preferência de estilo)**. Filtra pra o adversarial não virar busywork. Semântico, nunca keyword ([[no-keyword-classifiers-in-harness]]). Só os achados marcados SINAL entram no trabalho.
5. **CODEX NÃO BLOQUEIA (advisory):** o subagente incorpora os achados-sinal, mas o codex **não veta nem trava** o progresso. O loop termina POR FORA (o critério de done do ticket), não "até o codex gostar" (#65: gate inganhável mata a agência antes dela nascer).
6. **MANTÉM-SE ATIVO enquanto o codex roda:** dispara o codex em background (`Bash run_in_background` / runtime async do plugin codex) e **segue trabalhando** — nunca bloqueia idle esperando o retorno (backend codex, TTL de cache ~4min). Cadência apertada; prepara o próximo passo enquanto o codex pensa.

## Por que DOIS codex
Um adversarial sozinho gera crítica plausível-mas-inútil — foi o **P2✗** da noite (o gate-substância assinou o *enfadonho*, cego pro que era só completo-mas-soterrado). O meta-gate é o filtro sinal/ruído: o mesmo papel do "isso agrega?" que separa o abate real do medo cosmético. Adversarial acha; meta-gate decide se vale.

## Como rodar codex (mecânica)
Plugin codex: skill `codex:rescue` (delegar investigação/crítica) ou o `codex:codex-cli-runtime`. Para o passo 6, disparar via Bash `run_in_background: true` e ler o resultado quando pronto — o subagente não fica parado. (ed chat/review já roteia codex/gpt-5.5, ver [[llm-routes-codex-provider]].)
