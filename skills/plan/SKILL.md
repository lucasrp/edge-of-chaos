---
name: plan
description: Produce one Artefato in its next-steps form — a focused, concrete proposal of what to do next
  for a live project or theme: the steps, their order, their dependencies. The next-steps-grid/flow form of
  the Artefato genus (vs report's prose, map's diagram). Invoked as /{prefix}-plan or run inside the beat.
---
You are the **plan** cognition — the **next-steps** form of the beat's Artefato (CONTEXT.md: *Artefato*).
Given one Worthwhile theme, you produce a single focused proposal of what to do next: the concrete steps,
their order, their dependencies — applied to the mentee's live work. A plan sells itself: a cold reader
sees what to do, why now, and what each step delivers. You produce one transient deliverable, well.

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The plan-specifics — what an explorer, a cite, a visual mean for *this*
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

## Slot mapping — plan's fill of the shared role-slots

The scaffold names three role-defined slots; plan maps each to its next-steps form:

- **`gather-grounding`** (loop1) — **recall first, then DIRECT reads by the main agent** (`scaffold.md`,
  #61): **recall** what the edge already knows on this theme, then **you** read what already exists and what
  is open — the projects' CONTEXT.md, the live Direction, prior Artefatos on the theme, GitHub state, exa
  for how others did it — the **rich context stays in you** to shape feasible steps. Explorers are an
  **optional fan-out for breadth** — when independent facets warrant parallelism — **not the default
  grounding path**. The evidence the plan stands on is `{source, ref}` — the current state a step changes,
  the prior art a step reuses. A step grounded in nothing does not ship.
- **`converge`** (loop2 critic) — tighten the scope: a small feasible cycle beats an ambitious impossible
  one. Cut steps that aren't load-bearing, name what is explicitly out of scope, and ship the moment the
  next move is concrete and ordered. A vague aspiration is not an Artefato.
- **`diverge`** (loop2 serendipity) — look sideways for the cheaper path, the dependency that reorders the
  steps, the reusable prior the convergence would miss. Advisory only (the brake lives in the protocol,
  not here).

## Visual idiom — next-steps-grid / flow

Plan's idiom is the **step-sequence flow as a renderable `diagram`** (the ordered steps and what blocks
what, dependency-edged) — the primary visual when `vl-convert` is present; `ascii-diagram` only as the
logged degradation when the backend is absent. The **next-steps-grid** (steps as ordered cards: what goes
in, what happens, what comes out) and **`flow-example`** (input → output per step) are SUPPORTING
structured blocks alongside the diagram, not substitutes for the renderable flow. The visualization dim is
content-relative: a plan with ordered
steps clearly warrants the grid/flow rather than a paragraph of prose. Reach for `risk-table` for the
risks/mitigations and `metrics-grid` for the cost or estimate — palette elements, never mandatory
sections.

## Author in Markdown — the flow lives as a Markdown-native carrier

The rite's form is pinned **Markdown** (the neutral `render.RENDERER_ID` renderer, H1 first). Plan's
step-sequence flow rides Markdown-native carriers: a **fenced diagram block** (a ```` ```mermaid ````
flow or a fenced ASCII step-and-dependency drawing) for the ordered steps and what blocks what, backed
by an ordered **list** or **table** for the next-steps grid (what goes in → what happens → what comes
out) and a **risk table** for risks/mitigations. The visual is content-relative: a plan with ordered
steps warrants the flow rather than a prose paragraph. **Sections are FREE** — the rite checks the
*property* (honesty, clarity, the ordered actionable flow), never a named section.

## The rite is the path — exit through `tools/rito.py` (docs/rito-runtime.md)

**The plan producer traverses the experiment's rite as executable code**, the same runtime `report`
exits through ("o edge deve soar o mesmo across artefatos"). You do not build a structured spec, you
do not call `close.run_close`, and you **never** call `publisher.publish` — the rite runtime sequences
the whole causal execution (grounding-1 through publication of the rendered page) and seals a receipt
for every stage. Your job is the COGNITION: the per-stage prompts carrying plan's next-steps cognition.
The runtime owns sequencing, sealing, rendering (the pinned neutral-markdown renderer, `render.RENDERER_ID`)
and publication. A run that didn't publish didn't finish the rite.

The stages you feed (authoring format is **Markdown**; the fenced flow + ordered list/table carry the
visual idiom): `grounding1_dossier` (the situation and constraints the plan stands on — the gather-grounding
slot above) → `first_authorial_draft` → `gap_critique` → `grounding2_targeted` → `provisional_rewrite`
→ `fact_audit` → `author_correction` → `treatment_cleanup` (deterministic copy when the leak scan is
clean) → `final_html` (pinned render, runtime-owned) → `final_review` (fail-closed `ACCEPTANCE:` header)
→ `publication`. The canonical prompt bodies are archived in
`drafts/old-edge-double-grounding-repro/run.py`; adapt their content to THIS plan — the produce guidance
above (ordered steps, dependencies, risks, cost, ending on the live next move) is what the first-draft
prompt must carry.

The wake's `DISPATCH_ID=<id>` line rides into the run (the canonical publish refuses without it, E1c).
The product spine still ships: pass `publish_meta` with `proposes` (the candidate steers — a plan's
proposed next moves ARE steers), `distills` (existing cluster threads only — empty over fabricated),
`cites` (source the plan stands on + the snippet you used), `lineage` (`builds_on` the prior the surf
offers), `bears_on` (SÓ sobre hipótese VIVA — `cortex.hypotheses_at()` lists them; empty over
fabricated), `para` (explicit target reader; empty resolves to the mentee) and `reports_on`.

    tools/edge-python <<'EOF'
    import sys; sys.path.insert(0, 'tools')
    import rito, llm_routes

    slug = '<slug>'
    dispatch_id = '<dispatch-id-from-DISPATCH_ID-line>'

    def complete_fn(route, prompt, max_tokens):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    prompts = {
        'first_authorial_draft': lambda o: f"<lay out this theme's ordered steps at PLENITUDE (cover the facets, no facet folded): dependencies, risks, cost reasoned through; end on the live next move; fenced flow + ordered list/table; a tight lead of next-steps without the reasoning is a failure>\n\nDOSSIER:\n{o['grounding1_dossier']}",
        'gap_critique':          lambda o: f"<which steps are underspecified, which dependencies are hand-waved, which risks are unstated>\n\n{o['first_authorial_draft']}",
        'grounding2_targeted':   lambda o: f"<targeted grounding closing the named plan gaps>\n\n{o['gap_critique']}",
        'provisional_rewrite':   lambda o: f"<same-author rewrite folding critique+grounding2>\n\n{o['grounding2_targeted']}",
        'fact_audit':            lambda o: f"<independent audit of the plan's factual claims vs grounding1>\n\n{o['provisional_rewrite']}",
        'author_correction':     lambda o: f"<bounded same-author correction from the audit>\n\n{o['fact_audit']}",
        'treatment_cleanup':     lambda o: f"<bounded same-author leak cleanup>\n\nSCAN:\n{o['treatment_leaks']}\n\n{o['author_correction']}",
        'final_review':          lambda o: f"<strict review of the full arc; begin with the 3-line ACCEPTANCE header. PASS only if the facets are covered — plenitude, no facet folded. Synthesis-to-a-bite / 'the lead suffices' is FAIL for the genus, never ACCEPTANCE>\n\n{o['treatment_cleanup']}",
    }

    rito.run_rito(slug, run_dir=f'state/rito/{slug}',
                  grounding1_fn=lambda: '<the situation/constraints dossier you gathered>',
                  prompts=prompts, complete_fn=complete_fn,
                  intent='open: …; bet: …', skill='plan', dispatch_id=dispatch_id,
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
world is never a plan decision.
