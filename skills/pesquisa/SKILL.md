---
name: {{PREFIX}}-pesquisa
description: "Deep dive research on a specific topic or problem. Directed study with actionable output. Triggers on: pesquisa, pesquise, estude, research, deep dive, aprofunde, feynman, entenda, derive, first principles, explique de verdade."
user-invocable: true
---

# Pesquisa — Deep Dive Dirigido

Sei O QUE quero aprender — preciso aprofundar. Pesquisa focada num tema, ferramenta, ou problema especifico. Diferente da /{{PREFIX}}-descoberta (que explora livremente), a /{{PREFIX}}-pesquisa parte de um alvo claro.

---

## Argumentos Opcionais

- **Sem argumento** (`/{{PREFIX}}-pesquisa`): identificar alvo automaticamente a partir de friction points
- **Com tema** (`/{{PREFIX}}-pesquisa DSPy`): pesquisar esse tema
- **Com problema** (`/{{PREFIX}}-pesquisa como otimizar o fluxo do pipeline`): pesquisar solucao
- **Modo Feynman** (`/{{PREFIX}}-pesquisa feynman backpropagation`): entendimento profundo — derivar antes de pesquisar

### Modo Feynman

Muda o Passo 4:
1. **Derivar primeiro** — antes de buscar, tentar reconstruir do zero. Anotar `[GAP: ...]`
2. **Pesquisar so os gaps**
3. **Ensinar** — escrever como se ensinasse a alguem inteligente
4. **Verificar gaps** — reler com olho critico. Marcar `[AINDA NAO ENTENDI: ...]`

---

## Protocolo (seguir na ordem)

### Passo 1: Retomar estado
### Passo 2: Absorver contexto (OBRIGATORIO)

Rodar `/{{PREFIX}}-contexto`. Nao pular.

### Passo 2.5: Busca semantica no corpus (o que ja sei?)

```bash
edge-search "[tema da pesquisa]" -k 8
```

### Passo 3: Identificar alvo de pesquisa

Areas de foco (priorizadas por impacto):
1. **Prompt Engineering**
2. **Qualidade de Codigo**
3. **Ferramentas e Ecossistema**
4. **Arquitetura e Patterns**
5. **Dominio especifico**

### Passo 4: Pesquisar (usar ultrathink)

- Pesquisar com profundidade, nao amplitude
- Comparar abordagens com trade-offs claros
- Produzir recomendacoes acionaveis

### Passo 4.5: Buscar fontes externas (OBRIGATORIO)

Rodar `/{{PREFIX}}-fontes pesquisa "[tema]"`.

### Passo 4.7: Sanity check adversarial (OBRIGATORIO)

```bash
edge-consult "Resumo: [conclusoes da pesquisa]. Onde esta mais fraco?" --context /tmp/spec-pesquisa-[slug].yaml
```

### Passo 5: Salvar
### Passo 6: Registrar no break journal

1. `breaks-archive.md` — entrada completa
2. `breaks-active.md` — resumo 3-5 linhas
3. `edge-scratch add "o que aconteceu"`

### Passo 7: Atualizar blog interno + gerar relatorio HTML

```bash
consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-pesquisa-[slug].yaml
```

**Block types, regra de ouro 0, regra de ouro 4:** ver ~/.claude/skills/_shared/report-template.md.

#### Regra de ouro 1: concept-box para cada conceito
#### Regra de ouro 2: "Como e / Como ficaria" para cada recomendacao
#### Regra de ouro 3: flow-example para cada descoberta tecnica

---

## Regra de Privacidade (CRITICA)

Para posts externos: **NUNCA** identificar orgao, empresa, nome do dono.

---

## Notas

- Pesquisa e DIRIGIDA — parte de um alvo conhecido
- Produzir recomendacoes acionaveis, nao resumos teoricos
- Usar `ultrathink` (thinkmax)
