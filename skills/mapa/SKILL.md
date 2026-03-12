---
name: {{PREFIX}}-mapa
description: "Query on-demand map of internal connections — between ideas, projects, tools, discoveries, and data sources. Triggers on: mapa, map, connections, como se relaciona, what connects to."
user-invocable: true
---

# Mapa — Conexoes Internas On-Demand

Consulta de conexoes entre ideias, projetos, ferramentas, descobertas e fontes de dados. Nao e um arquivo estatico — e uma query que cruza todas as fontes de contexto e responde "como X se relaciona com Y?"

**O que /{{PREFIX}}-mapa NAO e:**
- NAO e /{{PREFIX}}-contexto (estado atual)
- NAO e /{{PREFIX}}-fontes (mundo externo)

---

## O Job

Responder perguntas do tipo:
- "O que conecta X com Y?"
- "Quais descobertas se aplicam ao projeto Z?"
- "Que ferramentas resolvem o problema de extracao?"

---

## Argumentos

- **`/{{PREFIX}}-mapa [conceito]`**: mostrar todas as conexoes de um conceito
- **`/{{PREFIX}}-mapa [A] [B]`**: mostrar caminho de conexao entre A e B
- **`/{{PREFIX}}-mapa full`**: mapa completo (pesado, so para estrategia)

---

## Fontes de Conexao

| Fonte | Tipo de conexao | Como ler |
|-------|----------------|----------|
| `~/work/CLAUDE.md` | Projetos <-> projetos | Read direto |
| `memory/breaks-active.md` | Breaks <-> areas de foco | Read direto |
| `~/edge/notes/INDEX.md` | Notas <-> temas | Read direto |
| `~/edge/blog/entries/*.md` (frontmatter) | Entries <-> tags | Parse frontmatter |
| `~/edge/autonomy/workflows.md` | Capacidades <-> capacidades | Read direto |
| `memory/descobertas.md` | Descobertas <-> projetos | Read direto |

---

## Protocolo

### Passo 1: Entender a query
### Passo 2: Busca semantica no corpus (PRIMARIO)

```bash
edge-search "[conceito]" -k 10
```

### Passo 2b: Grep estrutural (COMPLEMENTAR)

### Passo 3: Construir grafo de conexoes

Para cada match, extrair: De, Para, Tipo, Forca.

### Passo 4: Apresentar

Formato table ou SVG inline.

### Passo 5: Gerar relatorio HTML (se resultado rico)

---

## Notas

- /{{PREFIX}}-mapa e leve. Busca direcionada
- Pode ser chamado por outras skills como consulta auxiliar
