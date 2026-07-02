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
