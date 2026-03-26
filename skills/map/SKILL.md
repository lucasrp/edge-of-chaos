---
name: ed-map
description: "Query on-demand map of internal connections — between ideas, projects, tools, discoveries, and data sources. Triggers on: map, map, connections, como se relaciona, what connects to."
user-invocable: true
---

# Mapa — Conexoes Internas On-Demand

Consulta de conexoes entre ideias, projetos, ferramentas, discoverys e sources de dados. Nao e um arquivo estatico — e uma query que cruza todas as sources de context e responde "como X se relaciona com Y?"

**O que /ed-map NAO e:**
- NAO e /ed-context (status atual) — map e sobre CONEXOES, nao status
- NAO e /ed-sources (mundo externo) — map e sobre o que JA SABEMOS internamente
- NAO e /nexus (catalogo de acesso + tradecraft) — map e sobre RELACOES, nao localizacao

---

## O Job

Responder perguntas do tipo:
- "O que conecta information retrieval com DSPy?"
- "Quais discoverys se aplicam ao projeto X?"
- "Que ferramentas resolvem o problema de extracao?"
- "Como os breaks recentes se conectam com o trabalho?"

---

## Argumentos

- **`/ed-map [conceito]`**: mostrar todas as conexoes de um conceito especifico
- **`/ed-map [A] [B]`**: mostrar caminho de conexao entre A e B
- **`/ed-map full`**: map completo (pesado, so para strategy)

---

## Fontes de Conexao

| Fonte | Tipo de conexao | Como ler |
|-------|----------------|----------|
| `~/work/CLAUDE.md` (secao "Conexoes") | Projetos ↔ projetos | Read direto |
| `~/work/CLAUDE.md` (secao "Sugestoes") | Ideias ↔ projetos | Read direto |
| `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md` | Breaks ↔ areas de foco | Read direto |
| `~/edge/notes/INDEX.md` | Notas ↔ temas | Read direto |
| `~/edge/blog/entries/*.md` (frontmatter tags/keywords) | Entries ↔ tags | Parse frontmatter |
| `~/edge/autonomy/workflows.md` | Capacidades ↔ capacidades | Read direto |
| `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md` | Descobertas ↔ projetos | Read direto |

---

## Protocolo

### Passo 1: Entender a query

- Se argumento unico: buscar todas as conexoes do conceito
- Se dois argumentos: buscar caminho entre A e B
- Se "full": construir grafo completo

### Passo 2: Busca semantica no corpus (PRIMARIO)

A busca semantica e o motor principal do /ed-map. Encontra conexoes que compartilham conceito sem compartilhar keywords.

```bash
# Busca hibrida (FTS + embeddings) — 10 resultados por conceito
edge-search "[conceito]" -k 10
```

Para queries com dois conceitos (A e B), buscar cada um e cruzar:
```bash
edge-search "[conceito A]" -k 10
edge-search "[conceito B]" -k 10
# Documentos que aparecem em AMBOS = conexao forte
```

Para explorar o ESPACO ao redor de um conceito (vizinhanca semantica):
```bash
edge-search "[conceito formulado de forma diferente]" -k 5
edge-search "[sinonimo ou conceito adjacente]" -k 5
```

### Passo 2b: Grep estrutural (COMPLEMENTAR)

A busca semantica pega conexoes conceituais. O grep pega mencoes literais em sources estruturadas:
```bash
# Fontes estruturadas — conexoes explicitas
grep -ri "[conceito]" ~/work/CLAUDE.md ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/*.md ~/edge/autonomy/*.md 2>/dev/null | head -20
```

Para blog entries (tags/keywords — conexoes tagueadas):
```bash
grep -rl "[conceito]" ~/edge/blog/entries/*.md 2>/dev/null | while read f; do
  head -20 "$f" | grep -E "^(tags|keywords):"
  echo "FILE: $f"
done
```

### Passo 3: Construir grafo de conexoes

Para cada match, extrair:
- **De:** onde apareceu (projeto, nota, entry, discovery)
- **Para:** o que conecta (outro projeto, ferramenta, conceito)
- **Tipo:** aplicacao, sinergia, dependencia, inspiracao, conflito
- **Forca:** direta (mencionados juntos) vs. indireta (compartilham tag)

### Passo 4: Apresentar

Formato table:
```
| De | Tipo | Para | Evidencia |
```

Se query complexa: gerar grafo SVG inline (nodes + edges).

### Passo 5: Gerar report HTML

Se resultado rico (>5 conexoes), gerar report com:
- Grafo SVG dos nodes e edges
- Table de conexoes com evidencia
- Insights sobre clusters (coisas que se conectam muito)
- Gaps (coisas que deveriam se conectar mas nao se conectam)

---

## Notas

- /ed-map e leve. Nao carrega context pesado. Busca direcionada
- Pode ser chamado por outras skills (/ed-strategy, /ed-planner) como consulta auxiliar
- Futuro: campo `related:` no frontmatter das entries para conexoes explicitas
