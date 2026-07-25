# Waking is a state; the Delta is discretionary; a source is blind to subject; the graph is mandatory

The agent's coming-online (the reborn "pre-flight") is named **Waking** — a *state*, not a mechanic — and is
**briefing + Cortex navigation**, ending at "situated and ready". The **Delta** stops being a deterministic,
mandatory beat-open fan-out and becomes a **discretionary, on-demand** orientation: the agent **wakes to
itself first**, then pulls the world only when it judges it needs to. A **source is a locator blind to
subject** — the same key feeds **Mundo and/or Atividade** (many-to-many) — so sources unify on *access* and
*relevance* while the **subject survives as a tag on the yield**. The **briefing** gains a fourth part: the
declared source roster as a floor that is never blank. Finally the **graph is made mandatory on every
install** — the Cortex is guaranteed, not a Tier-1 luxury — but the **log stays the source of truth and
versioning engine**, so "Tier-0" demotes from a host class to a runtime degrade mode.

## Status

proposed (2026-06-06; Voz ratifies). Refines ADR-0001 (agentic delta), ADR-0004 (beat-open subagents),
ADR-0006 (log-is-truth — reaffirmed under a now-mandatory graph), ADR-0009 (briefing/source-feedback),
ADR-0010 (navigate the Cortex).

## Context

- The reborn **pre-flight** — the agent waking up in a clean context — had **no name** and no clean line
  between its parts. The Idiom names **states, not mechanics** (ADR-0010 kept `Cortex` the noun, `recall`/
  `navigate` lowercase verbs); `pre-flight` is on the `_Avoid_` list, and **`load` is the trigger, not the
  state** (already in the Assemble `_Avoid_`).
- **Delta carried a deterministic mandate** — *"everything new since the last consolidation"* — even though
  ADR-0001 already made it agentic, it is *orientation, not evidence*, and it **never gates a beat**. Its
  "list the keys" step **duplicated the Source roadmap**, and the consolidation-anchor implied a completeness
  guarantee that **actually lives in the sweep** (ADR-0008, cursor-guarded), not in the delta.
- **Mundo and Atividade look like one concept** because they are accessed identically (by key — ADR-0001)
  and evaluated identically for relevance (one **Source feedback** — ADR-0009). But they are the **two halves
  of Worthwhile content** (Mundo ∩ Atividade), and **the same source serves both** (GitHub = the mentee's
  repo *and* the ecosystem).
- The briefing's source section could render **blank** (a fresh source/install has no feedback yet).

## Considered options

- **Name the waking act / call it `load` / `arousal` / keep `pre-flight`.** Rejected: the Idiom names states
  not acts; `load` is the trigger; `arousal` carries an unwanted connotation; `pre-flight` is a banned
  mechanic. **Chosen: `Waking`** (the state), with `wake` as the lowercase verb.
- **Put the Cortex-navigation inside `assemble`.** Rejected: `assemble` is mechanical (read-only subagent,
  one LLM call); **navigating the Cortex is judgment** and must live in the loop's own window. Waking
  **calls** assemble; it is not a step *of* it.
- **Keep the delta deterministic ("grab everything since the cursor").** Rejected: the world is inexhaustible,
  the delta never gates, and completeness already lives in the **sweep**. **Chosen: discretionary**, the
  consolidation point a **reference horizon**, not a mandate.
- **Collapse Mundo/Atividade into one leg** (they're accessed/evaluated the same). Rejected: it kills
  Worthwhile content = the intersection. **Or keep them split by source.** Rejected: one source serves both.
  **Chosen: source blind to subject (many-to-many); the subject is a tag on the yield.**

## Decision

- **Waking** — the state of the agent **coming online** at dispatch-open and on `/load`: **read the briefing**
  (composed deterministically by Assemble) **+ navigate the Cortex** to get situated (the serendipitous half).
  Ends at **situated and ready**; what follows (choose a theme, act) is the caller's, **not** part of Waking.
  A **primitive with multiple triggers** (heartbeat · any ed skill at entry · `/load`) — `load` is the
  **trigger**, Waking the **state**. The briefing half is mechanical (Assemble); the **navigation half is
  judgment** in the loop. The graph is mandatory (see the **Graph mandatory** decision below), so Waking **always** includes Cortex
  navigation; a transient graph outage degrades cleanly to a briefing-only Waking — **runtime resilience, not
  a host class**. `wake` stays a
  lowercase verb. The **loader** / `/load` concept folds in as the operator-triggered Waking.
- **Delta** — a **noun** (the orientation of what's new in the world: Mundo / Atividade), the yield of the
  agent **updating itself** (`update` the lowercase verb). **Discretionary, not deterministic**: the
  consolidation point is a **reference horizon**, not a mandate to exhaust; the **deterministic completeness
  floor is the sweep** (Assemble), not the delta. **On-demand, not a mandatory beat-open fan-out** — the agent
  **wakes to itself first**, pulls the world **only when it judges it needs to**; it **never gates** a beat.
  **Voz leaves the delta's scope** (it is *directed*, captured by the sweep, not "the world").
- **Source** — a **key is a locator, blind to subject**: the same source feeds **Mundo and/or Atividade**
  (**many-to-many**; the subject is a **lens on the read**, not a property of the source). Sources unify on
  **access** (ADR-0001) and **relevance** (one Source feedback — ADR-0009). The **subject survives as a tag on
  the yield** (world vs mentee) because **Worthwhile content = Mundo ∩ Atividade**. **Trust/vetting** (the
  adversarial judge) is an **orthogonal axis** (claim vs fact), *not* the Mundo/Atividade split.
- **Briefing** — gains a **fourth part**, the **source orientation**: the **declared roster** (← Source
  roadmap, what the sources are and what each does) as the **floor (never blank)**, with **Source feedback**
  layered on as it accrues.
- **Graph mandatory** — every install provisions the graph runtime (neo4j + graphiti); the **Cortex is
  guaranteed**, not optional. This does **not** make the graph the truth: the **log remains the source of
  truth and the versioning engine** (ADR-0006/0010 — only log replay reconstructs a past cursor
  byte-faithfully; the Cortex is current-state, LLM-extracted, lossy). So the briefing's **Direction /
  Source / Corpus legs fold the log** (not the Cortex), and **only Facts navigate the graph**. "Tier-0"
  demotes from a *host class* to a *runtime degrade mode*: a transient graph outage darkens only the Facts
  leg — the log-fold legs still compose, the beat never crashes (**mandatory at install, graceful at runtime**).

## Consequences

- A named **Waking** completes the anatomy (corpus = body · Cortex = mind · log = record · Mundo/Atividade/Voz
  = senses · **Waking** = coming online); `/load` and the **loader** fold in as triggers of one primitive.
- **The delta dissolves as a mandatory beat-open subagent** → an on-demand capability. This **refines
  ADR-0004** (the beat-open fan-out shrinks to Waking; the world is pulled mid-beat by judgment) and **further
  loosens ADR-0001's determinism** — the reproducibility-for-freedom trade ADR-0001 made on purpose; the known
  fallback if decay returns is to re-harden toward the sweep's determinism.
- **Source becomes subject-blind** → the Source roadmap can mark which role(s)/lens(es) a key serves; the
  delta/sweep read **by role**, not by raw source; the **yield carries a subject tag**. Same key, two lenses.
- The briefing **never renders a blank source section**.
- **The skills now lag the glossary** (a build follows, not in this ADR): `skills/delta/SKILL.md` (drop "list
  the keys" + "since the last consolidation"); `skills/beat/SKILL.md` (step 1 = Waking, not an `assemble +
  delta` blocking fan-out; delta on-demand); `skills/assemble/SKILL.md` ("On `/load`" → Waking);
  `tools/briefing.py` (compose the source-roster floor). Secrets-out-of-the-log + a standard env dir is a
  **CONTRACT** concern, tracked separately.
- **Graph-mandatory:** every install now carries a neo4j+graphiti runtime — the **#18 robust-install**
  scope grows (petertosh included). The Facts leg is **always live**; its Tier-0 degrade note becomes an
  outage-only path. This **supersedes the "Tier-0 host" reading** wherever it appears — there is no
  graph-less host, only a graph that may be transiently down, survivable precisely because the log stayed
  primary.
- **Open:** the Waking Cortex-navigation **budget** (hops/nodes) stays a tuning knob (ADR-0010 left it open);
  whether Waking **leaves a trace** of what it navigated (vs ephemeral) is unresolved.
