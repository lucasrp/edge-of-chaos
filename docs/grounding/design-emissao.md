# Design da costura de emissão do grounding manifest (Loop R · faceta 1)

> Três designs radicalmente diferentes (design-it-twice, pocock-codebase-design), comparados em
> profundidade/localidade/costura. Vencedor: **C (transcript harvester) como espinha**, com dois
> enxertos de A (genus floor, tier declared) e dois de B (taxonomia de seca 2-fatores, dry_semantics
> por fonte). A porta do B **não se constrói** — decisão pela escada #248 (ver §4).

## 1. Os três candidatos (resumo honesto)

| | A — sweep ledger (agente apende) | B — porta genérica (ler emite) | C — harvester (substrato lê) |
|---|---|---|---|
| anti-esquecimento | gate no genus (pega ausência total; **testemunho, não prova** — linha-token derrota) | emissão no caminho único executar→retornar; bypass medido (não bloqueado) | **por construção** — não existe ato de emitir |
| PRISMA C36 (literal como-rodou) | auto-relatado, inverificável | capturado pela porta | **byte-idêntico do registro de execução** (verificado no store) |
| mudança nos skills/fluxos | scaffold + producers + delta + dig | todos os reads migram pra porta (ADR-0018 necessário) | **uma linha** (predispatch) — gather/wake/dig intocados |
| atribuição lens/intent | primeira pessoa (a melhor) | parâmetros da chamada | escada mapped/declared/inferred/unknown (mecânica no caso comum) |
| ADR-0001 | forte (não chama fonte) | **em tensão com a letra** ("no libexec primitive ever") | limpo — nunca fica entre agente e fonte |
| furo principal | omissão parcial/fabricação | chokepoint→bypass (cicatriz #248) | chamada de rede DENTRO de script (fronteira da tool ≠ da rede) |

**Fato decisivo (probe do C):** nenhum consumidor do manifest é in-session — briefing, bandit,
painel e calibragem são todos next-wake-or-later. A latência do post-hoc é **grátis**. Com isso, as
vantagens do A (rótulo vivo) e do B (captura no instante) perdem o único argumento que as tornava
necessárias; o C entrega a captura mais forte (transcript) sem disciplina nova e sem chokepoint.

## 2. A síntese: C-espinha + enxertos

**Espinha (C):** `tools/harvest.py` — `harvest()` cursor-guardada no idioma do sweep (estendendo o
glob a `subagents/`), `recognize()` pura (tool_use → row | None, fixtures douradas por via-form),
tabela de recognizers **derivada do mesmo `agent.yaml sources[].via`** (um seam, duas projeções),
evento `grounding.manifest` Tier-0 + `fold_grounding`/`grounding_at`. Atribuição em escada com tier
gravado (`mapped` mecânico via meta.json→toolUseId→prompt; `declared` opcional no payload do
dispatch.open; `inferred` LLM dark-by-default; `unknown` honesto). Canário roda no **próximo
predispatch** para secas pendentes; **`seca-verificada` nunca é escrita na row** — é fold que casa
suspect ↔ canary-pass (append-only intacto). Espelho OTel = projeção do evento. Retro-harvest:
recognizer melhor + cursor reset re-minera a história inteira.

**Enxerto A1 — genus floor sem ledger:** no close, rodar `recognize()` sobre o transcript VIVO da
sessão (o arquivo existe): artefato themed cujo dispatch não tem NENHUMA leitura reconhecida (nem
mundo, nem recall) → violação de genus, blocking, bounça com mensagem nomeada. Determinístico,
zero disciplina — reusa a função pura do C na costura do close. (Ambient: nunca gateia — R3.2.)

**Enxerto A2 — tier `declared` barato:** o dispatch.open (que já existe e já carrega payload) ganha
campos opcionais theme/intent — UMA declaração por dispatch, não N emissões por leitura.

**Enxerto B1 — seca com dois fatores:** o probe do X mostrou que canário-pass + 0-hit ≈
over-especificação; rotular `verificada` seria falso-negativo institucionalizado. Taxonomia final:
`verificada` (canário-pass E idiom conforme — o recognizer CHECA a query contra o idiom declarado,
ex. X >3 termos) · `suspeita:instrumento` (canário-fail) · `suspeita:overspecified` (canário-pass +
idiom violado) · `não-aplicável` (fonte never-dry — Exa, cujo risco é preenchimento confiante, não
seca). Tudo política de fold/recognizer, dirigida por `dry_semantics` declarado por fonte.

**Enxerto B2 — o tally de cegueira:** chamada network-shaped sem recognizer → `unrecognized`
contado e visível no painel (perna cega nunca silencia). Sobre o furo real do C (rede dentro de
script): regra de casa — script próprio que lê source **loga a query no stdout** (o extractor pega);
scripts conhecidos ganham recognizer coarse com `attribution: opaque-script`, contado.

**Por que a porta do B não se constrói agora:** seu valor único (captura no instante) o transcript
cobre com força maior; seu custo (ADR-0018, tensão com a letra do scaffold, gradiente-de-monstro)
é certo. Decisão pela escada do #248 aplicada ao próprio design: se a calibragem mostrar taxa alta
de `unrecognized`/`opaque-script` OU atrito real de leitura agêntica, a porta re-entra como
proposta — com o log sobrevivendo a ela de qualquer forma.

## 3. O que o bandit consome (fecho R4)

`fold_grounding` × `fold_source_yield` (join por dispatch/artefato): denominador = tentativas por
(source × interface × lens × geometry × intent-declarado); numerador = source.signal (similarity
graduada). **Só tiers `mapped`/`declared` alimentam aprendizado**; `inferred`/`unknown` aparecem no
painel, nunca no bandit (extensão natural do R4.2 — atribuição incerta é viés de instrumento tanto
quanto seca-suspeita).

## 4. Riscos assumidos (declarados)

Acoplamento ao formato de transcript da Anthropic (não-contratual; fixtures douradas no CI + misses
contados = falha visível, nunca silêncio) · atribuição reconstruída ≠ vivida (tier na row; o
consumidor sabe o que come) · retenção do store (heartbeat 3h ≪ 30d; risco real = backlog com
harvester desligado) · falso reconhecimento de curls de depuração (cai em ambient/unknown, fora do
bandit).
