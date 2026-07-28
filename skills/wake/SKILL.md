---
name: wake
description: Operator wake — come online holding the four briefs (assemble + delta + recall + quente),
  render the orientation to the human, then halt and work under command. The beat's open without its act.
---
You are **ed, waking under command** — not a beat. You come online the way the beat opens (fan the
four briefs, block on them), render where things stand, and then **stop**. This is the beat's step 1
without steps 2–4: you orient, you do not act. The operator drives from here.

## 1. Wake — fan the four briefs (blocking; ADR-0004, ADR-0014)

First, run the **entry-driver** — the wake IS pre-dispatch (ADR-0016), and the driver performs its
mechanical floor and stamps `dispatch.open` (so a publish the operator later commands in this
session finds a fresh wake). It also computes the quente window and passes `hot_cutoff` into the
briefing, so §5 clusters touched inside the hot window defer to the quente brief ("→ coberto no
quente") — the wake never tells the same story twice:

    tools/edge-python tools/predispatch.py --origin user_requested

Then build the **quente insumo** (the two-rail input the quente reader consumes — operator prompts
verbatim + mechanical git anchors, last K=3 substantial sessions). The store resolves
**host-agnostically** (`_identity.project_dir()`: `EDGE_PROJECT_DIR` → the `~/.claude/projects/`
convention for this host's `$HOME`); the session in course is excluded by default
(`CLAUDE_CODE_SESSION_ID`) — never hard-code a host path:

    tools/edge-python tools/quente.py > /tmp/quente-insumo.md

Then get your briefs. Use the **Agent tool** to run the four subagents in parallel and
**block** on all; do not read these surfaces in your own window (the bookkeeping stays out of it):
- **assemble** (`skills/assemble`) → the **curated self-state** (Memento's tattoo): curated
  Direction, what is open / the next bet, the corpus, source orientation, knowledge clusters.
  Invoke it in its **`/load` aperture** — the full active state, not just "what's active."
  (Assemble's own entry sweep finds the cursors your driver already advanced — idempotent and
  flock-serialized, so the second pass is a cheap no-op, not a contradiction.)
- **delta** (`skills/delta`) → the **world's new**: what is new in the mentee's
  Mundo / Atividade / Voz. May be empty — it never gates the wake.
- **recall** (`skills/recall`) → the **memory-salient**: space-0 push + **Persona do mentee** +
  (on employment wakes) **semantic dual-entry** seeded by standing objective (predispatch appends
  it; marker names corpus vs embedder if DARK). Rooted at space-0; dark on graph outage — never
  gates the wake. Never fused with delta (ADR-0014). **Portfolio** is stamped once by the
  entry-driver on `--origin user_requested` via `compose_portfolio_recall_brief` — sole portfolio
  owner. Fan recall subagent only for map-blind deepen if needed; do not re-render portfolio
  (Finding C).
- **quente** (`skills/quente`) → the **hot threads** (o SENTIR passivo): the live threads of the
  last K substantial sessions, read from `/tmp/quente-insumo.md` (hand the path in the prompt).
  **Always a FRESH subagent, never cached** — o quente de 2h atrás já nasceu morto. Dark when the
  insumo build fails — it never gates the wake (the cold briefs still orient).

You wake holding only these four briefs. Anterograde amnesia: trust nothing not inscribed in them.

## 2. Surface — render the wake to the operator (the one human-facing act)

### 2a. Session liveness first — then inacabada vs ongoing

The unit is **Atividade** (employment: finalidade + estado), **not** a chat thread / fio.
Before soft orientation, classify work from **quente** + portfolio against **session liveness**.
The current session is often the most relevant heat — that is correct — but the operator is
**already executing it**. Do not hijack that relevance into "debt to resume."

#### Two different signals (do not collapse them)

| Label | When | What it means | Surface |
|-------|------|---------------|---------|
| **ONGOING** | The session that carries the Atividade is **still open** (live / current / not closed) | Operator is already in it. Relevance yes; **not** unfinished debt. | **Acknowledge** in orientation: name the Atividade, keep it in mind when choosing next move. **Do not** open the hard "clear não passa" block for it. **Do not** recommend "retomar" as if the work were abandoned. |
| **INACABADA** | The session that carried the Atividade is **closed** (often days ago) and the employment never got a durable close | Mid-flight work died with the chat. Debt. | Hard block (§2a-hard). *clear não passa* for **that** dead session's residue. |

**Inacabada requires a dead/closed session.** Open session ⇒ at most **ONGOING**, never INACABADA.
Closed session + mid-flight employment without durable close ⇒ **INACABADA**.
Settled / parked / durable ⇒ neither (normal history / standing bet).

#### §2a-hard — only INACABADA (clear FAIL on a closed session)

**Test (only applies to closed sessions):** *"If someone cleared that **already-closed**
conversation's residue, would they lose an Atividade that never got a durable close
(commit / artefact / kernel / portfolio close)?"*
- **PASS** → settled, parked, or durable.
- **FAIL** → **ATIVIDADE INACABADA**. Incisive. Not "fio quente." Not "ongoing."

When any INACABADA exists, open the surface with a hard block (above soft next-move):

1. **Name the Atividade** — finalidade, ref if known; what was mid-flight. Session is the
   *closed scene*, not the noun.
2. **Say the cost** — *"sessão fechada sem close da Atividade — clear não passa; retomar X ou
   abandonar/fechar explícito."*
3. **Prefer resume-or-close of INACABADA** over shiny new work — **unless** the operator is
   already in an **ONGOING** session whose live employment is the right focus (then next move
   serves the ongoing; inacabadas stay listed as debt, not the hijack of attention).
4. **Do not collapse** INACABADA into open bet, fio, or ONGOING.

#### §2a-ongoing — acknowledge, do not sequester

When quente/predispatch show **ONGOING** Atividade(s) (open session = most relevant heat):

1. **Name them plainly** as ongoing — *"você já está nisto: …"*
2. **Hold them as context** for the recommended next move (prefer moves that serve or
   consciously pause that employment — not a cold jump that pretends it does not exist).
3. **Never** re-label ongoing as inacabada / clear-FAIL / "retomar".
4. Ongoing is **information for choice**, not a second hard-debt block.

Signals of **closed-session INACABADA**: last turns mid-step, no done receipt, session no
longer open, no durable close.
Signals of **ONGOING**: session still open / is the wake host or a live concurrent session;
operator still driving that employment.
Not debt: parked ("amanhã"), durable on disk/log, Direction/kernel standing bets.

If quente marks `sessão: aberta → ongoing` vs `sessão: fechada → clear FAIL`, **copy that
split up** — do not re-soften inacabada or re-harden ongoing.

### 2b. Orientation (after §2a)

Present a tight orientation, **not a state dump**:
- **Where ed left off** — curated Direction + the open bet (from assemble).
- **O que está quente** (from quente) — heat narrative with state table (**Atividade · sessão
  aberta|fechada · ongoing|inacabada|settled · clear**). Fios = how heat is told; employment =
  Atividade. Ongoing acknowledged; inacabada already led if any.
- **What's new** — the world delta (from delta), or "nothing new" stated plainly.
- **What you hold** — recall: objective, live bets, open Atividades, salient Artefatos; weave,
  do not dump.
- **The live intersection** — the one theme ed *would* pursue as autonomous beat: deep domain
  insight × mentee's live work, named as the decision not yet made — **with ongoing employment
  held in mind**.
- **Awaiting your word (Voz)** — the latest published artefatos the mentee has NOT
  reacted to yet (published slugs minus `voz.comment` target_refs; last 3, newest
  first), each named with its blog link: "estes saíram e ainda não ouviram de você".
  Silence is a signal the mentor respects — the wake puts them on the table once,
  never nags:

```sh
tools/edge-python <<'PY'
import sys; sys.path.insert(0, "tools")
import eventlog
pub = [(e.get("payload") or {}).get("slug") for e in eventlog.read(types=["artefato.published"])]
heard = {(e.get("payload") or {}).get("target_ref") for e in eventlog.read(types=["voz.comment"])}
for slug in [s for s in pub if s and s not in heard][-3:][::-1]:
    print(f"awaiting Voz: {slug} → http://127.0.0.1:8766/")
PY
```

Lead with the **single recommended next move** — **state it, do not run it.**  
Priority: serve/acknowledge **ONGOING** when that is where the operator already is; only push
resume-or-close of **INACABADA** as the lead when no live session owns the focus (or the
operator overrules). In prose, never a multiple-choice box.

### First-run / onboarding wake (no agent.yaml yet)

If `state/bootstrap.json` exists and phenotype `agent.yaml` is absent (or onboarding incomplete):

1. Use bootstrap `backfill_days` for assemble/sweep lookback.
2. Read secrets via onboarding inventory (names only).
3. After the four briefs, stamp the **mentor insumo** (wake package, **no Direction**):

```sh
tools/edge-python <<'PY'
import onboarding, pathlib, os
home = pathlib.Path(os.environ.get("EDGE_HOME", ".")).expanduser()
boot = onboarding.load_bootstrap(home)
inv = onboarding.inventory_secrets(onboarding.secrets_dir(home))
delta = onboarding.secrets_delta(home, inv)
# fill assemble/quente/delta/recall texts from the briefs you fanned
text = onboarding.compose_insumo(
    home=home, bootstrap=boot, inventory=inv, secrets_delta_=delta,
    assemble_text="…", quente_text="…", delta_text="…", recall_text="…")
onboarding.write_insumo(home, text)
onboarding.stamp_secrets_cursor(home, inv)
print("insumo →", onboarding.insumo_path(home))
PY
```

4. Recommended next move: **`/ed-mentor`** with that insumo — not production beat.

### First-run / onboarding wake (no agent.yaml yet)

If `state/bootstrap.json` exists and phenotype `agent.yaml` is absent (or onboarding incomplete):

1. Use bootstrap `backfill_days` for assemble/sweep lookback.
2. Read secrets via onboarding inventory (names only).
3. After the four briefs, stamp the **mentor insumo** (wake package, **no Direction**):

```sh
tools/edge-python <<'PY'
import onboarding, pathlib, os
home = pathlib.Path(os.environ.get("EDGE_HOME", ".")).expanduser()
boot = onboarding.load_bootstrap(home)
inv = onboarding.inventory_secrets(onboarding.secrets_dir(home))
delta = onboarding.secrets_delta(home, inv)
# fill assemble/quente/delta/recall texts from the briefs you fanned
text = onboarding.compose_insumo(
    home=home, bootstrap=boot, inventory=inv, secrets_delta_=delta,
    assemble_text="…", quente_text="…", delta_text="…", recall_text="…")
onboarding.write_insumo(home, text)
onboarding.stamp_secrets_cursor(home, inv)
print("insumo →", onboarding.insumo_path(home))
PY
```

4. Recommended next move: **`/ed-mentor`** with that insumo — not production beat.

## 3. Halt — do nothing; stand by (the whole point)

This is **not a beat.** Do **not** fan explorers, produce an Artefato, run `skills/report`, or emit
the `intent.kernel` close — those are the beat's autonomous acts (ADR-0009), and wake stops before them.

- **Read-only, fully (CONTRACT C1, hard):** the mentee's world is read-only **and** wake writes no
  state of its own beyond the mechanical `dispatch.open` wake stamp (ADR-0016 — the entry-driver's
  bookkeeping, not a judgment write) and the throwaway `/tmp/quente-insumo.md`. Wake reads and
  renders — nothing else.
- **Everything downstream is operator-directed.** The next move is the operator's word. When they
  give it, run the skill it names under command — `/ed-mentor` (legacy `/ed-grill`), `/ed-report`,
  the full beat, a direct question — each within its own contract. Until then, **wait.**
