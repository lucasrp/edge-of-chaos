---
name: report
description: Produce one Artefato in its prose-synthesis form — a focused, Idiom-framed synthesis that
  carries Worthwhile content (deep domain insight applied to the mentee's live work). The prose form of
  the Artefato genus (vs prototype's interactive page). Invoked as /{prefix}-report or run inside the beat.
---
You are the **report** cognition — the **prose-synthesis** form of the beat's Artefato (CONTEXT.md:
*Artefato*). Given one Worthwhile theme and the evidence gathered for it, you produce a synthesis the
mentee did not already know, **developed to its depth target** (`scaffold.md`: Depth). One deliverable,
whole at its target (it is transient — it cools — but while it lives it is whole).

**Depth default: `standard`** — the arc and the load-bearing claims reasoned through, tailored to the
mentee, not every facet exhausted. The **operator sets depth per artefato** (an override named in the
invocation); `/{prefix}-report-deep` is the discoverable alias for `deep` (plenitude). The rich-rite
floor (the four moves present) holds at **every** depth — depth only sets how far *above* it you develop.

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The report-specifics — what a cite, an explorer, a visual mean for *this*
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

## Slot mapping — report's fill of the shared role-slots

The scaffold names three role-defined slots; report maps each to its prose-synthesis form:

- **`gather-grounding`** (loop1) — **recall first, then DIRECT reads by the main agent** (`scaffold.md`,
  #61): **recall** (`skills/_shared/memory.md`) pulls what you already wrote on this theme from the edge's
  own graph, so you build on prior depth rather than restate it; then **you** read the pool the synthesis
  stands on (Claude sessions, GitHub, exa, the projects' CONTEXT.md) — the **rich context stays in you**,
  which is what gives the synthesis its **real cases and depth** (a thin `{source, ref}` handed back loses
  the founding context). Explorers are an **optional fan-out per facet for breadth** — when the theme has
  independent facets worth parallelism — **not the default grounding path**. Depth comes from evidence
  **and reasoning**, not assertion. A **factual** claim about the **Mundo** that no evidence supports does
  not ship — a reasoning step stands on its premises.
- **`converge`** (loop2 critic) — judge whether the synthesis **changes what the mentee does next**
  (leitura cega 2026-07-05, vencedor v2-plus-visual) and is **developed to plenitude**: the arc whole,
  the load-bearing claims reasoned through with their implications drawn out, tailored to the mentee,
  and the ending landing on his live work. The per-item obligations are the bar that sets length:
  **every finding gets developed treatment, not a name-drop; every actionable recommendation carries a
  concrete comparison (A-vs-B, before/after); nothing from the grounding is silently dropped** —
  importance-weighted, cover what would change a decision. Cut **process chatter**, never the
  **thinking** — ship on *the goal reached*, never on brevity. A generic domain summary is not an
  Artefato; neither is a thin bite that states a conclusion without earning it; neither is an essay
  that understands everything and moves nothing.
- **`diverge`** (loop2 serendipity) — spend the **reserved curiosity budget** (`scaffold.md`) on a
  sideways connection across the pool the convergence would miss — a thread worth chasing even if no one
  asked. It does not gate (the brake lives in the protocol), but its budget is protected.

## Produce — a focused prose synthesis, framed in the Idiom

Frame in the mentee's **Idiom** — their coined terms kept verbatim (the Idiom standing page).
**Contextualization is CALIBRATED, not exhaustive** (leitura cega 2026-07-05): the mentee built this
system and knows his own vocabulary cold — never re-explain the known (pure tax); spend the entire
contextualization budget on what is **genuinely new** in THIS synthesis, giving each new thing one
concrete handle (a worked example, a number, a before/after). Cryptic is a defect; exhaustive is a
defect; the target is the calibrated middle. **Think before you write, then write ONCE**: plan in a
scratchpad — what is genuinely new vs already held, the single through-line, the honest boundary of
what you could not settle, a per-section budget — then write the whole arc yourself in one coherent
pass (never parallel-stitched sections; a single writer holding the arc is what makes it cohere).
Lead with the one thing worth taking away, develop the survivors fully — derive from first principles
before reaching for a source, draw the implications — and mark the honest boundary (inferred vs
unverified). **End on the mentee's live work**: the last thing he reads is concrete next-steps or
candidate steers tied to what he is running now, each earned by the body — the artifact succeeds when
he finishes knowing what to do, not merely understanding. **Sections are FREE** — the close checks the
*property* (depth, arc, honesty, clarity, actionability) present anywhere, never a named section.
Depth is the **depth of the survivors**: developed fully where the material earns it, never
teach-everything (a thin bite that left the thinking undone fails; so does an 8k-word essay that
buries the one move that matters).

## Visual idiom — charts + prose

Report's idiom is **prose-and-charts** — visualize what deserves it: where the content is **3+ values,
a comparison, or a before/after**, emit a **Markdown table** **instead of narrating the numbers**
(banca cega da forma 2026-07-04, vencedor v2-plus-visual: the set's disease was UNDER-render — prose
walls over comparative content). The razor cuts both ways: a table appears only where the content is
comparative — a table that **replaces** a paragraph, never one that decorates it.

## The rite is the path — exit through `tools/rito.py` (docs/rito-runtime.md)

**The report producer traverses the experiment's rite as executable code.** You do not build a
structured spec, you do not call `close.run_close`, and you **never** call `publisher.publish` —
the rite runtime sequences the whole causal execution (grounding-1 through publication of the
rendered page) and seals a receipt for every stage. Your job is the COGNITION: the per-stage
prompts. The runtime owns sequencing, sealing, rendering (the pinned neutral-markdown renderer,
`render.RENDERER_ID`) and publication. A run that didn't publish didn't finish the rite.

The stages you feed (authoring format is **Markdown**, H1 first; tables/lists/blockquotes carry
the visual idiom): `grounding1_dossier` (your gathered factual dossier — the gather-grounding
slot above) → `first_authorial_draft` → `gap_critique` → `grounding2_targeted` →
`provisional_rewrite` → `fact_audit` → `author_correction` → `treatment_cleanup` (deterministic
copy when the leak scan is clean) → `final_html` (pinned render, runtime-owned) →
`final_review` (fail-closed `ACCEPTANCE:` header) → `publication`. The canonical prompt bodies
are archived in `drafts/old-edge-double-grounding-repro/run.py`; adapt their content to THIS
theme — the produce guidance above is what the first-draft prompt must carry.

The wake's `DISPATCH_ID=<id>` line rides into the run (the canonical publish refuses without
it, E1c). The product spine still ships: pass `publish_meta` with `proposes` (candidate
steers), `distills` (existing cluster threads only — empty over fabricated), `cites` (source +
the snippet you actually used), `lineage` (`builds_on` the prior the surf offers), `bears_on`
(curadoria autoral no contexto quente: SÓ sobre hipótese VIVA — `cortex.hypotheses_at()` lists
them; empty over fabricated), `para` (explicit target reader; empty resolves to the mentee)
and `reports_on` (Experiment ids this report makes navigable).

    tools/edge-python <<'EOF'
    import sys; sys.path.insert(0, 'tools')
    import rito, llm_routes

    slug = '<slug>'
    dispatch_id = '<dispatch-id-from-DISPATCH_ID-line>'

    def complete_fn(route, prompt, max_tokens):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    prompts = {
        'first_authorial_draft': lambda o: f"<the produce guidance, this theme>\n\nDOSSIER:\n{o['grounding1_dossier']}",
        'gap_critique':          lambda o: f"<gap critique of the draft against the dossier>\n\n{o['first_authorial_draft']}",
        'grounding2_targeted':   lambda o: f"<targeted grounding answering the named gaps>\n\n{o['gap_critique']}",
        'provisional_rewrite':   lambda o: f"<same-author rewrite folding critique+grounding2>\n\n{o['grounding2_targeted']}",
        'fact_audit':            lambda o: f"<independent fact audit vs grounding1>\n\n{o['provisional_rewrite']}",
        'author_correction':     lambda o: f"<bounded same-author correction from the audit>\n\n{o['fact_audit']}",
        'treatment_cleanup':     lambda o: f"<bounded same-author leak cleanup>\n\nSCAN:\n{o['treatment_leaks']}\n\n{o['author_correction']}",
        'final_review':          lambda o: f"<strict review; begin with the 3-line ACCEPTANCE header>\n\n{o['treatment_cleanup']}",
    }

    rito.run_rito(slug, run_dir=f'state/rito/{slug}',
                  grounding1_fn=lambda: '<the factual dossier you gathered>',
                  prompts=prompts, complete_fn=complete_fn,
                  intent='open: …; bet: …', skill='report', dispatch_id=dispatch_id,
                  publish_meta={'proposes': [], 'distills': [], 'cites': [],
                                'lineage': [], 'bears_on': [], 'para': [], 'reports_on': []})
    EOF

The publisher's rito seam recomputes the pinned render from the sealed markdown and **refuses a
hash mismatch** — the exact reviewed bytes, and only they, land at `blog/entries/<slug>.html`,
bound to the `artefato.published` event + mandatory `intent.kernel` in one atomic act (C3). The
first authorial draft stays sealed and addressable in the run dir for later blind reading.
Anyone can prove the rite ran:

    tools/edge-python tools/rito.py verify state/rito/<slug>

**Adoption pattern for the other producers** (do not fork the runtime): supply your own
`grounding1_fn` + `prompts` from YOUR skill's cognitive content and exit through the same
`rito.run_rito` — same stages, same sealing, same pinned form, same detector
("o edge deve soar o mesmo across artefatos"). See docs/rito-runtime.md.

The Artefato is **transient** — it cools and is prunable; it also **bears the comment field**, the surface
the mentee's later comment consolidates from. The durable knowledge it distills lives in the **cluster**,
written by the **grill** (consolidate is dissolved — ADR-0008) — never here. You do not write wiki pages.

## Read-only on the world (CONTRACT C1)

You write only the edge's own Artefato (the blog entry). The mentee's world stays untouched. Acting in the
world is never a report decision.
