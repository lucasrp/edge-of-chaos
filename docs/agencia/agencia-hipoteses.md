# A agência e nossas hipóteses

**A tese central (confirmada n=1, experimento Grok em trabalho real):** o ouro do mentor velho
era o **resíduo de um auto-abate adversarial** — formar tese, atacá-la, entregar só o
sobrevivente. O edge-next robotizou ao trocar isso por um gate ADITIVO de conteúdo (forma sem
função) e perdeu os dois adversariais (subtrativo + meta) e o self (lazer). O resgate é o
organismo SENTIR→JULGAR→CHEGAR (docs/agencia/design-organismo.md; regras em ADR-0023).

## Hipóteses (falsificáveis; estado em 2026-07-04)

- **H1 — Abate → ordem-de-serviço.** Review subtrativo+meta produz A-type (work-order), não
  B-type (think-piece). *Evidência:* n=1 confirmada (Grok matou as 3 eloquentes, sobrou 1 P0
  falsificável). *Teste:* o aceite pré-registrado abaixo.
- **H2 — O registro humano é o que aterrissa.** O que fez o DSPy pegar foi parecer "alguém mais
  sênior me ajudando, dentro do meu contexto" — gente, não sistema. *Teste:* taxa de acionamento
  das entregas do organismo (acionou ≠ acertou).
- **H3 — A banda da fronteira adjacente.** O juízo valioso vive fora do que ele sabe, colado no
  que ele faz. *Teste:* reações "não conhecia e devia" vs "já sabia" (imposto) nas entregas.
- **H4 — Sem reflexão o abate não aprende.** O órgão reflexao (causa-raiz do próprio erro +
  padrão recorrente + arquivos alterados) é o que faz o juízo COMPOR. *Evidência:* nailton
  (reflexao-log) manteve honestidade até o fim; estrategia sem obediência decaiu. *Teste:* taxa
  de erro repetido do organismo com/sem reflexão periódica.
- **H5 — Silêncio válido reduz clutter.** Se o organismo só fala quando algo sobrevive, o
  operador para de receber think-pieces. *Métrica de saúde:* kill-rate do abate (esperado ≥50%)
  e frequência de silêncio.
- **H6 — Lazer gera serendipidade defasada.** Curiosidade própria do agente ilumina, semanas
  depois, problemas reais por ângulos que ninguém pediu. *Teste:* hits defasados (só após S5).
- **H7 — Lei do executor.** Output cujo executor é o próprio agente (ou que CHEGA de verdade)
  gera valor; output que espera o operador na gaveta vira "aguardando operador". *Evidência:*
  reflexao vs estrategia no corpus velho.

## Aceite pré-registrado (CONGELADO 2026-07-04 — não editar após S1/S2 rodarem)

**Desenho:** 3 janelas reais no roberto (contextos recentes do operador). Por janela: o
organismo produz (A) e o producer edge-next produz (B) sobre a MESMA janela. Pares cegos
(letras, ordem sorteada), lidos pelo operador.

**Perguntas por par:** (1) qual dos dois muda o que você faz esta semana? (2) algum é
think-piece? (3) qual você guardaria?

**Passa se:** A vence a pergunta (1) em ≥2 das 3 janelas E nenhum A é julgado think-piece.

**Regra do silêncio:** se o organismo silenciar numa janela, o operador julga o B sozinho —
silêncio conta como vitória de A se ele confirmar que o B daquela janela é clutter ("não valia
vir me buscar por isso").

**Previsões (fable, antes de construir):** A vence todos os pares julgados; kill-rate do abate
≥50%; se houver silêncio, o operador o confirma correto.

**Leituras de falsificação:** B vence ≥2 → o diagnóstico está errado OU o build perdeu o abate
(conferir eventlog: matou algo?). Ambos think-piece → o abate não está mordendo. A vence mas
zero acionamento em 2 semanas → problema de CHEGAR (registro/canal), não de juízo.

**Juiz:** o operador, único leitor experto, cego, sem discussão antes do veredito registrado.
