# edge (new) — glossary

The ubiquitous language of the reborn edge: a **mentor** that knows the mentee and the
domain well, and produces content worth reading. Built fresh (not edited from the old
one) so it can be **confronted** with the old glossary (`~/edge/CONTEXT.md`, today a
machine-language). Grows as concepts evolve (via /pocock-grill-with-docs).

> Language only. Invariants live in `CONTRACT.md`, decisions in `docs/adr/`.

## Language

**Mentee**:
The person the edge serves — their real work is the subject. The edge knows them from
what they do (code, docs, words), not from supposition.
_Avoid_: user, client, operator

**Domain**:
The field the mentee works in. The edge must know it deeply to have substance.
_Avoid_: area, topic, field

**Worthwhile content**:
The intersection: deep domain insight **applied to the mentee's live work**. Domain
alone is generic; mentee alone is shallow.
_Avoid_: report, output, post

**Artefato / Artifact**:
A beat's **published deliverable**, in whatever form the producing skill yields — a prose
synthesis (`ed-report`), an interactive page (`prototype`), and others. The genus, not one
form. Carries Worthwhile content; bears the comment field (consolidation surface).
**Transient**: it cools and is prunable — the durable knowledge it distills lives in the
**cluster**. Not a permanent wiki page.
_Avoid_: report (a skill name), output, post

**Hypothesis**:
Something the edge supposed (mined or inferred) and not yet confirmed (`assumed`). The
edge **works naturally** with hypotheses — the abundant, cheap tier.
_Avoid_: guess, draft

**Curated**:
Knowledge consolidated by the mentee (`confirmed`/`corrected`). **Prioritized** over a
hypothesis in every read-model.
_Avoid_: validated, final, approved

**Consolidação de hipóteses / Hypothesis consolidation**:
Promoting hypothesis → curated. What `/grill-me` (active) and the per-report comment
(async) do. Does not drain the hypothesis tier; consolidates what carries **harm potential**.
"Afinamento" is the same loop when the object is the mentee's **language** (Idiom).
_Avoid_: approval, review, afinamento (as a separate concept)

**Harm potential**:
The consolidation priority: source ambiguity × cost of acting wrong. Decides what spends
the mentee's scarce attention.
_Avoid_: urgency, score

**llm-wiki**:
The edge's knowledge, held as two kinds of durable page — **Knowledge clusters** (emergent,
grown) and a few **Standing pages** (declared then refined: Direction, Idiom, Source roadmap)
— plus cross-references, holding both hypothesis and curated. An **Artefato** is a transient
delivery (a Query result), never a page. Read in full each beat when size permits — the edge's
own bounded knowledge, not deltized like the inputs. This is what **replaces the code**:
orientation that used to be scaffolding now lives here.
_Avoid_: knowledge base, RAG

**Knowledge cluster**:
The wiki's **emergent durable page** — a unit of knowledge (mentee or domain) that
accumulates hypothesis + curated, **grown** from reading and grilling, never declared.
Materializes as a **thread**. Artefatos hang off it. Not the wiki's *only* durable page —
see **Standing page**.
_Avoid_: topic, tag

**Standing page**:
A durable wiki page that is **declared then refined**, not grown — seeded from `agent.yaml`
and sharpened by the onboarding grill. Three today: **Direction**, **Idiom**, **Source
roadmap**. These are what the rebuild moves out of code/config and **into the wiki** (the
project's "replace the code with the wiki").
_Avoid_: config, settings, scaffolding

**Direction**:
The mentee's current direction the edge aligns its work to — phase, priorities, constraints,
what they are working toward now. A **standing page**. The old `config/strategy.md`, as wiki.
_Avoid_: strategy, plan, goals, alignment (collides with Convergence)

**Idiom**:
The mentee's own language — their terms and meanings, kept so the edge frames work in their
words. A **standing page**, the **Voz** glossary. The old `memory/operator-idiom.md`, as wiki.
_Avoid_: jargon, terminology

**Source roadmap**:
The registry of **keys** the edge reads — the Mundo and Atividade sources, source-agnostic
(just a locator, no per-source primitive). A **standing page**. The old source bindings, as wiki.
_Avoid_: config, bindings, feeds

**Convergence**:
The edge's model (wiki + mentee glossary) matching the mentee's reality. The loop closes
when Lint exposes the error and the mentee resolves it.
_Avoid_: sync, alignment

## Knowledge intake / Entrada de conhecimento

> Three legs feed the llm-wiki. Named by the **subject** the knowledge comes from, not
> by the mechanic. The axis that separates them: **world vs observed vs directed**.

**Mundo / World**:
The external field the edge pulls from (arXiv, HN, EXA, Twitter). Unverified claims about
the world — pass the adversarial judge before they compose into the wiki.
_Avoid_: coleta, source, corpus, busca

**Atividade / Activity**:
What the mentee **does** — code, commits, docs, transcripts, whatever they leave. **Observed,
not directed**: it shows what the mentee actually does, not something said to the edge. The
mentee need not even work in Claude Code. Yields `hypothesis` about domain and intent. The
reborn `signals` leg, scoped to the mentee.
_Avoid_: obra, work, rastro, trace, ingest, signals, operator pressure

**Voz / Voice**:
What the mentee **directs** at the edge — correction and language. **Directed, not
observed**: authored and highest priority ("a correção sempre ganha"). Subsumes language
(Idiom) and correction. Keeps the mentee glossary.
_Avoid_: operator pressure, feedback, pressão

**Delta**:
What's new in the **inputs** — the world the edge ingests (Mundo, Atividade, Voz) — since the
last consolidation. The world is too big to re-scan whole, so the edge reads the inputs
incrementally, anchored at the previous beat's consolidation point. **The delta is over the
world, never over the wiki**: the edge's own accumulated knowledge is read *in full* (size
permitting), not deltized — only the inputs are. **Source-agnostic**: a git tree, a folder of
docs, a transcript — never narrowed to one surface's mechanics. Its role is **orientation, not
evidence**: it stays light and points the beat at fresh material so a theme can be chosen.
Depth comes afterward — once a theme is picked, **research reads the actual documents directly,
including old ones**, unbounded by the delta. Sufficient **only if state consolidation is
faithful** — the last consolidation is the point it reconciles against.
_Avoid_: changeset, watermark, cursor (do not narrow it to a git changeset; do not deltize the
wiki; do not let the delta become the evidence — it orients, research deepens)

## Curation / Curadoria

> Two **orthogonal, unmerged** processes move pages between strata (L1/L2 split, like the
> digest). They act on two orthogonal axes: **tier** (hypothesis vs curated) and
> **temperature** (hot/cold/archived).

**Envelhecimento / Aging**:
Mechanical curation (L1, every beat) on the **temperature** axis. The signal is **usage =
consumption**: the wiki offers the whole list each beat, the edge pulls only what it needs,
and that reach keeps a page hot. Offered-but-unconsumed cools, then archives; pulling a cold
page back re-warms it. No proxy signals — the edge's own reach is the signal.
_Avoid_: decay, ttl, eviction

**Lint**:
Semantic curation (L2, LLM, periodic): detects contradiction / superseded / orphan / gap.
**Resolves only the rule-decidable** (`curado > hipótese`, recency) and **escalates the
residual to Voz** by harm potential. Detects; the rule or the mentee resolves — never by
judgment in code. The detector half of `Convergence`.
_Avoid_: validator, linter, cleanup
