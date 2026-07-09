# The shared producer scaffold

The producer-loop every producer-skill inherits (ADR-0012). A producer-skill — `report`,
`map`, `research`, `plan`, … — does **not** write its own loop. It inherits this scaffold,
supplies the theme and the producing cognition, and fills three **role-defined slots**. The
loop structure and the context-denial ladder are the same for every producer; only the slot
*content* differs.

This scaffold is **non-procrusto** by design: it names roles, never report-specifics. A `map`
producing a diagram and a `report` producing prose-and-charts run the **same** scaffold.

## Genus default rite v6 — old-edge grounded, canonical form

This rite is **genus**, not `report`: every producer translates it into its own form. It is not
a loose property checklist. The canonical reader journey and block grammar are default for the
roster. A map can carry them as edges and captions, a plan as dependency rationale, a prototype
as interaction plus notes, a report as prose and tables. No skill opts out; a skill only changes
the **vehicle**, not the house style.

Canonical content: `docs/genus-rite-v6-canonical-form.md`.

The promoted rite is the old Edge manifestation with one extra grounding turn and a default form.
It is a **sequence of cognition plus a canonical reader journey**, not a reviewer checklist:

1. **Old-edge equivalent first draft** — reason from the live problem before authority: derivation,
   honest unknowns, outside-frame instinct, lineage, and a mentor arc. The first read should feel
   like an intelligent operator discovering the claim, not a compliance template filling slots.
2. **Actionable gap gate** — the gate is not only approval. It names the lacunas the draft exposed:
   missing context, weak mechanism, missing predecessor, shallow Mundo, overclaim, or unclear next
   validation. A vague "needs more sources" is not a gate; a task tied to a claim is.
3. **Directed post-gate Mundo grounder** — grounding happens after the gap gate, aimed by the named
   lacunas. It reopens the relevant prior artefacts/sessions, reader model, lineage, and world
   sources. It must answer the draft's actual unknowns rather than decorate the text with citations.
4. **Rewrite with visible grounding effect** — the final artefato shows what changed: which claim was
   repositioned, which magnitude was narrowed, which analogy failed, which caveat strengthened, which
   next validation changed. If Mundo did not validate the local result, say that; positioning is useful
   even when it withholds comfort.
5. **Fact-audited final close** — external sources may locate the work in a family of methods, but
   they do not validate a local effect size, saturation band, ranking, or causal claim unless they
   support that exact transfer.

For developed syntheses, this sequence also rides as a proof-bound `genus_rite` trace in the publish
payload. It is not reader-visible process diary; it is the mechanical evidence that the final voice and
shape came from the approved rite rather than from end-stage imitation.
Trace entries are linked: `gap_gate[].id` -> `post_gate_grounding[].gap_id` ->
`rewrite_delta[].gap_id`; each `post_gate_grounding[].source_ref` must exist in `cites[].ref`, each
`gap_gate` entry must be grounded and rewritten, each `rewrite_delta[].final_anchor` must appear in the
final artefato, and each `canonical_journey[].where` must point to visible text while covering the
canonical moves below.

The canonical form grammar is also genus default. The reader should experience this sequence unless
the artefact explicitly earns a translation: thesis title; live question / reader context; identity
and setup; configuration or lineage ledger; observed result/current read; concrete mechanism trace;
interpretation/teaching; Mundo/outside frame; visible grounding effect; unknowns/limits; decision
and next validation; references/pointers. Section names may vary, but an artefact that jumps from
thesis to implementation, or emits a compact internal ADR where the canonical form calls for a
contextualized mentor artefact, has changed the genus rather than translated it.

The canonical block palette is default too: prose for the arc, `comparison-table`/`table` for arms,
configs, lineage, and fit/mismatch, `metrics-grid`/`chart` for quantitative results, `derivation` for
first-principles reasoning, `gap-table` for lacunas and unknowns, `next-steps-grid` for the closing
decision path, and `bibliography` when Mundo appears. Structural blocks carry information shape; they
are not decoration, and paragraph-only output is a failure when the content has comparisons, results,
gaps, and next steps.

Every Artefato also owes these properties at its depth target:

- **Reader growth model / contextualization**: the artefato is explicitly for the mentee or a named
  reader, and spends context only where that reader needs it. The default reader is the operator/mentee.
  The producer models that reader's **leveling**, live **interests**, decision context, and what would
  maximize utility and growth for them now. Cryptic is a defect; re-teaching what the reader already
  holds is also a defect.
- **Lineage ledger**: prior artefacts, sessions, experiments, commits, reports, tickets, or decisions
  that matter are named with stable ids/paths when available. Use a **numbered** lineage ledger when
  more than one predecessor matters. For each predecessor, say what this artefato inherits, rejects, or
  changes. Hidden publish metadata is not enough. If there is no meaningful lineage, mark that honestly.
- **Derivation and boundary**: derive the load-bearing claim before leaning on authority, and mark
  what remains unknown, inferred, untested, or outside scope.
- **Concrete mechanism trace**: include at least one worked example, case row, diff, path, failure mode,
  or representative instance that shows how the claim works. Results without mechanism do not teach.
- **Mundo deepening / outside frame**: use external concepts, field names, studies, comparable
  experiments, benchmarks, and **best practices** where the topic deserves that depth and where they
  improve the reader's model. The Mundo move is not a shallow analogy: it gives pointers for deeper
  study, names the field's vocabulary, and explains fit/mismatch. Each external term must change or
  sharpen a claim, caveat, example, decision, or next validation.
- **Post-gate grounder**: when a gate, critic, or review exposes a real gap, run a targeted grounding
  pass after that feedback and before the final gating review. The grounder revisits the relevant prior
  sessions/artefacts, reader model, lineage, and Mundo sources. It is not prose polish; the new read must
  change something: claim, caveat, example, decision, or next validation.
- **Fact-audit**: before publish, audit every external comparator and numeric transfer. Sources can
  position a local result without validating its magnitude. Do not import bands, rankings, causal claims,
  or generalization unless the source supports that exact transfer.

The old rich-rite floor (derivation, unknown boundary, outside frame, lineage) is the **hard minimum**.
The rite above is the richer genus default that the blind reviewers judge semantically.
Depth controls how much each property is developed; it never deletes the property.

## The writer's identity — seja Feynman nesse sentido

Whoever writes the artefato: **seja Feynman nesse sentido** — the NAME is the pointer (it fires
the trained attractor better than pages of rule), scoped fine: the mind that does not fool
itself, that explains simple-and-complete, that names what it does not know. The taste to point
at lives in the cânone tattoo (`memory/canone.md` — carried in every briefing): when in doubt,
be like those; the anti-cânone names the smell of the hollow. The persona stays in the WRITER
only — the production gates remain impersonal (concepts, never the persona; reviewer≠asserter).

## Depth — the producer works to its depth TARGET; the subagents serve it

The producer develops the theme to a **depth target**, not to a fixed size. The scarce resource is
the **mentee's attention**, and only they know how deep a theme is worth to them — so the target is
the **operator's to set per artefato**. Absent an override, the target is the **producing skill's
declared default** (`Depth default:` in its SKILL; a skill that declares none defaults to `standard`).
Depth is an **attention/development target, NEVER a block count** — sizing to a block count rebuilds
the shadow-metric this exists to avoid; the producer translates the target into whatever blocks realize
it.

Three targets:
- **`brief`** — the lead that stands alone: the one takeaway, its single load-bearing claim, and the
  honest boundary. Deeper development is *available* (progressive disclosure) but folded, not spent on
  the reader up front.
- **`standard`** — the arc whole and the load-bearing claims reasoned through, tailored to the mentee;
  the derivation is shown but not every facet exhausted.
- **`deep`** — **plenitude**: the theme developed to its full depth, every move developed, no facet left
  folded. The multi-agent structure is leverage for this depth: the subagents exist to **free the
  producer to go deep**, never to compress the result. This is the target the old universal doctrine
  assumed for *every* artefato — now it is **one target among three, chosen by the operator**, not the
  producer's default guess.

The **rich-rite floor is INVARIANT across depth**: the four cognitive moves (derivation, a marked
boundary, an outside frame, the lineage) must be **present** at every target — that is the genus gate,
unchanged. Depth sets how far *above* the floor the producer develops: the floor is the moves'
**presence**, the target is their **development**. A `brief` still carries all four moves — tightly.
Synthesis-to-a-bite is a **failure** only against a `standard`/`deep` target; at `brief` a tight honest
lead **is** the job. The producer is **free** to wield its subagents however it judges best toward the
target; the slots below name *roles*, not a fixed delegation shape.

## The three slots are role-defined, NOT report-defined

The scaffold defines three slots by their **role** in the loop. It says what the role *does*,
never what a particular report-form *is*:

- **`gather-grounding`** — loop1's role: the producer **grounds in its own context — recall (rung 1)
  + DIRECT reads of the sources** — so the **rich context stays in the producer**, available for the
  synthesis (#61). **Recall before you research** (`skills/_shared/memory.md`): first pull the subgraph
  your theme already touches from the edge's own memory, so you chase what is *missing*, not what you
  already published. Then **read the sources yourself**: direct reading brings back the **real cases and
  the depth** — a real report's grounding was done in the main loop, and that is why it had concrete cases
  and depth; the thin `{source, ref}` an explorer returns **loses the founding context** the synthesis
  needs (the #61 evidence). Delegating to explorers is an **OPTIONAL fan-out for BREADTH** — reach for it
  when the theme has **independent facets** worth parallelism, or to probe a gap a first pass exposes —
  **not the default grounding path**. The producer wields the subagents **as it judges best**, within the
  runtime's concurrency cap — the scaffold offers the affordance and per-form *guidance*, **never a fixed
  delegation shape**. The slot says "gather grounding," not "fetch this URL." Whether an explorer
  reads a paper, a repo, or a graph thread is the **producer skill's** decision. *How* an explorer reaches a world source is
  the same for every producer and is **never a per-source primitive** (ADR-0001): read the source's
  `interfaces[].via` spec in `agent.yaml` plus `state/source-roadmap.md` and call it **agentically** — the
  install's keys are already loaded. There is no `libexec/` primitive and there never will be; an
  explorer that cannot ground reports *which key it could not work*, never "a primitive is missing"
  and never waits for one to be built.

  Every world read in this slot is **harvested, never emitted**: the `grounding.manifest`
  record is mined post-hoc from the transcript by the substrate (`tools/harvest.py`) —
  literal queries byte-identical, PRISMA-grade — so neither the producer nor its explorers
  carry ANY emission duty; there is no manifest act to forget. What the slot DOES owe is
  reading `state/source-roadmap.md` **at gather time**: query each source in its **declared
  idiom** (an off-idiom query that comes back empty is a false dry you manufactured), take
  the briefing's **yield table** as advisory ordering (never a router), and treat any dry
  read as **licensing no negative claim** until the fold rules it — the only in-session
  move is running the source's **canary as advice**. One house rule guards the harvester's
  blind spot: a script of yours that reads a source **logs the literal query to stdout**.

  **The explorer is a WORLD-reading subject — DENY it the `cortex` self door (N5/R6, ADR-0014).** An
  explorer reads the *world* (a paper, a repo, a source key); the **self** (the edge's own memory) is
  the producer's own job, reached **directly at rung 1** (the recall pass below), never by an explorer.
  Fan it through the **committed `{prefix}-explorer` subagent** (`.claude/agents/explorer.md`, deployed
  to `~/.claude/agents/`) — that artifact's frontmatter declares `disallowedTools: mcp__cortex__*`, so
  the harness **mechanically strips** the self door from the explorer BY CONSTRUCTION (not by prose you
  must remember). A read-only door does NOT make this safe: ADR-0014's failure is one CONTEXT holding
  world-new evidence beside recalled-self, where one is read as the other — the contamination forms
  before any write, so the **scope deny** is the wall, not read-only-ness. The producer holds the door
  and recalls for itself; its world-reading fan does not. (A graph-reading recall is rung-1 producer
  work, not an explorer — `memory.md`.)
- **`converge`** — loop2's critic role: decide whether the artefato is **developed to its depth
  target** and ready to ship — the arc whole, the moves present, tailored to the mentee, carrying what
  they did not already know, developed *as far as the target asks* (a `deep` target ships only at
  plenitude; a `brief` ships when the standalone lead is whole — no further). Converge means *judge the
  development matches the target*, **never** *cut below it*. The slot says "converge," not "compress"
  — but the target, not the producer's appetite, sets how far.
- **`diverge`** — loop2's serendipity role: look sideways for the connection the convergence
  would miss. It carries a **reserved curiosity budget** (the *budget for curiosity*): a fixed slice
  of the dispatch's spend that **must** go to a sideways thread, so serendipity is never starved by
  the pull to converge. It does not *gate* the ship (the brake still caps reopens), but its budget is
  **protected** — the producer can never spend 100% converging.

**Role-defined, not report-defined** is the load-bearing rule. The scaffold must never hard-code
report semantics into a slot — an explorer is a role, not a URL fetcher; a cite is a role, not a
hyperlink; and no section is ever mandated (sections are FREE; the scaffold names no section and
requires none). If the scaffold welded report semantics,
`map` and `plan` would have to fight it. Instead, **report-specifics live in each producer
skill's mapping** — the report skill maps `gather-grounding`→its explorers, `converge`→its
critic, `diverge`→its serendipity, and decides what a cite or a visual means **for that form**.
Those mappings live in the skill, never here.

## The loop structure

Two loops run inside the scaffold:

- **loop1 — explorers → evidence.** The `gather-grounding` slot fans explorers out; each returns
  evidence. loop1 is the grounding pass: it builds the pile of evidence the producing cognition
  reasons over. (Honoring the operator rename, the grounded material is named **evidence**.)

- **loop1.5 — excavate (EDGE_EXCAVATE, dark by default).** The mechanical enforcement of this
  scaffold's own plenitude doctrine: a producer reasoning over a large evidence pile writes from one
  lossy pass with a brevity prior, and the non-obvious long tail — the worthwhile, course-changing
  material — dies silently in that compression. When `EDGE_EXCAVATE` is on, before the producer
  converges it runs `tools/excavate.py` over the evidence: a single structured pass working the
  synthetic grill's four probes (relevance / contradiction / surprise / lineage) **aimed by the
  Direction**, recovering only what the producer's own thin summary dropped — as an accountable
  **seed** (each finding cites back into the evidence and states how it bears on the Direction). The
  producer then develops loop2 **from the seed**, discharging every entry (it lands in the artefato
  or is cut with a reason). Off ⇒ the stage is a pure no-op with zero model spend; the producer
  works exactly as today. This is the *collapsed* form of the grill (one extraction pass); the
  multi-turn agent×agent dialogue is the costed escalation, gated on this cheap cut earning its lift.

- **loop2 — critic / serendipity.** The `converge` slot's critic judges whether the draft is
  **developed to plenitude** and emits a verdict carrying a `ship` boolean; the loop ends the moment
  the critic ships — it ships on *depth reached*, never on *brevity reached*. The `diverge` slot's
  serendipity holds a **protected curiosity budget** that is always spent, but it does not *gate*: it
  may request a reopen of loop1, and the brake honors that request **at most `LOOP2_MAX_REOPENS`
  times** before the loop stops anyway. A critic that ships ends the loop immediately even while
  serendipity still wants to diverge — the reservation guarantees serendipity *happens*, never that
  it can hold the loop hostage.

The brake is not the producer's discretion: it lives in the protocol. See `tools/close.py`
`run_loop2(artefato, critic_fn, serendipity_fn, reopen_fn)` — the testable spine that converges
on `critic.ship`, caps serendipity's reopens at `LOOP2_MAX_REOPENS`, and returns the final
critic verdict.

## The inner passes — recall before you act, project after you publish (#28)

Besides the world and the mentee, the producer has a **third relation: its own memory** — the edge's
graph (the curated web + the projected spine). It is reached by the producer **directly (rung 1)**, not
by an explorer: it is *recall*, not research. The discipline and the concrete cypher live in
**`skills/_shared/memory.md`**; the loop obeys it at two points:

- **Recall-before-act** — at the **start of loop1** (before fanning explorers) and **before the close**:
  pull the subgraph your theme touches (its clusters, prior Artefatos, open bets). You never re-derive,
  re-research, or re-publish what you already know — recall is cheap and owned, the world expensive and
  fuzzy. Recall *feeds* plenitude: you build on the depth of prior Artefatos rather than duplicate them.
- **Project-after-publish** — immediately **after the close publishes**: project the Artefato into the
  graph (`MERGE (:Artefato …)` + `DISTILLS/CITES/PROPOSES` edges) so today's output is tomorrow's recall.
  The log stays canonical (ADR-0006); the graph projection is best-effort (a failed write is reported,
  never fatal).

This closes the loop `recall → research (the gap) → produce → publish → project → recall`.

## The type→format rule — reach the whole palette, lead with your floor

The writer's default is prose; left alone it answers every content-shape with a paragraph and the rich
palette (`tools/render.py` `BLOCK_SCHEMAS`) goes unused. This rule is **property-not-section** (ADR-0012/0013):
it says **which block fits which content shape**, never a mandatory ordered section — no block here is owed by
position, only by what the content *is*. Match the shape, reach for the block:

- **3+ values / metrics** → `metrics-grid`.
- **a comparison** → `comparison-table` (or `comparison` for a two-sided pros/cons).
- **before / after** → `diff-block`.
- **a reasoning chain** → `derivation`.
- **an open boundary** (a gap, an unknown) → `gap-table` (several) or `gap-marker` (one).
- **verbatim source evidence** → `evidence`.
- **quantitative data to visualize** → `chart` (`line` · `sparkline` · `bar` · `scatter` · `slopegraph`).
- **a relation / dependency / flow** → `diagram` (`dag` · `force`); `ascii-diagram` is the zero-dep fallback.

A producer **leads with the blocks its descriptor's `richness.require` names** (`tools/producer_descriptor.py`)
— `map` leads with illustrations (`diagram`, `ascii-diagram`); `plan` leads with framed steps
(`next-steps-grid` / `numbered-card`) and a dependency `diagram`; `discovery` leads with a framing `callout`
— while the **full palette above stays reachable** for whatever else the content owes. Leading is by
**declaration**, not a fixed position: the floor blocks surface first because the form owes them, not because
a section mandates them.

## The context-denial ladder

Each rung sees strictly less than the one before. **Freshness is evidence vs reasoning, not
cites vs no-cites** (ADR-0013): a later rung is denied the *evidence* and the *session* so its
read of the text is fresh, not because it lacks links.

1. **producer** — sees all (briefing + Mundo + session + evidence) **+ its own memory (recall — `skills/_shared/memory.md`)**.
2. **serendipity** — `+briefing +Mundo`, `−session`.
3. **critic** — `−briefing`, `−session`.
4. **reviewers** — content + cites **only** (evidence, session, briefing all denied).
5. **publisher** — the final Artefato **only**.

The reviewers are blind by evidence-and-session (the blindfold): a **factual claim** must be
re-sourceable from its cite or it is struck — but a **reasoning step** (a derivation, an inference
from premises already on the page) is judged by its **internal validity**, not by a cite. If that
reasoning is useful but contestable, the reviewer marks a non-blocking `risk`; the producer can do
fresh grounding and rewrite it, or keep it as `accepted_risks` with a visible tag. The producer's
thinking-out-loud is never amputated (the depth dims reward it; ADR-0013 — freshness is
evidence-vs-reasoning, not cites-vs-no-cites). The publisher writes the final Artefato atomically with its kernel — it
needs nothing but the finished thing. The close that runs the reviewers and the publisher lives
at the skill's exit, defined in `skills/_shared/pipeline.md`.
