# S4 — discharge persistence (R9) · local-verified snapshot

**Slice:** S4 (R9): a finding RESOLVED in an earlier review round is stamped discharged and never
re-litigated in the same terms by a later round — the anti-livelock fix (roberto: 15 rounds, "saiu na
marra" = non-convergence from a flaky reviewer re-raising cleared strikes). Working tree only, no commit.

## Design
- **Discharge ledger** threaded through `run_close` (`tools/close.py`): a strike RAISED in round k but
  ABSENT in k+1 (the revision resolved it) is stamped `discharged`; a discharged strike RE-EMERGING in a
  later round — in the SAME terms (`_norm_strike`: whitespace-collapsed, casefolded) — is SUPPRESSED.
- Helpers: `_norm_strike`, `_round_strikes`, `_discharge_verdict` (removes discharged strikes; a verdict
  that failed ONLY on discharged strikes becomes passing; a NEW or unnamed-opaque failure is never cleared).
- Applied in BOTH the improve loop (issue-count + feedback) AND the gating close (before `_verdict_clean`),
  so convergence is real end-to-end (the gate is the final round of the same review).
- **Genus violations are deterministic and NEVER discharged** — all structural correctness stays gated.
- **Empty when no `improve_fn`** → direct close paths are byte-for-byte unchanged.

## Verification (red→green TDD)
- `tests/test_close_loop.py::DischargePersistsAcrossRounds`:
  - re-emergent (alternating A/B) strike → discharged → loop converges, gate mints + publishes (was: ran
    to IMPROVE_BACKSTOP → non-convergence). RED before, GREEN after.
  - persistent (always-raised) strike → never discharged → fails closed, never publishes (over-suppression guard).
- Full close suite 70 OK; internal_evidence 31, runstore 11, envconf 5 — all OK.
- The 18 env-dependent / pre-existing visual-coverage failures fail identically against HEAD close.py
  (proven by stash) — not caused by S4.

## Iteration 2 — gate authority restored (Codex S4 #1 [high])
Codex found a real soundness hole: discharge was a SINGLE-absence heuristic AND was applied at the
gating close, so one reviewer false-negative (A raised → flakily absent one round → discharged) could
permanently suppress a still-unresolved A re-raised at the gate and MINT a proof for it.
- **Fix:** discharge is now LOOP-ONLY. The gating close no longer discharges — it requires the CURRENT
  reviewers to be clean on every non-genus blocking finding. The gate is the backstop that catches a
  finding the loop discharged prematurely, so a genuinely-unresolved blocker can never mint.
- R9 now = improve-loop ANTI-CHURN (converge instead of running the receding target to IMPROVE_BACKSTOP);
  gate-level / cross-round semantic discharge for the authoritative mint is R5/S9's slice (the conductor).
- Tests reworked: (1) re-emergence stops loop churn (≤3 improve calls vs the cap); (2) Codex regression —
  flaky-absence then gate re-raise FAILS CLOSED, no publish; (3) persistent strike never discharged.
  Full close suite 71 OK.

## ✅ CODEX SHIP (iter-2, verdict: approve)
No material findings: the gate reviews UNSUPPRESSED verdicts and mints only when all current verdicts are clean; loop-only discharge cannot bypass it. (Codex sandbox could not run python — tests verified locally: close suite 71 OK, the 3 discharge tests green.) S4 COMPLETE — working tree only.
