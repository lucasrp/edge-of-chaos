# Capabilities e primitivas vieram da migração texto-livre → CLI (enforcement)

**Status:** accepted — re-projeção 1:1 **resolvida** (2026-05; ver "Resolução" no fim); premissa de enforcement segue sob revisão

## Contexto e decisão

Originalmente o agente recebia capacidades em **texto livre** ("consulte o Google
Drive") e descobria sozinho como agir — consultava, lia o que era recente, voltava
e repetia se preciso. Quando a profundidade do Opus caiu (início de 2026), o agente
parou de consultar qualquer coisa. A resposta foi converter cada capacidade de texto
livre em **CLI**: as **primitivas** (capacidades da casa) e as **capabilities**
(superfície unificada via `edge-cap invoke`). A razão é pura função-forçante: *o que
está atrás de uma CLI o agente é obrigado a usar.* É a mesma raiz do ADR-0001 (o
engessamento da exploração) — um andaime para um modelo raso.

## Consequências

A migração comprou **certeza de uso**, mas pagou em **tamanho e legibilidade**: o
código foi de texto livre para ~95k linhas, em boa parte andaime de enforcement
acrescido sem critério (vibe code). Com o modelo recuperado (2026-05), a premissa
(forçar o uso) provavelmente **expirou** — um modelo que sustenta 1–2h de trabalho
profundo volta a saber "consultar o Drive" sozinho.

O alvo declarado do operador é sair do vibe code para um **projeto legível** — a
intuição é que algo muito melhor cabe em ~2–3k linhas. **Para revisitar:** separar
as capabilities/primitives que existem *só* como enforcement (candidatas a voltar a
ser capacidade livre do agente) das que têm valor próprio independente do modelo
(resiliência, probe de saúde, binding de fonte). O glossário (`CONTEXT.md`) é o
passo um dessa recuperação: registrar a intenção, o norte, separada do andaime.

### Drift específico: capability ↔ primitive

Cronologia: primeiro só **primitivas** (`edge-primitives`, um read model de
status/saúde/lifecycle, ainda vivo e usado direto). Quando elas "não bastaram", veio
a camada de **capability** por cima (`edge-cap`), que *lê* as primitivas e as
re-projeta. O wrapper, portanto, existe — mas a generalização foi preguiçosa e a
camada faz três coisas, das quais só uma realiza a intenção:

1. **Re-projeção 1:1** — cada primitiva-de-fonte vira uma capability `source.X`
   idêntica, só re-etiquetada. Redundância pura entre `edge-primitives` e `edge-cap`.
2. **Registry estático** — capabilities de CLI externo (`kind: external_cli`).
3. **`sources.aggregate`** — o *único* ponto onde uma capability de fato orquestra
   várias primitivas (fan-out por provedores em `build_source_bindings`). É a
   intenção original ("capacidade decomposta em primitivas") realizada — em um só
   lugar.

Diagnóstico: o conceito (capability = orquestrador sobre primitivas) é bom e está
vivo na `sources.aggregate`; a "gambiarra ruim" é a *generalização* — o
re-etiquetamento 1:1 que duplica a camada de primitivas sem agregar nada. A camada
funciona (skills e runtime usam `edge-cap invoke`), mas está meio-realizada e
redundante. **Para revisitar:** manter a forma `aggregate` (orquestração real),
eliminar a re-projeção 1:1.

## Resolução (2026-05)

A re-projeção 1:1 foi **eliminada**: a espécie de capability `primitive`/`source.X`
(`_primitive_capability_row` + seu merge em `build_capability_status`) saiu.
`build_source_bindings` agora lê o status de primitiva direto do read-model
`edge-primitives` (via `_load_primitives_payload` → núcleo puro `_resolve_bindings`),
sem o espelho redundante. Mantidas as capabilities `external_cli` e o
`sources.aggregate` (única que orquestra de verdade). A forma `aggregate` permanece
como a intenção viva; o resto da premissa de enforcement (primitivas como
forcing-function sobre CLI) segue aberto.
