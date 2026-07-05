# The beat is a pure round-robin scheduler; one shared pipeline carries every producer skill

The beat holds **no judgment** — it is a **pure round-robin scheduler** over the producer-skills
`[report, map, research, plan, …]`, carrying only rotation state (whose turn it is). **Theme-choice
and production belong to the skill, not the beat:** when a producer's turn comes it points itself at
the most Worthwhile theme against Direction + delta, then produces. The whole dispatch is **ONE
shared pipeline definition** — a single file, outside the skills — that every producer funnels
through: **pre-dispatch** (assemble + delta) → **producer-loop** (the shared scaffold) → **close**
(review gate + publisher). This **amends ADR-0004**: it *evacuates* judgment from the beat (0004's
loop chose-theme-and-produced; now the skill does both), and it **honors ADR-0008** — the close at
the skill's exit observes the same effects a standalone `/ed-report` does.

## Status

proposed (2026-06-08; Close-architecture rewrite, Story S4)

## Context

- ADR-0004 fanned the beat into assemble / delta / loop subagents, with **the loop carrying the
  judgment** — it chose the Worthwhile theme *and* produced the one Artefato. Two problems surfaced
  in the Close rewrite:
  - **The beat conflated scheduling with judgment.** One loop deciding *what to make next* makes
    breadth a function of that loop's taste; over many beats the rotation narrows to whatever the
    loop favors. Breadth should come from **rotation**, aim from **Direction** — two different
    organs, welded in 0004.
  - **There was no shared lifecycle across producers.** A `report` and a `map` each re-implement
    read-the-world, produce, review, publish. The legacy `consolidate-state` + `_shared/` trio was
    the only common ground, and it was a YAML-driven monolith.
- ADR-0008 already moved digestion to a **pull-at-open sweep** and **absorbed `consolidate`**, so
  the close-time act is no longer "consolidate the session" — it is **publish the Artefato**. The
  close pipeline can therefore be thin: review + publish, with session-digestion already handled
  upstream by the sweep.
- ADR-0003 killed the artifact-supervisor **retry-envelope**. A bounce-bound that lives in the
  *protocol* (a fixed gate with a bounded bounce) is a different construct from that retry loop — it
  is a gate, not a re-invocation rail — and is what keeps the close from drifting back into 0003's
  envelope.
- The Idiom already names the **Artefato** as the genus of output and **Direction** as the aim; the
  rewrite needs only to redraw *who schedules* and *what is shared*, adding no new glossary entity.

## Considered options

- **Keep the 0004 judgment-loop beat.** Simplest continuity. **Rejected:** the loop's taste governs
  breadth, and there is still no shared lifecycle — each producer re-implements the close.
- **Beat schedules *and* picks the theme (round-robin + central pointing).** The beat rotates but
  also aims each turn. **Rejected:** aim is producer-specific (a `map`'s Worthwhile theme is not a
  `plan`'s); centralizing it re-imports judgment into the scheduler — the very weld being cut.
- **Pure round-robin beat + theme-choice-in-skill + ONE shared pipeline.** The beat is rotation
  state only; each producer points itself when its turn comes; all producers funnel through one
  pre-dispatch → producer-loop → close definition. **Chosen:** breadth from rotation, aim from
  Direction, and a single legible lifecycle every producer inherits.

## Decision

- **Beat = pure round-robin scheduler.** It carries only rotation state (whose turn) over the
  producer-skills `[report, map, research, plan, …]`. **Strict round-robin:** the moment does not
  jump the queue. The beat makes **no semantic judgment** — it never chooses a theme and never
  produces. This **amends ADR-0004**, which had the loop carry the judgment: judgment is *evacuated*
  from the beat into the skill.
- **Theme-choice + production belong to the SKILL.** When a producer's turn comes, the skill points
  itself at the most Worthwhile theme against **Direction + delta**, then produces. **Breadth comes
  from the rotation; aim comes from Direction** — two organs, no longer welded.
- **ONE shared pipeline definition.** A single file, **outside the skills**, defines the lifecycle
  every producer funnels through:
  - **pre-dispatch** = assemble + delta (the briefing seams of ADR-0004, kept).
  - **producer-loop** = the **shared scaffold** (below).
  - **close** = the review gate (ADR-0013) + the publisher.
  This is the de-YAML'd, publish-only rewrite of the legacy `consolidate-state` + `_shared/` trio.
- **Scaffold compartilhado with role-defined slots.** loop1 (explorers → evidence) + loop2
  (critic / serendipity) are **shared scaffold** every producer inherits. The skill fills
  **role-defined slots** — `gather-grounding` / `converge` / `diverge` — and supplies the theme +
  the producing cognition. **Slots are role-defined, NOT report-defined:** the scaffold must not
  hard-code report semantics (explorer = URL fetch, cite = link), or `map` / `plan` fight it.
  Report-specifics live in the report skill's mapping of the slots, never in the scaffold.
- **The close lives at the skill's EXIT, not in the beat.** It is part of the shared pipeline, run at
  every producer's exit — **honoring ADR-0008** (a standalone `/ed-report` observes the same close;
  the lifecycle is not privileged to `/ed-beat`). The **bounce-bound lives in the protocol**, never
  in the producer's discretion — that is what separates a gate from the retry-envelope ADR-0003
  killed.
- **Producers = skills (open roster).** Importable, independently invocable, round-robinable.
  **Close-roles** (reviewers, publisher) = parts of the **shared protocol**, **not** round-robinable.
- **Artefato genus = the conformance contract (output, enforced).** Every producer's output is an
  Artefato that **cites / proposes / distills / kernel** (pinned against the real
  `eventlog.publish_artefato` + `kernel` signatures) **+ visual coverage + genus-properties**.
  **Sections are FREE** — the contract is on the properties and the kernel, never on a section order.
- **Publisher = `consolidate-state` minus session-digestion** (ADR-0008 moved digestion to the
  pull-at-open sweep), **de-YAML'd**. It is **atomic:** write `blog/entries/<slug>.html` →
  `publish_artefato + embed_and_signal + kernel` in **one atomic act** — you cannot publish without
  the kernel.
- **C3 enforced at the publisher.** Because publish-and-kernel are one atomic act, **C3** (no
  Artefato without its kernel) is enforced here: `eventlog.artefatos_without_kernel()` **blocks**
  (not warns) and `publish_artefato` **requires** the kernel in the same call.

## Consequences

- **Breadth is structural, not discretionary.** Rotation guarantees every producer gets its turn;
  no single loop's taste can starve `map` or `plan`. Aim stays sharp because each skill points
  against Direction when its turn comes.
- **One lifecycle to reason about.** Adding a producer means writing a skill that fills the three
  slots — the pre-dispatch, the scaffold, the close, and C3 come for free from the shared pipeline.
- **The close is uniform and dispatch-agnostic.** A heartbeat beat and a manual `/ed-report` run the
  identical review-and-publish exit, consistent with ADR-0008's "lifecycle belongs to the dispatch,
  not to `/ed-beat`."
- **C3 cannot be skipped.** The atomic publish-and-kernel act makes a kernel-less Artefato
  unpublishable; the blocking `artefatos_without_kernel()` is the backstop.
- **Cost: the scaffold must stay genus-general.** Any report-specific in the shared scaffold makes
  the non-report producers fight it (the procrustean failure). The mitigation is the role-defined
  slots — report-specifics live only in the report skill's slot mapping. This is a standing
  discipline, not a one-time fix.
- **Amends ADR-0004** (evacuates judgment from the beat; the beat becomes rotation state, the skill
  carries theme-choice + production). **Honors ADR-0008** (the close at the skill's exit observes
  the pull-at-open digestion contract; session-digestion is *not* re-added to the publisher).
  **Consistent with ADR-0003** (the protocol's bounded bounce is a gate, not the retry-envelope),
  **ADR-0006** (the publisher writes the log; pages are projections), and **ADR-0013** (the close's
  review gate is the blind, property-not-section verification).

## Amendment — ticket 05 (2026-07-05): the 3-act flow supersedes the PURE-scheduler beat

The operator's three-act split (`docs/agencia/implementacao/05-fluxo-3atos-multiartefato.md`)
kills the monolith this ADR still assumed (one grounding → one close). The beat is now the
**trunk of ato-1**: grounding inicial → an explicit **PROPOSTA** (WHICH artefatos, 1..N, why —
the plan-side gates —, each with its angle), then **one branch agent per artefato**, each doing
its **own grounding rounds** and exiting through this ADR's **unchanged shared pipeline** at its
own exit. What survives intact: the ONE shared pipeline, the close-at-the-skill's-exit
(ADR-0008), C3, the bounded bounce, and `_beat.next_producer` — the rotation cursor demoted to a
**breadth prior / tie-breaker** inside the proposal, no longer the sole selector. What is
superseded: "the beat makes no semantic judgment" — ato-1's proposal IS judgment, now grounded
and gated (VoI/é-real/é-pra-ele) instead of a taste-driven loop (the 0004 failure this ADR cut;
the cure is the gated proposal, not the blind rotation). See `skills/beat/SKILL.md`.
