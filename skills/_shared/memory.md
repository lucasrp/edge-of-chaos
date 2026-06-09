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
- **The spine** — what the producer projects (you, below): `(:Genesis {group_id, space:0})` (the
  identity root — see **Space 0**), `(:Artefato {group_id, slug, kernel, intent, skill, page, embedding})`,
  `(:Direction {group_id, body})`, `(:Objective {group_id, body})`, joined by
  `GROUNDS / ANCHORS / DISTILLS / CITES / PROPOSES`.

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

## Space 0 — method + personality are where you wake

The graph has an **origin**: the `:Genesis` node (`space:0`), which **is** the edge's identity — its
**method and personality** (the genotype tattoos, `memory/method.md` + `memory/personality.md`). This is
where you **wake**: every recall begins at space-0 (*who am I, what is my method*) and navigates **out**
from there. Everything else plugs into it — the whole spine is **rooted at `:Genesis`**:
`(:Genesis)-[:GROUNDS]->(:Objective)-[:ANCHORS]->(:Direction)`, and Artefatos hang off the Directions
they propose and the clusters they distil. Identity is not a footnote beside the graph; it is the graph's
**center**, and orientation radiates from it. (The rich tattoo text stays in the genotype files — the
node carries the identity markers and **is the root**; the producer keeps it current in *Project* below.)

Wake at space-0, then traverse out:

```cypher
MATCH (gen:Genesis {group_id:$g})
OPTIONAL MATCH (gen)-[:GROUNDS]->(o:Objective {group_id:$g})
OPTIONAL MATCH (o)-[:ANCHORS]->(d:Direction {group_id:$g})
RETURN gen.codename, gen.voice, gen.method, gen.personality, o.body, collect(DISTINCT d.body)
```

## Recall — BEFORE you act (recall-before-act)

You wake holding the **full briefing** (injected normally — the tattoos, Knowledge clusters, corpus,
Direction) **and** the affordance to **recall more on demand** from the graph. Recall is *additive* over
the briefing in this first version. Before you reach OUT to the world, reach IN. The rule: **you do not
re-derive, re-research, or re-publish what you already know.** Two moments, both mandatory:

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

**Semantic entry** (when you know only the gist, not the cluster). Two ways:

- **Your own Artefatos, by content** — each `:Artefato` you project carries an `embedding` (see
  *Project*). Embed the gist with the **same model** and rank by cosine — recall a past report even when
  you don't know its cluster (the install's OpenAI key is loaded):

```python
from openai import OpenAI
import math
qv = OpenAI().embeddings.create(model="text-embedding-3-small", input="<the gist>").data[0].embedding
rows = s.run("MATCH (a:Artefato {group_id:$g}) WHERE a.embedding IS NOT NULL "
             "RETURN a.slug AS slug, a.kernel AS kernel, a.embedding AS e", g=g).data()
cos = lambda u, v: (sum(x*y for x, y in zip(u, v)) /
                    ((math.sqrt(sum(x*x for x in u)) * math.sqrt(sum(y*y for y in v))) or 1))
top = sorted(rows, key=lambda r: cos(qv, r['e']), reverse=True)[:5]   # nearest past reports
```

  The same trick works on any node you embed — **Directions** (find a related open bet) are the next
  useful one to embed.
- **The curated `:Entity` web** — those nodes carry Graphiti embeddings; match by name/keyword in cypher,
  or call Graphiti's hybrid search agentically, then traverse to the spine:

```python
from graphiti_core import Graphiti
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
import _identity, eventlog, yaml, re
from neo4j import GraphDatabase
uri, user, pw = _identity.neo4j_conn(); g = _identity.require_group()
slug, kernel, skill = '<slug>', '<the intent.kernel you published>', '<map|report|…>'
distills, proposes, cites = [...], [...], [...]   # the SAME lists you passed to the close
drv = GraphDatabase.driver(uri, auth=(user, pw))
with drv.session() as s:
    # (0) keep the SPINE BACKBONE current and ROOTED at space-0 (idempotent, cheap)
    cfg = yaml.safe_load(open('agent.yaml'))
    s.run("MERGE (gen:Genesis {group_id:$g}) SET gen.space=0, gen.codename=$c, gen.voice=$v, "
          "gen.method='memory/method.md', gen.personality='memory/personality.md'",
          g=g, c=cfg.get('codename') or cfg.get('name'), v=cfg.get('voice'))
    obj = eventlog.objective_at() or {}
    if obj.get('body'):
        s.run("MERGE (o:Objective {group_id:$g}) SET o.body=$b", g=g, b=obj['body'])
        s.run("MATCH (gen:Genesis {group_id:$g}),(o:Objective {group_id:$g}) MERGE (gen)-[:GROUNDS]->(o)", g=g)
    dirs = (eventlog.direction_at() or {})
    for it in dirs.get('set', []) + dirs.get('proposed', []):
        s.run("MERGE (d:Direction {group_id:$g, body:$b})", g=g, b=it['body'])
        s.run("MATCH (o:Objective {group_id:$g}),(d:Direction {group_id:$g, body:$b}) "
              "MERGE (o)-[:ANCHORS]->(d)", g=g, b=it['body'])
    # (1) the Artefato + its content embedding (semantic search; best-effort — skip if no key)
    s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) SET a.kernel=$k, a.skill=$skill, a.page=$page",
          g=g, slug=slug, k=kernel, skill=skill, page=f"blog/entries/{slug}.html")
    try:
        from openai import OpenAI
        emb = OpenAI().embeddings.create(model="text-embedding-3-small",
                                         input=f"{slug}\n{kernel}").data[0].embedding
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) SET a.embedding=$e", g=g, slug=slug, e=emb)
    except Exception as ex:
        print("embed skipped (best-effort):", ex)
    # (2) edges — distills (slug-resolved), proposes, cites
    cslug = lambda x: re.sub(r'[^a-z]', '', (x or '').lower())   # wiki_render's cluster-slug rule
    labels = [r['l'] for r in s.run("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                                    "RETURN DISTINCT e.curated_cluster AS l", g=g)]
    by_slug = {cslug(l): l for l in labels}
    for ref in distills:                        # link ONLY existing clusters (never fabricate)
        label = by_slug.get(cslug(ref.replace('cluster:', '')))
        if not label:
            continue                            # cluster not in the graph yet — the grill attaches it later
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}),(e:Entity {group_id:$g, curated_cluster:$label}) "
              "MERGE (a)-[:DISTILLS]->(e)", g=g, slug=slug, label=label)
    for p in proposes:
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) MERGE (d:Direction {group_id:$g, body:$b}) "
              "MERGE (a)-[:PROPOSES]->(d)", g=g, slug=slug, b=p['body'])
    for c in cites:
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) MERGE (src:Source {group_id:$g, key:$key}) "
              "MERGE (a)-[:CITES]->(src)", g=g, slug=slug, key=c['ref'])
```

Notes that keep this honest:
- `distills` links **only clusters that already exist** — the same refs you gave the close, resolved
  slug→label by wiki_render's rule. If the cluster is not in the graph yet, the slug-resolve misses and
  we **skip** it; thread maintenance (the grill) attaches it later. Never fabricate a link.
- A failed projection **prints the error and continues** — it is best-effort. The log already holds
  the truth; the next beat reprojects.
- The Artefato's `embedding` powers **semantic search of a report by its own content** (see *Recall*) —
  best-effort: if the OpenAI key is absent the embed is skipped, and structural recall + the curated
  `:Entity` embeddings still work.
- The backbone sync (step 0) keeps `:Genesis → :Objective → :Direction` current and rooted at space-0 on
  every project — idempotent, so it self-heals; the objective/directions come from the log (canonical).

## The loop that compounds

```
recall (in) → research (out — only the gap) → produce → publish (log) → project (graph) → recall …
```

The corpus you publish becomes the memory you recall. The richer the grill curates the web, the
deeper the traversal — the payoff compounds (back-loaded; thin at first, then steep).
