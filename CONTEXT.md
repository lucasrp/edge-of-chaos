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
**Exists to move or confirm the Direction**: it ends on the decision not yet made and
**declares candidate steers** — to open a proposed thread, or to confirm/challenge an existing
one — which the **grill** consolidates into Direction's `proposed` tier (the Artefato never
writes Direction itself). The candidate is **optional**: an Artefato may only deepen a
**Knowledge cluster** (pure domain insight, no steer). **Transient**: it cools and is prunable —
the durable knowledge it distills lives in the **cluster**, the steer it proposes in
**Direction**. Not a permanent wiki page.
_Avoid_: report (a skill name), output, post

**Hypothesis**:
Something the edge supposed (mined or inferred) and not yet confirmed (`assumed`). The
edge **works naturally** with hypotheses — the abundant, cheap tier.
_Avoid_: guess, draft

**Curated**:
Knowledge consolidated by the mentee (`confirmed`/`corrected`). **Prioritized** over a
hypothesis in every read-model. **Exempt from passive aging** (it does not cool by going unread
or unreinforced) but **actively retirable by Voz** — a strategic realignment can supersede it.
Only the mentee retires curated; passive forgetting never does.
_Avoid_: validated, final, approved

**Consolidação de hipóteses / Hypothesis consolidation**:
Promoting hypothesis → curated. The **inward** half of what `/grill-me` (active) and the
per-report comment (async) do — it keeps the edge's model accurate, but is not the whole of
the grill, which also **generates outward orientation** for the mentee (see Convergence).
Does not drain the hypothesis tier; consolidates what carries **harm potential**.
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
own bounded knowledge, not deltized like the inputs. The durable pages are **rendered projections
of the graph** (ADR-0005), not hand-edited documents. This is what **replaces the code**:
orientation that used to be scaffolding now lives here.
_Avoid_: knowledge base, RAG

**Knowledge cluster**:
The wiki's **emergent durable page** — a unit of knowledge (mentee or domain) that
accumulates hypothesis + curated, **grown** from reading and grilling, never declared.
The graph **proposes** clusters (Graphiti communities, algorithmic); the **grill curates**
them — directing a fact into a cluster, spawning a new one, or merging — **by harm potential**,
not exhaustively. Materializes as a **thread**: a **rendered projection** of the cluster's graph
(ADR-0005), never hand-edited. Artefatos hang off it. Not the wiki's *only* durable page — see
**Standing page**.
_Avoid_: topic, tag

**Standing page**:
A durable wiki page that is **declared then refined**, not grown — seeded from `agent.yaml`
and sharpened by the onboarding grill. Three today: **Direction**, **Idiom**, **Source
roadmap**. These are what the rebuild moves out of code/config and **into the wiki** (the
project's "replace the code with the wiki").
_Avoid_: config, settings, scaffolding

**Direction**:
The mentee's current direction the edge aligns its work to — phase, priorities, constraints,
what they are working toward now. **Two tiers, mirroring hypothesis/curated**: **proposed** —
the grill's strategic achados (the open thread, the next bet, the decision not yet made; the
**grill consolidates** these) — and **set** — what the mentee has ratified (Voz owns it, their
correction always wins). The rendered standing page shows **both tiers**; a proposed thread the
mentee ratifies is **promoted to set** (superseding it), the same promotion the grill runs on
knowledge. **Co-produced** but Voz-owned. A **standing page**, projected from the log
(ADR-0006), never hand-edited. The old `config/strategy.md`, as wiki.
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
when Lint exposes the error and the mentee resolves it. **Two-way**: converging means both
**promoting** what is now true and **retiring** what is now false — a grill that follows a
strategic realignment (a `Direction` change) has a wide blast radius and can be **net-subtractive**.
Accuracy is **not the end**: the edge converges so it can **orient the mentee** — a precise model
is the precondition for worthwhile mentorship, not a goal in itself.
_Avoid_: sync, alignment

## Knowledge intake / Entrada de conhecimento

> Three legs feed the llm-wiki. Named by the **subject** the knowledge comes from, not
> by the mechanic. The axis that separates them: **world vs observed vs directed**.

**Mundo / World**:
The external field the edge pulls from (arXiv, HN, EXA, Twitter). Unverified claims about
the world — pass the adversarial judge before they compose into the wiki.
_Avoid_: coleta, source, busca

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

**Corpus**:
The collection of **content the agent itself created** — its published Artefatos (a fold of the log's
`artefato.published` events). The edge's **own** body of work, the **reflexive** complement to the
three legs: Mundo/Atividade/Voz are about the mentee and the world; the corpus is the **edge's own
steps**. Per-install (each install's own work, isolated). Autonomous beats are excluded from the
Atividade sweep precisely because their output lands **here** instead. It feeds the briefing's third
part (the agent's last steps, related to the mentee's Atividade).
_Avoid_: obra, output, log (the corpus is the created content, not the raw event log)

**Recap**:
The **projection of the corpus** shown as the briefing's third part — the agent's recent steps and
their *why*, correlated at compose-time to the mentee's current **Atividade**. A **projection**
(ADR-0006), not a stored doc: the corpus↔Atividade relation is **synthesized fresh each load**
(orientation must be current, never frozen at publish-time; the Artefato's stored `cites`/`distills`
are provenance, not the relation). PT gloss: *informativo / relatório*.
_Avoid_: report (the Artefato / `ed-report` skill), digest (the rolling chat-digest), bulletin

**Source feedback**:
A **two-tier** relevance signal over the sources that fed an Artefato — **Mundo** (exa/X/HN/arXiv) **and
Atividade** (GitHub commits/PRs, docs), e.g. *"this commit was relevant to this report"*. It takes the
edge's **universal hypothesis→curated shape** (cf. Knowledge clusters, Direction) — one curation act (the
grill) governs all three:
- **hypothesis tier — mechanical, no agent/mentee load**: the cheap abundant signal — intrinsic citation
  (the agent names sources as part of writing a cited Artefato) + **outcome credit** (Voz ratification of a
  `proposes` / engagement, propagated back through `cites`, MemQ-style) + retrieval-use detection (AgentOS
  `RetrievalFeedbackSignal`). Machine-generated, contradiction-prone, **never agent self-rating**.
- **curated tier — the grill distills the mentee's opinion**: *"the mentee values X in reports because of
  Y."* Voz-grounded and reasoned; **re-ranks the Source roadmap with curated authority**; exempt from
  passive aging, retirable only by Voz. The grill promotes hypothesis→curated **by harm potential**, the
  same act it runs on knowledge and Direction — so the reasoning lands here without new burden on the agent.
This closes the artifact→human-outcome credit the 2026 survey (AgentOS `RetrievalFeedbackSignal` —
mechanical but overlap-proxy; MemQ Q-value over the provenance DAG) found **unbuilt** — outcome-grounded.
_Avoid_: rating, star-score, self-scoring (the hypothesis tier is mechanical; judgment lives in the curated tier)

**Delta**:
What's new in the **inputs** — the world the edge ingests (Mundo, Atividade, Voz) — since the
last consolidation. The world is too big to re-scan whole, so the edge reads the inputs
incrementally, anchored at the previous beat's consolidation point. **The delta is over the
world, never over the wiki**: the edge's own accumulated knowledge is read *in full* (size
permitting), not deltized — only the inputs are. **Source-agnostic**: a git tree, a folder of
docs, a transcript — never narrowed to one surface's mechanics. Its role is **orientation, not
evidence**: it stays light and points the beat at fresh material so a theme can be chosen.
Depth comes afterward — once a theme is picked, **research reads the actual documents directly,
including old ones**, unbounded by the delta. **Never a precondition**: the beat works from the
**wiki** alone when the delta is empty — the delta enriches a beat, it does not gate one.
Sufficient **only if state consolidation is faithful** — the last consolidation is the point it
reconciles against.
_Avoid_: changeset, watermark, cursor (do not narrow it to a git changeset; do not deltize the
wiki; do not let the delta become the evidence — it orients, research deepens; do not let it gate
the beat)

## Curation / Curadoria

> Two **orthogonal, unmerged** processes move pages between strata (L1/L2 split, like the
> digest). They act on two orthogonal axes: **tier** (hypothesis vs curated) and
> **temperature** (hot/cold/archived).

**Envelhecimento / Aging**:
Mechanical curation (L1, every beat) on the **temperature** axis. Two signals feed it.
**Consumption** (steady-state): the wiki offers the whole list each beat, the edge pulls only
what it needs, and that reach keeps a page hot; offered-but-unconsumed cools, then archives, and
a cold page pulled back re-warms. **Reinforcement-recency** (cold-start, from provenance): when no
new episode has touched a page — it catches the *valid-but-abandoned* that a contradiction never
invalidates and consumption cannot see before beats accrue. Touches only the **hypothesis** tier;
curated is exempt. **Archives, never deletes** (raw stays non-lossy).
_Avoid_: decay, ttl, eviction

**Lint**:
Semantic curation (L2, LLM, periodic): detects contradiction / superseded / orphan / gap.
**Resolves only the rule-decidable** (`curado > hipótese`, recency) and **escalates the
residual to Voz** by harm potential. Detects; the rule or the mentee resolves — never by
judgment in code. The detector half of `Convergence`.
_Avoid_: validator, linter, cleanup

## Beat lifecycle / Ciclo do beat

> A **dispatch** runs as cognitions in fresh contexts (ADR-0004), inside the single dispatch
> (ADR-0003). The heartbeat beat is the maximal case (three subagents around one judgment loop);
> a standalone skill wraps fewer. Named so each stays faithful to one task without competing for
> the main window.

**Dispatch**:
Any ed-skill invocation — the heartbeat's `/ed-beat`, or a manual `/ed-report`, `/ed-grill`, etc.
run in a live session. **`/ed-beat` is just a shell**: it holds no privileged lifecycle. **Every
dispatch observes the same effects** — the digestion sweep at entry (**Assemble**) and persistence
at close — so a **manual `/ed-report` dispatch leaves the same durable residue as the heartbeat
beat**; they differ only in the cognition wrapped (a full judgment loop vs a single Artefato),
never in the lifecycle around it. The lifecycle belongs to the **dispatch**, not to the beat skill.
_Avoid_: beat (it is one shell, not the lifecycle), run, invocation

**Assemble / Consolidação prévia**:
The opening primitive (**blocking**). It runs the **digestion sweep to currency** — an idempotent,
cursor-guarded pass over the **transcript store** (every operator session since the cursor, *not
just beats*) that runs the **full pipeline**: append raw episodes → distil handoffs → run
**zep/Graphiti extraction** (incremental, on the delta) → **re-project** the wiki and **Direction**.
So at every dispatch entry the **non-curated (hypothesis / `proposed`) tier is current — ambiguous
and `contested` items included** (flagged, not hidden). It **defers only curation** to the grill:
promotion (hypothesis→curated, `proposed`→`set`) and cleanup of the ambiguous. **The Zep-failure
guard is the tier boundary**: extraction only ever writes the **non-curated** tier, never asserts a
vent as a curated decision. Then it hands the loop a **state digest**. **Keyed on the store, not on
any skill**: a session that ran no ed skill is still brought current at the next trigger.
**Triggers** (same idempotent sweep, pluggable): the heartbeat dispatch, **any standalone ed skill
at entry**, and `/load`. The loop blocks until it lands.
_Avoid_: load (the trigger, not the primitive), context-gather, preflight

**Consolidate / Consolidação posterior** *(dissolved — ADR-0008)*:
The old closing subagent is **absorbed**: *archive raw* → the pull-at-open **digestion sweep**
(Assemble); *fan/curate the pages* → the **grill** (Hypothesis consolidation); *the handoff
document* → gone (durable delta = the swept log; strategy = **Direction**). No async close step,
no `consolidate→assemble` race. The only close-time act is the thin **intent kernel** breadcrumb,
by whoever lived the session. The word **consolidate** now means only **Hypothesis consolidation**
(the grill's curation), never a lifecycle close.
_Avoid_: postflight, save, the 1905-line consolidate-state, posterior close subagent

**Briefing**:
The composite orientation the edge **presents to the agent every time it is loaded to act** (at
dispatch start, and on `/load`). A **collection of information**, in three parts:
1. the **Knowledge clusters** — what the edge knows;
2. the **Direction** — the strategic steer (both tiers);
3. the **Recap** (PT: *informativo*) — **a projection of the corpus**: the agent's **own last steps**,
   what it did and why, correlated at compose-time to **how it relates to the mentee's Atividade**.
Composed from projections (clusters ← graph · Direction ← log · Recap ← corpus) — the *oriented* read,
not raw state. It is what
`assemble` hands the loop. The old `State digest` / `briefing.md`, now first-class. Distinct from the
**handoff** (the raw intent-kernel breadcrumb): the briefing is the composed orientation; the handoff
is one pragmatic input to it.
_Avoid_: state digest (the old mechanical name — retired), dump, context pack

**Intent kernel**:
The agent's **intent** — ~3 lines: what is open, the next bet, the *why* behind the work — the
**pragmatic layer no cold reader recovers**. **Mandatory metadata on edge work** (CONTRACT C3): every
dispatch that produces an Artefato emits an **`intent.kernel` event** at close — edge work without its
intent is incomplete. It is the durable **why** the **corpus** carries and the **Recap** projects.
Written by whoever lived the session (the loop, or live grilling). (A no-skill *chat* — not edge work —
leaves none; the sweep captures its raw and the grill picks it up.) The tier boundary, not the kernel,
is what stops a vent becoming a curated decision (ADR-0008, the Zep failure).
_Avoid_: summary, notes, handoff (that is the digested delta, not the kernel)
