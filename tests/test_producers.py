"""Story S13 — the producer-skills (report / map / plan).

The producer roster is open; these three are the producer-skills the beat round-robins
(roster = ["report", "map", "plan"], agreed with S12). Each is a THIN specialization
(ADR-0012): it does not write its own loop. It references the shared scaffold
(`skills/_shared/scaffold.md`, the loop1/loop2 role-slots) and the shared pipeline
(`skills/_shared/pipeline.md`, the close at exit), declares its own SLOT MAPPING
(what its gather-grounding / converge / diverge are) and its visual idiom, draws blocks
from the canonical palette (tools/render.py) and publishes through the close
(tools/publisher.py) — never an inline eventlog.publish_artefato snippet.

The load-bearing invariants this test pins:
  * each producer SKILL.md exists, references the scaffold + the pipeline (the shared docs)
    and the publisher (tools/publisher.py);
  * each declares a slot mapping (mentions gather-grounding / converge / diverge or the
    slot idea), so report-specifics live HERE, not welded into the scaffold;
  * report/SKILL.md NO LONGER mandates a fixed section order — sections are FREE (the
    welded "first / penultimate / last" section phrases are forbidden);
  * map declares a visual-by-nature idiom (diagram / graph) so the visualization dim never
    false-fails it; plan declares a next-steps-grid / flow idiom;
  * the rename is honored everywhere: "evidence", never "insumos".

Grep-based, case-insensitive: the docs are prose, so the test reads them and asserts
presence/absence of the load-bearing tokens.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"

# The open producer roster the beat round-robins (agreed with S12).
PRODUCERS = ("report", "map", "plan")

# The shared contracts every producer conforms to.
SCAFFOLD_REF = "scaffold"      # skills/_shared/scaffold.md (loop1/loop2 role-slots)
PIPELINE_REF = "pipeline"      # skills/_shared/pipeline.md (the close at exit)
PUBLISHER_REF = "tools/publisher.py"  # publish through the close, not an inline snippet

# The ENFORCED close path: publish only ever happens via close.run_close (it runs the genus
# + both blind reviewers, then publishes on pass with the minted proof). A bare
# `publisher.publish(` call is now the FORBIDDEN back door — publish_fn refuses without the
# proof only run_close mints, so a direct publisher.publish raises.
ENFORCED_CLOSE_REF = "close.run_close"
FORBIDDEN_BARE_PUBLISH = "publisher.publish("

# The slot idea a producer's mapping must declare (role-defined slots from the scaffold).
SLOT_TOKENS = ("gather-grounding", "converge", "diverge")

# The fixed-section mandates report/SKILL.md must NO LONGER carry — sections are FREE.
# (Only positive welds: a NAMED/ORDERED section requirement. The de-welding prose may
# still say "never mandatory sections" / "sections are FREE" — that is the negation, not
# a mandate, so we forbid only the order/position welds, never the bare word "section".)
FORBIDDEN_SECTION_MANDATES = (
    "first section",
    "primeira seção",
    "penultimate",
    "section (first)",
    "glossário (last)",
    "glossary (last)",
    "fixed section order",
    "in this order",
    "section order",
)


def _path(producer):
    return SKILLS / producer / "SKILL.md"


class ProducersFillSlotsAndExitThroughClose(unittest.TestCase):
    def setUp(self):
        self.texts = {}
        for p in PRODUCERS:
            path = _path(p)
            self.assertTrue(path.exists(), f"missing producer skill: {path}")
            self.texts[p] = path.read_text(encoding="utf-8").lower()

    def test_each_producer_references_the_shared_contracts(self):
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn(SCAFFOLD_REF, t, f"{p} does not reference the shared scaffold")
            self.assertIn(PIPELINE_REF, t, f"{p} does not reference the shared pipeline")

    def test_each_producer_publishes_through_the_publisher(self):
        for p in PRODUCERS:
            self.assertIn(PUBLISHER_REF, self.texts[p],
                          f"{p} does not publish via {PUBLISHER_REF}")

    def test_each_producer_does_not_inline_publish_artefato(self):
        # publish through the close, NOT an inline eventlog.publish_artefato snippet.
        for p in PRODUCERS:
            self.assertNotIn("eventlog.publish_artefato", self.texts[p],
                             f"{p} inlines an eventlog.publish_artefato snippet")

    def test_each_producer_routes_through_the_enforced_close(self):
        # the close is ENFORCED: publish happens ONLY via close.run_close (it mints the
        # passing-review proof publisher.publish now requires).
        for p in PRODUCERS:
            self.assertIn(ENFORCED_CLOSE_REF, self.texts[p].replace(" ", ""),
                          f"{p} does not route through the enforced close ({ENFORCED_CLOSE_REF})")

    def test_no_producer_shows_a_bare_publisher_publish_call(self):
        # a direct publisher.publish(...) now RAISES (no passing-review proof) — the skill
        # must never show that forbidden back door; it publishes via close.run_close.
        for p in PRODUCERS:
            self.assertNotIn(FORBIDDEN_BARE_PUBLISH, self.texts[p].replace(" ", ""),
                             f"{p} shows a forbidden bare publisher.publish( call")

    def test_each_producer_declares_a_slot_mapping(self):
        # mentions the slot idea (gather-grounding / converge / diverge or "slot").
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn("slot", t, f"{p} declares no slot mapping")
            self.assertTrue(any(s in t for s in SLOT_TOKENS),
                            f"{p} names none of the role slots {SLOT_TOKENS}")

    def test_each_producer_draws_from_the_canonical_palette(self):
        # blocks come from the one palette (tools/render.py), not freeform HTML.
        for p in PRODUCERS:
            self.assertIn("tools/render.py", self.texts[p],
                          f"{p} does not draw blocks from the canonical palette")

    def test_report_no_longer_mandates_a_fixed_section_order(self):
        # sections are FREE — the welded section-order mandate is gone.
        report = self.texts["report"]
        for mandate in FORBIDDEN_SECTION_MANDATES:
            self.assertNotIn(mandate, report,
                             f"report still mandates a fixed section: {mandate!r}")

    def test_map_declares_a_visual_by_nature_idiom(self):
        # map is visual by nature (so the visualization dim never false-fails it).
        m = self.texts["map"]
        self.assertTrue("diagram" in m or "graph" in m,
                        "map declares no visual idiom (diagram/graph)")

    def test_plan_declares_a_next_steps_grid_or_flow_idiom(self):
        plan = self.texts["plan"]
        self.assertTrue("next-steps-grid" in plan or "flow" in plan,
                        "plan declares no next-steps-grid / flow idiom")

    def test_uses_evidence_not_insumos_in_every_producer(self):
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn("evidence", t, f"{p} does not use 'evidence'")
            self.assertNotIn("insumos", t, f"{p} still uses 'insumos'")


# The proof is bound to a sha256 digest of the EXACT publish payload (close.proof_digest):
# slug + spec(content) + intent + cites + proposes + distills + skill. run_close mints the
# digest from the `artefato` dict it is handed (artefato.get(field) per field); verify_proof
# (at the publish seam) recomputes it from what is actually published. So the `artefato` dict
# the snippet passes to run_close MUST carry EVERY proof-bound field — including `skill` and
# `distills` — or the minted digest is over None/None while the publisher verifies the real
# values → mismatch → publish raises. And the publish_fn must publish FROM its `art` argument
# (read the fields off `art`), not from separately-captured locals, so the published payload
# is provably the one the proof was minted over. S2 (E1b): `dispatch_id` joined the bound set —
# same class as slug (persisted field = digested field), read from the wake's DISPATCH_ID line.
# `lineage` has been digest-bound since Cortex-v1 brick-1 but was missing from this helper set
# (pre-existing test gap, closed at the S2 codex gate).
PROOF_BOUND_ARTEFATO_FIELDS = ("skill", "distills", "slug", "intent", "cites", "proposes",
                               "dispatch_id", "lineage")


class ProducerCloseSnippetMintsOverPublishPayload(unittest.TestCase):
    """The producer close snippet must mint the proof over the EXACT payload it publishes:
    every proof-bound field is in the `artefato` dict run_close digests, and the publish_fn
    reads from its `art` argument (not separately-captured values)."""

    def setUp(self):
        # raw (case-preserving) text — we assert on the literal snippet code, not prose.
        self.texts = {p: _path(p).read_text(encoding="utf-8") for p in PRODUCERS}

    def _artefato_literal(self, text):
        """Return the `artefato={...}` dict literal passed to run_close (the snippet builds it
        once as a name, then hands it to close.run_close)."""
        marker = "artefato={"
        start = text.find(marker)
        self.assertNotEqual(start, -1, "no artefato={...} literal in snippet")
        # match to the closing brace of the literal
        i = start + len(marker)
        depth = 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        return text[start:i]

    def test_artefato_carries_every_proof_bound_field(self):
        # run_close mints from artefato.get(field); the dict must carry all proof-bound fields
        # (skill, distills, slug, intent, content, cites, proposes) so the mint digest == the
        # verified digest. `content` is the artefato dict's name for the digest's `spec`.
        for p in PRODUCERS:
            lit = self._artefato_literal(self.texts[p])
            for field in ("skill", "distills", "slug", "intent", "content", "cites", "proposes",
                          "dispatch_id", "lineage"):
                self.assertIn(f"'{field}'", lit,
                              f"{p}'s run_close artefato omits proof-bound field {field!r} "
                              f"(minted digest would not bind to the publish payload)")

    def test_publish_fn_reads_payload_from_its_art_argument(self):
        # the publish_fn must publish FROM `art` (its received artefato), reading the
        # proof-bound fields off it — not from separately-captured locals — so the published
        # payload is provably the one the proof was minted over.
        for p in PRODUCERS:
            t = self.texts[p]
            for field in PROOF_BOUND_ARTEFATO_FIELDS:
                self.assertIn(f"art['{field}']", t,
                              f"{p}'s publish_fn does not read {field!r} off its `art` "
                              f"argument (must publish from the minted artefato)")
            # the proof rides as verdict=
            self.assertIn("verdict=proof", t.replace(" ", ""),
                          f"{p}'s publish_fn does not pass verdict=proof")


class ProducersWireRealReProduction(unittest.TestCase):
    """#30 — the rich-rite gate must FORCE depth, not only hard-fail. The producer close snippet
    must wire `improve_fn` into `close.run_close` (run_close already loops IMPROVE_ROUNDS=2): so a
    genus/reviewer strike (incl. a rich-rite floor violation) re-PRODUCES a richer draft from the
    feedback, rather than dead-ending in a hard-fail. A `produce_fn` that just returns the static
    artefato is no longer enough on its own."""

    def setUp(self):
        self.texts = {p: _path(p).read_text(encoding="utf-8") for p in PRODUCERS}

    def test_each_producer_wires_improve_fn(self):
        for p in PRODUCERS:
            self.assertIn("improve_fn", self.texts[p].replace(" ", ""),
                          f"{p} does not wire improve_fn into run_close (a strike would only "
                          "hard-fail, never re-produce richer — #30)")

    def test_each_producer_improve_fn_takes_feedback(self):
        # improve_fn(artefato, feedback) — run_close hands it the reviewers' rationales+strikes,
        # which it uses to REVISE the draft. The signature must accept the feedback.
        for p in PRODUCERS:
            t = self.texts[p].replace(" ", "")
            self.assertTrue("improve_fn=lambda" in t or "defimprove_fn" in t,
                            f"{p}'s improve_fn is not defined to receive the feedback")
            self.assertIn("feedback", self.texts[p].lower(),
                          f"{p} does not mention the feedback the improve_fn revises from")


class PipelineDocumentsTheReProductionWiring(unittest.TestCase):
    """#30 — the shared pipeline must document that the producer wires `improve_fn` so the close's
    improve stage (IMPROVE_ROUNDS) actually re-produces from feedback — the gate forces depth, not
    only a hard-fail. Pin the load-bearing tokens so the wiring cannot go dormant in prose."""

    def setUp(self):
        self.text = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8").lower()

    def test_pipeline_states_the_producer_wires_improve_fn(self):
        self.assertIn("improve_fn", self.text)

    def test_pipeline_ties_re_production_to_the_gate_forcing_depth(self):
        # the WHY: without the wiring a gate violation only hard-fails; with it, the close
        # re-produces a richer draft. The rich-rite floor is named as a strike source.
        self.assertIn("rich-rite", self.text)
        self.assertTrue("hard-fail" in self.text or "hard fail" in self.text,
                        "pipeline must contrast re-production against a bare hard-fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
