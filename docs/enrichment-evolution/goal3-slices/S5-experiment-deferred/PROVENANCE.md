# S5 — R0a A/B (single-writer vs fan-out) · DEFERRED RUNTIME EXPERIMENT (documented)

**Slice:** S5 (R0a). Per requirements & plan this is explicitly an **experiment, NOT a feature**
("experimento, não feature — orçar como tal; resultado alimenta a Fase C"). It is therefore NOT a
working-tree-only, codex-gateable code change — it requires the LIVE conductor (neo4j + the
~/edge-experiments venv + provider keys) run on identical material under two architectures, then scored.

## Why no code ships here
R0a's INVARIANT — "the final artefato passes R0(II) continuity, independent of architecture" — is ALREADY
enforced by the shipped **S2** (`_check_storytelling_floor` + the narrative_depth dimension). R0a only adds
the *hypothesis* that per-node WRITE fan-out fragments the narrative into a label-anthology and that
single-writer (fan-out on the GATHER only) fixes it. The requirement is explicit that single-writer is a
HYPOTHESIS to A/B-test, NOT a mandate to impose on suspicion — so the correct deliverable is the EXPERIMENT
PROTOCOL, run live, not a code gate.

## Experimental protocol (to run live, operator action)
Same source material; prompts / visual pressure / review controlled. Produce two artefatos:
  A = conductor with per-node WRITE fan-out (current);
  B = single-writer (fan-out on the GATHER only, one writer composes).
Score each with the S2 R0 gate + these continuity metrics (R0-II): connected-paragraph ratio,
unresolved-label count (visual labels never expanded in prose), transition-coverage (section boundaries
with a connective sentence), explanation density (non-label prose tokens ÷ inventory concepts).
**Decision rule:** if B moves the R0 metrics ABOVE A on the same material → the single-writer mandate
becomes structural (Fase C). Else the cause is elsewhere (prompt / visual pressure) and is fixed there —
do NOT force an architectural rewrite on suspicion (gate v-reframe F3).

## Status
DEFERRED to a live run. No working-tree code change; the R0a invariant is held by S2. This is the honest
treatment per the requirement (an experiment that decides architecture by EVIDENCE, not folklore).
