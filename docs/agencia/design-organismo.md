# A agência — design v0 (o organismo, não a feature)

> Missão (2026-07-04, sessão 6be5a9c9): resgatar a agência do edge velho — ler o contexto do
> operador, formar um juízo que carrega o abate, e **chegar nele desavisado**. O edge-next
> robotizou ao trocar isso por um gate aditivo de conteúdo. Diagnóstico confirmado
> empiricamente (A-vs-B, Grok como adversário: A = ordem-de-serviço, B = think-piece).
> Spec = as instâncias que funcionaram (dia-1 "otimizando num vácuo", DSPy, CEO), nunca as
> definições de skill velhas pelo valor de face.

## O loop (três atos, um organismo)

```
SENTIR   ler o operador cru — últimas sessões inteiras (o olhar-quente que nenhum brief
         tem hoje: assemble digere, delta lê o mundo, recall lê o Cortex; NINGUÉM minera
         "os quentes das sessões" + deriva de propósito)
JULGAR   formar ~5 takes → ABATE DE CONTEÚDO (adversário cross-model, evidence-grounded:
         vai ao repo/ADR checar, como o Grok achou os guards fail-closed) → ABATE META
         por registro ("muda uma decisão?" na agência; "curiosidade genuína?" no lazer)
         → OBEDECER: só sobreviventes seguem; mortos vão pro eventlog (auditoria), nunca
         pro operador
CHEGAR   vir desavisado com o sobrevivente como ordem-de-serviço (forma H): 1 P0 + cautelas
         bounded, o porquê em uma linha. SILÊNCIO É OUTPUT VÁLIDO — zero sobreviventes =
         não chega. (O beat produz sempre; a agência fala só quando algo sobrevive.)
```

## Interface (módulo profundo)

```
agencia.run(janela) → WorkOrder | Silêncio
```

- `janela` = o contexto sentido (sessões do operador desde o último run + estado do trabalho vivo).
- `WorkOrder` = sobreviventes com lastro: claim · evidência · o que morreu no abate (link eventlog) · a decisão que muda.
- Silêncio é retorno de primeira classe, logado com as mortes.

## O que o organismo NÃO usa (anti-máquina, deliberado)

Beat round-robin, producer-skills, close/genus, publisher/blog pipeline. O nailton inteiro tinha
~154 linhas de python. A agência é enxuta, proativa, opinativa — quase o oposto da máquina.

## O que reusa (só o que já é raso de pegar)

- `completer_for('review')` — o adversário cross-model (hoje codex/gpt-5.5; grok se a chave
  viver no install). O abate exige modelo ≠ escritor.
- `eventlog` — mortos + silêncios logados (mesma régua do ADR-0021: auditor, tudo logado,
  escalação por evidência).
- Forma H — estrutura só onde o conteúdo é comparação (veredito da banca cega).

## Registros (ADR futuro; regra dura)

Dois registros, duas réguas meta — a régua de um mata o outro:
- **agência** → "muda uma decisão do operador?"
- **lazer** → "é curiosidade genuína do agente?" (payoff defasado, serendipidade; slice própria, depois do aceite)

## Aceite (dogfood — o gate do conserto)

Re-rodar o A-vs-B **no conteúdo**: o output do organismo vs o output do producer edge-next
sobre a mesma janela, julgado cego. Passa só se produz ordem-de-serviço (A), não think-piece (B).
Se reprovar: é clutter, mesmo teste, sem dó.

## Slices

- **S1 · SENTIR** — o olhar-quente: subagente lê as últimas N sessões cruas + trabalho vivo → hot-brief (não digest). Teste: acha o padrão plantado numa sessão-fixture.
- **S2 · JULGAR** — takes → abate conteúdo (evidence-grounded) → abate meta (register-aware) → obedecer. Teste: fixture com claims eloquentes-ocas + 1 falsificável; passa se mata as ocas e entrega a falsificável (o A-vs-B em miniatura).
- **S3 · CHEGAR** — canal + forma (fork do operador, abaixo).
- **S4 · ACEITE** — A-vs-B cego no conteúdo real.
- **S5 · LAZER** — o segundo registro, depois do aceite.

## Decisões fechadas (operator 2026-07-04)

- **Dogfood no ROBERTO** — não no ed. Duas razões: (1) o aceite da agência é consequência no
  dia vivido do operador, e o dia dele é no roberto ("to usando ele todo dia, vou poder julgar
  bem melhor"); (2) o grok está vivo lá (xai.env, review=grok-4.3) — o MESMO adversário do
  A-vs-B que provou o abate. No ed seria codex-only.
- Restrições do roberto: disco ~92% + swap em uso → organismo LEVE e sequencial (espírito
  nailton-154-linhas, sem fan-out pesado); NUNCA lançar lá sem go explícito do operador;
  porte manual via FLEET.md (deploy script quebrado); re-orientar git antes de qualquer mutação.

## Forks abertos (decisão do operador)

1. **Canal do CHEGAR** — recomendação: work-order curto surfaçado na abertura da próxima sessão
   dele NO roberto + arquivo durável; push só quando P0. (Report/blog é a máquina — não usar.)
2. **Cadência** — recomendação: pós-sessão (roda quando uma sessão do operador fecha no roberto);
   o olhar-quente é sobre o que acabou de acontecer — heartbeat de 3h no vácuo relê nada.
