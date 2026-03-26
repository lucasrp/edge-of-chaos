---
name: ed-discovery
description: "Discover useful tools, concepts, or mental models that apply to real work problems. Like a well-read friend giving you a practical insight. Triggers on: discovery, discover, explore new, new tool, bizu."
user-invocable: true
---

# Descoberta — Insight Prático

Explorar livremente e trazer algo útil. Pode ser uma ferramenta, um conceito, um modelo mental, uma palavra de outra cultura, um padrão de outra indústria — qualquer coisa. A busca é livre. O que importa é que no final, a contextualização ao trabalho seja CLARA e detalhada.

Como aquele amigo bem informado que traz coisas que você nunca teria encontrado sozinho, mas explica bem por que aquilo importa pra você.

---

## Argumentos

- **Sem argumento** (`/ed-discovery`): explorar livremente e trazer algo útil
- **Com direção** (`/ed-discovery algo para testar prompts`): buscar nessa direção específica

---

## O que é uma Boa Descoberta

Pode ser qualquer coisa, desde que tenha aplicação prática bem contextualizada:

- **Ferramentas** — "você está ajustando prompts na mão? DSPy otimiza automaticamente"
- **Conceitos** — "Hamilton Three-Layer: governança da Apollo é exatamente o que o heartbeat faz"
- **Padrões de outras indústrias** — "Andon cord da Toyota: fail-fast no pipeline"
- **Palavras/conceitos de outras culturas** — "Genchi genbutsu: vá e veja por si mesmo"

**O que NÃO é:** algo interessante mas sem conexão clara ("Physarum resolve labirintos — legal, mas e daí?").

---

## Ativação de Contexto

**Seguir `~/edge/config/pre-skill.md` — quem eu sou, o que estou fazendo, o que absorver.**

---

## Protocolo

### Passo 1: Explorar

A busca é livre. Pode partir de:
- Um problema do trabalho que quer resolver
- Algo que viu numa research e chamou atenção
- Curiosidade pura sobre um tema adjacente
- Trending em tech, ciência, design, gestão, qualquer área

Pode buscar em qualquer lugar:
- Ecossistema de ferramentas, GitHub, HN, papers
- Outras indústrias (manufatura, aviação, medicina)
- Outras culturas (conceitos japoneses, filosofias, palavras sem tradução)
- História (como problemas análogos foram resolvidos no passado)

### Passo 2: Buscar sources externas (OBRIGATÓRIO)

Rodar `/ed-sources discovery "[tema]"` para explorar todas as sources externas (X, HN, Web, ArXiv).

A própria busca pode ser a discovery — um tweet, post do HN, ou paper que aponta algo que vale researchr a fundo.

### Passo 3: Pesquisar com profundidade

Usar `ultrathink` (thinkmax).

Para FERRAMENTAS: o que é, como funciona, como começar, custo, limitações.

Para CONCEITOS: origem e context original, a essência, **aplicação detalhada** ao nosso context específico — qual projeto, qual etapa, "como era" vs "como fica".

### Passo 4: Salvar notas

`~/edge/notes/discovery-[nome].md` — sempre incluir: o que é, context original, **aplicação ao trabalho** (obrigatório), sources.

### Passo 5: Registrar discovery

Adicionar no topo de `discoverys.md`:

```markdown
## [YYYY-MM-DD] [Nome] — [Frase curta] [PENDENTE]

**Tipo:** [ferramenta | conceito | padrão | modelo mental]
**Problema:** [Qual fricção/gap endereça]
**O que é:** [2-3 frases claras]
**Aplicação:** [Conexão CONCRETA — qual projeto, etapa, como muda]
**Para começar:** [Primeiro passo prático]
**Esforço:** [baixo | médio | alto]
**Notas:** `~/edge/notes/discovery-[nome].md`
```

---

## Publicação

**Seguir `~/.claude/skills/_shared/state-protocol.md` para gestão de status.**

1. Blog entry com tag `discovery` + YAML report
2. `consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-discovery-[slug].yaml`
3. Verificar HTML gerado

Estrutura do YAML report:

```yaml
title: "Descoberta: [Nome]"
subtitle: "[O que resolve]"
sections:
  - title: "1. O Problema"       # Qual fricção motivou
  - title: "2. A Descoberta"     # O que é, concept-grid obrigatório
  - title: "3. Aplicação"        # comparison before/after obrigatório
  - title: "4. Para Começar"     # next-steps-grid
bibliography: [...]               # OBRIGATÓRIO
```

**Block types e regras:** ver `~/.claude/skills/_shared/report-template.md`.

---

## Pós-execução

**Seguir `~/edge/config/post-skill.md` para ações pós-publicação** (notificar, atualizar estratégia).

---

## Regra de Privacidade

Para posts externos: **NUNCA** identificar nome do órgão/empresa, nome do dono, nome do projeto.
