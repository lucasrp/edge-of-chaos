# The shared producer scaffold

The producer-loop every producer-skill inherits (ADR-0012). A producer-skill — `report`,
`map`, `research`, `plan`, … — does **not** write its own loop. It inherits this scaffold,
supplies the theme and the producing cognition, and fills three **role-defined slots**. The
loop structure and the context-denial ladder are the same for every producer; only the slot
*content* differs.

This scaffold is **non-procrusto** by design: it names roles, never report-specifics. A `map`
producing a diagram and a `report` producing prose-and-charts run the **same** scaffold.

## Plenitude — the producer works at full depth; the subagents serve it

The producer's job is **plenitude**: fed by its subagents, it develops the theme to its full
depth — concrete, derived from first principles, tailored to the mentee, carrying what they did
not already know. The multi-agent structure is **leverage for depth**, never a press that boils
the work down: the subagents exist to **free the producer to go deep** (offload the grunt-work,
develop facets in parallel, probe the gaps), not to compress the result into a single bite.
Synthesis-to-a-bite is a **failure** of plenitude, not a success of concision — a thin honest
summary that cut the thinking did not do the job. The producer is **free** to wield its subagents
however it judges best toward that depth; the slots below name *roles*, not a fixed delegation shape.

## The three slots are role-defined, NOT report-defined

The scaffold defines three slots by their **role** in the loop. It says what the role *does*,
never what a particular report-form *is*:

- **`gather-grounding`** — loop1's role: the producer **freely delegates to its subagent fleet**
  to reach plenitude. **But recall before you research** (`skills/_shared/memory.md`): first pull the
  subgraph your theme already touches from the edge's own memory, so explorers chase what is *missing*,
  not what you already published. Gathering grounding is one use — explorers go out and bring back evidence;
  **decomposing the theme into facets developed in parallel** is another, as is probing the gaps a
  first pass exposes. The producer wields the subagents **as it judges best**, within the runtime's
  concurrency cap — the scaffold offers the affordance and per-form *guidance*, **never a fixed
  delegation shape**. The slot says "gather grounding," not "fetch this URL." Whether an explorer
  reads a paper, a repo, or a graph thread is the **producer skill's** decision. *How* an explorer reaches a world source is
  the same for every producer and is **never a per-source primitive** (ADR-0001): read the source's
  `via` spec in `agent.yaml` plus `state/source-roadmap.md` and call it **agentically** — the
  install's keys are already loaded. There is no `libexec/` primitive and there never will be; an
  explorer that cannot ground reports *which key it could not work*, never "a primitive is missing"
  and never waits for one to be built.
- **`converge`** — loop2's critic role: decide whether the artefato is **developed to plenitude**
  and ready to ship — the arc whole, the depth present and derived, tailored to the mentee, carrying
  what they did not already know. Converge means *judge the development is complete*, **never** *cut
  to a single point*. The slot says "converge," not "compress."
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
from premises already on the page) is judged by its **internal validity**, not by a cite, so the
producer's thinking-out-loud is never amputated (the depth dims reward it; ADR-0013 — freshness is
evidence-vs-reasoning, not cites-vs-no-cites). The publisher writes the final Artefato atomically with its kernel — it
needs nothing but the finished thing. The close that runs the reviewers and the publisher lives
at the skill's exit, defined in `skills/_shared/pipeline.md`.
