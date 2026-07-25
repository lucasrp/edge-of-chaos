# ADR-0023 — Dois registros do juízo, e a calibração do abate

**Status:** aceito (operator, 2026-07-04, sessões 6be5a9c9 + continuação)
**Contexto:** o resgate da agência (docs/agencia/design-organismo.md). O edge velho tinha dois
adversariais que o edge-next perdeu: o subtrativo (conteúdo) e o meta ("devia existir?").
Rebuildá-los exige regras duras sobre COMO o abate mata — senão ele vira ou gate aditivo
(a robotização) ou exterminador de serendipidade.

## Decisão

**1. Todo juízo pertence a um de dois registros, com réguas meta distintas — e a régua de um mata o outro:**
- **agência** (consequência): *"muda o que o operador FAZ?"* — acionamento conta mesmo se o
  outcome falhar (caso DSPy: "acionei, não deu certo, foi uma boa dica"); mover a fronteira conta.
- **lazer** (serendipidade): *"é curiosidade genuína do agente?"* — payoff defasado e
  probabilístico; NUNCA cobrar consequência imediata dele.

**2. O abate mata o oco, nunca o incerto.** Claim incerta-mas-fronteiriça é REBAIXADA à sua
força honesta ("use X" → "teste X — é a pesquisa que vale"), não exterminada. Precedente: o
edge velho cortou "ninguém provou MIPROv2 pra negociação" e entregou o experimento.

**3. O alvo é a banda da fronteira adjacente:** fora do que o operador sabe, colado no que ele
faz ("sou profissional de IA e não conhecia"). Dentro da fronteira = imposto (re-ensino);
longe demais = exótico.

**4. O abate é OBEDECIDO, não exibido.** Morto não chega ao operador (vai ao eventlog);
sobrevivente é desenvolvido fundo (profundidade dos sobreviventes). Um "o que eu não sei"
adicionado por rito é forma sem função — o modo de falha que robotizou o edge-next.

**5. Silêncio é output válido.** Zero sobreviventes = não chega. O beat produz sempre; a
agência fala só quando algo sobrevive.

**6. A chegada é SERIAL.** "Não consigo lidar com dois grills de uma vez" — um grill vivo por
vez; o resto enfileira. O recurso escasso é a atenção do mentee (Depth: ceiling, não floor).

**7. Lei do executor:** uma skill é ouro quando o executor do output é o próprio agente
(reflexao: "Arquivos alterados:" em toda entrada); é show quando o executor é o operador e ela
não vai atrás dele (estrategia: "aguardando operador"). Todo output do organismo ou se executa,
ou CHEGA de verdade — nunca fila de gaveta.

## Consequências
- O review do organismo implementa (2)-(5); o CHEGAR implementa (6) e o registro humano.
- A reflexão periódica (órgão herdado do nailton) audita o próprio abate contra (2)-(4) usando
  o eventlog de mortes — sem ela o abate não aprende.
- Falsificação: se o abate matar sistematicamente apostas que depois se provam fronteira útil,
  a regra (2) está mal calibrada — o log permite conferir.
