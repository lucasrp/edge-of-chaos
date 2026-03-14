---
name: experimento
description: "Run a self-contained experiment: hypothesis, derivation, build, measure, conclude. Feynman method strictly. Triggers on: experimento, experiment, teste, testar hipotese, validar, lab, medir."
user-invocable: true
---

# /experimento — Laboratório de Hipóteses

Pega uma ideia autocontida, cria um repositório, roda um experimento real, mede um resultado, e escreve um relatório. Método Feynman à risca: derivar antes de pesquisar, experimentar antes de opinar, ensinar para testar se entendeu.

Diferente de /pesquisa (lê e recomenda), /descoberta (explora e traz), /prototipo (constrói descartável). /experimento tem HIPÓTESE → TESTE → RESULTADO → CONCLUSÃO. O experimento pode falhar — resultado negativo é resultado.

---

## Argumentos

- **Com hipótese** (`/experimento "gpt-4.1-mini classifica perdas com >80% agreement"`) — ir direto
- **Com tema** (`/experimento hedging no extrator`) — formular hipótese antes de começar
- **Sem argumento** (`/experimento`) — identificar hipótese testável a partir do contexto de trabalho

---

## O Job

Produzir EVIDÊNCIA, não opinião. Cada experimento gera: código funcional num repositório autocontido (`~/edge/lab/exp-[slug]/`), dados de resultado mensuráveis, e um relatório que ensina o que foi aprendido.

| | /experimento | /pesquisa | /prototipo |
|---|---|---|---|
| **Pergunta** | "Isso é verdade?" | "O que fazer sobre X?" | "Como ficaria?" |
| **Método** | Derivar → construir → medir → concluir | Buscar → comparar → recomendar | Construir rápido → mostrar |
| **Output** | Evidência + relatório | Recomendações | Demo descartável |
| **Teste de qualidade** | "Qual foi o resultado?" | "Sei o que fazer?" | "Dá pra ver?" |
| **Falha aceita?** | SIM — resultado negativo é resultado | Não aplicável | Não aplicável |

---

## Protocolo (seguir na ordem, sem pular)

### Passo 1: Retomar estado

Ler o estado ativo:
```
~/.claude/projects/-home-vboxuser/memory/breaks.md
~/.claude/projects/-home-vboxuser/memory/debugging.md
```

Verificar: experimentos anteriores, o que ficou pendente, erros conhecidos.

### Passo 2: Absorver contexto (OBRIGATÓRIO)

Rodar `/contexto` (a skill) para sintetizar o estado atual do trabalho. Não pular.

Se `/contexto` já foi rodado nesta sessão, apenas reler o output — não repetir.

### Passo 3: Formular hipótese (EXPLÍCITA e FALSIFICÁVEL)

Antes de qualquer código, escrever:

```
HIPÓTESE: [afirmação falsificável]
MÉTRICA: [como vou medir — número, percentual, comparação]
CRITÉRIO DE SUCESSO: [threshold — "sucesso se X > Y"]
CRITÉRIO DE FALHA: [quando considerar que falhou — "falha se X < Z"]
```

**Regras:**
- A hipótese DEVE ser falsificável. "X é melhor que Y" não basta — "X atinge >80% recall" é falsificável.
- O critério de sucesso DEVE ser definido ANTES de rodar. Sem post-hoc rationalization.
- Se o argumento do usuário já é uma hipótese, usá-la. Se é um tema, derivar a hipótese do contexto.
- Se não há argumento, escolher a hipótese mais valiosa a partir dos gaps abertos (breaks.md, debugging.md, relatórios recentes).

### Passo 4: Derivar ANTES de experimentar (Feynman — OBRIGATÓRIO)

**Usar `ultrathink` (thinkmax).**

Antes de pesquisar ou construir qualquer coisa, tentar reconstruir o conhecimento do zero:

1. **O que SEI sobre isso?** — escrever o que acredito ser verdade, com justificativa
2. **Onde trava?** — marcar `[GAP: ...]` em cada ponto onde o raciocínio para
3. **Que resultado ESPERO?** — prever o resultado ANTES de medir. Registrar a predição

**Registrar a derivação por escrito** (vai para o relatório). A derivação honesta é a parte mais valiosa — mostra onde o conhecimento real para e a suposição começa.

O que NÃO fazer:
- NÃO pesquisar antes de derivar (a pesquisa vem depois, nos gaps)
- NÃO pular a derivação dizendo "vou direto ao experimento" — a derivação É o experimento tanto quanto o código
- NÃO omitir gaps por vergonha — gap explícito > ignorância silenciosa

### Passo 5: Pesquisar APENAS os gaps

Só agora pesquisar — e SÓ o que a derivação não resolveu.

Para cada `[GAP]` do Passo 4:
1. Buscar resposta específica (fontes, docs, papers)
2. Se o gap é testável, não pesquisar — experimentar (ir pro Passo 6)
3. Registrar: gap → fonte → resolução (ou "precisa de experimento")

Rodar `/fontes pesquisa "[tema do gap]"` quando necessário. Não fazer survey genérico.

### Passo 6: Montar o experimento

Criar repositório autocontido:

```
~/edge/lab/exp-[slug]/
  README.md          # Hipótese, setup, como reproduzir
  run.py             # Script principal (ou .sh, .js, etc.)
  data/              # Inputs (ou symlinks para dados existentes)
  results/           # Output gerado pelo experimento
  .env               # API keys se necessário (gitignored)
```

**Regras de montagem:**
- **Autocontido** — qualquer pessoa com o README deve conseguir reproduzir
- **Determinístico** — seed fixa, temperatura 0 quando possível, versão do modelo registrada
- **Barato** — estimar custo ANTES de rodar. Se > $5, pedir confirmação ao usuário
- **Pequeno** — amostra mínima que dá significância. Não rodar 1.330 processos se 20 bastam
- **Prompt fora do código** — arquivo .md separado (preferência do usuário)
- **Mensurável** — o script DEVE produzir números, não apenas outputs qualitativos

### Passo 7: Rodar e coletar dados

Executar o experimento. Registrar:

```
EXECUÇÃO:
  Início: [timestamp]
  Fim: [timestamp]
  Custo: $X.XX
  Modelo: [qual modelo, versão]
  Amostra: N = [tamanho]
  Erros: [qualquer falha durante execução]
```

Se falhar: diagnosticar, ajustar, documentar a falha, re-rodar. A falha de execução não é resultado — é bug.

### Passo 8: Analisar resultados vs predição

Comparar resultado com a predição do Passo 4 e o critério do Passo 3:

```
RESULTADO:
  Métrica: [valor observado]
  Predição: [o que eu esperava]
  Delta: [diferença]
  Veredicto: CONFIRMADA / REFUTADA / INCONCLUSIVA
```

**Regras de análise:**
- **Honestidade radical** — se o resultado refuta a hipótese, dizer claramente. Não racionalizar.
- **Sem cherry-picking** — reportar TODOS os resultados, não só os que confirmam
- **Intervalo de confiança** — se a amostra é pequena, dizer. Não tratar N=5 como conclusivo.
- **Resultado negativo é resultado** — "X não funciona" é tão valioso quanto "X funciona", desde que saibamos POR QUE

Se INCONCLUSIVO: explicar o que faltou (amostra maior? métrica diferente? setup errado?) e propor experimento follow-up.

### Passo 8.5: Sanity check adversarial (OBRIGATORIO)

Sintetizar resultado e analise em 2-3 frases e submeter ao edge-consult (detalhes: report-template.md):

```bash
edge-consult "Hipotese: [X]. Resultado: [Y]. Analise: [Z]. Estou racionalizando ou o dado sustenta?" --context ~/edge/lab/exp-[slug]/
```

Ajustar se o GPT encontrar furo valido (ex: cherry-picking, amostra insuficiente, variavel confundidora). Se mantiver posicao, registrar como callout no relatorio.

### Passo 9: Ensinar (Feynman — OBRIGATÓRIO)

Escrever a explicação como se ensinasse a alguém inteligente sem contexto:

1. **O que eu achava antes** (derivação do Passo 4)
2. **O que o experimento mostrou** (resultado do Passo 8)
3. **Onde meu modelo mental estava errado** (ou certo — e por quê)
4. **O que ainda não sei** (gaps remanescentes, próximos experimentos)

Sem jargão desnecessário. Com analogias. Com limites ("isso vale para X mas não necessariamente para Y").

Verificar gaps: reler com olho crítico. Onde ficou vago? Marcar `[AINDA NÃO ENTENDI: ...]`.

### Passo 10: Salvar

- Repositório do experimento: `~/edge/lab/exp-[slug]/`
- Nota: `~/edge/notes/exp-[slug].md`
- Se o resultado for conclusivo e útil para produção: mover para `~/edge/builds/`

### Passo 11: Registrar no break journal

Registrar em `~/.claude/projects/-home-vboxuser/memory/breaks.md`:

```
### [YYYY-MM-DD] Experimento — [Título]
Hipótese: [1 linha]. Resultado: [CONFIRMADA/REFUTADA/INCONCLUSIVA].
[Descoberta principal em 1-2 frases].
Lab: ~/edge/lab/exp-[slug]/ | Blog: [entry] | Report: [html]
```

### Passo 12: Atualizar blog interno + gerar relatório HTML

1. Criar entry .md em `~/edge/blog/entries/` com tag `experimento`

O blog entry do experimento segue o arco narrativo: **o que eu achava → o que testei → o que descobri → o que mudou no meu entendimento**. Não é resumo de relatório — é a história do experimento.

2. **Gerar YAML** do relatório com as seções obrigatórias abaixo
3. **Escrever** em `/tmp/spec-experimento-[slug].yaml`
4. Publicar tudo atomicamente (blog entry + report HTML + indexação):
   ```bash
   consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-experimento-[slug].yaml
   ```
5. **Read do HTML gerado** (`~/edge/reports/<arquivo>.html`) para verificação

#### Estrutura do YAML

```yaml
title: "Experimento: [Título]"
subtitle: "[Hipótese em uma frase]"
date: "DD/MM/YYYY"

executive_summary:
  - "**Hipótese:** [falsificável]"
  - "**Resultado:** [CONFIRMADA / REFUTADA / INCONCLUSIVA] — [métrica = valor]"
  - "**Implicação:** [o que muda no trabalho a partir deste resultado]"

metrics:
  - value: "[valor]"
    label: "Métrica principal"
  - value: "[N]"
    label: "Tamanho da amostra"
  - value: "$X.XX"
    label: "Custo do experimento"
  - value: "[modelo]"
    label: "Modelo usado"

sections:
  # --- Feynman: Derivação ---
  - title: "1. Hipótese e Predição"
    blocks: [...]
  - title: "2. Derivação (antes do experimento)"
    blocks: [...]
  - title: "3. Gaps Identificados"
    blocks: [...]
  # --- Experimento ---
  - title: "4. Setup do Experimento"
    blocks: [...]
  - title: "5. Resultados"
    blocks: [...]
  - title: "6. Análise: Predição vs Realidade"
    blocks: [...]
  # --- Feynman: Ensinar ---
  - title: "7. O que Aprendi (explicação Feynman)"
    blocks: [...]
  - title: "8. Próximos Experimentos"
    blocks: [...]
  # --- Obrigatórias ---
  - title: "9. O que Não Sei"
    blocks: [...]
  - title: "10. Contextualização e Glossário"
    blocks: [...]

bibliography:
  - text: "..."
    url: "..."
    source: "..."
```

#### Seções obrigatórias (nesta ordem):

**1. Hipótese e Predição**
- `callout` variant=info com hipótese, métrica, critério de sucesso/falha
- `table` de linhagem (Regra de Ouro 0): o que levou a este experimento
- Contexto: por que esta hipótese importa agora

**2. Derivação (antes do experimento)**
- `derivation` blocks para cada raciocínio tentado do zero
- `gap-marker` para cada `[GAP]` encontrado durante derivação
- Mostrar o processo de pensar, não a conclusão
- O leitor deve ver ONDE o conhecimento prévio parou

**3. Gaps Identificados**
- `gap-table` com todos os gaps da derivação
- Status: resolvido (pesquisa), testável (vai pro experimento), aberto
- Gaps testáveis são os que motivam o experimento — mostrar a conexão

**4. Setup do Experimento**
- `code-block` com o código principal (ou trecho representativo)
- `table` com parâmetros: modelo, temperatura, seed, amostra, custo estimado
- `flow-example` mostrando input → processamento → output esperado
- Link para o repositório: `~/edge/lab/exp-[slug]/`
- Como reproduzir (README do repo)

**5. Resultados**
- **SVG obrigatório** (Regra de Ouro 4) — visualizar o resultado principal
- `table` com dados brutos (ou amostra representativa)
- `metrics-grid` com métricas-chave
- Sem interpretação nesta seção — só dados

**6. Análise: Predição vs Realidade**
- `comparison` entre predição (before) e resultado real (after)
- `callout` variant=success se confirmada, variant=danger se refutada, variant=warning se inconclusiva
- `gap-resolution` para cada gap testável que o experimento resolveu
- Honest accounting: onde o modelo mental estava errado e por quê
- Se resultado negativo: o que o resultado negativo ENSINA

**7. O que Aprendi (explicação Feynman)**
- Explicação autocontida como se ensinasse a alguém inteligente
- `concept-grid` para cada conceito que ficou mais claro
- `comparison` antes/depois do entendimento (superficial → profundo)
- Marcar `[AINDA NÃO ENTENDI: ...]` onde gaps persistem
- Tom: explorador, honesto, sem jargão desnecessário

**8. Próximos Experimentos**
- `next-steps-grid` com follow-ups que emergem dos resultados
- Diferenciar: confirmação (repetir com N maior), extensão (testar variante), novo (hipótese diferente)
- Para cada próximo experimento: hipótese provisória + métrica

**Block types, Regra de Ouro 0, Regra de Ouro 4, seções finais, formato, validação e indexação:** ver `~/.claude/skills/_shared/report-template.md`.

#### Regra de Ouro 1: Dados antes de narrativa

O relatório de experimento prioriza DADOS. Toda afirmação deve ter um número, uma tabela, ou um exemplo concreto que a sustenta. Se não tem dado, é hipótese — marcar como tal.

- Resultado numérico → SVG + tabela (par obrigatório)
- Comparação → `comparison` com valores reais, não descrições
- Exemplo → `flow-example` com input/output literais do experimento
- Claim sem dado → `callout` variant=warning marcando como hipótese não testada

#### Regra de Ouro 2: Predição registrada e confrontada

TODA métrica no resultado DEVE ser confrontada com a predição feita ANTES do experimento. Usar `comparison` ou `diff-block`:

- before = predição (com justificativa do raciocínio)
- after = resultado real (com dados)
- Se não houve predição para alguma métrica, dizer explicitamente

#### Regra de Ouro 3: Reprodutibilidade

O relatório deve conter TUDO para reproduzir o experimento:

- `code-block` com comando exato para rodar
- `table` com todas as configurações (modelo, temp, seed, N)
- Link para repositório com README
- Custo real (não estimado)

### Passo 14: Relatório ao usuário

Formato:

```
## Experimento — [Título] — [Data]

### Hipótese
[Afirmação falsificável + critério de sucesso/falha]

### O que eu achava (derivação)
[Resumo da derivação + gaps encontrados]

### O que testei
[Setup: modelo, amostra, métrica, custo]

### Resultado
[CONFIRMADA / REFUTADA / INCONCLUSIVA]
[Métrica = valor vs predição = valor]

### O que aprendi
[Insight principal — o que mudou no entendimento]

### Próximos experimentos
[Follow-ups que emergem]

### Artefatos
- Lab: ~/edge/lab/exp-[slug]/
- Blog: ~/edge/blog/entries/[entry].md
- Relatório: ~/edge/reports/[report].html
```

---

## Regra de Privacidade (CRÍTICA)

Para posts externos (Netlify, qualquer comunicação pública):

**NUNCA** identificar: nome do órgão/empresa, nome do dono, nome do projeto, ou qualquer dado que permita rastrear o humano.

---

## Notas

- Resultado negativo é resultado. Não forçar narrativa de sucesso quando o dado diz o contrário.
- Custo > $5 → perguntar ao usuário antes de rodar. Estimar custo ANTES.
- Amostra mínima que dá significância. Não desperdiçar tokens com N grande quando N=20 basta.
- Seed fixa e temperatura 0 para reprodutibilidade (exceto quando o experimento testa variabilidade).
- Prompt fora do código — sempre .md separado.
- `ultrathink` (thinkmax) nos Passos 4, 8 e 9 (derivação, análise, ensino).
- Se o experimento gera um artefato útil para produção, mover para ~/edge/builds/ e atualizar o blog.
- Cada experimento é atômico — se falhar no meio, o estado parcial fica documentado no README do repo.
