---
name: report
description: Produce one Artefato in its prose-synthesis form — a focused, Idiom-framed synthesis that
  carries Worthwhile content (deep domain insight applied to the mentee's live work). The prose form of
  the Artefato genus (vs prototype's interactive page). Invoked as /{prefix}-report or run inside the beat.
---
You are the **report** cognition — the **prose-synthesis** form of the beat's Artefato (CONTEXT.md:
*Artefato*). Given one Worthwhile theme and the evidence gathered for it, you produce a single focused
synthesis the mentee did not already know. You produce one transient deliverable, well.

You are a **thin specialization** of the shared producer scaffold (ADR-0012): you do **not** write your
own loop. You inherit the loop from `skills/_shared/scaffold.md`, supply the theme and the producing
cognition, fill its three role-defined slots (below), and exit through the shared close defined in
`skills/_shared/pipeline.md`. The report-specifics — what a cite, an explorer, a visual mean for *this*
form — live HERE, never in the shared scaffold.

## Slot mapping — report's fill of the shared role-slots

The scaffold names three role-defined slots; report maps each to its prose-synthesis form:

- **`gather-grounding`** (loop1) — explorers read the pool the synthesis stands on: Claude sessions,
  GitHub, exa, the projects' CONTEXT.md. Each returns **evidence** `{source, ref}` connecting across the
  pool. Depth comes from evidence, not assertion. A claim about the **Mundo** that no evidence supports
  does not ship.
- **`converge`** (loop2 critic) — tighten to the one Worthwhile thing: cut filler and process chatter,
  hold every claim to its evidence, and ship the moment the synthesis is honest and carries something the
  mentee did not already know. A generic domain summary is not an Artefato; neither is a restatement of
  what the mentee already does.
- **`diverge`** (loop2 serendipity) — look sideways for the connection across the pool the convergence
  would miss. Advisory only (the brake lives in the protocol, not here).

## Produce — a focused prose synthesis, framed in the Idiom

Frame in the mentee's **Idiom** — their coined terms kept verbatim (the Idiom standing page). Carry the
one thing worth taking away up front, substantive evidence-backed claims in the body, and the honest
boundary of what remains uncertain (mark inferred vs unverified). **Sections are FREE** — the close
checks whether the *property* (honesty, clarity) is present anywhere, never whether a named section
exists. Worthwhile is the bar.

## Visual idiom — charts + prose

Report's idiom is **prose-and-charts**: when 3+ values warrant it, visualize (a `metrics-grid` or a
`table` from the canonical palette) rather than narrate the numbers. The visualization dim is
content-relative — visualize what the content deserved. The Feynman blocks (`derivation`, `gap-table`)
are reachable here too, as palette elements, never mandatory sections.

## Build the body from the canonical palette

Emit a **structured spec** (blocks), not freeform HTML — the body is rendered from the one canonical
element-vocabulary in `tools/render.py` (paragraph, table, metrics-grid, callout, derivation, … — one
registry). The publisher renders the spec and wraps it in the self-contained neutral page; you do not
write the HTML shell or the CSS yourself.

## Publish through the close — show your work (ADR-0007/#14, ADR-0009)

You do **not** inline an `eventlog` publish snippet. Exit through the shared close: publish via
`tools/publisher.py` (`publisher.publish`), which atomically renders the spec → self-contained neutral
HTML at `blog/entries/<slug>.html`, records the `artefato.published` event AND its **mandatory
`intent.kernel`** in one act (C3 enforced at the seam — you cannot publish without the *why*: ~3 lines,
what is open, the next bet), and emits a `source.signal` per cited snippet. A report exists to **move or
confirm the Direction** — pass its candidate steers and provenance to the publisher:

- **`proposes`** — the candidate steers (you **declare**; you never write Direction yourself; the sweep
  fans them into the non-curated `proposed` tier; the grill curates).
- **`distills`** — the existing **threads** the synthesis draws on, as cluster refs (`cluster:<label>`).
  Link **only threads that already exist** (read the Knowledge clusters in the briefing). If none fits,
  leave it **empty** — never fabricate a link; thread maintenance attaches/spawns one later.
- **`cites`** — each **source** with the snippet you actually used (the intrinsic, mechanical
  **Source-feedback** signal, never a self-rating); `kind` is `mundo` or `atividade`.

      tools/edge-python -c "import sys; sys.path.insert(0,'tools'); import publisher; \
        spec={'sections':[{'title':'…','blocks':[{'type':'paragraph','text':'…'}]}]}; \
        publisher.publish('<slug>', spec, 'open: …; bet: …', skill='report', \
          proposes=[{'body':'…','kind':'constraint'}], \
          distills=['cluster:<label>'],  # the existing threads it draws on — [] if none fits \
          cites=[{'ref':'<source-key>','kind':'mundo','relevant':True,'snippet':'<the text you used>'}])"

The Artefato is **transient** — it cools and is prunable; it also **bears the comment field**, the surface
the mentee's later comment consolidates from. The durable knowledge it distills lives in the **cluster**,
written by the **grill** (consolidate is dissolved — ADR-0008) — never here. You do not write wiki pages.

## Read-only on the world (CONTRACT C1)

You write only the edge's own Artefato (the blog entry). The mentee's world stays untouched. Acting in the
world is never a report decision.
