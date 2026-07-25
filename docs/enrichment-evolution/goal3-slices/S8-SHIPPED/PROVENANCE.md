# S8 — SKILL.md reconciliation (R4) · local-verified

Reconciled the producer skills with the capability-conditional floor + grounding boundary:
- **map/SKILL.md**: node-edge layout is now a renderable `diagram`/`chart` first; `ascii-diagram` only as
  the logged degradation when `vl-convert` is absent; the `raw-html`/inline-SVG authored-visual option is
  REMOVED (ungroundable path, R2/R4). The worked example now emits a real `diagram` block + an explanatory
  paragraph (so it also models R0 explain-not-label). Vocabulary list reframed (diagram/chart-first).
- **plan/SKILL.md**: flow is a renderable `diagram` first; ascii-diagram as logged degradation; vocabulary
  list reframed; no raw-html/SVG authored-visual offered.
- discovery/report/research/critique: already clean (0 ascii-first / raw-html / SVG hits).

**R4 acceptance:** no producer SKILL.md presents ascii-diagram as a PRIMARY choice nor offers raw-html/
inline-SVG as an authored visual (verified by grep — remaining mentions are degradation/negation only).

## Iteration 2 — plan diagram-first (Codex S8)
Reworded plan flow so the step-sequence flow is a renderable `diagram` FIRST; next-steps-grid + flow-example are SUPPORTING structured blocks, not the alternative flow visual. Vocabulary list now leads with diagram.

## Iteration 3 — copyable examples (Codex S8)
The publish examples in both map & plan used inline `# ...` comments inside the backslash-continued `tools/edge-python -c "..."` string; the shell joins the continued lines so the `#` comments out the rest (verified: a test print never ran). Stripped all inline/full-line `#` comments from BOTH `-c` blocks so the examples are mechanically copyable; the surrounding prose already explains the fields. (Pre-existing pervasive pattern; fixed in the two R4-touched skills.) Both blocks now `#`-free.

## ✅ CODEX SHIP (verdict: approve) — R4 reconciliation complete; examples diagram-first + copyable.
