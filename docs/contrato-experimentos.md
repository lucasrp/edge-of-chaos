# Contrato de experimentos (schema do genótipo)

**Origem:** operator 2026-07-04 — "vamos ter um contrato (um arquivo .md) descrevendo quais são
os limites dos experimentos... lembre-se que experimentos mudam" (o dele: resultado imediato;
um web designer pode querer um A/B de semanas).

**Regra genótipo/fenótipo:** este arquivo define OS EIXOS (schema, compartilhado pela fleet);
os VALORES são por install (agent.yaml → console futuro). Identidade nunca vaza pro schema.

## Eixos que boundam um experimento

- **Custo — um VETOR de recursos nomeados, não um escalar em dinheiro.** Dinheiro é UM recurso;
  %-de-usuários é outro; duração é outro. O genótipo é cego ao recurso: o install declara
  `{recurso: teto}` (ex.: `{dinheiro: $X}` vs `{usuários: 5%, duração: 3 semanas}`). O HITL
  dispara se QUALQUER recurso estoura. Distinção que morde: recursos que o edge MEDE (dinheiro
  — ele gasta, pode enforçar) vs recursos que ele só DECLARA (%-usuários — quem enforça é o
  sistema do mentee).
- **Duração / ciclo de vida:** síncrono (nasce e resolve num beat — ÚNICO construído agora) vs
  longo-vivo/assíncrono (sobrevive ao beat; dimensão DECLARADA no schema, máquina de polling
  NÃO construída — YAGNI até um install real pedir).
- **Act-types permitidos:** rodar-local · abrir-PR · deploy — cada um cruza o C1 num grau; o
  install lista os autorizados.
- **Regra C1/HITL:** dentro dos bounds declarados = pré-autorizado; fora = aprovação humana
  (superfície = o console do dashboard, deferido junto com ele).
- **Como fazer:** método/procedimento por install (o "regular" do operador ≠ o A/B do web designer).

## Estado

**O estado do experimento é um nó do Cortex** (nós `experimento` + `observation` — onde #67 e
#68 se encontram), NÃO um store novo. Imediato = nó criado+observado num beat; longo-vivo = nó
persiste entre beats e é repolido (o *revisitar* é o que está deferido, não o estado).

## Fluxo pelos módulos

cria (3·Produção, classe act) → roda (5·Publicação, act-adapter, cruza C1) → guarda estado
(2·Cortex) → lê e decide (operador/grill, 6·Curadoria) → boundado por este contrato.
