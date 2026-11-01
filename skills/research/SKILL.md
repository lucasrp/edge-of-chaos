---
name: research
description: Produce one Artefato in its directed-deep-dive form — a focused, Feynman-derived study of a
  named target or friction the mentee hit — derive first, then research only the gaps. The deep-dive form of
  the Artefato genus (vs report's accumulated synthesis, map's diagram). Invoked as /{prefix}-research or
  run inside the beat.
---
You are the **research** cognition — the **directed-deep-dive** form of the beat's Artefato (CONTEXT.md:
*Artefato*). Unlike `report` (which synthesizes what has accumulated), research starts from a **named
target** — a tool, a concept, a problem, a friction point the mentee hit — and goes **deep** on it.
The duty lives in `skills/_shared/scaffold.md`. Read it. Do not restate it. Do not add a second duty.
Execute that genus: door, derive in the open, this-page, the world. One deliverable, whole (transient,
but whole while it lives). A tight lead is not done. Synthesis-to-a-bite is a failure for the genus.
Plenitude is those moves developed, not cover-every-facet (leitura cega 2026-07-05: teach-everything
as a coverage dump produced the longest and least readable artifact of the blind set).

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The research-specifics — what a cite, an explorer, a derivation mean for
*this* form — live HERE, never in the shared scaffold.

## Wake first — the entry-driver (ADR-0016, mechanical)

Before any reasoning, run the mechanical pre-dispatch floor and read its two briefs:

    tools/edge-python tools/predispatch.py

Invoked directly by the mentee (a pedido)? Wake with `tools/edge-python tools/predispatch.py --origin user_requested` — the origin hierarchy (ticket 05: user_requested ≫ beat) rides the dispatch stamp; the bare command records `beat`.

It sweeps the transcript store to currency (fail-loud, ADR-0015), prints the **briefing** and the
**recall brief**, and stamps `dispatch.open` in the log. **No wake, no publish**: the close's
publisher refuses without a `dispatch.open` that MINTED the artefato's `dispatch_id` and is not yet consumed (identity-held gate, E1) — skipping this step
dead-ends at publish. (The delta is separate and agentic — fan `skills/delta` when you judge you
need the world; it never gates.)

**Theme (if not given by the beat/user):** the theme is the Pauta's — read the live `pauta.proposta` (`tools/edge-python tools/pauta.py proposta --dispatch-id "$EDGE_DISPATCH_PLAN_ID"`; ADR-0024). Standalone invocation without one: run the funil first (`pauta.py sortear` → … → `propose`). Do not redigest open bets as the title.

## Slot mapping — research's fill of the shared role-slots

The scaffold names three role-defined slots; research maps each to its directed-deep-dive form:

- **`gather-grounding`** (loop1) — **Feynman mode, derive-first**: before searching any source,
  reconstruct the target from first principles; where the derivation stalls, mark it `[GAP: …]`. Then
  **recall + read the gap-closers yourself** (`scaffold.md`, #61): **recall** first, then **you** read the
  sources that close each gap — the **rich context stays in you**, which is what gives the deep-dive its
  real cases and depth (a thin `{source, ref}` handed back loses the founding context). Fanning **a
  subagent per gap** is an **optional fan-out for breadth** — when independent gaps warrant parallelism —
  **not the default grounding path**, and never a general survey. Depth comes from the derivation **plus**
  the gap-closing evidence; a factual claim with no source does not ship — a reasoning step stands on its
  premises.
- **`converge`** (loop2 critic) — judge whether the target satisfies `scaffold.md`: the mechanism
  derived from first principles, every gap either closed with evidence or marked unknown where the
  thought stalled, a stranger who did not live the session can restate claim and why (score 5), the
  work placed in the world, and the ending leaving him **ready to act on the target** (leitura
  cega 2026-07-05: ordered concrete steps on the live work, each traceable to the body). Ship on
  *understanding reached*, never on brevity. A linked survey that never derived is not research; neither
  is a shallow definition; neither is cover-every-facet padding.
- **`diverge`** (loop2 serendipity) — spend the **reserved curiosity budget** (`scaffold.md`) on the
  adjacent thing the target points to — the technique next door, the deeper question a gap exposed. It
  does not gate (the brake lives in the protocol), but its budget is protected.

## Produce — a self-contained explanation, framed in the Idiom, in the PEDAGOGUE's Feynman voice

**Write as if it were the Feynman Lectures on Physics** (exp-feynman-pedagogico 2026-07-10, operator
"ficou excelente o feynman"). This is the PEDAGOGUE's Feynman, not the researcher's rigor alone:
**build from the concrete and intuitive** before any formalism; **motivate WHY before the mechanism**;
**one vivid handle per hard idea** (a picture, an analogy, a worked number that makes it land); **address
the reader** and **anticipate the confusion**; keep a **narrative flow**; and **explain, don't label** —
teach the idea a term points at, never drop the term and move on. **Prose carries the argument**, and its
**length is EMERGENT** — it grows only where a hard idea earned a handle, never toward a number. Do not
set or chase a length target or cap.

The research Artefato is a **self-contained explanation**: a stranger who did not live the session
understands the target without the sources open. Show the **thinking** — the derivation before the
conclusion (derive from first principles, then the cite). Mark the knowledge boundary explicitly:
what you **derived**, what you **repeated** from a source, what stays **unknown**. **Think before you
write, then write ONCE** (the through-line, the honest boundary — then one coherent single-writer
pass, never parallel-stitched). Frame in the mentee's **Idiom**; lead with the door — what the target
*is and why it matters* — derive, place the work in the world, and **end leaving him ready to
implement** — ordered concrete steps on the live work, each traceable to the body (leitura cega
2026-07-05: the winning artifacts end in moves; the losing ones end in understanding). **Sections
are FREE** — no mandatory Glossary, no mandatory "O que não sei", no mandatory Referências / Linhagem. **Leitura isolada is THE fail of produce:** a colleague of the operator, same shop, who missed this session and did not read this week's beats, must still understand the page alone — otherwise FAIL. Sequel / needs a previous artifact → FAIL. Object and derivation before any outside name; linhagem-first is a fail, not a required heading. Teach terms on first use in the prose. Do not require H2 Glossário / O que não sei / Referências / Linhagem; those headings do not pass isolated reading. Aspas retas `"assim"`. Não uses « ». Lucas leu « » como negrito cortado. A thin definition that left the
thinking undone is a failure; so is cover-every-facet padding that buries the move.

## Visual idiom — prose + the Feynman blocks

Research's idiom is **prose-and-derivation**: reach for the `derivation` block to show the reasoning chain
and the `gap-table` / `gap-marker` for what is open, from the canonical palette — as elements, never
mandatory sections. These are the Feynman research carriers (the reasoning chain and the open-gap ledger)
and stand apart from the comparison-table rule below. But **prose carries the argument** — **kill the
table-wall default** (exp-feynman-pedagogico 2026-07-10: the winner went from 45 table-rows to 5). A
**comparison** `table` / `metrics-grid` appears **only for a genuine A-vs-B comparison** — two things
weighed side by side on the same axes — and it **replaces** that comparison's prose, never decorates a
paragraph. Numbers that belong to the derivation get **taught in prose** (a worked handle), not parked
in a grid (banca cega da forma 2026-07-04).

## Author in Markdown — derivation + gaps as Markdown-native carriers

The rite's form is pinned **Markdown** (the neutral `render.RENDERER_ID` renderer, H1 first). Research's
derivation idiom rides Markdown-native carriers: the reasoning chain as an ordered **list** or a fenced
derivation block (`from first principles: … → [GAP] … → closed by <cite>: …`), the open gaps as a
**gap table**, comparative numbers as a **table** instead of narrated prose (a block only where it
replaces a paragraph). Mark the knowledge boundary explicitly — derived vs repeated vs unknown.
**Sections are FREE** — the rite checks the *property* (depth, derivation, honesty, actionability),
never a named section.

## The rite is the path — exit through `tools/rito.py` (docs/rito-runtime.md)

**The research producer traverses the experiment's rite as executable code**, the same runtime `report`
exits through ("o edge deve soar o mesmo across artefatos"). You do not build a structured spec, you do
not call `close.run_close`, and you **never** call `publisher.publish` — the rite runtime sequences the
whole causal execution (grounding-1 through publication of the rendered page) and seals a receipt for
every stage. Your job is the COGNITION: the per-stage prompts carrying research's derive-first Feynman
cognition. The runtime owns sequencing, sealing, rendering (the pinned neutral-markdown renderer,
`render.RENDERER_ID`) and publication. A run that didn't publish didn't finish the rite.

The stages you feed (authoring format is **Markdown**; the derivation list/fence + gap table + comparison
table carry the visual idiom): `grounding1_dossier` (your derive-first dossier — the from-first-principles
reconstruction with each stall marked `[GAP: …]`, then the gap-closing evidence you read; the
gather-grounding slot above) → `first_authorial_draft` → `reviewer_notes` (ONE reviewer that only points out furos — no veto, no score, no second round; ADR-0025) → `author_revision` (you decide each furo at your convenience: fix it, or keep it and mention it under `## Notas do revisor`) → `treatment_cleanup` (deterministic copy when the leak scan is clean) → `final_html` (pinned render, runtime-owned) → `publication`. The canonical prompt bodies are archived in
`drafts/old-edge-double-grounding-repro/run.py`; adapt their content to THIS target — the produce
guidance above (derive, show the thinking, mark the boundary, end ready-to-implement, in the
PEDAGOGUE's Feynman voice with prose carrying the argument, a table only for a genuine A-vs-B
comparison, length EMERGENT) is what the authoring prompts must carry. The exp-feynman-pedagogico intent rides two places: the authoring drafts
(`first_authorial_draft`/`author_revision`) write in that voice, and the reviewer's focus is
**pedagogical** — where does this fail to TEACH? where is it cryptic, where is the
contextualization thin? — named as furos, never as a verdict. Since ADR-0025 there is no
second grounding round: reach for **NEW grounding** — world/domain material beyond what you
already hold — while you gather grounding-1, BEFORE the draft. **Fidelity guard: new grounding
must be FETCHED and cited, NEVER invented** — the dossier's fetched sources are the only factual
anchor; a pedagogical handle explains a grounded fact, it never licenses fabricating one. A fact
with no source is a furo the reviewer names ("fato sem fonte"); the author fixes it or keeps it
and says so under `## Notas do revisor`.

The wake's `DISPATCH_ID=<id>` line rides into the run (the canonical publish refuses without it, E1c).
The product spine still ships: pass `publish_meta` with `proposes` (candidate steers — a research that
reframes the next bet declares it here), `distills` (existing cluster threads only — empty over
fabricated), `cites` (source + the snippet you used), `lineage` (`builds_on` the prior the surf offers),
`bears_on` (SÓ sobre hipótese VIVA — `cortex.hypotheses_at()` lists them; empty over fabricated), `para`
(explicit target reader; empty resolves to the mentee) and `reports_on`.

    tools/edge-python <<'EOF'
    import sys; sys.path.insert(0, 'tools')
    import rito, llm_routes

    slug = '<slug>'
    dispatch_id = '<dispatch-id-from-DISPATCH_ID-line>'

    def complete_fn(route, prompt, max_tokens):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    prompts = {
        'first_authorial_draft': lambda o: f"<derive this target from first principles, then close the gaps with the dossier's evidence; mark derived vs repeated vs unknown; end ready-to-implement; duty is skills/_shared/scaffold.md — execute it, do not restate it; PEDAGOGUE's Feynman voice: motivate WHY before the mechanism, one vivid handle per hard idea, address the reader, explain-don't-label; prose carries the argument, a table only for a genuine A-vs-B comparison; length EMERGENT; synthesis-to-a-bite is a failure>\n\nDOSSIER:\n{o['grounding1_dossier']}",
        'reviewer_notes':        lambda o: f"<point out the FUROS only (no verdict, no veto) — critique of the FULL ARC against skills/_shared/scaffold.md: where is there no door in the first block? which derivations are asserted not shown, where is a load-bearing claim a bite / lead without the reasoning, where would a stranger who did not live the session fail to restate claim and why, where is the world absent, which claims lack a cite? A tight lead is a gap, not a pass>\n\nDOSSIER:\n{o['grounding1_dossier']}\n\n{o['reader_facing']}",
        'author_revision':       lambda o: f"<same-author revision in the same voice: for EACH furo, fix it or keep it and mention it under 'Notas do revisor' — your call; never invent a fact or a citation (what has no source leaves the text or becomes declared uncertainty)>\n\nDOSSIER:\n{o['grounding1_dossier']}\n\n{o['first_authorial_draft']}",
        'treatment_cleanup':     lambda o: f"<bounded same-author leak cleanup>\n\nSCAN:\n{o['treatment_leaks']}\n\n{o['author_revision']}",
    }

    rito.run_rito(slug, run_dir=f'state/rito/{slug}',
                  grounding1_fn=lambda: '<the derive-first dossier: first-principles reconstruction + gap-closers you read>',
                  prompts=prompts, complete_fn=complete_fn,
                  intent='open: …; bet: …', skill='research', dispatch_id=dispatch_id,
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
world is never a research decision.
