# S9 — conductor CUT-with-reason + severity circuit-breaker (R5) · local-verified

`conductor.circuit_breaker(result, *, declined=None, render_ok=True)` partitions a run's unresolved
findings/violations into BLOCKING vs NON-BLOCKING and decides ship:
- **Fail-closed (blocking, never a residual):** any gate/genus violation, a synthetic-shape violation, a
  GROUNDING shortfall (R2), a render failure, and a SILENTLY-dropped assigned finding (correctness drop).
- **Logged residual (non-blocking, ships):** a dropped finding DECLINED with an accepted reason
  (`declined[fid]=reason`); plus non-blocking quality flags (form/opener).
A blocking item is NEVER declinable — `declined` only excuses a dropped finding the reviewer accepted;
structural failures are not declinable. status 'final' iff nothing blocking, else 'blocked' (fail-closed
even at the round cap). Conductor-altitude mirror of close's S1 severity; combines with R7 (cap) + R9
(discharge) for deterministic convergence.

## Verification (R5 acceptance)
- (a) a non-blocking declined-with-reason finding → ships final as a logged residual.
- (b) a blocking finding (grounding shortfall / genus / synthetic-shape / render / silent drop) → fails
  closed even at the cap; an empty/whitespace reason does NOT excuse a drop.
- 9 tests in tests/test_conductor_circuit_breaker.py; test_conductor / _lang / _slice3 green; blast radius 18.

## Iteration 2 — wired into run_conductor + structured decline (Codex S9, 2 findings)
- **[high] dead code**: circuit_breaker wasn't called on the conductor path. Fix: run_conductor now calls
  it before returning and merges ship/status/residuals/blocking into the result (declined= param threaded
  through; OFF passthrough carries a neutral final verdict). End-to-end tests: dropped findings → the run
  returns status 'blocked'; accepted declines clear them.
- **[high] decline laundering**: a bare string reason excused any drop. Fix: a drop is excused ONLY by a
  STRUCTURED record declined[fid]={reason, accepted:True, severity:'non_blocking'}; a bare string, an
  un-accepted decline, a 'blocking'-severity decline, or a whitespace reason all stay blocking.
- 15 tests (9 unit + OFF-shape + 2 e2e + bare-string/blocking-severity/unaccepted guards). conductor
  suites green; blast radius 18.

## Iteration 3 — reviewer-bound decline (Codex S9 trust boundary)
The caller-supplied `declined` param was self-attestation — a producer could launder its own correctness
drops. Fix: decline acceptance is now REVIEWER-BOUND. The semantic judge's verdict may carry
`decline:{accepted:true, severity:"non_blocking", reason:…}` per finding (`_parse_decline`, fail-closed);
`semantic_discharge` records carry it; `circuit_breaker` reads the per-node JUDGE discharge records in
`result['outline']` — NOT a caller param (the `declined` kwarg is removed; passing it raises TypeError).
A dropped finding is a residual ONLY if the JUDGE accepted it; else blocking. e2e: dropping judge → run
blocked; judge that drops-but-accepts → cleared to residuals. 16 tests; conductor suites green; blast radius 18.

## Iteration 4 — per-node gate failures block (Codex S9)
circuit_breaker now aggregates every non-empty per-node deterministic contract `gate` failure into blocking (gate:<id>:<violation>) — never declinable; a clean/accepted semantic discharge cannot clear a deterministic gate failure. Regression: a node with a non-empty gate but delivered discharge → blocked. 17 tests; blast radius 18.

## ✅ CODEX SHIP (iter-4, verdict: approve) — no structural escape; declines reviewer-bound. S9 COMPLETE.
