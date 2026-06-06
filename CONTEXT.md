# Obrigado. Obrigado. Obrigado. edge (new) — glossary

The ubiquitous language of the reborn edge: a **mentor** that knows the mentee and the
domain well, and produces content worth reading. Built fresh (not edited from the old
one) so it can be **confronted** with the old glossary (`~/edge/CONTEXT.md`, today a
machine-language). Grows as concepts evolve (via /pocock-grill-with-docs).

> Language only. Invariants live in `CONTRACT.md`, decisions in `docs/adr/`.

## Language

**Mentee**:
The person the edge serves — their real work is the subject. The edge knows them from
what they do (code, docs, words), not from supposition.
*Avoid*: user, client, operator

**Domain**:
The field the mentee works in. The edge must know it deeply to have substance.
*Avoid*: area, topic, field

**Worthwhile content**:
The intersection: deep domain insight **applied to the mentee's live work**. Domain
alone is generic; mentee alone is shallow.
*Avoid*: report, output, post

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
*Avoid*: report (a skill name), output, post

**Hypothesis**:
Something the edge supposed (mined or inferred) and not yet confirmed (`assumed`). The
edge **works naturally** with hypotheses — the abundant, cheap tier.
*Avoid*: guess, draft

**Curated**:
Knowledge consolidated by the mentee (`confirmed`/`corrected`). **Prioritized** over a
hypothesis in every read-model. **Exempt from passive aging** (it does not cool by going unread
or unreinforced) but **actively retirable by Voz** — a strategic realignment can supersede it.
Only the mentee retires curated; passive forgetting never does.
*Avoid*: validated, final, approved

**Consolidação de hipóteses / Hypothesis consolidation**:
Promoting hypothesis → curated. The **inward** half of what `/grill-me` (active) and the
per-report comment (async) do — it keeps the edge's model accurate, but is not the whole of
the grill, which also **generates outward orientation** for the mentee (see Convergence).
Does not drain the hypothesis tier; consolidates what carries **harm potential**.
"Afinamento" is the same loop when the object is the mentee's **language** (Idiom).
*Avoid*: approval, review, afinamento (as a separate concept)

**Harm potential**:
The consolidation priority: source ambiguity × cost of acting wrong. Decides what spends
the mentee's scarce attention.
*Avoid*: urgency, score

**llm-wiki**:
The edge's knowledge, held as two kinds of durable page — **Knowledge clusters** (emergent,
grown) and a few **Standing pages** (declared then refined: Direction, Idiom, Source roadmap)
— plus cross-references, holding both hypothesis and curated. An **Artefato** is a transient
delivery (a Query result), never a page. Read **in full when small** (the briefing's entry read);
**navigated as a graph beyond that budget** (the **Cortex**) — the edge's own bounded knowledge,
not deltized like the inputs. The durable pages are **rendered projections
of the graph** (ADR-0005), not hand-edited documents. This is what **replaces the code**:
orientation that used to be scaffolding now lives here.
*Avoid*: knowledge base, RAG

**Cortex**:
The edge's whole navigable knowledge as one connected graph — the **mind** it thinks *in*. Everything
projects into it: intake → episodes/clusters (extracted), plus the **asserted** edges (Direction, curated,
**corpus**, artifact refs, source signals) — one surface where it all connects (artifact retrieval =
traverse to the reference node, fetch the blob). **Navigate the Cortex, replay the log**: the **log** is
the record / source of truth (replayed for time & versioning, un-navigable by design); the Cortex is the
navigable projection (ADR-0006/0010). The **briefing** seeds entry points; the edge *navigates* it on
demand — the read that **scales past full-read** (no token-budget wall). Trust is legible per edge:
**asserted** (folds from the log) faithful, **extracted** (Graphiti) hypothesis. A **declared** capability
(agent.yaml / Source roadmap), used like github/exa — for recall of its own knowledge, **never
re-ingested** (recall, not a source — the self-reference guard). The **llm-wiki** pages are renders of it.
*Avoid*: RAG, retrieval, top-k, vector DB, memory store (recall is navigation of own knowledge, not a fetch)

**Knowledge cluster**:
The wiki's **emergent durable page** — a unit of knowledge (mentee or domain) that
accumulates hypothesis + curated, **grown** from reading and grilling, never declared.
The graph **proposes** clusters (Graphiti communities, algorithmic); the **grill curates**
them — directing a fact into a cluster, spawning a new one, or merging — **by harm potential**,
not exhaustively. Materializes as a **thread**: a **rendered projection** of the cluster's graph
(ADR-0005), never hand-edited. Artefatos hang off it. Not the wiki's *only* durable page — see
**Standing page**.
*Avoid*: topic, tag

**Standing page**:
A durable wiki page that is **declared then refined**, not grown — seeded from `agent.yaml`
and sharpened by the onboarding grill. Three today: **Direction**, **Idiom**, **Source
roadmap**. These are what the rebuild moves out of code/config and **into the wiki** (the
project's "replace the code with the wiki").
*Avoid*: config, settings, scaffolding

**Direction**:
The mentee's current direction the edge aligns its work to — phase, priorities, constraints,
what they are working toward now. **Two tiers, mirroring hypothesis/curated**: **proposed** —
the grill's strategic achados (the open thread, the next bet, the decision not yet made; the
**grill consolidates** these) — and **set** — what the mentee has ratified (Voz owns it, their
correction always wins). The rendered standing page shows **both tiers**; a proposed thread the
mentee ratifies is **promoted to set** (superseding it), the same promotion the grill runs on
knowledge. **Co-produced** but Voz-owned. A **standing page**, projected from the log
(ADR-0006), never hand-edited. The old `config/strategy.md`, as wiki.
*Avoid*: strategy, plan, goals, alignment (collides with Convergence)

**Idiom**:
The mentee's own language — their terms and meanings, kept so the edge frames work in their
words. A **standing page**, the **Voz** glossary. The old `memory/operator-idiom.md`, as wiki.
*Avoid*: jargon, terminology

**Source roadmap**:
The registry of **keys** the edge reads — a **standing page**. A **key is a locator, blind to subject**:
the **same source can feed Mundo and/or Atividade** (GitHub as the mentee's repo = Atividade; GitHub as
the ecosystem = Mundo) — **many-to-many**, the subject is a **lens on the read, not a property of the
source**. Sources therefore unify on **access** (give the key, read agentically — ADR-0001) and on
**relevance** (one **Source feedback**, spanning both). What does **not** unify is the **subject**: it
rides as a **tag on the yield** (world vs mentee), because **Worthwhile content = Mundo ∩ Atividade** needs
it. The old source bindings, as wiki.
*Avoid*: config, bindings, feeds, per-source primitive (a key is a locator, not a leg)

**Convergence**:
The edge's model (wiki + mentee glossary) matching the mentee's reality. The loop closes
when Lint exposes the error and the mentee resolves it. **Two-way**: converging means both
**promoting** what is now true and **retiring** what is now false — a grill that follows a
strategic realignment (a `Direction` change) has a wide blast radius and can be **net-subtractive**.
Accuracy is **not the end**: the edge converges so it can **orient the mentee** — a precise model
is the precondition for worthwhile mentorship, not a goal in itself.
*Avoid*: sync, alignment

## Knowledge intake / Entrada de conhecimento

> Three legs feed the llm-wiki. Named by the **subject** the knowledge comes from, not
> by the mechanic. The axis that separates them: **world vs observed vs directed**.

**Mundo / World**:
The external field the edge pulls from (arXiv, HN, EXA, Twitter). Unverified claims about
the world — pass the adversarial judge before they compose into the wiki.
*Avoid*: coleta, source, busca

**Atividade / Activity**:
What the mentee **does** — code, commits, docs, transcripts, whatever they leave. **Observed,
not directed**: it shows what the mentee actually does, not something said to the edge. The
mentee need not even work in Claude Code. Yields `hypothesis` about domain and intent. The
reborn `signals` leg, scoped to the mentee.
*Avoid*: obra, work, rastro, trace, ingest, signals, operator pressure

**Voz / Voice**:
What the mentee **directs** at the edge — correction and language. **Directed, not
observed**: authored and highest priority ("a correção sempre ganha"). Subsumes language
(Idiom) and correction. Keeps the mentee glossary.
*Avoid*: operator pressure, feedback, pressão

**Briefing**:
The orientation presented to the agent at **every dispatch** (and `/load`) — **Memento's tattoo**. The
protagonist of *Memento* has anterograde amnesia, so he tattoos the load-bearing facts onto his skin and
trusts nothing that isn't inscribed. The briefing is that tattoo for a zero-memory agent: it must carry
**everything** needed to orient and hold continuity, because the agent acts on nothing it cannot read here.
Three **projections** (ADR-0006/0009) — **Knowledge clusters** (← graph), **Direction** (← log), and the
**Recap** (← corpus) — plus the **source orientation**: the **declared roster** (← Source roadmap — the
sources and what each does) as the **floor (never blank)**, with **Source feedback** layered on as it
accrues. Composed by **Assemble** at compose-time;
**supersedes the old "state digest."** The load-bearing lines (the curated Direction, what is open / the
next bet, the source yield) are **deterministically inscribed from the log** — never left to the LLM to
remember; only the Recap is synthesized fresh. Tier-0 composes from the log alone (clusters degrade where
there is no graph).
*Avoid*: state digest, dump, context (the briefing is curated orientation, not a raw dump)

**Corpus**:
The collection of **content the agent itself created** — its published Artefatos (a fold of the log's
`artefato.published` events). The edge's **own** body of work, the **reflexive** complement to the
three legs: Mundo/Atividade/Voz are about the mentee and the world; the corpus is the **edge's own
steps**. Per-install (each install's own work, isolated). Autonomous beats are excluded from the
Atividade sweep precisely because their output lands **here** instead. It feeds the briefing's third
part (the agent's last steps, related to the mentee's Atividade).
*Avoid*: obra, output, log (the corpus is the created content, not the raw event log)

**Recap**:
The **projection of the corpus** shown as the briefing's third part — the agent's recent steps and
their *why*, correlated at compose-time to the mentee's current **Atividade**. A **projection**
(ADR-0006), not a stored doc: the corpus↔Atividade relation is **synthesized fresh each load**
(orientation must be current, never frozen at publish-time; the Artefato's stored `cites`/`distills`
are provenance, not the relation). PT gloss: *informativo / relatório*.
*Avoid*: report (the Artefato / `ed-report` skill), digest (the rolling chat-digest), bulletin

**Source feedback**:
A **two-tier** relevance signal over the sources that fed an Artefato — **Mundo** (exa/X/HN/arXiv) **and
Atividade** (GitHub commits/PRs, docs), e.g. *"this commit was relevant to this report"*. It takes the
edge's **universal hypothesis→curated shape** (cf. Knowledge clusters, Direction) — one curation act (the
grill) governs all three:

- **hypothesis tier — mechanical, no agent/mentee load**: the cheap abundant signal — intrinsic citation
(the agent names each source **and the snippet it used** as it writes a cited Artefato) + **embedding
attribution** (cosine of each cited snippet vs the Artefato body — cheap, `RetrievalFeedbackSignal`-style,
one OpenAI embedding call) + **outcome credit** (Voz ratification of a `proposes` / engagement, propagated
back through `cites`, MemQ-style). Machine-generated, contradiction-prone, **never agent self-rating**.
**Stored as `source.signal` events in the Tier-0 log** (the *score*, not vectors — no separate DB, no
vector store) and projected into the graph; the **grill consults it via `grill_lint`** (per-source yield →
a hypothesis agenda item). **Never used alone** — fused with the mentee's voiced opinion in the curated tier.
- **curated tier — the grill distills the mentee's opinion**: *"the mentee values X in reports because of
Y."* Voz-grounded and reasoned; **re-ranks the Source roadmap with curated authority**; exempt from
passive aging, retirable only by Voz. The grill promotes hypothesis→curated **by harm potential**, the
same act it runs on knowledge and Direction — so the reasoning lands here without new burden on the agent.
This closes the artifact→human-outcome credit the 2026 survey (AgentOS `RetrievalFeedbackSignal` —
mechanical but overlap-proxy; MemQ Q-value over the provenance DAG) found **unbuilt** — outcome-grounded.
*Avoid*: rating, star-score, self-scoring (the hypothesis tier is mechanical; judgment lives in the curated tier)

**Delta**:
The **orientation of what's new in the world** the edge ingests (Mundo / Atividade) — a **noun**, the
yield of the agent **updating itself** (the act stays a lowercase verb; the Idiom names the thing, not the
act). **Discretionary, not deterministic**: the edge does **not** "grab everything since the last
consolidation" — the consolidation point is a **reference horizon** (it knows where it last looked), **not
a mandate to exhaust**; within it the agent uses judgment about what is worth surfacing (agentic, never a
per-source primitive — ADR-0001). **The deterministic completeness floor is the sweep** (cursor-guarded, in
**Assemble**), **not the delta** — the world was never exhaustible anyway. **Over the world, never over the
wiki**: the edge's own knowledge is navigated in full (the **Cortex**), not deltized — only the world is.
Its role is **orientation, not evidence**: light, it points; **research deepens later**, reading the actual
documents directly (incl. old ones), unbounded by it. **On-demand, not a precondition**: it is **not** a
mandatory beat-open fan-out — the agent **wakes to itself first** (**Waking**: briefing + Cortex) and pulls
the world **only when it judges it needs to**; the beat works from the **wiki** alone when nothing is
pulled. It enriches a beat; it never gates one.
*Avoid*: changeset, watermark, cursor (not a git diff; do not deltize the wiki; it orients, research
deepens; it does not gate the beat), the act of updating (Delta is the yield; "update" is the verb)

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
*Avoid*: decay, ttl, eviction

**Lint**:
Semantic curation (L2, LLM, periodic): detects contradiction / superseded / orphan / gap.
**Resolves only the rule-decidable** (`curado > hipótese`, recency) and **escalates the
residual to Voz** by harm potential. Detects; the rule or the mentee resolves — never by
judgment in code. The detector half of `Convergence`.
*Avoid*: validator, linter, cleanup

## Beat lifecycle / Ciclo do beat

> A **dispatch** runs as cognitions in fresh contexts (ADR-0004), inside the single dispatch
> (ADR-0003). The heartbeat beat is the maximal case (three subagents around one judgment loop);
> a standalone skill wraps fewer. Named so each stays faithful to one task without competing for
> the main window.

**Dispatch**:
Any ed-skill invocation — the heartbeat's `/ed-beat`, or a manual `/ed-report`, `/ed-grill`, etc.
run in a live session. `**/ed-beat` is just a shell**: it holds no privileged lifecycle. **Every
dispatch observes the same effects** — the digestion sweep at entry (**Assemble**) and persistence
at close — so a **manual `/ed-report` dispatch leaves the same durable residue as the heartbeat
beat**; they differ only in the cognition wrapped (a full judgment loop vs a single Artefato),
never in the lifecycle around it. The lifecycle belongs to the **dispatch**, not to the beat skill.
*Avoid*: beat (it is one shell, not the lifecycle), run, invocation

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
*Avoid*: load (the trigger, not the primitive), context-gather, preflight

**Consolidate / Consolidação posterior** *(dissolved — ADR-0008)*:
The old closing subagent is **absorbed**: *archive raw* → the pull-at-open **digestion sweep**
(Assemble); *fan/curate the pages* → the **grill** (Hypothesis consolidation); *the handoff
document* → gone (durable delta = the swept log; strategy = **Direction**). No async close step,
no `consolidate→assemble` race. The only close-time act is the thin **intent kernel** breadcrumb,
by whoever lived the session. The word **consolidate** now means only **Hypothesis consolidation**
(the grill's curation), never a lifecycle close.
*Avoid*: postflight, save, the 1905-line consolidate-state, posterior close subagent

**Briefing**:
The composite orientation the edge **presents to the agent every time it is loaded to act** (at
dispatch start, and on `/load`). A **collection of information**, in four parts:

1. the **Knowledge clusters** — what the edge knows;
2. the **Direction** — the strategic steer (both tiers);
3. the **Recap** (PT: *informativo*) — **a projection of the corpus**: the agent's **own last steps**,
  what it did and why, correlated at compose-time to **how it relates to the mentee's Atividade**.
4. the **source orientation** — the **declared roster** of sources (← Source roadmap), **never blank**,
  with **Source feedback** layered on as it accrues.

Composed from projections (clusters ← graph · Direction ← log · Recap ← corpus · sources ← Source roadmap)
— the *oriented* read,
not raw state. It is what
`assemble` hands the loop. The old `State digest` / `briefing.md`, now first-class. Distinct from the
**handoff** (the raw intent-kernel breadcrumb): the briefing is the composed orientation; the handoff
is one pragmatic input to it.
*Avoid*: state digest (the old mechanical name — retired), dump, context pack

**Intent kernel**:
The agent's **intent** — ~3 lines: what is open, the next bet, the *why* behind the work — the
**pragmatic layer no cold reader recovers**. **Mandatory metadata on edge work** (CONTRACT C3): every
dispatch that produces an Artefato emits an `**intent.kernel` event** at close — edge work without its
intent is incomplete. It is the durable **why** the **corpus** carries and the **Recap** projects.
Written by whoever lived the session (the loop, or live grilling). (A no-skill *chat* — not edge work —
leaves none; the sweep captures its raw and the grill picks it up.) The tier boundary, not the kernel,
is what stops a vent becoming a curated decision (ADR-0008, the Zep failure).
*Avoid*: summary, notes, handoff (that is the digested delta, not the kernel)