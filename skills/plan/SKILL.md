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

## Slot mapping — plan's fill of the shared role-slots

The scaffold names three role-defined slots; plan maps each to its next-steps form:

- **`gather-grounding`** (loop1) — explorers read what already exists and what is open: the projects'
  CONTEXT.md, the live Direction, prior Artefatos on the theme, GitHub state, exa for how others did it.
  Each returns **evidence** the plan stands on `{source, ref}` — the current state a step changes, the
  prior art a step reuses. A step grounded in nothing does not ship.
- **`converge`** (loop2 critic) — tighten the scope: a small feasible cycle beats an ambitious impossible
  one. Cut steps that aren't load-bearing, name what is explicitly out of scope, and ship the moment the
  next move is concrete and ordered. A vague aspiration is not an Artefato.
- **`diverge`** (loop2 serendipity) — look sideways for the cheaper path, the dependency that reorders the
  steps, the reusable prior the convergence would miss. Advisory only (the brake lives in the protocol,
  not here).

## Visual idiom — next-steps-grid / flow

Plan's idiom is the **next-steps-grid** (the steps as ordered cards: what goes in, what happens, what
comes out, what blocks what) and the **flow** (`flow-example` — input → output per step, or an
`ascii-diagram` of the step sequence). The visualization dim is content-relative: a plan with ordered
steps clearly warrants the grid/flow rather than a paragraph of prose. Reach for `risk-table` for the
risks/mitigations and `metrics-grid` for the cost or estimate — palette elements, never mandatory
sections.

## Build the body from the canonical palette

Emit a **structured spec** (blocks), not freeform HTML — the body is rendered from the one canonical
element-vocabulary in `tools/render.py` (next-steps-grid, flow-example, ascii-diagram, risk-table,
metrics-grid, table, … — one registry). The publisher renders the spec and wraps it in the self-contained
neutral page; you do not write the HTML shell or the CSS yourself. **Sections are FREE** — the close
checks whether the *property* (honesty, clarity) is present anywhere, never whether a named section exists.

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
what is open, the next bet), and emits a `source.signal` per cited snippet. A plan exists to **move or
confirm the Direction** — its proposed next moves are candidate steers; pass them and the provenance
through the publish_fn:

- **`proposes`** — the candidate steers, the proposed next moves (you **declare**; you never write
  Direction yourself; the sweep fans them into the non-curated `proposed` tier; the grill curates).
- **`distills`** — the existing **threads** the plan draws on, as cluster refs (`cluster:<label>`). Link
  **only threads that already exist** (read the Knowledge clusters in the briefing). If none fits, leave
  it **empty** — never fabricate a link; thread maintenance attaches/spawns one later.
- **`cites`** — each **source** the plan stands on, with the snippet you actually used (the intrinsic,
  mechanical **Source-feedback** signal, never a self-rating); `kind` is `mundo` or `atividade`.

      tools/edge-python -c "import sys, functools; sys.path.insert(0,'tools'); import close, publisher; \
        slug='<slug>'; intent='open: …; bet: …'; \
        spec={'sections':[{'title':'…','blocks':[ \
          {'type':'next-steps-grid','steps':[{'title':'…','description':'what goes in → what comes out'}]}]}]}; \
        proposes=[{'body':'…','kind':'phase'}]; \
        distills=['cluster:<label>']  # the existing threads it draws on — [] if none fits ; \
        cites=[{'ref':'<source-key>','kind':'atividade','relevant':True,'snippet':'<the text you used>'}]; \
        artefato={'slug':slug,'intent':intent,'content':spec,'proposes':proposes,'cites':cites}; \
        # the publisher-backed publish_fn: close hands it (artefato, proof); proof rides as verdict= \
        do_publish=functools.partial(publisher.publish, slug, spec, intent, skill='plan', \
          proposes=proposes, distills=distills, cites=cites); \
        publish_fn=lambda art, proof: do_publish(verdict=proof); \
        close.run_close(artefato, produce_fn=lambda: artefato, complete_fn=<review-completer>, \
          publish_fn=publish_fn)"

The Artefato is **transient** — it cools and is prunable; it also **bears the comment field**, the surface
the mentee's later comment consolidates from. The durable knowledge it distills lives in the **cluster**,
written by the **grill** (consolidate is dissolved — ADR-0008) — never here. You do not write wiki pages.

## Read-only on the world (CONTRACT C1)

You write only the edge's own Artefato (the blog entry). The mentee's world stays untouched. Acting in the
world is never a plan decision.
