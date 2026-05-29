# Meta-skills (estratégia, reflexão, map) absorvidas na curation interna + lifecycle

**Status:** accepted — premissa sob revisão (2026-05)

## Contexto e decisão

Originalmente a atualização *estratégica* e *reflexiva* do estado morava em
**skills dedicadas** — `strategy`, `reflection`, `map` — cada uma um dispatch
próprio que parava para se reparar: revisar rumo, refletir sobre o que foi feito,
mapear o estado. Eram ciclos à parte, com artefato próprio.

Sob a degeneração de profundidade do Opus (início de 2026, mesma raiz do ADR-0001 e
ADR-0002), esse trabalho foi **absorvido para dentro da lifecycle** em dois passos:

1. **#391 — "Persist curated delta digest from strategy and reflection"**: o estado
   curado que essas skills produziam passou a ser despejado no **delta digest**
   (nasce o `tools/edge-delta`), que o passa adiante de ciclo a ciclo.
2. **#481 — "Replace heartbeat meta skills with internal curation"**: as skills
   `strategy`, `reflection` e `map` foram **deletadas** e substituídas por
   *internal curation* — `run_internal_heartbeat_curation` (lê `config/strategy.md`)
   + procedimentos de postflight (`curation.digest`, `cycle_health.observe`).

Resultado: a reflexão deixou de ser um ciclo dedicado e virou refresh embutido —
hoje **todo ciclo reatualiza o estado inteiro**. Ficou mais dinâmico (o estado nunca
fica defasado por falta de um beat de reflexão), ao custo de cada ciclo ficar mais
pesado e de a reflexão deixar de ser um *artefato-para-ler*.

## Consequências

A troca comprou **frescor** (estado sempre atualizado, sem depender de um ciclo
reflexivo separado disparar) e pagou em **legibilidade e em produto**: a reflexão e a
estratégia, que eram julgamento semântico explícito produzido por uma skill, viraram
**procedimentos mecânicos** espalhados pelo pré/postflight. Não há mais um *lugar*
onde a reflexão acontece — ela está difusa na lifecycle. Quem chega depois olha o
sistema e pergunta "cadê o ciclo de reflexão?", e não acha.

Como nos ADRs 0001 e 0002, a premissa (um modelo raso não reflete sozinho, então a
reflexão tem de ser forçada como procedimento mecânico de toda volta) provavelmente
**expirou** com o modelo recuperado. **Para revisitar:** avaliar restaurar a reflexão
como skill de primeira classe — um artefato-para-ler que é o produto do próprio
sistema sobre si mesmo — separando-a do bookkeeping de estado, que pode continuar
mecânico no postflight. O `cycle_health.observe` (auto-reparo) tem valor próprio
independente do modelo e pode ficar; a *reflexão como mecânica difusa* é o andaime
candidato a poda.
