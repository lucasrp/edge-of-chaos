# Briefing lifecycle audit — what `state/briefing.md` MUST contain, per stage

The briefing (Memento's tattoo, ADR-0009) is the **only** thing the amnesiac beat orients from.
A section that is blank when it should be filled is a silent lobotomy — and today nothing in the
install (`_validate` → HEALTHY) asserts it. This audit is the **gate**: the `/goal` (a certified
edge) is not done until the briefing matches the per-stage expectations below, verified by review.

The load-bearing distinction issue #26 conflates: **`required` (bug if empty)** vs
**`expected-empty` (correct at this stage — the honest marker must render, never a crash or a silent
blank, and never a generic inference)**. A section is only a bug when it is `required` at that stage
and its feeder exists.

Stages: **(i)** fresh install (clone + `edge-apply --provision-runtime`, no grill, no beat) ·
**(ii)** + one simulated grill · **(iii)** + two beats in sequence.

| Briefing section | Feeder (source of truth) | (i) fresh | (ii) after grill | (iii) after 2 beats |
|---|---|---|---|---|
| **Initial tattoos — Personality** | genotype `memory/personality.md` or `.md.tpl` rendered w/ `agent.yaml` identity | **REQUIRED** | REQUIRED | REQUIRED |
| **Initial tattoos — Method** | genotype `memory/method.md` | **REQUIRED** | REQUIRED | REQUIRED |
| **Idiom** (mentee's terms) | genotype `state/idiom.md` / `CONTEXT.md` | **REQUIRED** | REQUIRED | REQUIRED |
| **Objective — the anchor** | `eventlog.objective_at()` (log) | expected-empty (honest marker) | **REQUIRED** (grill `set_objective`) | REQUIRED |
| **1. Direction** | `eventlog.direction_at()` (log) | expected-empty | **REQUIRED** (grill set/propose) | REQUIRED |
| **Direcionamento — rolling steer** | `eventlog.report_at()` (log) | expected-empty | **REQUIRED** (grill `report_direction`) | REQUIRED |
| **2. What is open / next bet** (kernel) | latest `intent.kernel` (log) | expected-empty | expected-empty (grill need not publish) | **REQUIRED** (latest beat's kernel) |
| **3. Corpus — what I already did** | `fold_corpus` (log) | expected-empty | expected-empty | **REQUIRED ≥2 Artefatos, each kerneled (zero C3 debt)** |
| **4. Source orientation** | `agent.yaml` sources + `state/source-roadmap.md` | **REQUIRED — the REAL declared roster, never a generic inference** | REQUIRED (+ curated source opinions if any) | REQUIRED (+ source-signals from beat cites) |
| **5. Knowledge clusters** | the graph (`curated_cluster`) | expected-empty on a fresh graph (curation is Voz-gated) | expected-empty unless the grill curated | expected-empty (curation is Voz-gated; not a beat output) |
| **6. Recap** | synthesized at assemble | slot/marker | present | present |

## The gate (acceptance per stage)

- **(i) fresh install** — FAILS the gate if any of {Personality, Method, Idiom, the real Source
  roster} is empty or generic. The log-fed sections (Objective/Direction/Direcionamento/Open-bet/
  Corpus) MUST render their **honest empty marker** (never crash, never a silent blank). This is the
  check `_validate` lacks today — HEALTHY must imply *the edge has an identity and knows its sources*.
- **(ii) after grill** — additionally FAILS if Objective, Direction, or Direcionamento is still
  empty (the grill's `set_objective` / `report_direction` must have fed them — issue #26's done-criterion).
- **(iii) after 2 beats** — additionally FAILS if Corpus has < 2 Artefatos, any published Artefato
  lacks its kernel (C3 debt), or the Open/next-bet is empty.

## Root causes this gate guards against (issue #26)

1. **Tattoos not injected** — `_section_tattoos` must emit non-empty Personality+Method; the `.tpl`
   render must not silently return empty when `agent.yaml` identity fields are thin (fail loud instead).
2. **Objective / Direcionamento empty *after a grill*** — the feeder (`set_objective`/`report_direction`)
   must run; empty-on-fresh is correct, empty-post-grill is the bug.
3. **Sources generic/stale** — the briefing must inject the **real** `agent.yaml` source roster (the
   never-blank floor), not a subagent's inferred categories; and `agent.yaml`'s `ground_truth` +
   source list must be current (the wiring #26 names as never done).
4. **No install-time identity assertion** — `_validate` must gain a `check_identity` that composes the
   briefing and asserts the stage-(i) REQUIRED sections are non-empty, so a lobotomized edge can never
   reach HEALTHY.

This file is the gate fed to `/codex:review`; the `/goal` closes only when the briefing meets it at all
three stages.
