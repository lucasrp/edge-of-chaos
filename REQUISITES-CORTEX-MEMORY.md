# REQUISITES — Cortex as omnipresent memory

The edge's own memory (the **Cortex**) available at **every step of self-work**, to **the lead beat
and the self-reading subjects it fans** — not only the wake-time push, and (the one scope wall)
**NOT to the delta/world-reading subject** (ADR-0014 keeps that split — §4/N5). The settled mechanism
is a standing **`cortex` MCP** server (read-navigation), since the single-shot `claude -p` beat can
only reach mid-turn information through a tool call. This document fixes the requirements, grounds each
design choice in the 2026 SOTA, and prescribes the concrete refactor of what we built (the cortex MCP
v1 — contract inlined in Appendix A, `tools/recall.py`, the `/cortex` dashboard).

Scope of authority: this is a requirements + refactor doc on `feat/cortex-requisites`. It **proposes**
glossary changes (§7) but does not enact them — an actual `CONTEXT.md` edit is Voz-ratified and trips
the count-pin fence (`tests/test_idiom_rename.py` `EXPECTED_GLOSSARY_COUNT`).

---

## 0. The design this serves (settled — refined here, not relitigated)

- The Cortex stops being reachable only at pre-dispatch (the recall PUSH, ADR-0014). It becomes
  **pullable at every step** by the lead beat and the self-reading subjects it fans, via a tool —
  but NOT by the delta/world-reading subject (the one scope wall, N5).
- **`recall` stops being a *phase* and becomes the *seed*.** The pre-dispatch recall brief is the
  entry-point push; deep navigation is a mid-turn pull (ADR-0011's "navigation is judgment in the
  loop", now mechanized as a tool rather than left to prose the agent must remember to run).
- **Read-only** on the graph. The self/world boundary (ADR-0014) is **no longer held by phase
  separation** (a standing tool cannot be phase-scoped) — it is held by **three layers**: the
  explicit `cortex_*` **tool-name boundary**, the **write-free read** (no telemetry into the truth
  path), AND a **v1-mandatory per-cognition allowlist** that DENIES `cortex_*` to delta/world
  subagents (§4 / N5). Read-only stops durable graph contamination; the allowlist stops the
  *in-context* mixing ADR-0014 names (world-new delta + recalled-self in one context). Both are
  required — neither alone replaces the phase split.
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
| Memory poisoning propagates via shared memory / unsanitized tool output (WorkOS, arXiv 2603.20357, 2604.16548) | group_id isolation; C1 read-only world | **Write-free read + subject-scope deny** (delta/world denied the self door) is the prescribed defense; boundary = scope wall, not tool-name alone |
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

**F1 — Omnipresent read door (subject-scoped, NOT unconditionally inherited).** A standing `cortex`
MCP server exposes the Cortex as pull-able tools to the **lead beat and its permitted in-cognition
fan-out (the self-reading subjects)**, persisting across beats/sessions, via `--mcp-config` on the
parent `claude -p`. **The delta/world subagent dispatch is DENIED `cortex_*`** (N5/R6) — "omnipresent"
means present at every STEP of self-work, not present to the world-reading subject. The door is NOT
unconditionally inherited by every Task-fanned subagent; inheritance is gated by subject so the
ADR-0014 self/world split survives (the in-context mixing a read-only door does not stop).

**F2 — The seed (`cortex_recall`).** Returns the salient subgraph rooted at space-0 (reuse
`recall.recall_subgraph` → `compose_recall_brief`). This is the same content as the pre-dispatch push,
now also pullable mid-turn. Capped small (the current 8-Artefato salience cap stays — F8).

**F3 — Active navigation (`cortex_surf`, `cortex_node`).** `cortex_surf(seeds, hops≤2)` walks the
typed associative web (BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES, SERVES excluded
structurally) — reuse `recall.surf_subgraph`. `cortex_node(ref)` returns a node + immediate neighbors
(filter `cortex_fold`). Together they implement the SOTA's agent-controlled multi-step traversal: the
agent picks the next hop from evidence already in hand, not a fixed top-k.
**PATH-WIDE group scoping is REQUIRED (not just endpoints):** the variable-length 2-hop traversal must
constrain EVERY node on the path to the group (`all(x IN nodes(p) WHERE x.group_id=$g)`), not only the
seed and the terminal node. The current `recall.SURF_QUERY` scopes only `seed` and `n` — on the SHARED
neo4j (roberto/petertosh share one graph split by `group_id`), a foreign intermediate bridge node
could influence which same-group peers are returned. This is a v1 isolation blocker — see R7b.

**F4 — Lookup (`cortex_search`).** Locate nodes by label/title.
- **v1 (ship gate): label/keyword substring is ACCEPTABLE** — it is a known-incomplete path, shipped
  deliberately because navigation (F3) is the primary recall mode and `cortex_search` is the
  fallback locator. v1 does NOT claim SOTA-conformant retrieval on this tool.
- **v1.1 (explicit, non-blocking follow-up — NOT a v1 acceptance blocker): multi-signal**
  (structural/keyword first, then semantic via the existing Artefato embeddings — never
  semantic-only). Mem0 2026: entity-aware retrieval needs more than cosine; Latenode: keyword miss is
  a named brittleness. This is the FIRST follow-up (R4), gated by its own tests, not deferred to a
  vague "v2."

The contract is unambiguous: substring is a conformant v1 ship; multi-signal is a named v1.1 with
its own gate. v1 is NOT declared SOTA-conformant on search.

**F5 — Read-only.** No tool writes the graph. All curated writes stay owned by the close/grill
(ADR-0008 pull-at-open: `cites`/`distills`, Direction/Voz/Earmarked). No mid-work raw graph writes,
ever. (CONTRACT C1 extended to the self: the door reads the self, never mutates it.)

**F6 — Group-scoped; identity fails loud, runtime fails dark.** Every tool is scoped to the install's
`graph_group` (no graph-wide MATCH — cross-install isolation is the `group_id`, enforced at the query,
exactly as `cortex_fold` does). Two FAILURE CLASSES, never conflated (ADR-0015):
- **Unresolved identity (no `EDGE_GROUP`) FAILS LOUD** — the MCP server resolves identity through the
  canonical seam (`_identity`) at startup, BEFORE it serves any call; an unidentified install must
  not serve `cortex_*` at all (ADR-0015 rejects silent read-side degrade: a darkened unidentified
  install hides empty/foreign state — the exact multi-tenant contamination ADR-0015 was written to
  stop). This is NOT the C1 dark path.
- **Transient graph health (neo4j down/slow AFTER a group is resolved) FAILS DARK** — an honest dark
  marker, never a raise (CONTRACT C1 degrade, ADR-0011 "name the leg that darkened, never block the
  beat"). Fail-dark is reserved for runtime outage of a KNOWN group, never for missing identity.

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

**F9 — Provenance marked on EVERY read, INCLUDING the seed.** Each returned node/edge carries its
trust tier — **asserted** (folds from the log → faithful) vs **extracted** (Graphiti → hypothesis) —
per ADR-0006/0010. An agent navigating mid-turn must see which is which (the SSGM provenance-grounding
principle; without it a hypothesis reads as a fact). **This covers `cortex_recall` too** — the seed is
the FIRST and most-likely read, so it is the worst place to drop the distinction. The recall brief
either renders an explicit asserted/extracted marker per line, OR `cortex_recall` returns a structured
payload whose nodes carry `tier` (the MCP's call, but the marker must reach the caller — see R8/R8b).
The spine the seed renders (Genesis/Objective/Direction/Artefatos via SERVES/ANCHORS) is asserted by
construction; the clusters it DISTILLS are extracted — so the seed mixes tiers and must mark them.

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

**N5 — Boundary safety: write-free read AND v1 allowlist.** Two guards, BOTH required:
- **Write-free read** (no Tier-0 write, no recall-rank fold) stops a subagent from reinforcing the
  *authoritative durable self*.
- **The per-cognition allowlist is a v1 REQUIREMENT** (not an optional tightening): `cortex_*` is
  exposed to the lead/recall path and DENIED to delta/world subagents. This stops the *in-context*
  contamination ADR-0014 names — a delta/world subagent pulling self-memory while it evaluates world
  signal, where one is read as the other (read-only does not prevent this; it only prevents durable
  writes). This is the SOTA scope-isolation prescription (WorkOS / arXiv 2603.20357: deny which
  agents read which memory scopes). Mechanically: the `--mcp-config` allowlist on the parent grants
  `cortex_*` to the lead; the delta/world subagent dispatch withholds it.

The settled "one inherited door" decision is honored for the *lead and its in-cognition fan-out*; the
exclusion is specifically the **delta/world subject** (the half ADR-0014 must keep separate), which is
a deny-by-subject, not a re-introduction of phase separation.

**N6 — Fail-loud identity, fail-dark runtime (see F6).** Absent identity (`EDGE_GROUP`) FAILS LOUD at
the identity seam BEFORE the server serves any call (ADR-0015 / Install glossary — silent darkening of
an unidentified install is forbidden); a transient graph outage of a *resolved* group FAILS DARK (C1).
The two are different failures and must never be conflated. (F6 is the functional statement of this
split; N6 is its non-functional invariant.)

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
   world-signal could reinforce the *durable* self (the boundary collapse) requires the usage WRITE
   to be authoritative — and it is not (N4). This is exactly SSGM's finding: reinforcement that writes
   back drifts; reinforcement kept off the truth path does not. **But write-free alone is not
   enough** — it stops durable contamination, not the *in-context* mixing of guard 3.
3. **A v1-mandatory scope deny on the delta/world subject (the in-context guard).** ADR-0014's named
   failure is one CONTEXT holding world-new delta beside recalled-self, where one is read as the
   other — and a read-only door does NOT prevent that (the polluted observation forms before any
   write). So the allowlist DENIES `cortex_*` to the delta/world subagent (N5) — the SOTA
   scope-isolation prescription. The self door is exposed to the lead and its in-cognition fan-out;
   the world-reading subject does not get the self door. This is a deny-by-subject, replacing the
   phase split with a scope wall, not abandoning it.
4. **The boundary is also the tool-name + provenance.** `cortex_*` is the self door; source keys
   (github/exa/drive) are the world door — different tools, different names; an agent does not confuse
   "navigate my own memory" with "read the world." Provenance marking (F9) keeps hypothesis from being
   read as fact inside the self read.

This is the WorkOS / arXiv-2603.20357 prescription for multi-agent memory: read/write gating + scope
isolation + unsanitized-tool-output discipline. The edge satisfies all three: read-only + the
delta/world deny (gate + scope), group_id (cross-install scope), and the curated-write tier behind the
grill (no tool output becomes authoritative memory without a human). The replacement for ADR-0014's
phase split is therefore **subject-scope isolation**, not "tool-name discipline alone" — which is why
the allowlist is a v1 requirement, not a tightening.

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

- **R1 — Build it to the inlined v1 contract (Appendix A); it conforms.** The v1 spec
  (`DESIGN-CORTEX-MCP.md`) lives in the parallel `edge-cortex-mcp` worktree, NOT this branch — so the
  normative v1 contract (tools, return shapes, failure markers, timeout, telemetry semantics) is
  **inlined in Appendix A** below, making this doc self-validating. The design is SOTA-aligned (active
  navigation, read-only, write-free usage, dual-track isolation). Ship v1 to Appendix A; the refactors
  below are the deltas the SOTA adds ON TOP (and where they override the v1 design — R6 — it is
  flagged).
- **R2 — Mark provenance on every returned node (NEW, F9).** v1's tool returns
  `{slug, kernel, labels, hops}`. ADD a `tier: asserted|extracted` field (asserted = spine
  nodes/edges that fold from the log; extracted = Graphiti `:Entity`/`RELATES_TO`). The agent must
  see hypothesis-vs-fact mid-navigation. Cheap: it is a label/relationship-type check on data already
  fetched. SOTA: SSGM provenance grounding; ADR-0006 trust axis.
- **R3 — Bound every tool's latency (NEW, N1).** v1 says "fail-dark on outage" but a slow (not down)
  neo4j blocks the beat. ADD an explicit driver/query timeout; the dark marker is the timeout value.
  SOTA: Mem0 async-default.
- **R4 — `cortex_search`: substring (v1) → multi-signal (v1.1, own gate) (CHANGE, F4).** v1 ships
  label/title substring (acceptable — F4 ship gate). v1.1 (the FIRST follow-up, NOT a v1 blocker,
  gated by its own tests): substring/keyword + structural match FIRST, then rank candidates by cosine
  over the EXISTING Artefato embeddings (already in `recall`/the project block) — never semantic-only.
  The SOTA names substring as brittle (Latenode) and cosine-only as insufficient (Mem0); v1 does not
  claim to clear that bar, v1.1 does.
- **R5 — Usage re-rank reads recency+frequency, not frequency (CONFIRM, F7/N3).** The design already
  says recency+frequency — keep it; do not let the implementation collapse to a raw count. Recency is
  first-class (Designing Agentic Memory 2026). Add a half-life so a stale-hot ref decays in the
  re-rank (off-truth-path decay is allowed per §5-REJECT-decay's carve-out).
- **R6 — Per-cognition allowlist is a v1 REQUIREMENT (CHANGE, N5).** Supersedes the v1 design's
  "one inherited door, allowlist optional" stance. The MCP config grants `cortex_*` to the lead/recall
  path and DENIES it to the delta/world subagent dispatch. Rationale: read-only stops durable writes,
  NOT the in-context world+self mixing ADR-0014 names (the contamination forms before any write);
  scope isolation is the SOTA fix (WorkOS / arXiv 2603.20357). Build: the `build_beat_command`
  `--mcp-config` allowlist differentiates by dispatched subject — lead/recall get the door, delta/world
  do not. (This is the one place this doc overrides the v1 DESIGN's settled "inherited everywhere"
  line; the override is gate-driven, per codex iter1.)

### `tools/recall.py`

- **R7 — Extract the connection/identity scaffolding (CHANGE).** `recall_subgraph` and
  `surf_subgraph` each re-implement the same driver-open / identity-resolve / fail-dark / close
  boilerplate (recall.py:83-116 vs 138-166). The MCP will add a third copy. EXTRACT a single guarded
  `_session(group)` context helper (open, resolve, fail-dark, close) and have all three reuse it.
  This is the surgical de-dup the MCP refactor forces — not a speculative abstraction (it has three
  call sites the moment the MCP lands). Keep `recall_subgraph`/`surf_subgraph` signatures stable; the
  MCP imports them as-is.
- **R7b — Scope the SURF traversal PATH-WIDE (CHANGE — v1 isolation blocker, F3/F6).** `SURF_QUERY`
  (recall.py:55-61) constrains only `seed` (`slug IN $seeds`, group-scoped seeds) and the terminal `n`
  (`n.group_id=$g`); the variable-length `*1..2` path can pass through an intermediate node with no
  group constraint. On the shared neo4j (roberto/petertosh, one graph by `group_id`), a foreign bridge
  node could route which same-group peers surface — a cross-install topology leak that LOOKS scoped
  (rows are same-group) while the traversal was contaminated. FIX: add `all(x IN nodes(p) WHERE
  x.group_id=$g)` to the WHERE (or expand to explicitly-scoped 1-hop + 2-hop patterns). TEST: a
  fixture with a foreign intermediate bridge asserting it cannot affect surf results. This fixes the
  ONE reused backend the MCP inherits — `cortex_fold` already scopes correctly (it is a flat
  group-filtered read, no variable-length path), so the leak is specific to surf.
- **R8 — Return provenance from the reused functions (CHANGE, supports R2/F9).** `surf_subgraph`
  already returns `labels`; `recall_subgraph` returns bare dicts. Add the `tier` derivation here (one
  place) so both the brief and the MCP get it, rather than the MCP re-deriving it.
- **R8b — Mark provenance in the recall SEED, not just surf/search (CHANGE — supersedes the earlier
  "brief unchanged" stance, F9).** The recall brief currently renders prose with no asserted/extracted
  marker, and `cortex_recall` returns only that prose — so the seed (the first read) can present an
  extracted cluster as if it were asserted fact. FIX: either (a) `compose_recall_brief` renders an
  inline marker on the lines whose content is extracted (the DISTILLED clusters) vs asserted (the
  spine), OR (b) `cortex_recall` returns a structured payload alongside/instead of the prose, nodes
  carrying `tier`. Cheap: the spine is asserted by construction, clusters are the extracted half — the
  split is already known at compose time. TEST: a recall fixture with both an asserted spine and an
  extracted cluster asserts both tiers reach the caller.
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
> and the self-reading subjects it fans, DENIED to the delta/world subject so the subject split
> survives), not only the recall agent's one-shot brief.

This is a definition sharpen on an existing header — **count stays 43**.

### P2 — Sharpen **Cortex** (the navigable mind is now pull-able every step). [edit, count unchanged]

The **Cortex** entry says "the **briefing** seeds entry points; the edge *navigates* it on demand."
Add that the navigation surface is now a standing read door, and reinforce `*Avoid*` (no new avoid
terms, the existing RAG/retrieval/top-k/vector-DB/memory-store set already covers the MCP misframing).

Drafted addition (after "the read that scales past full-read"):
> The on-demand navigation is exposed as the standing **`cortex` read door** (read-only; the self
> query, never intake — ADR-0014's boundary now held by **subject-scope isolation** (the delta/world
> subject is denied the door) + the write-free read + the tool-name, replacing phase separation).

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
+and the self-reading subjects it fans, DENIED to the delta/world subject), not only the recall agent's
+one-shot brief.
 *Avoid*: retrieval, fetch, memory query, delta-over-the-wiki, recall-push-inside-assemble

 **Cortex**:
 ... the edge *navigates* it on demand — the read that **scales past full-read** (no token-budget wall).
+The on-demand navigation is exposed as the standing **`cortex` read door** (read-only; the self query,
+never intake — ADR-0014's boundary now held by subject-scope isolation (the delta/world subject is
+denied the door) + the write-free read + the tool-name, replacing phase separation).
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
  from phase-separation to **subject-scope isolation** (the v1-mandatory deny of `cortex_*` to the
  delta/world subagent, N5) + write-free read + tool-name + provenance. The in-context mixing ADR-0014
  names is blocked by the scope wall, not merely by read-only. Conforms (no ADR amendment needed — the
  scope deny preserves the subject split).
- **ADR-0008 (curated writes pull-at-open):** held by F5 — no tool writes; curation stays the grill's.
  Conforms.
- **ADR-0011 (navigation is judgment in the loop; source blind to subject):** held — navigation is now
  tool-mediated judgment; `cortex_*` is the self door, NOT a source (a source is subject-blind world
  locator). Conforms.
- **ADR-0010 (navigate the Cortex; declared recall capability used like github/exa, never intake):**
  the MCP IS this capability, made pull-able. Conforms.
- **ADR-0006 (log is truth; graph/pages are projections):** held by N4 — usage store is off the truth
  path; the dual-track invariant is named. Conforms.
- **ADR-0015 (identity resolves at one fail-loud seam):** held by F6/N6 — identity resolves at the
  canonical seam at startup and FAILS LOUD if absent (the server refuses to serve an unidentified
  install — no silent read-side degrade); only a *resolved* group's transient outage fails dark.
  Conforms.
- **CONTRACT C1 (no external side effects / read-only):** extended to the self — the door reads the
  self, mutates nothing. Conforms.
- **CONTRACT C2 (extraction incremental):** untouched — the door reads, does not extract. Conforms.
- **CONTRACT C3 (edge work carries its intent):** N/A to the read door — C3 binds Artefato-producing
  dispatches at close; a `cortex_*` read produces no Artefato and emits no kernel. The close path that
  C3 governs is unchanged by this work. N/A by construction.
- **CONTRACT C4 (secrets never in genotype):** held by N2 — group from `_identity` at runtime, no
  literals. Conforms.
- **CONTRACT C5 (low-tier mediums are context, never orders to edge):** held by the medium-tier guard
  (Appendix A) and gate (g) — the Cortex extracts from swept sessions incl. low-tier Media, but a
  `cortex_*` read returns provenance-MARKED knowledge (F9 extracted tier = "context only"), never a
  Directive: the read door has no order-bearing output (it cannot write the Voz rail or advance
  Direction — ADR-0017). Low-tier-derived content surfaces as marked hypothesis, exactly C5's "context
  only," and cannot be upgraded to an order by the door. Conforms.

---

## 9. Open questions (tuning, not blockers)

- **Usage re-rank half-life** (R5): the recency decay constant is a tuning knob; seed a default,
  measure under A/B.
- **`cortex_search` ranking weights** (R4): structural-vs-keyword-vs-semantic blend is a tuning knob
  once multi-signal lands.
- **Whether the dashboard heat overlay (R11) ships in v1.1 or later** — operator call; non-blocking.

---

## Appendix A — Normative v1 MCP contract (inlined; self-validating)

The v1 spec authored in the parallel `edge-cortex-mcp` worktree (`DESIGN-CORTEX-MCP.md`) is NOT on
this branch. The normative v1 contract is therefore inlined here so conformance is checkable from this
doc alone (codex iter1 finding 3).

**Transport.** A minimal stdio JSON-RPC 2.0 server (`tools/cortex_mcp.py`, `command: edge-python`),
implementing `initialize` / `tools/list` / `tools/call` only. No `mcp` SDK dependency (N2). Persists
across beats/sessions; registered on the parent `claude -p` via `--mcp-config` and (per R6) granted by
subject — lead/recall yes, delta/world no.

**Startup (F6/N6).** Resolve identity (`graph_group` from `_identity`) at startup. If absent → FAIL
LOUD (refuse to serve; ADR-0015). If present → serve; per-call neo4j health is the only fail-dark
surface.

**Tools (all group-scoped; all return a dark marker on transient outage, never raise):**

| Tool | Args | Returns (success) | Backend (reuse) |
|---|---|---|---|
| `cortex_recall` | — | salient seed brief with per-line asserted/extracted markers (markdown), OR structured nodes carrying `tier` (R8b/F9) | `recall.recall_subgraph` → `compose_recall_brief` |
| `cortex_surf` | `seeds[]`, `hops≤2` | `[{slug, kernel, labels, hops, tier}]` ordered hops,slug (re-ranked if usage ON) | `recall.surf_subgraph` (+R8 tier) |
| `cortex_node` | `ref` | node + immediate neighbors, each with `tier` | filter `cortex_fold` |
| `cortex_search` | `query` | `[{slug/ref, label, tier}]` — v1 substring; v1.1 multi-signal (F4) | filter `cortex_fold` (+R8 tier) |

**Dark marker.** A structured value, e.g. `{"dark": true, "leg": "cortex", "reason": "graph offline"}`
(or the recall brief's existing dark-leg markdown for `cortex_recall`) — the SAME shape the recall
brief already uses. Never an exception; the caller sees an honest "this leg is dark," orients from
elsewhere (ADR-0011).

**Timeout (N1/R3).** Each tool sets an explicit neo4j driver/query timeout; on timeout it returns the
dark marker (the timeout's value), never blocks the beat.

**Provenance (F9/R2/R8/R8b).** Every returned node/edge — across ALL four tools, the seed
`cortex_recall` INCLUDED — carries `tier ∈ {asserted, extracted}`: asserted = spine nodes/edges that
fold from the log; extracted = Graphiti `:Entity`/`RELATES_TO` hypotheses. The seed renders the marker
inline (its spine is asserted, its DISTILLED clusters extracted) or returns structured tiers; it must
not present an extracted cluster as unmarked fact.

**Usage telemetry (F7/N3/N4).** `EDGE_CORTEX_USAGE=off` (default) → no write, no re-rank. `=on` →
append `{ts, tool, refs, run_id}` to `state/cortex/usage.jsonl` (NON-authoritative; excluded from
replay and every fold) AND apply the ephemeral recency+frequency re-rank to `cortex_surf`/`cortex_search`
results, computed over PRIOR telemetry only (the current write never affects its own ordering). Cold
store → ON == OFF.

**Non-goals (v1).** No graph writes (curated salience promotion is v2, via the grill). No semantic
search (v1.1 — R4). No dashboard wiring (F10/R10-R11 are post-v1).

**Medium-tier guard (C5).** The Cortex extracts from swept sessions, some of which are low-tier Media
(the native Claude Code session — C5: context, never orders to edge). A `cortex_*` read returns
KNOWLEDGE (asserted spine + extracted hypotheses), never a Directive — the read door has NO
order-bearing channel: it cannot emit a Directive, advance Direction, or write the Voz rail. So a
self-subject pulling a node whose content traces to a low-tier Medium reads it as MARKED-hypothesis
context (F9 extracted tier), exactly C5's "context only" — never as an order. The guard is structural:
Directives ride the Voz rail (ADR-0017), a write surface the read door does not touch; the door cannot
upgrade low-tier content into an order. Acceptance (g) below proves it.

**Acceptance (v1 ship gate).** (a) all four tools return correct group-scoped data against a fixture
and a dark marker on a forced outage; (a2) a `cortex_surf` fixture with a FOREIGN intermediate bridge
node asserts it cannot affect results (path-wide scoping, R7b); (b) identity-absent startup fails loud
(refuses to serve); (c) `cortex_*` denied to a delta/world dispatch (negative `tools/list` test),
granted to lead/recall; (d) usage OFF == no write AND no re-rank; usage ON DIVERGES from OFF on a
seeded `usage.jsonl` and CONVERGES on a cold store; (e) **no AUTHORITATIVE write occurs on any read
path** — no graph write, no Tier-0 event, no corpus/recall/Direction/curated fold; the ONLY permitted
write is, when `EDGE_CORTEX_USAGE=on`, exactly one append to the non-authoritative
`state/cortex/usage.jsonl` AFTER ranking (OFF writes nothing at all). (e) is the truth-path-isolation
proof, consistent with F7 (the usage append is non-authoritative telemetry, not self-state); (f) a
recall fixture carrying an asserted spine AND an extracted cluster exposes BOTH tiers to the caller
(seed provenance, F9/R8b); (g) no `cortex_*` tool emits a Directive / advances Direction / writes the
Voz rail — the read door has no order-bearing output (C5). Multi-signal search (F4 v1.1) and
provenance-on-dashboard (R11) are EXCLUDED from the v1 gate.

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
