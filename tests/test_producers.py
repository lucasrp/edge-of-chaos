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


if __name__ == "__main__":
    unittest.main(verbosity=2)
