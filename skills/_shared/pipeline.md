# The shared pipeline

THE single shared pipeline definition (ADR-0012). Every producer-skill — `report`, `map`,
`research`, `plan`, … — funnels through this one pipeline. The beat is a pure round-robin
scheduler; the pipeline is what runs once a producer's turn comes. There is no per-skill
pipeline: a skill supplies theme and producing cognition, the pipeline supplies the spine.

This is the modern, **de-YAML'd, publish-only rewrite** of the legacy `consolidate-state` +
the `_shared/` trio (`report-template` / `state-protocol` / `workflow-conventions`). The legacy
mandated report-sections and emitted YAML; this pipeline mandates none and publishes HTML
directly.

## The three phases

1. **pre-dispatch — assemble + delta + recall (ADR-0014), mechanically enforced (ADR-0016).**
   Before the producer reasons, the pipeline assembles the briefing (the prior consolidated
   state, Memento's tattoo), reads the world delta (what is new at the source keys), and renders
   the recall brief (the memory-salient subgraph of the Cortex, rooted at space-0 —
   `skills/recall`, never fused with delta). Three views, three subjects, three faithful agents.
   This is wake-context injection, not production. **The mechanical floor is the entry-driver**:

       tools/edge-python tools/predispatch.py

   It sweeps to currency (fail-loud store, ADR-0015), composes the briefing + the recall brief,
   stamps **`dispatch.open`** in the log and prints the machine-readable **`DISPATCH_ID=<id>`**
   line first on stdout (S2, E1 — carry that id into the artefato). The stamp is the teeth,
   and it is **identity-held**: the publisher refuses to publish unless the `dispatch.open`
   that MINTED the artefato's `dispatch_id` exists and is still unconsumed by a prior
   `artefato.published` — **no wake, no publish**, one wake per publish, and concurrent
   dispatches never spend each other's stamps (a legacy id-less publish falls back to the
   global newest-stamp check). Skipping this step dead-ends at the close. Delta stays agentic
   and is never stamped nor gated (ADR-0001/0011).
   The briefing also carries the **Voz pendente** section (`tools/voz.py brief` — bounded:
   counts + top-N one-liners): the mentee's undisposed votes/comments. The beat wakes HOLDING
   the pending Voz as a strong guide (theme-material when it aligns) — but a Directive is
   resolved by the GRILL, never by jumping the beat's rotation (ADR-0017/0018).

2. **producer-loop — the scaffold.** The producer fills the three role-defined slots of the
   shared scaffold (`skills/_shared/scaffold.md`): loop1 (`gather-grounding`: explorers →
   evidence) then loop2 (`converge` critic / `diverge` serendipity). The scaffold names roles,
   never report-specifics; the producer skill's mapping supplies the form. The scaffold is where
   the artefato is produced and tightened to a `ship` verdict.

3. **close — review → improve → publish.** The produced artefato passes the genus conformance
   contract, then the two blind reviewers — which return **per-dimension rationales** (the
   actionable FEEDBACK; the 0-5 score is advisory and never gates) and **strikes** (the
   qualitative gate). When an `improve_fn` is wired, the close runs `IMPROVE_ROUNDS` unconditional
   **review→improve** passes (the two improve-gates, one after the other) that revise the draft
   from that feedback BEFORE the gating review seals the proof — so what publishes is exactly what
   the reviewers passed. Then it publishes atomically with its kernel.

   Two sibling acts complete the close, right after the publish:
   - **the chamada** — append an `artefato.teaser` event (`{slug, text}`, ~3 short paragraphs,
     blog voice, same language as the artefato): the home's index renders it as the post's
     body. It introduces and invites the click — name the tension the artefato resolves and
     the payoff, never manufactured curiosity; the density stays behind the link.
   - **the Voz cycle** — dispose everything pending: `voz.close_cycle(answered={seq: slug})`
     (votes get their receipt; a comment this artefato answered closes with its ref; an
     unanswered comment gets a one-time receipt and stays pending), then
     `voz.assert_all_received()` — the fail-loud gate that no Voz was ignored without even
     a receipt. (Enforcement inside `close.run_close` plugs in when the conductor work in
     `tools/close.py` settles; until then this prose IS the contract.)

## The testable surfaces

The prose phases above bottom out in two testable modules in `tools/`:

- **`tools/close.py`** — the genus conformance contract (`check_genus`: output-enforced,
  sections FREE), the two blind reviewers (`feynman_review` rigor+honesty, `regular_review`
  clarity+craft+**frame-enrichment** — the outward vector: it STRIKES a closed internal
  diagnosis that names nothing in the field and brings no outside benchmark/best-practice to
  enrich the mentee's frame; both see content + cites only). Each verdict carries per-dimension
  `rationales` (the FEEDBACK) + `strikes`; the weighted `overall` is advisory and never gates (an
  LLM 0-5 score is too noisy to threshold). `run_close` adds the optional **improve stage**
  (`improve_fn`, `IMPROVE_ROUNDS`) before the bounded bounce (both reviewers must pass; a strike
  bounces to re-produce, capped at `BOUNCE_MAX`, then hard-fails — never unbounded). The
  producer-loop's brake (`run_loop2`, `LOOP2_MAX_REOPENS`) lives here too.

- **`tools/publisher.py`** — the atomic publish seam: render the artefato → self-contained
  neutral HTML → `publish_artefato_atomic`, which records the `artefato.published` event AND its
  `intent.kernel` in one act. Because the kernel rides in the same call, you cannot publish
  without the *why*: **C3 is enforced here** (the publisher raises with no intent, so
  `artefatos_without_kernel` is empty right after).

## The close lives at the skill's EXIT

The close is **not** the beat's job. It lives in this shared pipeline, at the **skill's exit**.
This honors **ADR-0008**: a **standalone** `/ed-report` — invoked directly, with no beat around
it — exits through the same close, so it observes the same review gates and the same atomic
publish. The lifecycle is never privileged to the beat; whatever runs the producer, the close
runs at its exit.

The bounce-bound (`BOUNCE_MAX`) and the loop-2 brake (`LOOP2_MAX_REOPENS`) live in the protocol
constants, never in the producer's discretion — that is what separates a gate from the
retry-envelope ADR-0003 killed.

## The improve-gates and cross-model help (codex)

The close is not only a gate — it **refines**. When the producer wires an `improve_fn`,
`run_close` runs `IMPROVE_ROUNDS` (default 2) **review→improve** passes before the gating review:
each pass reviews the draft purely for FEEDBACK (the per-dimension `rationales` + the `strikes` —
the noisy score never drives this) and hands it to the improve subagent, which **revises the
existing draft**, not re-produce from scratch. The two improve-gates run one after the other; the
gating review then seals the proof on the final, twice-improved artefato, so the reviewers' pass
is always of exactly what publishes.

**Wiring the re-production is what makes the floor force depth, not only hard-fail (#30).** Every
producer-skill MUST wire `improve_fn` (see each SKILL.md's close snippet): the genus contract now
carries the **rich-rite floor** (`check_genus` returns `rich-rite:<move>` strikes when a *developed
prose synthesis* lacks a cognitive move — derivation, the "what I don't know" boundary, an external
frame, lineage; content-relative, never a named section, never a word floor). Without an `improve_fn`,
a `produce_fn=lambda: artefato` is static, so any strike — a rich-rite floor violation included —
just bounces to the same draft and **hard-fails** after `BOUNCE_MAX`. With `improve_fn(art, feedback)`
wired, the `IMPROVE_ROUNDS` passes REVISE the draft from the named gaps BEFORE the gating close — so a
shallow report is **re-produced richer** (the missing move added) rather than dead-ending. The floor
is a depth-forcer because the re-production is wired; the gate alone would only reject.

The review and improve subagents — the **adversarial** blind pass, the **feynman** rigor
reviewer, the **enrichment** (frame / outward-vector) reviewer, and the **improve** reviser — MAY
reach for the **`/codex` skill** (the Codex CLI: a second, independent model) to pressure-test
their analysis, when `agent.yaml`'s `subagents.codex_assist.<role>` is true (all on by default).
Use it to challenge a claim, derive cross-model, or hunt the outside benchmark a frame-closed
draft is missing — the score is noise; a cross-model second opinion sharpens the *feedback*, which
is the signal.

## Producers round-robin; close-roles do NOT

The **producer-skills** are the open, round-robinable roster: the beat rotates strictly through
them, one turn each. The **close-roles** — the two reviewers and the publisher — are parts of
this shared protocol and are **NOT round-robinable**: they are not skills in the rotation, they
run at every producer's exit. Round-robin is for the producers; the close is the fixed gate they
all funnel through.

## The grounding floor at the close (S6)

Every producer's `close.run_close(...)` call **wires `floor_fn=harvest.close_floor`** (see each
producer SKILL.md's close snippet — the line rides beside `improve_fn`). Under the #61 split the
**publisher** runs that close, so it wires the floor as
`floor_fn=lambda: harvest.close_floor(session_id=main_session_id, child_session="")` — the `main_session_id`
from the brief points the floor at the MAIN's transcript and the cleared `child_session` keeps its teeth
(without it the child-session guard darks the floor out). The floor is a
`() -> list[str]` the wiring injects at the call-site (`close.py` never imports `harvest` — the same
injection idiom as `publish_fn`); a returned list is **genus-class** — summed into the gate's
`violations`, blocking-first, before the reviewers. `harvest.close_floor` reads the knob
**`EDGE_GROUNDING_FLOOR`** (default **`0=off` → `[]`**, byte-compat with today; `1=observe` counts
the would-be `grounding.floor` / `grounding.floor_dark` but never blocks; `2=gate` returns the named
violation on a **THEMED** dispatch that recognized **zero** source-reads). It is **fail-OPEN** (the
inverse of genus): out-of-session, undeclared geometry, or a child-session transcript → `[]` + a
counted `grounding.floor_dark`, never a close crash. Ambient geometry never gates (R3.2). Wiring the
kwarg is what lets the observe→gate rollout ride the #248 ladder purely by the knob — the genotype
carries the floor at 0 and nothing changes until the operator turns it up.

## The publisher subagent OWNS the close (Facet B, #61)

**The default publish path is delegation to the `publisher` subagent** (`.claude/agents/publisher.md`) —
this is not an optional form-only clerk anymore; the publisher owns the WHOLE `run_close`. Once the
producer has **SETTLED** the artefato (every claim already made, the rich context still in the MAIN's
window), it does **not** run `close.run_close` inline. It writes the settled spec + fields to **disk
pointers** and hands off to the publisher (via the Agent tool) with a **brief + disk POINTERS** — the
`conductor.py` node_briefs idiom, never a context dump: `{dispatch_id, main_session_id, skill,
intent_kernel, slug, spec_path, cites_path, proposes_path, distills_path, lineage_path}`. The publisher
runs the **whole close** in a clean process — the genus contract, the two blind reviewers, the
**mechanical** improve loop, the mint, the render, the atomic publish — and returns a typed **pull-channel**
`{status, slug, url, cost, residuals, rationales, bounce_reason}`. Moving the heavy publish machine off the
MAIN is the point: it **stalled the producer >4min inline**, and it never needed the rich context (the
close's rungs 4-5 are already context-denied).

**The wall still stands — the publisher is a tipógrafo of MECHANICS, never an author.** It receives the
spec ASSENTADO and never creates a claim, a cite, a proposal, or a sentence of substance — a claim born in
the publisher is a defect. What it owns is the **close machinery**, not the synthesis. So the bounce splits
by nature: a **FORM-only** leftover after the mechanical improve → **publish-with-residuals** (the S6 knob
`EDGE_PUBLISH_WITH_RESIDUALS`, the "Crítica não endereçada" section, graded not gated); a **SUBSTANTIVE**
strike — one that needs a re-derive, a missing factual anchor, a new claim, or a genus-floor violation —
**bounces to the author** (`status: bounced, needs author`), because only the MAIN holds the context to
re-found it. The MAIN re-produces and re-hands the pointers under the **same `dispatch_id`** (no re-wake —
the stamp is unconsumed, so re-publish under the same id still passes the identity-held gate).

**The floor keeps its teeth across the split.** The publisher runs as a child
(`CLAUDE_CODE_CHILD_SESSION` set) with a read-less transcript, so a naive `close_floor()` would go
always-dark — the very S6 grounding floor would lose its teeth. The brief's `main_session_id` cures it:
the publisher wires `floor_fn=lambda: harvest.close_floor(session_id=main_session_id, child_session="")` —
pointing the floor at the MAIN's transcript (where the reads live) and **clearing** the child guard.
Without `child_session=""` the floor re-darkens under the split (pinned in
`tests/test_publisher_floor_split.py`).

The proof, the kernel, and the atomic publish still belong to the enforced close (`run_close` →
`publish_fn`); the publisher just runs that close where the context is clean. Minting the proof in the
publisher is **sound**: the digest covers only content + identity fields (`{slug, spec, intent, cites,
proposes, distills, skill, lineage, dispatch_id}`), **no session/process field** — so it binds the spec
plus the `dispatch_id` that rode in the brief, wherever the close runs.
