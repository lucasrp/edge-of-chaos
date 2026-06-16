# REQUISITES — Cortex as omnipresent memory

The edge's own memory (the **Cortex**) available at **every step of productive work**, to **every
phase and every fanned subagent** — not only the wake-time push. The settled mechanism is a standing
**`cortex` MCP** server (read-navigation), since the single-shot `claude -p` beat can only reach
mid-turn information through a tool call. This document fixes the requirements, grounds each design
choice in the 2026 SOTA, and prescribes the concrete refactor of what we built (`DESIGN-CORTEX-MCP.md`
v1, `tools/recall.py`, the `/cortex` dashboard).

Scope of authority: this is a requirements + refactor doc on `feat/cortex-requisites`. It **proposes**
glossary changes (§7) but does not enact them — an actual `CONTEXT.md` edit is Voz-ratified and trips
the count-pin fence (`tests/test_idiom_rename.py` `EXPECTED_GLOSSARY_COUNT`).

---

## 0. The design this serves (settled — refined here, not relitigated)

- The Cortex stops being reachable only at pre-dispatch (the recall PUSH, ADR-0014). It becomes
  **pullable at every step** by the lead beat AND every fanned subagent, via a tool.
- **`recall` stops being a *phase* and becomes the *seed*.** The pre-dispatch recall brief is the
  entry-point push; deep navigation is a mid-turn pull (ADR-0011's "navigation is judgment in the
  loop", now mechanized as a tool rather than left to prose the agent must remember to run).
- **Read-only** on the graph. The self/world boundary (ADR-0014) is **no longer held by phase
  separation** (a standing tool cannot be phase-scoped) — it is held by the explicit `cortex_*`
  **tool-name boundary** + agent discipline + the **write-free read** (no telemetry into the truth
  path).
- **Feedback** = the EXISTING curated doors (value = `cites`/`distills` at close; correction =
  node-targeted Voz / Earmarked) PLUS a new **implicit usage counter**, behind an `EDGE_CORTEX_USAGE`
  on/off toggle for A/B.

---

## 1. The SOTA frame (derive-first, then the gaps)

The edge's prior architecture already anticipates most of the 2026 agent-memory frontier; the research
confirms direction and sharpens four specifics. The frame, mapped to edge nouns:

| SOTA finding (2026) | Edge already has | The gap this doc closes |
|---|---|---|
| Active reconstruction beats passive top-k; *strictly* more expressive (MRAgent) | "navigate the Cortex" (ADR-0010), surf the typed web (recall.surf) | Make navigation a **mid-turn pull**, not just a prose affordance — the MCP |
| Multi-signal retrieval (semantic + BM25 + entity) beats vector-only (Mem0 2026) | embeddings on Artefatos; Graphiti entity web; substring search | `cortex_search` is substring-only — adopt **structural+keyword first, semantic next** |
| Reinforcement-by-use causes **semantic drift** if it writes back (SSGM) | log-is-truth; curated tier behind the grill | The usage counter MUST stay **off the truth path** — the design's resolution is the SOTA-correct one |
| Memory poisoning propagates via shared memory / unsanitized tool output (WorkOS, arXiv 2603.20357, 2604.16548) | group_id isolation; C1 read-only world | The **write-free read** is the prescribed defense; the boundary is the tool-name, validated |
| Dual-track (mutable graph + immutable ledger) bounds drift (SSGM) | log (truth) + Cortex (projection) — ADR-0006 | Already correct; name it as the governance invariant the usage store must not breach |
| Async / non-blocking memory ops (Mem0 2026) | projection is best-effort, never fatal | The MCP read must be **bounded-latency, fail-dark**, never block the beat |
| Token preload tax grows with store (Latenode) | recall cap = 8 salient Artefatos | Keep the **seed small**; depth is pulled, not preloaded — already right, make it a requirement |

**The one-line SOTA verdict:** the field is moving from *retrieve-then-reason* (one-shot top-k push)
to *reason-while-retrieving* (agent-controlled, multi-step, tool-mediated navigation), and is
simultaneously erecting governance walls (read/write gates, provenance, drift bounds) because adaptive
memory that writes back drifts and poisons. The edge's design is on the right side of **both** trends:
the MCP delivers active navigation; the write-free read + log-as-truth delivers the governance wall.
This doc's job is to make the implementation conform to that frame and not regress on either axis.

---

## 2. Functional requirements

**F1 — Omnipresent read door.** A standing `cortex` MCP server exposes the Cortex as pull-able tools
to the lead beat and every Task-fanned subagent, persisting across beats/sessions. Inherited via
`--mcp-config` on the parent `claude -p`.

**F2 — The seed (`cortex_recall`).** Returns the salient subgraph rooted at space-0 (reuse
`recall.recall_subgraph` → `compose_recall_brief`). This is the same content as the pre-dispatch push,
now also pullable mid-turn. Capped small (the current 8-Artefato salience cap stays — F8).

**F3 — Active navigation (`cortex_surf`, `cortex_node`).** `cortex_surf(seeds, hops≤2)` walks the
typed associative web (BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES, SERVES excluded
structurally) — reuse `recall.surf_subgraph`. `cortex_node(ref)` returns a node + immediate neighbors
(filter `cortex_fold`). Together they implement the SOTA's agent-controlled multi-step traversal: the
agent picks the next hop from evidence already in hand, not a fixed top-k.

**F4 — Lookup (`cortex_search`).** Locate nodes by label/title. v1 substring; **REQUIRED upgrade**
(§6 R4) to multi-signal: structural/keyword first, then semantic via the existing Artefato embeddings
— never semantic-only (Mem0 2026: entity-aware retrieval needs more than cosine; Latenode: keyword
miss is a named brittleness).

**F5 — Read-only.** No tool writes the graph. All curated writes stay owned by the close/grill
(ADR-0008 pull-at-open: `cites`/`distills`, Direction/Voz/Earmarked). No mid-work raw graph writes,
ever. (CONTRACT C1 extended to the self: the door reads the self, never mutates it.)

**F6 — Group-scoped, fail-dark.** Every tool is scoped to the install's `graph_group` (no graph-wide
MATCH — cross-install isolation is the `group_id`, enforced at the query, exactly as `cortex_fold`
does). Every tool returns an **honest dark marker** (never raises) on unresolved group or neo4j
outage (CONTRACT C1 degrade, ADR-0011 "name the leg that darkened, never block the beat").

**F7 — Usage telemetry + A/B toggle (`EDGE_CORTEX_USAGE`, default off).**
- OFF: no telemetry write, no re-rank — a clean side-effect-free baseline.
- ON: append `{ts, tool, refs, run_id}` to `state/cortex/usage.jsonl` (a SEPARATE, NON-AUTHORITATIVE
  store, EXCLUDED from log replay and from every corpus/recall/Direction fold), AND apply an
  ephemeral read-time re-rank: surf/search results with more PRIOR usage (recency+frequency) sort
  ahead of base hops/slug order. The re-rank reads ONLY prior telemetry; it never folds into neo4j or
  the Tier-0 log. Cold-start specified: with no overlapping prior usage, ON == OFF.

**F8 — Seed stays small; depth is pulled.** The recall seed is capped (8 salient Artefatos, the
existing `RECALL_ARTEFATO_LIMIT`). The omnipresent door does NOT enlarge the wake-time preload — it
moves depth from a bigger push to an on-demand pull (Latenode token-preload tax; the recall
confrontation's full-read wall).

**F9 — Provenance marked on every read.** Each returned node/edge carries its trust tier — **asserted**
(folds from the log → faithful) vs **extracted** (Graphiti → hypothesis) — per ADR-0006/0010. An
agent navigating mid-turn must see which is which (the SSGM provenance-grounding principle; without it
a hypothesis reads as a fact).

**F10 — Dashboard parity (later, not v1 blocking).** The `/cortex` page and the MCP read the SAME
group-scoped fold (`cortex_fold`); the door is the one read surface. Dashboard wiring is post-v1 (a
non-goal of v1, kept as a forward requirement so the two reads do not diverge).

---

## 3. Non-functional requirements

**N1 — Latency / non-blocking.** A `cortex_*` call must return within a bounded budget or fail dark;
it must never block the beat on a slow/absent graph (Mem0 2026 async-default; C1 degrade). Recommend a
connection/query timeout; the dark marker is the timeout's value.

**N2 — Zero new runtime deps.** A minimal stdio JSON-RPC 2.0 MCP server (initialize / tools/list /
tools/call), so the pinned `requirements.txt` (graphiti/neo4j/openai/flask) is untouched and the
server is unit-testable without the `mcp` SDK. (Genotype discipline: subject-blind, no identity
literals; group resolves from `agent.yaml`/`_identity` at runtime — Genotype glossary entry.)

**N3 — Determinism of the A/B treatment.** ON vs OFF must be a real, deterministic, testable
behavior change: ON re-orders the SAME result set by a usage score over telemetry written BEFORE the
call (the current call's own write never affects its own ordering — no self-referential read). Tests
seed `usage.jsonl` fixtures and assert ON/OFF DIVERGE once a result has history and CONVERGE cold.

**N4 — Truth-path isolation (the governance invariant).** `usage.jsonl` is NOT self-state: the
eventlog never reads it, no fold reads it, no Tier-0 event is emitted. ADR-0006 ("the log is truth")
holds; ADR-0008 (curated-write ownership) holds; ADR-0010 (recall-not-intake) holds. This is the
SSGM dual-track invariant: the mutable read-rank is reconcilable-to-zero against the immutable log;
drift is bounded because the read door can never reinforce the authoritative self.

**N5 — Boundary safety under inheritance.** The door inherited into every fanned subagent is safe
*because* it is write-free (no Tier-0 write, no recall-rank fold): a delta/world subagent reading its
own memory cannot reinforce the authoritative self. The per-cognition allowlist (expose to
lead/recall, deny to delta) remains an available tightening (N5a, below) but is not required for
safety in v1.

**N6 — Fail-loud identity, fail-dark runtime.** Absent identity (`EDGE_GROUP`) fails loud at the
identity seam (ADR-0015 / Install glossary); a transient graph outage fails dark (C1). The two are
not the same failure and must not be conflated.

---

## 4. The boundary argument (ADR-0014), restated for a standing tool

ADR-0014 split recall from delta because a SINGLE CONTEXT holding both world-signal and recalled-self
lets one be read as the other (the Zep-failure shape). A standing `cortex` MCP cannot reinstate that
split by phase. The SOTA gives the correct replacement guard, and it is the one the design already
chose:

1. **The door is a side-effect-free SELF read.** ADR-0010 already declares the Cortex "a declared
   recall capability, used like github/exa — for recall, never intake." A delta/world subagent
   calling `cortex_*` is querying its OWN memory (the github-recall analogy), not re-ingesting the
   world into the self. The self-reference guard is about **intake** (writing the world into the
   self); this door never writes.
2. **No write back into self-state.** No Tier-0 event, no recall-rank fold. The channel by which
   world-signal could reinforce self (the boundary collapse) requires the usage WRITE to be
   authoritative — and it is not (N4). This is exactly SSGM's finding: reinforcement that writes back
   drifts; reinforcement kept off the truth path does not.
3. **The boundary is now the tool-name + provenance + discipline.** `cortex_*` is the self door;
   source keys (github/exa/drive) are the world door. They are different tools with different names;
   an agent does not confuse "navigate my own memory" with "read the world" because the verbs and the
   tool surfaces differ. Provenance marking (F9) keeps hypothesis from being read as fact inside the
   self read.

This is the WorkOS / arXiv-2603.20357 prescription for multi-agent memory: read/write gating + scope
isolation + unsanitized-tool-output discipline. The edge satisfies all three: read-only (gate),
group_id (scope), and the curated-write tier behind the grill (no tool output becomes authoritative
memory without a human).

---

## 5. SOTA techniques — ADOPT vs REJECT (each with why)

### ADOPT

- **Active, agent-controlled multi-step navigation** (MRAgent, arXiv 2606.06036). The proof that
  active retrieval is *strictly more expressive* than passive top-k is the formal backing for the
  whole MCP: the agent picks the next hop from evidence in hand. ADOPT — it IS the door (F3).
- **Recall-as-seed + navigate-on-demand** (MRAgent "reconstruction"; ADR-0011). The push seeds a
  small entry set; depth is reconstructed by traversal. ADOPT — F2 + F3, and it bounds the
  preload tax (Latenode).
- **Multi-signal retrieval** (Mem0 2026: semantic + keyword + entity). ADOPT for `cortex_search`
  (F4 / R4): structural+keyword first, semantic (existing embeddings) next, never cosine-only.
- **Provenance grounding** (SSGM principle 2). ADOPT — mark asserted vs extracted on every returned
  node (F9). Already an ADR-0006 axis; surface it through the tool.
- **Dual-track storage = drift bound** (SSGM principle 4). ADOPT as the framing for N4: the
  immutable log is the reconciliation ledger; the usage re-rank is the mutable track, reconcilable to
  zero. Name it; do not rebuild it (the edge already has it).
- **Read/write gating + scope isolation + unsanitized-output discipline** (WorkOS; arXiv 2603.20357,
  2604.16548). ADOPT as the boundary argument (§4). The read-only door + group_id + grill-gated
  curation IS this defense.
- **Bounded-latency, fail-dark / async-default reads** (Mem0 2026). ADOPT — N1.
- **Recency as a first-class retrieval signal** (Designing Agentic Memory 2026). ADOPT — the usage
  re-rank is recency+frequency, not frequency alone (F7); this is the correct shape.

### REJECT (with why)

- **Write-back reinforcement / self-improving memory** (Memory-R1, MemAgent RL-overwrite). REJECT for
  v1. The edge's reinforcement is an EPHEMERAL READ-TIME re-rank, never a graph write. SSGM shows
  write-back reinforcement is the drift/poisoning channel; ADR-0008 reserves all curated writes for
  the grill (the human). The curated fold of hot-usage → durable salience is explicitly v2 and goes
  through the existing close/grill path, never the read door.
- **ADD-only auto-extraction treating agent facts == user facts** (Mem0 single-pass ADD). REJECT —
  this is precisely the Zep failure ADR-0008's tier boundary forbids: extraction writes only the
  non-curated tier; a vent never lands as a curated decision. The edge's tiering is the antidote, not
  a gap.
- **Drop the external graph store for built-in entity linking** (Mem0 2026 "avoid external graph
  stores"). REJECT — the edge's whole value is the navigable typed graph (Cortex, ADR-0010); the
  graph IS the product, not an implementation detail. Mem0's advice optimizes a vendor SaaS, not a
  navigable mind.
- **Weibull/automatic decay-and-prune of memories** (SSGM principle 2). REJECT for the authoritative
  graph — forgetting is the grill's curated act (Convergence is two-way: promote AND retire, by
  Voz), not an automatic time-decay. Decay MAY inform the ephemeral usage re-rank's recency weight
  (that is fine — it is off-truth-path), never the graph.
- **Semantic-only / vector-DB retrieval** (the default many systems ship). REJECT — `*Avoid*: RAG,
  retrieval, top-k, vector DB` is already canon (Cortex glossary). Navigation of own knowledge, not a
  fetch.
- **Memory-as-a-Service purpose-bound per-call mediation** (arXiv 2506.22815). REJECT for v1 —
  over-engineered for a single-install, single-mentee, group_id-isolated graph. The mediator's
  owner/requester/recipient matrix is multi-tenant machinery the edge does not have. Note as a
  forward option only if the fleet ever shares one graph across mentees without group_id walls
  (it does not — Install glossary).
- **Synchronous blocking memory writes.** REJECT — N1; the read is bounded/fail-dark, the projection
  write stays best-effort post-publish.

---

## 6. REFACTOR what we built (concrete, per the SOTA)

Grounded in `DESIGN-CORTEX-MCP.md` (the v1 spec), `tools/recall.py` (the reuse backend), and
`blog/server.py` `cortex_fold` + the `/cortex` page.

### The cortex MCP v1 (`tools/cortex_mcp.py`, per DESIGN-CORTEX-MCP.md)

- **R1 — Build it to the spec; it conforms.** The design doc is SOTA-aligned (active navigation,
  read-only, write-free usage, dual-track isolation). Ship v1 as specified. The refactors below are
  the deltas the SOTA adds ON TOP.
- **R2 — Mark provenance on every returned node (NEW, F9).** v1's tool returns
  `{slug, kernel, labels, hops}`. ADD a `tier: asserted|extracted` field (asserted = spine
  nodes/edges that fold from the log; extracted = Graphiti `:Entity`/`RELATES_TO`). The agent must
  see hypothesis-vs-fact mid-navigation. Cheap: it is a label/relationship-type check on data already
  fetched. SOTA: SSGM provenance grounding; ADR-0006 trust axis.
- **R3 — Bound every tool's latency (NEW, N1).** v1 says "fail-dark on outage" but a slow (not down)
  neo4j blocks the beat. ADD an explicit driver/query timeout; the dark marker is the timeout value.
  SOTA: Mem0 async-default.
- **R4 — `cortex_search`: substring → multi-signal (CHANGE, F4).** v1 is label/title substring only
  (a named non-goal). The SOTA names substring as brittle (Latenode) and cosine-only as insufficient
  (Mem0). The right v1.1 is: substring/keyword + structural match FIRST, then rank candidates by
  cosine over the EXISTING Artefato embeddings (already in `recall`/the project block) — never
  semantic-only. Keep it a label/keyword tool in v1 if it must ship fast, but file R4 as the first
  follow-up, not "v2 someday."
- **R5 — Usage re-rank reads recency+frequency, not frequency (CONFIRM, F7/N3).** The design already
  says recency+frequency — keep it; do not let the implementation collapse to a raw count. Recency is
  first-class (Designing Agentic Memory 2026). Add a half-life so a stale-hot ref decays in the
  re-rank (off-truth-path decay is allowed per §5-REJECT-decay's carve-out).
- **R6 — Per-cognition allowlist as a documented tightening, not a v1 requirement (N5a).** v1 ships
  one inherited door (settled). DOCUMENT the allowlist seam (expose to lead/recall, deny to delta) so
  the operator can tighten without re-architecting, per the multi-agent isolation literature — but do
  not gate v1 on it (the write-free read already makes inheritance safe).

### `tools/recall.py`

- **R7 — Extract the connection/identity scaffolding (CHANGE).** `recall_subgraph` and
  `surf_subgraph` each re-implement the same driver-open / identity-resolve / fail-dark / close
  boilerplate (recall.py:83-116 vs 138-166). The MCP will add a third copy. EXTRACT a single guarded
  `_session(group)` context helper (open, resolve, fail-dark, close) and have all three reuse it.
  This is the surgical de-dup the MCP refactor forces — not a speculative abstraction (it has three
  call sites the moment the MCP lands). Keep `recall_subgraph`/`surf_subgraph` signatures stable; the
  MCP imports them as-is.
- **R8 — Return provenance from the reused functions (CHANGE, supports R2).** `surf_subgraph` already
  returns `labels`; `recall_subgraph` returns bare dicts. Add the `tier` derivation here (one place)
  so both the brief and the MCP get it, rather than the MCP re-deriving it. Keep the brief's rendered
  text unchanged (the tier is for the structured MCP payload, not the prose push).
- **R9 — Do NOT widen recall's push (CONFIRM, F8).** Leave `RECALL_ARTEFATO_LIMIT = 8`. The
  omnipresent door is the answer to "I need more" — pull deeper, do not preload fatter. Resist the
  temptation to grow the seed now that a richer backend exists.

### The dashboard (`/cortex`, `blog/server.py`)

- **R10 — One read surface, no divergence (CONFIRM, F10).** The MCP and `/cortex` both read
  `cortex_fold` (group-scoped, fail-dark, never a graph-wide MATCH). Keep it that way: when R2/R4 add
  provenance/multi-signal to the MCP path, route them THROUGH `cortex_fold`/the reused recall
  functions so the page inherits them. Do not fork a second read path for the MCP.
- **R11 — Surface the usage signal on the dashboard, READ-ONLY (NEW, optional).** If `EDGE_CORTEX_USAGE=on`,
  the `/cortex` page MAY visualize hot refs (a heat overlay from `usage.jsonl`). This is a render of a
  non-authoritative store — it must carry no write affordance and must not enter any fold (N4). File
  as optional, post-v1; it makes the A/B legible to the operator.
- **R12 — No write affordance regressions.** The `/cortex` write gate (the `_json_for_script`
  breakout escaping at server.py:1287+ that guards the Slice-1 write gate) stays. The MCP adds a
  read door; it must not become a same-origin write vector. (C1 / §4.)

---

## 7. Glossary engagement (PROPOSED — flagged for Voz ratification, NOT enacted)

Cross-checked every requirement against `CONTEXT.md`. The work **strains four concepts** and would
**add one**. Per the guardrail, these are PROPOSALS: an actual edit is Voz-ratified and bumps
`EXPECTED_GLOSSARY_COUNT` (currently **43**) in the same commit. **Do not silently rewrite the canon.**

### P1 — Sharpen **Recall** (recall-as-seed, not recall-as-phase). [edit, count unchanged]

The current entry frames Recall as "handed to the agent at pre-dispatch by an independent subagent" —
true, but the omnipresent door makes the pre-dispatch hand-off the SEED, with depth pulled mid-turn.
The existing line "**The push seeds; navigation deepens**: on-demand Cortex navigation stays the
loop's own judgment" already anticipates this; the sharpening is to name that navigation is now
**tool-mediated** (the `cortex` door), not only prose the loop must remember.

Drafted addition to the **Recall** entry (after the "push seeds" sentence):
> The push remains the pre-dispatch seed; deep navigation is now a **mid-turn pull** through the
> standing `cortex` read door (the loop's judgment, mechanized as a tool — available to the lead beat
> and every fanned subagent), not only the recall agent's one-shot brief.

This is a definition sharpen on an existing header — **count stays 43**.

### P2 — Sharpen **Cortex** (the navigable mind is now pull-able every step). [edit, count unchanged]

The **Cortex** entry says "the **briefing** seeds entry points; the edge *navigates* it on demand."
Add that the navigation surface is now a standing read door, and reinforce `*Avoid*` (no new avoid
terms, the existing RAG/retrieval/top-k/vector-DB/memory-store set already covers the MCP misframing).

Drafted addition (after "the read that scales past full-read"):
> The on-demand navigation is exposed as the standing **`cortex` read door** (read-only; the self
> query, never intake — ADR-0014's boundary now held by the tool-name + the write-free read, not by
> phase separation).

Count stays 43.

### P3 — NEW entity **Usage signal** (the implicit, off-truth-path feedback). [NEW header → count 44]

There is no glossary noun for the implicit usage telemetry. It is genuinely new and distinct from the
two existing feedback doors (value = `cites`/`distills`; correction = Voz/Earmarked). It needs a name
to keep agents from reading it as authoritative salience.

Drafted entry:
> **Usage signal**:
> The **implicit, non-authoritative** record of which Cortex nodes the edge READ while working —
> appended to `state/cortex/usage.jsonl` (behind `EDGE_CORTEX_USAGE`), EXCLUDED from log replay and
> every fold. It drives an **ephemeral read-time re-rank only** (recency+frequency), never a graph
> write: it is NOT self-state (the log stays truth — ADR-0006). Distinct from **value feedback**
> (`cites`/`distills` at close) and **correction** (node-targeted Voz / Earmarked), both curated and
> authoritative. The dual-track guard: reconcilable to zero against the log.
> *Avoid*: salience (that is the Earmarked's harm axis / the curated tier), reinforcement (it never
> writes back), memory store

This is the one entry that **bumps the count to 44** and requires Voz ratification + a same-commit
`EXPECTED_GLOSSARY_COUNT` change. FLAGGED.

### P4 — Confirm **Space-0** unchanged. The seed still roots at space-0; no strain. No proposal.

### P5 — "Omnipresent memory" / "surf" — NO new headers.

- **"surf"** stays a lowercase verb (the Idiom names subjects, not mechanics — ADR-0010). It is the
  act `cortex_surf` performs; it does not earn a header. (Matches the `recall`/`navigate` precedent.)
- **"Omnipresent memory"** is a property of the Cortex under this design, captured by the P2
  sharpen — not its own noun. No header.

### Drafted `CONTEXT.md` diff (proposal only — DO NOT APPLY without Voz)

```diff
 **Recall**:
 ... third view (self-curated · world-new · memory-salient). **The push seeds; navigation deepens**:
 on-demand Cortex navigation stays the loop's own judgment, not the recall agent's.
+The push remains the pre-dispatch seed; deep navigation is now a **mid-turn pull** through the
+standing `cortex` read door (the loop's judgment, mechanized as a tool — available to the lead beat
+and every fanned subagent), not only the recall agent's one-shot brief.
 *Avoid*: retrieval, fetch, memory query, delta-over-the-wiki, recall-push-inside-assemble

 **Cortex**:
 ... the edge *navigates* it on demand — the read that **scales past full-read** (no token-budget wall).
+The on-demand navigation is exposed as the standing **`cortex` read door** (read-only; the self query,
+never intake — ADR-0014's boundary now held by the tool-name + the write-free read, not by phase).
 Trust is legible per edge: ...

+**Usage signal**:
+The **implicit, non-authoritative** record of which Cortex nodes the edge READ while working —
+appended to `state/cortex/usage.jsonl` (behind `EDGE_CORTEX_USAGE`), EXCLUDED from log replay and
+every fold. It drives an **ephemeral read-time re-rank only** (recency+frequency), never a graph write:
+it is NOT self-state (the log stays truth — ADR-0006). Distinct from **value feedback** (`cites`/
+`distills` at close) and **correction** (node-targeted Voz / Earmarked), both curated and authoritative.
+*Avoid*: salience, reinforcement, memory store
```

And the same-commit fence bump (only on ratification):
```diff
-EXPECTED_GLOSSARY_COUNT = 43
+EXPECTED_GLOSSARY_COUNT = 44  # 2026-06-16 cortex omnipresent memory (Voz-ratified): +1 Usage signal
```

---

## 8. ADR / CONTRACT conformance check

- **ADR-0014 (recall third independent brief, self/world boundary):** held by §4 — boundary moves
  from phase-separation to tool-name + write-free read + provenance. Conforms.
- **ADR-0008 (curated writes pull-at-open):** held by F5 — no tool writes; curation stays the grill's.
  Conforms.
- **ADR-0011 (navigation is judgment in the loop; source blind to subject):** held — navigation is now
  tool-mediated judgment; `cortex_*` is the self door, NOT a source (a source is subject-blind world
  locator). Conforms.
- **ADR-0010 (navigate the Cortex; declared recall capability used like github/exa, never intake):**
  the MCP IS this capability, made pull-able. Conforms.
- **ADR-0006 (log is truth; graph/pages are projections):** held by N4 — usage store is off the truth
  path; the dual-track invariant is named. Conforms.
- **ADR-0015 (identity resolves at one fail-loud seam):** held by N6 — identity fails loud, runtime
  fails dark. Conforms.
- **CONTRACT C1 (no external side effects / read-only):** extended to the self — the door reads the
  self, mutates nothing. Conforms.
- **CONTRACT C2 (extraction incremental):** untouched — the door reads, does not extract. Conforms.
- **CONTRACT C4 (secrets never in genotype):** held by N2 — group from `_identity` at runtime, no
  literals. Conforms.

---

## 9. Open questions (tuning, not blockers)

- **Usage re-rank half-life** (R5): the recency decay constant is a tuning knob; seed a default,
  measure under A/B.
- **`cortex_search` ranking weights** (R4): structural-vs-keyword-vs-semantic blend is a tuning knob
  once multi-signal lands.
- **Whether the dashboard heat overlay (R11) ships in v1.1 or later** — operator call; non-blocking.

---

## Sources (2026 SOTA)

- MRAgent — *Memory is Reconstructed, Not Retrieved: Graph Memory for LLM Agents*, arXiv 2606.06036
  (active reconstruction > passive top-k; cue–tag–content; strict expressivity separation).
- Mem0 — *State of AI Agent Memory 2026* (multi-signal retrieval, benchmarks, async-default, named
  production gaps: staleness, identity resolution).
- *SSGM: Governing Evolving Memory in LLM Agents*, arXiv 2603.11768 (semantic/goal drift from
  reinforcement; dual-track mutable+immutable; provenance grounding; pre-consolidation validation).
- WorkOS, *AI agent memory poisoning*; *Memory poisoning and secure multi-agent systems*, arXiv
  2603.20357; *Survey on Security of Long-Term Memory in LLM Agents*, arXiv 2604.16548
  (shared-memory propagation; read/write gating + scope isolation + unsanitized-output discipline).
- Latenode, *Memory MCP Server explained* (token-preload tax; substring brittleness; per-project
  scoping).
- *Designing Agentic Memory in 2026* (recency as a first-class retrieval signal).
- MemGraphRAG, arXiv 2606.00610; *Memory as a Service*, arXiv 2506.22815 (rejected — multi-tenant
  mediation, over-engineered for one group_id-isolated install).
