# Implementação — ordem e a decisão load-bearing

Esta pasta = os specs de BUILD da nova produção (o desenho está em `../design-nova-producao.md` + `../ontologia-cortex-v2.md`; a rota em `../wayfinder-nova-producao.md`). Aqui é o COMO, file-by-file. **Não re-desenhe — execute.**

## A regra que rege tudo (implementar PRIMEIRO)
O eixo **`provenance_class`** + a invariante **CX-1** no `verificar`:
> `provenance_class ∈ {computed, asserted, llm_judged, extracted}` em toda aresta/anotação.
> **CX-1: o `scoreboard`/`verdict` consome SÓ bearings `computed`; `verificar` grita LOUD se qualquer não-computed cair num rollup.**

Ponha ISSO primeiro. Com essa invariante no lugar, todo o resto (gates, RAG, nós) é **aditivo** e não pode corromper a integridade da valência-computada do episteme. Sem ela, cada peça nova é um risco. É o que faz o design ser um **superset estrito** (teste de deleção: apaga judgment+semantic → o módulo de verdict é byte-idêntico).

## Ordem (por que essa ordem)
1. **`git-consolidate`** — merge limpo (o repo está mid-merge; nada constrói sem base limpa). Ver o ticket no wayfinder.
2. **`provenance_class` + CX-1 no `verificar`** — a invariante-mestra. Load-bearing.
3. **B + D = fiação barata** (o grande achado do gap-map: *o grafo já computa os sinais e joga fora*):
   - **B** (`01-B-...md`): gates persistem verdict como metadado (`gate.scored` → `a.gate_scores`) + **curadoria de sources** (join no `grounding_yield` por `dispatch_id`).
   - **D** (`02-D-...md`): acorda o RAG — wire `relate.py` (built-mas-sem-caller) + o `MERGE RELATES_TO` faltante.
4. **A** (episteme nodes: `:Hypothesis` + arestas valenciadas) — **de-riscado por B+D** (B dá o sinal de valência; D dá o typer NLI). Ver `03-migration.md`.
5. **C** (genus interativo, standalone) — paralelo, base = o `prototype` do relicário (`drafts/relicario/ed-20260417/skills/prototype/`).

## Postura de build
Feynman-ponteiro (nome > verborragia); gates de produção IMPESSOAIS; **provas > afirmações** (dogfood: o gate-Feynman + o passável-pro-colega + o leitor-faminto-de-contexto); `/pocock-tdd` + `/pocock-codebase-design`; heavy = subagentes opus/fable em background. Forward-only (sem backfill de verdicts descartados — ausência honesta).

## Diferido
Grill (a cereja, em cima do grafo navegável) · `/artefato` (issue #69, auto-capacitação: o edge itera nos próprios JS-artefatos como tools).
