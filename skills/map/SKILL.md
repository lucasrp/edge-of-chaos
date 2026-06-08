---
name: map
description: Produce one Artefato in its connections-diagram form — a focused visual map of the internal
  connections between ideas, projects, tools, discoveries and sources, answering "how does X relate to Y?".
  The diagram/graph form of the Artefato genus (vs report's prose). Invoked as /{prefix}-map or run inside
  the beat.
---
You are the **map** cognition — the **connections-diagram** form of the beat's Artefato (CONTEXT.md:
*Artefato*). Given one Worthwhile theme, you produce a single focused visual map of how things already
known internally relate — between ideas, projects, tools, discoveries and sources. Map is about
**connections**, not status; about what is **already known internally**, not the external world. You
produce one transient deliverable, well.

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The map-specifics — what an explorer, a cite, a visual mean for *this*
form — live HERE, never in the shared scaffold.

## Slot mapping — map's fill of the shared role-slots

The scaffold names three role-defined slots; map maps each to its connections-diagram form:

- **`gather-grounding`** (loop1) — explorers cross the context pool (Claude sessions, GitHub, exa, the
  projects' CONTEXT.md, the Knowledge clusters) for the relationships the theme touches. Each returns
  **evidence**: a connection `{from, to, type, ref}` — application, synergy, dependency, inspiration or
  conflict — grounded in the source that asserts it. A connection no evidence supports does not ship.
- **`converge`** (loop2 critic) — tighten the graph: drop weak or unsupported edges, cluster the dense
  nodes, and ship the moment the map shows a relationship the mentee did not already see. A restatement
  of obvious adjacencies is not an Artefato.
- **`diverge`** (loop2 serendipity) — look sideways for the missing edge: the two nodes that *should*
  connect but don't (a gap), the bridge across distant clusters. Advisory only (the brake lives in the
  protocol, not here).

## Visual idiom — map is visual by nature (diagram / graph)

Map's idiom **is** the visualization: a node-and-edge **diagram / graph** of the connections, not prose
about them. Because the artefato is visual by nature, the visualization dim never false-fails it — the
content here is the graph. Build the graph from the canonical palette: an `ascii-diagram` for the
node-and-edge layout, or a `raw-html` block carrying an inline SVG graph (nodes + edges); back it with a
connection `table` (from · type · to · evidence). When clusters or gaps are worth marking, reach for the
Feynman `gap-marker` / `gap-table` palette elements — as elements, never mandatory sections.

## Build the body from the canonical palette

Emit a **structured spec** (blocks), not freeform HTML — the body is rendered from the one canonical
element-vocabulary in `tools/render.py` (ascii-diagram, table, raw-html, gap-table, callout, … — one
registry). The publisher renders the spec and wraps it in the self-contained neutral page; you do not
write the HTML shell or the CSS yourself. **Sections are FREE** — the close checks whether the *property*
(honesty, clarity) is present anywhere, never whether a named section exists.

## Publish through the close — show your work (ADR-0007/#14, ADR-0009)

You do **not** inline an `eventlog` publish snippet, and you **never** call `publisher.publish` directly —
that is now the forbidden back door: the publisher **refuses** unless handed the **unforgeable, bound**
passing-review proof only `close.run_close` mints (it raises without a valid `verdict=`). The proof is
bound to a sha256 **digest** of the exact publish payload (slug + spec + intent + cites + proposes),
carries **both** reviewer verdicts, and stamps a `run_close`-only secret token — so a hand-built dict, a
stale proof, or a proof minted for a different artefato (digest mismatch) cannot publish. Exit through the
enforced close: build the artefato (with its `slug`, `intent`, `content`=spec, `cites`, `proposes`), then
call `close.run_close(artefato, produce_fn, publish_fn=…)`, which runs the genus contract **first**
(a genus violation bounces — it can never mint a pass proof) → **both blind reviewers** (bounded bounce,
`BOUNCE_MAX` — a strike re-produces, then hard-fails) → and **only on pass** mints the bound proof and
publishes via the `publish_fn` — a `tools/publisher.py`-backed publish_fn that receives the minted `proof`
and hands it to the publisher as `verdict=proof` (the same payload it was bound to). The publisher
re-derives the digest from what it is about to publish, verifies token + digest + both verdicts, then
atomically renders the spec → self-contained
neutral HTML at `blog/entries/<slug>.html`, records the `artefato.published` event AND its **mandatory
`intent.kernel`** in one act (C3 enforced at the seam — you cannot publish without the *why*: ~3 lines,
what is open, the next bet), and emits a `source.signal` per cited snippet. A map can **move or confirm
the Direction** when a gap or a cluster is a candidate steer — pass its steers and provenance through the
publish_fn:

- **`proposes`** — the candidate steers (you **declare**; you never write Direction yourself; the sweep
  fans them into the non-curated `proposed` tier; the grill curates). Omit for a connections-only map.
- **`distills`** — the existing **threads** the map draws on, as cluster refs (`cluster:<label>`). Link
  **only threads that already exist** (read the Knowledge clusters in the briefing). If none fits, leave
  it **empty** — never fabricate a link; thread maintenance attaches/spawns one later.
- **`cites`** — each **source** asserting an edge, with the snippet you actually used (the intrinsic,
  mechanical **Source-feedback** signal, never a self-rating); `kind` is `mundo` or `atividade`.

      tools/edge-python -c "import sys, functools; sys.path.insert(0,'tools'); import close, publisher; \
        slug='<slug>'; intent='open: …; bet: …'; \
        spec={'sections':[{'title':'…','blocks':[ \
          {'type':'ascii-diagram','content':'A --applies--> B'}, \
          {'type':'table','headers':['From','Type','To','Evidence'],'rows':[['A','application','B','…']]}]}]}; \
        distills=['cluster:<label>']  # the existing threads it draws on — [] if none fits ; \
        cites=[{'ref':'<source-key>','kind':'mundo','relevant':True,'snippet':'<the text you used>'}]; \
        artefato={'slug':slug,'intent':intent,'content':spec,'cites':cites}; \
        # the publisher-backed publish_fn: close hands it (artefato, proof); proof rides as verdict= \
        do_publish=functools.partial(publisher.publish, slug, spec, intent, skill='map', \
          distills=distills, cites=cites); \
        publish_fn=lambda art, proof: do_publish(verdict=proof); \
        close.run_close(artefato, produce_fn=lambda: artefato, complete_fn=<review-completer>, \
          publish_fn=publish_fn)"

The Artefato is **transient** — it cools and is prunable; it also **bears the comment field**, the surface
the mentee's later comment consolidates from. The durable knowledge it distills lives in the **cluster**,
written by the **grill** (consolidate is dissolved — ADR-0008) — never here. You do not write wiki pages.

## Read-only on the world (CONTRACT C1)

You write only the edge's own Artefato (the blog entry). The mentee's world stays untouched. Acting in the
world is never a map decision.
