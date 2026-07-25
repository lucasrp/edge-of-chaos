# Protocolo de leitura cega (experimentos de config de escrita)

**Origem:** v10-exp 2026-07-04 (PLAN.md + amendments do dig de validade + fixes da montagem).
Reusável para: re-rolls, feynman-exp, opus-vs-sonnet, futuros bake-offs.

## Produção (antes da leitura)
1. **Grounding congelado:** UM dossiê único; todos os arms escrevem dele, nunca do corpus cru
   (tira a estocasticidade do gather do confound).
2. **Um config-change por arm** (ablação); prompts salvos em `prompts/` (recuperabilidade — um
   re-run fiel muda só o modelo, byte-idêntico no resto).
3. **Modelo baseline = sonnet** (regra do operador: sonnet para arms de experimento; opus/forte
   só no follow-up "nos melhores" para medir o delta de modelo).
4. **Shell HTML idêntico** para todos (a forma só varia se a forma É o tratamento).
5. Writer nunca sabe do experimento (sem "arm", sem meta-comentário no artefato).

## Montagem da leitura
6. **Re-letragem:** se QUALQUER veredito público já nomeou letras (ex.: banca de forma), gerar
   permutação nova — ancoragem move ~14/100.
7. **Duplicatas cegas:** +2 cópias re-letradas (teste-reteste do leitor único; ele pode saber QUE
   existem, nunca QUAIS são).
8. **Key selada FORA da pasta de leitura** (`.{nome}-key`, chmod 600). Quem monta não olha o
   mapeamento se for opinar depois; o designer pré-registra ANTES da produção e não edita.
9. **Sentadas sorteadas** (2-3, ordem embaralhada por sentada, impressa no README e na ficha).
10. **Ficha (AVALIACAO.html):** dimensões 0-5 + 4 perguntas (leu numa passada? sabe o que fazer?
    publicaria? o que VAI USAR?) + notas livres; localStorage KEY único por rodada; exporta JSON.

## Leitura e análise
11. **Só top-3/bottom-3 decidem** — o meio é ruído. Leitor único experto = prática endossada
    para as perguntas de utilidade.
12. **Não premiar comprimento:** length é tratamento — logar palavras/arm (MECHANICS.md) e
    reportar a correlação comprimento×rank (~10-12 pts vêm de graça); as perguntas de utilidade
    são o desempate robusto.
13. **Re-roll n=1:** re-gerar top-3 e bottom-3 (mesmo prompt, subagente fresco, MESMO modelo) e
    checar se o ranking sobrevive — ruído geração-a-geração ≈ o efeito. Até lá, resultado é hipótese.
14. **Não discutir com o leitor até o JSON exportado.**
