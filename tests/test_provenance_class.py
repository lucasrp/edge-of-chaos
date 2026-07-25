"""provenance_class + CX-1 (ontologia-cortex-v2 §0) — the THIRD provenance axis, sibling to tier.

AXIS — provenance_class ∈ {computed, asserted, llm_judged, extracted} per edge type/label:
  computed   = Evidence plane (bearing; source-yield observation) — the ONLY class a verdict
               rollup may consume.
  asserted   = Structural plane (mentions/distills/cites/supersedes/via/deriva_de/tem/spine).
  llm_judged = Judgment plane (assesses) — rigor teto lead, NEVER computed.
  extracted  = Semantic plane (relates_to/in_community) — AND the fail-safe for unknown types
               (never computed-by-default, mirroring tier_for's never-asserted-by-default).

CX-1 (invariante mestra): the scoreboard/verdict consumes ONLY computed bearings;
assert_rollup_computed raises LOUD, naming every offender, if any non-computed item
lands in a rollup.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_provenance as prov  # noqa: E402


class ProvenanceClassIsThePlaneAxis(unittest.TestCase):
    """provenance_class = which plane an edge lives on (§0). ONE derivation, fail-safe extracted."""

    def test_the_enum_is_the_four_planes(self):
        self.assertEqual(set(prov.PROVENANCE_CLASSES),
                         {"computed", "asserted", "llm_judged", "extracted"})

    def test_evidence_plane_is_computed(self):
        # bearing + the source-yield observation: the ONLY rollup-eligible class.
        for t in ("bearing", "observation"):
            with self.subTest(t=t):
                self.assertEqual(prov.provenance_class_for(t), "computed")

    def test_structural_plane_is_asserted(self):
        for t in ("mentions", "distills", "cites", "supersede", "supersedes",
                  "via", "deriva_de", "tem", "spine"):
            with self.subTest(t=t):
                self.assertEqual(prov.provenance_class_for(t), "asserted")

    def test_judgment_plane_is_llm_judged(self):
        self.assertEqual(prov.provenance_class_for("assesses"), "llm_judged")

    def test_semantic_plane_is_extracted(self):
        for t in ("relates_to", "in_community"):
            with self.subTest(t=t):
                self.assertEqual(prov.provenance_class_for(t), "extracted")

    def test_graph_casing_is_normalized(self):
        # neo4j edge types are UPPERCASE (RELATES_TO, MENTIONS, SUPERSEDES) — same class.
        self.assertEqual(prov.provenance_class_for("RELATES_TO"), "extracted")
        self.assertEqual(prov.provenance_class_for("MENTIONS"), "asserted")
        self.assertEqual(prov.provenance_class_for("ASSESSES"), "llm_judged")

    def test_an_unknown_type_defaults_to_extracted(self):
        # fail-safe: unknown is a hypothesis, NEVER computed-by-default.
        self.assertEqual(prov.provenance_class_for("WeirdNewEdge"), "extracted")
        self.assertEqual(prov.provenance_class_for(None), "extracted")

    def test_rigor_teto_llm_judged_and_extracted_never_compute(self):
        # the hard ceiling (§2): no judgment/semantic type may EVER resolve computed.
        for t in ("assesses", "relates_to", "in_community", "AnythingUnknown"):
            with self.subTest(t=t):
                self.assertNotEqual(prov.provenance_class_for(t), "computed")


class CX1RollupGate(unittest.TestCase):
    """CX-1: the ONE gate any scoreboard/verdict must pass its inputs through. All-computed flows
    through unchanged; ANY non-computed item raises LOUD, naming the offenders."""

    def test_all_computed_passes_through_unchanged(self):
        items = [{"edge_type": "bearing", "id": "b1"},
                 {"edge_type": "OBSERVATION", "id": "o1"}]
        self.assertEqual(prov.assert_rollup_computed(items), items)

    def test_one_non_computed_raises_naming_the_offender(self):
        items = [{"edge_type": "bearing", "id": "b1"},
                 {"edge_type": "assesses", "id": "gate-feynman"}]
        with self.assertRaises(ValueError) as ctx:
            prov.assert_rollup_computed(items)
        msg = str(ctx.exception)
        self.assertIn("CX-1", msg)
        self.assertIn("gate-feynman", msg)
        self.assertIn("llm_judged", msg)

    def test_every_offender_is_named_not_just_the_first(self):
        items = [{"edge_type": "assesses", "id": "a1"},
                 {"edge_type": "bearing", "id": "b1"},
                 {"edge_type": "relates_to", "id": "r1"}]
        with self.assertRaises(ValueError) as ctx:
            prov.assert_rollup_computed(items)
        msg = str(ctx.exception)
        self.assertIn("a1", msg)
        self.assertIn("r1", msg)
        self.assertNotIn("b1", msg)

    def test_a_typeless_item_is_an_offender_failsafe(self):
        # no type, no stamp → unknown → extracted → NEVER in a rollup.
        with self.assertRaises(ValueError):
            prov.assert_rollup_computed([{"id": "mystery"}])

    def test_a_stamp_can_demote_but_never_promote(self):
        # an assesses edge stamped "computed" is STILL an offender (rigor teto is structural);
        # a bearing stamped non-computed is an offender too (the stamp demotes, fail-safe).
        with self.assertRaises(ValueError):
            prov.assert_rollup_computed(
                [{"edge_type": "assesses", "provenance_class": "computed", "id": "x"}])
        with self.assertRaises(ValueError):
            prov.assert_rollup_computed(
                [{"edge_type": "bearing", "provenance_class": "llm_judged", "id": "y"}])

    def test_no_plane_can_be_stamp_promoted_into_a_rollup(self):
        # codex adversarial [5]: the promotion attack on EVERY non-computed plane, not just assesses.
        for t in ("relates_to", "in_community", "mentions", "WeirdNewEdge"):
            with self.subTest(t=t):
                with self.assertRaises(ValueError):
                    prov.assert_rollup_computed(
                        [{"edge_type": t, "provenance_class": "computed", "id": "z"}])

    def test_a_stamped_computed_item_without_type_passes(self):
        # a bare annotation carrying only the stamp: computed stamp + no contradicting type → in.
        items = [{"provenance_class": "computed", "id": "b2"}]
        self.assertEqual(prov.assert_rollup_computed(items), items)

    def test_empty_rollup_is_fine(self):
        self.assertEqual(prov.assert_rollup_computed([]), [])

    def test_a_blank_type_key_is_malformed_not_stampable(self):
        # codex adversarial [1]: a type key PRESENT but blank is an unknown type — fail-safe
        # extracted; the computed stamp cannot rescue it (unlike a bare stamped annotation).
        with self.assertRaises(ValueError):
            prov.assert_rollup_computed(
                [{"edge_type": "", "provenance_class": "computed", "id": "blank"}])

    def test_a_malformed_stamp_is_never_silently_dropped(self):
        # codex adversarial [2]: a PRESENT-but-invalid stamp ("extracted " etc.) demotes to the
        # fail-safe — it never falls through to the type derivation as if absent.
        with self.assertRaises(ValueError):
            prov.assert_rollup_computed(
                [{"edge_type": "bearing", "provenance_class": "extracted ", "id": "dirty"}])

    def test_non_dict_members_are_offenders_not_crashes(self):
        # codex adversarial [4]: malformed members raise the NAMED CX-1 error, not AttributeError.
        with self.assertRaises(ValueError) as ctx:
            prov.assert_rollup_computed([None, "a-string"])
        self.assertIn("item[0]", str(ctx.exception))
        self.assertIn("item[1]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
