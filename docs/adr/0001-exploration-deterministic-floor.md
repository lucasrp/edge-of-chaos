# Exploração é padronizada deterministicamente (o Exploration pack), não livre

**Status:** accepted — premissa sob revisão (2026-05)

## Contexto e decisão

A tese do sistema é exploração *livre* (ver `CONTEXT.md`). Mas durante a regressão
de qualidade do Opus no início de 2026, o modelo passou a explorar de forma rasa e
a pular passos, ameaçando o padrão de qualidade do artefato. Para compensar, tiramos
a exploração da discrição do agente: o runtime passou a montar um **Exploration pack**
determinístico e read-only (loop fixo — memory retrieval → fan-out de sources/signals
→ Feynman adversarial → segundo round) que toda skill deve ler antes de agir. O
encurtamento do heartbeat (50 → 15 → 10 min) e a complexidade do `dispatch_runtime`
são parte da mesma cicatriz: andaimes para forçar um modelo fraco a pensar. A
migração mais ampla de texto-livre → CLI que produziu essa cicatriz está no ADR-0002;
este ADR é o caso específico da exploração.

## Consequências

O engessamento faz **dois trabalhos separáveis**:

1. **Função-forçante** — obrigar um modelo que não exploraria sozinho a seguir os
   passos. Prótese para o Opus fraco.
2. **Piso de evidência** — garantir uma base mínima, com resiliência (fonte quebrada
   vira warning, não para o ciclo) e um veredito de `decision_readiness`.

Há um custo ganha-perde **comportamental**, não só de tempo: ao prescrever os
passos, a padronização *ancora* o agente neles. Mesmo livre para explorar além do
padrão, o agente tende a satisfazer no padrão — o conjunto prescrito vira o teto de
fato. Ou seja, a função-forçante (1) não é apenas peso morto hoje: com um modelo
recuperado, ela *ativamente suprime* a exploração livre que ele faria sozinho.

Em 2026-05 os modelos se recuperaram (dá para sustentar 1–2h de trabalho profundo),
então a razão (1) provavelmente **expirou**, enquanto (2) segue valiosa
independentemente da qualidade do modelo. **Para revisitar:** afrouxar a prescrição
de passos (a função-forçante) preservando a base de evidência e o veredito de
prontidão — devolvendo a exploração livre sem perder a resiliência que motivou o
engessamento.
