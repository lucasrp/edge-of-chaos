"""briefing-lifecycle gate — the EXECUTABLE form of docs/briefing-lifecycle-audit.md.

The audit (Memento's tattoo, ADR-0009) says a `/goal` (a certified edge) is not done until the
briefing matches the per-stage expectations. That doc is prose fed to a human reviewer; this file
is the DURABLE, machine-checked gate: it composes the briefing at the three lifecycle stages and
asserts the audit's per-section `required` / `expected-empty` table at each. HEALTHY must imply the
edge has an identity, knows its sources, and — after a grill / after beats — carries the steer and
the corpus it should.

Each stage builds from a THROWAWAY tree (CONTRACT C1 — never the real `state/`): a fresh temp log,
a temp `agent.yaml` (identity + a non-empty `sources` list + `ground_truth.documents` pointing at
temp CONTEXT glossaries), and the CANONICAL `seeds/memory/` doctrine COPIED into a temp `memory/`
(so the content is the genuine personality/method/canone doctrine while `state_dir` resolves to the
temp tree, not real `state/idiom.md`). Offline: `clusters=None` (no graph), the roster is read from
the versioned `tests/fixtures/roster.agent.yaml` (the DECLARED roster the audit's stage-(i) row 4
demands).

Host-independence: the genotype has, BY CONTRACT, no `agent.yaml` and no `memory/` — both are
outputs of onboarding. Reading them at import time made this whole module fail to LOAD on a
genotype (`unittest.loader._FailedTest`, hiding every test here). `seeds/memory/` is the versioned
seed the install's `memory/` is provisioned FROM, and `tests/fixtures/roster.agent.yaml` the
versioned declared phenotype — same doctrine, same roster, on any host.
"""
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog    # noqa: E402
import briefing    # noqa: E402
import grill_gate  # noqa: E402

ROSTER_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "roster.agent.yaml"
SEEDS_MEMORY = REPO / "seeds" / "memory"

# The DECLARED source roster, read READ-ONLY from the versioned fixture (never state/, never the
# host's agent.yaml). The audit's stage-(i) row 4 requires the briefing inject the DECLARED roster,
# not a generic inference — the fixture is that declaration, identical on every host.
REAL_ROSTER = briefing.source_roster(agent_yaml=ROSTER_FIXTURE)


def _genotype(tmp):
    """Build a throwaway genotype tree under `tmp` and return (agent_yaml, memory, log).

    - memory/: the canonical doctrine from `seeds/memory/` (personality + method + canone) COPIED
      in, so the briefing's tattoos carry the genuine content while `state_dir`
      (memory.parent/state) stays the temp tree — no read of the real `state/idiom.md`
      (CONTRACT C1).
    - agent.yaml: full identity (name/mission/voice — the personality `.tpl` substitutes them),
      a non-empty `sources` list, and `ground_truth.documents` pointing at a temp CONTEXT glossary.
    - log: a path under tmp (the fresh, empty log each stage starts from).
    """
    tmp = Path(tmp)
    memory = tmp / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    for doc in ("personality.md", "method.md", "canone.md"):
        shutil.copy(SEEDS_MEMORY / doc, memory / doc)
    (tmp / "state").mkdir(parents=True, exist_ok=True)  # temp state_dir; intentionally no idiom.md

    glossary = tmp / "project-CONTEXT.md"
    glossary.write_text("# Project canon\n\n"
                        "**confrontação** — the act that yields a decision.\n\n"
                        "**beat** — the edge's work cycle.")
    agent_yaml = tmp / "agent.yaml"
    agent_yaml.write_text(textwrap.dedent("""\
        name: ed
        mission: "Mentor to the edge-of-chaos PM: compare intent with runtime evidence."
        voice: "Direct, technical, skeptical."
        sources:
          - name: exa
            kind: api
            description: "Neural/semantic web + paper search."
          - name: github
            kind: cli
            description: "The mentee's repos and the ecosystem, read-only."
        ground_truth:
          inject_into_load: true
          documents:
        """) + f'    - "{glossary}"\n')
    return agent_yaml, memory, tmp / "log.jsonl"


def _compose(agent_yaml, memory, log, **kw):
    """Compose the briefing offline (clusters=None, real declared roster), genotype injected."""
    return briefing.compose_briefing(
        log=log, clusters=None, roster=REAL_ROSTER,
        agent_yaml=agent_yaml, memory=memory, **kw)


class StageIFreshInstall(unittest.TestCase):
    """Stage (i) — fresh install (clone + `edge-apply`, no grill, no beat): a FRESH empty log.

    The audit's stage-(i) acceptance FAILS if any of {Personality, Method, Idiom, the real Source
    roster} is empty or generic. The log-fed sections (Objective/Direction/Direcionamento/Corpus)
    MUST render their HONEST empty marker — present, not crashed, never a silent blank."""

    def test_fresh_install_meets_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_yaml, memory, log = _genotype(tmp)
            self.assertEqual(eventlog.read(log=log), [])  # fresh: empty log

            out = _compose(agent_yaml, memory, log)

            # --- genotype identity head — REQUIRED, non-empty (a blank here is a lobotomy) ---
            self.assertIn("### Personality", out)
            self.assertIn("distrust the rationality, not the person", out)  # real personality doctrine
            self.assertIn("### Method", out)
            # the method doctrine is anchored by its SUBSTANCE, not by a label: e4db5de rewrote
            # seeds/memory/method.md from "Feynman Method" to "The Method — o abate". The two
            # engines identify the text; the old bigram identified only the old heading
            # (same anchor test_briefing.py already uses).
            self.assertIn("Feynman", out)                                   # o motor de derivação
            self.assertIn("o abate", out)                                   # o motor de abate
            # Idiom glossary FLOOR — the temp ground_truth.documents content is injected
            self.assertIn("## Idiom", out)
            self.assertIn("the act that yields a decision", out)            # the temp CONTEXT glossary
            # The REAL declared source roster (never a generic inference)
            self.assertIn("**exa**", out)
            self.assertIn("**github**", out)
            self.assertTrue(any("session" in line.lower() for line in out.splitlines()
                                if line.startswith("- ")))                  # native source, additive floor

            # --- log-fed sections — HONEST empty markers (present, not crashed, not silent) ---
            low = out.lower()
            self.assertIn("no confirmed objective yet", low)
            self.assertIn("no direction set yet", low)
            self.assertIn("no direcionamento report yet", low)
            self.assertIn("no corpus yet", low)
            self.assertIn("nothing open recorded yet", low)                 # the open/next-bet empty marker


class StageIIAfterGrill(unittest.TestCase):
    """Stage (ii) — + one simulated grill on the temp log. Additionally FAILS if Objective,
    Direction, or Direcionamento is still empty (the grill's set_objective / set_direction-or-propose
    / report_direction must have fed them — issue #26's done-criterion, enforced by grill_gate)."""

    def test_after_grill_meets_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_yaml, memory, log = _genotype(tmp)

            # simulate the grill — steers + leveling-state floor land on the temp log
            eventlog.set_objective("ship the durable steer before tuning the grill",
                                   rationale="says mission A, behavior shows B", log=log)
            eventlog.set_direction("d1", "tighten the close path", kind="priority", log=log)
            eventlog.propose("d2", "explore the source-feedback loop", log=log)
            eventlog.report_direction("the live steer: anchor on the close, defer the loop", log=log)
            import grill_writeback
            grill_writeback.leveling(
                "diario", "sem update de persona; residual = lifecycle audit",
                root=Path(tmp) / "leveling", log=log)
            # the wayfind MAPA — grill_gate's fifth stage-(ii) piece (operator 2026-07-28):
            # Direction is the direção, the map is the MAPA, and every mentor updates both.
            eventlog.open_map(operacao="edge", titulo="Mapa do close",
                              rationale="o mapa que acompanha o steer do close",
                              dispatch_id="lifecycle-map", author="grill", log=log)

            # the post-grill gate confirms no stage-(ii) gap remains
            self.assertEqual(grill_gate.grill_complete(log=log), [])
            out = _compose(agent_yaml, memory, log)

            # the genotype head is still REQUIRED at this stage
            self.assertIn("### Personality", out)
            self.assertIn("### Method", out)
            self.assertIn("## Idiom", out)

            # the three stage-(ii) sections are now NON-EMPTY (the grill fed them)
            self.assertIn("ship the durable steer before tuning the grill", out)        # Objective
            self.assertNotIn("no confirmed objective yet", out.lower())
            self.assertIn("tighten the close path", out)                                # Direction (set)
            self.assertIn("explore the source-feedback loop", out)                      # Direction (proposed)
            self.assertNotIn("no direction set yet", out.lower())
            self.assertIn("the live steer: anchor on the close, defer the loop", out)   # Direcionamento
            self.assertNotIn("no direcionamento report yet", out.lower())


class StageIIIAfterTwoBeats(unittest.TestCase):
    """Stage (iii) — + two beats in sequence on the temp log. Additionally FAILS if Corpus has < 2
    Artefatos, any published Artefato lacks its kernel (C3 debt), or the Open/next-bet is empty.

    Each beat publishes ONE Artefato with its intent kernel via publish_artefato_atomic (the
    producer path that cannot ship C3 debt — published + intent.kernel in one indivisible write)."""

    def test_after_two_beats_meets_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_yaml, memory, log = _genotype(tmp)
            # a grill first (the realistic order), so the steer is present going into the beats
            eventlog.set_objective("ship the durable steer", log=log)
            eventlog.set_direction("d1", "tighten the close path", kind="priority", log=log)
            eventlog.report_direction("the live steer", log=log)

            # two beats — each an Artefato + its kernel (atomic, zero C3 debt)
            eventlog.publish_artefato_atomic(
                "beat-one-report", "open: read-budget unnamed; bet: name it next beat", log=log)
            eventlog.publish_artefato_atomic(
                "beat-two-report", "open: source loop unproven; bet: prove it next beat", log=log)

            # --- the stage-(iii) invariants the audit enforces ---
            self.assertGreaterEqual(eventlog.corpus_at(log=log).__len__(), 2)  # ≥ 2 Artefatos
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])   # zero C3 debt

            out = _compose(agent_yaml, memory, log)

            # Corpus — both Artefatos with their why, most-recent-first
            self.assertIn("beat-one-report", out)
            self.assertIn("beat-two-report", out)
            self.assertLess(out.index("beat-two-report"), out.index("beat-one-report"))
            self.assertNotIn("no corpus yet", out.lower())
            self.assertNotIn("C3 debt", out)                                   # no debt surfaced

            # Open / next bet — the LATEST beat's kernel, non-empty
            self.assertIn("open: source loop unproven; bet: prove it next beat", out)
            self.assertNotIn("nothing open recorded yet", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
