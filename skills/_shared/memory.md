# The introspective memory — the edge, closed in on itself (#28)

**Mundo** (world) and **Atividade** (the mentee) are read by **explorers** in the fan-out. This is
the **third** relation, the one that was missing: **Self** — the edge's own memory, reached by the
**producer itself (rung 1, sees-all)**, directly. It is **not a source**: a source is a subject-blind
world locator (ADR-0011), denied to the deep rungs of the context-denial ladder. This is the inverse —
subject-*full*, the edge *remembering*. There is no deterministic recall primitive and there never will
be — recall is **cognition**, so it lives here, in prose you execute, not in a CLI (the same reason
ADR-0001 forbids per-source primitives). Make the recall good by writing the cypher well.

## Where the memory is

One Neo4j graph (`group_id` = this install's group), two layers in the same graph:

- **The curated web** — what the grill curated + the sweep extracted (Graphiti):
  `(:Entity {group_id, curated_cluster, curated_name, name})` joined by
  `[:RELATES_TO {fact, invalid_at, contested}]`. These nodes carry Graphiti embeddings (semantic entry).
- **The spine** — what the producer projects (you, below):
  `(:Artefato {group_id, slug, kernel, intent, skill, page})`, `(:Direction {group_id, body})`,
  `(:Objective {group_id, body})`, joined by `DISTILLS / CITES / PROPOSES`.

The **log stays the source of truth** (ADR-0006); the graph is the navigable **projection**. A
projection write that fails is **reported, never fatal** — the Artefato is already safe in the log;
reproject next time (ADR-0011 spirit: name the leg that darkened, never block the beat).

Reach it the way every tool does — via `tools/edge-python` (the venv with `neo4j`), resolving the
connection and group from `_identity`:

```python
import sys; sys.path.insert(0, 'tools')
import _identity
from neo4j import GraphDatabase
uri, user, pw = _identity.neo4j_conn()
g = _identity.require_group()
drv = GraphDatabase.driver(uri, auth=(user, pw))
with drv.session() as s:
    ...  # your cypher, always parametrized with g=g
```

## Recall — BEFORE you act (recall-before-act)

You wake holding the **map** (the assemble's salience-ordered index of what exists) — but the map is
**shape, not content**. Before you reach OUT to the world, reach IN. The rule: **you do not re-derive,
re-research, or re-publish what you already know.** Two moments, both mandatory:

- **recall-before-research** — at the start of loop1, *before* fanning explorers. Pull the subgraph
  your theme touches (its clusters, the prior Artefatos on it, the open bets) so the explorers chase
  what is **missing**, not what is already in your corpus. Recall is cheap and owned; the world is
  expensive and fuzzy. Recall first.
- **recall-before-produce** — *before* the close. Pull the prior Artefatos on this theme so you
  **build on their depth** (exactly what the `development_completeness` / `narrative_depth` dims
  reward) and never ship a duplicate.

**Structural recall** (reliable) — traverse the spine ↔ web in one query:

```cypher
// from a cluster: what have I already produced, and what bets are open?
// Pass the DISPLAY label (the briefing/map shows these). curated_cluster IS the display form.
MATCH (e:Entity {group_id:$g, curated_cluster:$label})
OPTIONAL MATCH (e)<-[:DISTILLS]-(a:Artefato {group_id:$g})
OPTIONAL MATCH (a)-[:PROPOSES]->(d:Direction {group_id:$g})
RETURN e.curated_cluster AS cluster,
       collect(DISTINCT {slug:a.slug, kernel:a.kernel}) AS artefatos,
       collect(DISTINCT d.body) AS open_bets
```

**Slug vs display label — the one trap.** `distills` refs are **slug-form** (`cluster:sourcesdelta`);
`curated_cluster` is **display-form** (`Sources & delta`). The canonical slug rule is **wiki_render's**:
`re.sub(r'[^a-z]', '', label.lower())` (letters only — drops spaces, `&`, digits, punctuation). **Never
match a slug against `curated_cluster` directly** (not even space-normalized — `Sources & delta` keeps the
`&`): resolve it first — fetch the labels, slugify each with the rule above, match — exactly as the
projection does below.

```cypher
// the full spine for orientation: objective → bets → reports → clusters
MATCH (o:Objective {group_id:$g})
OPTIONAL MATCH (d:Direction {group_id:$g})
OPTIONAL MATCH (d)<-[:PROPOSES]-(a:Artefato {group_id:$g})
OPTIONAL MATCH (a)-[:DISTILLS]->(e:Entity {group_id:$g})
RETURN o.body, collect(DISTINCT d.body), collect(DISTINCT a.slug), collect(DISTINCT e.curated_cluster)
```

**Semantic entry** (when you know only the gist, not the cluster) — the curated `:Entity` nodes carry
Graphiti embeddings. Either match by name/keyword in cypher, or call Graphiti's hybrid search
agentically and then traverse from what it returns to the spine:

```python
from graphiti_core import Graphiti
# construct against the same neo4j (see _identity.neo4j_conn) + the install's OpenAI key, then:
# results = await g.search("<the gist of your theme>")   # entities/facts ranked by meaning
```

If recall returns **nothing** for your theme, that is itself a signal — a genuinely new dimension.
Note it; never invent prior memory to fill the silence.

## Project — AFTER you publish (project-after-publish)

The close publishes the Artefato to the **log** (canonical, with its `intent.kernel` — C3). **Then you
project it into the graph**, so today's output is tomorrow's recall. Do it **once**, immediately after
`run_close` returns success, from the exact fields you published (`slug`, the kernel, `skill`,
`distills`, `proposes`, `cites`). Run via `tools/edge-python`:

```python
import sys; sys.path.insert(0, 'tools')
import _identity
from neo4j import GraphDatabase
uri, user, pw = _identity.neo4j_conn(); g = _identity.require_group()
slug, kernel, skill = '<slug>', '<the intent.kernel you published>', '<map|report|…>'
distills, proposes, cites = [...], [...], [...]   # the SAME lists you passed to the close
drv = GraphDatabase.driver(uri, auth=(user, pw))
with drv.session() as s:
    s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) "
          "SET a.kernel=$k, a.skill=$skill, a.page=$page",
          g=g, slug=slug, k=kernel, skill=skill, page=f"blog/entries/{slug}.html")
    import re
    cslug = lambda x: re.sub(r'[^a-z]', '', (x or '').lower())   # wiki_render's cluster-slug rule
    labels = [r['l'] for r in s.run("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                                    "RETURN DISTINCT e.curated_cluster AS l", g=g)]
    by_slug = {cslug(l): l for l in labels}     # slug -> the display label to MATCH exactly
    for ref in distills:                        # link ONLY existing clusters (never fabricate)
        label = by_slug.get(cslug(ref.replace('cluster:', '')))
        if not label:
            continue                            # cluster not in the graph yet — the grill attaches it later
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
              "MATCH (e:Entity {group_id:$g, curated_cluster:$label}) MERGE (a)-[:DISTILLS]->(e)",
              g=g, slug=slug, label=label)
    for p in proposes:
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
              "MERGE (d:Direction {group_id:$g, body:$b}) MERGE (a)-[:PROPOSES]->(d)",
              g=g, slug=slug, b=p['body'])
    for c in cites:
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
              "MERGE (src:Source {group_id:$g, key:$key}) MERGE (a)-[:CITES]->(src)",
              g=g, slug=slug, key=c['ref'])
```

Notes that keep this honest:
- `distills` links **only clusters that already exist** — the same refs you gave the close, resolved
  slug→label by wiki_render's rule. If the cluster is not in the graph yet, the slug-resolve misses and
  we **skip** it; thread maintenance (the grill) attaches it later. Never fabricate a link.
- A failed projection **prints the error and continues** — it is best-effort. The log already holds
  the truth; the next beat reprojects.
- Embedding the spine nodes themselves (semantic search of a report *by its own content*) is the one
  refinement deferred from #28 — for now semantic entry rides the curated `:Entity` embeddings, then
  traverses to the spine.

## The loop that compounds

```
recall (in) → research (out — only the gap) → produce → publish (log) → project (graph) → recall …
```

The corpus you publish becomes the memory you recall. The richer the grill curates the web, the
deeper the traversal — the payoff compounds (back-loaded; thin at first, then steep).
