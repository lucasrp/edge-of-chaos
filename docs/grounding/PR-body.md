# Grounding iteration — PR body (branch `feat/grounding-iteration`)

> The operator opens the PR (an ACT / write-to-world, HITL — per this project's own
> source-vs-act boundary). This file is the body to paste. NOTHING here is deployed:
> `edge-apply` runs only post-merge.

## What this shifts

Move the pipeline's centre of gravity **from the shape-on-output to the acquisition-on-input,
with a fixed ceiling on the output.** The grounding *manifest* is not EMITTED by the agent
(testimony) nor by a read-gate (chokepoint — cicatriz #248); it is **HARVESTED** from the
substrate's own execution record (the Claude transcript store), where the command that ran is
byte-identical and the result is parseable. There is no act of emitting to forget.

## The arc

`requirements.md` (Loop R: deep-research 37 agents, 14 findings adversarially verified + 3
empirical probes + 8 declared residuals) → **4 designs** → **design-amendments-r1** (E1-E8, gate
codex) → **9 slices** S1-S9 (each: TDD test-first green, codex-adversarial on the diff to only-nits,
commit).

### Requirements → 4 designs
- **design-emissao.md** — the emission seam. Design C won: harvest from the transcript substrate
  (not testimony, not a read-gate). Spine C + grafts A (attribution) / B (dry taxonomy, blindness).
- **design-yield.md** — the transparent bandit posterior (R4): revealed utility per source×interface,
  rendered as a table — advice, NEVER a router (the routing table died of #248).
- **design-close.md** — genus floor + publish-with-residuals (R5), all opt-in.
- **design-skills.md** — the genotype texts (glossary, scaffold slot, dig/calibrate, roadmap prose).
- **design-amendments-r1.md** — E1-E8 binding amendments from the codex gate on the designs
  (dispatch_id proof-bound E1/E1b/E1c; raw_ref BRUTE E2b; interfaces[] schema E3; dig event E4;
  Voz out of the roster E5; bounce counter E6; glob over all project dirs E7; **E8: a source is
  OPERATOR DATA, never a name in code** — the "Overleaf test").

### The 9 slices (one line each)
- **S1 — eventlog types + folds** (`65615934`, 44 tests, 5 gate rounds). New types
  `grounding.manifest/finding`, `canary.result`, `grounding.floor_dark`, `grounding.unmanifested`.
  `fold_grounding` (raw_ref E2b semantic-shape dedup; `supersedes` contends by (recognizer_rev, seq);
  two-factor B1 dry labeling; hits None never coerced to 0; excluded counted by reason) + cursor-aware
  `grounding_at`.
- **S2 — dispatch_id identity chain** (`21285aee`, 27 tests, 2 gate rounds). Predispatch mints a ULID
  and prints `DISPATCH_ID=` as the guaranteed first stdout line; `dispatch.open` carries id + session
  anchor + declared theme/intent/geometry; the id enters
  `proof_digest`/`_mint_proof`/`verify_proof`/`publisher.publish` (E1b: persisted=digested, like slug);
  canonical publish without it fails loud before any write (E1c); `wake_fresh_for(dispatch_id)` gates
  the publisher (phantom ids refused).
- **S3 — sources[].interfaces schema + acts** (`8a47e427`, 29 tests). Per-source structured
  `{interface_id, via, idiom, canary, dry_semantics}` (measured probe data as declaration); top-level
  `acts:` section (gdrive-upload HITL, rclone-not-MCP) — act-shaped entries are dropped from the read
  roster (no write-via can reach the S4 recognizers). `state/source-roadmap.md` REPLACED with the
  machine-readable skeleton from yaml truth (zero Voz — E5; seed yield rows with provenance).
- **S4 — harvest.py, o colhedor** (`c9ef99b3`, 226 tests, 14 gate rounds, impl=opus). The harvester
  derives 100% from `interfaces[].via` (E8 Overleaf test). `recognize()` pure; `harvest()` incremental
  cursor walk over ALL project dirs + subagents/; dispatch mapping by session anchor + interval
  (orphan when outside every interval, NEVER "last open"); `session_floor()` for S6. Invariants locked
  by adversarial gate: **A (no phantom)**, **B (no double-vanish)**, fail-closed on unparseable input.
- **S5 — predispatch harvest+canary+ambient** (`d41028ad`, 13 tests, 1 gate round, 0 defects). The
  wake floor GAINS two degrade-DARK legs (harvest, canary) that NEVER raise (R3.2: grounding annotates,
  never gates); `dispatch.open` stamped with `harvested`/`ambient_rows`.
- **S6 — close genus floor + publish-with-residuals** (`9361d177`, 23 tests, 2 gate rounds, defects
  1/0). Two grafts on the mint gate, both opt-in default-OFF: (A) genus floor via injected
  `floor_fn` (=`harvest.close_floor`), knob `EDGE_GROUNDING_FLOOR`; (B) publish-with-residuals on
  bounce exhaustion with a clean genus + real strikes — appends "Crítica não endereçada" before the
  mint, re-gates genus, `unaddressed` first-class in the proof/event. `EDGE_GENUS_BOUNCE_MAX` default =
  `BOUNCE_MAX` (single shared pool → byte-identical to HEAD).
- **S7 — yield join + table + panel** (`ae56f901`, 29 tests, 1 gate + completion, 0 blocking).
  `fold_grounding_yield`/`grounding_yield_at`: join manifest×source.signal by proof-bound dispatch_id →
  slug; ladder exact/coarse/ambiguous/orphan; graded reward (PURPLE, sim==0.0-no-embedder off mean_sim);
  `YIELD_POLICY` as DATA. Renders TWO surfaces only: the ≤6-line advisory briefing block (never-blank
  seed floor) and the `/sources` panel (observe rung, sibling of `/llm`). A test craves the absence of
  `choose_source`/argmax/router.
- **S8 — genotype texts** (`a89ebbe3`, impl=opus, consistency gate PASS 0 defects — **AWAITS operator
  voice-review**). `skills/dig/SKILL.md` + `skills/calibrate/SKILL.md` (new); CONTEXT.md `Grounding`
  verbete; scaffold gather-grounding paragraph; roadmap prose; `floor_fn=harvest.close_floor` wired
  into `run_close` in the 5 producers (closes the S6 pending dependency).
- **S9 — E2E smoke + PR body** (this slice). Real harvest over this machine's store (read-only, scratch
  cursor + scratch log), yield table + `/sources` panel rendered with real data, full suite. NO deploy,
  NO push, NO PR (the operator opens it).

## Knob map (all default OFF / observe — byte-compat guaranteed)

| Knob | Default | Values | Effect |
|------|---------|--------|--------|
| `EDGE_GROUNDING_FLOOR` | `0` (off) | 0=off / 1=observe / 2=gate | 0 → `close_floor` returns `[]` (no read, no event). 1 → counts the would-be violation (`grounding.floor` / darkness `grounding.floor_dark`) but NEVER blocks. 2 → returns the named floor violation on a THEMED dispatch with ZERO recognized source-reads. |
| `EDGE_PUBLISH_WITH_RESIDUALS` | `0` (off) | 0=off / 1=on | 1 → on bounce exhaustion with clean genus + real strikes, publishes-with-residuals (appends unaddressed critique before mint) instead of hard-fail. Required ON at verify-time too (no orphan proof). |
| `EDGE_GENUS_BOUNCE_MAX` | `= BOUNCE_MAX` | int | Separate genus-bounce counter. At the default it EQUALS `BOUNCE_MAX` → genus and reviewers SHARE the single `bounces` pool → byte-identical to HEAD. A disjoint pool manifests ONLY when raised above `BOUNCE_MAX` (declared opt-in, never silent). |

**Byte-compat guarantee:** with all knobs at default, `close`/`publisher` are **byte-identical to the
pre-iteration HEAD**. The S6 gate found and fixed a HIGH here (disjoint pools broke byte-compat); r2
confirmed byte-identical over 5 sequences. Every slice's `Verify` asserts the pre-existing suite stays
green modulo the same 8 unrelated failures.

## Rollout plan — the #248 ladder (everything is born observe)

The arqueologia lesson (`memory/`, the edge-of-chaos control monster): **telemetry first, gate last**.
Control of the search grew into a monster in 4 phases in one month / 217 commits (monolith → structure →
enforcement → confession #248). This iteration's rollout rides the antithesis ladder:

1. **observe rung** — the `/sources` panel. NO consumer, no router, no decision rides it. It just
   renders what was harvested. Ships live at default.
2. **advisory rung** — the briefing yield block. Advice tone (`- research → exa/search-deep: util 0.62
   (n=9, cited 5×)`), never a route. Becomes meaningful only AFTER the cells populate (~2 weeks of real
   dispatches crossing `min_attempts=5`); until then the never-blank SEED rows carry it.
3. **gate rung** — the genus floor rides `EDGE_GROUNDING_FLOOR` observe→gate. `0` ships. `1` (observe)
   is a ROLLOUT step post-S9, not a code default (a code default of 1 would break the byte-compat the
   verify itself asserts). `2` (hard-gate) is NEVER a default — an operator turns it on deliberately,
   after the observe telemetry has proven the floor fires only where it should.

**No hard-gate is default.** publish-with-residuals is opt-in. The genus floor is opt-in. The whole
iteration is byte-inert until an operator turns a knob.

## E2E smoke — REAL numbers (Deliverable 1)

Read-only harvest over this machine's real transcript store (scratch cursor + scratch log — the
repo's `state/` is untouched), scoped to the `-home-roberto*` project dirs. The harvester ran to the
500s cap mid-scan of this session's (very large) dir and still recognized **3 532 real reads** across
**all 8 declared sources**, deriving every recognizer from `agent.yaml interfaces[].via` (E8):

| source / interface | rows | note |
|---|---:|---|
| webfetch-native / native | 1 686 | harness pseudo-source |
| websearch-native / native | 1 594 | 727 hits harvested; **42 dry rows → seca-suspeita** |
| github / gh-cli | 199 | read-only CLI recognized |
| arxiv / api-query | 29 | |
| hn / algolia-search | 11 | |
| exa / search-deep | 7 | |
| gdrive-consortium / rclone-read | 4 | FROM-remote read (not the upload act) |
| x / v2-recent | 2 | |
| exa / contents | — | **DEAD LEG** (declared, no reads yet) |
| x / xai-responses | — | **DEAD LEG (declared WITHOUT key)** — the E8 visible dead leg |

**Blindness tally (`grounding.unmanifested`): 204** network-shaped calls not matched to a declared
source — the B2 leg is visible, never silent.

**Attribution: all 3 532 rows are `geometry=ambient`, `attribution=orphan`** — the honest result: the
pre-iteration transcript predates `dispatch_id`, so no read falls inside a dispatch interval and none
is scored. Exactly the expected shape (`excluded`: seca-suspeita 42; orphans/ambiguous/coarse/
unconsumed 0). Scoring cells populate once real dispatches (this iteration onward) carry the id.

The **`/sources` panel rendered** (1 797 chars, every source×interface row + the two dead legs +
the excluded/orphan footer) and the **never-blank briefing block rendered** the roadmap SEED rows
(exa named-entities, PMC/reCAPTCHA — marked `seed — prose, not measured`). **Nothing product-side
raised.** (A first pass hit a smoke-harness calling bug — passing the raw `load_sources()` tuple
instead of `declared_interfaces(sources)`; corrected by calling the route's own `sources_panel_html`
seam, confirming the panel path is sound.)

## Gate provenance

- **Rounds:** codex adversarial rounds 1-8, then **Opus-independent adversarial rounds 9+** (codex was
  rate-limited to Aug 1 — a substitute reviewer with the same invariant lens). S4 ran 14 rounds
  (1-8 codex, 9-14 Opus), defects-per-round `10/6/4/4/3/3/2/3/1/1/2/3/2/0` → only-nits (GATE PASS).
- **Invariant lens** for the harvest + close slices:
  - **A (no phantom):** a URL never fetched produces NO manifest row and NO blind tally
    (echo/comment/subshell/heredoc/flag-value URLs excluded).
  - **B (no silent double-vanish):** a URL that WAS fetched appears in at least one of {row, tally}.
  - **crash-safety:** unparseable input → blind tally, never a confident row; corrupt cursor →
    visible degradation, never a crash; the floor NEVER raises into the close (fail-open by design).
  - **byte-compat:** knobs-off → close/publisher byte-identical to HEAD (the S6 HIGH was exactly here).
- **Defects-per-round** live in the commit trailers of each slice (see `git log` above).
- **Accepted irreducible limitations** (A-vs-B tradeoffs, non-agent-typical shapes) documented in
  `docs/grounding/S4-known-limitations.md`: (1) pipe-fed `echo URL | xargs curl` (vanishes from both —
  tallying it would resurrect every echo phantom); (2) `exec -a NAME curl` exotic residual (fails
  closed, a DROP never a phantom).

## Two OPEN operator decisions

1. **`grounding.finding` — a 3-way contradiction.** `design-skills.md §1` says `dig` writes NO event
   (topic file only); BUT `plan §S8` + amendment E4 + the built substrate (`eventlog.py`,
   `grounding.finding` type declared in S1) all expect `dig` to emit a `grounding.finding` event (the
   topic file as its projection). S8 shipped FAITHFUL to §1 (no emission). **Recommendation: emit
   `grounding.finding`** — the substrate is already built for it and E4+plan agree; §1 looks like the
   stale draft. Operator's call (1 line of reconciliation).
2. **S8 genotype line-by-line voice-review is still owed.** The genotype texts (prose that shapes the
   agent) passed the mechanical/functional/fidelity consistency gate (0 defects) but NOT Lucas's
   line-by-line voice review. The S8 commit is explicitly marked `AWAITS operator voice-review`. Also a
   NIT flagged there: the verbete says "PRISMA C36" but `requirements.md` attributes C36 to
   MECIR/Cochrane (inherited verbatim from the draft — a voice call).

## Test totals

- **harvest (S4):** 226 tests.
- **close + floor + residuals (S6):** 23 tests.
- **predispatch / canary (S5):** 13 tests.
- **yield (S7):** 29 tests.
- **eventlog folds (S1):** 44 tests. **dispatch_id (S2):** 27. **sources schema (S3):** 29.
- **Full suite:** green modulo the **8 pre-existing unrelated failures** (publisher genus-contract ×4,
  frontend UX, identity seam, llm transport, venv pin) — byte-identical to the pre-iteration baseline.

```
8 failed, 2184 passed, 27 skipped, 164 subtests passed in 107.79s
```
The 8 failures are the pre-iteration baseline (publisher genus-contract ×4, frontend UX `--accent`,
identity env-read seam, llm transport-error, `vl-convert-python` unpinned) — none in the grounding
surface, confirmed identical to HEAD via stash-control at S4.

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
