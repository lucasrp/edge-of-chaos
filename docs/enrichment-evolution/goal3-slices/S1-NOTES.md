# Goal 3 / S1 — review loop (R7) + severity (R5)

## Increment 1 (DONE, tests green): R7 marginal-gain loop
- `tools/close.py`: the improve stage was a fixed `for _ in range(IMPROVE_ROUNDS=2)` unconditional
  loop. Replaced with the R7 contract: iterate **while each round gains** (changes the draft), stop
  on a **plateau** (a round whose revision == input = marginal gain 0), bounded by
  **`IMPROVE_BACKSTOP=8`** only against divergence. `improve_rounds` param repurposed as the backstop
  override. (close.py: constant + loop + docstring.)
- `tests/test_close_loop.py`: the old `test_improve_fn_runs_improve_rounds_times` pinned the
  fixed-2 premise R7 overturns → replaced by three contract tests: **plateau-stops** (1 no-gain
  attempt), **continues-while-gaining** (runs 4 > old 2), **divergent-hits-backstop** (bounded at 8);
  `test_improve_rounds_is_overridable` → `test_improve_rounds_overrides_the_backstop`.
- **Verified:** `python3 tests/test_close_loop.py` → 38 ok. Close-dependent suites green
  (reviewers, producers, floor_evaluator, pipeline_def, adr_close). `test_visuals` has 9
  PRE-EXISTING failures (chart/diagram render domain — fail identically against committed close.py;
  scoped to S7, not S1).

## Increment 2 (NEXT): severity classifier + ship-with-logged-residual (R5)
- After the loop plateaus with remaining strikes: classify severity — blocking
  (correctness/evidence/grounding/render-fail **+ R0-class**) **fail-closed** (current default);
  only **non-blocking** → ship-with-logged-residual. Genus violations are inherently blocking.
  Design point: strikes need a severity tag (default = blocking for safety).
- Then `/codex:review` gate (full iteration) over the whole S1.
