# The shared producer scaffold

The producer-loop every producer-skill inherits (ADR-0012). A producer-skill — `report`,
`map`, `research`, `plan`, … — does **not** write its own loop. It inherits this scaffold,
supplies the theme and the producing cognition, and fills three **role-defined slots**. The
loop structure and the context-denial ladder are the same for every producer; only the slot
*content* differs.

This scaffold is **non-procrusto** by design: it names roles, never report-specifics. A `map`
producing a diagram and a `report` producing prose-and-charts run the **same** scaffold.

## The three slots are role-defined, NOT report-defined

The scaffold defines three slots by their **role** in the loop. It says what the role *does*,
never what a particular report-form *is*:

- **`gather-grounding`** — loop1's role: explorers go out and bring back evidence. The slot
  says "gather grounding," not "fetch this URL." Whether an explorer reads a paper, a repo, or
  a graph thread is the **producer skill's** decision. *How* an explorer reaches a world source is
  the same for every producer and is **never a per-source primitive** (ADR-0001): read the source's
  `via` spec in `agent.yaml` plus `state/source-roadmap.md` and call it **agentically** — the
  install's keys are already loaded. There is no `libexec/` primitive and there never will be; an
  explorer that cannot ground reports *which key it could not work*, never "a primitive is missing"
  and never waits for one to be built.
- **`converge`** — loop2's critic role: tighten, cut, and decide whether the artefato is ready
  to ship. The slot says "converge," not "check section order."
- **`diverge`** — loop2's serendipity role: look sideways for the connection the convergence
  would miss. Advisory only (see the brake below).

**Role-defined, not report-defined** is the load-bearing rule. The scaffold must never hard-code
report semantics into a slot — an explorer is a role, not a URL fetcher; a cite is a role, not a
hyperlink; and no section is ever mandated (sections are FREE; the scaffold names no section and
requires none). If the scaffold welded report semantics,
`map` and `plan` would have to fight it. Instead, **report-specifics live in each producer
skill's mapping** — the report skill maps `gather-grounding`→its explorers, `converge`→its
critic, `diverge`→its serendipity, and decides what a cite or a visual means **for that form**.
Those mappings live in the skill, never here.

## The loop structure

Two loops run inside the scaffold:

- **loop1 — explorers → evidence.** The `gather-grounding` slot fans explorers out; each returns
  evidence. loop1 is the grounding pass: it builds the pile of evidence the producing cognition
  reasons over. (Honoring the operator rename, the grounded material is named **evidence**.)

- **loop2 — critic / serendipity.** The `converge` slot's critic tightens the draft and emits a
  verdict carrying a `ship` boolean; the loop ends the moment the critic ships. The `diverge`
  slot's serendipity is **advisory** — it never gates. It may request a reopen of loop1, and the
  brake honors that request **at most `LOOP2_MAX_REOPENS` times** before the loop stops anyway.
  A critic that ships ends the loop immediately even while serendipity still wants to diverge —
  serendipity can never hold the loop hostage.

The brake is not the producer's discretion: it lives in the protocol. See `tools/close.py`
`run_loop2(artefato, critic_fn, serendipity_fn, reopen_fn)` — the testable spine that converges
on `critic.ship`, caps serendipity's reopens at `LOOP2_MAX_REOPENS`, and returns the final
critic verdict.

## The context-denial ladder

Each rung sees strictly less than the one before. **Freshness is evidence vs reasoning, not
cites vs no-cites** (ADR-0013): a later rung is denied the *evidence* and the *session* so its
read of the text is fresh, not because it lacks links.

1. **producer** — sees all (briefing + Mundo + session + evidence).
2. **serendipity** — `+briefing +Mundo`, `−session`.
3. **critic** — `−briefing`, `−session`.
4. **reviewers** — content + cites **only** (evidence, session, briefing all denied).
5. **publisher** — the final Artefato **only**.

The reviewers are blind by evidence-and-session (the blindfold): they re-source every claim from
its cite or strike it. The publisher writes the final Artefato atomically with its kernel — it
needs nothing but the finished thing. The close that runs the reviewers and the publisher lives
at the skill's exit, defined in `skills/_shared/pipeline.md`.
