"""Phase 4 of the shared rich producer protocol — the falsifiable EXTENSIBILITY PROOF.

The claim: "a new producer is added by DECLARATION only." Adding `critique` required ONLY (a) one entry in
`producer_descriptor.DESCRIPTORS` and (b) a tiny skill file — with ZERO changes to the shared MECHANISM
(`tools/close.py`, `tools/render.py`, `skills/_shared/*`, and the generic evaluator/predicate code in
`producer_descriptor.py`). These tests prove the generic evaluator enforces critique's NOVEL declared floor
purely from the descriptor, that the descriptor still cannot buy critique out of the genus rich rite, and —
the META assertion — that no per-producer special-casing for "critique" leaked into the shared seam.

critique's floor is novel vs map/plan/discovery: it conjoins TWO `min_blocks_of` obligations over block
types no other descriptor names — a side-by-side comparison (`comparison-table`/`comparison`) AND a marked
uncertainty (`gap-table`/`gap-marker`). No new predicate, no new block, no new branch: declaration only.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import producer_descriptor as pd  # noqa: E402


def _art(blocks, *, cites=None):
    # prepend explanatory prose so a visual/labeled block (e.g. comparison-table) doesn't trip R0
    # (visual-without-prose) — which, being dominant, would SUPPRESS the presentation floor these tests
    # exercise. R0 must be clean for the R1 presentation violation to surface. The prose also states the
    # comparison-table's latency figures (300ms vs <100ms) so R0-for-values is satisfied too.
    return {
        "skill": "critique",
        "content": {"sections": [{"title": "s", "blocks": [
            _para("The critique weighs the claim: measured latency is 300ms against the <100ms bar it owes.")
        ] + blocks}]},
        "intent": "open: x; bet: y",
        "cites": cites if cites is not None else [
            {"ref": "r", "snippet": "s", "kind": "mundo", "relevant": True}],
        "proposes": [{"body": "b", "kind": "thread"}],
    }


def _para(t):
    return {"type": "paragraph", "text": t}


def _comparison_table():
    # the verdict surface — the claim weighed side by side against the bar it should meet.
    return {"type": "comparison-table", "headers": ["Aspect", "Claim", "Bar it owes"],
            "rows": [{"cells": ["latency", "300ms", "<100ms"]}]}


def _gap_marker():
    # the marked uncertainty — what the critique could not settle.
    return {"type": "gap-marker", "text": "unverified whether this holds under concurrent load"}


class GenericEvaluatorEnforcesTheNovelFloor(unittest.TestCase):
    """The generic evaluator enforces critique's declared floor from the descriptor ALONE."""

    def test_critique_is_registered_by_declaration(self):
        self.assertIsNotNone(pd.descriptor_for("critique"))
        self.assertEqual(pd.require_descriptor("critique"), pd.DESCRIPTORS["critique"])

    def test_critique_floor_uses_block_types_no_other_descriptor_does(self):
        # novelty guard: the comparison + gap block types in critique's floor are used by NO other
        # descriptor's require list — the evaluator handles a genuinely new SHAPE.
        critique_types = {t for r in pd.DESCRIPTORS["critique"]["require"] for t in r.get("types", [])}
        self.assertEqual(critique_types, {"comparison-table", "comparison", "gap-table", "gap-marker"})
        for other, desc in pd.DESCRIPTORS.items():
            if other == "critique":
                continue
            other_types = {t for r in desc.get("require", []) for t in r.get("types", [])}
            self.assertEqual(critique_types & other_types, set(),
                             f"{other} shares floor block types with critique")

    def test_satisfying_floor_passes_genus(self):
        # R0 (S2): a visual/labeled structure owes accompanying prose — a real critique explains its
        # comparison in prose, so the conformant fixture carries a paragraph alongside the table.
        v = close.check_genus(_art([
            _para("The latency claim is weighed against the bar it owes, and the open risk is named."),
            _comparison_table(), _gap_marker()]))
        self.assertFalse(any(x.startswith("presentation") for x in v), v)
        self.assertEqual(v, [])  # nothing owed — clean close

    def test_missing_comparison_fails_with_the_right_presentation_violation(self):
        v = close.check_genus(_art([_gap_marker()]))           # has the gap, lacks the comparison
        self.assertIn("presentation:min_blocks_of(comparison-table/comparison,1)", v)

    def test_missing_uncertainty_fails_with_the_right_presentation_violation(self):
        v = close.check_genus(_art([_comparison_table()]))      # has the comparison, lacks the gap
        self.assertIn("presentation:min_blocks_of(gap-table/gap-marker,1)", v)


class DescriptorAddsNeverSubtracts(unittest.TestCase):
    """The Phase-4 restatement of the hard invariant: the declaration ADDS presentation; it can never
    buy critique out of the content-relative genus rich rite."""

    def test_developed_prose_critique_missing_a_move_still_fails_genus(self):
        # 3 prose blocks → the rich rite is owed. The presentation floor is FULLY satisfied
        # (comparison-table + gap-marker), yet a developed-prose critique with no derivation/lineage
        # marker and no external cite STILL fails genus on the missing cognitive moves.
        v = close.check_genus(_art([
            _para("plain prose with no cognitive markers at all here"),
            _para("more plain prose carrying none of the four moves"),
            _para("still more ordinary prose, nothing marked"),
            _comparison_table(), _gap_marker(),
        ], cites=[]))                                            # no external cite → external-frame owed
        self.assertTrue(any(x.startswith("rich-rite") for x in v), v)       # genus floor still bites
        self.assertFalse(any(x.startswith("presentation") for x in v), v)   # presentation IS satisfied


class SeamStayedGeneric(unittest.TestCase):
    """The META proof: no per-producer special-casing for `critique` landed in the shared MECHANISM.
    The only place the string `critique` may appear is inside the DESCRIPTORS dict (the declaration)."""

    def test_shared_mechanism_files_never_name_critique(self):
        for rel in ("tools/close.py", "tools/render.py", "skills/_shared/scaffold.md"):
            text = (REPO / rel).read_text()
            self.assertNotIn("critique", text,
                             f"{rel} names 'critique' — a per-producer branch leaked into the seam")

    def test_descriptor_module_names_critique_only_inside_the_DESCRIPTORS_dict(self):
        lines = (REPO / "tools" / "producer_descriptor.py").read_text().splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith("DESCRIPTORS = {"))
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")  # the dict's closing brace
        occurrences = [i for i, ln in enumerate(lines) if "critique" in ln]
        self.assertTrue(occurrences, "critique must be declared in producer_descriptor.py")
        for i in occurrences:
            self.assertTrue(start < i < end,
                            f"producer_descriptor.py line {i + 1} names 'critique' OUTSIDE the "
                            f"DESCRIPTORS dict — the generic evaluator/predicate code must stay producer-blind")


if __name__ == "__main__":
    unittest.main(verbosity=2)
