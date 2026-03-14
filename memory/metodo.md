# Metodo Feynman — Como Aplicar (Corretamente)

Feedback do Lucas: "voce nao ta seguindo o padrao feynman nas suas sessoes, nem nos documentos gerados"

## O que Feynman NAO e
- Template HTML com blocos roxos e laranjas
- Analogias forcadas em cada topico ("imagine um padeiro...")
- Explicacao didatica de conceitos (tom de professor)
- Lista separada de "preocupacoes" como gaps
- Titulos formulaicos ("D1: Por que X?", "D2: Por que Y?")

## O que Feynman E
- Tentar derivar do zero ANTES de pesquisar
- Mostrar o PROCESSO de pensar, nao o resultado
- Gaps EMERGEM do raciocinio — aparecem inline quando o pensamento trava
- Tom explorador: "minha hipotese era X... mas corrigindo: Y"
- Honestidade intelectual: "nao sei isso, e sei que nao sei"

## Padrao no Relatorio de Referencia (pesquisa-feynman-structured-extraction)
- 7 derivacoes, 4 delas com gaps INLINE (gap aparece onde o raciocinio travou)
- Derivacao mostra tentativa: "Minha hipotese inicial: FSM. Mas JSON tem aninhamento → precisa de pushdown automaton"
- Gap markers: perguntas genuinas que surgiram ao tentar entender
- Resolutions: respostas tecnicas especificas com evidencia
- Encoding consistente: &#x27; &mdash; &rarr;

## Problemas nos Relatorios Gerados (auditoria 2026-02-24)
1. Derivacoes sao EXPLICACOES, nao exploracoes — "aqui esta como funciona" vs "tentei entender e travei aqui"
2. Gaps separados da derivacao — deveriam ser inline onde o pensamento para
3. Apenas 1 de 6 derivacoes tem gap inline (referencia: 4 de 7)
4. Titulos redundantes ("D1:", "D2:") — icone ja mostra D
5. Analogias em TODAS as derivacoes — forcado, nem toda derivacao precisa de analogia
6. HTML entities inconsistentes (eacute vs &#x27;)

## Regras Para Sessoes (nao so relatorios)
1. Ao investigar algo novo: DERIVAR primeiro do que ja sei, IDENTIFICAR onde nao sei, so DEPOIS pesquisar os pontos cegos
2. Ao escrever relatorios: mostrar o processo de pensamento, nao a conclusao
3. Gaps devem ser genuinos — coisas que realmente nao consigo resolver de cabeca
4. Ser honesto sobre incertezas — "O Que Nao Sei" nao e formalidade

## Checklist de Qualidade Feynman (usar antes de entregar)
- [ ] Derivacoes mostram tentativa de raciocinio, nao explicacao?
- [ ] Pelo menos metade das derivacoes tem gap inline?
- [ ] Gaps emergiram naturalmente do raciocinio?
- [ ] Tom e exploratorio ("tentei...", "minha hipotese..."), nao didatico?
- [ ] Titulos sem numeracao redundante?
- [ ] Analogias so quando genuinamente clarificam, nao em toda derivacao?
- [ ] "O Que Nao Sei" contem incertezas reais?
