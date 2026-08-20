# The shared producer scaffold

The producer-loop every producer-skill inherits (ADR-0012). A producer-skill — `report`,
`map`, `research`, `plan`, … — does **not** write its own loop. It inherits this scaffold,
supplies the theme and the producing cognition, and fills three **role-defined slots**. **Theme policy (beats and autonomous producers):** the theme comes from the Pauta's `pauta.proposta` (ADR-0024 — o dente: sem proposta viva não abre Ato-2; read it via `tools/edge-python tools/pauta.py proposta --dispatch-id "$EDGE_DISPATCH_PLAN_ID"`). The PROPOSTA carries tema/forma/faceta/lastro — the producer develops them in its form and never re-chooses the theme. Never seed from open-bet / exp ticket vocabulary. The
loop structure and the context-denial ladder are the same for every producer; only the slot
*content* differs.

This scaffold is **non-procrusto** by design: it names roles, never report-specifics. A `map`
producing a diagram and a `report` producing prose-and-charts run the **same** scaffold.

## The writer's identity — seja Feynman nesse sentido

Whoever writes the artefato: **seja Feynman nesse sentido** — the NAME is the pointer (it fires
the trained attractor better than pages of rule), scoped fine: the mind that does not fool
itself, that explains simple-and-complete, that names what it does not know. The taste to point
at lives in the cânone tattoo (`memory/canone.md` — carried in every briefing): when in doubt,
be like those; the anti-cânone names the smell of the hollow. The persona stays in the WRITER
only — the production gates remain impersonal (concepts, never the persona; reviewer≠asserter).

## The production duty — the genus (one path; no knob)

There is **one** production path. It is a **genus property of the Artefato**, not a knob, not a
menu of sizes, not a depth field, not a template of headings. Length is **emergent**. There is no
word-count floor and no word-count target. A tight lead that stands alone is **not done**.
Synthesis-to-a-bite is a **failure** for the genus.

### Contrato (verbatim)

Estas frases são o contrato. Sem exemplos. Sem instâncias. Sem bibliografia.

- ensina alguém muito inteligente que não viveu a sessão
- todo termo na primeira vez
- o nome da ferramenta pelo que ela faz, não pelo que ela é
- deriva antes de ir buscar fora
- score 5 = um estranho entende tudo
- o mundo é importante: contextualizar o trabalho com o mundo

### Plenitude

**Plenitude is those moves developed** — developed until a stranger who did not live the session
can restate the claim and the why from this page alone, and can place the work in the world.

Plenitude is **not** cover-every-facet. Facets that are not on the derivation path may stay out.
No mandatory Glossary. No mandatory "O que não sei" H2. No word-count floor. No depth knob.

The writer may look things up for *this* page after deriving. Those names are lastro of the page,
not of this genus. Do not invent citations.

### The four load-bearing moves (cognition order, not typography)

1. **DOOR** — name the object before the scoreboard. *todo termo na primeira vez. o nome da
   ferramenta pelo que ela faz, não pelo que ela é.* The first block must leave a stranger able
   to retell what world this is, what the object is, what a unit is, and what the printed claim
   alleges. A slug is not a door. Infering "the operator already knows" from a prior dialogue is
   out of this genus. The page is the only briefing the reader gets.

2. **DERIVE IN THE OPEN** — *deriva antes de ir buscar fora.* Show the thinking, not the
   conclusion: charitable hypothesis, then where it breaks, then what the disk forces. Gaps
   emerge from reasoning; they are not a pre-allocated "O que não sei" heading. Facets not on
   this path stay out.

3. **THIS PAGE CARRIES** — *ensina alguém muito inteligente que não viveu a sessão. score 5 =
   um estranho entende tudo.* If a stranger cannot restate the claim and the why from this page
   only, the piece failed. Lineage ≤ one sentence. IDs are not a scene. No mandatory H2 skeleton.
   Calibrate to a stranger, not to an operator.

4. **O MUNDO É IMPORTANTE** — *contextualizar o trabalho com o mundo.* After the derivation,
   bring in enough of the world that a stranger can place the work. This is not a bibliography
   H2 and not a dump of papers. If a stranger can retell the local plot and still has no world
   to hang it on, the page failed.

PASS only if: (a) the first block is a door; (b) the derivation is visible; (c) claim and why
can be restated from this page alone — score 5; (d) the work is contextualized with the world.
FAIL if the page opens on a parable or ID plate that already assumes the object; FAIL if unused
facets were padded in; FAIL if the reader must have lived the session; FAIL if the page never
leaves the local idiom.

The producer is **free** to wield its subagents however it judges best toward this duty; the
slots below name *roles*, not a fixed delegation shape. Skills execute this file. They do not
own it, and they do not restate assume-known.

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
- **`converge`** — loop2's critic role: decide whether the artefato has **developed the genus
  moves** and is ready to ship — door in the first block, derivation visible, a stranger who
  did not live the session can restate claim and why (score 5), the work placed in the world.
  Converge means *judge that plenitude*, **never** *cut it to a bite*, and never *cover every
  facet*. A standalone lead is not a ship condition. The slot says "converge," not "compress."
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
  pull the subgraph your theme touches (its clusters, prior Artefatos, open bets). Recall is cheap and
  owned, the world expensive and fuzzy. Recall *feeds* the derivation — what was already established,
  in one sentence. It does not license skipping the door. A stranger still has to be taught from this
  page alone.
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
