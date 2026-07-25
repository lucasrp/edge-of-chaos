# S6 — capability-conditional visual floor (R1) · local-verified

R1, subordinate to R0 AND S7:
- **Descriptors** (producer_descriptor): map/plan floors now demand the RENDERABLE `diagram`/`chart`
  (ascii-diagram dropped from the types — S7). When `vl-convert` is PRESENT the floor requires a renderable
  visual (writer-unsat if absent → bounce); when ABSENT it degrades to ENV_UNSAT (NOT owed — the relation
  goes in grounded prose, never an ascii substitute). The existing evaluate_floor env-skip path carries it.
- **Subordinate to R0** (close.check_genus): the presentation (R1) floor does NOT fire while R0
  (storytelling) violations exist — don't fight render-vs-degradation on an artefato that already lost its
  storytelling; it re-surfaces once R0 is clean.
- **Subordinate to S7**: a renderable diagram counts for the floor but a renderable-but-UNGROUNDED diagram
  still fails `_check_visual_grounding` (the form is not enough).

## Verification
- `tests/test_floor_evaluator.py::test_visual_producers_owe_their_form_floor` — FLIPPED to R1: ascii no
  longer satisfies; vl-convert PRESENT → renderable required; ABSENT → not owed. 20 tests OK.
- `tests/test_floor_subordination.py` — 2 tests: presentation floor suppressed while R0 fails; surfaces
  once R0 clean.
- test_new_producer / test_publisher / close suites green; baseline 18 unchanged.
