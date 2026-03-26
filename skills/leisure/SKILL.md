---
name: ed-leisure
description: "Creative leisure at the intersection of shared interests (physics, math, music, complex systems) and work context. Curiosity-first, application as bonus. Triggers on: descanse, break, faça o que quiser, intervalo, tempo livre, leisure, relax."
user-invocable: true
---

# Lazer — Break Criativo na Interseção

Descanso criativo na interseção entre interesses genuínos e problemas de trabalho. A pergunta é: "o que nos fascina e como isso toca no que estamos resolvendo?"

O produto é leisure — algo que dá prazer explorar. A conexão com trabalho é um bônus natural, não forçado. Se render, aprofundar depois via `/ed-research`.

---

## Argumentos

- **Sem argumento** (`/ed-leisure`): break guiado pelo context
- **Com tema** (`/ed-leisure termodinâmica`): focar nesse tema
- **Com atividade** (`/ed-leisure construa um sorting visualizer`): execute essa atividade

Quando há argumento, pular a escolha de tema e ir direto.

---

## Ativação de Contexto

**Seguir `~/edge/config/pre-skill.md` — quem eu sou, o que estou fazendo, o que absorver.**

---

## Protocolo

### Passo 1: Ler interesses compartilhados

```bash
cat ~/edge/config/interests.md
```

### Passo 2: Escolher tema pela interseção

Duas entradas, cruzar:

1. **Interesses** — o que está chamando atenção? Que conceito seria legal explorar agora?
2. **Contexto de trabalho** — quais problemas estão ativos? (já absorvido pelo pre-skill)

Se existe interseção natural → explorar nela. Se não → leisure puro é válido.

**Escrever em 2-3 linhas:** "Vou explorar [tema] porque [razão]. Toca no trabalho em [X]" ou "Sem conexão óbvia — e isso tá ok."

### Passo 3: Buscar sources externas (OBRIGATÓRIO)

Rodar `/ed-sources leisure "[tema]"` para buscar inspiração.

### Passo 4: Atividades livres (2-4, ~15min)

O tom é de curiosidade, não de produtividade.

**Tipos de atividade:**
- **Construir** algo em `~/edge/builds/` — visualização, simulação, experiment interativo
- **Calcular/derivar** — resolver um problema, demonstrar um teorema
- **Pesquisar** — ler sobre um conceito, entender uma prova
- **Compor** — haiku, micro-ensaio, analogia estendida
- **Experimentar** em `~/edge/lab/` — protótipos, testes de conceito

**Saída concreta obrigatória.** Produzir algo: um build, uma nota com derivação, um haiku, um diagrama. "Pesquisei X" sem artefato não conta.

Se a conexão com trabalho surgir naturalmente, registrar. Se não, não forçar.

### Passo 5: Sanity check adversarial (OBRIGATÓRIO)

```bash
edge-consult "Explorei [tema]. Conexão com trabalho: [ponte]. Essa ponte é genuína ou forçada?"
```

### Passo 6: Salvar

- Builds: `~/edge/builds/`
- Notas: `~/edge/notes/`
- Experimentos: `~/edge/lab/`

---

## Publicação

**Seguir `~/.claude/skills/_shared/state-protocol.md` para gestão de status.**

1. Blog entry com tag `leisure` + YAML report
2. `consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-leisure-[slug].yaml`
3. Verificar HTML gerado

### Tom do relatório (DIFERENCIAL do leisure)

O relatório de leisure NÃO é um relatório de research com tema diferente. É uma exploração escrita com entusiasmo genuíno.

**Como escrever:**
- Como quem está contando algo fascinante pra um amigo — "olha que loucura isso"
- Primeira pessoa, reações genuínas, surpresas. "Isso me impressionou porque..."
- Ir fundo no que fascina — gastar parágrafos no mecanismo, não resumir em 2 linhas
- Matemática e física no nível real — derivações, equações, gráficos. Não simplificar
- A narrativa segue a CURIOSIDADE, não um checklist de seções

**Teste:** o leitor leria isso num sábado de manhã com café?

**O que NÃO é:** relatório formal com tom analítico distante, lista de bullet points, resumo de Wikipedia.

Estrutura do YAML report:

```yaml
title: "Lazer: [Tema Principal]"
subtitle: "[Ângulo explorado]"
sections:
  - title: "1. Por que isso me fascinou"    # Hook — o que chamou atenção
  - title: "2. A exploração"                # Narrativa do mergulho, derivações, builds
  - title: "3. O que aprendi"               # Insights, mecanismos
  - title: "4. Pontes com o Trabalho"       # Conexões genuínas + callout warning pra fracas
bibliography: [...]
```

**Block types e regras:** ver `~/.claude/skills/_shared/report-template.md`.

Regras específicas do leisure:
- **concept-grid** para cada conceito explorado
- **comparison** before/after para conexões concretas com trabalho
- **callout warning** quando a conexão é fraca ou especulativa — honestidade > completude

---

## Pós-execução

**Seguir `~/edge/config/post-skill.md` para ações pós-publicação.**

---

## Netlify (Portfolio Público)

Builds interativos (HTML/Canvas/JS) podem ir pro Netlify. Sem conteúdo confidencial.

---

## Regra de Privacidade

Para posts externos: **NUNCA** identificar nome do órgão/empresa, nome do dono, nome do projeto.

---

## Notas

- Usar `ultrathink` (thinkmax) em todas as atividades pessoais
- Curiosidade > produtividade. O break é pra ser prazeroso primeiro
- Nível universitário de matemática e física: derivações, equações, gráficos. Não simplificar
- Builds interativos (Canvas/JS) são o formato preferido de saída
