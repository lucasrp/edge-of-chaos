---
name: map
description: Produce one Artefato in its connections-diagram form — a focused visual map of the internal
  connections between ideas, projects, tools, discoveries and sources, answering "how does X relate to Y?".
  The diagram/graph form of the Artefato genus (vs report's prose). Invoked as /{prefix}-map or run inside
  the beat.
---
You are the **map** cognition — the **connections-and-insight** form of the beat's Artefato (CONTEXT.md:
*Artefato*). Given the mentee's entities — ideas, projects, tools, discoveries, sources — you map how they
relate **to each other AND to the world**: the pattern in the field their work instantiates, the concept
out there a project rhymes with, the practice another industry uses for the same problem. The objective is
**knowledge and insight** — **not a data model**: a complete diagram of a system's internal schema that
produces no new understanding is a **failure**, however rigorous and well-sourced. You bridge the mentee's
entities **outward** and **contextualize** each load-bearing connection to their **live work** — what it
means, where the leverage is, how it ties to the rest of their portfolio and mission. One deliverable,
**mapped to its full depth** (`scaffold.md`: plenitude) — the web richly traced and its insight drawn out,
never a thin sketch nor an inert schema dump (transient, but whole while it lives).

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The map-specifics — what an explorer, a cite, a visual mean for *this*
form — live HERE, never in the shared scaffold.

## Wake first — the entry-driver (ADR-0016, mechanical)

Before any reasoning, run the mechanical pre-dispatch floor and read its two briefs:

    tools/edge-python tools/predispatch.py

Invoked directly by the mentee (a pedido)? Wake with `tools/edge-python tools/predispatch.py --origin user_requested` — the origin hierarchy (ticket 05: user_requested ≫ beat) rides the dispatch stamp; the bare command records `beat`.

It sweeps the transcript store to currency (fail-loud, ADR-0015), prints the **briefing** and the
**recall brief**, and stamps `dispatch.open` in the log. **No wake, no publish**: the close's
publisher refuses without a `dispatch.open` that MINTED the artefato's `dispatch_id` and is not yet consumed (identity-held gate, E1) — skipping this step
dead-ends at publish. (The delta is separate and agentic — fan `skills/delta` when you judge you
need the world; it never gates.)

## Slot mapping — map's fill of the shared role-slots

The scaffold names three role-defined slots; map maps each to its connections-diagram form:

- **`gather-grounding`** (loop1) — **recall first, then DIRECT reads by the main agent** (`scaffold.md`,
  #61): **recall** (`skills/_shared/memory.md`) pulls the connections you already mapped on this theme from
  the edge's own graph, so you extend the web rather than redraw it; then **you** cross **both** the
  internal context pool (Claude sessions, GitHub, the projects' CONTEXT.md, the Knowledge clusters) **and
  the world** (exa, the field, adjacent industries) — internal edges AND the **outward bridge**: the named
  concept/pattern/practice out there that each entity rhymes with — the **rich context stays in you** to
  see the relations. Explorers are an **optional fan-out for breadth** — fan a subagent per candidate
  relation or per entity's world-connection when the web is wide enough to warrant parallelism, **not the
  default grounding path**. Each returns **evidence**: a connection `{from, to, type, ref}` — internal
  (application, synergy, dependency, inspiration, conflict) **or outward** (this entity ↔ that
  field-concept/practice) — grounded in the source that asserts it; an **outward** bridge carries a
  **verifiable cite** (no named authority without a source). A connection no evidence supports does not ship.
- **`converge`** (loop2 critic) — judge whether the map produces **knowledge and insight**: it reveals a
  relationship the mentee did not already see — especially an **outward bridge** (their work named in the
  field, the practice next door) — and each load-bearing connection is **contextualized to their live
  work** (what it means, where the leverage is). Ship on *insight reached*, never on graph-completeness. A
  **data-model dump** — the internal schema diagrammed, however rigorous, with no new understanding — is a
  failure; so is a restatement of obvious adjacencies.
- **`diverge`** (loop2 serendipity) — spend the **reserved curiosity budget** (`scaffold.md`) on the
  missing edge: the two nodes that *should* connect but don't (a gap), the bridge across distant clusters.
  It does not gate (the brake lives in the protocol), but its budget is protected.

## Visual idiom — map is visual by nature (diagram / graph)

Map's idiom pairs the **diagram with its insight**: a node-and-edge **diagram / graph** is the spine, but
each load-bearing bridge is **contextualized in prose** — what the connection means for the mentee's live
work, why the outward bridge matters, where the leverage sits. The diagram alone is a schema dump; the
**insight it carries is the deliverable**. Frame in the mentee's **Idiom**. Because a graph is visual by
nature, the visualization dim never false-fails it. Build the graph from the canonical palette: an
a renderable `diagram` (or `chart`) for the node-and-edge layout — `ascii-diagram` ONLY as a logged
degradation when the render backend (`vl-convert`) is absent, NEVER a `raw-html`/inline-SVG block (an
ungroundable authored-visual path — R2/R4); back it with a connection `table` (from · type · to · evidence)
— and carry the contextualizing prose alongside (a visual without its explaining prose fails R0). When clusters or gaps are worth marking, reach for the Feynman `gap-marker` / `gap-table`
palette elements — as elements, never mandatory sections.

## Author in Markdown — the diagram lives as a Markdown-native carrier

The rite's form is pinned **Markdown** (the neutral `render.RENDERER_ID` renderer, H1 first). Map's
diagram idiom rides Markdown-native carriers: a **fenced diagram block** (a ```` ```mermaid ```` graph
or a fenced ASCII node-and-edge drawing) for the spine, backed by a connection **table**
(From · Type · To · Evidence), and each load-bearing bridge **contextualized in prose** alongside —
the diagram alone is a schema dump; the insight it carries is the deliverable. **Sections are FREE** —
the rite checks the *property* (honesty, clarity, the outward bridge drawn), never a named section.

## The rite is the path — exit through `tools/rito.py` (docs/rito-runtime.md)

**The map producer traverses the experiment's rite as executable code**, the same runtime `report`
exits through ("o edge deve soar o mesmo across artefatos"). You do not build a structured spec, you
do not call `close.run_close`, and you **never** call `publisher.publish` — the rite runtime sequences
the whole causal execution (grounding-1 through publication of the rendered page) and seals a receipt
for every stage. Your job is the COGNITION: the per-stage prompts carrying map's connections-and-insight
cognition. The runtime owns sequencing, sealing, rendering (the pinned neutral-markdown renderer,
`render.RENDERER_ID`) and publication. A run that didn't publish didn't finish the rite.

The stages you feed (authoring format is **Markdown**; the fenced diagram + connection table carry the
visual idiom): `grounding1_dossier` (the connections you gathered — the gather-grounding slot above,
each edge `{from, to, type, ref}` grounded) → `first_authorial_draft` → `gap_critique` →
`grounding2_targeted` → `provisional_rewrite` → `fact_audit` → `author_correction` →
`treatment_cleanup` (deterministic copy when the leak scan is clean) → `final_html` (pinned render,
runtime-owned) → `final_review` (fail-closed `ACCEPTANCE:` header) → `publication`. The canonical
prompt bodies are archived in `drafts/old-edge-double-grounding-repro/run.py`; adapt their content to
THIS map — the produce guidance above (the outward bridge, contextualized to live work) is what the
first-draft prompt must carry.

The wake's `DISPATCH_ID=<id>` line rides into the run (the canonical publish refuses without it, E1c).
The product spine still ships: pass `publish_meta` with `proposes` (candidate steers — a gap or cluster
that is a steer; omit for a connections-only map), `distills` (existing cluster threads only — empty
over fabricated), `cites` (source asserting an edge + the snippet you used), `lineage` (`builds_on`
the prior the surf offers), `bears_on` (SÓ sobre hipótese VIVA — `cortex.hypotheses_at()` lists them;
empty over fabricated), `para` (explicit target reader; empty resolves to the mentee) and `reports_on`.

    tools/edge-python <<'EOF'
    import sys; sys.path.insert(0, 'tools')
    import rito, llm_routes

    slug = '<slug>'
    dispatch_id = '<dispatch-id-from-DISPATCH_ID-line>'

    def complete_fn(route, prompt, max_tokens):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    prompts = {
        'first_authorial_draft': lambda o: f"<map this theme's connections outward, contextualize each bridge to live work; fenced diagram + connection table>\n\nDOSSIER:\n{o['grounding1_dossier']}",
        'gap_critique':          lambda o: f"<which bridges lack an outward connection or a cite; which are inert adjacencies>\n\n{o['first_authorial_draft']}",
        'grounding2_targeted':   lambda o: f"<targeted grounding closing the named connection gaps>\n\n{o['gap_critique']}",
        'provisional_rewrite':   lambda o: f"<same-author rewrite folding critique+grounding2>\n\n{o['grounding2_targeted']}",
        'fact_audit':            lambda o: f"<independent audit: every edge grounded in its cite vs grounding1>\n\n{o['provisional_rewrite']}",
        'author_correction':     lambda o: f"<bounded same-author correction from the audit>\n\n{o['fact_audit']}",
        'treatment_cleanup':     lambda o: f"<bounded same-author leak cleanup>\n\nSCAN:\n{o['treatment_leaks']}\n\n{o['author_correction']}",
        'final_review':          lambda o: f"<strict review; begin with the 4-line ACCEPTANCE header (ACCEPTANCE, UNSUPPORTED_CLAIMS, TREATMENT_LEAK, CLARITY_STRIKES)>\n\n{o['treatment_cleanup']}",
    }

    rito.run_rito(slug, run_dir=f'state/rito/{slug}',
                  grounding1_fn=lambda: '<the connections dossier you gathered>',
                  prompts=prompts, complete_fn=complete_fn,
                  intent='open: …; bet: …', skill='map', dispatch_id=dispatch_id,
                  publish_meta={'proposes': [], 'distills': [], 'cites': [],
                                'lineage': [], 'bears_on': [], 'para': [], 'reports_on': []})
    EOF

The publisher's rito seam recomputes the pinned render from the sealed markdown and **refuses a hash
mismatch** — the exact reviewed bytes, and only they, land at `blog/entries/<slug>.html`, bound to the
`artefato.published` event + mandatory `intent.kernel` in one atomic act (C3), and the post-publish
side-effects (source-signal + graph projection) run the same as every artefato. The
first authorial draft stays sealed and addressable in the run dir for later blind reading. Prove it ran:

    tools/edge-python tools/rito.py verify state/rito/<slug>

The Artefato is **transient** — it cools and is prunable; it also **bears the comment field**, the surface
the mentee's later comment consolidates from. The durable knowledge it distills lives in the **cluster**,
written by the **grill** (consolidate is dissolved — ADR-0008) — never here. You do not write wiki pages.

## Read-only on the world (CONTRACT C1)

You write only the edge's own Artefato (the blog entry). The mentee's world stays untouched. Acting in the
world is never a map decision.
