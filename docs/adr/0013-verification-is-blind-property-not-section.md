# Verification is blind by evidence-and-session; the gate checks a property anywhere, not a named section

The close's verification runs **two blind review gates on the FINAL Artefato text** — a **feynman
reviewer** (rigor + honesty) and a **regular reviewer** (clarity + craft) — both seeing the
`Artefato.content + cites` **only**, denied the evidence and the session. The load-bearing principle
is **property-not-section:** each gate checks whether a **property is present anywhere** in the text,
**not** whether a named **section** exists; sections are free (ADR-0012). The legacy 9-dim review is
cut to **7 KEPT dims** (`content_depth`, `feynman_method`, `intellectual_honesty`, `didactic_clarity`,
`internal_consistency`, `visualization`, `writing_quality`) with **2 DROPPED** (`structural_completeness`
and `storytelling` — both welded to the report-form), and the freed weight rebalanced. This is
consistent with ADR-0012 (the close at the skill's exit) and with the blindfold principle of the Bet-A
Artefato.

## Status

proposed (2026-06-08; Close-architecture rewrite, Story S4)

## Context

- The legacy review-gate (`tools/review-gate.py`) scored an Artefato on a `DIMENSIONS` table —
  **9 dims with weights** in the code (the markdown doc's "6" is stale; **the code is truth**).
  Several dims were **welded to the report-form**: `structural_completeness` mandates a section order;
  `storytelling` mandates a narrative arc; `intellectual_honesty` literally references an
  `"O que Não Sei"` **section**. ADR-0012 freed sections, so a section-mandate is now a category
  error — a `map` or a `plan` has no such sections and would be falsely failed.
- The Bet-A Artefato established the **blindfold:** *the reviewer must be denied what the author had.*
  Freshness is **evidence vs reasoning**, not cites-vs-no-cites — a reviewer who sees the evidence
  can wave through a claim the text itself never derives.
- The rewrite needs a verification that is **genus-general** (works for every producer, not just
  report), **honest** (a vent cannot pass as a derivation), and **blind** (the reviewer re-sources
  every claim from the text + its cite, not from the author's context). No new glossary entity is
  introduced — this redraws *how* the existing review gate (ADR-0012's close) judges.

## Considered options

- **Keep the 9-dim, section-checking review.** Continuity. **Rejected:** the section mandates and the
  narrative-arc dim are welded to report-form; under ADR-0012's free sections they false-fail every
  non-report producer.
- **Drop the review gate entirely (trust the producer).** Cheapest. **Rejected:** it reinstates the
  author grading their own work in the same window — the failure the blind gate exists to remove —
  and lets a vent ship as a derivation (the Zep failure, one floor up).
- **One blind gate on rigor only.** Simpler than two. **Rejected:** rigor and craft are different
  apertures; folding them collapses "is this true and derived" into "is this well-written," and one
  masks the other.
- **Two blind gates, property-not-section, 7 KEPT / 2 DROPPED dims.** **Chosen:** genus-general
  (checks properties, not sections), honest (the feynman gate's blindfold), and decomposed (rigor and
  craft judged separately).

## Decision

- **Verification is blind by evidence-and-session.** Freshness = **evidence vs reasoning**. Both
  gates see the **final `Artefato.content + cites` only**; they are denied the **evidence** and the
  **session**. This sits on a **context-denial ladder:** producer (all) → serendipity
  (+briefing +Mundo, −session) → critic (−briefing, −session) → reviewers (content + cites only) →
  publisher (final Artefato only).
- **Two blind review gates on the FINAL text** (both must pass; a strike **bounces to the producer**,
  bounded by the protocol per ADR-0012):
  - **feynman reviewer (rigor + honesty):** simple explanation, first-principles derivation, explicit
    uncertainty — mark each claim **derived** vs **repeated** vs **unknown** — and the **blindfold:**
    every claim must be **re-sourceable from its cite** or it is struck.
  - **regular reviewer (clarity + craft):** substance, didactic clarity, flowing prose, internal
    consistency.
- **PROPERTY-NOT-SECTION (the load-bearing principle).** Each gate checks whether the **property is
  present anywhere** in the text, **not** whether a named **section** exists — sections are free
  (ADR-0012). The legacy dim defs are reworded from *"section X present"* → *"property X present
  anywhere, genuine + specific."* Two **twin properties** are blocking:
  - **honesty / knowledge-boundary:** is uncertainty + the derived/repeated/unknown boundary
    **explicit, specific (not boilerplate), and location-agnostic**? **Absent OR boilerplate →
    block.**
  - **clarity:** is every term comprehensible **somewhere** (not "does a glossary section exist")?
  (The legacy `intellectual_honesty` referenced the `"O que Não Sei"` **section** — this unwelds it
  into a property checkable anywhere.)
- **KEEP 7 dims (genus / universal):** `content_depth`, `feynman_method`, `intellectual_honesty`,
  `didactic_clarity`, `internal_consistency`, `visualization`, `writing_quality` — the last with its
  prose-bias **softened** so a visual Artefato is not penalized for being non-prose.
- **DROP 2 dims (welded to report-form):** `structural_completeness` (the section-order mandate) and
  `storytelling` (the narrative-arc mandate). **Rebalance weights:** the dropped ~27% (structural 15
  + storytelling 12) redistributes across the 7 kept dims.
- **`visualization` KEPT and explicit** (operator: *"eu gosto de gráficos"*), made **content-relative**:
  *"did you visualize what the content deserved?"* (a `map` is visual by nature; `plan` → flow /
  timeline; report → charts when 3+ values). It stays **blocking**, but phrased as *"no viz where the
  content clearly warranted it"* — so a genuinely non-visualizable Artefato is **not** false-failed.
- **Cross-provider review allowed:** producer on `chat` (OpenAI), reviewers on `review` (Grok) —
  model-blindness atop context-blindness. Config in `agent.yaml` (already wired).
- **Loop-2 brake (advisory, bounded):** the **critic converges**; **serendipity does not** — it is
  **advisory, never a gate**, and may re-open loop 1. It is bounded by a max-rounds / explicit
  *"ship"* verdict / diminishing-returns brake so loop 2 cannot spin.

## Consequences

- **Genus-general verification.** Checking properties, not sections, lets one gate judge a `report`,
  a `map`, and a `plan` alike — no producer is false-failed for lacking a report's sections.
- **Honesty is enforced, not hoped for.** The feynman blindfold strikes any claim not re-sourceable
  from its cite, and the honesty twin blocks absent-or-boilerplate uncertainty — a vent cannot ship
  as a derivation.
- **Visuals are first-class but not coerced.** A content-relative `visualization` dim rewards the
  `map`/`plan`/charts that the content deserved without false-failing a genuinely non-visualizable
  Artefato.
- **The cut is grounded in the real code.** Dropping `structural_completeness` + `storytelling`
  removes exactly the report-welded dims; rebalancing their ~27% keeps the kept dims comparable in
  scale.
- **Cost / open item:** the loop-2 brake's exact stop condition (max-rounds vs diminishing-returns vs
  explicit ship verdict) is pinned during implementation — serendipity must stay advisory and
  bounded, never a gate that spins the close.
- **Consistent with ADR-0012** (this is the close's review gate at the skill's exit; the bounded
  bounce is the protocol's, not the producer's), the **Bet-A blindfold** (the reviewer is denied what
  the author had), and **ADR-0008** (session-digestion already happened at open, so the reviewers are
  cleanly denied the session here).
