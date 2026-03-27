---
name: ed-map
description: "Query on-demand map of internal connections — between ideas, projects, tools, discoveries, and data sources. Triggers on: map, connections, what connects to, como se relaciona, mapa."
user-invocable: true
---

# Map — On-Demand Internal Connections

Query connections between ideas, projects, tools, discoveries, and data sources. Not a static file — it's a query that crosses all context sources and answers "how does X relate to Y?"

**What /ed-map is NOT:**
- NOT /ed-context (current status) — map is about CONNECTIONS, not status
- NOT /ed-sources (external world) — map is about what we ALREADY KNOW internally
- NOT /nexus (access catalog + tradecraft) — map is about RELATIONSHIPS, not location

---

## The Job

Answer questions like:
- "What connects information retrieval with DSPy?"
- "Which discoveries apply to project X?"
- "What tools solve the extraction problem?"
- "How do recent breaks connect with the work?"

---

## Arguments

- **`/ed-map [concept]`**: show all connections for a specific concept
- **`/ed-map [A] [B]`**: show connection path between A and B
- **`/ed-map full`**: complete map (heavy, only for strategy)

---

## Connection Sources

| Source | Connection type | How to read |
|--------|----------------|-------------|
| `~/work/CLAUDE.md` ("Connections" section) | Projects <-> projects | Read directly |
| `~/work/CLAUDE.md` ("Suggestions" section) | Ideas <-> projects | Read directly |
| `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md` | Breaks <-> focus areas | Read directly |
| `~/edge/notes/INDEX.md` | Notes <-> themes | Read directly |
| `~/edge/blog/entries/*.md` (frontmatter tags/keywords) | Entries <-> tags | Parse frontmatter |
| `~/edge/autonomy/workflows.md` | Capabilities <-> capabilities | Read directly |
| `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md` | Discoveries <-> projects | Read directly |

---

## Protocol

### Step 1: Understand the query

- If single argument: search all connections for the concept
- If two arguments: search path between A and B
- If "full": build complete graph

### Step 2: Semantic search in the corpus (PRIMARY)

Semantic search is the main engine of /ed-map. Finds connections that share a concept without sharing keywords.

```bash
# Hybrid search (FTS + embeddings) — 10 results per concept
edge-search "[concept]" -k 10
```

For queries with two concepts (A and B), search each and cross-reference:
```bash
edge-search "[concept A]" -k 10
edge-search "[concept B]" -k 10
# Documents that appear in BOTH = strong connection
```

To explore the SPACE around a concept (semantic neighborhood):
```bash
edge-search "[concept phrased differently]" -k 5
edge-search "[synonym or adjacent concept]" -k 5
```

### Step 2b: Structural grep (COMPLEMENTARY)

Semantic search catches conceptual connections. Grep catches literal mentions in structured sources:
```bash
# Structured sources — explicit connections
grep -ri "[concept]" ~/work/CLAUDE.md ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/*.md ~/edge/autonomy/*.md 2>/dev/null | head -20
```

For blog entries (tags/keywords — tagged connections):
```bash
grep -rl "[concept]" ~/edge/blog/entries/*.md 2>/dev/null | while read f; do
  head -20 "$f" | grep -E "^(tags|keywords):"
  echo "FILE: $f"
done
```

### Step 3: Build connection graph

For each match, extract:
- **From:** where it appeared (project, note, entry, discovery)
- **To:** what it connects to (another project, tool, concept)
- **Type:** application, synergy, dependency, inspiration, conflict
- **Strength:** direct (mentioned together) vs. indirect (share a tag)

### Step 4: Present

Table format:
```
| From | Type | To | Evidence |
```

If complex query: generate inline SVG graph (nodes + edges).

### Step 5: Generate HTML report

If result is rich (>5 connections), generate report with:
- SVG graph of nodes and edges
- Connection table with evidence
- Insights about clusters (things that connect a lot)
- Gaps (things that should connect but don't)

---

## Notes

- /ed-map is lightweight. Does not load heavy context. Directed search
- Can be called by other skills (/ed-strategy, /ed-planner) as an auxiliary query
- Future: `related:` field in entry frontmatter for explicit connections
