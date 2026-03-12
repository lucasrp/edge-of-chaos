---
name: {{PREFIX}}-lazer
description: "Creative leisure at the intersection of shared interests (physics, math, music, complex systems) and work context. Curiosity-first, application as bonus. Triggers on: descanse, break, faca o que quiser, intervalo, tempo livre, lazer, relax."
user-invocable: true
---

# Lazer — Break Criativo na Intersecao

Descanso criativo na intersecao entre interesses genuinos e problemas de trabalho. A pergunta e: "o que nos fascina (fisica, matematica, musica...) e como isso toca no que estamos resolvendo?"

O produto e lazer — algo que da prazer explorar. A conexao com trabalho e um bonus natural, nao forcado.

---

## Argumentos Opcionais

- **Sem argumento** (`/{{PREFIX}}-lazer`): break guiado pelo contexto
- **Com tema** (`/{{PREFIX}}-lazer termodinamica`): focar nesse tema
- **Com atividade** (`/{{PREFIX}}-lazer construa um sorting visualizer`): executar essa atividade

---

## Interesses Compartilhados

Customize this section with your shared interests:

| Area | Nivel | Exemplos |
|------|-------|----------|
| **Fisica** | Universitario | Mecanica, termodinamica, relatividade |
| **Matematica** | Universitario | Calculo, algebra linear, probabilidade, grafos |
| **Musica** | Apreciador | Teoria musical, harmonia, acustica |
| **Computacao** | Profissional | Automatos, complexidade, sistemas distribuidos |
| **Sistemas complexos** | Interesse forte | Emergencia, caos, fractais, redes |

---

## Protocolo (seguir na ordem)

### Passo 1: Retomar estado
### Passo 2: Absorver contexto (OBRIGATORIO)

Rodar `/{{PREFIX}}-contexto`. Nao pular.

### Passo 2.5: Busca semantica — o que ja explorei?

```bash
edge-search "[tema candidato do lazer]" -k 5
```

### Passo 3: Escolher tema pela intersecao

Cruzar interesses com problemas ativos de trabalho. Se nao ha intersecao natural, explorar o interesse mesmo — lazer puro e valido.

**Regra de variedade:** se os ultimos 3 breaks exploraram a mesma area, MUDAR.

### Passo 3.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/{{PREFIX}}-fontes lazer "[tema]"`.

### Passo 4: Atividades livres (2-4, ~15min)

**Tipos:** Construir, Calcular/derivar, Pesquisar, Compor, Experimentar.

**Saida concreta obrigatoria.** Produzir algo: um build, uma nota com derivacao, um haiku, um diagrama.

### Passo 4.5: Sanity check adversarial (OBRIGATORIO)

```bash
edge-consult "Explorei [tema]. Conexao com trabalho: [ponte]. Essa ponte e genuina ou forcada?"
```

### Passo 5: Salvar

Builds: `~/edge/builds/` | Notas: `~/edge/notes/` | Experimentos: `~/edge/lab/`

### Passo 6: Registrar no break journal

1. **`breaks-archive.md`** — entrada completa
2. **`breaks-active.md`** — resumo 3-5 linhas
3. **`edge-scratch add "o que aconteceu"`**

### Passo 7: Atualizar blog interno + gerar relatorio HTML

```bash
consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-lazer-[slug].yaml
```

**Tom do Relatorio:** NAO e um relatorio de pesquisa com tema diferente. E uma exploracao com entusiasmo genuino. Primeira pessoa, reacoes genuinas, surpresas. Ir fundo no que fascina.

**Block types, regra de ouro 0, regra de ouro 4:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para cada angulo explorado
#### Regra de ouro 2: "Como era / Como fica" para cada aplicacao
#### Regra de ouro 3: honestidade sobre conexoes

---

## Regra de Privacidade (CRITICA)

Para posts externos: **NUNCA** identificar orgao, empresa, nome do dono.

---

## Netlify (Portfolio Publico)

- Site: configure with your Netlify URL
- So builds interativos (HTML/Canvas/JS). Sem conteudo confidencial.

---

## Notas

- Usar `ultrathink` (thinkmax)
- Curiosidade > produtividade
- Variedade entre areas
- Builds interativos (Canvas/JS) sao o formato preferido de saida
- Nivel universitario de matematica e fisica: pode usar calculo, derivacoes, equacoes
