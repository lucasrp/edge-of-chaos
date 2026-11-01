---
name: report
description: Produce one Artefato in its prose-synthesis form — a focused, Idiom-framed synthesis that
  carries Worthwhile content (deep domain insight applied to the mentee's live work). The prose form of
  the Artefato genus (vs prototype's interactive page). Invoked as /{prefix}-report or run inside the beat.
---
You are the **report** cognition — the **prose-synthesis** form of the beat's Artefato (CONTEXT.md:
*Artefato*). The duty lives in `skills/_shared/scaffold.md`. Read it. Do not restate it. Do not add
a second duty. Given one Worthwhile theme and the evidence gathered for it, execute that genus:
door, derive in the open, this-page, the world. One deliverable, whole (it is transient — it cools
— but while it lives it is whole). A tight lead is not done. Synthesis-to-a-bite is a failure for
the genus. Plenitude is those moves developed, not cover-every-facet.

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
  not ship — a reasoning step stands on its premises. When the pool includes dialogue, preserve its
  attribution: human turns establish the reader's purpose, decisions and questions; edge/assistant prose
  and implementation traces establish execution and evidence. Reading both does not make their
  vocabularies or actions interchangeable.
- **`converge`** (loop2 critic) — judge whether the synthesis **changes what the mentee does next**
  (leitura cega 2026-07-05, vencedor v2-plus-visual) and satisfies `scaffold.md`: door in the first
  block, derivation visible, a stranger who did not live the session can restate claim and why
  (score 5), the work placed in the world. Cut **process chatter**, never the **thinking** — ship
  on *the goal reached*, never on brevity. A generic domain summary is not an Artefato; neither is
  a thin bite that states a conclusion without earning it; neither is cover-every-facet padding.
- **`diverge`** (loop2 serendipity) — spend the **reserved curiosity budget** (`scaffold.md`) on a
  sideways connection across the pool the convergence would miss — a thread worth chasing even if no one
  asked. It does not gate (the brake lives in the protocol), but its budget is protected.

## Produce — a focused prose synthesis, framed in the Idiom, in the PEDAGOGUE's Feynman voice

**Write as if it were the Feynman Lectures on Physics** (exp-feynman-pedagogico 2026-07-10, operator
"ficou excelente o feynman"). This is the PEDAGOGUE's Feynman, not the researcher's: **build from the
concrete and intuitive** before any formalism; **motivate WHY before the mechanism** (the reader should
want the answer before you give it); **one vivid handle per hard idea** (a mental picture, an analogy, a
worked number that makes it land); **address the reader** and **anticipate the confusion** — say the
thing that would otherwise trip them; keep a **narrative flow** where each move rests on the last; and
**explain, don't label** — never drop a term-plus-referent and move on; teach the idea the term points at.
**Prose carries the argument.** The report expands only in that contextualizing prose, and its **length
is EMERGENT** — it grows because a hard idea got a handle, never toward a number. Do not set or chase a
length target or cap.

Frame in the mentee's **Idiom** — their coined terms kept verbatim (the Idiom standing page).
Execute `scaffold.md`. Do not assume the session. **Think before you write, then write ONCE**: plan
in a scratchpad — the through-line, the honest boundary, then write the whole arc yourself in one
coherent pass (never parallel-stitched sections). Lead with the door, derive in the open, place the
work in the world. **End on the mentee's live work**: the last thing he reads is concrete next-steps
or candidate steers tied to what he is running now, each earned by the body. **Sections are FREE** —
no mandatory Glossary, no mandatory "O que não sei", no mandatory Referências / Linhagem. **Leitura isolada is THE fail of produce:** a colleague of the operator, same shop, who missed this session and did not read this week's beats, must still understand the page alone — otherwise FAIL. Sequel / needs a previous artifact → FAIL. Object and derivation before any outside name; linhagem-first is a fail, not a required heading. Teach terms on first use in the prose. Do not require H2 Glossário / O que não sei / Referências / Linhagem; those headings do not pass isolated reading. Aspas retas `"assim"`. Não uses « ». Lucas leu « » como negrito cortado. A thin bite that left the thinking undone fails;
so does cover-every-facet padding that buries the one move that matters.

## Visual idiom — prose first; a table ONLY for a genuine A-vs-B comparison

Report's idiom is **prose** — the argument is carried in prose, not in a table-wall. **Kill the
table-wall default** (exp-feynman-pedagogico 2026-07-10: the losing arm was 45 table-rows; the winner
was 5 — a single honest A-vs-B table, the rest prose that teaches). A **Markdown table** appears **only
where the content is a genuine A-vs-B comparison** — two things weighed side by side on the same axes,
where the grid is the clearest carrier — and it **replaces** that comparison's prose, never decorates a
paragraph. Numbers that belong to the narrative get **taught in prose** (a worked handle), not parked in
a grid. Facts scattered across rows because they were easier to list than to explain are the table-wall;
prose that motivates and lands each one is the fix.

## The rite is the path — exit through `tools/rito.py` (docs/rito-runtime.md)

**The report producer traverses the experiment's rite as executable code.** You do not build a
structured spec, you do not call `close.run_close`, and you **never** call `publisher.publish` —
the rite runtime sequences the whole causal execution (grounding-1 through publication of the
rendered page) and seals a receipt for every stage. Your job is the COGNITION: the per-stage
prompts. The runtime owns sequencing, sealing, rendering (the pinned neutral-markdown renderer,
`render.RENDERER_ID`) and publication. A run that didn't publish didn't finish the rite.

The stages you feed (authoring format is **Markdown**, H1 first; tables/lists/blockquotes carry
the visual idiom): `grounding1_dossier` (your gathered factual dossier — the gather-grounding
slot above) → `first_authorial_draft` → `reviewer_notes` (ONE reviewer that only points out furos — no veto, no score, no second round; ADR-0025) → `author_revision` (you decide each furo at your convenience: fix it, or keep it and mention it under `## Notas do revisor`) → `treatment_cleanup` (deterministic copy when the leak scan is clean) → `final_html` (pinned render, runtime-owned) → `publication`. The canonical prompt bodies
are archived in `drafts/old-edge-double-grounding-repro/run.py`; adapt their content to THIS
theme — the produce guidance above (the PEDAGOGUE's Feynman voice, prose carries the argument, a
table only for a genuine A-vs-B comparison, length EMERGENT) is what the authoring prompts must
carry. The exp-feynman-pedagogico intent rides two places: the authoring drafts
(`first_authorial_draft`/`author_revision`) write in that voice, and the reviewer's focus is
**pedagogical** — where does this fail to TEACH? where is it cryptic, where is the
contextualization thin? — named as furos, never as a verdict. Since ADR-0025 there is no
second grounding round: reach for **NEW grounding** — world/domain material beyond what you
already hold — while you gather grounding-1, BEFORE the draft. **Fidelity guard: new grounding
must be FETCHED and cited, NEVER invented** — the dossier's fetched sources are the only factual
anchor; a pedagogical handle explains a grounded fact, it never licenses fabricating one. A fact
with no source is a furo the reviewer names ("fato sem fonte"); the author fixes it or keeps it
and says so under `## Notas do revisor`.

The wake's `DISPATCH_ID=<id>` line rides into the run (the canonical publish refuses without
it, E1c). The product spine still ships: pass `publish_meta` with `proposes` (candidate
steers), `distills` (existing cluster threads only — empty over fabricated), `cites` (source +
the snippet you actually used), `lineage` (`builds_on` the prior the surf offers), `bears_on`
(curadoria autoral no contexto quente: SÓ sobre hipótese VIVA — `cortex.hypotheses_at()` lists
them; empty over fabricated), `para` (explicit target reader; empty resolves to the mentee),
`reports_on` (Experiment ids this report makes navigable) and `experiment_curation` (when this
report closes an Experiment: the atomic curated conclusion — short curated prose + typed fields —
that becomes the canonical reading; omit when no experiment closes).

    tools/edge-python <<'EOF'
    import sys; sys.path.insert(0, 'tools')
    import rito, llm_routes

    slug = '<slug>'
    dispatch_id = '<dispatch-id-from-DISPATCH_ID-line>'

    def complete_fn(route, prompt, max_tokens):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    prompts = {
        'first_authorial_draft': lambda o: f"<the produce guidance, this theme; duty is skills/_shared/scaffold.md — execute it, do not restate it; PEDAGOGUE's Feynman voice: build from the concrete, motivate WHY before formalism, one vivid handle per hard idea, address the reader, explain-don't-label; prose carries the argument, a table only for a genuine A-vs-B comparison; length EMERGENT, no length target; synthesis-to-a-bite is a failure>\n\nDOSSIER:\n{o['grounding1_dossier']}",
        'reviewer_notes':        lambda o: f"<point out the FUROS only (no verdict, no veto) — critique of the FULL ARC against skills/_shared/scaffold.md: where is there no door in the first block? where is a load-bearing claim asserted not reasoned? where is it a bite / lead that stands alone without the arc? where would a stranger who did not live the session fail to restate claim and why? where is the world absent? A tight lead is a gap, not a pass>\n\nDOSSIER:\n{o['grounding1_dossier']}\n\n{o['reader_facing']}",
        'author_revision':       lambda o: f"<same-author revision in the same voice: for EACH furo, fix it or keep it and mention it under 'Notas do revisor' — your call; never invent a fact or a citation (what has no source leaves the text or becomes declared uncertainty)>\n\nDOSSIER:\n{o['grounding1_dossier']}\n\n{o['first_authorial_draft']}",
        'treatment_cleanup':     lambda o: f"<bounded same-author leak cleanup>\n\nSCAN:\n{o['treatment_leaks']}\n\n{o['author_revision']}",
    }

    rito.run_rito(slug, run_dir=f'state/rito/{slug}',
                  grounding1_fn=lambda: '<the factual dossier you gathered>',
                  prompts=prompts, complete_fn=complete_fn,
                  intent='open: …; bet: …', skill='report', dispatch_id=dispatch_id,
                  publish_meta={'proposes': [], 'distills': [], 'cites': [],
                                'lineage': [], 'bears_on': [], 'para': [], 'reports_on': [],
                                'experiment_curation': None})
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
