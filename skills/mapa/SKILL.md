---
name: mapa
description: "Query on-demand map of internal connections — between ideas, projects, tools, discoveries, and data sources. Triggers on: mapa, map, connections, como se relaciona, what connects to."
user-invocable: true
---

# Mapa — Conexoes Internas On-Demand

Consulta de conexoes entre ideias, projetos, ferramentas, descobertas e fontes de dados. Nao e um arquivo estatico — e uma query que cruza todas as fontes de contexto e responde "como X se relaciona com Y?"

**O que /mapa NAO e:**
- NAO e /contexto (estado atual) — mapa e sobre CONEXOES, nao estado
- NAO e /fontes (mundo externo) — mapa e sobre o que JA SABEMOS internamente
- NAO e /nexus (catalogo de acesso + tradecraft) — mapa e sobre RELACOES, nao localizacao

---

## O Job

Responder perguntas do tipo:
- "O que conecta jurisprudencia com DSPy?"
- "Quais descobertas se aplicam ao assertia-nextjs?"
- "Que ferramentas resolvem o problema de extracao?"
- "Como os breaks recentes se conectam com o trabalho?"

---

## Argumentos

- **`/mapa [conceito]`**: mostrar todas as conexoes de um conceito especifico
- **`/mapa [A] [B]`**: mostrar caminho de conexao entre A e B
- **`/mapa full`**: mapa completo (pesado, so para estrategia)

---

## Fontes de Conexao

| Fonte | Tipo de conexao | Como ler |
|-------|----------------|----------|
| `~/tcu/CLAUDE.md` (secao "Conexoes") | Projetos ↔ projetos | Read direto |
| `~/tcu/CLAUDE.md` (secao "Sugestoes") | Ideias ↔ projetos | Read direto |
| `~/.claude/projects/-home-vboxuser/memory/breaks-active.md` | Breaks ↔ areas de foco | Read direto |
| `~/edge/notes/INDEX.md` | Notas ↔ temas | Read direto |
| `~/edge/blog/entries/*.md` (frontmatter tags/keywords) | Entries ↔ tags | Parse frontmatter |
| `~/edge/autonomy/workflows.md` | Capacidades ↔ capacidades | Read direto |
| `~/.claude/projects/-home-vboxuser/memory/descobertas.md` | Descobertas ↔ projetos | Read direto |

---

## Protocolo

### Passo 1: Entender a query

- Se argumento unico: buscar todas as conexoes do conceito
- Se dois argumentos: buscar caminho entre A e B
- Se "full": construir grafo completo

### Passo 2: Busca semantica no corpus (PRIMARIO)

A busca semantica e o motor principal do /mapa. Encontra conexoes que compartilham conceito sem compartilhar keywords.

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

A busca semantica pega conexoes conceituais. O grep pega mencoes literais em fontes estruturadas:
```bash
# Fontes estruturadas — conexoes explicitas
grep -ri "[conceito]" ~/tcu/CLAUDE.md ~/.claude/projects/-home-vboxuser/memory/*.md ~/edge/autonomy/*.md 2>/dev/null | head -20
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
- **De:** onde apareceu (projeto, nota, entry, descoberta)
- **Para:** o que conecta (outro projeto, ferramenta, conceito)
- **Tipo:** aplicacao, sinergia, dependencia, inspiracao, conflito
- **Forca:** direta (mencionados juntos) vs. indireta (compartilham tag)

### Passo 4: Apresentar

Formato table:
```
| De | Tipo | Para | Evidencia |
```

Se query complexa: gerar grafo SVG inline (nodes + edges).

### Passo 5: Gerar relatorio HTML

Se resultado rico (>5 conexoes), gerar relatorio com:
- Grafo SVG dos nodes e edges
- Table de conexoes com evidencia
- Insights sobre clusters (coisas que se conectam muito)
- Gaps (coisas que deveriam se conectar mas nao se conectam)

---

## Notas

- /mapa e leve. Nao carrega contexto pesado. Busca direcionada
- Pode ser chamado por outras skills (/estrategia, /planejar) como consulta auxiliar
- Futuro: campo `related:` no frontmatter das entries para conexoes explicitas
