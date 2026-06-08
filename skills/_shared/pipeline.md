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

1. **pre-dispatch — assemble + delta.** Before the producer reasons, the pipeline assembles the
   briefing (the prior consolidated state, Memento's tattoo) and reads the world delta (what is
   new at the source keys). This is wake-context injection, not production.

2. **producer-loop — the scaffold.** The producer fills the three role-defined slots of the
   shared scaffold (`skills/_shared/scaffold.md`): loop1 (`gather-grounding`: explorers →
   evidence) then loop2 (`converge` critic / `diverge` serendipity). The scaffold names roles,
   never report-specifics; the producer skill's mapping supplies the form. The scaffold is where
   the artefato is produced and tightened to a `ship` verdict.

3. **close — reviewers + publisher.** The produced artefato passes the genus conformance
   contract, then the two blind review gates, then is published atomically with its kernel.

## The testable surfaces

The prose phases above bottom out in two testable modules in `tools/`:

- **`tools/close.py`** — the genus conformance contract (`check_genus`: output-enforced,
  sections FREE), the two blind reviewers (`feynman_review` rigor+honesty, `regular_review`
  clarity+craft — both see content + cites only), and `run_close` (the bounded bounce: both
  reviewers must pass; a strike bounces to the producer to re-produce, capped at `BOUNCE_MAX`,
  then hard-fails — never unbounded). The producer-loop's brake (`run_loop2`,
  `LOOP2_MAX_REOPENS`) lives here too.

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

## Producers round-robin; close-roles do NOT

The **producer-skills** are the open, round-robinable roster: the beat rotates strictly through
them, one turn each. The **close-roles** — the two reviewers and the publisher — are parts of
this shared protocol and are **NOT round-robinable**: they are not skills in the rotation, they
run at every producer's exit. Round-robin is for the producers; the close is the fixed gate they
all funnel through.
