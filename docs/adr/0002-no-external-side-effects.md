# Affirm Contract C1 (no external side effects) under agentic-first

Going agentic ([ADR-0001](0001-agentic-delta-not-primitive-per-key.md)) makes *acting in the
world* mechanically possible in the rebuild for the first time. We **affirm Contract clause C1
(no external side effects)** as the one line that "everything agentic, vemos depois" does
**not** defer. The canonical invariant lives in [`CONTRACT.md`](../../CONTRACT.md#c1--no-external-side-effects);
this ADR records *why it is fixed from the start*, not restated here.

## Status

accepted

## Why this one isn't deferred

"Everything agentic, vemos depois" (ADR-0001) defers *capability* guardrails — gates,
determinism, reproducibility. C1 is a different kind of thing: it is **identity, not
reliability**. Going agentic is exactly when an unattended 3h beat is one bad tool-call away
from editing the mentee's repo, so the line is fixed now, not "later". Recording it here stops
a future change from quietly treating "the agent can write" as a feature rather than a
violation of what the edge *is*.
