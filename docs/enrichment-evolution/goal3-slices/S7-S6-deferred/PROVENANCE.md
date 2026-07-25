# S7 (R2/R3 grounding boundary) + S6 (R1 capability floor) · DEFERRED, documented (operator decision)

Deferred from this working-tree session with a precise design + the concrete blockers. S6 depends on S7
(plan sequence `… → S7 → S6 → …`), so both defer together. This is the honest call per the operator
cadence rule (decide/document when a slice can't be cleanly resolved here) — mirrors the S5 deferral and
the R8-prov residual.

## Why deferred (not a silent skip)
1. **High blast radius / coordinated migration.** R2 is DEFAULT-DENY: EVERY authored reader-visible
   claim-bearing visual (owed OR optional) must carry an unforgeable grounding attestation or be banned.
   Wired as a `check_genus` guard it fires on every DIRECTLY-authored chart/table/metrics-grid/diagram —
   17 test files build exactly those and expect clean genus, and every non-conductor producer authors
   visuals directly. Landing it safely needs the plan's coordinated migration, not a working-tree add.
2. **P1 dependency unverified.** The plan flags "S7a depende de a evidência do explorer chegar à montagem
   do spec — verificar P1." The grounding seam (`visuals.add_visuals`) runs ONLY in the conductor path;
   the single-producer default path authors visuals with no evidence pipeline at spec-assembly. Verifying/
   building that evidence flow is prerequisite and not doable offline here.
3. **The conductor path is ALREADY grounded.** `_existing_drawn_visuals` + `_assert_no_drawn_visuals`
   enforce "no drawn visual before add_visuals"; `add_visuals` splices ONLY `attributable()`-passing
   visuals; the close proof DIGEST binds the spliced spec (no post-mint swap). So R2's exposure is the
   SINGLE-PRODUCER directly-authored visual — exactly the high-blast-radius part.

## S7 design (ready to build, post-P1)
- **Per-visual unforgeable attestation (R2):** a process-private grounding secret (`secrets.token_hex`);
  `add_visuals` mints `block["_grounding"] = HMAC(secret, canonical(block − _grounding))` ONLY when
  `attributable()` passes (already gated). A new `visual_grounding.py` (imported by both close and visuals,
  no cycle) holds `_SECRET`, `attest(block)`, `verify(block)`, `is_claim_bearing(block)`.
- **Default-deny guard (R2):** `close._check_visual_grounding(content)` in `check_genus` — every
  reader-visible CLAIM-BEARING visual (visual palette + data tables; raw-html/svg NEVER decorative; only a
  mechanical decorative-allowlist of label/number/edge-free blocks is exempt) must `verify(block)`; else a
  `visual-grounding:<type>` violation. Runs at the publish path (publisher calls check_genus) and respects
  the ADR-0013 blindfold — HMAC verify needs only the secret + block data, NO evidence. Provenance, not a
  self-consistent digest (closes the gate-reframe-4 F1 gap).
- **R3 ascii-edge grounding:** `attributable()` already grounds chart/diagram chrome + edges; extend the
  attestation to cover the `ascii-diagram` fallback so its nodes/edges resolve to evidence EVEN when
  `vl-convert` is absent (content validity is never capability-gated — only render is).
- **Migration:** thread explorer evidence to spec assembly (P1); route directly-authored producer visuals
  through the grounding seam (or ground+attest them in-place); update the ~17 fixtures to grounded+attested
  visuals (the expectation flip is the proof of the fix, exactly as R1's `test_visual_producers_owe_their
  _form_floor` flips).

## S6 design (after S7)
- `producer_descriptor`: with `vl-convert` present, a `ascii-diagram` type-fallback does NOT satisfy the
  primary `min_blocks_of` floor — the floor demands the RENDERABLE `diagram`/`chart`; ascii satisfies only
  when the backend is ABSENT (logged degradation). Subordinate to R0 (the floor doesn't fire while R0
  fails) AND to S7 (a visual only counts if it survives the grounding guard). Red test: with vl-convert
  present + R0 satisfied + grounded — map+2×ascii FAILS, plan ascii-only FAILS, both with a renderable
  grounded diagram PASS, a renderable-but-ungrounded diagram FAILS. Flip `test_visual_producers_owe_their
  _form_floor`.
